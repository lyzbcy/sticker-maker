import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from gif_sheet_trial import sheet_layout, stabilize
from make_gif import encode_rgba_frames


class GifTrialTests(unittest.TestCase):
    def test_head_registration_ignores_moving_arm(self):
        rng = np.random.default_rng(17)
        head = Image.fromarray(rng.integers(20, 180, (38, 62, 3), dtype=np.uint8)).convert('RGBA')
        frames = []
        shifts = [(0, 0), (3, -2), (-4, 3), (2, 1)]
        for i, (x, y) in enumerate(shifts):
            frame = Image.new('RGBA', (180, 180))
            frame.alpha_composite(head, (59+x, 16+y))
            draw = ImageDraw.Draw(frame)
            draw.rectangle((65+x, 80+y, 105+x, 140+y), fill='red')
            draw.rectangle((20+i*14, 95, 60+i*14, 115), fill='orange')
            frames.append(frame)
        aligned, report = stabilize(frames)
        self.assertEqual(len(aligned), len(frames))
        for item, expected in zip(report, shifts):
            self.assertTrue(item['accepted'])
            # Masked ECC can have subpixel bias at the cap boundary. Require
            # recovery within half a source pixel, not exact floating equality.
            np.testing.assert_allclose(item['template_to_input_xy'], expected, atol=.5)

    def test_encoder_preserves_timing_and_transparency(self):
        frames = []
        for x in [4, 8, 12]:
            frame = Image.new('RGBA', (40, 40))
            ImageDraw.Draw(frame).rectangle((x, 10, x+8, 20), fill='red')
            frames.append(frame)
        with tempfile.TemporaryDirectory() as temp:
            report = encode_rgba_frames(frames, Path(temp)/'test.gif', [60, 80, 100])
        self.assertEqual(report['durations_ms'], [60, 80, 100])
        self.assertEqual(report['frames'], 3)
        self.assertEqual(report['total_ms'], 240)

    def test_layout_mismatch_is_rejected_without_padding(self):
        image = Image.new('RGB', (400, 280), '#ff00ff')
        draw = ImageDraw.Draw(image)
        for row in range(7):
            for col in range(10):
                draw.rectangle((col*40+8, row*40+8, col*40+30, row*40+30), fill='white')
        self.assertRaises(ValueError, sheet_layout, image, 10, 8)
        xs, ys = sheet_layout(image, 10, 7)
        self.assertEqual((len(xs), len(ys)), (11, 8))


if __name__ == '__main__':
    unittest.main()
