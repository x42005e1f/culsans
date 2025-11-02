#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

import sys

from collections import deque
from heapq import heappop, heappush
from math import inf, isnan
from typing import Any, Protocol, TypeVar, Union

from aiologic import Condition
from aiologic.lowlevel import async_checkpoint, green_checkpoint

from ._exceptions import (
    QueueEmpty,
    QueueFull,
    QueueShutDown,
    UnsupportedOperation,
)
from ._protocols import MixedQueue
from ._proxies import AsyncQueueProxy, SyncQueueProxy

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

try:
    from aiologic.lowlevel import ThreadLock, create_thread_lock
except ImportError:  # aiologic<0.15.0
    from aiologic.lowlevel._thread import (  # type: ignore[assignment]
        LockType as ThreadLock,
        allocate_lock as create_thread_lock,
    )

try:
    from aiologic.lowlevel import green_clock
except ImportError:  # aiologic<0.15.0
    from time import monotonic as green_clock

try:
    from aiologic.lowlevel import (
        async_checkpoint_enabled,
        green_checkpoint_enabled,
    )
except ImportError:  # aiologic<0.15.0

    def async_checkpoint_enabled() -> bool:
        return True

    def green_checkpoint_enabled() -> bool:
        return True


_T = TypeVar("_T")
_T_contra = TypeVar("_T_contra", contravariant=True)


class _SupportsBool(Protocol):
    __slots__ = ()

    def __bool__(self, /) -> bool: ...


class _SupportsLT(Protocol[_T_contra]):
    __slots__ = ()

    def __lt__(self, other: _T_contra, /) -> _SupportsBool: ...


class _SupportsGT(Protocol[_T_contra]):
    __slots__ = ()

    def __gt__(self, other: _T_contra, /) -> _SupportsBool: ...


_RichComparableT = TypeVar(
    "_RichComparableT",
    bound=Union[_SupportsLT[Any], _SupportsGT[Any]],
)


