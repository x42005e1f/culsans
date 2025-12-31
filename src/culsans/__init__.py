#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

"""
Thread-safe async-aware queue for Python

Mixed sync-async queue, supposed to be used for communicating between classic
synchronous (threaded) code and asynchronous one, between two asynchronous
codes in different threads, and for any other combination that you want.

If you want to know more, visit https://culsans.readthedocs.io.
"""

from __future__ import annotations

__author__: str = "Ilya Egorov <0x42005e1f@gmail.com>"
__version__: str  # dynamic
__version_tuple__: tuple[int | str, ...]  # dynamic

from ._groupers import (
    Grouper as Grouper,
    RWLock as RWLock,
)
from ._queues import (
    AsyncQueue as AsyncQueue,
    AsyncQueueEmpty as AsyncQueueEmpty,
    AsyncQueueFull as AsyncQueueFull,
    AsyncQueueProxy as AsyncQueueProxy,
    AsyncQueueShutDown as AsyncQueueShutDown,
    BaseQueue as BaseQueue,
    BaseQueueProxy as BaseQueueProxy,
    GreenQueue as GreenQueue,
    GreenQueueProxy as GreenQueueProxy,
    LifoQueue as LifoQueue,
    MixedQueue as MixedQueue,
    PriorityQueue as PriorityQueue,
    Queue as Queue,
    QueueEmpty as QueueEmpty,
    QueueFull as QueueFull,
    QueueShutDown as QueueShutDown,
    SyncQueue as SyncQueue,
    SyncQueueEmpty as SyncQueueEmpty,
    SyncQueueFull as SyncQueueFull,
    SyncQueueProxy as SyncQueueProxy,
    SyncQueueShutDown as SyncQueueShutDown,
    UnsupportedOperation as UnsupportedOperation,
)

# prepare for external use
from aiologic import meta  # isort: skip

if not __import__("os").getenv("SPHINX_AUTODOC_RELOAD_MODULES", ""):
    meta.export(globals())  # aiologic<0.17.0
meta.export_dynamic(globals(), "__version__", "._version.version")
meta.export_dynamic(globals(), "__version_tuple__", "._version.version_tuple")

del meta
