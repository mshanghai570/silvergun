"""Explicit Binary Ninja host-thread execution boundary."""
from __future__ import annotations
from typing import Any, Callable

try:
    from binaryninja.mainthread import execute_on_main_thread_and_wait, is_main_thread
except ImportError:  # pragma: no cover - test environments without Binary Ninja
    def is_main_thread() -> bool:
        return False
    def execute_on_main_thread_and_wait(callback):
        return callback()


def on_binary_ninja_thread(callback: Callable[[], Any]) -> Any:
    """Run callback in BN's required execution context; never sleep or poll."""
    if is_main_thread():
        return callback()
    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def invoke() -> None:
        try:
            result["value"] = callback()
        except BaseException as exc:  # propagate the host failure to the caller
            error.append(exc)

    execute_on_main_thread_and_wait(invoke)
    if error:
        raise error[0]
    return result.get("value")


def require_binary_view(bv):
    if bv is None:
        raise ValueError("No active BinaryView is available")
    return bv
