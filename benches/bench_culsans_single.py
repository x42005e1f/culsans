#!/usr/bin/env python3

import sys
import asyncio

import culsans


async def func(in_q, out_q):
    ops = 0

    try:
        item = 42
        loop = asyncio.get_running_loop()

        while True:
            loop.call_soon(out_q.put, item)

            item = await in_q.get()

            ops += 1
    finally:
        print(ops // 6)


async def main():
    queue = culsans.Queue()

    try:
        await asyncio.wait_for(func(queue.async_q, queue.sync_q), 6)
    except asyncio.TimeoutError:
        pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
