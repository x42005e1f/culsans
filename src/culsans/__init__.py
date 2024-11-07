#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: 0BSD

__all__ = (
    "SyncQueueEmpty",
    "SyncQueueFull",
    "SyncQueueShutDown",
    "AsyncQueueEmpty",
    "AsyncQueueFull",
    "AsyncQueueShutDown",
    "BaseQueue",
    "AsyncQueue",
    "SyncQueue",
    "Queue",
    "LifoQueue",
    "PriorityQueue",
)

import sys
import time

from heapq import heappop, heappush
from queue import Empty as SyncQueueEmpty, Full as SyncQueueFull
from typing import Generic, Optional, Protocol, TypeVar
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
else:

    class SyncQueueShutDown(Exception):
        """Raised when put/get with shut-down queue."""


if sys.version_info >= (3, 13):
    from asyncio import QueueShutDown as AsyncQueueShutDown
else:

    class AsyncQueueShutDown(Exception):
        """Raised when put/get with shut-down queue."""


T = TypeVar("T")


class BaseQueue(Protocol[T]):
    __slots__ = ()

    def qsize(self) -> int: ...

    def empty(self) -> bool: ...

    def full(self) -> bool: ...

    def put_nowait(self, item: T) -> None: ...

    def peek_nowait(self) -> T: ...

    def get_nowait(self) -> T: ...

    def task_done(self) -> None: ...

    def shutdown(self, immediate: bool = False) -> None: ...

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
    ) -> None: ...

    def peek(
        self, block: bool = True, timeout: Optional[float] = None
    ) -> T: ...

    def get(
        self, block: bool = True, timeout: Optional[float] = None
    ) -> T: ...

    def join(self) -> None: ...


class AsyncQueue(BaseQueue[T], Protocol[T]):
    __slots__ = ()

    async def put(self, item: T) -> None: ...

    async def peek(self) -> T: ...

    async def get(self) -> T: ...

    async def join(self) -> None: ...


