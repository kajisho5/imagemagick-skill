"""alpha.py: report, straight <-> premultiplied, defringe, key and fill."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import _contract  # noqa: E402
from _common import which_magick  # noqa: E402
from fixtures import fringed_disc_alpha, write_fringed_logo_png, write_solid_png  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "alpha.py")
SIZE, RGB = 40, (200, 20, 40)


def pixels(path, colorspace="sRGB"):
    """{(x, y): (channel values 0..255)} from a txt: dump, 8-bit."""
    out = subprocess.run([which_magick(), path, "-colorspace", colorspace, "-depth", "8", "txt:-"],
                         capture_output=True, text=True, check=True).stdout
    result = {}
    for line in out.splitlines():
        m = re.match(r"(\d+),(\d+):\s*\(([^)]*)\)", line)
        if m:
            values = [float(v.strip().rstrip("%")) for v in m.group(3).split(",")]
            result[(int(m.group(1)), int(m.group(2)))] = tuple(int(round(v)) for v in values)
    return result


def expected_alpha(x, y):
    return fringed_disc_alpha(x, y, SIZE / 2, SIZE / 2, SIZE / 2 - 4)


@unittest.skipUnless(which_magick(), "requires ImageMagick")
class AlphaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logo = self.path("logo.png")
        write_fringed_logo_png(self.logo, SIZE, RGB)
        self.opaque = self.path("opaque.png")
        write_solid_png(self.opaque, 20, 10)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def alpha(self, *args):
        proc = subprocess.run([sys.executable, SCRIPT, *args, "--json"], capture_output=True, text=True, timeout=120)
        return proc.returncode, json.loads(proc.stdout)

    def partial(self):
        return [(x, y) for x in range(SIZE) for y in range(SIZE) if 0 < expected_alpha(x, y) < 255]

    def test_report_tells_present_used_and_absent(self):
        code, out = self.alpha(self.logo, "--mode", "report")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["has_alpha"])
        self.assertTrue(out["alpha_used"])
        self.assertEqual(out["pixels"]["partial"], len(self.partial()))
        self.assertEqual(sum(out["pixels"].values()), SIZE * SIZE)
        self.assertEqual((out["alpha_min"], out["alpha_max"]), (0.0, 1.0))
        self.assertFalse(out["color_within_alpha"])  # a white-fringed straight image

        code, out = self.alpha(self.opaque, "--mode", "report")
        self.assertEqual(code, 0, out)
        self.assertFalse(out["has_alpha"])
        self.assertFalse(out["alpha_used"])
        self.assertEqual(out["pixels"], {"opaque": 200, "transparent": 0, "partial": 0})
        self.assertIsNone(out["color_within_alpha"])

    def test_defringe_removes_a_white_fringe(self):
        before = pixels(self.logo)
        fringed = [p for p in self.partial() if before[p][1] > RGB[1] + 30]
        self.assertTrue(fringed, "the fixture should carry a white fringe")
        out_path = self.path("clean.png")
        code, out = self.alpha(self.logo, "-o", out_path, "--mode", "defringe", "--matte", "white")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["alpha_max_difference"], 0.0)
        after = pixels(out_path)
        for p in self.partial():
            a = expected_alpha(*p)
            # one 8-bit rounding step in the fixture is amplified by 1/alpha
            tolerance = 2 + 255 / (2 * a)
            with self.subTest(pixel=p, alpha=a):
                self.assertEqual(after[p][3], a)
                for got, want in zip(after[p][:3], RGB):
                    self.assertLessEqual(abs(got - want), tolerance)

    def test_defringe_uses_the_supplied_matte(self):
        logo, out_path = self.path("blue-fringe.png"), self.path("clean.png")
        write_fringed_logo_png(logo, SIZE, RGB, matte=(0, 0, 255))
        code, out = self.alpha(logo, "-o", out_path, "--mode", "defringe", "--matte", "#0000FF")
        self.assertEqual(code, 0, out)
        after = pixels(out_path)
        for p in self.partial():
            tolerance = 2 + 255 / (2 * expected_alpha(*p))
            for got, want in zip(after[p][:3], RGB):
                self.assertLessEqual(abs(got - want), tolerance, p)

    def test_cmyk_input_is_worked_on_in_srgb(self):
        cmyk, out_path = self.path("logo.tif"), self.path("pre.png")
        subprocess.run([which_magick(), self.logo, "-colorspace", "CMYK", cmyk], check=True)
        code, out = self.alpha(cmyk, "-o", out_path, "--mode", "premultiply")
        self.assertEqual(code, 0, out)
        src, got = pixels(self.logo), pixels(out_path)
        for p in [(SIZE // 2, SIZE // 2)] + self.partial()[:20]:
            a = expected_alpha(*p) / 255
            for value, straight in zip(got[p][:3], src[p][:3]):
                self.assertLessEqual(abs(value - straight * a), 3, p)
        key = self.path("key.png")
        code, out = self.alpha(cmyk, "-o", key, "--mode", "key")
        self.assertEqual(code, 0, out)
        for (x, y), value in pixels(key, "gray").items():
            self.assertEqual(value[0], expected_alpha(x, y), (x, y))
        code, out = self.alpha(cmyk, "--mode", "report")
        self.assertEqual(out["pixels"]["partial"], len(self.partial()))

    def test_key_pixels_equal_the_alpha(self):
        out_path = self.path("key.png")
        code, out = self.alpha(self.logo, "-o", out_path, "--mode", "key")
        self.assertEqual(code, 0, out)
        self.assertFalse(out["has_alpha"])
        key = pixels(out_path, "gray")
        self.assertEqual(len(key), SIZE * SIZE)
        for (x, y), value in key.items():
            self.assertEqual(value[0], expected_alpha(x, y), (x, y))

    def test_fill_drops_alpha_and_keeps_colour(self):
        out_path = self.path("fill.png")
        code, out = self.alpha(self.logo, "-o", out_path, "--mode", "fill")
        self.assertEqual(code, 0, out)
        self.assertFalse(out["has_alpha"])
        self.assertEqual(pixels(out_path)[(SIZE // 2, SIZE // 2)][:3], RGB)

    def test_premultiply_then_unpremultiply_round_trips(self):
        pre, back = self.path("pre.png"), self.path("back.png")
        code, out = self.alpha(self.logo, "-o", pre, "--mode", "premultiply")
        self.assertEqual(code, 0, out)
        code, out = self.alpha(pre, "--mode", "report")
        self.assertTrue(out["color_within_alpha"])
        src, mid = pixels(self.logo), pixels(pre)
        for p in self.partial():
            a = expected_alpha(*p) / 255
            for got, straight in zip(mid[p][:3], src[p][:3]):
                self.assertLessEqual(abs(got - straight * a), 1, p)
        code, out = self.alpha(pre, "-o", back, "--mode", "unpremultiply")
        self.assertEqual(code, 0, out)
        end = pixels(back)
        for p in self.partial():
            # 8-bit premultiplied colour keeps only round(c*a) levels: one level back is 255/alpha
            tolerance = 1 + 255 / expected_alpha(*p)
            for got, want in zip(end[p][:3], src[p][:3]):
                self.assertLessEqual(abs(got - want), tolerance, p)

    def test_refusals(self):
        cases = [
            ([self.opaque, "-o", self.path("k.png"), "--mode", "key"], "no alpha channel"),
            ([self.logo, "-o", self.path("d.png"), "--mode", "defringe"], "needs --matte"),
            ([self.logo, "-o", self.path("d.png"), "--mode", "defringe", "--matte", "none"], "opaque"),
            ([self.logo, "-o", self.path("p.jpg"), "--mode", "premultiply"], "no alpha channel"),
            ([self.logo, "-o", self.path("k.png"), "--mode", "key", "--matte", "white"], "only applies"),
            ([self.logo, "-o", self.path("r.png"), "--mode", "report"], "writes nothing"),
            ([self.logo, "--mode", "key"], "give -o"),
            ([self.logo, "-o", self.logo, "--mode", "key"], ""),
        ]
        for args, needle in cases:
            with self.subTest(args=args[1:]):
                code, out = self.alpha(*args)
                self.assertEqual(code, 1, out)
                self.assertFalse(out["ok"])
                self.assertIn(needle, out["reason"])
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["logo.png", "opaque.png"])

    def test_every_mode_matches_the_output_schema(self):
        spec = _contract.tool_spec("alpha")["output_schema"]
        for mode in ("report", "premultiply", "unpremultiply", "defringe", "key", "fill"):
            with self.subTest(mode=mode):
                args = [self.logo, "--mode", mode]
                if mode != "report":
                    args += ["-o", self.path(f"{mode}.png")]
                if mode == "defringe":
                    args += ["--matte", "#FFFFFF"]
                code, out = self.alpha(*args)
                self.assertEqual(code, 0, out)
                self.assertLessEqual(set(out), set(spec["properties"]) | {"ok"})
                self.assertLessEqual(set(spec["required"]), set(out))

    def test_dry_run_writes_nothing(self):
        code, out = self.alpha(self.logo, "-o", self.path("k.png"), "--mode", "key", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["dry_run"])
        self.assertFalse(os.path.exists(self.path("k.png")))


if __name__ == "__main__":
    unittest.main()
