#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

import asyncio
import queue
import sys

SyncQueueEmpty = queue.Empty
AsyncQueueEmpty = asyncio.QueueEmpty


class QueueEmpty(SyncQueueEmpty, AsyncQueueEmpty):
    """
    Raised when non-blocking get/peek with empty queue.
    """


SyncQueueFull = queue.Full
AsyncQueueFull = asyncio.QueueFull


class QueueFull(SyncQueueFull, AsyncQueueFull):
    """
    Raised when non-blocking put with full queue.
    """


if sys.version_info >= (3, 13):  # python/cpython#96471
    SyncQueueShutDown = queue.ShutDown
    AsyncQueueShutDown = asyncio.QueueShutDown

else:

    class SyncQueueShutDown(Exception):
        """
        A backport of :exc:`queue.ShutDown`.
        """

    class AsyncQueueShutDown(Exception):
        """
        A backport of :exc:`asyncio.QueueShutDown`.
        """


class QueueShutDown(SyncQueueShutDown, AsyncQueueShutDown):
    """
    Raised when put/get/peek with shut-down queue.
    """


class UnsupportedOperation(ValueError):
    """
    Raised when peek/clear with non-peekable/non-clearable queue.
    """
