"""Suggest sticker meanings from local PNGs. Results still require visual review."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image


def caption_crop(image, ratio, top_edge=False):
    background = Image.new('RGB', image.size, 'white')
    background.paste(image, mask=image.getchannel('A'))
    left, top, right, bottom = image.getbbox()
    height = round((bottom - top) * ratio)
    crop_top, crop_bottom = ((top, top + height) if top_edge else
                             (bottom - height, min(image.height, bottom + 4)))
    cropped = background.crop((max(0, left - 4), crop_top, min(image.width, right + 4), crop_bottom))
    return np.asarray(cropped)[:, :, ::-1].copy()


def normalize(text):
    text = text.strip().replace('—起', '一起').replace('–起', '一起')
    return ''.join(re.findall(r'[\u3400-\u9fff]', text))


def normalize_caption(text):
    text = text.translate(str.maketrans('!?.,:;~％', '！？。，：；～%'))
    return ''.join(re.findall(r'[\u3400-\u9fffA-Za-z0-9%！？。，、：；…～]', text)).lstrip('%！？。，、：；…～')


def recognize_panels(recognizer, images, transcribe, top_edge=False):
    variants = [recognizer([caption_crop(image, ratio, top_edge) for image in images])[0]
                for ratio in (.18, .22, .26, .30, .34)]
    results = []
    for options in zip(*variants):
        normalized = [((normalize_caption if transcribe else normalize)(text), score) for text, score in options]
        votes = Counter(text for text, _ in normalized if len(normalize(text)) >= 2 and (transcribe or len(text) <= 5))
        confidences = {text: max(score for candidate, score in normalized if candidate == text) for text in votes}
        best = max(votes, key=lambda text: (votes[text], confidences[text]), default='')
        results.append({'text': best, 'votes': votes[best], 'confidence': float(confidences.get(best, 0))})
    return results


def candidates(manifest, transcribe=False):
    from rapidocr_onnxruntime import RapidOCR

    recognizer = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1).text_rec
    output = []
    for album in manifest['albums']:
        root = Path(album['dir'])
        source = json.loads((root / '成品清单.json').read_text(encoding='utf-8'))
        images = []
        for item in source['files']:
            with Image.open(root / item['file']) as image:
                images.append(image.convert('RGBA'))
        result = recognize_panels(recognizer, images, transcribe)
        placement = 'bottom'
        if transcribe:
            top = recognize_panels(recognizer, images, transcribe, top_edge=True)
            quality = lambda panels: sum(panel['votes'] * panel['confidence'] for panel in panels)
            if quality(top) > quality(result):
                placement, result = 'top', top
        panel_candidates = [{'index': item['index'], **candidate}
                            for item, candidate in zip(source['files'], result, strict=True)]
        output.append({'episode': album['episode'], 'placement': placement, 'candidates': panel_candidates})
    return {'source': 'local_caption_ocr' if transcribe else 'local_ocr', 'visual_review_required': True, 'albums': output}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--captions', action='store_true', help='Suggest full captions including common punctuation')
    args = parser.parse_args()
    document = json.loads(args.manifest.read_text(encoding='utf-8'))
    result = candidates(document, transcribe=args.captions)
    temporary = args.out.with_suffix(args.out.suffix + '.partial')
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(args.out)
