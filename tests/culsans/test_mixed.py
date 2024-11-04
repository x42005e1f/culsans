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
