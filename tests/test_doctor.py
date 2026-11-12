import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import _contract  # noqa: E402


class TestDoctorNoBackend(unittest.TestCase):
    def test_doctor_reports_not_ok_when_no_backend_found(self):
        with mock.patch.object(_contract, "which_magick", return_value=None), mock.patch.object(
            _contract, "which_sips", return_value=None
        ):
            payload = _contract.build_doctor_payload()

        self.assertFalse(payload["ok"])
        self.assertIn("reason", payload)
        for tool in _contract.TOOL_META:
            self.assertFalse(payload["tools"][tool]["usable"], f"{tool} should be unusable with no backend")
        self.assertFalse(payload["heic"]["usable"])
        self.assertFalse(payload["webp"]["usable"])

    def test_doctor_sips_only_marks_strip_and_trim_unusable(self):
        with mock.patch.object(_contract, "which_magick", return_value=None), mock.patch.object(
            _contract, "which_sips", return_value="/usr/bin/sips"
        ), mock.patch.object(_contract.sys, "platform", "darwin"):
            payload = _contract.build_doctor_payload()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["tools"]["convert"]["usable"])
        self.assertEqual(payload["tools"]["convert"]["backend"], "sips")
        self.assertFalse(payload["tools"]["strip"]["usable"])
        self.assertFalse(payload["tools"]["trim"]["usable"])
        self.assertFalse(payload["webp"]["usable"])


FORMATS_HEIC_RW = "     HEIC* HEIC      rw+   High Efficiency Image Format\n     WEBP* WEBP      rw+   WebP\n"


class TestDoctorHeicRoundTrip(unittest.TestCase):
    """-list format says rw+ for HEIC whenever the coder exists; which libheif plugins are
    installed decides what really works, so doctor writes and reads back a tiny HEIC."""

    def doctor(self, verified):
        with mock.patch.object(_contract, "which_magick", return_value="/usr/bin/magick"), \
                mock.patch.object(_contract, "which_sips", return_value=None), \
                mock.patch.object(_contract, "magick_kind", return_value="magick"), \
                mock.patch.object(_contract, "_magick_lists", return_value=(FORMATS_HEIC_RW, "", "Version: ImageMagick 7")), \
                mock.patch.object(_contract, "_heic_roundtrip", return_value=verified), \
                mock.patch.object(_contract.sys, "platform", "linux"):
            return _contract.build_doctor_payload()["heic"]

    def test_encoder_without_decoder_is_not_readable(self):
        heic = self.doctor({"write": True, "read": False})
        self.assertEqual((heic["usable"], heic["read"], heic["write"]), (False, False, True))
        self.assertIn("libheif-plugin-libde265", heic["fix"])
        self.assertEqual(heic["verified"], {"write": True, "read": False})

    def test_nothing_written_means_no_write_but_read_keeps_the_listing(self):
        heic = self.doctor({"write": False, "read": None})
        self.assertEqual((heic["usable"], heic["read"], heic["write"]), (True, True, False))

    def test_full_round_trip(self):
        heic = self.doctor({"write": True, "read": True})
        self.assertEqual((heic["usable"], heic["read"], heic["write"], heic["fix"]), (True, True, True, None))


@unittest.skipUnless(_contract.which_magick(), "requires ImageMagick")
class TestHeicRoundTripForReal(unittest.TestCase):
    def test_agrees_with_the_listing_where_heic_is_writable(self):
        caps = _contract._format_capabilities(_contract._magick_lists(_contract.which_magick())[0])
        if not caps.get("HEIC", (False, False))[1]:
            self.skipTest("this ImageMagick lists no HEIC write support")
        verified = _contract._heic_roundtrip(_contract.which_magick())
        self.assertTrue(verified["write"], verified)
        self.assertIn(verified["read"], (True, False))


class TestContract(unittest.TestCase):
    def test_contract_lists_every_tool(self):
        payload = _contract.build_contract_payload()
        names = {t["name"] for t in payload["tools"]}
        self.assertEqual(
            names,
            {"probe", "convert", "resize", "thumb", "strip", "trim", "check", "batch",
             "look", "compare", "optimize", "crop", "pad", "rotate",
             "adjust", "overlay", "montage", "icons", "alpha", "preset"},
        )
        self.assertTrue(payload["ok"])
        self.assertIn("rules", payload)

    def test_contract_reports_the_package_name(self):
        self.assertEqual(_contract.build_contract_payload()["name"], "imagemagick-skill")


if __name__ == "__main__":
    unittest.main()
