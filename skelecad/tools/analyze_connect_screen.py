"""Read-only OCR experiment. No input injection, networking, or print dispatch."""
from __future__ import annotations

import argparse
import copy
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from PIL import Image, ImageOps, ImageChops
from connect_ocr_worker import run_ocr


def green(rgb):
    r, g, b = rgb[:3]
    return g > 110 and g > r + 45 and g > b + 25


def take_component(data, width, first):
    """Remove one four-connected mask component using whole horizontal spans."""
    pending = [first]
    left, top, right, bottom, count = width, len(data) // width, 0, 0, 0
    while pending:
        point = pending.pop()
        if data[point] != 255:
            continue
        row = point // width
        row_start, row_end = row * width, (row + 1) * width
        start = data.rfind(b'\0', row_start, point) + 1
        start = max(row_start, start)
        end = data.find(b'\0', point, row_end)
        if end < 0:
            end = row_end
        data[start:end] = b'\0' * (end - start)
        left, right = min(left, start - row_start), max(right, end - row_start)
        top, bottom = min(top, row), max(bottom, row + 1)
        count += end - start
        for offset in (-width, width):
            a, b = start + offset, end + offset
            if a < 0 or b > len(data):
                continue
            while a < b:
                seed = data.find(b'\xff', a, b)
                if seed < 0:
                    break
                pending.append(seed)
                a = data.find(b'\0', seed, b)
                if a < 0:
                    break
    return (left, top, right, bottom), count


def button_regions(image):
    r, g, b = image.convert('RGB').split()
    mask = ImageChops.multiply(g.point(lambda v: 255 if v > 110 else 0),
                              ImageChops.subtract(g, r).point(lambda v: 255 if v > 45 else 0))
    mask = ImageChops.multiply(mask, ImageChops.subtract(g, b).point(lambda v: 255 if v > 25 else 0))
    remaining = bytearray(mask.tobytes())
    regions = []
    first = remaining.find(b'\xff')
    while first >= 0:
        box, count = take_component(remaining, image.width, first)
        w, h = box[2] - box[0], box[3] - box[1]
        if w >= 30 and h >= 20 and count / (w * h) > .65:
            regions.append(box)
        first = remaining.find(b'\xff', first)
    return sorted(regions, key=lambda b: (b[1], b[0]))


def resolve_button_text(report, box, cropped_text):
    """Use exact labels from the same rectangle, not fuzzy OCR substitutions."""
    supported = {'Import Gcode 3MF', 'Print', 'Send'}
    left, top, right, bottom = box
    full_labels = []
    for line in report['lines']:
        label = line['text'].strip()
        words = line['words']
        if label in supported and words and all(
            left <= w['x'] and top <= w['y'] and
            w['x'] + w['width'] <= right and w['y'] + w['height'] <= bottom
            for w in words
        ):
            full_labels.append(label)
    unique = set(full_labels)
    crop = cropped_text.strip()
    if len(unique) > 1 or (len(unique) == 1 and crop in supported and crop not in unique):
        return {'text': '', 'text_source': 'conflicting_OCR', 'cropped_text': crop, 'full_labels': full_labels}
    if len(full_labels) == 1:
        return {'text': full_labels[0], 'text_source': 'full_image_same_bounds', 'cropped_text': crop}
    return {'text': crop, 'text_source': 'cropped_image', 'cropped_text': crop}


