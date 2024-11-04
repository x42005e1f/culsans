#!/usr/bin/env python3

import sys
import asyncio

from threading import Thread

import aiologic


def work(in_q, out_q):
    while True:
        item = in_q.green_get()

        if item is None:
            break

        out_q.green_put(item)


async def func(in_q, out_q):
    ops = 0

    try:
        item = 42

        while True:
            await out_q.async_put(item)

            ops += 1

            item = await in_q.async_get()
    finally:
        print(ops)


async def main():
    in_q = aiologic.SimpleQueue()
    out_q = aiologic.SimpleQueue()

    Thread(target=work, args=[out_q, in_q]).start()

    try:
        await asyncio.wait_for(func(in_q, out_q), 6)
    except asyncio.TimeoutError:
        pass
    finally:
        await out_q.async_put(None)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
