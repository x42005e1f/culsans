#!/usr/bin/env python3

import pytest
import culsans


class _TestQueueBase:
    def test_init(self):
        assert self.factory().maxsize == 0
        assert self.factory(1).maxsize == 1
        assert self.factory(maxsize=-1).maxsize == -1

    def test_getters(self):
        queue = self.factory()

        assert queue.sync_q.wrapped is queue
        assert queue.async_q.wrapped is queue

        assert queue.unfinished_tasks == 0
        assert queue.sync_q.unfinished_tasks == 0
        assert queue.async_q.unfinished_tasks == 0

        assert not queue.is_shutdown
        assert not queue.sync_q.is_shutdown
        assert not queue.async_q.is_shutdown

        assert queue.maxsize == 0
        assert queue.sync_q.maxsize == 0
        assert queue.async_q.maxsize == 0

        with pytest.raises(AttributeError):
            queue.nonexistent_attribute
        with pytest.raises(AttributeError):
            queue.sync_q.nonexistent_attribute
        with pytest.raises(AttributeError):
            queue.async_q.nonexistent_attribute

    def test_setters(self):
        queue = self.factory()

        with pytest.raises(AttributeError):
            queue.sync_q = queue.sync_q
        with pytest.raises(AttributeError):
            queue.async_q = queue.async_q

        with pytest.raises(AttributeError):
            queue.unfinished_tasks = queue.unfinished_tasks
        with pytest.raises(AttributeError):
            queue.sync_q.unfinished_tasks = queue.sync_q.unfinished_tasks
        with pytest.raises(AttributeError):
            queue.async_q.unfinished_tasks = queue.async_q.unfinished_tasks

        with pytest.raises(AttributeError):
            queue.is_shutdown = queue.is_shutdown
        with pytest.raises(AttributeError):
            queue.sync_q.is_shutdown = queue.sync_q.is_shutdown
        with pytest.raises(AttributeError):
            queue.async_q.is_shutdown = queue.async_q.is_shutdown

        queue.maxsize = 1
        assert queue.maxsize == 1
        queue.maxsize = -1
        assert queue.maxsize == -1

        queue.sync_q.maxsize = 1
        assert queue.maxsize == 1
        queue.sync_q.maxsize = -1
        assert queue.maxsize == -1

        queue.async_q.maxsize = 1
        assert queue.maxsize == 1
        queue.async_q.maxsize = -1
        assert queue.maxsize == -1

        with pytest.raises(AttributeError):
            queue.nonexistent_attribute = 42
        with pytest.raises(AttributeError):
            queue.sync_q.nonexistent_attribute = 42
        with pytest.raises(AttributeError):
            queue.async_q.nonexistent_attribute = 42

    def test_deleters(self):
        queue = self.factory()

        with pytest.raises(AttributeError):
            del queue.sync_q
        with pytest.raises(AttributeError):
            del queue.async_q

        with pytest.raises(AttributeError):
            del queue.unfinished_tasks
        with pytest.raises(AttributeError):
            del queue.sync_q.unfinished_tasks
        with pytest.raises(AttributeError):
            del queue.async_q.unfinished_tasks

        with pytest.raises(AttributeError):
            del queue.is_shutdown
        with pytest.raises(AttributeError):
            del queue.sync_q.is_shutdown
        with pytest.raises(AttributeError):
            del queue.async_q.is_shutdown

        with pytest.raises(AttributeError):
            del queue.maxsize
        with pytest.raises(AttributeError):
            del queue.sync_q.maxsize
        with pytest.raises(AttributeError):
            del queue.async_q.maxsize

        with pytest.raises(AttributeError):
            del queue.nonexistent_attribute
        with pytest.raises(AttributeError):
            del queue.sync_q.nonexistent_attribute
        with pytest.raises(AttributeError):
            del queue.async_q.nonexistent_attribute

    def test_unfinished(self):
        queue = self.factory()
        assert queue.unfinished_tasks == 0

        queue.sync_q.put(1)
        assert queue.unfinished_tasks == 1

        queue.sync_q.get()
        assert queue.unfinished_tasks == 1

        queue.sync_q.task_done()
        assert queue.unfinished_tasks == 0

    def test_shutdown(self):
        queue = self.factory()

        queue.sync_q.put(1)
        queue.sync_q.task_done()
        queue.sync_q.put(2)

        queue.shutdown()

        assert queue._qsize() == 2
        assert queue.unfinished_tasks == 1
        assert queue.is_shutdown

        queue.shutdown()

    def test_immediate_shutdown(self):
        queue = self.factory()

        queue.sync_q.put(1)
        queue.sync_q.task_done()
        queue.sync_q.put(2)

        queue.shutdown(immediate=True)

        assert queue._qsize() == 0
        assert queue.unfinished_tasks == 0
        assert queue.is_shutdown

        queue.shutdown(immediate=True)


class TestQueue(_TestQueueBase):
    factory = culsans.Queue


class TestLifoQueue(_TestQueueBase):
    factory = culsans.LifoQueue


class TestPriorityQueue(_TestQueueBase):
    factory = culsans.PriorityQueue
