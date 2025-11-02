#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
# SPDX-License-Identifier: ISC

from __future__ import annotations

import sys

from typing import TYPE_CHECKING, Any, TypeVar

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


def _export(namespace: dict[str, Any]) -> None:
    if TYPE_CHECKING:
        # sphinx.ext.autodoc does not support hacks below. In particular,
        # 'bysource' ordering will not work, nor will some cross-references. So
        # we skip them on type checking (implied by
        # SPHINX_AUTODOC_RELOAD_MODULES=1).
        return

    module_name: str = namespace["__name__"]

    for value in namespace.values():
        if getattr(value, "__module__", "").startswith(f"{module_name}."):
            value.__module__ = module_name
