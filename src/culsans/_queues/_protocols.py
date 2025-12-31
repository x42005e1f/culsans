#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

import sys

from typing import TYPE_CHECKING, TypeVar

from aiologic.meta import DEFAULT

from culsans._utils import copydoc

if TYPE_CHECKING:
    from aiologic.meta import DefaultType

if sys.version_info >= (3, 13):  # various fixes and improvements
    from typing import Protocol
else:  # typing-extensions>=4.10.0
    from typing_extensions import Protocol

_T = TypeVar("_T")


class BaseQueue(Protocol[_T]):
    """
    A base queue protocol that includes all except blocking methods.

    Can be useful when you need to make sure that none of the methods will
    block (except for the underlying lock).
    """

    __slots__ = ()

    def __bool__(self, /) -> bool:
        """
        Return :data:`True` if the queue is not empty, :data:`False` otherwise.

        Note, ``bool(queue)`` does not guarantee that subsequent get/peek calls
        will not block (such an approach risks a race condition where the queue
        can shrink before the result can be used).

        To create code that needs to wait for all queued tasks to be completed,
        the preferred technique is to use the join methods.
        """
        ...

    def __len__(self, /) -> int:
        """
        Return the number of items in the queue.

        Note, ``len(queue) > 0`` does not guarantee that subsequent get/peek
        calls will not block (such an approach risks a race condition where the
        queue can shrink before the result can be used).

        To create code that needs to wait for all queued tasks to be completed,
        the preferred technique is to use the join methods.
        """
        ...

    def peekable(self, /) -> bool:
        """
        Return :data:`True` if the queue is peekable, :data:`False` otherwise.
        """
        ...

    def clearable(self, /) -> bool:
        """
        Return :data:`True` if the queue is clearable, :data:`False` otherwise.
        """
        ...

    def isize(self, /, item: _T) -> int:
        """
        Return the size of the item.

        This method uses the sizer passed during initialization. If it was not
        passed (and the corresponding protected attribute/method was not
        defined), it returns 1 for any object.
        """
        ...

    def qsize(self, /) -> int:
        """
        This method is provided for compatibility with the standard queues. Use
        :meth:`len(queue) <__len__>` as a direct substitute.
        """
        ...

    def empty(self, /) -> bool:
        """
        This method is provided for compatibility with the standard queues. Use
        :meth:`not queue <__bool__>` as a direct substitute.
        """
        ...

    def full(self, /) -> bool:
        """
        Return :data:`True` if the queue is full, :data:`False` otherwise.

        Note, ``not queue.full()`` does not guarantee that subsequent put calls
        will not block (such an approach risks a race condition where the queue
        can grow before the result can be used).
        """
        ...

    def put_nowait(self, /, item: _T) -> None:
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

    def get_nowait(self, /) -> _T:
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

    def peek_nowait(self, /) -> _T:
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

    def task_done(self, /) -> None:
        """
        Indicate that a formerly enqueued task is complete.

        Used by queue consumers. For each get call used to fetch a task, a
        subsequent call to :meth:`task_done` tells the queue that the
        processing on the task is complete.

        If a join call is currently blocking, it will resume when all items
        have been processed (meaning that a :meth:`task_done` call was received
        for every item that had been put into the queue).

        Raises:
          ValueError:
            if called more times than there were items placed in the queue.
        """
        ...

    def shutdown(self, /, immediate: bool = False) -> None:
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

    def clear(self, /) -> None:
        """
        Clear all items from the queue atomically.

        Also calls :meth:`task_done` for each removed item.

        Raises:
          UnsupportedOperation:
            if the queue is not clearable.
        """
        ...

    @property
    def unfinished_tasks(self, /) -> int:
        """
        The current number of tasks remaining to be processed.

        See the :meth:`task_done` method.
        """
        ...

    @property
    def is_shutdown(self, /) -> bool:
        """
        A boolean that is :data:`True` if the queue has been shut down,
        :data:`False` otherwise.

        See the :meth:`shutdown` method.
        """
        ...

    @property
    def closed(self, /) -> bool:
        """
        This property is provided for compatibility with the Janus queues. Use
        :attr:`is_shutdown` as a direct substitute.
        """
        ...

    @property
    def maxsize(self, /) -> int:
        """
        The maximum cumulative size of items which the queue can hold.

        if *maxsize* is <= 0, the size is infinite. If it is an integer greater
        that 0, then the put methods block when the queue reaches *maxsize*
        until an item is removed by the get methods.

        It can be changed dynamically by setting the attribute.
        """
        ...

    @maxsize.setter
    def maxsize(self, value: int, /) -> None: ...

    @property
    def size(self, /) -> int:
        """
        The current cumulative size of items in the queue.
        """
        ...


