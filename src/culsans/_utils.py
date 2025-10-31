#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

import sys

from typing import Any, TypeVar

if sys.version_info >= (3, 9):
    from collections.abc import Callable
else:
    from typing import Callable

_CallableT = TypeVar("_CallableT", bound=Callable[..., Any])


def _copydoc(
    wrapped: Callable[..., Any],
) -> Callable[[_CallableT], _CallableT]:
    def decorator(func: _CallableT) -> _CallableT:
        func.__doc__ = wrapped.__doc__

        return func

    return decorator
