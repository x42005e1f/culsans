#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sys

    from typing import Any, TypeVar

    if sys.version_info >= (3, 9):  # PEP 585
        from collections.abc import Callable
    else:
        from typing import Callable

    _CallableT = TypeVar("_CallableT", bound=Callable[..., Any])


def copydoc(wrapped: Callable[..., Any]) -> Callable[[_CallableT], _CallableT]:
    def decorator(function: _CallableT, /) -> _CallableT:
        function.__doc__ = wrapped.__doc__

        return function

    return decorator