class Queue(Generic[T]):
    """Create a queue object with a given maximum size.

    If maxsize is <= 0, the queue size is infinite.
    """

    __slots__ = (
        "__weakref__",
        "_mutex",
        "_not_empty",
        "_not_full",
        "_all_tasks_done",
        "_unfinished_tasks",
        "_is_shutdown",
        "_is_closing",
        "_maxsize",
        "data",
    )

    data: deque[T]

    def __init__(self, maxsize: int = 0) -> None:
        self._maxsize = maxsize
        self._init(maxsize)

        # Mutex must be held whenever the queue is mutating. All methods
        # that acquire mutex must release it before returning. Mutex
        # is shared between the three conditions, so acquiring and
        # releasing the conditions also acquires and releases mutex.
        self._mutex = mutex = allocate_lock()

        # Notify not_empty whenever an item is added to the queue; a
        # thread waiting to get is notified then.
        self._not_empty = Condition(mutex)

        # Notify not_full whenever an item is removed from the queue;
        # a thread waiting to put is notified then.
        self._not_full = Condition(mutex)

        # Notify all_tasks_done whenever the number of unfinished tasks
        # drops to zero; thread waiting to join() is notified to resume
        self._all_tasks_done = Condition(mutex)
        self._unfinished_tasks = 0

        # Queue shutdown state
        self._is_shutdown = False
        self._is_closing = False

    def shutdown(self, immediate: bool = False) -> None:
        """Shut-down the queue, making queue gets and puts raise QueueShutDown.

        By default, gets will only raise once the queue is empty. Set
        'immediate' to True to make gets raise immediately instead.

        All blocked callers of put() and get() will be unblocked. If
        'immediate', a task is marked as done for each item remaining in
        the queue, which may unblock callers of join().
        """

        with self._mutex:
            self._is_shutdown = True

            if immediate:
                while self._qsize():
                    self._get()

                    if self._unfinished_tasks > 0:
                        self._unfinished_tasks -= 1

                # release all blocked threads in `join()`
                self._all_tasks_done.notify_all()

            # all getters need to re-check queue-empty to raise QueueShutDown
            self._not_empty.notify_all()
            self._not_full.notify_all()

    def close(self) -> None:
        with self._mutex:
            self._is_closing = True

            while self._qsize():
                self._get()

                if self._unfinished_tasks > 0:
                    self._unfinished_tasks -= 1

            # release all blocked threads in `join()`
            self._all_tasks_done.notify_all()

            # all getters need to re-check queue-empty to raise QueueShutDown
            self._not_empty.notify_all()
            self._not_full.notify_all()

    async def wait_closed(self) -> None:
        if not self._is_closing:
            raise RuntimeError("Waiting for non-closed queue")

        await checkpoint()

    # Override these methods to implement other queue organizations
    # (e.g. stack or priority queue).
    # These will only be called with appropriate locks held

    # Initialize the queue representation
    def _init(self, maxsize: int) -> None:
        self.data = deque()

    def _qsize(self) -> int:
        return len(self.data)

    # Put a new item in the queue
    def _put(self, item: T) -> None:
        self.data.append(item)

    def _peek(self) -> T:
        return self.data[0]

    # Get an item from the queue
    def _get(self) -> T:
        return self.data.popleft()

    @property
    def sync_q(self) -> SyncQueue[T]:
        return SyncQueueProxy(self)

    @property
    def async_q(self) -> AsyncQueue[T]:
        return AsyncQueueProxy(self)

    @property
    def unfinished_tasks(self) -> int:
        return self._unfinished_tasks

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    @property
    def closed(self) -> bool:
        return self._is_closing

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @maxsize.setter
    def maxsize(self, value: int) -> None:
        with self._mutex:
            maxsize = self._maxsize

            if value <= 0:
                self._not_full.notify_all()
            elif value > maxsize:
                self._not_full.notify(value - maxsize)

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

    def _peek(self) -> T:
        return self.data[-1]

    def _get(self) -> T:
        return self.data.pop()


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

    def _peek(self) -> T:
        return self.data[0]

    def _get(self) -> T:
        return heappop(self.data)


