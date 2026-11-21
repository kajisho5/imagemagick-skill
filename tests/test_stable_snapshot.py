"""The 1.0 compatibility promise (docs/decisions.md ADR-001; roadmap RM-074): a STABLE tool keeps every argument name and
every required output key it had at 1.0.0, and gains no newly required argument, until a major release.

tests/stable_tools_snapshot.json was written from the 1.0.0 contract. Adding an optional argument or an output key needs
no change here. Removing or renaming one, or making an argument required, fails this test: that is a breaking change and
waits for a major release, after a DEPRECATED minor (README, "Compatibility promise (1.0)"). Promoting another tool to
STABLE adds its entry to the snapshot in the same pull request."""
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import _contract  # noqa: E402

SNAPSHOT = os.path.join(os.path.dirname(__file__), "stable_tools_snapshot.json")


class StableToolsSnapshotTest(unittest.TestCase):
    def setUp(self):
        with open(SNAPSHOT, encoding="utf-8") as f:
            self.snapshot = json.load(f)
        payload = _contract.build_contract_payload()
        self.tools = {t["name"]: t for t in payload["tools"]}
        self.stable = {p["tool_id"].split("/", 1)[1] for p in payload["provides"] if p["lifecycle"] == "STABLE"}

    def test_the_snapshot_covers_exactly_the_stable_tools(self):
        self.assertEqual(set(self.snapshot), self.stable)

    def test_no_stable_argument_or_output_key_is_gone_and_none_became_required(self):
        for name, want in sorted(self.snapshot.items()):
            tool = self.tools[name]
            inputs = set(tool["input_schema"]["properties"])
            required = set(tool["input_schema"]["required"])
            outputs = set(tool["output_schema"]["required"])
            with self.subTest(tool=name):
                self.assertEqual(set(want["inputs"]) - inputs, set(), "arguments removed or renamed")
                self.assertEqual(required - set(want["required_inputs"]), set(), "arguments that became required")
                self.assertEqual(set(want["output_keys"]) - outputs, set(), "required output keys removed or renamed")


if __name__ == "__main__":
    unittest.main()
