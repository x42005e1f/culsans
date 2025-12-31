#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

import sys

from collections import deque
from heapq import heappop, heappush
from math import inf, isinf, isnan
from typing import TYPE_CHECKING, Protocol, TypeVar, Union

from aiologic import Condition
from aiologic.lowlevel import (
    async_checkpoint,
    async_checkpoint_enabled,
    create_thread_rlock,
    green_checkpoint,
    green_checkpoint_enabled,
    green_clock,
)
from aiologic.meta import DEFAULT, DefaultType, copies

from ._exceptions import (
    QueueEmpty,
    QueueFull,
    QueueShutDown,
    UnsupportedOperation,
)
from ._protocols import MixedQueue
from ._proxies import AsyncQueueProxy, GreenQueueProxy, SyncQueueProxy

if TYPE_CHECKING:
    from typing import Any

    from aiologic.lowlevel import ThreadRLock

    if sys.version_info >= (3, 9):  # PEP 585
        from collections.abc import Callable
    else:
        from typing import Callable

if sys.version_info >= (3, 12):  # PEP 698
    from typing import override
else:  # typing-extensions>=4.5.0
    from typing_extensions import override


class _SupportsBool(Protocol):
    def __bool__(self, /) -> bool: ...


class _SupportsLT(Protocol):
    def __lt__(self, other: Any, /) -> _SupportsBool: ...


class _SupportsGT(Protocol):
    def __gt__(self, other: Any, /) -> _SupportsBool: ...


