"""bin/install.js end to end, in a throwaway HOME: the new install targets, and the
migration away from the old "image-skill" name. A legacy directory is removed only
when it is provably this project's; anything else (the unrelated npm package that
owns the "image-skill" name, a user's own files) must survive, with a warning."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTALL_JS = os.path.join(ROOT, "bin", "install.js")
NODE = shutil.which("node")


def make_legacy_install(path, with_package_json=True, repo="https://github.com/kajisho5/image-skill"):
    """Recreate the layout 0.1.x (no package.json) and 0.2.x (with one) installed."""
    os.makedirs(os.path.join(path, "scripts", "__pycache__"))
    with open(os.path.join(path, "SKILL.md"), "w") as f:
        f.write("---\nname: image-skill\ndescription: Local image editing\n---\n\n# image-skill\n")
    with open(os.path.join(path, "scripts", "_contract.py"), "w") as f:
        f.write('parser = JSONArgumentParser(description="image-skill contract/doctor")\n')
    with open(os.path.join(path, "scripts", "probe.py"), "w") as f:
        f.write("print('probe')\n")
    if with_package_json:
        with open(os.path.join(path, "package.json"), "w") as f:
            json.dump({"name": "image-skill", "version": "0.2.2", "repository": {"url": repo}}, f)


def make_foreign_install(path):
    """What a different package owning the npm name "image-skill" might leave behind."""
    os.makedirs(os.path.join(path, "references"))
    with open(os.path.join(path, "SKILL.md"), "w") as f:
        f.write("---\nname: image-skill\ndescription: someone else's skill\n---\n")
    with open(os.path.join(path, "references", "api.md"), "w") as f:
        f.write("not ours\n")


@unittest.skipUnless(NODE, "requires node")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        self.cwd = os.path.join(self.tmp.name, "project")
        os.makedirs(self.home)
        os.makedirs(self.cwd)

    def install(self, *flags):
        env = dict(os.environ, HOME=self.home, USERPROFILE=self.home)
        return subprocess.run(
            [NODE, INSTALL_JS, *flags], cwd=self.cwd, env=env, capture_output=True, text=True, timeout=60
        )

    def home_path(self, *parts):
        return os.path.join(self.home, *parts)

    def test_contract_and_doctor_reach_python(self):
        # `npx imagemagick-skill contract|doctor` hands over to scripts/_contract.py
        # through a spawned Python; this runs that hand-off on every CI platform.
        r = self.install("contract", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("probe", {t["name"] for t in json.loads(r.stdout)["tools"]})
        r = self.install("doctor", "--json")
        self.assertIn("backends", json.loads(r.stdout), r.stderr)

    def test_default_install_uses_the_new_name(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        skill_md = self.home_path(".claude", "skills", "imagemagick-skill", "SKILL.md")
        with open(skill_md) as f:
            self.assertIn("name: imagemagick-skill", f.read())
        self.assertTrue(os.path.isfile(self.home_path(".claude", "skills", "imagemagick-skill", "scripts", "_contract.py")))
        self.assertTrue(os.path.isfile(self.home_path(".claude", "skills", "imagemagick-skill", "mcp", "server.py")))

    def test_codex_installs_where_codex_reads_user_skills(self):
        r = self.install("--codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(self.home_path(".agents", "skills", "imagemagick-skill", "SKILL.md")))
        self.assertFalse(os.path.exists(self.home_path(".codex", "skills", "imagemagick-skill")))

    def test_own_legacy_install_is_removed(self):
        for variant in ("0.2.x", "0.1.x"):
            with self.subTest(variant=variant):
                legacy = self.home_path(".claude", "skills", "image-skill")
                make_legacy_install(legacy, with_package_json=(variant == "0.2.x"))
                r = self.install()
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertFalse(os.path.exists(legacy), r.stdout + r.stderr)
                self.assertIn("removed old image-skill install", r.stdout)

    def test_legacy_codex_location_is_cleaned_up(self):
        legacy = self.home_path(".codex", "skills", "image-skill")
        make_legacy_install(legacy)
        r = self.install("--codex")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(legacy))

    def test_foreign_image_skill_is_left_alone_with_a_warning(self):
        legacy = self.home_path(".claude", "skills", "image-skill")
        make_foreign_install(legacy)
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(legacy, "references", "api.md")))
        self.assertIn("left", r.stderr)
        self.assertIn(legacy, r.stderr)

    def test_own_layout_with_extra_user_file_is_left_alone(self):
        legacy = self.home_path(".claude", "skills", "image-skill")
        make_legacy_install(legacy)
        with open(os.path.join(legacy, "my-notes.md"), "w") as f:
            f.write("mine\n")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(legacy, "my-notes.md")))
        self.assertIn("my-notes.md", r.stderr)

    def test_package_json_from_another_repo_is_left_alone(self):
        legacy = self.home_path(".claude", "skills", "image-skill")
        make_legacy_install(legacy, repo="https://github.com/someone-else/image-skill")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isdir(legacy))

    @unittest.skipIf(os.name == "nt", "symlinks need privileges on Windows")
    def test_symlinked_legacy_dir_is_left_alone(self):
        real = os.path.join(self.tmp.name, "real-image-skill")
        make_legacy_install(real)
        link = self.home_path(".claude", "skills", "image-skill")
        os.makedirs(os.path.dirname(link))
        os.symlink(real, link)
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.isfile(os.path.join(real, "SKILL.md")))

    def test_uninstall_removes_new_and_own_legacy_but_keeps_foreign(self):
        self.assertEqual(self.install("--all").returncode, 0)
        own = self.home_path(".cursor", "skills", "image-skill")
        make_legacy_install(own)
        foreign = self.home_path(".claude", "skills", "image-skill")
        make_foreign_install(foreign)

        r = self.install("--all", "--uninstall")
        self.assertEqual(r.returncode, 0, r.stderr)
        for agent_dir in ((".claude", "skills"), (".cursor", "skills"), (".agents", "skills")):
            self.assertFalse(os.path.exists(self.home_path(*agent_dir, "imagemagick-skill")))
        self.assertFalse(os.path.exists(own))
        self.assertTrue(os.path.isfile(os.path.join(foreign, "SKILL.md")))

    def test_uninstall_of_only_a_legacy_copy(self):
        legacy = self.home_path(".claude", "skills", "image-skill")
        make_legacy_install(legacy)
        r = self.install("--uninstall")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(legacy))
        self.assertNotIn("no imagemagick-skill install found", r.stdout)

    def test_dir_and_project_targets_migrate_their_own_sibling(self):
        parent = os.path.join(self.tmp.name, "custom")
        make_legacy_install(os.path.join(parent, "image-skill"))
        r = self.install("--dir", parent)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(parent, "imagemagick-skill", "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(parent, "image-skill")))

        project_legacy = os.path.join(self.cwd, ".claude", "skills", "image-skill")
        make_legacy_install(project_legacy, with_package_json=False)
        r = self.install("--project")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.cwd, ".claude", "skills", "imagemagick-skill", "SKILL.md")))
        self.assertFalse(os.path.exists(project_legacy))



NPM = shutil.which("npm")  # npm.cmd on Windows, which CreateProcess finds only by its full name


@unittest.skipUnless(NPM, "requires npm")
class PackageContentsTests(unittest.TestCase):
    def test_tarball_ships_sources_only(self):
        with tempfile.TemporaryDirectory() as cache:
            proc = subprocess.run(
                [NPM, "pack", "--dry-run", "--json", "--cache", cache],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        files = {f["path"] for f in json.loads(proc.stdout)[0]["files"]}
        self.assertFalse([f for f in files if f.endswith(".pyc") or "__pycache__" in f])
        for required in ("bin/install.js", "SKILL.md", "package.json", "scripts/_contract.py", "scripts/_common.py",
                         "scripts/presets.json", "mcp/server.py"):
            self.assertIn(required, files)


if __name__ == "__main__":
    unittest.main()
