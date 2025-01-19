#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from ._exceptions import (
    AsyncQueueEmpty as AsyncQueueEmpty,
    AsyncQueueFull as AsyncQueueFull,
    AsyncQueueShutDown as AsyncQueueShutDown,
    QueueEmpty as QueueEmpty,
    QueueFull as QueueFull,
    QueueShutDown as QueueShutDown,
    SyncQueueEmpty as SyncQueueEmpty,
    SyncQueueFull as SyncQueueFull,
    SyncQueueShutDown as SyncQueueShutDown,
    UnsupportedOperation as UnsupportedOperation,
)
from ._protocols import (
    AsyncQueue as AsyncQueue,
    BaseQueue as BaseQueue,
    MixedQueue as MixedQueue,
    SyncQueue as SyncQueue,
)
from ._proxies import (
    AsyncQueueProxy as AsyncQueueProxy,
    SyncQueueProxy as SyncQueueProxy,
)
from ._queues import (
    LifoQueue as LifoQueue,
    PriorityQueue as PriorityQueue,
    Queue as Queue,
)

# modify __module__ for shorter repr()
for __value in list(globals().values()):
    if getattr(__value, "__module__", "").startswith(f"{__name__}."):
        try:
            __value.__module__ = __name__
        except AttributeError:
            pass

    del __value
