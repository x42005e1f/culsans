#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

__all__ = (
    "AsyncQueueEmpty",
    "AsyncQueueFull",
    "AsyncQueueShutDown",
    "QueueEmpty",
    "QueueFull",
    "QueueShutDown",
    "SyncQueueEmpty",
    "SyncQueueFull",
    "SyncQueueShutDown",
    "UnsupportedOperation",
)

import sys

from asyncio import QueueEmpty as AsyncQueueEmpty, QueueFull as AsyncQueueFull
from queue import Empty as SyncQueueEmpty, Full as SyncQueueFull

if sys.version_info >= (3, 13):
    from asyncio import QueueShutDown as AsyncQueueShutDown
    from queue import ShutDown as SyncQueueShutDown

    class QueueShutDown(SyncQueueShutDown, AsyncQueueShutDown):
        """Raised when put/get with shut-down queue."""

else:

    class QueueShutDown(Exception):
        """Raised when put/get with shut-down queue."""

    SyncQueueShutDown = QueueShutDown
    AsyncQueueShutDown = QueueShutDown


class QueueFull(SyncQueueFull, AsyncQueueFull):
    """Raised when non-blocking put with full queue."""


class QueueEmpty(SyncQueueEmpty, AsyncQueueEmpty):
    """Raised when non-blocking get with empty queue."""


class UnsupportedOperation(ValueError):
    """Raised when peek with non-peekable queue."""
