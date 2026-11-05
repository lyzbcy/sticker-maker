"""Offline multi-animation sheet trial: common framing, head registration, honest QA."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from web_edge_finish import clean_key_edges, white_outline
from make_gif import encode_rgba_frames


def write(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def bands(profile, minimum=8):
    mask = ndimage.binary_closing(profile > .025, iterations=2)
    labels, n = ndimage.label(mask)
    result = []
    for i in range(1, n + 1):
        points = np.flatnonzero(labels == i)
        if len(points) >= minimum:
            result.append((int(points[0]), int(points[-1]) + 1))
    return result


def sheet_layout(image, cols, rows):
    rgb = np.asarray(image.convert('RGB')).astype(float)
    distance = np.abs(rgb - [255, 0, 255]).sum(axis=2)
    foreground = distance > 100
    rb = bands(foreground.mean(axis=1))
    cb = bands(foreground.mean(axis=0))
    if len(rb) != rows or len(cb) != cols:
        raise ValueError(f'Layout mismatch: expected {cols}x{rows}, detected {len(cb)}x{len(rb)}; inspect once and supply actual layout, never pad missing frames')
    def cuts(bs, length):
        return [0] + [round((a[1] + b[0]) / 2) for a, b in zip(bs, bs[1:])] + [length]
    return cuts(cb, image.width), cuts(rb, image.height)


def gray(image):
    bg = Image.new('RGB', image.size, 'white')
    bg.paste(image, mask=image.getchannel('A'))
    return cv2.cvtColor(np.asarray(bg), cv2.COLOR_RGB2GRAY)


def head_mask(side):
    mask = np.zeros((side, side), np.uint8)
    # Fixed forehead/hair cap, excluding the mouth, moving hands and captions.
    mask[round(side*.07):round(side*.31), round(side*.23):round(side*.77)] = 255
    return mask


def feature_motion(frames):
    """Independent LK measurement of successive stationary head features."""
    reference = gray(frames[0])
    features = cv2.goodFeaturesToTrack(reference, 100, .01, 3, mask=head_mask(frames[0].width))
    if features is None or len(features) < 4:
        return {'valid': False, 'reason': 'too few stationary head features'}
    positions = []
    for frame in frames:
        pts, status, error = cv2.calcOpticalFlowPyrLK(reference, gray(frame), features, None,
                                                    winSize=(21, 21), maxLevel=2)
        delta = (pts - features).reshape(-1, 2)
        valid = (status.ravel() == 1) & (error.ravel() < 30) & (np.linalg.norm(delta, axis=1) < frame.width*.2)
        if valid.sum() < 4:
            return {'valid': False, 'reason': 'head feature tracking unreliable'}
        positions.append(np.median(delta[valid], axis=0))
    positions = np.asarray(positions)
    steps = np.diff(np.vstack([positions, positions[0]]), axis=0)
    return {'valid': True, 'head_rms_px': float(np.sqrt(np.mean(positions**2))),
            'step_rms_px': float(np.sqrt(np.mean(steps**2))),
            'max_step_px': float(np.linalg.norm(steps, axis=1).max()),
            'positions': positions.tolist()}


def stabilize(frames):
    side = frames[0].width
    template = gray(frames[0])
    mask = head_mask(side)
    result, records = [], []
    for i, frame in enumerate(frames):
        matrix = np.eye(2, 3, dtype=np.float32)
        correlation, accepted, reason = 1., True, 'reference'
        if i:
            try:
                correlation, matrix = cv2.findTransformECC(template, gray(frame), matrix,
                    cv2.MOTION_TRANSLATION, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5), mask, 3)
                accepted = correlation >= .7 and np.max(np.abs(matrix[:, 2])) < side*.18
                reason = 'head translation' if accepted else 'low confidence or excessive displacement'
            except cv2.error:
                accepted, reason = False, 'ECC did not converge'
        if not accepted:
            matrix = np.eye(2, 3, dtype=np.float32)
        # Premultiplied alpha avoids dark fringes when translating fractional pixels.
        rgba = np.asarray(frame).astype(np.float32) / 255
        rgba[:, :, :3] *= rgba[:, :, 3:4]
        warped = cv2.warpAffine(rgba, matrix, (side, side), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        warped[:, :, :3] /= np.maximum(warped[:, :, 3:4], 1e-5)
        result.append(Image.fromarray(np.clip(warped*255, 0, 255).astype('uint8')))
        records.append({'frame': i, 'correlation': float(correlation), 'accepted': bool(accepted),
                        'template_to_input_xy': matrix[:, 2].tolist(), 'reason': reason})
    return result, records


def render_both(raw, aligned, label):
    bounds = [f.getbbox() for f in raw + aligned]
    if any(b is None for b in bounds):
        raise ValueError('Empty animation frame')
    x0, y0 = min(b[0] for b in bounds)-3, min(b[1] for b in bounds)-3
    x1, y1 = max(b[2] for b in bounds)+3, max(b[3] for b in bounds)+3
    side = max(x1-x0, y1-y0)
    # The same crop and scale applies to all raw/aligned frames in this GIF.
    box = (x0-(side-(x1-x0))//2, y0-(side-(y1-y0))//2, 0, 0)
    box = (box[0], box[1], box[0]+side, box[1]+side)
    font = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 26)
    caption = Image.new('RGBA', (240, 240))
    draw = ImageDraw.Draw(caption)
    draw.text((120, 211), label, font=font, anchor='mt', fill='#42251c', stroke_width=3, stroke_fill='white')
    def render(frames):
        out = []
        for f in frames:
            canvas = Image.new('RGBA', (240, 240))
            small = f.crop(box).resize((204, 204), Image.Resampling.LANCZOS)
            canvas.alpha_composite(small, (18, 5))
            canvas = white_outline(canvas, 1)
            canvas.alpha_composite(caption)
            out.append(canvas)
        return out
    return render(raw), render(aligned), box


def process(config):
    start = time.time()
    root = Path(config['outputDir'])
    folder = root / config.get('variant', '成品')
    folder.mkdir(exist_ok=False)
    reports = []
    for sheet in config['sheets']:
        image = Image.open(root / sheet['file']).convert('RGB')
        xs, ys = sheet_layout(image, sheet['cols'], sheet['rows'])
        side = max(max(np.diff(xs)), max(np.diff(ys))) + 48
        cells, edge_contacts = [], []
        for y0, y1 in zip(ys, ys[1:]):
            for x0, x1 in zip(xs, xs[1:]):
                cell = clean_key_edges(image.crop((x0, y0, x1, y1)), '#ff00ff')
                rgba = np.asarray(cell)
                # A few white/magenta antialias pixels on the outer boundary
                # are not the same as a cropped face or body.
                colored = (rgba[:, :, 3] > 128) & (rgba[:, :, :3].min(axis=2) < 180)
                edge_contacts.append(int(colored[0].sum()+colored[-1].sum()+colored[:, 0].sum()+colored[:, -1].sum()))
                canvas = Image.new('RGBA', (side, side))
                canvas.alpha_composite(cell, ((side-cell.width)//2, (side-cell.height)//2))
                cells.append(canvas)
        used = []
        for group in sheet['animations']:
            indexes = group['indexes']
            if len(indexes) < 2 or any(i < 0 or i >= len(cells) for i in indexes):
                raise ValueError('Invalid timeline: no invented or duplicated source frames')
            excluded = [i for i in indexes if edge_contacts[i] > 3]
            if excluded and config.get('exclude_truncated', False):
                indexes = [i for i in indexes if i not in excluded]
                if len(indexes) < 12:
                    raise ValueError(f'{group["meaning"]}: fewer than 12 complete source frames remain; regenerate the failed animation')
            elif excluded:
                raise ValueError(f'{group["meaning"]}: source frame touches cell edge; exclude truncated cells before processing')
            used.extend(indexes)
            raw = [cells[i] for i in indexes]
            aligned, transforms = stabilize(raw)
            before, after = feature_motion(raw), feature_motion(aligned)
            name = group['meaning']
            raw_render, aligned_render, box = render_both(raw, aligned, name)
            frame_dir = folder / '逐帧' / name
            frame_dir.mkdir(parents=True)
            timings = [60]*len(raw)
            final = folder / f'{name}.gif'
            encoded = encode_rgba_frames(aligned_render, final, timings)
            encode_rgba_frames(raw_render, folder / '对照原始' / f'{name}.gif', timings)
            for source, dest in [(final, frame_dir),
                    (folder / '对照原始' / f'{name}.gif', folder / '对照原始' / '逐帧' / name)]:
                dest.mkdir(parents=True, exist_ok=True)
                with Image.open(source) as gif:
                    for i in range(gif.n_frames):
                        gif.seek(i)
                        gif.convert('RGBA').save(dest / f'{i:02d}.png')
            aligned_render[0].save(folder / f'{name}.png')
            strip = Image.new('RGB', (240*5, 265*((len(raw)+4)//5)), '#eeeae4')
            draw = ImageDraw.Draw(strip)
            for i, f in enumerate(aligned_render):
                x, y = (i%5)*240, (i//5)*265
                strip.paste(f, (x, y), f)
                draw.text((x+8, y+242), f'{i+1} / 60ms', fill='black')
            strip.save(frame_dir / '逐帧.jpg', quality=90)
            flags = []
            if any(not t['accepted'] for t in transforms):
                flags.append('registration_low_confidence')
            if not after['valid'] or (before['valid'] and after['step_rms_px'] > before['step_rms_px']+.1):
                flags.append('head_motion_not_improved')
            report = {'meaning': name, 'file': final.name, 'source': sheet['file'],
                'actual_source_frames': len(indexes), 'indexes': indexes, 'cuts': {'x': xs, 'y': ys},
                'excluded_truncated_indexes': excluded,
                'shared_crop': box, 'registration': transforms, 'before': before, 'after': after,
                'flags': flags, 'visual_review': None, 'human_score': None, **encoded,
                'sha256': hashlib.sha256(final.read_bytes()).hexdigest()}
            reports.append(report)
        if len(used) != len(set(used)):
            raise ValueError('A source frame was reused across different animations')
    write(folder / '核验与防抖.json', {'seconds': time.time()-start, 'animations': reports})
    return {'folder': str(folder), 'gifs': len(reports), 'seconds': time.time()-start,
            'flagged': [r['meaning'] for r in reports if r['flags']]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(process(json.loads(args.config.read_text(encoding='utf-8'))), ensure_ascii=False))
