#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: 0BSD

__all__ = (
    "UnsupportedOperation",
    "QueueEmpty",
    "QueueFull",
    "QueueShutDown",
    "SyncQueueEmpty",
    "SyncQueueFull",
    "SyncQueueShutDown",
    "AsyncQueueEmpty",
    "AsyncQueueFull",
    "AsyncQueueShutDown",
    "BaseQueue",
    "SyncQueue",
    "AsyncQueue",
    "Queue",
    "LifoQueue",
    "PriorityQueue",
)

import sys
import time

from heapq import heappop, heappush
from queue import Empty as SyncQueueEmpty, Full as SyncQueueFull
from typing import Optional, Protocol, TypeVar
from asyncio import QueueEmpty as AsyncQueueEmpty, QueueFull as AsyncQueueFull
from collections import deque

from aiologic import Condition  # type: ignore[import-untyped]
from aiologic.lowlevel import (  # type: ignore[import-untyped]
    checkpoint,
    green_checkpoint,
)
from aiologic.lowlevel.thread import (  # type: ignore[import-untyped]
    allocate_lock,
)

if sys.version_info >= (3, 13):
    from queue import ShutDown as SyncQueueShutDown
    from asyncio import QueueShutDown as AsyncQueueShutDown
else:

    class ShutDown(Exception):
        """Raised when put/get with shut-down queue."""

    SyncQueueShutDown = ShutDown

    class QueueShutDown(Exception):
        """Raised when putting on to or getting from a shut-down Queue."""

    AsyncQueueShutDown = QueueShutDown


class UnsupportedOperation(ValueError):
    """Raised when peek with non-peekable queue."""


class QueueEmpty(SyncQueueEmpty, AsyncQueueEmpty):
    """Raised when non-blocking get with empty queue."""


class QueueFull(SyncQueueFull, AsyncQueueFull):
    """Raised when non-blocking put with full queue."""


class QueueShutDown(  # type: ignore[no-redef]
    SyncQueueShutDown,
    AsyncQueueShutDown,
):
    """Raised when put/get with shut-down queue."""


T = TypeVar("T")


class BaseQueue(Protocol[T]):
    __slots__ = ()

    def peekable(self) -> bool:
        """Return True if the queue is peekable, False otherwise."""

    def qsize(self) -> int:
        """Return the approximate size of the queue (not reliable!)."""

    def empty(self) -> bool:
        """Return True if the queue is empty, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() == 0
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can grow before the result of empty() or
        qsize() can be used.

        To create code that needs to wait for all queued tasks to be
        completed, the preferred technique is to use the join() method.
        """

    def full(self) -> bool:
        """Return True if the queue is full, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() >= n
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can shrink before the result of full() or
        qsize() can be used.
        """

    def put_nowait(self, item: T) -> None:
        """Put an item into the queue without blocking.

        Only enqueue the item if a free slot is immediately available.
        Otherwise raise the QueueFull exception.

        Raises QueueShutDown if the queue has been shut down.
        """

    def get_nowait(self) -> T:
        """Remove and return an item from the queue without blocking.

        Only get an item if one is immediately available.
        Otherwise raise the QueueEmpty exception.

        Raises QueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

    def peek_nowait(self) -> T:
        """Return an item from the queue without blocking.

        Only peek an item if one is immediately available.
        Otherwise raise the QueueEmpty exception.

        Raises QueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

    def clear(self) -> None:
        """Clear all items from the queue atomically."""

    def task_done(self) -> None:
        """Indicate that a formerly enqueued task is complete.

        Used by queue consumers.  For each get() used to fetch a task,
        a subsequent call to task_done() tells the queue that the processing
        on the task is complete.

        If a join() is currently blocking, it will resume when all items have
        been processed (meaning that a task_done() call was received for every
        item that had been put() into the queue).

        shutdown(immediate=True) calls task_done() for each remaining item in
        the queue.

        Raises ValueError if called more times than there were items placed in
        the queue.
        """

    def shutdown(self, immediate: bool = False) -> None:
        """Shut-down the queue, making queue gets and puts raise QueueShutDown.

        By default, gets will only raise once the queue is empty. Set
        'immediate' to True to make gets raise immediately instead.

        All blocked callers of put() and get() will be unblocked. If
        'immediate', a task is marked as done for each item remaining in
        the queue, which may unblock callers of join().
        """

    @property
    def unfinished_tasks(self) -> int: ...

    @property
    def is_shutdown(self) -> bool: ...

    @property
    def closed(self) -> bool: ...

    @property
    def maxsize(self) -> int: ...

    @maxsize.setter
    def maxsize(self, value: int) -> None: ...