class MixedQueue(BaseQueue[_T], Protocol[_T]):
    """
    A mixed queue protocol that includes both types of blocking methods via
    prefixes.

    Provides specialized proxies via properties.
    """

    __slots__ = ()

    def sync_put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None:
        """
        This method is provided for consistency with the Janus queues. Use
        :meth:`green_put` as a direct substitute.
        """
        ...

    def green_put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None:
        """
        Put *item* into the queue.

        Args:
          block:
            This parameter is provided for compatibility with the standard
            queues. Use *blocking* as a direct substitute.
          blocking:
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
        """
        ...

    async def async_put(self, /, item: _T) -> None:
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
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        """
        This method is provided for consistency with the Janus queues. Use
        :meth:`green_get` as a direct substitute.
        """
        ...

    def green_get(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        """
        Remove and return an item from the queue.

        Args:
          block:
            This parameter is provided for compatibility with the standard
            queues. Use *blocking* as a direct substitute.
          blocking:
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
        """
        ...

    async def async_get(self, /) -> _T:
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
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        """
        This method is provided for consistency with the Janus queues. Use
        :meth:`green_peek` as a direct substitute.
        """
        ...

    def green_peek(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        """
        Return an item from the queue without removing it.

        Args:
          block:
            This parameter is provided for compatibility with the standard
            queues. Use *blocking* as a direct substitute.
          blocking:
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
        """
        ...

    async def async_peek(self, /) -> _T:
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

    def sync_join(self, /) -> None:
        """
        This method is provided for consistency with the Janus queues. Use
        :meth:`green_join` as a direct substitute.
        """
        ...

    def green_join(self, /) -> None:
        """
        Block until all items in the queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls
        :meth:`~BaseQueue.task_done` to indicate that the item was retrieved
        and all work on it is complete.

        When the count of unfinished tasks drops to zero, the caller unblocks.
        """
        ...

    async def async_join(self, /) -> None:
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
    def green_proxy(self, /) -> GreenQueue[_T]:
        """
        An interface compatible with the standard queues from the :mod:`queue`
        module.
        """
        ...

    @property
    def async_proxy(self, /) -> AsyncQueue[_T]:
        """
        An interface compatible with the standard queues from the
        :mod:`asyncio` module.
        """
        ...

    @property
    def sync_q(self, /) -> SyncQueue[_T]:
        """
        This property is provided for compatibility with the Janus queues. Use
        :attr:`green_proxy` instead.
        """
        ...

    @property
    def async_q(self, /) -> AsyncQueue[_T]:
        """
        This property is provided for compatibility with the Janus queues. Use
        :attr:`async_proxy` as a direct substitute.
        """
        ...


class SyncQueue(BaseQueue[_T], Protocol[_T]):
    """
    This protocol is provided for compatibility with the Janus queues. Use
    :class:`GreenQueue` instead.
    """

    __slots__ = ()

    @copydoc(MixedQueue.green_put)
    def put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None: ...
    @copydoc(MixedQueue.green_get)
    def get(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T: ...
    @copydoc(MixedQueue.green_peek)
    def peek(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T: ...
    @copydoc(MixedQueue.green_join)
    def join(self, /) -> None: ...


class GreenQueue(BaseQueue[_T], Protocol[_T]):
    """
    A queue protocol that covers the standard queues' interface from the
    :mod:`queue` module.

    Compliant with the Python API version 3.13.
    """

    __slots__ = ()

    @copydoc(MixedQueue.green_put)
    def put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None: ...
    @copydoc(MixedQueue.green_get)
    def get(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T: ...
    @copydoc(MixedQueue.green_peek)
    def peek(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T: ...
    @copydoc(MixedQueue.green_join)
    def join(self, /) -> None: ...


class AsyncQueue(BaseQueue[_T], Protocol[_T]):
    """
    A queue protocol that covers the standard queues' interface from the
    :mod:`asyncio` module.

    Compliant with the Python API version 3.13.
    """

    __slots__ = ()

    @copydoc(MixedQueue.async_put)
    async def put(self, /, item: _T) -> None: ...
    @copydoc(MixedQueue.async_get)
    async def get(self, /) -> _T: ...
    @copydoc(MixedQueue.async_peek)
    async def peek(self, /) -> _T: ...
    @copydoc(MixedQueue.async_join)
    async def join(self, /) -> None: ...
