"""--timeout (RM-070): every tool declares it, a run that outlives it fails with code
"timeout" and exit 124, and nothing ImageMagick started is left running.

The hanging backend is a fake `magick` placed first on PATH: a shell script that starts
two background processes (standing in for delegates such as gs or ffmpeg, one of them
a grandchild), records every pid, begins writing the output file, then waits forever.
POSIX only - the Windows path (CREATE_NEW_PROCESS_GROUP + taskkill /T) is exercised by
the same code with a different kill call."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

import _common  # noqa: E402
import _contract  # noqa: E402
from fixtures import write_solid_png  # noqa: E402

FAKE_MAGICK = """#!/bin/sh
# Hangs like an ImageMagick stuck in a delegate. Every pid it starts is recorded.
echo $$ >> "$IMSKILL_TEST_PIDS"
sleep 300 &
echo $! >> "$IMSKILL_TEST_PIDS"
sh -c 'sleep 300 & echo $! >> "$IMSKILL_TEST_PIDS"; wait' &
echo $! >> "$IMSKILL_TEST_PIDS"
for last in "$@"; do :; done
case "$last" in *.png|*.jpg|*.webp) printf 'partial' > "$last" ;; esac
wait
"""


def alive(pid):
    """True while pid is a live, non-zombie process (an orphan may linger as a zombie
    until init reaps it; it is not running)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        pass
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


@unittest.skipIf(os.name == "nt", "the fake magick is a POSIX shell script")
class HungBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bindir = os.path.join(self.tmp.name, "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "magick")
        with open(fake, "w") as f:
            f.write(FAKE_MAGICK)
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.pidfile = os.path.join(self.tmp.name, "pids")
        open(self.pidfile, "w").close()
        self.env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""),
                        IMSKILL_TEST_PIDS=self.pidfile)
        self.src = os.path.join(self.tmp.name, "in.png")
        write_solid_png(self.src, 8, 8)
        self.addCleanup(self.kill_leftovers)

    def pids(self):
        with open(self.pidfile) as f:
            return [int(line) for line in f.read().split()]

    def kill_leftovers(self):
        for pid in self.pids():
            try:
                os.kill(pid, 9)
            except OSError:
                pass

    def assert_nothing_left(self):
        pids = self.pids()
        self.assertGreaterEqual(len(pids), 4, "the fake magick did not start its children")
        end = time.monotonic() + 5
        while time.monotonic() < end and any(alive(p) for p in pids):
            time.sleep(0.05)
        self.assertEqual([p for p in pids if alive(p)], [], "processes outlived the timeout")

    def tool(self, script, *argv):
        start = time.monotonic()
        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(argv),
                              capture_output=True, text=True, env=self.env, timeout=60)
        return proc, time.monotonic() - start

    def test_timed_out_run_fails_with_the_timeout_code_and_leaves_no_child(self):
        out = os.path.join(self.tmp.name, "out.png")
        proc, took = self.tool("convert.py", self.src, "-o", out, "--timeout", "1", "--json")
        self.assertEqual(proc.returncode, _common.TIMEOUT_EXIT_CODE, proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 124)
        payload = json.loads(proc.stdout)
        shape = _contract.build_contract_payload()["result_shapes"]["timeout"]
        self.assertEqual(set(payload), set(shape))
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["code"], "timeout")
        self.assertEqual(payload["timeout"], 1)
        self.assertIn("timed out after 1 s", payload["reason"])
        self.assertLess(took, 30)
        self.assert_nothing_left()
        self.assertFalse(os.path.exists(out), "the half-written output was left behind")

    def test_text_mode_exits_124_too(self):
        proc, _ = self.tool("probe.py", self.src, "--timeout", "0.5")
        self.assertEqual(proc.returncode, 124)
        self.assertIn("timed out", proc.stderr)
        self.assert_nothing_left()

    def test_batch_records_the_timeout_per_file_and_kills_each_run(self):
        in_dir = os.path.join(self.tmp.name, "in")
        os.makedirs(in_dir)
        for name in ("a.png", "b.png"):
            write_solid_png(os.path.join(in_dir, name), 8, 8)
        proc, _ = self.tool("batch.py", "convert", "-i", in_dir, "-o", os.path.join(self.tmp.name, "out"),
                            "--ext", "jpg", "--timeout", "0.5", "--json")
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["all_ok"])
        self.assertEqual([r["code"] for r in payload["results"]], ["timeout", "timeout"])
        self.assertEqual([r["timeout"] for r in payload["results"]], [0.5, 0.5])
        self.assert_nothing_left()

    def test_mcp_call_reports_the_timeout(self):
        out = os.path.join(self.tmp.name, "mcp.png")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "mcp", "server.py"), "--call", "convert",
             json.dumps({"input": self.src, "output": out, "timeout": 1})],
            capture_output=True, text=True, env=self.env, timeout=60,
        )
        self.assertIn('"code": "timeout"', proc.stdout)
        self.assert_nothing_left()


class TimeoutContractTests(unittest.TestCase):
    def test_every_tool_declares_timeout(self):
        payload = _contract.build_contract_payload()
        for tool in payload["tools"]:
            with self.subTest(tool=tool["name"]):
                prop = tool["input_schema"]["properties"]["timeout"]
                self.assertEqual(prop["type"], "number")
                self.assertEqual(prop["default"], _common.DEFAULT_TIMEOUT)
                self.assertEqual(prop["cli"], ["--timeout"])
                self.assertNotIn("timeout", tool["input_schema"]["required"])
                self.assertIn("timeout", _contract.mcp_tool(tool)["inputSchema"]["properties"])
        self.assertEqual(payload["result_shapes"]["timeout"]["code"]["enum"], ["timeout"])

    def test_timeout_must_be_a_positive_number(self):
        for bad in ("0", "-1", "abc", "nan", "inf"):
            with self.subTest(value=bad):
                proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "probe.py"), "x.png",
                                       "--timeout", bad, "--json"], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 1)
                self.assertNotIn("code", json.loads(proc.stdout))

    def test_nested_budget_never_extends_the_outer_one(self):
        with _common.deadline(1):
            outer = _common._DEADLINE
            with _common.deadline(100):
                self.assertEqual(_common._DEADLINE, outer)
            with _common.deadline(0.5):
                self.assertEqual(_common._DEADLINE[1], 0.5)
            self.assertEqual(_common._DEADLINE, outer)
        self.assertIsNone(_common._DEADLINE)

    def test_a_spent_budget_starts_nothing(self):
        with _common.deadline(0.001):
            time.sleep(0.01)
            with self.assertRaises(_common.ImageSkillTimeout):
                _common.run_process([sys.executable, "-c", "raise SystemExit(3)"])

    def test_a_fast_command_is_unaffected(self):
        with _common.deadline(30):
            code, out, _ = _common.run_process([sys.executable, "-c", "print('hi')"])
        self.assertEqual((code, out.strip()), (0, "hi"))


if __name__ == "__main__":
    unittest.main()
