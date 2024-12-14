#!/usr/bin/env python3

import sys
import asyncio


def work(loop, in_q, out_q):
    while True:
        item = asyncio.run_coroutine_threadsafe(in_q.get(), loop).result()

        if item is None:
            break

        loop.call_soon_threadsafe(out_q.put_nowait, item)


async def func(in_q, out_q):
    ops = 0

    try:
        item = 42

        while True:
            out_q.put_nowait(item)

            item = await in_q.get()

            ops += 1
    finally:
        print(ops // 6)


async def main():
    in_q = asyncio.Queue()
    out_q = asyncio.Queue()

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, work, loop, out_q, in_q)

    try:
        await asyncio.wait_for(func(in_q, out_q), 6)
    except asyncio.TimeoutError:
        pass
    finally:
        out_q.put_nowait(None)
        await future


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
