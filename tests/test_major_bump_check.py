"""docs/decisions.md ADR-002: from 1.0.0, a contract:breaking pull request passes only with a hand major bump of
package.json (.github/scripts/major_bump_check.py), exercised without GitHub."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, ".github", "scripts"))

from major_bump_check import package_version, pr_verdict, release_blockers  # noqa: E402


class PullRequestCheckTests(unittest.TestCase):
    def test_breaking_without_a_major_bump_fails(self):
        for version in ("1.0.0", "1.1.0", "1.0.1"):
            ok, message = pr_verdict(["contract:breaking", "feature"], "v1.0.0", version)
            self.assertFalse(ok, version)
            self.assertIn("not a major release", message)

    def test_a_major_label_alone_does_not_pass(self):
        # resolve_version.py refuses `major`: only the hand bump makes a major release here
        ok, _ = pr_verdict(["contract:breaking", "major"], "v1.0.0", "1.0.0")
        self.assertFalse(ok)

    def test_breaking_with_a_major_bump_passes(self):
        ok, message = pr_verdict(["contract:breaking"], "v1.0.0", "2.0.0")
        self.assertTrue(ok)
        self.assertIn("2.0.0", message)
        self.assertTrue(pr_verdict(["Contract:Breaking"], "v2.3.1", "3.0.0")[0])

    def test_additive_and_none_pass(self):
        for labels in (["contract:additive", "feature"], ["contract:none", "fix"], ["chore"]):
            self.assertTrue(pr_verdict(labels, "v1.0.0", "1.0.0")[0], labels)

    def test_before_1_0_is_unaffected(self):
        for tag in ("v0.10.2", "", None):
            ok, message = pr_verdict(["contract:breaking"], tag, "0.10.2", need_contract_label=True)
            self.assertTrue(ok, tag)
            self.assertIn("before 1.0.0", message)
        self.assertTrue(pr_verdict([], "v0.10.2", "0.11.0", need_contract_label=True)[0])

    def test_unclassified_pull_request_fails_once_contract_diff_ran(self):
        self.assertFalse(pr_verdict(["fix"], "v1.0.0", "1.0.0", need_contract_label=True)[0])
        self.assertTrue(pr_verdict(["fix"], "v1.0.0", "1.0.0", need_contract_label=False)[0])

    def test_unreadable_version_fails_a_breaking_pull_request(self):
        self.assertFalse(pr_verdict(["contract:breaking"], "v1.0.0", None)[0])

    def test_reads_this_repository_package_json(self):
        self.assertRegex(package_version(), r"^\d+\.\d+\.\d+")


class ReleaseCheckTests(unittest.TestCase):
    PULLS = [("fix: a (#60)", ["fix", "contract:none"]), ("feat!: drop a flag (#61)", ["feature", "contract:breaking"])]

    def test_auto_release_with_a_merged_breaking_pull_request_stops(self):
        blockers = release_blockers("v1.0.0", "1.0.0", self.PULLS)
        self.assertEqual(len(blockers), 1)
        self.assertIn("#61", blockers[0])

    def test_hand_bumped_minor_still_stops(self):
        self.assertTrue(release_blockers("v1.0.0", "1.1.0", self.PULLS))

    def test_hand_bumped_major_goes(self):
        self.assertEqual(release_blockers("v1.0.0", "2.0.0", self.PULLS), [])

    def test_additive_and_none_go(self):
        self.assertEqual(release_blockers("v1.0.0", "1.0.0", self.PULLS[:1] + [("feat: b (#62)", ["contract:additive"])]),
                         [])

    def test_before_1_0_is_unaffected(self):
        self.assertEqual(release_blockers("v0.10.2", "0.10.2", self.PULLS), [])


class WorkflowWiringTests(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8") as fh:
            return fh.read()

    def test_check_reruns_on_label_changes(self):
        text = self.read("major-bump-check.yml")
        self.assertIn("types: [opened, synchronize, reopened, labeled, unlabeled]", text)
        self.assertIn("major_bump_check.py --check-pr", text)

    def test_release_checks_before_bumping_or_tagging(self):
        text = self.read("release.yml")
        gate = text.index("major_bump_check.py --release")
        self.assertLess(gate, text.index("python3 .github/scripts/resolve_version.py"))
        self.assertLess(gate, text.index("gh release create"))


if __name__ == "__main__":
    unittest.main()
