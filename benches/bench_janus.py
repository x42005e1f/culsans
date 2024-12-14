#!/usr/bin/env python3

import sys
import asyncio

import janus


def work(in_q, out_q):
    while True:
        item = in_q.get()

        if item is None:
            break

        out_q.put_nowait(item)


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
    in_q = janus.Queue()
    out_q = janus.Queue()

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, work, out_q.sync_q, in_q.sync_q)

    try:
        await asyncio.wait_for(func(in_q.async_q, out_q.async_q), 6)
    except asyncio.TimeoutError:
        pass
    finally:
        out_q.sync_q.put_nowait(None)
        await future


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
