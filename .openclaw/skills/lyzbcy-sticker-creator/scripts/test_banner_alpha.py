import unittest
from PIL import Image
from make_banner import maybe_remove_flat_opaque_background


class BannerAlphaTest(unittest.TestCase):
    def test_tight_transparent_portrait_keeps_skin_and_clothing(self):
        portrait = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
        portrait.paste((240, 210, 180, 255), (0, 0, 40, 40))
        portrait.putpixel((20, 0), (0, 0, 0, 0))
        self.assertEqual(maybe_remove_flat_opaque_background(portrait).tobytes(), portrait.tobytes())

    def test_opaque_background_still_removed(self):
        picture = Image.new('RGBA', (40, 40), 'white')
        picture.paste((180, 30, 10, 255), (10, 10, 30, 30))
        result = maybe_remove_flat_opaque_background(picture)
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((20, 20)), (180, 30, 10, 255))


if __name__ == '__main__':
    unittest.main()
