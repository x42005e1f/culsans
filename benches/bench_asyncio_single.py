#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: 0BSD

import asyncio
import sys


async def func(in_q, out_q):
    ops = 0

    try:
        item = 42
        loop = asyncio.get_running_loop()

        while True:
            loop.call_soon_threadsafe(out_q.put_nowait, item)

            item = await in_q.get()

            ops += 1
    finally:
        print(ops // 6)


async def main():
    queue = asyncio.Queue()

    try:
        await asyncio.wait_for(func(queue, queue), 6)
    except asyncio.TimeoutError:
        pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
