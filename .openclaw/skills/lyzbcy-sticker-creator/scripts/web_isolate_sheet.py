"""Recover a square master whose isolated stickers overlap only in projection."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from web_static_density import _content_mask, _detect_background, clean_square_cuts


def isolate_sheet(source, cells, assign_detached=False, row_counts=None):
    if row_counts is not None:
        minimum = (cells ** 2 // 16) * 16
        if (len(row_counts) != cells or not minimum <= sum(row_counts) <= cells ** 2 + cells
                or sum(row_counts[:-1]) >= cells ** 2
                or any(not 1 <= count <= 12 for count in row_counts)):
            raise ValueError('Reviewed row counts must cover the sticker albums within the square atlas')
    expected_counts = row_counts or [cells] * cells
    with Image.open(source) as image:
        pixels = np.asarray(image.convert('RGB'))
    mask = _content_mask(pixels, _detect_background(pixels))
    height, width = mask.shape
    y_cuts = clean_square_cuts(mask.mean(axis=1), cells)
    if not y_cuts:
        raise ValueError('Missing clean horizontal row gutters')
    boundaries = [0, *y_cuts, height]
    tiles, source_tiles = [], []
    ignored = 0
    for row, (top, bottom) in enumerate(zip(boundaries, boundaries[1:]), 1):
        expected = expected_counts[row - 1]
        pitch = width / max(cells, expected)
        row_pixels = pixels[top:bottom]
        labels, count = ndimage.label(mask[top:bottom], np.ones((3, 3), bool))
        sizes = np.bincount(labels.ravel(), minlength=count + 1)
        parts = np.flatnonzero(sizes[1:] > 1) + 1
        regions = [index for index in parts if not assign_detached or sizes[index] > .27 * pitch**2]
        noise = count - len(parts)
        if len(regions) != expected or noise > 2:
            raise ValueError(f'Unexpected connected regions in row {row}: {len(regions)} main regions, {noise} isolated pixels')
        ignored += noise
        boxes = ndimage.find_objects(labels)

        def center(index):
            span = boxes[index - 1][1]
            return (span.start + span.stop) / 2

        groups = {index: [index] for index in sorted(regions, key=center)}
        if expected < cells:
            # A short reviewed row can retain the original columns or span the entire width.
            wide_pitch = width / expected
            offsets = [(center(index), column - .5) for column, index in enumerate(groups, 1)]
            if not all(abs(x - column * pitch) <= .18 * pitch for x, column in offsets):
                pitch = wide_pitch
        for part in set(parts) - groups.keys():
            ranked = sorted((abs(center(part) - center(index)), index) for index in groups)
            distance, owner = ranked[0]
            owner_span = boxes[owner - 1][1]
            part_span = boxes[part - 1][1]
            ambiguous = len(ranked) > 1 and ranked[1][0] - distance <= .14 * pitch
            if part_span.start < owner_span.start - 5 or part_span.stop > owner_span.stop + 5 or ambiguous:
                raise ValueError(f'A detached region has ambiguous ownership in row {row}')
            groups[owner].append(part)

        for column, (index, owned_parts) in enumerate(groups.items(), 1):
            spans = [boxes[part - 1][1] for part in owned_parts]
            start, stop = min(span.start for span in spans), max(span.stop for span in spans)
            if not .62 * pitch < stop - start < 1.2 * pitch or abs(center(index) - (column - .5) * pitch) > .18 * pitch:
                raise ValueError(f'Unexpected component size or position at row {row}, column {column}')
            left = max(0, start - 4)
            right = min(width, stop + 4)
            region = labels[:, left:right]
            own = np.isin(region, owned_parts)
            padded = ndimage.binary_dilation(own) & ((region == 0) | own)
            tile = np.full_like(row_pixels[:, left:right], [255, 0, 255])
            tile[padded] = row_pixels[:, left:right][padded]
            tiles.append(Image.fromarray(tile))
            source_tiles.append({'row': row, 'column': column, 'source_box': [left, top, right, bottom],
                                 'foreground_pixels': int(own.sum()), 'connected_parts': len(owned_parts)})

    # A reviewed extra slot in the last row may be beyond the atlas capacity.
    # Validate every region above, then omit only trailing reserves.
    atlas_tiles = tiles[:cells ** 2]
    atlas_pitch = max(max(tile.size) for tile in atlas_tiles) + 12
    atlas = Image.new('RGB', (atlas_pitch * cells, atlas_pitch * cells), '#ff00ff')
    for index, tile in enumerate(atlas_tiles):
        row, column = divmod(index, cells)
        atlas.paste(tile, (column * atlas_pitch + (atlas_pitch - tile.width) // 2, row * atlas_pitch))
    proof = {'source_master': str(source.resolve()), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'row_cuts': boundaries, 'source_cells': source_tiles, 'tiny_isolated_pixels_omitted': ignored,
             'visual_review_required': True}
    if row_counts is not None:
        proof['reviewed_row_counts'] = row_counts
        proof['omitted_trailing_reserves'] = max(0, len(tiles) - len(atlas_tiles))
    return atlas, proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--cells', type=int, choices=[6, 7, 8], required=True)
    parser.add_argument('--assign-detached', action='store_true', help='Allow separate captions with unambiguous component ownership')
    parser.add_argument('--reviewed-row-counts', nargs='+', type=int,
                        help='Use explicitly reviewed row lengths, packed in reading order')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    proof_path = args.out.with_suffix('.components.json')
    if args.out.exists() or proof_path.exists():
        raise FileExistsError('Component recovery output already exists')
    image, proof = isolate_sheet(args.master, args.cells, assign_detached=args.assign_detached,
                                 row_counts=args.reviewed_row_counts)
    image.save(args.out, format='PNG')
    proof['output_sha256'] = hashlib.sha256(args.out.read_bytes()).hexdigest()
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
