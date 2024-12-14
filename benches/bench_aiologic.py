#!/usr/bin/env python3

import sys
import asyncio

import aiologic


def work(in_q, out_q):
    while True:
        item = in_q.green_get()

        if item is None:
            break

        out_q.put(item)


async def func(in_q, out_q):
    ops = 0

    try:
        item = 42

        while True:
            out_q.put(item)

            item = await in_q.async_get()

            ops += 1
    finally:
        print(ops // 6)


async def main():
    in_q = aiologic.SimpleQueue()
    out_q = aiologic.SimpleQueue()

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, work, out_q, in_q)

    try:
        await asyncio.wait_for(func(in_q, out_q), 6)
    except asyncio.TimeoutError:
        pass
    finally:
        out_q.put(None)
        await future


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
