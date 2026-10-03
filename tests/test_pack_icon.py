import tempfile
import unittest
from pathlib import Path

from panda_pack.cli import normalize_icon

try:
    from PIL import Image

    HAVE_PIL = True
except ImportError:  # pragma: no cover - environment specific
    HAVE_PIL = False


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class NormalizeIconTest(unittest.TestCase):
    def test_bakes_a_circular_png(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.png"
            Image.new("RGB", (100, 60), (200, 30, 30)).save(source)

            target = Path(temp) / "assets" / "icon.png"
            normalize_icon(source, target)

            icon = Image.open(target)
            self.assertEqual(icon.size, (256, 256))
            self.assertEqual(icon.mode, "RGBA")
            # The circle mask makes the corners transparent, centre opaque.
            self.assertEqual(icon.getpixel((0, 0))[3], 0)
            self.assertEqual(icon.getpixel((128, 128))[3], 255)

    def test_missing_source_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(Exception):
                normalize_icon(
                    Path(temp) / "nope.png",
                    Path(temp) / "assets" / "icon.png",
                )


if __name__ == "__main__":
    unittest.main()