def scope_active_dialog(report, image, buttons):
    """Bound modal decisions to the bright panel containing its title, not its dimmed background."""
    text = '\n'.join(line['text'] for line in report['lines'])
    title = 'Send to print' if 'Send to print' in text else (
        'Import file' if 'You will import the file' in text else None)
    if title is None:
        return report, buttons, {'kind': 'full_window'}
    mask = image.convert('L').point(lambda value: 255 if value > 235 else 0)
    boxes = set()
    for line in report['lines']:
        if line['text'].strip() != title or not line['words']:
            continue
        words = line['words']
        left = min(w['x'] for w in words)
        right = max(w['x'] + w['width'] for w in words)
        top = min(w['y'] for w in words)
        bottom = max(w['y'] + w['height'] for w in words)
        for x in (int(left - 6), int(right + 6)):
            y = int((top + bottom) / 2)
            if not (0 <= x < image.width and 0 <= y < image.height) or mask.getpixel((x, y)) != 255:
                continue
            box, _ = take_component(bytearray(mask.tobytes()), image.width, y * image.width + x)
            if box and box[2] - box[0] >= 200 and box[3] - box[1] >= 100 and (
                box[0] <= left < right <= box[2] and box[1] <= top < bottom <= box[3]
            ):
                boxes.add(box)
    if len(boxes) != 1:
        raise RuntimeError('Cannot uniquely locate the active confirmation panel; no action allowed.')
    bounds = next(iter(boxes))
    def inside(box):
        return bounds[0] <= box[0] < box[2] <= bounds[2] and bounds[1] <= box[1] < box[3] <= bounds[3]
    included, excluded = [], []
    for line in report['lines']:
        words = line['words']
        if words and all(inside((w['x'], w['y'], w['x'] + w['width'], w['y'] + w['height'])) for w in words):
            included.append(line)
        else:
            excluded.append(line['text'])
    return {**report, 'lines': included}, [b for b in buttons if inside(b['bounds'])], {
        'kind': 'active_dialog', 'title': title, 'bounds': list(bounds),
        'excluded_background_messages': [s for s in excluded if re.search(r'\bfailed\b|\berror\b|\bincompatible\b', s, re.I)]}


def read_spool(report, image, output):
    """Inspect one material card. Never infer an external spool from PLA alone."""
    option_lines = [line for line in report['lines'] if line['text'].strip() == 'Print Options']
    if len(option_lines) != 1 or not option_lines[0]['words']:
        return {'selection': 'unknown', 'reason': 'material_card_not_located'}
    bottom = min(word['y'] for word in option_lines[0]['words'])
    labels = [word for line in report['lines'] for word in line['words']
              if word['text'] == 'PLA' and word['y'] < bottom]
    if len(labels) != 2:
        return {'selection': 'unknown', 'reason': 'expected_one_PLA_card'}
    size = max(word['height'] for word in labels)
    if abs(labels[0]['x'] - labels[1]['x']) > size * 5:
        return {'selection': 'unknown', 'reason': 'ambiguous_material_cards'}
    box = (max(0, int(min(w['x'] for w in labels) - size * 4)),
           max(0, int(min(w['y'] for w in labels) - size * 2)),
           min(image.width, int(max(w['x'] + w['width'] for w in labels) + size * 9)),
           min(image.height, int(bottom - size * .5)))
    if box[3] <= box[1] or box[2] <= box[0]:
        return {'selection': 'unknown', 'reason': 'invalid_material_bounds'}
    crop = ImageOps.autocontrast(image.crop(box).convert('L'))
    crop = ImageOps.expand(crop.point(lambda value: 0 if value < 150 else 255), border=12, fill=255)
    path = output / 'material-card.png'
    crop.save(path)
    ocr = run_ocr(path, output / 'material-card', scale=3)
    words = [word['text'] for line in ocr['lines'] for word in line['words']]
    external = words.count('Ext') == 1 and 'PLA' in words
    return {'selection': 'external' if external else 'unknown', 'bounds': list(box),
            'recognized_text': ' '.join(words), 'reason': 'visual_candidate_only'}


