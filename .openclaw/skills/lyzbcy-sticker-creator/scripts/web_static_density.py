"""Split a reviewed dense static master into prepared albums using current tools.

The manifest uses web_batch.cjs's album schema. Prepare empty albums first;
never clone an already processed album. This command does not publish.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image
from gif_sheet_trial import sheet_layout


def split(master, manifest, cols=4, rows=12):
    albums = manifest['albums']
    if cols != 4 or rows != 4 * len(albums):
        raise ValueError('Each album must contain four rows of four stickers')
    image = Image.open(master).convert('RGB')
    xs, ys = sheet_layout(image, cols, rows)
    # Check every destination before writing any: never overwrite prior work.
    for album in albums:
        root = Path(album['dir'])
        if not (root / 'prep_state.json').is_file():
            raise ValueError(f'Prepare album before splitting: {root}')
        if (root / '原图/grid_4x4.png').exists() or (root / '成品清单.json').exists():
            raise FileExistsError(root)
    digest = hashlib.sha256(Path(master).read_bytes()).hexdigest()
    for i, album in enumerate(albums):
        root = Path(album['dir'])
        (root / '原图').mkdir(exist_ok=True)
        box = (0, ys[4 * i], image.width, ys[4 * i + 4])
        image.crop(box).save(root / '原图/grid_4x4.png')
        proof = dict(master=str(Path(master).resolve()), master_sha256=digest,
                     master_box=box, master_grid=[cols, rows],
                     panel_indexes=list(range(16*i+1, 16*i+17)),
                     image_calls_for_master=1, cuts={'x': xs, 'y': ys})
        (root / '原图/generation-source.json').write_text(
            json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
        meanings = root / 'meanings.json'
        meanings.write_text(json.dumps({str(n): f'{n:02}' for n in range(1,17)}), encoding='utf-8')
        subprocess.run([sys.executable, '-X', 'utf8', str(Path(__file__).with_name('web_process_grid.py')),
                        '--episode-dir', str(root), '--meanings', str(meanings), '--outline-px', '2'], check=True)
    return {'albums': len(albums), 'stickers': 16*len(albums), 'master_sha256': digest}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--rows', type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(split(args.master, json.loads(args.manifest.read_text(encoding='utf-8')), rows=args.rows)))
