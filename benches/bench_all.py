#!/usr/bin/env python3

import sys
import subprocess

from pathlib import Path

workdir = Path(__file__).parent
executables = [
    "python3.9",
    "python3.10",
    "python3.11",
    "python3.12",
    "python3.13",
    "python3.13t",
    "pypy3.10",
]
libraries = [
    "janus",
    "culsans",
    "aiologic",
    "asyncio",
]
iterations = 9


def print_table(header, data):
    columns_count = len(libraries) + 1
    table_column_width = (
        max(
            7,
            *map(len, libraries),
            *map(len, executables),
        )
        + 2
    )
    table_header_width = max(
        len(header) + 2,
        (table_column_width + 1) * columns_count - 1,
    )
    table_column_width = max(
        table_column_width,
        (table_header_width + 1) // columns_count - 1,
    )

    print()
    print(end="+")
    print(end="+".join(["-" * table_header_width] * 1))
    print(end="+")
    print()
    print(end="|")
    print(end=f"{header:^{table_header_width}}")
    print(end="|")
    print()
    print(end="+")
    print(end="+".join(["-" * table_column_width] * columns_count))
    print(end="+")
    print()
    print(end="|")
    print(
        end="|".join(
            [
                f"{'python':^{table_column_width}}",
                *(f"{library:^{table_column_width}}" for library in libraries),
            ]
        )
    )
    print(end="|")
    print()
    print(end="+")
    print(end="+".join(["=" * table_column_width] * columns_count))
    print(end="+")
    print()

    for executable in executables:
        values = [data[library][executable] for library in libraries]
        relative_values = [value / values[0] for value in values]
        humanized_values = [
            (
                f"{1 - relative_value:>+5.2%}"
                if relative_value != 1 and abs(1 - relative_value) < 1
                else f"×{relative_value:>4.2f}"
            )
            for relative_value in relative_values
        ]

        print(end="|")
        print(
            end="|".join(
                [
                    f" {executable:<{table_column_width - 1}}",
                    *(
                        f"{humanized_value:^{table_column_width}}"
                        for humanized_value in humanized_values
                    ),
                ]
            )
        )
        print(end="|")
        print()
        print(end="+")
        print(end="+".join(["-" * table_column_width] * columns_count))
        print(end="+")
        print()


def measure(library):
    data = {}

    for executable in executables:
        ops = []

        print(f"    {executable}:")

        for i in range(1, iterations + 1):
            ops.append(
                int(
                    subprocess.run(
                        [executable, str(workdir / f"bench_{library}.py")],
                        capture_output=True,
                        timeout=10,
                        check=True,
                    ).stdout
                )
            )

            print(f"      {ops[-1]} ops ({i}/{iterations})")

        data[executable] = max(ops)

    return data


def measure_all(header, suffix):
    print(f"{header}:")

    data = {}

    for library in libraries:
        print(f"  {library}:")

        data[library] = measure(f"{library}{suffix}")

    print_table(header, data)


def main():
    measure_all("sync -> async, single-threaded", "_single")
    print()
    measure_all("sync -> async, multi-threaded", "")


if __name__ == "__main__":
    sys.exit(main())
