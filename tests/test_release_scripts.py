"""The release automation's decision logic (.github/scripts), exercised without GitHub:
label -> version rules, the doc bump helpers, and auto_bump.py end to end inside a
throwaway git repository (never this checkout)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RELEASE_SCRIPTS = os.path.join(ROOT, ".github", "scripts")
sys.path.insert(0, RELEASE_SCRIPTS)

from bump_contract_md import bump_contract_md  # noqa: E402
from bump_roadmap_md import bump_roadmap_md  # noqa: E402
from resolve_version import MajorRefused, bump_for_labels, resolve  # noqa: E402

GIT = shutil.which("git")


class ResolveVersionTests(unittest.TestCase):
    def labels(self, mapping):
        return lambda n: mapping[n]

    def test_label_rules(self):
        self.assertEqual(bump_for_labels(["feature", "docs"]), "minor")
        self.assertEqual(bump_for_labels(["fix", "test"]), "patch")
        self.assertEqual(bump_for_labels(["chore", "fix"]), "patch")
        self.assertEqual(bump_for_labels([]), "patch")
        self.assertIsNone(bump_for_labels(["chore", "ci", "docs"]))
        self.assertIsNone(bump_for_labels(["dependencies", "major"]))
        self.assertEqual(bump_for_labels(["breaking"]), "major")

    def test_minor_wins_over_patch(self):
        v, _ = resolve("0.3.0", ["feat: a (#5)", "fix: b (#6)"], self.labels({5: ["feature"], 6: ["fix"]}))
        self.assertEqual(v, "0.4.0")

    def test_patch_only(self):
        v, _ = resolve("0.3.0", ["fix: b (#6)"], self.labels({6: ["fix"]}))
        self.assertEqual(v, "0.3.1")

    def test_nothing_releasable(self):
        v, decisions = resolve(
            "0.3.0",
            ["chore: tidy (#7)", "build(deps): bump x (#8)", "chore(release): bump version to 0.3.0 [skip ci]"],
            self.labels({7: ["chore", "ci"], 8: ["dependencies", "major"]}),
        )
        self.assertIsNone(v)
        self.assertEqual([d["bump"] for d in decisions], [None, None, None])

    def test_direct_commit_without_pr_is_patch_unless_housekeeping(self):
        self.assertEqual(resolve("0.3.0", ["hotfix typo"], self.labels({}))[0], "0.3.1")
        self.assertIsNone(resolve("0.3.0", ["docs: typo"], self.labels({}))[0])

    def test_major_is_refused(self):
        with self.assertRaises(MajorRefused):
            resolve("0.3.0", ["feat!: x (#9)"], self.labels({9: ["major"]}))


class DocBumpTests(unittest.TestCase):
    def test_contract_md_moves_only_the_two_anchors(self):
        text = ('the npm / package.json version (`0.3.0`)\n"added in 0.3.0"\n'
                '"skill": {"id": "imagemagick-skill", "version": "0.3.0", ...')
        out = bump_contract_md(text, "0.3.0", "0.4.0")
        self.assertIn("(`0.4.0`)", out)
        self.assertIn('"version": "0.4.0"', out)
        self.assertIn('"added in 0.3.0"', out)

    def test_contract_md_anchor_must_exist_once(self):
        with self.assertRaises(ValueError):
            bump_contract_md("nothing here", "0.3.0", "0.4.0")

    def test_roadmap_rows_merged_since_the_last_release_get_the_new_version(self):
        text = ("The released version today is **0.6.2**.\n"
                "| RM-047 | done | 0.6.1 | a |\n| RM-048 | done | main | b |\n| RM-049 | planned | | c |\n")
        out = bump_roadmap_md(text, "0.6.2", "0.7.0")
        self.assertIn("| RM-048 | done | 0.7.0 | b |", out)
        self.assertIn("| RM-047 | done | 0.6.1 | a |", out)
        self.assertIn("| RM-049 | planned | | c |", out)

    def test_roadmap_keeps_prose_attached_to_its_version(self):
        text = "The released version today is **0.4.0** — look.py and compare.py.\n"
        once = bump_roadmap_md(text, "0.4.0", "0.4.1")
        self.assertIn("**0.4.1** (notes in CHANGELOG.md); **0.4.0** — look.py", once)
        twice = bump_roadmap_md(once, "0.4.1", "0.4.2")
        self.assertIn("**0.4.2** (notes in CHANGELOG.md); **0.4.0** — look.py", twice)


@unittest.skipUnless(GIT, "requires git")
def _root_file(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class AutoBumpInFixtureRepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "fixture")
        self.assertNotEqual(os.path.realpath(self.repo), os.path.realpath(ROOT))
        os.makedirs(os.path.join(self.repo, ".claude-plugin"))
        os.makedirs(os.path.join(self.repo, "docs"))
        for rel in ("package.json", ".claude-plugin/plugin.json", "skill.contract.json", "docs/contract.md", "docs/roadmap.md", "CHANGELOG.md"):
            shutil.copy(os.path.join(ROOT, rel), os.path.join(self.repo, rel))
        with open(os.path.join(ROOT, "package.json")) as f:
            self.old = json.load(f)["version"]
        major, minor, _ = self.old.split(".")
        self.new = f"{major}.{int(minor) + 1}.0"
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("tag", f"v{self.old}")
        self.git("commit", "-q", "--allow-empty", "-m", "feat: add look.py (#20)", "-m", "Closes #3")
        self.git("commit", "-q", "--allow-empty", "-m", "fix: `$(touch pwned)` title (#21)")

    def git(self, *args):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        subprocess.run([GIT, *args], cwd=self.repo, check=True, capture_output=True, env=env)

    def run_bump(self, new):
        env = dict(os.environ, OLD_VERSION=self.old, NEW_VERSION=new)
        return subprocess.run([sys.executable, os.path.join(RELEASE_SCRIPTS, "auto_bump.py")],
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def read(self, rel):
        with open(os.path.join(self.repo, rel), encoding="utf-8") as f:
            return f.read()

    def test_bump_moves_every_version_and_writes_changelog(self):
        proc = self.run_bump(self.new)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(self.read("package.json"))["version"], self.new)
        self.assertEqual(json.loads(self.read(".claude-plugin/plugin.json"))["version"], self.new)
        skillpact = json.loads(self.read("skill.contract.json"))
        self.assertEqual(skillpact["skill"]["version"], self.new)
        before = json.loads(_root_file("skill.contract.json"))
        before["skill"]["version"] = self.new
        self.assertEqual(skillpact, before)   # requirement ranges and everything else untouched
        self.assertIn(f"(`{self.new}`)", self.read("docs/contract.md"))
        self.assertIn(f"The released version today is **{self.new}**", self.read("docs/roadmap.md"))
        changelog = self.read("CHANGELOG.md")
        self.assertTrue(changelog.index("## Unreleased") < changelog.index(f"## {self.new}"))
        self.assertIn("- feat: add look.py (#20)", changelog)
        self.assertIn("Closes: #3", changelog)
        self.assertIn("- fix: `$(touch pwned)` title (#21)", changelog)
        self.assertFalse(os.path.exists(os.path.join(self.repo, "pwned")))

    def test_major_crossing_is_refused_and_writes_nothing(self):
        before = self.read("package.json")
        proc = self.run_bump(f"{int(self.old.split('.')[0]) + 1}.0.0")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("major boundary", proc.stderr)
        self.assertEqual(self.read("package.json"), before)


if __name__ == "__main__":
    unittest.main()
