#!/usr/bin/env python3

import sys
import asyncio

from threading import Thread
from concurrent.futures import CancelledError


def work(loop, in_q, out_q):
    try:
        while True:
            item = asyncio.run_coroutine_threadsafe(in_q.get(), loop).result()

            if item is None:
                break

            loop.call_soon_threadsafe(out_q.put_nowait, item)
    except (CancelledError, RuntimeError):  # event loop is closed
        pass


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
    in_q = asyncio.Queue()
    out_q = asyncio.Queue()

    Thread(target=work, args=[asyncio.get_running_loop(), out_q, in_q]).start()

    try:
        await asyncio.wait_for(func(in_q, out_q), 6)
    except asyncio.TimeoutError:
        pass
    finally:
        await out_q.put(None)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