_T = TypeVar("_T")
_RichComparableT = TypeVar(
    "_RichComparableT",
    bound=Union[_SupportsLT, _SupportsGT],
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
        "__one_get_one_item",
        "__one_put_one_item",
        "__weakref__",
        "_is_shutdown",
        "_isize",
        "_maxsize",
        "_size",
        "_unfinished_tasks",
        "all_tasks_done",
        "mutex",
        "not_empty",
        "not_full",
    )

    __data: deque[_T]

    __one_put_one_item: bool
    __one_get_one_item: bool

    _isize: Callable[[_T], int]

    _size: int
    _maxsize: int
    _unfinished_tasks: int
    _is_shutdown: bool

    mutex: ThreadRLock

    not_full: Condition[ThreadRLock]
    not_empty: Condition[ThreadRLock]
    all_tasks_done: Condition[ThreadRLock]

    def __init__(
        self,
        /,
        maxsize: int = 0,
        *,
        sizer: Callable[[_T], int] | DefaultType = DEFAULT,
    ) -> None:
        """
        Create a queue object with the given maximum size.

        Args:
          sizer:
            A function used to calculate the size of each item in the queue.
        """

        if sizer is DEFAULT:
            if not hasattr(self, "_isize"):
                self._isize = self.__isize
        else:
            self._isize = sizer

        self._size = 0
        self._maxsize = maxsize
        self._unfinished_tasks = 0
        self._is_shutdown = False

        self.mutex = mutex = create_thread_rlock()

        self.not_full = Condition(mutex)  # putters
        self.not_empty = Condition(mutex)  # getters
        self.all_tasks_done = Condition(mutex)  # joiners

        self.__one_put_one_item = True
        self.__one_get_one_item = True

        self._init(maxsize)  # data

    def __bool__(self, /) -> bool:
        with self.mutex:
            return 0 < self._qsize()

    def __len__(self, /) -> int:
        with self.mutex:
            return self._qsize()

    def peekable(self, /) -> bool:
        with self.mutex:
            return self._peekable()

    def clearable(self, /) -> bool:
        with self.mutex:
            return self._clearable()

    def isize(self, /, item: _T) -> int:
        with self.mutex:
            return self._isize(item)

    def qsize(self, /) -> int:
        with self.mutex:
            return self._qsize()

    def empty(self, /) -> bool:
        with self.mutex:
            return self._qsize() <= 0

    def full(self, /) -> bool:
        with self.mutex:
            return 0 < self._maxsize <= self._size

    def sync_put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None:
        self.green_put(item, block, timeout, blocking=blocking)

    def green_put(
        self,
        /,
        item: _T,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> None:
        if blocking is DEFAULT:
            if block is DEFAULT:
                blocking = True
            else:
                blocking = block
        elif block is not DEFAULT:
            msg = "cannot specify both 'block' and 'blocking'"
            raise ValueError(msg)

        rescheduled = False
        notified = False
        deadline = None

        if timeout is not None:
            if isinstance(timeout, int):
                try:
                    timeout = float(timeout)
                except OverflowError:
                    timeout = (-1 if timeout < 0 else +1) * inf

            if isnan(timeout):
                msg = "'timeout' must be a number (non-NaN)"
                raise ValueError(msg)

            if timeout < 0:
                msg = "'timeout' must be a non-negative number"
                raise ValueError(msg)

            if isinf(timeout):
                timeout = None

        if not blocking:
            timeout = 0

        with self.not_full:
            try:
                while True:
                    self._check_closing()
                    size = self._size
                    isize = self._isize(item)
                    assert isize >= 0

                    if isize != 1:
                        self.__one_put_one_item = False

                    if timeout:
                        while 0 < self._maxsize <= size + isize - 1:
                            if deadline is None:
                                deadline = green_clock() + timeout
                            else:
                                timeout = deadline - green_clock()

                                if timeout <= 0:
                                    raise QueueFull

                            notified = self.not_full.wait(timeout)

                            self._check_closing()
                            size = self._size

                            rescheduled = True
                    elif timeout is None:
                        while 0 < self._maxsize <= size + isize - 1:
                            notified = self.not_full.wait()

                            self._check_closing()
                            size = self._size

                            rescheduled = True
                    else:
                        if 0 < self._maxsize <= size + isize - 1:
                            raise QueueFull

                        if not blocking:
                            break

                    if not rescheduled and green_checkpoint_enabled():
                        state = self.mutex._release_save()

                        try:
                            green_checkpoint()
                        finally:
                            self.mutex._acquire_restore(state)

                        rescheduled = True
                    else:
                        break

                length = self._qsize()

                self._put(item)

                new_length = self._qsize()
                new_tasks = new_length - length
                assert new_tasks >= 0

                if new_tasks != 1:
                    self.__one_put_one_item = False

                if new_tasks:
                    if 0 < new_length:
                        if self.__one_get_one_item:
                            if length < 0:
                                self.not_empty.notify(new_length)
                            else:
                                self.not_empty.notify(new_tasks)
                        else:
                            self.not_empty.notify()

                    if (tasks := self._unfinished_tasks) >= 0:
                        self._unfinished_tasks = tasks + new_tasks

                    self._size += isize
            finally:
                if notified and not self.__one_put_one_item:
                    self.not_full.notify()

    sync_put = copies(green_put, sync_put)

    async def async_put(self, /, item: _T) -> None:
        rescheduled = False
        notified = False

        with self.not_full:
            try:
                while True:
                    self._check_closing()
                    size = self._size
                    isize = self._isize(item)
                    assert isize >= 0

                    if isize != 1:
                        self.__one_put_one_item = False

                    while 0 < self._maxsize <= size + isize - 1:
                        notified = await self.not_full

                        self._check_closing()
                        size = self._size

                        rescheduled = True

                    if not rescheduled and async_checkpoint_enabled():
                        state = self.mutex._release_save()

                        try:
                            await async_checkpoint()
                        finally:
                            self.mutex._acquire_restore(state)

                        rescheduled = True
                    else:
                        break

                length = self._qsize()

                self._put(item)

                new_length = self._qsize()
                new_tasks = new_length - length
                assert new_tasks >= 0

                if new_tasks != 1:
                    self.__one_put_one_item = False

                if new_tasks:
                    if 0 < new_length:
                        if self.__one_get_one_item:
                            if length < 0:
                                self.not_empty.notify(new_length)
                            else:
                                self.not_empty.notify(new_tasks)
                        else:
                            self.not_empty.notify()

                    if (tasks := self._unfinished_tasks) >= 0:
                        self._unfinished_tasks = tasks + new_tasks

                    self._size += isize
            finally:
                if notified and not self.__one_put_one_item:
                    self.not_full.notify()

    def put_nowait(self, /, item: _T) -> None:
        with self.mutex:
            self._check_closing()
            size = self._size
            isize = self._isize(item)
            assert isize >= 0

            if isize != 1:
                self.__one_put_one_item = False

            if 0 < self._maxsize <= size + isize - 1:
                raise QueueFull

            length = self._qsize()

            self._put(item)

            new_length = self._qsize()
            new_tasks = new_length - length
            assert new_tasks >= 0

            if new_tasks != 1:
                self.__one_put_one_item = False

            if new_tasks:
                if 0 < new_length:
                    if self.__one_get_one_item:
                        if length < 0:
                            self.not_empty.notify(new_length)
                        else:
                            self.not_empty.notify(new_tasks)
                    else:
                        self.not_empty.notify()

                if (tasks := self._unfinished_tasks) >= 0:
                    self._unfinished_tasks = tasks + new_tasks

                self._size += isize

    def sync_get(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        return self.green_get(block, timeout, blocking=blocking)

    def green_get(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        if blocking is DEFAULT:
            if block is DEFAULT:
                blocking = True
            else:
                blocking = block
        elif block is not DEFAULT:
            msg = "cannot specify both 'block' and 'blocking'"
            raise ValueError(msg)

        rescheduled = False
        notified = False
        deadline = None

        if timeout is not None:
            if isinstance(timeout, int):
                try:
                    timeout = float(timeout)
                except OverflowError:
                    timeout = (-1 if timeout < 0 else +1) * inf

            if isnan(timeout):
                msg = "'timeout' must be a number (non-NaN)"
                raise ValueError(msg)

            if timeout < 0:
                msg = "'timeout' must be a non-negative number"
                raise ValueError(msg)

            if isinf(timeout):
                timeout = None

        if not blocking:
            timeout = 0

        with self.not_empty:
            try:
                while True:
                    length = self._qsize()

                    if timeout:
                        while length <= 0:
                            self._check_closing()

                            if deadline is None:
                                deadline = green_clock() + timeout
                            else:
                                timeout = deadline - green_clock()

                                if timeout <= 0:
                                    raise QueueEmpty

                            notified = self.not_empty.wait(timeout)

                            length = self._qsize()

                            rescheduled = True
                    elif timeout is None:
                        while length <= 0:
                            self._check_closing()

                            notified = self.not_empty.wait()

                            length = self._qsize()

                            rescheduled = True
                    else:
                        if length <= 0:
                            self._check_closing()

                            raise QueueEmpty

                        if not blocking:
                            break

                    if not rescheduled and green_checkpoint_enabled():
                        state = self.mutex._release_save()

                        try:
                            green_checkpoint()
                        finally:
                            self.mutex._acquire_restore(state)

                        rescheduled = True
                    else:
                        break

                item = self._get()

                new_tasks = length - self._qsize()
                assert new_tasks >= 0

                if new_tasks != 1:
                    self.__one_get_one_item = False

                if new_tasks:
                    size = self._size
                    isize = self._isize(item)
                    new_size = size - isize
                    assert new_size <= size

                    if 0 < self._maxsize and new_size < self._maxsize:
                        if self.__one_put_one_item:
                            if self._maxsize < size:
                                self.not_full.notify(self._maxsize - new_size)
                            else:
                                self.not_full.notify(isize)
                        else:
                            self.not_full.notify()

                    self._size = new_size

                return item
            finally:
                if notified and not self.__one_get_one_item:
                    self.not_empty.notify()

    sync_get = copies(green_get, sync_get)

    async def async_get(self, /) -> _T:
        rescheduled = False
        notified = False

        with self.not_empty:
            try:
                while True:
                    length = self._qsize()

                    while length <= 0:
                        self._check_closing()

                        notified = await self.not_empty

                        length = self._qsize()

                        rescheduled = True

                    if not rescheduled and async_checkpoint_enabled():
                        state = self.mutex._release_save()

                        try:
                            await async_checkpoint()
                        finally:
                            self.mutex._acquire_restore(state)

                        rescheduled = True
                    else:
                        break

                item = self._get()

                new_tasks = length - self._qsize()
                assert new_tasks >= 0

                if new_tasks != 1:
                    self.__one_get_one_item = False

                if new_tasks:
                    size = self._size
                    isize = self._isize(item)
                    new_size = size - isize
                    assert new_size <= size

                    if 0 < self._maxsize and new_size < self._maxsize:
                        if self.__one_put_one_item:
                            if self._maxsize < size:
                                self.not_full.notify(self._maxsize - new_size)
                            else:
                                self.not_full.notify(isize)
                        else:
                            self.not_full.notify()

                    self._size = new_size

                return item
            finally:
                if notified and not self.__one_get_one_item:
                    self.not_empty.notify()

    def get_nowait(self, /) -> _T:
        with self.mutex:
            length = self._qsize()

            if length <= 0:
                self._check_closing()

                raise QueueEmpty

            item = self._get()

            new_tasks = length - self._qsize()
            assert new_tasks >= 0

            if new_tasks != 1:
                self.__one_get_one_item = False

            if new_tasks:
                size = self._size
                isize = self._isize(item)
                new_size = size - isize
                assert new_size <= size

                if 0 < self._maxsize and new_size < self._maxsize:
                    if self.__one_put_one_item:
                        if self._maxsize < size:
                            self.not_full.notify(self._maxsize - new_size)
                        else:
                            self.not_full.notify(isize)
                    else:
                        self.not_full.notify()

                self._size = new_size

            return item

    def sync_peek(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        return self.green_peek(block, timeout, blocking=blocking)

    def green_peek(
        self,
        /,
        block: bool | DefaultType = DEFAULT,
        timeout: float | None = None,
        *,
        blocking: bool | DefaultType = DEFAULT,
    ) -> _T:
        if blocking is DEFAULT:
            if block is DEFAULT:
                blocking = True
            else:
                blocking = block
        elif block is not DEFAULT:
            msg = "cannot specify both 'block' and 'blocking'"
            raise ValueError(msg)

        rescheduled = False
        notified = False
        deadline = None

        if timeout is not None:
            if isinstance(timeout, int):
                try:
                    timeout = float(timeout)
                except OverflowError:
                    timeout = (-1 if timeout < 0 else +1) * inf

            if isnan(timeout):
                msg = "'timeout' must be a number (non-NaN)"
                raise ValueError(msg)

            if timeout < 0:
                msg = "'timeout' must be a non-negative number"
                raise ValueError(msg)

            if isinf(timeout):
                timeout = None

        if not blocking:
            timeout = 0

        with self.not_empty:
            try:
                while True:
                    self._check_peekable()
                    length = self._qsize()

                    if timeout:
                        while length <= 0:
                            self._check_closing()

                            if deadline is None:
                                deadline = green_clock() + timeout
                            else:
                                timeout = deadline - green_clock()

                                if timeout <= 0:
                                    raise QueueEmpty

                            notified = self.not_empty.wait(timeout)

                            self._check_peekable()
                            length = self._qsize()

                            rescheduled = True
                    elif timeout is None:
                        while length <= 0:
                            self._check_closing()

                            notified = self.not_empty.wait()

                            self._check_peekable()
                            length = self._qsize()

                            rescheduled = True
                    else:
                        if length <= 0:
                            self._check_closing()

                            raise QueueEmpty

                        if not blocking:
                            break

                    if not rescheduled and green_checkpoint_enabled():
                        state = self.mutex._release_save()

                        try:
                            green_checkpoint()
                        finally:
                            self.mutex._acquire_restore(state)

                        rescheduled = True
                    else:
                        break

                item = self._peek()
                assert self._qsize() == length

                return item
            finally:
                if notified:
                    self.not_empty.notify()

    sync_peek = copies(green_peek, sync_peek)

    async def async_peek(self, /) -> _T:
        rescheduled = False
        notified = False

        with self.not_empty:
            try:
                while True:
                    self._check_peekable()
                    length = self._qsize()

                    while length <= 0:
                        self._check_closing()

                        notified = await self.not_empty

                        self._check_peekable()
                        length = self._qsize()

                        rescheduled = True

                    if not rescheduled and async_checkpoint_enabled():
                        state = self.mutex._release_save()

                        try:
                            await async_checkpoint()
                        finally:
                            self.mutex._acquire_restore(state)

                        rescheduled = True
                    else:
                        break

                item = self._peek()
                assert self._qsize() == length

                return item
            finally:
                if notified:
                    self.not_empty.notify()

    def peek_nowait(self, /) -> _T:
        with self.mutex:
            self._check_peekable()
            length = self._qsize()

            if length <= 0:
                self._check_closing()

                raise QueueEmpty

            item = self._peek()
            assert self._qsize() == length

            return item

    def sync_join(self, /) -> None:
        self.green_join()

    def green_join(self, /) -> None:
        rescheduled = False

        with self.all_tasks_done:
            while self._unfinished_tasks:
                self.all_tasks_done.wait()

                rescheduled = True

        if not rescheduled:
            green_checkpoint()

    sync_join = copies(green_join, sync_join)

    async def async_join(self, /) -> None:
        rescheduled = False

        with self.all_tasks_done:
            while self._unfinished_tasks:
                await self.all_tasks_done

                rescheduled = True

        if not rescheduled:
            await async_checkpoint()

    def task_done(self, /) -> None:
        with self.mutex:
            tasks = self._unfinished_tasks - 1

            if tasks <= 0:
                if tasks < -1:
                    return

                if tasks < 0:
                    msg = "task_done() called too many times"
                    raise ValueError(msg)

                self.all_tasks_done.notify_all()

            self._unfinished_tasks = tasks

    def shutdown(self, /, immediate: bool = False) -> None:
        with self.mutex:
            self._is_shutdown = True

            if immediate:
                length = self._qsize()
                size = self._size

                if self._clearable():
                    self._clear()

                    new_size = self._size
                    assert new_size <= 0 or new_size == size
                    new_length = self._qsize()
                    assert new_length <= 0
                    new_tasks = length - new_length
                    assert new_tasks >= 0

                    if new_tasks:
                        new_size = min(new_size, 0)
                else:
                    new_size = size
                    new_tasks = 0

                    while length > 0:
                        item = self._get()

                        isize = self._isize(item)
                        assert isize >= 0
                        new_size -= isize
                        new_length = self._qsize()
                        assert new_length <= length
                        new_tasks += length - new_length

                        length = new_length

                    if new_tasks:
                        assert new_size <= 0

                if new_tasks:
                    if (tasks := self._unfinished_tasks) > 0:
                        self._unfinished_tasks = max(0, tasks - new_tasks)

                    self._size = new_size

                self.all_tasks_done.notify_all()

            self.not_empty.notify_all()
            self.not_full.notify_all()

    def close(self, /) -> None:
        """
        This method is provided for compatibility with the Janus queues. Use
        :meth:`queue.shutdown(immediate=True) <BaseQueue.shutdown>` as a direct
        substitute.
        """

        self.shutdown(immediate=True)

    async def wait_closed(self, /) -> None:
        """
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

    async def aclose(self, /) -> None:
        """
        This method is provided for compatibility with the Janus queues. Use
        :meth:`queue.shutdown(immediate=True) <BaseQueue.shutdown>` as a direct
        substitute.
        """

        self.close()
        await self.wait_closed()

    def clear(self, /) -> None:
        with self.mutex:
            self._check_clearable()
            length = self._qsize()
            size = self._size

            self._clear()

            new_size = self._size
            assert new_size <= 0 or new_size == size
            new_length = self._qsize()
            assert new_length <= 0
            new_tasks = length - new_length
            assert new_tasks >= 0

            if new_tasks:
                new_size = min(new_size, 0)

                if 0 < self._maxsize and new_size < self._maxsize:
                    if self.__one_put_one_item:
                        if self._maxsize < size:
                            self.not_full.notify(self._maxsize - new_size)
                        else:
                            self.not_full.notify(size - new_size)
                    else:
                        self.not_full.notify()

                if (tasks := self._unfinished_tasks) > 0:
                    self._unfinished_tasks = max(0, tasks - new_tasks)

                    if not self._unfinished_tasks:
                        self.all_tasks_done.notify_all()

                self._size = new_size

    def _check_closing(self, /) -> None:
        if self._is_shutdown:
            raise QueueShutDown

    def _check_peekable(self, /) -> None:
        if not self._peekable():
            msg = "peeking not supported"
            raise UnsupportedOperation(msg)

    def _check_clearable(self, /) -> None:
        if not self._clearable():
            msg = "clearing not supported"
            raise UnsupportedOperation(msg)

    def __isize(self, /, item: _T) -> int:
        return 1

    # Override these methods to implement other queue organizations
    # (e.g. stack or priority queue).
    # These will only be called with appropriate locks held

    def _init(self, /, maxsize: int) -> None:
        self.__data = deque()

    def _qsize(self, /) -> int:
        return len(self.__data)

    def _put(self, /, item: _T) -> None:
        self.__data.append(item)

    def _get(self, /) -> _T:
        return self.__data.popleft()

    def _peekable(self, /) -> bool:
        return True

    def _peek(self, /) -> _T:
        return self.__data[0]

    def _clearable(self, /) -> bool:
        return True

    def _clear(self, /) -> None:
        self.__data.clear()

    @property
    def green_proxy(self, /) -> GreenQueueProxy[_T]:
        return GreenQueueProxy(self)

    @property
    def async_proxy(self, /) -> AsyncQueueProxy[_T]:
        return AsyncQueueProxy(self)

    @property
    def sync_q(self, /) -> SyncQueueProxy[_T]:
        return SyncQueueProxy(self)

    @property
    def async_q(self, /) -> AsyncQueueProxy[_T]:
        return AsyncQueueProxy(self)

    @property
    def putting(self, /) -> int:
        """
        The current number of threads/tasks waiting to put.

        It represents the length of the wait queue and thus changes
        immediately.
        """

        return self.not_full.waiting

    @property
    def getting(self, /) -> int:
        """
        The current number of threads/tasks waiting to get/peek.

        It represents the length of the wait queue and thus changes
        immediately.
        """

        return self.not_empty.waiting

    @property
    def waiting(self, /) -> int:
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
    def unfinished_tasks(self, /) -> int:
        return self._unfinished_tasks

    @property
    def is_shutdown(self, /) -> bool:
        return self._is_shutdown

    @property
    def closed(self, /) -> bool:
        return self._is_shutdown

    @property
    def maxsize(self, /) -> int:
        return self._maxsize

    @maxsize.setter
    def maxsize(self, value: int, /) -> None:
        with self.mutex:
            if 0 < self._maxsize:
                if value <= 0:
                    self.not_full.notify_all()
                elif self._maxsize < value:
                    if self.__one_put_one_item:
                        self.not_full.notify(value - self._maxsize)
                    else:
                        self.not_full.notify()

            self._maxsize = value

    @property
    def size(self, /) -> int:
        return self._size


class LifoQueue(Queue[_T]):
    """
    A variant of :class:`Queue` that retrieves most recently added entries
    first (:abbr:`LIFO (last-in, first-out)`).
    """

    __slots__ = ("__data",)  # noqa: PLW0244

    __data: list[_T]

    @override
    def _init(self, /, maxsize: int) -> None:
        self.__data = []

    @override
    def _qsize(self, /) -> int:
        return len(self.__data)

    @override
    def _put(self, /, item: _T) -> None:
        self.__data.append(item)

    @override
    def _get(self, /) -> _T:
        return self.__data.pop()

    @override
    def _peekable(self, /) -> bool:
        return True

    @override
    def _peek(self, /) -> _T:
        return self.__data[-1]

    @override
    def _clearable(self, /) -> bool:
        return True

    @override
    def _clear(self, /) -> None:
        self.__data.clear()


class PriorityQueue(Queue[_RichComparableT]):
    """
    A variant of :class:`Queue` that retrieves entries in priority order
    (lowest first).
    """

    __slots__ = ("__data",)  # noqa: PLW0244

    __data: list[_RichComparableT]

    @override
    def _init(self, /, maxsize: int) -> None:
        self.__data = []

    @override
    def _qsize(self, /) -> int:
        return len(self.__data)

    @override
    def _put(self, /, item: _RichComparableT) -> None:
        heappush(self.__data, item)

    @override
    def _get(self, /) -> _RichComparableT:
        return heappop(self.__data)

    @override
    def _peekable(self, /) -> bool:
        return True

    @override
    def _peek(self, /) -> _RichComparableT:
        return self.__data[0]

    @override
    def _clearable(self, /) -> bool:
        return True

    @override
    def _clear(self, /) -> None:
        self.__data.clear()
