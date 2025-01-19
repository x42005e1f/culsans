#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2024 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: 0BSD

import asyncio
import sys

import aiologic


async def func(in_q, out_q):
    ops = 0

    try:
        item = 42
        loop = asyncio.get_running_loop()

        while True:
            loop.call_soon(out_q.put, item)

            item = await in_q.async_get()

            ops += 1
    finally:
        print(ops // 6)


async def main():
    aiologic.lowlevel.current_async_library_tlocal.name = "asyncio"

    queue = aiologic.SimpleQueue()

    try:
        await asyncio.wait_for(func(queue, queue), 6)
    except asyncio.TimeoutError:
        pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
