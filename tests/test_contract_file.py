"""contract/contract.json is the committed copy of the contract; it must match what the code prints."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CommittedContractFileTest(unittest.TestCase):
    def test_contract_file_is_up_to_date(self):
        result = subprocess.run([sys.executable, str(ROOT / "contract" / "generate.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_output_is_byte_identical_to_the_committed_file(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "_contract.py"), "contract", "--json"],
                             capture_output=True, check=True, cwd=str(ROOT)).stdout.replace(b"\r\n", b"\n")
        self.assertEqual(out, (ROOT / "contract" / "contract.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
