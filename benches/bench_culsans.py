#!/usr/bin/env python3

import sys
import asyncio

from threading import Thread

import culsans


def work(in_q, out_q):
    while True:
        item = in_q.get()

        if item is None:
            break

        out_q.put(item)


async def func(in_q, out_q):
    ops = 0

    try:
        item = 42

        while True:
            await out_q.put(item)

            ops += 1

            item = await in_q.get()
    finally:
        print(ops)


async def main():
    in_q = culsans.Queue()
    out_q = culsans.Queue()

    Thread(target=work, args=[out_q.sync_q, in_q.sync_q]).start()

    try:
        await asyncio.wait_for(func(in_q.async_q, out_q.async_q), 6)
    except asyncio.TimeoutError:
        pass
    finally:
        await out_q.async_q.put(None)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
