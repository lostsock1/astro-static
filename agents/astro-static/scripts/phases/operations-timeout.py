#!/usr/bin/env python3
"""Portable wall-clock timeout; kill the command's process group, not just its PID."""
import os
import signal
import subprocess
import sys
import time


def main():
    seconds = float(sys.argv[1])
    if seconds <= 0 or len(sys.argv) < 3:
        return 124
    child = None
    cancelling = False

    def signal_group(sig):
        if child is not None:
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                pass

    def cancel_group(grace):
        nonlocal cancelling
        cancelling = True
        deadline = time.monotonic() + grace
        signal_group(signal.SIGTERM)
        try:
            child.wait(timeout=grace) if child is not None else None
        except subprocess.TimeoutExpired:
            pass
        # The group leader can exit immediately while a nested supervisor is
        # still forwarding TERM and escalating in its separate command group.
        # Preserve the FULL grace, not merely the time needed to reap a shell.
        time.sleep(max(0, deadline - time.monotonic()))
        signal_group(signal.SIGKILL)
        if child is not None:
            child.wait()

    def interrupted(signum, _frame):
        if cancelling:
            return
        # Nested supervisors stay in their caller's group. Forward cancellation
        # to their own command group so an outer deadline cannot orphan work.
        cancel_group(0.5)
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, interrupted)
    child = subprocess.Popen(sys.argv[2:], start_new_session=True)
    try:
        code = child.wait(timeout=seconds)
        return code if code >= 0 else 128 - code
    except subprocess.TimeoutExpired:
        cancel_group(1)
        return 124


if __name__ == "__main__":
    sys.exit(main())
