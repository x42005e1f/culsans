#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

import sys

from asyncio import QueueEmpty as AsyncEmpty, QueueFull as AsyncFull
from queue import Empty as SyncEmpty, Full as SyncFull

if sys.version_info >= (3, 13):
    from asyncio import QueueShutDown as AsyncShutDown
    from queue import ShutDown as SyncShutDown

    AsyncQueueShutDown = AsyncShutDown
    SyncQueueShutDown = SyncShutDown

    class QueueShutDown(SyncQueueShutDown, AsyncQueueShutDown):
        """Raised when put/get with shut-down queue."""

else:

    class QueueShutDown(Exception):
        """Raised when put/get with shut-down queue."""

    SyncQueueShutDown = QueueShutDown
    AsyncQueueShutDown = QueueShutDown

AsyncQueueEmpty = AsyncEmpty
SyncQueueEmpty = SyncEmpty

AsyncQueueFull = AsyncFull
SyncQueueFull = SyncFull


class QueueFull(SyncQueueFull, AsyncQueueFull):
    """Raised when non-blocking put with full queue."""


class QueueEmpty(SyncQueueEmpty, AsyncQueueEmpty):
    """Raised when non-blocking get with empty queue."""


class UnsupportedOperation(ValueError):
    """Raised when peek with non-peekable queue."""
