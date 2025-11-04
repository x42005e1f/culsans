..
  SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
  SPDX-License-Identifier: CC-BY-4.0

=======
culsans
=======

|pypi-dw| |pypi-impl| |pypi-pyv| |pypi-types|

.. |pypi-dw| image:: https://img.shields.io/pypi/dw/culsans
  :target: https://pypistats.org/packages/culsans
  :alt:
.. |pypi-impl| image:: https://img.shields.io/pypi/implementation/culsans
  :target: #features
  :alt:
.. |pypi-pyv| image:: https://img.shields.io/pypi/pyversions/culsans
  :target: #features
  :alt:
.. |pypi-types| image:: https://img.shields.io/pypi/types/culsans
  :target: #features
  :alt:

.. description-start-marker

Mixed sync-async queue, supposed to be used for communicating between classic
synchronous (threaded) code and asynchronous one, between two asynchronous
codes in different threads, and for any other combination that you want. Based
on the `queue <https://docs.python.org/3/library/queue.html>`_ module. Built on
the `aiologic <https://github.com/x42005e1f/aiologic>`_ package. Inspired by
the `janus <https://github.com/aio-libs/janus>`_ library.

Like `Culsans god <https://en.wikipedia.org/wiki/Culsans>`_, the queue object
from the library has two faces: synchronous and asynchronous interface. Unlike
`Janus library <https://github.com/aio-libs/janus>`_, synchronous interface
supports `eventlet <https://github.com/eventlet/eventlet>`_, `gevent <https://
github.com/gevent/gevent>`_, and `threading <https://docs.python.org/3/library/
threading.html>`_, while asynchronous interface supports `asyncio <https://
docs.python.org/3/library/asyncio.html>`_, `curio <https://github.com/dabeaz/
curio>`_, and `trio <https://github.com/python-trio/trio>`_.

Synchronous is fully compatible with `standard queue <https://docs.python.org/
3/library/queue.html>`_, asynchronous one follows `asyncio queue design
<https://docs.python.org/3/library/asyncio-queue.html>`_.

.. description-end-marker

Installation
============

.. installation-start-marker

Install from `PyPI <https://pypi.org/project/culsans/>`_ (stable):

.. code:: console

    pip install culsans

Or from `GitHub <https://github.com/x42005e1f/culsans>`_ (latest):

.. code:: console

    pip install git+https://github.com/x42005e1f/culsans.git

You can also use other package managers, such as `uv <https://github.com/
astral-sh/uv>`_.

.. installation-end-marker

Usage
=====

.. usage-start-marker

Three queues are available:

* ``Queue``
* ``LifoQueue``
* ``PriorityQueue``

Each has two properties: ``sync_q`` and ``async_q``.

Use the first to get synchronous interface and the second to get asynchronous
one.

Example
-------

.. code:: python

    import anyio
    import culsans


    def sync_run(sync_q: culsans.SyncQueue[int]) -> None:
        for i in range(100):
            sync_q.put(i)
        else:
            sync_q.join()


    async def async_run(async_q: culsans.AsyncQueue[int]) -> None:
        for i in range(100):
            value = await async_q.get()

            assert value == i

            async_q.task_done()


    async def main() -> None:
        queue: culsans.Queue[int] = culsans.Queue()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(anyio.to_thread.run_sync, sync_run, queue.sync_q)
            tasks.start_soon(async_run, queue.async_q)

        queue.shutdown()


    anyio.run(main)

Extras
------

Both interfaces support some additional features that are not found in the
original queues.

growing & shrinking
^^^^^^^^^^^^^^^^^^^

You can dynamically change the upperbound limit on the number of items that can
be placed in the queue with ``queue.maxsize = N``. If it increases (growing),
the required number of waiting putters will be woken up. If it decreases
(shrinking), items exceeding the new limit will remain in the queue, but all
putters will be blocked until enough items are retrieved from the queue. And if
*maxsize* is less than or equal to zero, all putters will be woken up.

.. code:: python

    async with anyio.create_task_group() as tasks:
        async_q = culsans.Queue(1).async_q

        for i in range(4):
            tasks.start_soon(async_q.put, i)

        await anyio.sleep(1e-3)
        assert async_q.qsize() == 1

        async_q.maxsize = 2  # growing

        await anyio.sleep(1e-3)
        assert async_q.qsize() == 2

        async_q.maxsize = 1  # shrinking

        await anyio.sleep(1e-3)
        assert async_q.qsize() == 2

        async_q.get_nowait()

        await anyio.sleep(1e-3)
        assert async_q.qsize() == 1

        async_q.maxsize = 0  # now the queue size is infinite

        await anyio.sleep(1e-3)
        assert async_q.qsize() == 3

peek() & peek_nowait()
^^^^^^^^^^^^^^^^^^^^^^

If you want to check the first item of the queue, but do not want to remove
that item from the queue, you can use the ``peek()`` and ``peek_nowait()``
methods instead of the ``get()`` and ``get_nowait()`` methods.

