import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

IMAGE = "csv-sandbox"
PROJECT = Path(__file__).parent.resolve()
DATA_FILE = PROJECT / "data" / "transactions_train.csv"
TEST_FILE = PROJECT / "data" / "transactions_test.csv"
OUTPUT_DIR = PROJECT / "output"
LOG_FILE = PROJECT / "logs" / "runs.jsonl"

DEFAULT_TIMEOUT = 60
MAX_CHARS = 5000

SECRET_PATTERNS = [
    r"gsk_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"ghp_[A-Za-z0-9]{20,}",
]


def redact(text: str) -> str:
    """Second layer: hide anything that looks like a key."""
    for pattern in SECRET_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text)
    key = os.getenv("GROQ_API_KEY")
    if key:
        text = text.replace(key, "[REDACTED]")
    return text


def _drain(stream, buf):
    """Read output but keep only MAX_CHARS bytes, so a print loop cannot fill the host memory."""
    kept = 0
    truncated = False
    for chunk in iter(lambda: stream.read(4096), b""):
        room = MAX_CHARS - kept
        if room > 0:
            buf.append(chunk[:room])
            kept += min(room, len(chunk))
        if len(chunk) > room and not truncated:
            buf.append(b"\n[output truncated]")
            truncated = True


def _docker_cmd(name: str) -> list[str]:
    return [
        "docker", "run", "--rm", "-i", "--name", name,
        "--network", "none",                              # no internet
        "--read-only", "--tmpfs", "/tmp:rw,size=64m",     # read only filesystem
        "--memory", "2g", "--memory-swap", "2g",          # memory cap
        "--cpus", "2", "--pids-limit", "100",             # cpu and process caps
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", f"{os.getuid()}:{os.getgid()}",         # not root
        "-v", f"{DATA_FILE}:/data/transactions_train.csv:ro",
        "-v", f"{TEST_FILE}:/data/transactions_test.csv:ro",
        "-v", f"{OUTPUT_DIR}:/output",                    # the only writable place
        "-w", "/output",
        IMAGE, "python", "-",
    ]


def _log(code: str, result: dict) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    entry = {"time": datetime.now(timezone.utc).isoformat(), "code": redact(code), **result}
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def run_in_sandbox(code: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run Python code in a fresh container, then destroy it."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    name = f"sbx-{uuid.uuid4().hex[:8]}"
    start = time.time()

    proc = subprocess.Popen(
        _docker_cmd(name),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    out, err = [], []
    readers = [
        threading.Thread(target=_drain, args=(proc.stdout, out), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True),
    ]
    for r in readers:
        r.start()

    timed_out = False
    try:
        try:
            proc.stdin.write(code.encode())
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["docker", "kill", name], capture_output=True)  # kills the container itself
        proc.kill()

    for r in readers:
        r.join(timeout=5)

    exit_code = proc.poll()
    error = None
    if timed_out:
        error = f"Timed out after {timeout}s. Container killed."
    elif exit_code == 137:
        error = "Killed by the sandbox, probably the memory limit."

    result = {
        "ok": (not timed_out) and exit_code == 0,
        "exit_code": exit_code,
        "stdout": redact(b"".join(out).decode(errors="replace")),
        "stderr": redact(b"".join(err).decode(errors="replace")),
        "error": error,
        "seconds": round(time.time() - start, 1),
    }
    _log(code, result)
    return result