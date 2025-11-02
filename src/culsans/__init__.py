#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

"""Thread-safe async-aware queue for Python"""

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

# update .__module__ attributes for shorter representation
__import__(f"{__name__}._utils", fromlist=["_export"])._export(globals())
