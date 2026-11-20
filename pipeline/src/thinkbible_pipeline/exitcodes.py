"""Exit codes, exactly as in contracts/cli.md."""

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    USAGE = 1
    SOURCE_CHECKSUM = 2
    SECTIONS_FAILED = 3
    CAP_REACHED = 4
    GATE_REFUSED = 5
