#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

import time

from collections import deque
from heapq import heappop, heappush
from typing import TypeVar

from aiologic import Condition
from aiologic.lowlevel import checkpoint, green_checkpoint
from aiologic.lowlevel._thread import LockType, allocate_lock

from ._exceptions import (
    QueueEmpty,
    QueueFull,
    QueueShutDown,
    UnsupportedOperation,
)
from ._protocols import AsyncQueue, MixedQueue, SyncQueue
from ._proxies import AsyncQueueProxy, SyncQueueProxy

T = TypeVar("T")


class Queue(MixedQueue[T]):
    """Create a queue object with a given maximum size.

    If maxsize is <= 0, the queue size is infinite.
    """

    __slots__ = (
        "__data",
        "__weakref__",
        "_is_shutdown",
        "_maxsize",
        "_unfinished_tasks",
        "all_tasks_done",
        "mutex",
        "not_empty",
        "not_full",
    )

    __data: deque[T]

    _maxsize: int
    _unfinished_tasks: int
    _is_shutdown: bool

    mutex: LockType

    not_full: Condition[LockType]
    not_empty: Condition[LockType]
    all_tasks_done: Condition[LockType]

    def __init__(self, maxsize: int = 0) -> None:
        self._maxsize = maxsize
        self._unfinished_tasks = 0
        self._is_shutdown = False

        self.mutex = mutex = allocate_lock()

        self.not_full = Condition(mutex)  # putters
        self.not_empty = Condition(mutex)  # getters
        self.all_tasks_done = Condition(mutex)  # joiners

        self._init(maxsize)  # data

    def peekable(self) -> bool:
        with self.mutex:
            return self._peekable()

    def qsize(self) -> int:
        with self.mutex:
            return self._qsize()

    def empty(self) -> bool:
        with self.mutex:
            return not self._qsize()

    def full(self) -> bool:
        with self.mutex:
            return 0 < self._maxsize <= self._qsize()

    def sync_put(
        self,
        item: T,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        rescheduled = False

        with self.mutex:
            self._check_closing()

            if 0 < self._maxsize:
                if not block:
                    if 0 < self._maxsize <= self._qsize():
                        raise QueueFull
                elif timeout is None:
                    while 0 < self._maxsize <= self._qsize():
                        self.not_full.wait()

                        self._check_closing()

                        rescheduled = True
                elif timeout < 0:
                    msg = "'timeout' must be a non-negative number"
                    raise ValueError(msg)
                else:
                    endtime = time.monotonic() + timeout

                    while 0 < self._maxsize <= self._qsize():
                        remaining = endtime - time.monotonic()

                        if remaining <= 0:
                            raise QueueFull

                        self.not_full.wait(remaining)

                        self._check_closing()

                        rescheduled = True

            self._put(item)
            self._unfinished_tasks += 1

            self.not_empty.notify()

        if not rescheduled:
            green_checkpoint()

    async def async_put(self, item: T) -> None:
        rescheduled = False

        with self.mutex:
            self._check_closing()

            while 0 < self._maxsize <= self._qsize():
                await self.not_full

                self._check_closing()

                rescheduled = True

            self._put(item)
            self._unfinished_tasks += 1

            self.not_empty.notify()

        if not rescheduled:
            await checkpoint()

    def put_nowait(self, item: T) -> None:
        with self.mutex:
            self._check_closing()

            if 0 < self._maxsize <= self._qsize():
                raise QueueFull

            self._put(item)
            self._unfinished_tasks += 1

            self.not_empty.notify()

    def sync_get(self, block: bool = True, timeout: float | None = None) -> T:
        rescheduled = False

        with self.mutex:
            if not block:
                if not self._qsize():
                    self._check_closing()

                    raise QueueEmpty
            elif timeout is None:
                while not self._qsize():
                    self._check_closing()

                    self.not_empty.wait()

                    rescheduled = True
            elif timeout < 0:
                msg = "'timeout' must be a non-negative number"
                raise ValueError(msg)
            else:
                endtime = time.monotonic() + timeout

                while not self._qsize():
                    self._check_closing()

                    remaining = endtime - time.monotonic()

                    if remaining <= 0:
                        raise QueueEmpty

                    self.not_empty.wait(remaining)

                    rescheduled = True

            item = self._get()

            if 0 >= self._maxsize or self._maxsize > self._qsize():
                self.not_full.notify()

        if not rescheduled:
            green_checkpoint()

        return item

    async def async_get(self) -> T:
        rescheduled = False

        with self.mutex:
            while not self._qsize():
                self._check_closing()

                await self.not_empty

                rescheduled = True

            item = self._get()

            if 0 >= self._maxsize or self._maxsize > self._qsize():
                self.not_full.notify()

        if not rescheduled:
            await checkpoint()

        return item

    def get_nowait(self) -> T:
        with self.mutex:
            if not self._qsize():
                self._check_closing()

                raise QueueEmpty

            item = self._get()

            if 0 >= self._maxsize or self._maxsize > self._qsize():
                self.not_full.notify()

        return item

    def sync_peek(self, block: bool = True, timeout: float | None = None) -> T:
        rescheduled = False

        with self.mutex:
            self._check_peekable()

            if not block:
                if not self._qsize():
                    self._check_closing()

                    raise QueueEmpty
            elif timeout is None:
                while not self._qsize():
                    self._check_closing()

                    self.not_empty.wait()

                    rescheduled = True
            elif timeout < 0:
                msg = "'timeout' must be a non-negative number"
                raise ValueError(msg)
            else:
                endtime = time.monotonic() + timeout

                while not self._qsize():
                    self._check_closing()

                    remaining = endtime - time.monotonic()

                    if remaining <= 0:
                        raise QueueEmpty

                    self.not_empty.wait(remaining)

                    rescheduled = True

            try:
                item = self._peek()
            finally:
                if rescheduled:
                    self.not_empty.notify()

        if not rescheduled:
            green_checkpoint()

        return item

    async def async_peek(self) -> T:
        rescheduled = False

        with self.mutex:
            self._check_peekable()

            while not self._qsize():
                self._check_closing()

                await self.not_empty

                rescheduled = True

            try:
                item = self._peek()
            finally:
                if rescheduled:
                    self.not_empty.notify()

        if not rescheduled:
            await checkpoint()

        return item

    def peek_nowait(self) -> T:
        with self.mutex:
            self._check_peekable()

            if not self._qsize():
                self._check_closing()

                raise QueueEmpty

            item = self._peek()

        return item

    def sync_join(self) -> None:
        rescheduled = False

        with self.mutex:
            while self._unfinished_tasks:
                self.all_tasks_done.wait()

                rescheduled = True

        if not rescheduled:
            green_checkpoint()

    async def async_join(self) -> None:
        rescheduled = False

        with self.mutex:
            while self._unfinished_tasks:
                await self.all_tasks_done

                rescheduled = True

        if not rescheduled:
            await checkpoint()

    def task_done(self) -> None:
        with self.mutex:
            unfinished = self._unfinished_tasks - 1

            if unfinished <= 0:
                if unfinished < 0:
                    msg = "task_done() called too many times"
                    raise ValueError(msg)

                self.all_tasks_done.notify_all()

            self._unfinished_tasks = unfinished

    def shutdown(self, immediate: bool = False) -> None:
        with self.mutex:
            self._is_shutdown = True

            if immediate:
                while self._qsize():
                    self._get()

                    if self._unfinished_tasks > 0:
                        self._unfinished_tasks -= 1

                self.all_tasks_done.notify_all()

            self.not_empty.notify_all()
            self.not_full.notify_all()

    def close(self) -> None:
        self.shutdown(immediate=True)

    async def wait_closed(self) -> None:
        if not self._is_shutdown:
            msg = "Waiting for non-closed queue"
            raise RuntimeError(msg)

        await checkpoint()

    async def aclose(self) -> None:
        self.close()
        await self.wait_closed()

    def clear(self) -> None:
        with self.mutex:
            size = self._qsize()
            unfinished = max(0, self._unfinished_tasks - size)

            self._clear()

            if not unfinished:
                self.all_tasks_done.notify_all()

            self._unfinished_tasks = unfinished
            self.not_full.notify(size)

    def _check_peekable(self) -> None:
        if not self._peekable():
            msg = "peeking not supported"
            raise UnsupportedOperation(msg)

    def _check_closing(self) -> None:
        if self._is_shutdown:
            raise QueueShutDown

    # Override these methods to implement other queue organizations
    # (e.g. stack or priority queue).
    # These will only be called with appropriate locks held

    def _init(self, maxsize: int) -> None:
        self.__data = deque()

    def _qsize(self) -> int:
        return len(self.__data)

    def _put(self, item: T) -> None:
        self.__data.append(item)

    def _get(self) -> T:
        return self.__data.popleft()

    def _peek(self) -> T:
        return self.__data[0]

    def _peekable(self) -> bool:
        return True

    def _clear(self) -> None:
        self.__data.clear()

    @property
    def sync_q(self) -> SyncQueue[T]:
        return SyncQueueProxy(self)

    @property
    def async_q(self) -> AsyncQueue[T]:
        return AsyncQueueProxy(self)

    @property
    def putting(self) -> int:
        return self.not_full.waiting

    @property
    def getting(self) -> int:
        return self.not_empty.waiting

    @property
    def unfinished_tasks(self) -> int:
        return self._unfinished_tasks

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    @property
    def closed(self) -> bool:
        return self._is_shutdown

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @maxsize.setter
    def maxsize(self, value: int) -> None:
        with self.mutex:
            maxsize = self._maxsize

            if value <= 0:
                self.not_full.notify_all()
            elif value > maxsize:
                self.not_full.notify(value - maxsize)

            self._maxsize = value


class LifoQueue(Queue[T]):
    """A subclass of Queue; retrieves most recently added entries first."""

    __slots__ = ("__data",)

    __data: list[T]

    def _init(self, maxsize: int) -> None:
        self.__data = []

    def _qsize(self) -> int:
        return len(self.__data)

    def _put(self, item: T) -> None:
        self.__data.append(item)

    def _get(self) -> T:
        return self.__data.pop()

    def _peek(self) -> T:
        return self.__data[-1]

    def _peekable(self) -> bool:
        return True

    def _clear(self) -> None:
        self.__data.clear()


class PriorityQueue(Queue[T]):
    """A subclass of Queue; retrieves entries in priority order (lowest first).

    Entries are typically tuples of the form: (priority number, data).
    """

    __slots__ = ("__data",)

    __data: list[T]

    def _init(self, maxsize: int) -> None:
        self.__data = []

    def _qsize(self) -> int:
        return len(self.__data)

    def _put(self, item: T) -> None:
        heappush(self.__data, item)

    def _get(self) -> T:
        return heappop(self.__data)

    def _peek(self) -> T:
        return self.__data[0]

    def _peekable(self) -> bool:
        return True

    def _clear(self) -> None:
        self.__data.clear()
