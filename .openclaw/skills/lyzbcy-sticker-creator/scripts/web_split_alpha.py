"""Isolate sticker cells from a native-alpha PNG without chroma keying."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage


CORE_ALPHA = 192
BACKGROUND_ALPHA = 12
SEAM_ALPHA = 64
COMPONENT_SPAN_LIMIT = 1.20


def isolate_row(pixels, grid):
    alpha = pixels[:, :, 3]
    labels, _ = ndimage.label(alpha > CORE_ALPHA)
    boxes = ndimage.find_objects(labels)
    sizes = np.bincount(labels.ravel())
    pitch = alpha.shape[1] / grid
    minimum_subject = alpha.size / grid * 0.13
    subjects = [
        (label, box) for label, box in enumerate(boxes, 1)
        if sizes[label] >= minimum_subject
    ]
    subjects.sort(key=lambda pair: (pair[1][1].start + pair[1][1].stop) / 2)
    if len(subjects) != grid:
        raise ValueError(f'Found {len(subjects)} large subjects, expected {grid}')

    markers = np.zeros(labels.shape, dtype=np.uint8)
    for slot, (label, box) in enumerate(subjects, 1):
        center = (box[1].start + box[1].stop) / 2
        if abs(center - (slot - 0.5) * pitch) > 0.15 * pitch:
            raise ValueError(f'Unexpected subject center in column {slot}')
        markers[labels == label] = slot

    nearest = ndimage.distance_transform_edt(markers == 0, return_distances=False, return_indices=True)
    owner = markers[tuple(nearest)]
    main_labels = {label for label, _ in subjects}
    for label, size in enumerate(sizes[1:], 1):
        if size <= 25 or label in main_labels:
            continue
        region = labels == label
        votes = np.bincount(owner[region], minlength=grid + 1)
        slot = int(votes.argmax())
        if not slot or votes[slot] / size < 0.80:
            raise ValueError('Detached artwork has ambiguous ownership')
        markers[region] = slot

    distance, nearest = ndimage.distance_transform_edt(markers == 0, return_indices=True)
    owner = markers[tuple(nearest)]
    for slot in range(1, grid + 1):
        selected = (owner == slot) & (distance <= 4) & (alpha > BACKGROUND_ALPHA)
        ys, xs = np.where(selected)
        if not len(xs):
            raise ValueError(f'Empty sticker at column {slot}')
        bounds = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        isolated = np.zeros_like(pixels)
        isolated[selected] = pixels[selected]
        yield Image.fromarray(isolated).crop(bounds), bounds


def isolate_layout(pixels, columns, rows):
    """Recover only cells with one securely placed, isolated main component."""
    alpha = pixels[:, :, 3]
    labels, _ = ndimage.label(alpha > CORE_ALPHA)
    boxes = ndimage.find_objects(labels)
    sizes = np.bincount(labels.ravel())
    pitch_x = alpha.shape[1] / columns
    pitch_y = alpha.shape[0] / rows
    main_size = pitch_x * pitch_y * 0.13
    blocked = set()
    candidates = {}
    main_labels = set()

    for label, box in enumerate(boxes, 1):
        if sizes[label] < main_size:
            continue
        main_labels.add(label)
        y_slice, x_slice = box
        x = (x_slice.start + x_slice.stop) / (2 * pitch_x)
        y = (y_slice.start + y_slice.stop) / (2 * pitch_y)
        column, row = int(x), int(y)
        slot = row * columns + column + 1
        width = (x_slice.stop - x_slice.start) / pitch_x
        height = (y_slice.stop - y_slice.start) / pitch_y
        if (abs(x - column - 0.5) > 0.27 or abs(y - row - 0.5) > 0.27
                or max(width, height) > COMPONENT_SPAN_LIMIT):
            for touched_row in range(int(y_slice.start / pitch_y), int((y_slice.stop - 1) / pitch_y) + 1):
                for touched_column in range(int(x_slice.start / pitch_x), int((x_slice.stop - 1) / pitch_x) + 1):
                    blocked.add(touched_row * columns + touched_column + 1)
        elif slot in candidates:
            blocked.add(slot)
        else:
            candidates[slot] = label

    markers = np.zeros(labels.shape, dtype=np.int32)
    for slot, label in candidates.items():
        markers[boxes[label - 1]][labels[boxes[label - 1]] == label] = slot
    if not candidates:
        return
    nearest = ndimage.distance_transform_edt(markers == 0, return_distances=False, return_indices=True)
    owner = markers[tuple(nearest)]
    for label, size in enumerate(sizes[1:], 1):
        if size <= 25 or label in main_labels:
            continue
        region = boxes[label - 1]
        component = labels[region] == label
        votes = np.bincount(owner[region][component], minlength=columns * rows + 1)
        slot = int(votes.argmax())
        if votes[slot] / size < 0.80:
            blocked.update(np.flatnonzero(votes))
            continue
        markers[region][component] = slot

    distance, nearest = ndimage.distance_transform_edt(markers == 0, return_indices=True)
    owner = markers[tuple(nearest)]
    for slot in sorted(candidates.keys() - blocked):
        selected = (owner == slot) & (distance <= 4) & (alpha > BACKGROUND_ALPHA)
        ys, xs = np.where(selected)
        bounds = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
        isolated = np.where(selected[:, :, None], pixels, 0)
        yield slot, Image.fromarray(isolated).crop(bounds), bounds


def open_png(source, columns, rows):
    with Image.open(source) as image:
        if image.format != 'PNG' or 'A' not in image.getbands():
            raise ValueError('Expected a native-alpha PNG')
        pixels = np.asarray(image.convert('RGBA'))
    alpha = pixels[:, :, 3]
    if not (alpha == 0).any() or not (alpha > CORE_ALPHA).any():
        raise ValueError('Expected transparent pixels and visible foreground')
    height, width = alpha.shape
    if width < columns * 50 or height < rows * 50:
        raise ValueError('Grid dimensions are too small')
    return pixels


def render_sticker(tile):
    rendered = ImageOps.contain(tile, (218, 218), Image.Resampling.LANCZOS)
    sticker = Image.new('RGBA', (240, 240))
    sticker.alpha_composite(rendered, ((240 - rendered.width) // 2, (240 - rendered.height) // 2))
    return sticker


def split(source, output, grid, *, allow_partial=False):
    pixels = open_png(source, grid, grid)
    alpha = pixels[:, :, 3]
    height, width = alpha.shape

    pitch = height / grid
    window = max(4, round(pitch * 0.33))
    profile = (alpha > SEAM_ALPHA).sum(axis=1)
    soft_profile = (alpha > BACKGROUND_ALPHA).sum(axis=1)
    boundaries = [0]
    excluded_rows = {}
    for row in range(1, grid):
        target = round(pitch * row)
        seam = min(range(target - window, target + window + 1),
                   key=lambda y: (profile[y], soft_profile[y], abs(y - target)))
        if profile[seam]:
            reason = f'No transparent seam before row {row + 1}'
            if not allow_partial:
                raise ValueError(reason)
            excluded_rows[row] = reason
            excluded_rows[row + 1] = reason
            seam = target
        boundaries.append(seam)
    boundaries.append(height)

    tiles = {}
    for row, (top, bottom) in enumerate(zip(boundaries, boundaries[1:]), 1):
        if row in excluded_rows:
            continue
        try:
            isolated_row = list(isolate_row(pixels[top:bottom], grid))
            for column, (tile, (x0, y0, x1, y1)) in enumerate(isolated_row, 1):
                tiles[(row - 1) * grid + column] = (render_sticker(tile), [x0, y0 + top, x1, y1 + top])
        except ValueError as error:
            if not allow_partial:
                raise ValueError(f'Row {row}: {error}') from error
            excluded_rows[row] = str(error)

    if allow_partial and len(tiles) < 8:
        raise ValueError('Fewer than eight cells satisfy the row and ownership checks')

    return write_tiles(source, output, grid, grid, width, height, tiles, {
        'method': 'row_cuts',
        'row_boundaries': boundaries,
        'seam_alpha_threshold': SEAM_ALPHA,
        'excluded_rows': excluded_rows,
    })


def split_by_components(source, output, columns, rows, *, layout_bounds=None):
    pixels = open_png(source, columns, rows)
    height, width = pixels.shape[:2]
    left, top, right, bottom = layout_bounds or (0, 0, width, height)
    if not (0 <= left < right <= width and 0 <= top < bottom <= height
            and right - left >= columns * 50 and bottom - top >= rows * 50):
        raise ValueError('Layout bounds lie outside the PNG or are too small')
    alpha = pixels[:, :, 3]
    if any((strip > SEAM_ALPHA).any() for strip in (alpha[:top], alpha[bottom:], alpha[:, :left], alpha[:, right:])):
        raise ValueError('Layout bounds cut through foreground')
    layout = pixels[top:bottom, left:right]
    tiles = {}
    for slot, tile, (x0, y0, x1, y1) in isolate_layout(layout, columns, rows):
        tiles[slot] = (render_sticker(tile), [x0 + left, y0 + top, x1 + left, y1 + top])
    if len(tiles) < 8:
        raise ValueError('Fewer than eight cells satisfy the component placement checks')
    return write_tiles(source, output, columns, rows, width, height, tiles, {
        'method': 'component_placement',
        'component_span_limit': COMPONENT_SPAN_LIMIT,
        'layout_bounds': [left, top, right, bottom],
    })


def write_tiles(source, output, columns, rows, width, height, tiles, evidence):
    output.mkdir(exist_ok=False)
    board = Image.new('RGB', (150 * columns, 155 * rows), '#d9dadb')
    draw = ImageDraw.Draw(board)
    records = [None] * (columns * rows)
    for slot in range(1, columns * rows + 1):
        row, col = divmod(slot - 1, columns)
        x, y = col * 150, row * 155
        if slot not in tiles:
            draw.text((x + 6, y + 141), f'{slot} - held', fill='black')
            continue
        sticker, bounds = tiles[slot]
        name = f'{slot:02}.png'
        destination = output / name
        sticker.save(destination)
        records[slot - 1] = {
            'slot': slot,
            'file': name,
            'source_bounds': bounds,
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
        sticker.thumbnail((143, 140))
        board.paste(sticker, (x + (150 - sticker.width) // 2, y), sticker)
        draw.text((x + 6, y + 141), str(slot), fill='black')
    board.save(output / '透明分格复核.jpg', quality=91)
    proof = {
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_dimensions': [width, height],
        'grid': columns if columns == rows else None,
        'layout_columns_rows': [columns, rows],
        'core_alpha_threshold': CORE_ALPHA,
        'alpha_floor': BACKGROUND_ALPHA,
        **evidence,
        'source_tiles': records,
        'visual_review_required': True,
    }
    (output / '分格证据.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(tiles)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--grid', type=int, choices=range(2, 9), default=6)
    parser.add_argument('--allow-partial', action='store_true', help='Keep only rows whose boundaries and cells pass all checks')
    parser.add_argument('--component-layout', nargs=2, type=int, metavar=('COLUMNS', 'ROWS'),
                        help='Recover isolated components for a visually verified layout, with missing positions preserved')
    parser.add_argument('--layout-bounds', nargs=4, type=int, metavar=('X0', 'Y0', 'X1', 'Y1'),
                        help='Locate an offset layout without cropping any visible foreground')
    args = parser.parse_args()
    if args.component_layout:
        if args.allow_partial or any(not 2 <= dimension <= 8 for dimension in args.component_layout):
            parser.error('Component layout requires 2 to 8 rows and columns and cannot be combined with --allow-partial')
        count = split_by_components(args.source, args.output, *args.component_layout, layout_bounds=args.layout_bounds)
    else:
        if args.layout_bounds:
            parser.error('Layout bounds require --component-layout')
        count = split(args.source, args.output, args.grid, allow_partial=args.allow_partial)
    print(f'{count} transparent cells ready for visual review')
