"""brandkit.py: colour, mono, white, black and clear-space variants, sizes and palette."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import _contract  # noqa: E402
from _common import which_magick  # noqa: E402
from fixtures import write_rgba_png, write_solid_png  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "brandkit.py")
BLUE, GOLD, RED = (20, 60, 200), (230, 180, 20), (200, 30, 40)


def write_logo(path):
    """80x60, transparent background; a 60x40 mark: blue (30 columns), gold (20), red (10)."""
    def pixel(x, y):
        if 10 <= x < 70 and 10 <= y < 50:
            return (BLUE if x < 40 else GOLD if x < 60 else RED) + (255,)
        return (0, 0, 0, 0)

    write_rgba_png(path, 80, 60, pixel)


def rgba_at(path, x, y):
    out = subprocess.run([which_magick(), path, "-colorspace", "sRGB", "-format",
                          f"%[fx:int(255*p{{{x},{y}}}.r+0.5)] %[fx:int(255*p{{{x},{y}}}.g+0.5)] "
                          f"%[fx:int(255*p{{{x},{y}}}.b+0.5)] %[fx:int(255*p{{{x},{y}}}.a+0.5)]", "info:"],
                         capture_output=True, text=True, check=True).stdout
    return tuple(int(v) for v in out.split())


@unittest.skipUnless(which_magick(), "requires ImageMagick")
class BrandkitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logo = self.path("logo.png")
        write_logo(self.logo)

    def path(self, *names):
        return os.path.join(self.tmp.name, *names)

    def brandkit(self, *args):
        proc = subprocess.run([sys.executable, SCRIPT, *args, "--json"], capture_output=True, text=True, timeout=120)
        return proc.returncode, json.loads(proc.stdout)

    def test_every_variant_at_the_stated_sizes_and_a_palette_of_at_most_n(self):
        code, out = self.brandkit(self.logo, "-o", self.path("kit"), "--sizes", "40,20",
                                  "--clear-space", "5", "--palette", "2")
        self.assertEqual(code, 0, out)
        want = {}
        for variant in ("color", "mono", "white", "black"):
            want[(variant, 80)], want[(variant, 40)], want[(variant, 20)] = (80, 60), (40, 30), (20, 15)
        want[("clearspace", 90)], want[("clearspace", 40)], want[("clearspace", 20)] = (90, 70), (40, 31), (20, 16)
        got = {(f["variant"], f["long_edge"]): (f["width"], f["height"]) for f in out["files"]}
        self.assertEqual(got, want)
        for f in out["files"]:
            with self.subTest(file=os.path.basename(f["path"])):
                dims = subprocess.run([which_magick(), f["path"], "-format", "%w %h %m", "info:"],
                                      capture_output=True, text=True, check=True).stdout.split()
                self.assertEqual(dims, [str(f["width"]), str(f["height"]), "PNG"])

        # the two largest of the logo's three colours, as they are in the logo (never an average)
        self.assertEqual(out["palette"], [{"hex": "#143CC8", "share": 0.5}, {"hex": "#E6B414", "share": 0.3333}])
        self.assertEqual(out["palette_pixels"], 60 * 40)

        code, out = self.brandkit(self.logo, "-o", self.path("kit3"), "--sizes", "20",
                                  "--clear-space", "0", "--palette", "3")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["palette"], [{"hex": "#143CC8", "share": 0.5}, {"hex": "#E6B414", "share": 0.3333},
                                          {"hex": "#C81E28", "share": 0.1667}])

    def test_variants_have_the_right_pixels(self):
        code, out = self.brandkit(self.logo, "-o", self.path("kit"), "--sizes", "40",
                                  "--clear-space", "5", "--palette", "3")
        self.assertEqual(code, 0, out)
        kit = lambda name: self.path("kit", name)  # noqa: E731
        self.assertEqual(rgba_at(kit("logo-color.png"), 20, 20), BLUE + (255,))
        self.assertEqual(rgba_at(kit("logo-white.png"), 20, 20), (255, 255, 255, 255))
        self.assertEqual(rgba_at(kit("logo-black.png"), 50, 20), (0, 0, 0, 255))
        r, g, b, a = rgba_at(kit("logo-mono.png"), 50, 20)
        self.assertEqual((r, a), (g, 255))
        self.assertEqual(r, b)
        for name in ("logo-white.png", "logo-black.png", "logo-mono.png"):
            self.assertEqual(rgba_at(kit(name), 2, 2)[3], 0, name)  # the background stays transparent
        # clear space: the mark moves in by 5 px and the new margin is transparent
        self.assertEqual(rgba_at(kit("logo-clearspace.png"), 15, 15), BLUE + (255,))
        self.assertEqual(rgba_at(kit("logo-clearspace.png"), 2, 2)[3], 0)

    def test_brandkit_refusals(self):
        opaque = self.path("opaque.png")
        write_solid_png(opaque, 80, 60)
        base = ["--clear-space", "4", "--palette", "4"]
        cases = [
            ([opaque, "-o", self.path("a"), "--sizes", "40"] + base, "no alpha channel"),
            ([self.logo, "-o", self.path("b"), "--sizes", "160"] + base, "never upscaled"),
            ([self.logo, "-o", self.path("c"), "--sizes", "40,x"] + base, "comma-separated"),
            ([self.logo, "-o", self.path("d"), "--sizes", "40", "--clear-space", "4", "--palette", "1"], "between 2 and 32"),
            ([self.logo, "-o", self.path("e"), "--clear-space", "4", "--palette", "4"], "--sizes"),
        ]
        for args, needle in cases:
            with self.subTest(args=args[1:]):
                code, out = self.brandkit(*args)
                self.assertEqual(code, 1, out)
                self.assertIn(needle, out["reason"])
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["logo.png", "opaque.png"])

    def test_existing_files_are_refused_without_overwrite(self):
        args = [self.logo, "-o", self.path("kit"), "--sizes", "20", "--clear-space", "2", "--palette", "2"]
        self.assertEqual(self.brandkit(*args)[0], 0)
        code, out = self.brandkit(*args)
        self.assertEqual(code, 1, out)
        self.assertEqual(self.brandkit(*args, "--overwrite")[0], 0)

    def test_output_matches_the_schema_and_dry_run_writes_nothing(self):
        spec = _contract.tool_spec("brandkit")["output_schema"]
        args = [self.logo, "-o", self.path("kit"), "--sizes", "20", "--clear-space", "2", "--palette", "2"]
        code, out = self.brandkit(*args, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out["would_run"]), 10)
        self.assertFalse(os.path.exists(self.path("kit")))
        code, out = self.brandkit(*args)
        self.assertLessEqual(set(out), set(spec["properties"]) | {"ok"})
        self.assertLessEqual(set(spec["required"]), set(out))


if __name__ == "__main__":
    unittest.main()
