#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

from typing import Protocol, TypeVar

from ._utils import _copydoc as copydoc

_T = TypeVar("_T")


class BaseQueue(Protocol[_T]):
    """
    A base queue protocol that includes all except blocking methods.

    Can be useful when you need to make sure that none of the methods will
    block (except for the underlying lock).
    """

    __slots__ = ()

    def peekable(self) -> bool:
        """
        Return :data:`True` if the queue is peekable, :data:`False` otherwise.
        """
        ...

    def qsize(self) -> int:
        """
        Return the number of items in the queue.

        This method is provided for compatibility with the standard queues.
        Note, ``queue.qsize() > 0`` does not guarantee that subsequent get/peek
        calls will not block. Similarly, ``queue.qsize() < queue.maxsize`` does
        not guarantee that subsequent put calls will not block.
        """
        ...

    def empty(self) -> bool:
        """
        Return :data:`True` if the queue is empty, :data:`False` otherwise.

        This method is provided for compatibility with the standard queues. Use
        ``queue.qsize() == 0`` as a direct substitute, but be aware that either
        approach risks a race condition where the queue can grow before the
        result of :meth:`empty` or :meth:`qsize` can be used.

        To create code that needs to wait for all queued tasks to be completed,
        the preferred technique is to use the join methods.
        """
        ...

    def full(self) -> bool:
        """
        Return :data:`True` if the queue is full, :data:`False` otherwise.

        This method is provided for compatibility with the standard queues. Use
        ``queue.qsize() >= queue.maxsize`` as a direct substitute, but be aware
        that either approach risks a race condition where the queue can shrink
        before the result of :meth:`full` or :meth:`qsize` can be used.
        """
        ...

    def put_nowait(self, item: _T) -> None:
        """
        Put *item* into the queue without blocking.

        Only put (enqueue) the item if a free slot is immediately available.

        Raises:
          QueueFull:
            if the queue is full.
          QueueShutDown:
            if the queue has been shut down.
        """
        ...

    def get_nowait(self) -> _T:
        """
        Remove and return an item from the queue without blocking.

        Only get (dequeue) an item if one is immediately available.

        Raises:
          QueueEmpty:
            if the queue is empty.
          QueueShutDown:
            if the queue has been shut down and is empty, or if the queue has
            been shut down immediately.
        """
        ...

    def peek_nowait(self) -> _T:
        """
        Return an item from the queue without blocking.

        Only peek (front) an item if one is immediately available.

        Raises:
          QueueEmpty:
            if the queue is empty.
          QueueShutDown:
            if the queue has been shut down and is empty, or if the queue has
            been shut down immediately.
          UnsupportedOperation:
            if the queue is not peekable.
        """
        ...

    def task_done(self) -> None:
        """
        Indicate that a formerly enqueued task is complete.

        Used by queue consumers.  For each get call used to fetch a task,
        a subsequent call to :meth:`task_done` tells the queue that the
        processing on the task is complete.

        If a join call is currently blocking, it will resume when all items
        have been processed (meaning that a :meth:`task_done` call was received
        for every item that had been put into the queue).

        Raises:
          ValueError:
            if called more times than there were items placed in the queue.
        """
        ...

    def shutdown(self, immediate: bool = False) -> None:
        """
        Put the queue into a shutdown mode.

        The queue can no longer grow. Future calls to the put methods raise
        :exc:`QueueShutDown`. Currently blocked callers of the put methods will
        be unblocked and will raise :exc:`QueueShutDown` in the formerly
        blocked thread/task.

        Once the queue is empty, the get/peek methods will also raise
        :exc:`QueueShutDown`.

        Args:
          immediate:
            If set to :data:`True`, the queue is drained to be completely
            empty, and :meth:`task_done` is called for each item removed from
            the queue (but joiners are unblocked regardless of the number of
            unfinished tasks).
        """
        ...

    def clear(self) -> None:
        """
        Clear all items from the queue atomically.

        Also calls :meth:`task_done` for each removed item.
        """
        ...

    @property
    def unfinished_tasks(self) -> int:
        """
        The current number of tasks remaining to be processed.

        See the :meth:`task_done` method.
        """
        ...

    @property
    def is_shutdown(self) -> bool:
        """
        A boolean that is :data:`True` if the queue has been shut down,
        :data:`False` otherwise.

        See the :meth:`shutdown` method.
        """
        ...

    @property
    def closed(self) -> bool:
        """
        A boolean that is :data:`True` if the queue has been closed,
        :data:`False` otherwise.

        This property is provided for compatibility with the Janus queues. Use
        :attr:`queue.is_shutdown <is_shutdown>` as a direct substitute.
        """
        ...

    @property
    def maxsize(self) -> int:
        """
        The maximum number of items which the queue can hold.

        It can be changed dynamically by setting the attribute.
        """
        ...

    @maxsize.setter
    def maxsize(self, value: int) -> None: ...


