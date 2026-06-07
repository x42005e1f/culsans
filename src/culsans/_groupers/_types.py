#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

from collections import OrderedDict
from types import MappingProxyType
from typing import TYPE_CHECKING

from aiologic.lowlevel import (
    async_checkpoint,
    async_checkpoint_enabled,
    create_async_event,
    create_green_event,
    create_thread_rlock,
    current_async_task_ident,
    current_green_task_ident,
    green_checkpoint,
    green_checkpoint_enabled,
)
from aiologic.meta import DEFAULT, MISSING

if TYPE_CHECKING:
    import sys

    from collections.abc import Hashable
    from types import TracebackType

    from aiologic.lowlevel import Event, ThreadRLock
    from aiologic.meta import DefaultType, MissingType

    if sys.version_info >= (3, 9):  # PEP 585
        from collections.abc import Callable
    else:
        from typing import Callable

    if sys.version_info >= (3, 11):  # a caching bug fix
        from typing import Literal
    else:  # typing-extensions>=4.6.0
        from typing_extensions import Literal

    if sys.version_info >= (3, 11):  # PEP 673
        from typing import Self
    else:  # typing-extensions>=4.0.0
        from typing_extensions import Self


class Grouper:
    """
    A reentrant higher-level primitive that synchronizes tasks by groups.

    Can be used via the ``async with``/``with`` statements.
    """

    __slots__ = (
        "__weakref__",
        "_default_group",
        "_default_group_factory",
        "_default_group_mode",
        "_groups",
        "_groups_proxies",
        "_groups_proxy",
        "_mutex",
        "_owners",
        "_owners_proxies",
        "_owners_proxy",
        "_predicate",
        "_waiters",
        "_waiters_counter",
        "_wrapped",
    )

    _predicate: Callable[[Grouper, Hashable, tuple[str, int] | None], bool]

    _default_group: Hashable | MissingType
    _default_group_factory: Callable[[], Hashable] | MissingType
    _default_group_mode: Literal["exclusive", "shared"]

    _groups: dict[Hashable, dict[tuple[str, int], int]]
    _groups_proxies: dict[Hashable, MappingProxyType[tuple[str, int], int]]
    _groups_proxy: MappingProxyType[
        Hashable, MappingProxyType[tuple[str, int], int]
    ]

    _owners: dict[tuple[str, int], dict[Hashable, int]]
    _owners_proxies: dict[tuple[str, int], MappingProxyType[Hashable, int]]
    _owners_proxy: MappingProxyType[
        tuple[str, int], MappingProxyType[Hashable, int]
    ]

    _mutex: ThreadRLock

    _waiters: OrderedDict[
        tuple[Hashable, Literal["exclusive", "shared"]],
        dict[tuple[str, int], tuple[Event, int]],
    ]
    _waiters_counter: list[None]

    _wrapped: Grouper | None

    def __init__(
        self,
        wrapped_or_predicate: (
            Grouper
            | Callable[[Grouper, Hashable, tuple[str, int] | None], bool]
            | DefaultType
        ) = DEFAULT,
        /,
        *,
        default_group: Hashable | MissingType = MISSING,
        default_group_factory: Callable[[], Hashable] | MissingType = MISSING,
        default_group_mode: Literal["exclusive", "shared"] = "shared",
    ) -> None:
        """
        Create a grouper object with the given parameters.

        Args:
          wrapped_or_predicate:
            If another grouper object is passed, it will create a proxy/wrapper
            that uses the same underlying structures but with different default
            parameters (see below). Otherwise, the passed object is treated as
            a predicate (see the :attr:`predicate` property).
          default_group:
            See the :attr:`default_group` property.
          default_group_factory:
            See the :attr:`default_group_factory` property.
          default_group_mode:
            If ``"exclusive"`` is passed, only one task from the group will be
            woken up on release. Otherwise, if ``"shared"`` is passed, all
            tasks from the group will be woken up. It must be consistent with
            the predicate.

        Example:
          >>> import threading
          >>> thread_rlock = Grouper(default_group_factory=threading.get_ident)
          >>> async with thread_rlock:
          ...     ...  # exclusive for threads; shared for the thread's tasks
        """

        if (
            default_group is not MISSING
            and default_group_factory is not MISSING
        ):
            msg = (
                "cannot specify both 'default_group'"
                " and 'default_group_factory'"
            )
            raise ValueError(msg)

        self._default_group = default_group
        self._default_group_factory = default_group_factory
        self._default_group_mode = default_group_mode

        if isinstance(wrapped_or_predicate, Grouper):
            wrapped = wrapped_or_predicate

            if not hasattr(self, "_predicate"):
                self._predicate = wrapped._predicate

            self._owners = wrapped._owners
            self._owners_proxies = wrapped._owners_proxies
            self._owners_proxy = wrapped._owners_proxy

            self._groups = wrapped._groups
            self._groups_proxies = wrapped._groups_proxies
            self._groups_proxy = wrapped._groups_proxy

            self._mutex = wrapped._mutex

            self._waiters = wrapped._waiters
            self._waiters_counter = wrapped._waiters_counter

            self._wrapped = wrapped
        else:
            predicate = wrapped_or_predicate

            if not hasattr(self, "_predicate"):
                if predicate is DEFAULT:
                    self._predicate = self.__predicate
                else:
                    self._predicate = predicate

            self._groups = {}
            self._groups_proxies = {}
            self._groups_proxy = MappingProxyType(self._groups_proxies)

            self._owners = {}
            self._owners_proxies = {}
            self._owners_proxy = MappingProxyType(self._owners_proxies)

            self._mutex = create_thread_rlock()

            self._waiters = OrderedDict()
            self._waiters_counter = []

            self._wrapped = None

    def __bool__(self, /) -> bool:
        """
        Return :data:`True` if the grouper is used by any task, :data:`False`
        otherwise.

        Used by the standard :ref:`truth testing procedure <truth>`.
        """

        return bool(self._owners)

    async def __aenter__(self, /) -> Self:
        await self.async_acquire()

        return self

    def __enter__(self, /) -> Self:
        self.green_acquire()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self.async_release()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self.green_release()

    async def async_acquire(
        self,
        /,
        count: int = 1,
        *,
        blocking: bool = True,
    ) -> bool:
        """
        Acquire the grouper by the current async task on behalf of the default
        group.

        If no default group was passed to the constructor, the task identifier
        is used instead.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
          blocking:
            Unless set to :data:`False`, the method will block if necessary
            until it succeeds in acquiring the grouper. Otherwise, it will
            return :data:`False` if it fails to do so immediately.
        """

        if self._default_group_factory is not MISSING:
            group = self._default_group_factory()
        elif self._default_group is not MISSING:
            group = self._default_group
        else:
            group = current_async_task_ident()

        return await self.async_acquire_on_behalf_of(
            group,
            count,
            blocking=blocking,
        )

    def green_acquire(
        self,
        /,
        count: int = 1,
        *,
        blocking: bool = True,
        timeout: float | None = None,
    ) -> bool:
        """
        Acquire the grouper by the current green task on behalf of the default
        group.

        If no default group was passed to the constructor, the task identifier
        is used instead.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
          blocking:
            Unless set to :data:`False`, the method will block if necessary
            until it succeeds in acquiring the grouper. Otherwise,
            ``timeout=0`` is implied.
          timeout:
            If set to a non-negative number, the method will block at most
            *timeout* seconds and return :data:`False` if it fails to acquire
            the grouper within that time.
        """

        if self._default_group_factory is not MISSING:
            group = self._default_group_factory()
        elif self._default_group is not MISSING:
            group = self._default_group
        else:
            group = current_green_task_ident()

        return self.green_acquire_on_behalf_of(
            group,
            count,
            blocking=blocking,
            timeout=timeout,
        )

    def async_release(self, /, count: int = 1) -> None:
        """
        Release the grouper by the current async task on behalf of the default
        group.

        If no default group was passed to the constructor, the task identifier
        is used instead.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
        """

        if self._default_group_factory is not MISSING:
            group = self._default_group_factory()
        elif self._default_group is not MISSING:
            group = self._default_group
        else:
            group = current_async_task_ident()

        self.async_release_on_behalf_of(group, count)

    def green_release(self, /, count: int = 1) -> None:
        """
        Release the grouper by the current green task on behalf of the default
        group.

        If no default group was passed to the constructor, the task identifier
        is used instead.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
        """

        if self._default_group_factory is not MISSING:
            group = self._default_group_factory()
        elif self._default_group is not MISSING:
            group = self._default_group
        else:
            group = current_green_task_ident()

        self.green_release_on_behalf_of(group, count)

    async def async_acquire_on_behalf_of(
        self,
        /,
        group: Hashable,
        count: int = 1,
        *,
        blocking: bool = True,
    ) -> bool:
        """
        Acquire the grouper by the current async task on behalf of the *group*.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
          blocking:
            Unless set to :data:`False`, the method will block if necessary
            until it succeeds in acquiring the grouper. Otherwise, it will
            return :data:`False` if it fails to do so immediately.
        """

        group_mode = self._default_group_mode

        ident = current_async_task_ident()

        if ident in self._owners and group in self._owners[ident]:
            if blocking:
                await async_checkpoint()

            self._owners[ident][group] += count
            self._groups[group][ident] += count

            return True

        with self._mutex:
            if self._predicate(self, group, ident):
                success = True

                if blocking and async_checkpoint_enabled():
                    state = self.mutex._release_save()

                    try:
                        await async_checkpoint()
                    finally:
                        self.mutex._acquire_restore(state)

                    success = self._predicate(self, group, ident)

                if success:
                    if ident in self._owners:
                        self._owners[ident][group] = count
                    else:
                        self._owners[ident] = groups = {group: count}
                        self._owners_proxies[ident] = MappingProxyType(groups)

                    if group in self._groups:
                        self._groups[group][ident] = count
                    else:
                        self._groups[group] = tasks = {ident: count}
                        self._groups_proxies[group] = MappingProxyType(tasks)

                    return True

            if not blocking:
                return False

            key = (group, group_mode)
            events = self._waiters.setdefault(key, {})
            events[ident] = (
                event := create_async_event(),
                count,
            )

            self._waiters_counter.append(None)

            state = self.mutex._release_save()

            success = False

            try:
                success = await event
            finally:
                self.mutex._acquire_restore(state)

                if not success:
                    if event.cancelled():
                        self._waiters_counter.pop()

                        del events[ident]

                        if not events and self._waiters.get(key) is events:
                            del self._waiters[key]
                    else:
                        del self._owners[ident][group]
                        del self._groups[group][ident]

                        if not self._owners[ident]:
                            del self._owners_proxies[ident]
                            del self._owners[ident]

                        if not self._groups[group]:
                            del self._groups_proxies[group]
                            del self._groups[group]

                            self._release()

            return success

    def green_acquire_on_behalf_of(
        self,
        /,
        group: Hashable,
        count: int = 1,
        *,
        blocking: bool = True,
        timeout: float | None = None,
    ) -> bool:
        """
        Acquire the grouper by the current green task on behalf of the *group*.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
          blocking:
            Unless set to :data:`False`, the method will block if necessary
            until it succeeds in acquiring the grouper. Otherwise,
            ``timeout=0`` is implied.
          timeout:
            If set to a non-negative number, the method will block at most
            *timeout* seconds and return :data:`False` if it fails to acquire
            the grouper within that time.
        """

        group_mode = self._default_group_mode

        ident = current_green_task_ident()

        if ident in self._owners and group in self._owners[ident]:
            if blocking:
                green_checkpoint()

            self._owners[ident][group] += count
            self._groups[group][ident] += count

            return True

        with self._mutex:
            if self._predicate(self, group, ident):
                success = True

                if blocking and green_checkpoint_enabled():
                    state = self.mutex._release_save()

                    try:
                        green_checkpoint()
                    finally:
                        self.mutex._acquire_restore(state)

                    success = self._predicate(self, group, ident)

                if success:
                    if ident in self._owners:
                        self._owners[ident][group] = count
                    else:
                        self._owners[ident] = groups = {group: count}
                        self._owners_proxies[ident] = MappingProxyType(groups)

                    if group in self._groups:
                        self._groups[group][ident] = count
                    else:
                        self._groups[group] = tasks = {ident: count}
                        self._groups_proxies[group] = MappingProxyType(tasks)

                    return True

            if not blocking:
                return False

            key = (group, group_mode)
            events = self._waiters.setdefault(key, {})
            events[ident] = (
                event := create_green_event(),
                count,
            )

            self._waiters_counter.append(None)

            state = self.mutex._release_save()

            success = False

            try:
                success = event.wait(timeout)
            finally:
                self.mutex._acquire_restore(state)

                if not success:
                    if event.cancelled():
                        self._waiters_counter.pop()

                        del events[ident]

                        if not events and self._waiters.get(key) is events:
                            del self._waiters[key]
                    else:
                        del self._owners[ident][group]
                        del self._groups[group][ident]

                        if not self._owners[ident]:
                            del self._owners_proxies[ident]
                            del self._owners[ident]

                        if not self._groups[group]:
                            del self._groups_proxies[group]
                            del self._groups[group]

                            self._release()

            return success

    def async_release_on_behalf_of(
        self,
        /,
        group: Hashable,
        count: int = 1,
    ) -> None:
        """
        Release the grouper by the current async task on behalf of the *group*.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
        """

        if count < 1:
            msg = "'count' must be >= 1"
            raise ValueError(msg)

        if not self._owners:
            msg = "release unlocked lock"
            raise RuntimeError(msg)

        ident = current_async_task_ident()

        try:
            current_count = self._owners[ident][group]
        except KeyError:
            msg = "the current task is not holding this lock"
            raise RuntimeError(msg) from None

        if count > current_count:
            msg = "lock released too many times"
            raise RuntimeError(msg)

        current_count -= count

        self._owners[ident][group] = current_count
        self._groups[group][ident] = current_count

        if not current_count:
            with self._mutex:
                del self._owners[ident][group]
                del self._groups[group][ident]

                if not self._owners[ident]:
                    del self._owners_proxies[ident]
                    del self._owners[ident]

                if not self._groups[group]:
                    del self._groups_proxies[group]
                    del self._groups[group]

                    self._release()

    def green_release_on_behalf_of(
        self,
        /,
        group: Hashable,
        count: int = 1,
    ) -> None:
        """
        Release the grouper by the current green task on behalf of the *group*.

        Args:
          count:
            The recursion level delta (equivalent to the same number of calls).
        """

        if count < 1:
            msg = "'count' must be >= 1"
            raise ValueError(msg)

        if not self._owners:
            msg = "release unlocked lock"
            raise RuntimeError(msg)

        ident = current_green_task_ident()

        try:
            current_count = self._owners[ident][group]
        except KeyError:
            msg = "the current task is not holding this lock"
            raise RuntimeError(msg) from None

        if count > current_count:
            msg = "lock released too many times"
            raise RuntimeError(msg)

        current_count -= count

        self._owners[ident][group] = current_count
        self._groups[group][ident] = current_count

        if not current_count:
            with self._mutex:
                del self._owners[ident][group]
                del self._groups[group][ident]

                if not self._owners[ident]:
                    del self._owners_proxies[ident]
                    del self._owners[ident]

                if not self._groups[group]:
                    del self._groups_proxies[group]
                    del self._groups[group]

                    self._release()

    def _release(self, /) -> None:
        while self._waiters:
            key, events = self._waiters.popitem(last=False)
            group, group_mode = key

            if not self._predicate(self, group, None):
                self._waiters[key] = events
                self._waiters.move_to_end(key, last=False)

                break

            if group_mode == "exclusive":
                tasks = {}
                to_skip = set()

                for ident, (event, count) in events.items():
                    to_skip.add(ident)

                    if event.set() and not self._waiters_counter.pop():
                        tasks[ident] = count

                        break

                events = {
                    ident: info
                    for ident, info in events.items()
                    if ident not in to_skip
                }

                if events:
                    self._waiters[key] = events
            elif group_mode == "shared":
                tasks = {
                    ident: count
                    for ident, (event, count) in events.items()
                    if event.set() and not self._waiters_counter.pop()
                }
            else:
                msg = "unknown group mode"
                raise RuntimeError(msg)

            if tasks:
                for ident, count in tasks.items():
                    if ident in self._owners:
                        self._owners[ident][group] = count
                    else:
                        self._owners[ident] = groups = {group: count}
                        self._owners_proxies[ident] = MappingProxyType(groups)

                if group in self._groups:
                    self._groups[group].update(tasks)
                else:
                    self._groups[group] = tasks
                    self._groups_proxies[group] = MappingProxyType(tasks)

                break

    def async_owned(self, /, group: Hashable | MissingType = MISSING) -> bool:
        """
        Return :data:`True` if the current async task owns the grouper,
        :data:`False` otherwise.

        Args:
          group:
            If specified, then only on behalf of the *group*.
        """

        ident = current_async_task_ident()

        if group is MISSING:
            return ident in self._owners

        return ident in self._owners and group in self._owners[ident]

    def green_owned(self, /, group: Hashable | MissingType = MISSING) -> bool:
        """
        Return :data:`True` if the current green task owns the grouper,
        :data:`False` otherwise.

        Args:
          group:
            If specified, then only on behalf of the *group*.
        """

        ident = current_green_task_ident()

        if group is MISSING:
            return ident in self._owners

        return ident in self._owners and group in self._owners[ident]

    def async_count(self, /, group: Hashable | MissingType = MISSING) -> int:
        """
        Return the recursion level of the current async task.

        Args:
          group:
            If specified, then only for the *group*. Otherwise, the sum across
            all groups to which the task belongs.
        """

        ident = current_async_task_ident()

        if ident in self._owners:
            if group is MISSING:
                return sum(self._owners[ident].values())

            return self._owners[ident].get(group, 0)

        return 0

    def green_count(self, /, group: Hashable | MissingType = MISSING) -> int:
        """
        Return the recursion level of the current green task.

        Args:
          group:
            If specified, then only for the *group*. Otherwise, the sum across
            all groups to which the task belongs.
        """

        ident = current_green_task_ident()

        if ident in self._owners:
            if group is MISSING:
                return sum(self._owners[ident].values())

            return self._owners[ident].get(group, 0)

        return 0

    def locked(self, /) -> bool:
        """
        Return :data:`True` if the grouper is used by any task, :data:`False`
        otherwise.
        """

        return bool(self._owners)

    @staticmethod
    def __predicate(  # phase-fair
        grouper: Grouper,
        group: Hashable,
        ident: tuple[str, int] | None,
    ) -> bool:
        return not grouper._groups or (
            group in grouper._groups and not grouper._waiters_counter
        )

    @property
    def predicate(
        self,
        /,
    ) -> Callable[[Grouper, Hashable, tuple[str, int] | None], bool]:
        """
        A callable object that determines whether a given group (or a task in a
        given group) can acquire the grouper at a specific point in time.

        On acquire, it is called for the current task if it is not yet a member
        of the desired group (otherwise, access is reentrant and the call does
        not occur). It is called even when the current task is a member of some
        other group (but not the desired one). The grouper, the group, and the
        task identifier are passed.

        On release, it is called for the next group in the wait queue (if any)
        when the last task exits the current group. The grouper, the group, and
        :data:`None` (instead of the task identifier) are passed.

        Called only when the underlying lock is acquired, and must return
        :data:`True` if access is granted, :data:`False` otherwise. For
        acquire, this determines whether the task must acquire the grouper
        immediately or join the wait queue as part of the desired group. For
        release, this determines whether tasks from the next group in the wait
        queue must wake up (according to the chosen mode) or remain waiting.

        If no predicate was passed to the constructor, then the default
        predicate is used, which operates according to the phase-fair policy
        for reading: the grouper can be acquired on behalf of the desired group
        if there are no owners, or if the desired group is already the owner
        and there are no other waiting groups. This can be used, for example,
        to synchronize asynchronous tasks at the thread level (group = thread
        identifier).
        """

        return self._predicate

    @property
    def default_group(self, /) -> Hashable | MissingType:
        """
        The default group used by the acquire/release methods.
        """

        return self._default_group

    @property
    def default_group_factory(self, /) -> Callable[[], Hashable] | MissingType:
        """
        The default group factory used by the acquire/release methods.
        """

        return self._default_group_factory

    @property
    def groups(
        self,
        /,
    ) -> MappingProxyType[Hashable, MappingProxyType[tuple[str, int], int]]:
        """
        The read-only proxy of the dictionary that maps groups to their
        respective information regarding which tasks the group consists of and
        their recursion level in it. Contains only those groups that own the
        grouper. Updated automatically when the current state changes.
        """

        return self._groups_proxy

    @property
    def owners(
        self,
        /,
    ) -> MappingProxyType[tuple[str, int], MappingProxyType[Hashable, int]]:
        """
        The read-only proxy of the dictionary that maps tasks' identifiers to
        their respective information regarding which groups the task belongs to
        and its recursion level in each group. Contains identifiers only of
        those tasks that own the grouper. Updated automatically when the
        current state changes.
        """

        return self._owners_proxy

    @property
    def mutex(self, /) -> ThreadRLock:
        """
        The underlying lock.
        """

        return self._mutex

    @property
    def waiting(self, /) -> int:
        """
        The current number of tasks waiting to own.
        """

        return len(self._waiters_counter)

    @property
    def wrapped(self, /) -> Grouper | None:
        """
        The parent of this proxy/wrapper, if any.
        """

        return self._wrapped