class Queue(MixedQueue[_T]):
    """
    A mixed sync-async queue that is:

    * :abbr:`MPMC (multi-producer, multi-consumer)`
    * :abbr:`FIFO (first-in, first-out)`

    Compliant with the Janus API version 2.0.0.
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

    __data: deque[_T]

    _maxsize: int
    _unfinished_tasks: int
    _is_shutdown: bool

    mutex: ThreadLock

    not_full: Condition[ThreadLock]
    not_empty: Condition[ThreadLock]
    all_tasks_done: Condition[ThreadLock]

    def __init__(self, maxsize: int = 0) -> None:
        """
        Create a queue object with the given maximum size.

        if *maxsize* is <= 0, the queue size if infinite. If it is an integer
        greater that 0, then the put methods block when the queue reaches
        *maxsize* until an item is removed by the get methods.
        """

        self._maxsize = maxsize
        self._unfinished_tasks = 0
        self._is_shutdown = False

        self.mutex = mutex = create_thread_lock()

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
        item: _T,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        rescheduled = False
        endtime = None

        with self.mutex:
            while True:
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
                    else:
                        if isinstance(timeout, int):
                            try:
                                timeout = float(timeout)
                            except OverflowError:
                                timeout = (-1 if timeout < 0 else 1) * inf

                        if isnan(timeout):
                            msg = "'timeout' must be a number (non-NaN)"
                            raise ValueError(msg)

                        if timeout < 0:
                            msg = "'timeout' must be a non-negative number"
                            raise ValueError(msg)

                        if endtime is None:
                            endtime = green_clock() + timeout

                        while 0 < self._maxsize <= self._qsize():
                            remaining = endtime - green_clock()

                            if remaining <= 0:
                                raise QueueFull

                            self.not_full.wait(remaining)

                            self._check_closing()

                            rescheduled = True

                if not rescheduled and green_checkpoint_enabled():
                    self.mutex.release()

                    try:
                        green_checkpoint()
                    finally:
                        self.mutex.acquire()

                    rescheduled = True
                else:
                    break

            self._put(item)
            self._unfinished_tasks += 1

            self.not_empty.notify()

    async def async_put(self, item: _T) -> None:
        rescheduled = False

        with self.mutex:
            while True:
                self._check_closing()

                while 0 < self._maxsize <= self._qsize():
                    await self.not_full

                    self._check_closing()

                    rescheduled = True

                if not rescheduled and async_checkpoint_enabled():
                    self.mutex.release()

                    try:
                        await async_checkpoint()
                    finally:
                        self.mutex.acquire()

                    rescheduled = True
                else:
                    break

            self._put(item)
            self._unfinished_tasks += 1

            self.not_empty.notify()

    def put_nowait(self, item: _T) -> None:
        with self.mutex:
            self._check_closing()

            if 0 < self._maxsize <= self._qsize():
                raise QueueFull

            self._put(item)
            self._unfinished_tasks += 1

            self.not_empty.notify()

    def sync_get(self, block: bool = True, timeout: float | None = None) -> _T:
        rescheduled = False
        endtime = None

        with self.mutex:
            while True:
                if not block:
                    if not self._qsize():
                        self._check_closing()

                        raise QueueEmpty
                elif timeout is None:
                    while not self._qsize():
                        self._check_closing()

                        self.not_empty.wait()

                        rescheduled = True
                else:
                    if isinstance(timeout, int):
                        try:
                            timeout = float(timeout)
                        except OverflowError:
                            timeout = (-1 if timeout < 0 else 1) * inf

                    if isnan(timeout):
                        msg = "'timeout' must be a number (non-NaN)"
                        raise ValueError(msg)

                    if timeout < 0:
                        msg = "'timeout' must be a non-negative number"
                        raise ValueError(msg)

                    if endtime is None:
                        endtime = green_clock() + timeout

                    while not self._qsize():
                        self._check_closing()

                        remaining = endtime - green_clock()

                        if remaining <= 0:
                            raise QueueEmpty

                        self.not_empty.wait(remaining)

                        rescheduled = True

                if not rescheduled and green_checkpoint_enabled():
                    self.mutex.release()

                    try:
                        green_checkpoint()
                    finally:
                        self.mutex.acquire()

                    rescheduled = True
                else:
                    break

            item = self._get()

            if 0 >= self._maxsize or self._maxsize > self._qsize():
                self.not_full.notify()

        return item

    async def async_get(self) -> _T:
        rescheduled = False

        with self.mutex:
            while True:
                while not self._qsize():
                    self._check_closing()

                    await self.not_empty

                    rescheduled = True

                if not rescheduled and async_checkpoint_enabled():
                    self.mutex.release()

                    try:
                        await async_checkpoint()
                    finally:
                        self.mutex.acquire()

                    rescheduled = True
                else:
                    break

            item = self._get()

            if 0 >= self._maxsize or self._maxsize > self._qsize():
                self.not_full.notify()

        return item

    def get_nowait(self) -> _T:
        with self.mutex:
            if not self._qsize():
                self._check_closing()

                raise QueueEmpty

            item = self._get()

            if 0 >= self._maxsize or self._maxsize > self._qsize():
                self.not_full.notify()

        return item

    def sync_peek(
        self,
        block: bool = True,
        timeout: float | None = None,
    ) -> _T:
        rescheduled = False
        notified = False
        endtime = None

        with self.mutex:
            self._check_peekable()

            while True:
                if not block:
                    if not self._qsize():
                        self._check_closing()

                        raise QueueEmpty
                elif timeout is None:
                    while not self._qsize():
                        self._check_closing()

                        notified = self.not_empty.wait()

                        rescheduled = True
                else:
                    if isinstance(timeout, int):
                        try:
                            timeout = float(timeout)
                        except OverflowError:
                            timeout = (-1 if timeout < 0 else 1) * inf

                    if isnan(timeout):
                        msg = "'timeout' must be a number (non-NaN)"
                        raise ValueError(msg)

                    if timeout < 0:
                        msg = "'timeout' must be a non-negative number"
                        raise ValueError(msg)

                    if endtime is None:
                        endtime = green_clock() + timeout

                    while not self._qsize():
                        self._check_closing()

                        remaining = endtime - green_clock()

                        if remaining <= 0:
                            raise QueueEmpty

                        notified = self.not_empty.wait(remaining)

                        rescheduled = True

                if not rescheduled and green_checkpoint_enabled():
                    self.mutex.release()

                    try:
                        green_checkpoint()
                    finally:
                        self.mutex.acquire()

                    rescheduled = True
                else:
                    break

            try:
                item = self._peek()
            finally:
                if notified:
                    self.not_empty.notify()

        return item

    async def async_peek(self) -> _T:
        rescheduled = False
        notified = False

        with self.mutex:
            self._check_peekable()

            while True:
                while not self._qsize():
                    self._check_closing()

                    notified = await self.not_empty

                    rescheduled = True

                if not rescheduled and async_checkpoint_enabled():
                    self.mutex.release()

                    try:
                        await async_checkpoint()
                    finally:
                        self.mutex.acquire()

                    rescheduled = True
                else:
                    break

            try:
                item = self._peek()
            finally:
                if notified:
                    self.not_empty.notify()

        return item

    def peek_nowait(self) -> _T:
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
            await async_checkpoint()

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
        """
        Close the queue.

        This method is provided for compatibility with the Janus queues. Use
        :meth:`queue.shutdown(immediate=True) <BaseQueue.shutdown>` as a direct
        substitute.
        """

        self.shutdown(immediate=True)

    async def wait_closed(self) -> None:
        """
        Wait for finishing all pending activities.

        This method is provided for compatibility with the Janus queues. It
        actually does nothing.

        Raises:
          RuntimeError:
            if called for non-closed queue.
        """

        if not self._is_shutdown:
            msg = "Waiting for non-closed queue"
            raise RuntimeError(msg)

        await async_checkpoint()

    async def aclose(self) -> None:
        """
        Shutdown the queue and wait for actual shutting down.

        This method is provided for compatibility with the Janus queues. Use
        :meth:`queue.shutdown(immediate=True) <BaseQueue.shutdown>` as a direct
        substitute.
        """

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

    def _put(self, item: _T) -> None:
        self.__data.append(item)

    def _get(self) -> _T:
        return self.__data.popleft()

    def _peek(self) -> _T:
        return self.__data[0]

    def _peekable(self) -> bool:
        return True

    def _clear(self) -> None:
        self.__data.clear()

    @property
    def sync_q(self) -> SyncQueueProxy[_T]:
        return SyncQueueProxy(self)

    @property
    def async_q(self) -> AsyncQueueProxy[_T]:
        return AsyncQueueProxy(self)

    @property
    def putting(self) -> int:
        """
        The current number of threads/tasks waiting to put.

        It represents the length of the wait queue and thus changes
        immediately.
        """

        return self.not_full.waiting

    @property
    def getting(self) -> int:
        """
        The current number of threads/tasks waiting to get/peek.

        It represents the length of the wait queue and thus changes
        immediately.
        """

        return self.not_empty.waiting

    @property
    def waiting(self) -> int:
        """
        The current number of threads/tasks waiting to access.

        It is roughly equivalent to the sum of the :attr:`putting` and
        :attr:`getting` properties, but is more reliable than the sum in a
        multithreaded environment.
        """

        with self.mutex:
            # We use the underlying lock to ensure that no thread can increment
            # the counters during normal queue operation (since exclusive
            # access is required to enter the wait queue).
            return self.not_full.waiting + self.not_empty.waiting

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


class LifoQueue(Queue[_T]):
    """
    A variant of :class:`Queue` that retrieves most recently added entries
    first (:abbr:`LIFO (last-in, first-out)`).
    """

    __slots__ = ("__data",)  # noqa: PLW0244

    __data: list[_T]

    @override
    def _init(self, maxsize: int) -> None:
        self.__data = []

    @override
    def _qsize(self) -> int:
        return len(self.__data)

    @override
    def _put(self, item: _T) -> None:
        self.__data.append(item)

    @override
    def _get(self) -> _T:
        return self.__data.pop()

    @override
    def _peek(self) -> _T:
        return self.__data[-1]

    @override
    def _peekable(self) -> bool:
        return True

    @override
    def _clear(self) -> None:
        self.__data.clear()


class PriorityQueue(Queue[_RichComparableT]):
    """
    A variant of :class:`Queue` that retrieves entries in priority order
    (lowest first).
    """

    __slots__ = ("__data",)  # noqa: PLW0244

    __data: list[_RichComparableT]

    @override
    def _init(self, maxsize: int) -> None:
        self.__data = []

    @override
    def _qsize(self) -> int:
        return len(self.__data)

    @override
    def _put(self, item: _RichComparableT) -> None:
        heappush(self.__data, item)

    @override
    def _get(self) -> _RichComparableT:
        return heappop(self.__data)

    @override
    def _peek(self) -> _RichComparableT:
        return self.__data[0]

    @override
    def _peekable(self) -> bool:
        return True

    @override
    def _clear(self) -> None:
        self.__data.clear()
