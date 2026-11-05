import unittest
import numpy as np
from PIL import Image
from web_head_crop import center_square,crop_head

class FixedCropTests(unittest.TestCase):
    def test_top_80_percent_preserves_all_pixels_and_alpha(self):
        rng=np.random.default_rng(42)
        pixels=rng.integers(0,256,(100,100,4),dtype=np.uint8)
        result,box=center_square(Image.fromarray(pixels))
        self.assertEqual(box,(10,0,90,80))
        np.testing.assert_array_equal(np.asarray(result),pixels[0:80,10:90])
    def test_rectangular_tile_still_uses_center_square(self):
        result,box=center_square(Image.new('RGBA',(120,100)))
        self.assertEqual(result.size,(80,80));self.assertEqual(box,(20,0,100,80))
    def test_no_alternative_panel_or_automatic_reselection(self):
        with self.assertRaisesRegex(ValueError,'First-panel'):crop_head('not-read',2)

if __name__=='__main__':unittest.main()
