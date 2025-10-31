..
  SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
  SPDX-License-Identifier: CC-BY-4.0

API reference
=============

Queues
------

.. autoclass:: culsans.Queue
  :members:
  :no-inherited-members:
.. autoclass:: culsans.LifoQueue
  :members:
  :no-inherited-members:
.. autoclass:: culsans.PriorityQueue
  :members:
  :no-inherited-members:

Proxies
-------

.. autoclass:: culsans.SyncQueueProxy
  :members:
  :no-inherited-members:
.. autoclass:: culsans.AsyncQueueProxy
  :members:
  :no-inherited-members:

Protocols
---------

.. autoclass:: culsans.BaseQueue
  :members:
  :no-inherited-members:
.. autoclass:: culsans.MixedQueue
  :members:
  :no-inherited-members:
.. autoclass:: culsans.SyncQueue
  :members:
  :no-inherited-members:
.. autoclass:: culsans.AsyncQueue
  :members:
  :no-inherited-members:

Exceptions
----------

.. culsans.QueueEmpty-start-marker
.. py:exception:: culsans.QueueEmpty
  :no-index:

  Bases: :exc:`~culsans.SyncQueueEmpty`, :exc:`~culsans.AsyncQueueEmpty`

  Exception raised when non-blocking get/peek is called on a
  :class:`~culsans.Queue` object which is empty.
.. culsans.QueueEmpty-end-marker

.. culsans.SyncQueueEmpty-start-marker
.. py:exception:: culsans.SyncQueueEmpty
  :no-index:

  Bases: :exc:`Exception`

  The same as :exc:`queue.Empty`.
.. culsans.SyncQueueEmpty-end-marker

.. culsans.AsyncQueueEmpty-start-marker
.. py:exception:: culsans.AsyncQueueEmpty
  :no-index:

  Bases: :exc:`Exception`

  The same as :exc:`asyncio.QueueEmpty`.
.. culsans.AsyncQueueEmpty-end-marker

.. culsans.QueueFull-start-marker
.. py:exception:: culsans.QueueFull
  :no-index:

  Bases: :exc:`~culsans.SyncQueueFull`, :exc:`~culsans.AsyncQueueFull`

  Exception raised when non-blocking put is called on a :class:`~culsans.Queue`
  object which is full.
.. culsans.QueueFull-end-marker

.. culsans.SyncQueueFull-start-marker
.. py:exception:: culsans.SyncQueueFull
  :no-index:

  Bases: :exc:`Exception`

  The same as :exc:`queue.Full`.
.. culsans.SyncQueueFull-end-marker

.. culsans.AsyncQueueFull-start-marker
.. py:exception:: culsans.AsyncQueueFull
  :no-index:

  Bases: :exc:`Exception`

  The same as :exc:`asyncio.QueueFull`.
.. culsans.AsyncQueueFull-end-marker

.. culsans.QueueShutDown-start-marker
.. py:exception:: culsans.QueueShutDown
  :no-index:

  Bases: :exc:`~culsans.SyncQueueShutDown`, :exc:`~culsans.AsyncQueueShutDown`

  Exception raised when put/get/peek is called on a :class:`~culsans.Queue`
  object which has been shut down.
.. culsans.QueueShutDown-end-marker

.. culsans.SyncQueueShutDown-start-marker
.. py:exception:: culsans.SyncQueueShutDown
  :no-index:

  Bases: :exc:`Exception`

  The same as :exc:`queue.ShutDown`.
.. culsans.SyncQueueShutDown-end-marker

.. culsans.AsyncQueueShutDown-start-marker
.. py:exception:: culsans.AsyncQueueShutDown
  :no-index:

  Bases: :exc:`Exception`

  The same as :exc:`asyncio.QueueShutDown`.
.. culsans.AsyncQueueShutDown-end-marker

.. culsans.UnsupportedOperation-start-marker
.. py:exception:: culsans.UnsupportedOperation
  :no-index:

  Bases: :exc:`ValueError`

  Exception raised when peek is called on a :class:`~culsans.Queue` object
  which is not peekable.
.. culsans.UnsupportedOperation-end-marker
