import subprocess
import sys
import time


def main() -> int:
    if "--" not in sys.argv:
        print("Usage: launch_step.py <label> -- <command> [args...]")
        return 2

    sep = sys.argv.index("--")
    label = " ".join(sys.argv[1:sep]).strip()
    command = sys.argv[sep + 1 :]
    if not command:
        print("No command provided.")
        return 2

    if label:
        print(label, flush=True)
    print("Command: " + " ".join(command), flush=True)
    print("Progress: running. Long downloads or wheel builds can take several minutes.", flush=True)

    started = time.monotonic()
    try:
        proc = subprocess.Popen(command)
        while True:
            try:
                returncode = proc.wait(timeout=15)
                break
            except subprocess.TimeoutExpired:
                elapsed = int(time.monotonic() - started)
                print(f"Progress: still working after {elapsed}s...", flush=True)
    except KeyboardInterrupt:
        print("Interrupted. Terminating child process...", flush=True)
        try:
            proc.terminate()
        except Exception:
            pass
        return 130

    elapsed = int(time.monotonic() - started)
    if returncode == 0:
        print(f"Progress: completed in {elapsed}s.", flush=True)
    else:
        print(f"Progress: failed after {elapsed}s with exit code {returncode}.", flush=True)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