def evaluate_visible_fields(summary, expected, now=None):
    """Diagnostic only; even a match is insufficient to authorize printing."""
    reasons = []
    if summary['stage_candidate'] != 'send_dialog':
        reasons.append('send_dialog_not_visible')
    if summary['printer_label_candidates'] != [expected['printer_label']]:
        reasons.append('printer_mismatch_or_unknown')
    if summary['filament_text_visible'] != expected['material']:
        reasons.append('material_mismatch_or_unknown')
    if summary['spool_selection'] != expected['spool']:
        reasons.append('spool_mismatch_or_unknown')
    if set(expected['options']) != {'Timelapse', 'Bed leveling', 'Flow dynamic calibration'}:
        raise ValueError('Expected all three print options explicitly.')
    for label, value in expected['options'].items():
        if value not in ('On', 'Off'):
            raise ValueError('Expected options must be On or Off.')
        if summary['option_visual_candidates'].get(label) != value:
            reasons.append('option_mismatch_or_unknown:' + label)
    if summary['blocking_message_candidates']:
        reasons.append('error_message_visible')
    if sum(button['text'].strip() == 'Send' for button in summary['green_button_candidates']) != 1:
        reasons.append('unique_Send_not_found')
    live_reasons = list(reasons)
    if summary['source_kind'] != 'live_window_capture':
        live_reasons.append('saved_image_is_not_live_evidence')
    try:
        stamp = datetime.fromisoformat(summary['observed_at'])
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        if not 0 <= age <= 45:
            live_reasons.append('observation_expired')
    except (ValueError, TypeError):
        live_reasons.append('invalid_observation_time')
    return {'visible_fields_match': not reasons, 'visible_field_failures': reasons,
            'live_observation_matches': not live_reasons, 'live_observation_failures': live_reasons,
            'can_send': False, 'unverified': ['job_identity', 'printer_readiness', 'control_enabled_state'],
            'next_action': 'manual_review_only'}


def analyze(report, image, buttons, spool=None):
    lines = report['lines']
    text = '\n'.join(line['text'] for line in lines)
    words = [word for line in lines for word in line['words']]
    printer_candidates = sorted(set(re.findall(r'\b3DP-\d{3}-\d{3}\b', text)))
    labels = {button['text'].strip().casefold() for button in buttons}
    import_prompt = 'You will import the file' in text
    if 'Send to print' in text:
        stage = 'send_dialog'
    elif import_prompt:
        stage = 'import_confirmation'
    elif 'Compatible Printer' in text:
        stage = 'loaded_preview'
    elif 'Import Gcode 3MF' in text or 'import gcode 3mf' in labels:
        stage = 'import_page'
    else:
        stage = 'unknown'
    options = {}
    for label in ('Timelapse', 'Bed leveling', 'Flow dynamic calibration'):
        matching = [line for line in lines if line['text'].strip() == label]
        selected = []
        if len(matching) == 1 and matching[0]['words']:
            anchor = matching[0]['words']
            right = max(w['x'] + w['width'] for w in anchor)
            cy = sum(w['y'] + w['height'] / 2 for w in anchor) / len(anchor)
            candidates = [w for w in words if w['text'] in ('On', 'Off') and w['x'] > right
                          and abs(w['y'] + w['height'] / 2 - cy) < 12]
            # Use the nearest pair to this label, never a toggle from the next column.
            candidates = sorted(candidates, key=lambda w: w['x'])[:2]
            if {w['text'] for w in candidates} == {'On', 'Off'}:
                for word in candidates:
                    crop = image.crop((int(word['x']), int(word['y']),
                                       int(word['x'] + word['width'] + 1), int(word['y'] + word['height'] + 1)))
                    if sum(green(crop.getpixel((x, y))) for y in range(crop.height) for x in range(crop.width)) >= 4:
                        selected.append(word['text'])
        options[label] = selected[0] if len(selected) == 1 else 'unknown'
    return {
        'read_only': True, 'stage_candidate': stage,
        'visible_text_lines': [line['text'] for line in lines],
        'source_image': report['image'],
        'source_kind': 'live_window_capture' if report.get('window_title') else 'provided_image',
        'observed_at': report['captured_at'],
        'window_reference': report.get('window_reference'),
        'import_filename_candidates': re.findall(r'SkeleCAD-[A-Z0-9]+\.gcode\.3mf', text) if import_prompt else [],
        'printer_label_candidates': printer_candidates,
        'filename_line_candidates': [line['text'] for line in lines if re.search(r'\S+\.gcode\.3mf', line['text'], re.I)
                                     and not line['text'].startswith('Click to select')],
        'send_button_loading': any(
            w.get('text') == 'Send' and b['bounds'][0] <= w['x'] < b['bounds'][2]
            and b['bounds'][1] <= w['y'] < b['bounds'][3]
            and w['x'] + w['width'] / 2 > (b['bounds'][0] + b['bounds'][2]) / 2 + 5
            for w in words for b in buttons if b.get('text') == 'Send'),
        'cancel_button_candidates': [
            {'text': 'Cancel', 'bounds': [min(w['x'] for w in line['words']), min(w['y'] for w in line['words']),
                                        max(w['x'] + w['width'] for w in line['words']), max(w['y'] + w['height'] for w in line['words'])]}
            for line in lines if line['text'].strip() == 'Cancel' and line['words']],
        'green_button_candidates': buttons, 'option_visual_candidates': options,
        'filament_text_visible': 'PLA' if re.search(r'\bPLA\b', text) else None,
        'blocking_message_candidates': [line['text'] for line in lines
                                        if re.search(r'\bincompatible\b|\bfailed\b|\berror\b', line['text'], re.I)],
        'spool_selection': (spool or {}).get('selection', 'unknown'),
        'spool_evidence': spool or {'reason': 'not_inspected'},
        'can_send': False,
        'limitations': ['OCR results are observations, not print authorization.',
                        'Enabled state, exact job identity, spool mapping and printer readiness are not verified.',
                        'This program contains no click or send operation.'],
    }