class SyncQueue(BaseQueue[T], Protocol[T]):
    __slots__ = ()

    def put(
        self,
        item: T,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> None:
        """Put an item into the queue.

        If optional args 'block' is True and 'timeout' is None (the default),
        block if necessary until a free slot is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the QueueFull exception if no free slot was available within that time.
        Otherwise ('block' is False), put an item on the queue if a free slot
        is immediately available, else raise the QueueFull exception
        ('timeout' is ignored in that case).

        Raises QueueShutDown if the queue has been shut down.
        """

    def get(self, block: bool = True, timeout: Optional[float] = None) -> T:
        """Remove and return an item from the queue.

        If optional args 'block' is True and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the QueueEmpty exception if no item was available within that time.
        Otherwise ('block' is False), return an item if one is immediately
        available, else raise the QueueEmpty exception ('timeout' is ignored in
        that case).

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """

    def peek(self, block: bool = True, timeout: Optional[float] = None) -> T:
        """Return an item from the queue without removing it.

        If optional args 'block' is True and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the QueueEmpty exception if no item was available within that time.
        Otherwise ('block' is False), return an item if one is immediately
        available, else raise the QueueEmpty exception ('timeout' is ignored in
        that case).

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """

    def join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """


class AsyncQueue(BaseQueue[T], Protocol[T]):
    __slots__ = ()

    async def put(self, item: T) -> None:
        """Put an item into the queue.

        If the queue is full, wait until a free slot is available before adding
        item.

        Raises QueueShutDown if the queue has been shut down.
        """

    async def get(self) -> T:
        """Remove and return an item from the queue.

        If queue is empty, wait until an item is available.

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """

    async def peek(self) -> T:
        """Return an item from the queue without removing it.

        If queue is empty, wait until an item is available.

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """

    async def join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """


class Queue(BaseQueue[T]):
    """Create a queue object with a given maximum size.

    If maxsize is <= 0, the queue size is infinite.
    """

    __slots__ = (
        "__weakref__",
        "_maxsize",
        "_unfinished_tasks",
        "_is_shutdown",
        "mutex",
        "not_full",
        "not_empty",
        "all_tasks_done",
        "data",
    )

    data: deque[T]

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
        timeout: Optional[float] = None,
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
                    raise ValueError("'timeout' must be a non-negative number")
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

    def sync_get(
        self,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> T:
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
                raise ValueError("'timeout' must be a non-negative number")
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

    def sync_peek(
        self,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> T:
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
                raise ValueError("'timeout' must be a non-negative number")
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

    def clear(self) -> None:
        with self.mutex:
            size = self._qsize()
            unfinished = max(0, self._unfinished_tasks - size)

            self._clear()

            if not unfinished:
                self.all_tasks_done.notify_all()

            self._unfinished_tasks = unfinished
            self.not_full.notify(size)

    def task_done(self) -> None:
        with self.mutex:
            unfinished = self._unfinished_tasks - 1

            if unfinished <= 0:
                if unfinished < 0:
                    raise ValueError("task_done() called too many times")

                self.all_tasks_done.notify_all()

            self._unfinished_tasks = unfinished

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
            raise RuntimeError("Waiting for non-closed queue")

        await checkpoint()

    async def aclose(self) -> None:
        self.close()
        await self.wait_closed()

    def _check_peekable(self) -> None:
        if not self._peekable():
            raise UnsupportedOperation("peeking not supported")

    def _check_closing(self) -> None:
        if self._is_shutdown:
            raise QueueShutDown

    # Override these methods to implement other queue organizations
    # (e.g. stack or priority queue).
    # These will only be called with appropriate locks held

    def _init(self, maxsize: int) -> None:
        self.data = deque()

    def _qsize(self) -> int:
        return len(self.data)

    def _put(self, item: T) -> None:
        self.data.append(item)

    def _get(self) -> T:
        return self.data.popleft()

    def _peek(self) -> T:
        return self.data[0]

    def _peekable(self) -> bool:
        return True

    def _clear(self) -> None:
        self.data.clear()

    @property
    def sync_q(self) -> SyncQueue[T]:
        return SyncQueueProxy(self)

    @property
    def async_q(self) -> AsyncQueue[T]:
        return AsyncQueueProxy(self)

    @property
    def putting(self) -> int:
        return self.not_full.waiting  # type: ignore[no-any-return]

    @property
    def getting(self) -> int:
        return self.not_empty.waiting  # type: ignore[no-any-return]

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

    __slots__ = ()

    data: list[T]  # type: ignore[assignment]

    def _init(self, maxsize: int) -> None:
        self.data = []

    def _qsize(self) -> int:
        return len(self.data)

    def _put(self, item: T) -> None:
        self.data.append(item)

    def _get(self) -> T:
        return self.data.pop()

    def _peek(self) -> T:
        return self.data[-1]

    def _peekable(self) -> bool:
        return True

    def _clear(self) -> None:
        self.data.clear()


class PriorityQueue(Queue[T]):
    """A subclass of Queue; retrieves entries in priority order (lowest first).

    Entries are typically tuples of the form: (priority number, data).
    """

    __slots__ = ()

    data: list[T]  # type: ignore[assignment]

    def _init(self, maxsize: int) -> None:
        self.data = []

    def _qsize(self) -> int:
        return len(self.data)

    def _put(self, item: T) -> None:
        heappush(self.data, item)

    def _get(self) -> T:
        return heappop(self.data)

    def _peek(self) -> T:
        return self.data[0]

    def _peekable(self) -> bool:
        return True

    def _clear(self) -> None:
        self.data.clear()


class SyncQueueProxy(SyncQueue[T]):
    __slots__ = ("wrapped",)

    def __init__(self, wrapped: Queue[T]) -> None:
        self.wrapped = wrapped

    def peekable(self) -> bool:
        return self.wrapped.peekable()

    def qsize(self) -> int:
        return self.wrapped.qsize()

    def empty(self) -> bool:
        return self.wrapped.empty()

    def full(self) -> bool:
        return self.wrapped.full()

    def put(
        self,
        item: T,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> None:
        self.wrapped.sync_put(item, block, timeout)

    def put_nowait(self, item: T) -> None:
        self.wrapped.put_nowait(item)

    def get(self, block: bool = True, timeout: Optional[float] = None) -> T:
        return self.wrapped.sync_get(block, timeout)

    def get_nowait(self) -> T:
        return self.wrapped.get_nowait()

    def peek(self, block: bool = True, timeout: Optional[float] = None) -> T:
        return self.wrapped.sync_peek(block, timeout)

    def peek_nowait(self) -> T:
        return self.wrapped.peek_nowait()

    def clear(self) -> None:
        self.wrapped.clear()

    def task_done(self) -> None:
        self.wrapped.task_done()

    def join(self) -> None:
        self.wrapped.sync_join()

    def shutdown(self, immediate: bool = False) -> None:
        self.wrapped.shutdown(immediate)

    @property
    def unfinished_tasks(self) -> int:
        return self.wrapped.unfinished_tasks

    @property
    def is_shutdown(self) -> bool:
        return self.wrapped.is_shutdown

    @property
    def closed(self) -> bool:
        return self.wrapped.closed

    @property
    def maxsize(self) -> int:
        return self.wrapped.maxsize

    @maxsize.setter
    def maxsize(self, value: int) -> None:
        self.wrapped.maxsize = value


class AsyncQueueProxy(AsyncQueue[T]):
    __slots__ = ("wrapped",)

    def __init__(self, wrapped: Queue[T]) -> None:
        self.wrapped = wrapped

    def peekable(self) -> bool:
        return self.wrapped.peekable()

    def qsize(self) -> int:
        return self.wrapped.qsize()

    def empty(self) -> bool:
        return self.wrapped.empty()

    def full(self) -> bool:
        return self.wrapped.full()

    async def put(self, item: T) -> None:
        await self.wrapped.async_put(item)

    def put_nowait(self, item: T) -> None:
        self.wrapped.put_nowait(item)

    async def get(self) -> T:
        return await self.wrapped.async_get()

    def get_nowait(self) -> T:
        return self.wrapped.get_nowait()

    async def peek(self) -> T:
        return await self.wrapped.async_peek()

    def peek_nowait(self) -> T:
        return self.wrapped.peek_nowait()

    def clear(self) -> None:
        self.wrapped.clear()

    def task_done(self) -> None:
        self.wrapped.task_done()

    async def join(self) -> None:
        await self.wrapped.async_join()

    def shutdown(self, immediate: bool = False) -> None:
        self.wrapped.shutdown(immediate)

    @property
    def unfinished_tasks(self) -> int:
        return self.wrapped.unfinished_tasks

    @property
    def is_shutdown(self) -> bool:
        return self.wrapped.is_shutdown

    @property
    def closed(self) -> bool:
        return self.wrapped.closed

    @property
    def maxsize(self) -> int:
        return self.wrapped.maxsize

    @maxsize.setter
    def maxsize(self, value: int) -> None:
        self.wrapped.maxsize = value