class MixedQueue(BaseQueue[_T], Protocol[_T]):
    """
    A mixed queue protocol that includes both types of blocking methods via
    prefixes.

    Provides specialized proxies via properties.
    """

    __slots__ = ()

    def sync_put(
        self,
        item: _T,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        """
        Put *item* into the queue.

        Args:
          block:
            Unless set to :data:`False`, the method will block if necessary
            until a free slot is available. Otherwise, ``timeout=0`` is
            implied.
          timeout:
            If set to a non-negative number, the method will block at most
            *timeout* seconds and raise the :exc:`QueueFull` exception if no
            free slot was available within that time.

        Raises:
          QueueFull:
            if the queue is full and the timeout has expired.
          QueueShutDown:
            if the queue has been shut down.
          ValueError:
            if *timeout* is negative or :data:`NaN <math.nan>`.
        """
        ...

    async def async_put(self, item: _T) -> None:
        """
        Put *item* into the queue.

        If the queue is full, wait until a free slot is available.

        Raises:
          QueueShutDown:
            if the queue has been shut down.
        """
        ...

    def sync_get(
        self,
        block: bool = True,
        timeout: float | None = None,
    ) -> _T:
        """
        Remove and return an item from the queue.

        Args:
          block:
            Unless set to :data:`False`, the method will block if necessary
            until an item is available. Otherwise, ``timeout=0`` is implied.
          timeout:
            If set to a non-negative number, the method will block at most
            *timeout* seconds and raise the :exc:`QueueEmpty` exception if no
            item was available within that time.

        Raises:
          QueueEmpty:
            if the queue is empty and the timeout has expired.
          QueueShutDown:
            if the queue has been shut down and is empty, or if the queue has
            been shut down immediately.
          ValueError:
            if *timeout* is negative or :data:`NaN <math.nan>`.
        """
        ...

    async def async_get(self) -> _T:
        """
        Remove and return an item from the queue.

        If the queue is empty, wait until an item is available.

        Raises:
          QueueShutDown:
            if the queue has been shut down and is empty, or if the queue has
            been shut down immediately.
        """
        ...

    def sync_peek(
        self,
        block: bool = True,
        timeout: float | None = None,
    ) -> _T:
        """
        Return an item from the queue without removing it.

        Args:
          block:
            Unless set to :data:`False`, the method will block if necessary
            until an item is available. Otherwise, ``timeout=0`` is implied.
          timeout:
            If set to a non-negative number, the method will block at most
            *timeout* seconds and raise the :exc:`QueueEmpty` exception if no
            item was available within that time.

        Raises:
          QueueEmpty:
            if the queue is empty and the timeout has expired.
          QueueShutDown:
            if the queue has been shut down and is empty, or if the queue has
            been shut down immediately.
          UnsupportedOperation:
            if the queue is not peekable.
          ValueError:
            if *timeout* is negative or :data:`NaN <math.nan>`.
        """
        ...

    async def async_peek(self) -> _T:
        """
        Return an item from the queue without removing it.

        If the queue is empty, wait until an item is available.

        Raises:
          QueueShutDown:
            if the queue has been shut down and is empty, or if the queue has
            been shut down immediately.
          UnsupportedOperation:
            if the queue is not peekable.
        """
        ...

    def sync_join(self) -> None:
        """
        Block until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls
        :meth:`~BaseQueue.task_done` to indicate that the item was retrieved
        and all work on it is complete.

        When the count of unfinished tasks drops to zero, the caller unblocks.
        """
        ...

    async def async_join(self) -> None:
        """
        Block until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls
        :meth:`~BaseQueue.task_done` to indicate that the item was retrieved
        and all work on it is complete.

        When the count of unfinished tasks drops to zero, the caller unblocks.
        """
        ...

    @property
    def sync_q(self) -> SyncQueue[_T]:
        """
        An interface compatible with the standard queues from the :mod:`queue`
        module.
        """
        ...

    @property
    def async_q(self) -> AsyncQueue[_T]:
        """
        An interface compatible with the standard queues from the
        :mod:`asyncio` module.
        """
        ...


class SyncQueue(BaseQueue[_T], Protocol[_T]):
    """
    A synchronous queue protocol that covers the standard queues' interface
    from the :mod:`queue` module.

    Compliant with the Python API version 3.13.
    """

    __slots__ = ()

    @copydoc(MixedQueue.sync_put)
    def put(
        self,
        item: _T,
        block: bool = True,
        timeout: float | None = None,
    ) -> None: ...
    @copydoc(MixedQueue.sync_get)
    def get(self, block: bool = True, timeout: float | None = None) -> _T: ...
    @copydoc(MixedQueue.sync_peek)
    def peek(self, block: bool = True, timeout: float | None = None) -> _T: ...
    @copydoc(MixedQueue.sync_join)
    def join(self) -> None: ...


class AsyncQueue(BaseQueue[_T], Protocol[_T]):
    """
    An asynchronous queue protocol that covers the standard queues' interface
    from the :mod:`asyncio` module.

    Compliant with the Python API version 3.13.
    """

    __slots__ = ()

    @copydoc(MixedQueue.async_put)
    async def put(self, item: _T) -> None: ...
    @copydoc(MixedQueue.async_get)
    async def get(self) -> _T: ...
    @copydoc(MixedQueue.async_peek)
    async def peek(self) -> _T: ...
    @copydoc(MixedQueue.async_join)
    async def join(self) -> None: ...
