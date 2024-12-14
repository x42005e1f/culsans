#!/usr/bin/env python3

import asyncio

import pytest
import culsans


class TestMixedQueue:
    factory = culsans.Queue

    @pytest.mark.asyncio
    async def test_sync_put_async_get(self):
        queue = self.factory()
        loop = asyncio.get_running_loop()

        def sync_run(sync_q):
            assert sync_q.empty()

            for i in range(5):
                sync_q.put(i)

        async def async_run(async_q):
            for i in range(5):
                assert await async_q.get() == i

            assert async_q.empty()

        for i in range(3):
            await asyncio.gather(
                loop.run_in_executor(None, sync_run, queue.sync_q),
                async_run(queue.async_q),
            )

    @pytest.mark.asyncio
    async def test_async_put_sync_get(self):
        queue = self.factory()
        loop = asyncio.get_running_loop()

        def sync_run(sync_q):
            for i in range(5):
                assert sync_q.get() == i

            assert sync_q.empty()

        async def async_run(async_q):
            assert async_q.empty()

            for i in range(5):
                await async_q.put(i)

        for i in range(3):
            await asyncio.gather(
                loop.run_in_executor(None, sync_run, queue.sync_q),
                async_run(queue.async_q),
            )

    @pytest.mark.asyncio
    async def test_sync_join_async_done(self):
        queue = self.factory()
        loop = asyncio.get_running_loop()

        def sync_run(sync_q):
            assert sync_q.empty()

            for i in range(5):
                sync_q.put(i)

            sync_q.join()

        async def async_run(async_q):
            for i in range(5):
                assert await async_q.get() == i

                async_q.task_done()

            assert async_q.empty()

        for i in range(3):
            await asyncio.gather(
                loop.run_in_executor(None, sync_run, queue.sync_q),
                async_run(queue.async_q),
            )

    @pytest.mark.asyncio
    async def test_async_join_sync_done(self):
        queue = self.factory()
        loop = asyncio.get_running_loop()

        def sync_run(sync_q):
            for i in range(5):
                assert sync_q.get() == i

                sync_q.task_done()

            assert sync_q.empty()

        async def async_run(async_q):
            assert async_q.empty()

            for i in range(5):
                await async_q.put(i)

            await async_q.join()

        for i in range(3):
            await asyncio.gather(
                loop.run_in_executor(None, sync_run, queue.sync_q),
                async_run(queue.async_q),
            )

    @pytest.mark.asyncio
    async def test_growing_and_shrinking(self):
        queue = self.factory(1)
        loop = asyncio.get_running_loop()

        queue.async_q.put_nowait(0)
        assert queue.async_q.qsize() == 1

        task = loop.run_in_executor(None, queue.sync_q.put, 1)

        while not queue._not_full.waiting:
            await asyncio.sleep(1e-3)

        queue.async_q.maxsize = 2  # growing

        await task
        assert queue.async_q.qsize() == 2

        task = loop.run_in_executor(None, queue.sync_q.put, 2)

        while not queue._not_full.waiting:
            await asyncio.sleep(1e-3)

        queue.async_q.maxsize = 1  # shrinking

        assert queue._not_full.waiting == 1
        assert queue.async_q.qsize() == 2

        queue.async_q.get_nowait()

        assert queue._not_full.waiting == 1
        assert queue.async_q.qsize() == 1

        queue.async_q.maxsize = 0  # now the queue size is infinite

        await task
        assert queue.async_q.qsize() == 2

    @pytest.mark.asyncio
    async def test_peek(self):
        queue = self.factory()

        assert queue.sync_q.peekable()
        assert queue.async_q.peekable()

        with pytest.raises(culsans.SyncQueueEmpty):
            queue.sync_q.peek(block=False)
        with pytest.raises(culsans.SyncQueueEmpty):
            queue.sync_q.peek_nowait()
        with pytest.raises(culsans.AsyncQueueEmpty):
            queue.async_q.peek_nowait()

        queue.async_q.put_nowait(42)

        assert queue.sync_q.peek() == 42
        assert queue.sync_q.peek_nowait() == 42
        assert await queue.async_q.peek() == 42
        assert queue.async_q.peek_nowait() == 42

    @pytest.mark.asyncio
    async def test_clear(self):
        queue = self.factory()
        loop = asyncio.get_running_loop()

        for i in range(3):
            queue.async_q.put_nowait(i)

        assert queue.unfinished_tasks == 3
        assert queue.async_q.qsize() == 3

        task = loop.run_in_executor(None, queue.sync_q.join)

        queue.async_q.clear()

        assert queue.unfinished_tasks == 0
        assert queue.async_q.qsize() == 0

        await task

        for i in range(3):
            queue.async_q.put_nowait(i)

        assert queue.unfinished_tasks == 3
        assert queue.async_q.qsize() == 3

        task = asyncio.create_task(queue.async_q.join())

        queue.sync_q.clear()

        assert queue.unfinished_tasks == 0
        assert queue.async_q.qsize() == 0

        await task

    @pytest.mark.asyncio
    async def test_closed(self):
        queue = self.factory()

        assert not queue.closed
        assert not queue.async_q.closed
        assert not queue.sync_q.closed

        queue.close()

        assert queue.closed
        assert queue.async_q.closed
        assert queue.sync_q.closed

    @pytest.mark.asyncio
    async def test_double_closing(self):
        queue = self.factory()

        queue.close()
        queue.close()

        await queue.wait_closed()

    @pytest.mark.asyncio
    async def test_wait_without_closing(self):
        queue = self.factory()

        with pytest.raises(RuntimeError):
            await queue.wait_closed()

        queue.close()
        await queue.wait_closed()

    @pytest.mark.asyncio
    async def test_modifying_forbidden_after_closing(self):
        queue = self.factory()
        queue.close()

        with pytest.raises(culsans.SyncQueueShutDown):
            queue.sync_q.put(5)
        with pytest.raises(culsans.SyncQueueShutDown):
            queue.sync_q.put_nowait(5)

        with pytest.raises(culsans.SyncQueueShutDown):
            queue.sync_q.get()
        with pytest.raises(culsans.SyncQueueShutDown):
            queue.sync_q.get_nowait()

        with pytest.raises(culsans.AsyncQueueShutDown):
            await queue.async_q.put(5)
        with pytest.raises(culsans.AsyncQueueShutDown):
            queue.async_q.put_nowait(5)

        with pytest.raises(culsans.AsyncQueueShutDown):
            await queue.async_q.get()
        with pytest.raises(culsans.AsyncQueueShutDown):
            queue.async_q.get_nowait()

        await queue.wait_closed()
