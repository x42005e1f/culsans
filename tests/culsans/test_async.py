#!/usr/bin/env python3

import pytest
import culsans


class TestAsyncQueue:
    def factory(self, *args, **kwargs):
        return culsans.Queue(*args, **kwargs).async_q

    def test_getters(self):
        queue = self.factory()

        assert queue.unfinished_tasks == 0
        assert not queue.is_shutdown

        assert queue.maxsize == 0

        with pytest.raises(AttributeError):
            queue.nonexistent_attribute

    def test_setters(self):
        queue = self.factory()

        with pytest.raises(AttributeError):
            queue.unfinished_tasks = queue.unfinished_tasks
        with pytest.raises(AttributeError):
            queue.is_shutdown = queue.is_shutdown

        queue.maxsize = 1
        assert queue.maxsize == 1
        queue.maxsize = -1
        assert queue.maxsize == -1

        with pytest.raises(AttributeError):
            queue.nonexistent_attribute = 42

    def test_deleters(self):
        queue = self.factory()

        with pytest.raises(AttributeError):
            del queue.unfinished_tasks
        with pytest.raises(AttributeError):
            del queue.is_shutdown

        with pytest.raises(AttributeError):
            del queue.maxsize

        with pytest.raises(AttributeError):
            del queue.nonexistent_attribute