class SyncQueueProxy(SyncQueue[T]):
    __slots__ = ("wrapped",)

    def __init__(self, wrapped: Queue[T]) -> None:
        self.wrapped = wrapped

    def qsize(self) -> int:
        """Return the approximate size of the queue (not reliable!)."""

        wrapped = self.wrapped

        with wrapped._mutex:
            return wrapped._qsize()

    def empty(self) -> bool:
        """Return True if the queue is empty, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() == 0
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can grow before the result of empty() or
        qsize() can be used.

        To create code that needs to wait for all queued tasks to be
        completed, the preferred technique is to use the join() method.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            return not wrapped._qsize()

    def full(self) -> bool:
        """Return True if the queue is full, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() >= n
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can shrink before the result of full() or
        qsize() can be used.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            return 0 < wrapped._maxsize <= wrapped._qsize()

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
        the SyncQueueFull exception if no free slot was available within that
        time. Otherwise ('block' is False), put an item on the queue if a free
        slot is immediately available, else raise the SyncQueueFull exception
        ('timeout' is ignored in that case).

        Raises SyncQueueShutDown if the queue has been shut down.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            self._check_closing()

            if 0 < wrapped._maxsize:
                if not block:
                    if 0 < wrapped._maxsize <= wrapped._qsize():
                        raise SyncQueueFull
                elif timeout is None:
                    while 0 < wrapped._maxsize <= wrapped._qsize():
                        wrapped._not_full.wait()

                        self._check_closing()

                        rescheduled = True
                elif timeout < 0:
                    raise ValueError("'timeout' must be a non-negative number")
                else:
                    endtime = time.monotonic() + timeout

                    while 0 < wrapped._maxsize <= wrapped._qsize():
                        remaining = endtime - time.monotonic()

                        if remaining <= 0:
                            raise SyncQueueFull

                        wrapped._not_full.wait(remaining)

                        self._check_closing()

                        rescheduled = True

            wrapped._put(item)

            wrapped._unfinished_tasks += 1
            wrapped._not_empty.notify()

        if not rescheduled:
            green_checkpoint()

    def put_nowait(self, item: T) -> None:
        """Put an item into the queue without blocking.

        Only enqueue the item if a free slot is immediately available.
        Otherwise raise the SyncQueueFull exception.

        Raises SyncQueueShutDown if the queue has been shut down.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            self._check_closing()

            if 0 < wrapped._maxsize <= wrapped._qsize():
                raise SyncQueueFull

            wrapped._put(item)

            wrapped._unfinished_tasks += 1
            wrapped._not_empty.notify()

    def peek(self, block: bool = True, timeout: Optional[float] = None) -> T:
        """Return an item from the queue without removing it.

        If optional args 'block' is True and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the SyncQueueEmpty exception if no item was available within that time.
        Otherwise ('block' is False), return an item if one is immediately
        available, else raise the SyncQueueEmpty exception ('timeout' is
        ignored in that case).

        Raises SyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            if not wrapped._qsize():
                self._check_closing()

            if not block:
                if not wrapped._qsize():
                    raise SyncQueueEmpty
            elif timeout is None:
                while not wrapped._qsize():
                    wrapped._not_empty.wait()

                    if not wrapped._qsize():
                        self._check_closing()

                    rescheduled = True
            elif timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            else:
                endtime = time.monotonic() + timeout

                while not wrapped._qsize():
                    remaining = endtime - time.monotonic()

                    if remaining <= 0:
                        raise SyncQueueEmpty

                    wrapped._not_empty.wait(remaining)

                    if not wrapped._qsize():
                        self._check_closing()

                    rescheduled = True

            try:
                item = wrapped._peek()
            finally:
                if rescheduled:
                    wrapped._not_empty.notify()

        if not rescheduled:
            green_checkpoint()

        return item

    def peek_nowait(self) -> T:
        """Return an item from the queue without blocking.

        Only peek an item if one is immediately available.
        Otherwise raise the SyncQueueEmpty exception.

        Raises SyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            if not wrapped._qsize():
                self._check_closing()

                raise SyncQueueEmpty

            item = wrapped._peek()

        return item

    def get(self, block: bool = True, timeout: Optional[float] = None) -> T:
        """Remove and return an item from the queue.

        If optional args 'block' is True and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the SyncQueueEmpty exception if no item was available within that time.
        Otherwise ('block' is False), return an item if one is immediately
        available, else raise the SyncQueueEmpty exception ('timeout' is
        ignored in that case).

        Raises SyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            if not wrapped._qsize():
                self._check_closing()

            if not block:
                if not wrapped._qsize():
                    raise SyncQueueEmpty
            elif timeout is None:
                while not wrapped._qsize():
                    wrapped._not_empty.wait()

                    if not wrapped._qsize():
                        self._check_closing()

                    rescheduled = True
            elif timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            else:
                endtime = time.monotonic() + timeout

                while not wrapped._qsize():
                    remaining = endtime - time.monotonic()

                    if remaining <= 0:
                        raise SyncQueueEmpty

                    wrapped._not_empty.wait(remaining)

                    if not wrapped._qsize():
                        self._check_closing()

                    rescheduled = True

            item = wrapped._get()

            wrapped._not_full.notify()

        if not rescheduled:
            green_checkpoint()

        return item

    def get_nowait(self) -> T:
        """Remove and return an item from the queue without blocking.

        Only get an item if one is immediately available.
        Otherwise raise the SyncQueueEmpty exception.

        Raises SyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            if not wrapped._qsize():
                self._check_closing()

                raise SyncQueueEmpty

            item = wrapped._get()

            wrapped._not_full.notify()

        return item

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

        wrapped = self.wrapped

        with wrapped._mutex:
            unfinished = wrapped._unfinished_tasks - 1

            if not unfinished:
                wrapped._all_tasks_done.notify_all()
            elif unfinished < 0:
                raise ValueError("task_done() called too many times")

            wrapped._unfinished_tasks = unfinished

    def join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            while wrapped._unfinished_tasks:
                wrapped._all_tasks_done.wait()

                rescheduled = True

        if not rescheduled:
            green_checkpoint()

    def shutdown(self, immediate: bool = False) -> None:
        """Shut-down the queue, making queue gets and puts raise QueueShutDown.

        By default, gets will only raise once the queue is empty. Set
        'immediate' to True to make gets raise immediately instead.

        All blocked callers of put() and get() will be unblocked. If
        'immediate', a task is marked as done for each item remaining in
        the queue, which may unblock callers of join().
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            wrapped._is_shutdown = True

            if immediate:
                while wrapped._qsize():
                    wrapped._get()

                    if wrapped._unfinished_tasks > 0:
                        wrapped._unfinished_tasks -= 1

                # release all blocked threads in `join()`
                wrapped._all_tasks_done.notify_all()

            # all getters need to re-check queue-empty to raise QueueShutDown
            wrapped._not_empty.notify_all()
            wrapped._not_full.notify_all()

    def _check_closing(self) -> None:
        wrapped = self.wrapped

        if wrapped._is_closing:
            raise RuntimeError("Operation on the closed queue is forbidden")

        if wrapped._is_shutdown:
            raise SyncQueueShutDown

    @property
    def unfinished_tasks(self) -> int:
        return self.wrapped._unfinished_tasks

    @property
    def is_shutdown(self) -> bool:
        return self.wrapped._is_shutdown

    @property
    def closed(self) -> bool:
        return self.wrapped._is_closing

    @property
    def maxsize(self) -> int:
        return self.wrapped._maxsize

    @maxsize.setter
    def maxsize(self, value: int) -> None:
        wrapped = self.wrapped

        with wrapped._mutex:
            maxsize = wrapped._maxsize

            if value <= 0:
                wrapped._not_full.notify_all()
            elif value > maxsize:
                wrapped._not_full.notify(value - maxsize)

            wrapped._maxsize = value


