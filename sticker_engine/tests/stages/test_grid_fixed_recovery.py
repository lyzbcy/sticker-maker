"""Explicit recovery must keep overflowing components whole, without neighbours."""
import numpy as np
from PIL import Image, ImageDraw

from sticker_engine.stages.grid_cutter import cut_grid


def test_fixed_grid_keeps_overflow_and_excludes_neighbour(tmp_path):
    image = Image.new('RGB', (400, 400), (255, 0, 255))
    draw = ImageDraw.Draw(image)
    colors = [(20 + i * 10, 100, 50) for i in range(16)]
    for i, color in enumerate(colors):
        row, col = divmod(i, 4)
        # First sticker crosses x=100; its centroid still belongs to column 1.
        left = col * 100 + (25 if col else 20)
        right = col * 100 + (80 if col else 112)
        draw.rectangle((left, row * 100 + 20, right, row * 100 + 80), fill=color)
    source = tmp_path / 'source.png'
    image.save(source)
    panels, _ = cut_grid(source, 4, tmp_path / 'out', fixed_grid=True)
    for i, panel in enumerate(panels):
        pixels = np.asarray(Image.open(panel))
        foreground = pixels[(pixels != (255, 0, 255)).any(axis=2)]
        assert set(map(tuple, foreground)) == {colors[i]}
        assert len(foreground) == (93 if i % 4 == 0 else 56) * 61
