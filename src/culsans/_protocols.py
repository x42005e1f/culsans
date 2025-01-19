#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class BaseQueue(Protocol[T]):
    __slots__ = ()

    def peekable(self) -> bool:
        """Return True if the queue is peekable, False otherwise."""
        ...

    def qsize(self) -> int:
        """Return the approximate size of the queue (not reliable!)."""
        ...

    def empty(self) -> bool:
        """Return True if the queue is empty, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() == 0
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can grow before the result of empty() or
        qsize() can be used.

        To create code that needs to wait for all queued tasks to be
        completed, the preferred technique is to use the join() method.
        """
        ...

    def full(self) -> bool:
        """Return True if the queue is full, False otherwise (not reliable!).

        This method is likely to be removed at some point.  Use qsize() >= n
        as a direct substitute, but be aware that either approach risks a race
        condition where a queue can shrink before the result of full() or
        qsize() can be used.
        """
        ...

    def put_nowait(self, item: T) -> None:
        """Put an item into the queue without blocking.

        Only enqueue the item if a free slot is immediately available.
        Otherwise raise the QueueFull exception.

        Raises QueueShutDown if the queue has been shut down.
        """
        ...

    def get_nowait(self) -> T:
        """Remove and return an item from the queue without blocking.

        Only get an item if one is immediately available.
        Otherwise raise the QueueEmpty exception.

        Raises QueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """
        ...

    def peek_nowait(self) -> T:
        """Return an item from the queue without blocking.

        Only peek an item if one is immediately available.
        Otherwise raise the QueueEmpty exception.

        Raises QueueShutDown if the queue has been shut down and is empty,
        or if the queue has been shut down immediately.
        """
        ...

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
        ...

    def shutdown(self, immediate: bool = False) -> None:
        """Shut-down the queue, making queue gets and puts raise QueueShutDown.

        By default, gets will only raise once the queue is empty. Set
        'immediate' to True to make gets raise immediately instead.

        All blocked callers of put() and get() will be unblocked. If
        'immediate', a task is marked as done for each item remaining in
        the queue, which may unblock callers of join().
        """
        ...

    def clear(self) -> None:
        """Clear all items from the queue atomically."""
        ...

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
        timeout: float | None = None,
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
        ...

    def get(self, block: bool = True, timeout: float | None = None) -> T:
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
        ...

    def peek(self, block: bool = True, timeout: float | None = None) -> T:
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
        ...

    def join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        ...


class AsyncQueue(BaseQueue[T], Protocol[T]):
    __slots__ = ()

    async def put(self, item: T) -> None:
        """Put an item into the queue.

        If the queue is full, wait until a free slot is available before adding
        item.

        Raises QueueShutDown if the queue has been shut down.
        """
        ...

    async def get(self) -> T:
        """Remove and return an item from the queue.

        If queue is empty, wait until an item is available.

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """
        ...

    async def peek(self) -> T:
        """Return an item from the queue without removing it.

        If queue is empty, wait until an item is available.

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """
        ...

    async def join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        ...


class MixedQueue(BaseQueue[T], Protocol[T]):
    __slots__ = ()

    def sync_put(
        self,
        item: T,
        block: bool = True,
        timeout: float | None = None,
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
        ...

    async def async_put(self, item: T) -> None:
        """Put an item into the queue.

        If the queue is full, wait until a free slot is available before adding
        item.

        Raises QueueShutDown if the queue has been shut down.
        """
        ...

    def sync_get(
        self,
        block: bool = True,
        timeout: float | None = None,
    ) -> T:
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
        ...

    async def async_get(self) -> T:
        """Remove and return an item from the queue.

        If queue is empty, wait until an item is available.

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """
        ...

    def sync_peek(
        self,
        block: bool = True,
        timeout: float | None = None,
    ) -> T:
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
        ...

    async def async_peek(self) -> T:
        """Return an item from the queue without removing it.

        If queue is empty, wait until an item is available.

        Raises QueueShutDown if the queue has been shut down and is empty, or
        if the queue has been shut down immediately.
        """
        ...

    def sync_join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        ...

    async def async_join(self) -> None:
        """Blocks until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate that the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        ...

    @property
    def sync_q(self) -> SyncQueue[T]: ...

    @property
    def async_q(self) -> AsyncQueue[T]: ...
