=======
culsans
=======

Mixed sync-async queue, supposed to be used for communicating between classic
synchronous (threaded) code and asynchronous one, between two asynchronous
codes in different threads, and for any other combination that you want. Based
on the `queue <https://docs.python.org/3/library/queue.html>`_ module. Built
on the `aiologic <https://pypi.org/project/aiologic/>`_ package. Inspired
by the `janus <https://pypi.org/project/janus/>`_ library.

Like `Culsans god <https://en.wikipedia.org/wiki/Culsans>`_, the queue object
from the library has two faces: synchronous and asynchronous interface. Unlike
`Janus library <https://pypi.org/project/janus/>`_, synchronous interface
supports `eventlet <https://pypi.org/project/eventlet/>`_,
`gevent <https://pypi.org/project/gevent/>`_, and
`threading <https://docs.python.org/3/library/threading.html>`_, while
asynchronous interface supports
`asyncio <https://docs.python.org/3/library/asyncio.html>`_,
`trio <https://pypi.org/project/trio/>`_, and
`anyio <https://pypi.org/project/anyio/>`_.

Synchronous is fully compatible with
`standard queue <https://docs.python.org/3/library/queue.html>`_, asynchronous
one follows
`asyncio queue design <https://docs.python.org/3/library/asyncio-queue.html>`_.

Usage
=====

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
process. For this purpose, there is an atomic method ``clear()`` that clears
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
you were using the ``queue`` module. For example, this is how you can create an
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

        _peek = None

        def _peekable(self):
            return False

        def _get(self):
            return self.data.pop()

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

Greenlets
---------

Libraries such as ``eventlet`` and ``gevent`` use
`greenlets <https://greenlet.readthedocs.io/en/latest/>`_ instead of
`tasks <https://anyio.readthedocs.io/en/stable/tasks.html>`_.
Since they do not use async-await syntax, their code is similar to synchronous
code. There are three ways that you can tell ``culsans`` that you want to use
greenlets instead of threads:

* Set ``aiologic.lowlevel.current_green_library_tlocal.name``
  (for the current thread).
* Patch the ``threading`` module
  (for the main thread).
* Specify ``AIOLOGIC_GREEN_LIBRARY`` environment variable
  (for all threads).

The value is the name of the library that you want to use.

Checkpoints
-----------

Sometimes it is useful when each asynchronous call switches execution to the
next task and checks for cancellation and timeouts. For example, if you want to
distribute CPU usage across all tasks. There are two ways to do this:

* Set ``aiologic.lowlevel.<library>_checkpoints_cvar``
  (for the current context).
* Specify ``AIOLOGIC_<LIBRARY>_CHECKPOINTS`` environment variable
  (for all contexts).

The value is ``True`` or ``False`` for the first way, and a non-empty or empty
string for the second.

Checkpoints are enabled by default for the ``trio`` library.

Compatibility
=============

The interfaces are compliant with the Python API version 3.13, and the
``culsans`` library itself is almost fully compatible with the ``janus``
library version 1.1.0. If you are using ``janus`` in your application and want
to switch to ``culsans``, all you have to do is replace this:

.. code:: python

    import janus

with this:

.. code:: python

    import culsans as janus

and everything will work, except for the queue behavior after the ``close()``
call: new ``put()`` calls will still raise a ``RuntimeError``, but all
currently waiting ones will be woken up, and the ``join()`` and ``task_done()``
calls will succeed. This behavior corresponds to the queue behavior after the
``shutdown()`` call and solves
`aio-libs/janus#237 <https://github.com/aio-libs/janus/issues/237>`_.

Performance
===========

Being built on the ``aiologic`` package, the ``culsans`` library has
speed advantages. In sync -> async benchmarks, ``culsans.Queue`` is typically
5/6/3 times faster than ``janus.Queue`` on CPython 3.9-3.11/3.12/3.13, and 15
times faster on PyPy 3.10. However, if your application is performance
sensitive and you do not need API compatibility, try ``aiologic`` queues.
They are 6/7/4 times faster and 30 times faster in the same benchmarks.

Communication channels
======================

GitHub Discussions: https://github.com/x42005e1f/culsans/discussions

Feel free to post your questions and ideas here.

License
=======

The ``culsans`` library is offered under Zero-Clause BSD license.
