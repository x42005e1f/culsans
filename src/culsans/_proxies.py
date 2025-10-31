#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

from typing import TypeVar

from ._protocols import AsyncQueue, MixedQueue, SyncQueue

_T = TypeVar("_T")


class SyncQueueProxy(SyncQueue[_T]):
    """
    A proxy that implements the :class:`SyncQueue` protocol by wrapping a mixed
    queue.
    """

    __slots__ = ("wrapped",)

    wrapped: MixedQueue[_T]

    def __init__(self, wrapped: MixedQueue[_T]) -> None:
        self.wrapped = wrapped

    def __repr__(self) -> str:
        cls = self.__class__
        cls_repr = f"{cls.__module__}.{cls.__qualname__}"

        return f"{cls_repr}({self.wrapped!r})"

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
        item: _T,
        block: bool = True,
        timeout: float | None = None,
    ) -> None:
        self.wrapped.sync_put(item, block, timeout)

    def put_nowait(self, item: _T) -> None:
        self.wrapped.put_nowait(item)

    def get(self, block: bool = True, timeout: float | None = None) -> _T:
        return self.wrapped.sync_get(block, timeout)

    def get_nowait(self) -> _T:
        return self.wrapped.get_nowait()

    def peek(self, block: bool = True, timeout: float | None = None) -> _T:
        return self.wrapped.sync_peek(block, timeout)

    def peek_nowait(self) -> _T:
        return self.wrapped.peek_nowait()

    def join(self) -> None:
        self.wrapped.sync_join()

    def task_done(self) -> None:
        self.wrapped.task_done()

    def shutdown(self, immediate: bool = False) -> None:
        self.wrapped.shutdown(immediate)

    def clear(self) -> None:
        self.wrapped.clear()

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


class AsyncQueueProxy(AsyncQueue[_T]):
    """
    A proxy that implements the :class:`AsyncQueue` protocol by wrapping a
    mixed queue.
    """

    __slots__ = ("wrapped",)

    wrapped: MixedQueue[_T]

    def __init__(self, wrapped: MixedQueue[_T]) -> None:
        self.wrapped = wrapped

    def __repr__(self) -> str:
        cls = self.__class__
        cls_repr = f"{cls.__module__}.{cls.__qualname__}"

        return f"{cls_repr}({self.wrapped!r})"

    def peekable(self) -> bool:
        return self.wrapped.peekable()

    def qsize(self) -> int:
        return self.wrapped.qsize()

    def empty(self) -> bool:
        return self.wrapped.empty()

    def full(self) -> bool:
        return self.wrapped.full()

    async def put(self, item: _T) -> None:
        await self.wrapped.async_put(item)

    def put_nowait(self, item: _T) -> None:
        self.wrapped.put_nowait(item)

    async def get(self) -> _T:
        return await self.wrapped.async_get()

    def get_nowait(self) -> _T:
        return self.wrapped.get_nowait()

    async def peek(self) -> _T:
        return await self.wrapped.async_peek()

    def peek_nowait(self) -> _T:
        return self.wrapped.peek_nowait()

    async def join(self) -> None:
        await self.wrapped.async_join()

    def task_done(self) -> None:
        self.wrapped.task_done()

    def shutdown(self, immediate: bool = False) -> None:
        self.wrapped.shutdown(immediate)

    def clear(self) -> None:
        self.wrapped.clear()

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