.. code:: python

    sync_q = culsans.Queue().sync_q

    sync_q.put("spam")

    assert sync_q.peekable()
    assert sync_q.peek() == "spam"
    assert sync_q.peek_nowait() == "spam"
    assert sync_q.qsize() == 1

These methods can be considered an implementation of partial compatibility with
`gevent queues <https://www.gevent.org/api/gevent.queue.html>`_.

clear()
^^^^^^^

In some scenarios it may be necessary to clear the queue. But it is inefficient
to do this through a loop, and it causes additional difficulties when it is
also necessary to ensure that no new items can be added during the clearing
process. For this purpose, there is the atomic ``clear()`` method that clears
the queue most efficiently.

.. code:: python

    async with anyio.create_task_group() as tasks:
        async_q = culsans.Queue(3).async_q

        for i in range(5):
            tasks.start_soon(async_q.put, i)

        await anyio.sleep(1e-3)
        assert async_q.qsize() == 3

        async_q.clear()  # clearing

        await anyio.sleep(1e-3)
        assert async_q.qsize() == 2
        assert async_q.get_nowait() == 3
        assert async_q.get_nowait() == 4

Roughly equivalent to:

.. code:: python

    def clear(queue):
        while True:
            try:
                queue.get_nowait()
            except Empty:
                break
            else:
                queue.task_done()

Subclasses
----------

You can create your own queues by inheriting from existing queue classes as if
you were using the queue module. For example, this is how you can create an
unordered queue that contains only unique items:

.. code:: python

    from culsans import Queue


    class UniqueQueue(Queue):
        def _init(self, maxsize):
            self.data = set()

        def _qsize(self):
            return len(self.data)

        def _put(self, item):
            self.data.add(item)

        def _get(self):
            return self.data.pop()

        _peek = None

        def _peekable(self):
            return False

        def _clear(self):
            self.data.clear()

.. code:: python

    sync_q = UniqueQueue().sync_q

    sync_q.put_nowait(23)
    sync_q.put_nowait(42)
    sync_q.put_nowait(23)

    assert sync_q.qsize() == 2
    assert sorted(sync_q.get_nowait() for _ in range(2)) == [23, 42]

All seven of these methods are called in exclusive access mode, so you can
freely create your subclasses without thinking about whether your methods are
thread-safe or not.

Checkpoints
-----------

Sometimes it is useful when each asynchronous call switches execution to the
next task and checks for cancellation and timeouts. For example, if you want to
distribute CPU usage across all tasks.

The culsans library adopts aiologic's checkpoints, but unlike it does not
guarantee that there will only be one per asynchronous call, due to design
specifics.

See the aiologic documentation for details on how to control checkpoints.

.. usage-end-marker

Compatibility
=============

.. compatibility-start-marker

If you want to use culsans as a backport of the standard queues to older
versions of Python (for example, if you need the ``shutdown()`` method), you
can replace something like this:

.. code:: python

    sync_q = queue.Queue()
    async_q = asyncio.Queue()

with this:

.. code:: python

    sync_q = culsans.Queue().sync_q
    async_q = culsans.Queue().async_q

And if you are using janus in your application and want to switch to culsans,
all you have to do is replace this:

.. code:: python

    import janus

with this:

.. code:: python

    import culsans as janus

and everything will work!

.. compatibility-end-marker

Documentation
=============

Read the Docs: https://culsans.readthedocs.io (official)

DeepWiki: https://deepwiki.com/x42005e1f/culsans (AI generated)

Communication channels
======================

GitHub Discussions: https://github.com/x42005e1f/culsans/discussions (ideas,
questions)

GitHub Issues: https://github.com/x42005e1f/culsans/issues (bug tracker)

You can also send an email to 0x42005e1f@gmail.com with any feedback.

Support
=======

If you like culsans and want to support its development, please star `its
repository on GitHub <https://github.com/x42005e1f/culsans>`_.

.. image:: https://starchart.cc/x42005e1f/culsans.svg?variant=adaptive
  :target: https://starchart.cc/x42005e1f/culsans

License
=======

.. license-start-marker

The culsans library is `REUSE-compliant <https://api.reuse.software/info/
github.com/x42005e1f/culsans>`_ and is offered under multiple licenses:

* All original source code is licensed under `ISC`_.
* All original test code is licensed under `0BSD`_.
* All documentation is licensed under `CC-BY-4.0`_.
* All configuration is licensed under `CC0-1.0`_.
* Some test code borrowed from `python/cpython <https://github.com/python/
  cpython>`_ is licensed under `PSF-2.0`_.

For more accurate information, check the individual files.

.. _ISC: https://choosealicense.com/licenses/isc/
.. _0BSD: https://choosealicense.com/licenses/0bsd/
.. _CC-BY-4.0: https://choosealicense.com/licenses/cc-by-4.0/
.. _CC0-1.0: https://choosealicense.com/licenses/cc0-1.0/
.. _PSF-2.0: https://docs.python.org/3/license.html

.. license-end-marker
