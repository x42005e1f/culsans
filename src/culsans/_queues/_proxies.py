#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from aiologic.meta import DEFAULT

from ._protocols import (
    AsyncQueue,
    BaseQueue,
    GreenQueue,
    MixedQueue,
    SyncQueue,
)

if TYPE_CHECKING:
    from aiologic.meta import DefaultType

_T = TypeVar("_T")


class BaseQueueProxy(BaseQueue[_T]):
    """
    A proxy that implements the :class:`BaseQueue` protocol by wrapping a mixed
    queue.
    """

    __slots__ = (
        "__weakref__",
        "wrapped",
    )

    wrapped: MixedQueue[_T]

    def __init__(self, /, wrapped: MixedQueue[_T]) -> None:
        self.wrapped = wrapped

    def __repr__(self, /) -> str:
        cls = self.__class__
        cls_repr = f"{cls.__module__}.{cls.__qualname__}"

        return f"{cls_repr}({self.wrapped!r})"

    def __bool__(self, /) -> bool:
        return bool(self.wrapped)

    def __len__(self, /) -> int:
        return len(self.wrapped)

    def peekable(self, /) -> bool:
        return self.wrapped.peekable()

    def clearable(self, /) -> bool:
        return self.wrapped.clearable()

    def isize(self, /, item: _T) -> int:
        return self.wrapped.isize(item)

    def qsize(self, /) -> int:
        return self.wrapped.qsize()

    def empty(self, /) -> bool:
        return self.wrapped.empty()

    def full(self, /) -> bool:
        return self.wrapped.full()

    def put_nowait(self, /, item: _T) -> None:
        self.wrapped.put_nowait(item)

    def get_nowait(self, /) -> _T:
        return self.wrapped.get_nowait()

    def peek_nowait(self, /) -> _T:
        return self.wrapped.peek_nowait()

    def task_done(self, /) -> None:
        self.wrapped.task_done()

    def shutdown(self, /, immediate: bool = False) -> None:
        self.wrapped.shutdown(immediate)

    def clear(self, /) -> None:
        self.wrapped.clear()

    @property
    def unfinished_tasks(self, /) -> int:
        return self.wrapped.unfinished_tasks

    @property
    def is_shutdown(self, /) -> bool:
        return self.wrapped.is_shutdown

    @property
    def closed(self, /) -> bool:
        return self.wrapped.closed

    @property
    def maxsize(self, /) -> int:
        return self.wrapped.maxsize

    @maxsize.setter
    def maxsize(self, value: int, /) -> None:
        self.wrapped.maxsize = value

    @property
    def size(self, /) -> int:
        return self.wrapped.size


class SyncQueueProxy(BaseQueueProxy[_T], SyncQueue[_T]):
    """
    A proxy that implements the :class:`SyncQueue` protocol by wrapping a mixed
    queue.
    """

    __slots__ = ()

    def put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None:
        self.wrapped.sync_put(item, block, timeout, blocking=blocking)

    def get(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        return self.wrapped.sync_get(block, timeout, blocking=blocking)

    def peek(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        return self.wrapped.sync_peek(block, timeout, blocking=blocking)

    def join(self, /) -> None:
        self.wrapped.sync_join()


class GreenQueueProxy(BaseQueueProxy[_T], GreenQueue[_T]):
    """
    A proxy that implements the :class:`GreenQueue` protocol by wrapping a
    mixed queue.
    """

    __slots__ = ()

    def put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None:
        self.wrapped.green_put(item, block, timeout, blocking=blocking)

    def get(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        return self.wrapped.green_get(block, timeout, blocking=blocking)

    def peek(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        return self.wrapped.green_peek(block, timeout, blocking=blocking)

    def join(self, /) -> None:
        self.wrapped.green_join()


class AsyncQueueProxy(BaseQueueProxy[_T], AsyncQueue[_T]):
    """
    A proxy that implements the :class:`AsyncQueue` protocol by wrapping a
    mixed queue.
    """

    __slots__ = ()

    async def put(self, /, item: _T) -> None:
        await self.wrapped.async_put(item)

    async def get(self, /) -> _T:
        return await self.wrapped.async_get()

    async def peek(self, /) -> _T:
        return await self.wrapped.async_peek()

    async def join(self, /) -> None:
        await self.wrapped.async_join()
