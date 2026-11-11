"""Offline checks for real image persistence, ACK integrity, and WG route enforcement."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from configure_dds import check_route, make_config
from protocol import digest, transfer_id, validate_ack
from storage import save_image, save_text

IDENTIFIER = "a" * 32 + "-000001"
SOURCE = ROOT / "resources/Canon80D_8_8_12800_printer_14_real.jpg"


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)

    def test_requested_image_survives_png_save_with_identical_pixels(self):
        image = cv2.imread(str(SOURCE), cv2.IMREAD_COLOR)
        self.assertIsNotNone(image)
        ack = save_image(self.output, IDENTIFIER, image)
        saved = cv2.imread(str(self.output / ack["file"]), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(saved, image)
        validate_ack(ack, {"id": IDENTIFIER, "kind": "image", "sha256": digest(image.tobytes()),
                           "shape": list(image.shape), "bytes": image.nbytes})
        self.assertEqual(json.loads((self.output / f"{IDENTIFIER}.json").read_text()), ack)

    def test_unicode_text_and_retries(self):
        text = "Привет ROS! 🤖\nClient2 → Client1"
        first = save_text(self.output, IDENTIFIER, text)
        self.assertEqual(first, save_text(self.output, IDENTIFIER, text))
        self.assertEqual((self.output / f"{IDENTIFIER}.txt").read_text(), text)
        validate_ack(first, {"id": IDENTIFIER, "kind": "text", "sha256": digest(text.encode())})
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_path_traversal_rejected_before_writing(self):
        for value in ("../escape", "/tmp/escape", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                save_text(self.output, value, "payload")
        self.assertEqual(list(self.output.iterdir()), [])

    def test_bad_image_encoding_rejected(self):
        for image in (np.zeros((2, 2), np.uint8), np.zeros((2, 2, 3), np.float32)):
            with self.assertRaises(ValueError):
                save_image(self.output, IDENTIFIER, image)

    def test_disk_write_failure_does_not_produce_success(self):
        with patch("storage.cv2.imwrite", return_value=False), self.assertRaises(OSError):
            save_image(self.output, IDENTIFIER, np.zeros((2, 2, 3), np.uint8))
        self.assertFalse((self.output / f"{IDENTIFIER}.json").exists())

    def test_corrupt_saved_pixels_do_not_produce_success(self):
        with patch("storage.cv2.imread", return_value=np.ones((2, 2, 3), np.uint8)), self.assertRaises(OSError):
            save_image(self.output, IDENTIFIER, np.zeros((2, 2, 3), np.uint8))
        self.assertFalse((self.output / f"{IDENTIFIER}.json").exists())

    def test_bad_ack_rejected(self):
        expected = {"id": IDENTIFIER, "sha256": "expected"}
        for ack in ({"ok": False, "error": "disk full"},
                    {"ok": True, "id": IDENTIFIER, "sha256": "corrupted"},
                    {"ok": True, "id": "another-transfer", "sha256": "expected"}):
            with self.subTest(ack=ack), self.assertRaises(ValueError):
                validate_ack(ack, expected)

    def test_large_sequence_identifier(self):
        self.assertEqual(transfer_id("b" * 32 + "-1000000"), "b" * 32 + "-1000000")


class NetworkTest(unittest.TestCase):
    def test_route_must_use_wireguard_with_expected_source(self):
        check_route([{"dev": "wg0", "prefsrc": "10.10.0.4"}], "10.10.0.4")
        for routes in ([], [{"dev": "eth0", "prefsrc": "10.10.0.4"}],
                       [{"dev": "wg0", "prefsrc": "10.10.0.3"}]):
            with self.subTest(routes=routes), self.assertRaises(RuntimeError):
                check_route(routes, "10.10.0.4")

    def test_config_pins_interface_and_unicast_peer(self):
        root = ET.fromstring(make_config("10.10.0.4", "10.10.0.3"))
        ns = {"c": "https://cdds.io/config"}
        interface = root.find(".//c:NetworkInterface", ns)
        self.assertEqual(interface.attrib["name"], "wg0")
        self.assertEqual(interface.attrib["address"], "10.10.0.4")
        self.assertEqual(root.find(".//c:AllowMulticast", ns).text, "false")
        self.assertEqual(root.find(".//c:Peer", ns).attrib["Address"], "10.10.0.3")

    def test_invalid_peer_rejected(self):
        for peer in ("10.10.0.4", "127.0.0.1", "239.1.2.3", "0.0.0.0", "not-an-ip"):
            with self.subTest(peer=peer), self.assertRaises(ValueError):
                make_config("10.10.0.4", peer)


if __name__ == "__main__":
    unittest.main()