class RWLock(Grouper):
    """
    A readers-writer lock that is:

    * phase-fair (read `the paper <https://www.cs.unc.edu/~anderson/papers/
      ecrts09b.pdf>`__)
    * reentrant (like :class:`threading.RLock`)

    See the :attr:`reading` and :attr:`writing` properties.
    """

    __slots__ = (
        "_reading",
        "_writing",
    )

    def __init__(self, /) -> None:
        super().__init__(self.__predicate, default_group=None)

        self._reading = Grouper(
            self,
            default_group="reading",
            default_group_mode="shared",
        )
        self._writing = Grouper(
            self,
            default_group="writing",
            default_group_mode="exclusive",
        )

    @staticmethod
    def __predicate(
        grouper: Grouper,
        group: Hashable,
        ident: tuple[str, int] | None,
    ) -> bool:
        # direct access
        if group is None:
            msg = (
                "cannot acquire without a group;"
                " use the 'reading' or 'writing' property instead"
            )
            raise RuntimeError(msg)

        # first access
        if not grouper.groups:
            return True

        # inner reading on writing
        if group == "reading" and ident in grouper.owners:
            return True

        # inner writing on reading
        if group == "writing" and ident in grouper.owners:
            msg = "cannot upgrade from reading to writing"
            raise RuntimeError(msg)

        # reading without writers
        return (
            group == "reading"
            and group in grouper.groups
            and not grouper.waiting
        )

    @property
    def reading(self, /) -> Grouper:
        """
        The proxy/wrapper for reading.

        Example:
          >>> lock = RWLock()
          >>> async with lock.reading:
          ...     ...  # read
          ...     async with lock.reading:
          ...         ...  # nested read
          ...     ...  # read

        Example:
          >>> lock = RWLock()
          >>> with lock.reading:
          ...     ...  # read
          ...     with lock.reading:
          ...         ...  # nested read
          ...     ...  # read
        """

        return self._reading

    @property
    def writing(self, /) -> Grouper:
        """
        The proxy/wrapper for writing.

        Example:
          >>> lock = RWLock()
          >>> async with lock.writing:
          ...     ...  # write
          ...     async with lock.writing:
          ...         ...  # nested write
          ...     async with lock.reading:
          ...         ...  # nested read
          ...     ...  # write

        Example:
          >>> lock = RWLock()
          >>> with lock.writing:
          ...     ...  # write
          ...     with lock.writing:
          ...         ...  # nested write
          ...     with lock.reading:
          ...         ...  # nested read
          ...     ...  # write
        """

        return self._writing