_scene_cache = None


def scene_key(report, image):
    # Window identity and capture kind are part of the key. A saved screenshot
    # must never become live evidence merely because its pixels are identical.
    return (json.dumps(report.get('window_reference'), sort_keys=True), bool(report.get('window_title')),
            image.size, hashlib.sha256(image.tobytes()).digest())


def finish_observation(summary, report, expected_path, output, reused):
    summary = copy.deepcopy(summary)
    summary.update(source_image=report['image'], observed_at=report['captured_at'],
                   window_reference=report.get('window_reference'),
                   source_kind='live_window_capture' if report.get('window_title') else 'provided_image',
                   recognition_reused_for_identical_pixels=reused)
    summary.pop('preflight', None)
    if expected_path:
        expected = json.loads(expected_path.read_text(encoding='utf-8-sig'))
        summary['preflight'] = evaluate_visible_fields(summary, expected)
    (output / 'analysis.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def inspect_screen(output, expected_path=None, image_path=None):
    global _scene_cache
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = run_ocr(image_path.resolve() if image_path else None, output / 'full', capture_only=True)
    with Image.open(report['image']) as original:
        image = original.convert('RGB')
    key = scene_key(report, image)
    if _scene_cache is not None and _scene_cache[0] == key:
        return finish_observation(_scene_cache[1], report, expected_path, output, True)
    recognized = run_ocr(Path(report['image']), output / 'full-ocr')
    report['lines'] = recognized['lines']
    regions = button_regions(image)
    if len(regions) > 10:
        raise RuntimeError('Too many button candidates; unexpected screen.')
    buttons = []
    for index, box in enumerate(regions):
        direct = resolve_button_text(report, box, '')
        if direct['text_source'] == 'full_image_same_bounds':
            buttons.append({**direct, 'bounds': list(box)})
            continue
        left, top, right, bottom = box
        # Isolate white lettering against the detected green fill; no fixed screen coordinates.
        crop = image.crop((left + 3, top + 3, right - 3, bottom - 3)).convert('L')
        crop = ImageOps.expand(crop.point(lambda value: 0 if value > 220 else 255), border=10, fill=255)
        crop_path = output / f'button-{index}.png'
        crop.save(crop_path)
        button_ocr = run_ocr(crop_path, output / f'button-{index}', scale=3)
        cropped_text = ' '.join(line['text'] for line in button_ocr['lines'])
        buttons.append({**resolve_button_text(report, box, cropped_text), 'bounds': list(box)})
    report, buttons, scope = scope_active_dialog(report, image, buttons)
    spool = read_spool(report, image, output)
    summary = analyze(report, image, buttons, spool)
    summary['decision_scope'] = scope
    summary['recognition_source_image'] = report['image']
    summary['recognized_pixels_sha256'] = key[-1].hex()
    _scene_cache = (key, copy.deepcopy(summary))
    return finish_observation(summary, report, expected_path, output, False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, help='Use a saved screenshot instead of capturing Connect.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected', type=Path, help='Compare visible fields with a local JSON profile; never sends.')
    args = parser.parse_args()
    summary = inspect_screen(args.output, args.expected, args.image)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
