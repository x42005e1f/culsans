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

        def _get(self):
            return self.data.pop()

.. code:: python

    sync_q = UniqueQueue().sync_q

    sync_q.put_nowait(23)
    sync_q.put_nowait(42)
    sync_q.put_nowait(23)

    assert sync_q.qsize() == 2
    assert sorted(sync_q.get_nowait() for _ in range(2)) == [23, 42]

All four of these methods are called in exclusive access mode, so you can
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

Performance
===========

Being built on the ``aiologic`` package, the ``culsans`` library has
speed advantages.
In `sync -> async tests <https://github.com/aio-libs/janus/issues/679>`_,
``culsans.Queue`` is typically 4 times faster than ``janus.Queue`` on CPython,
and 8 times faster on PyPy. However, if your application is performance
sensitive and you do not need API compatibility, try ``aiologic`` queues.
They are 7 times faster and 24 times faster in the same tests.

Communication channels
======================

GitHub Discussions: https://github.com/x42005e1f/culsans/discussions

Feel free to post your questions and ideas here.

License
=======

The ``culsans`` library is offered under Zero-Clause BSD license.
