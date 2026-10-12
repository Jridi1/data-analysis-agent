import os
import time

from sandbox_runner import DATA_FILE, OUTPUT_DIR, run_in_sandbox

# A fake secret in the host environment. If it ever shows up in the sandbox, isolation failed.
os.environ["CANARY_SECRET"] = "canary-7f3a9c-do-not-leak"


def test_normal_work():
    r = run_in_sandbox(
        "import pandas as pd\n"
        "df = pd.read_csv('/data/transactions_train.csv')\n"
        "print(df.shape)"
    )
    assert r["ok"], r
    assert "(300113, 21)" in r["stdout"]


def test_cannot_see_host_secrets():
    r = run_in_sandbox("import os\nprint(dict(os.environ))")
    assert "canary-7f3a9c" not in r["stdout"]
    assert "GROQ_API_KEY" not in r["stdout"]


def test_cannot_see_host_files():
    r = run_in_sandbox("import os\nprint(os.path.exists('/mnt/c'), os.path.exists('/home/jridi'))")
    assert "True" not in r["stdout"]


def test_cannot_write_to_data():
    r = run_in_sandbox("open('/data/pwned.txt', 'w').write('x')")
    assert not r["ok"]
    assert not (DATA_FILE.parent / "pwned.txt").exists()


def test_can_write_to_output():
    r = run_in_sandbox("open('/output/ok.txt', 'w').write('hello')")
    assert r["ok"], r
    f = OUTPUT_DIR / "ok.txt"
    assert f.read_text() == "hello"
    f.unlink()


def test_no_network():
    r = run_in_sandbox(
        "import urllib.request\n"
        "urllib.request.urlopen('https://example.com', timeout=5)"
    )
    assert not r["ok"]


def test_infinite_loop_is_killed():
    start = time.time()
    r = run_in_sandbox("while True:\n    pass", timeout=5)
    assert not r["ok"]
    assert "Timed out" in r["error"]
    assert time.time() - start < 20


def test_output_flood_is_capped():
    r = run_in_sandbox("while True:\n    print('x' * 1000)", timeout=5)
    assert len(r["stdout"]) < 6000


def test_memory_bomb_is_killed():
    r = run_in_sandbox("data = b'x' * (3 * 1024**3)\nprint(len(data))")
    assert not r["ok"]


def test_process_limit():
    r = run_in_sandbox(
        "import subprocess\n"
        "procs = [subprocess.Popen(['sleep', '30']) for _ in range(500)]",
        timeout=20,
    )
    assert not r["ok"]


def test_secret_redaction():
    r = run_in_sandbox("print('gsk_' + 'A' * 40)")
    assert "gsk_AAAA" not in r["stdout"]
    assert "[REDACTED]" in r["stdout"]

def test_test_file_is_read_only():
    r = run_in_sandbox("open('/data/transactions_test.csv', 'r+')")
    assert not r["ok"]