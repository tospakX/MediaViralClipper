"""Safe subprocess wrappers: every command is an argv sequence, never a shell string."""

import subprocess
from collections.abc import Sequence


class CommandError(RuntimeError):
    def __init__(self, arguments: Sequence[str], returncode: int, stderr: str) -> None:
        self.arguments = tuple(arguments)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"command failed ({returncode}): {arguments[0]}: {stderr.strip()}")


def run_command(arguments: list[str]) -> str:
    completed = subprocess.run(arguments, check=False, capture_output=True, text=True)
    if completed.returncode:
        raise CommandError(arguments, completed.returncode, completed.stderr)
    return completed.stdout


def run_binary(arguments: list[str]) -> bytes:
    completed = subprocess.run(arguments, check=False, capture_output=True)
    if completed.returncode:
        raise CommandError(
            arguments, completed.returncode, completed.stderr.decode("utf-8", errors="replace")
        )
    return completed.stdout


def run_streaming(arguments: list[str]) -> None:
    completed = subprocess.run(arguments, check=False)
    if completed.returncode:
        raise CommandError(arguments, completed.returncode, "see FFmpeg output above")