class AsyncQueueProxy(AsyncQueue[T]):
    __slots__ = ("wrapped",)

    def __init__(self, wrapped: Queue[T]) -> None:
        self.wrapped = wrapped

    def qsize(self) -> int:
        """Return the approximate size of the queue (not reliable!)."""

        wrapped = self.wrapped

        with wrapped._mutex:
            return wrapped._qsize()

    def empty(self) -> bool:
        """Return True if the queue is empty, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() == 0
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can grow before the result of empty() or
        qsize() can be used.

        To create code that needs to wait for all queued tasks to be
        completed, the preferred technique is to use the join() method.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            return not wrapped._qsize()

    def full(self) -> bool:
        """Return True if the queue is full, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() >= n
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can shrink before the result of full() or
        qsize() can be used.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            return 0 < wrapped._maxsize <= wrapped._qsize()

    async def put(self, item: T) -> None:
        """Put an item into the queue.

        If the queue is full, wait until a free slot is available before adding
        item.

        Raises AsyncQueueShutDown if the queue has been shut down.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            self._check_closing()

            if 0 < wrapped._maxsize:
                while 0 < wrapped._maxsize <= wrapped._qsize():
                    await wrapped._not_full

                    self._check_closing()

                    rescheduled = True

            wrapped._put(item)

            wrapped._unfinished_tasks += 1
            wrapped._not_empty.notify()

        if not rescheduled:
            await checkpoint()

    def put_nowait(self, item: T) -> None:
        """Put an item into the queue without blocking.

        Only enqueue the item if a free slot is immediately available.
        Otherwise raise the AsyncQueueFull exception.

        Raises AsyncQueueShutDown if the queue has been shut down.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            self._check_closing()

            if 0 < wrapped._maxsize <= wrapped._qsize():
                raise AsyncQueueFull

            wrapped._put(item)

            wrapped._unfinished_tasks += 1
            wrapped._not_empty.notify()

    async def peek(self) -> T:
        """Return an item from the queue without removing it.

        If queue is empty, wait until an item is available.

        Raises AsyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            while not wrapped._qsize():
                self._check_closing()

                await wrapped._not_empty

                rescheduled = True

            try:
                item = wrapped._peek()
            finally:
                if rescheduled:
                    wrapped._not_empty.notify()

        if not rescheduled:
            await checkpoint()

        return item

    def peek_nowait(self) -> T:
        """Return an item from the queue without blocking.

        Only peek an item if one is immediately available.
        Otherwise raise the AsyncQueueEmpty exception.

        Raises AsyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            if not wrapped._qsize():
                self._check_closing()

                raise AsyncQueueEmpty

            item = wrapped._peek()

        return item

    async def get(self) -> T:
        """Remove and return an item from the queue.

        If queue is empty, wait until an item is available.

        Raises AsyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            while not wrapped._qsize():
                self._check_closing()

                await wrapped._not_empty

                rescheduled = True

            item = wrapped._get()

            wrapped._not_full.notify()

        if not rescheduled:
            await checkpoint()

        return item

    def get_nowait(self) -> T:
        """Remove and return an item from the queue without blocking.

        Only get an item if one is immediately available.
        Otherwise raise the AsyncQueueEmpty exception.

        Raises AsyncQueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            if not wrapped._qsize():
                self._check_closing()

                raise AsyncQueueEmpty

            item = wrapped._get()

            wrapped._not_full.notify()

        return item

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

        wrapped = self.wrapped

        with wrapped._mutex:
            unfinished = wrapped._unfinished_tasks - 1

            if not unfinished:
                wrapped._all_tasks_done.notify_all()
            elif unfinished < 0:
                raise ValueError("task_done() called too many times")

            wrapped._unfinished_tasks = unfinished

    async def join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """

        wrapped = self.wrapped

        rescheduled = False

        with wrapped._mutex:
            while wrapped._unfinished_tasks:
                await wrapped._all_tasks_done

                rescheduled = True

        if not rescheduled:
            await checkpoint()

    def shutdown(self, immediate: bool = False) -> None:
        """Shut-down the queue, making queue gets and puts raise QueueShutDown.

        By default, gets will only raise once the queue is empty. Set
        'immediate' to True to make gets raise immediately instead.

        All blocked callers of put() and get() will be unblocked. If
        'immediate', a task is marked as done for each item remaining in
        the queue, which may unblock callers of join().
        """

        wrapped = self.wrapped

        with wrapped._mutex:
            wrapped._is_shutdown = True

            if immediate:
                while wrapped._qsize():
                    wrapped._get()

                    if wrapped._unfinished_tasks > 0:
                        wrapped._unfinished_tasks -= 1

                # release all blocked threads in `join()`
                wrapped._all_tasks_done.notify_all()

            # all getters need to re-check queue-empty to raise QueueShutDown
            wrapped._not_empty.notify_all()
            wrapped._not_full.notify_all()

    def _check_closing(self) -> None:
        wrapped = self.wrapped

        if wrapped._is_closing:
            raise RuntimeError("Operation on the closed queue is forbidden")

        if wrapped._is_shutdown:
            raise AsyncQueueShutDown

    @property
    def unfinished_tasks(self) -> int:
        return self.wrapped._unfinished_tasks

    @property
    def is_shutdown(self) -> bool:
        return self.wrapped._is_shutdown

    @property
    def closed(self) -> bool:
        return self.wrapped._is_closing

    @property
    def maxsize(self) -> int:
        return self.wrapped._maxsize

    @maxsize.setter
    def maxsize(self, value: int) -> None:
        wrapped = self.wrapped

        with wrapped._mutex:
            maxsize = wrapped._maxsize

            if value <= 0:
                wrapped._not_full.notify_all()
            elif value > maxsize:
                wrapped._not_full.notify(value - maxsize)

            wrapped._maxsize = value
