"""User-launched URL import and preparation; dry-run by default; never clicks Send."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from types import SimpleNamespace
from urllib.parse import urlencode, quote
import zipfile

from connect_prepare_rpa import observe, plan_preparation, click_import_once, run as prepare


def create_staged_job(source, output):
    source = source.resolve(strict=True)
    if not source.name.lower().endswith('.gcode.3mf'):
        raise ValueError('Expected a sliced .gcode.3mf file.')
    content = source.read_bytes()
    # Verify the bytes being staged, rather than rereading a potentially changing source.
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(content)) as archive:
        if not any(re.fullmatch(r'Metadata/plate_\d+\.gcode', name) for name in archive.namelist()):
            raise ValueError('The package contains no sliced plate G-code.')
        if archive.testzip() is not None:
            raise ValueError('Corrupt 3MF package.')
    folder = output / 'job'
    folder.mkdir(parents=True, exist_ok=True)
    staged = folder / ('SkeleCAD-' + secrets.token_hex(4).upper() + '.gcode.3mf')
    with staged.open('xb') as destination:
        destination.write(content)
    return staged, hashlib.sha256(content).hexdigest()


def import_uri(staged):
    return 'bambu-connect://import-file?' + urlencode(
        {'path': str(staged), 'name': staged.name, 'version': '1.0.0'}, quote_via=quote)


def validate_handler():
    import winreg
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'bambu-connect\shell\open\command') as key:
        command = winreg.QueryValueEx(key, None)[0]
    match = re.fullmatch(r'\s*"([^"]+)"\s+"%1"\s*', command)
    expected = Path(os.environ['LOCALAPPDATA']) / 'Programs/bambu-connect/Bambu Connect.exe'
    if not match or not expected.is_file() or Path(match[1]).resolve() != expected.resolve():
        raise RuntimeError('The URL scheme does not point to the expected Bambu Connect executable.')


def plan_import(observation, filename, now=None):
    def stop(reason):
        return {'action': 'stop', 'reason': reason, 'can_send': False}
    if observation.get('source_kind') != 'live_window_capture':
        return stop('saved_image')
    try:
        age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(observation['observed_at'])).total_seconds()
        if not 0 <= age <= 20:
            return stop('expired_observation')
    except (ValueError, TypeError, KeyError):
        return stop('invalid_time')
    if observation.get('stage_candidate') != 'import_confirmation':
        return stop('import_confirmation_not_visible')
    if observation.get('blocking_message_candidates'):
        return stop('error_visible')
    if observation.get('import_filename_candidates') != [filename]:
        return stop('import_filename_mismatch_or_ambiguous')
    buttons = observation.get('green_button_candidates', [])
    if any(b['text'].strip() == 'Send' for b in buttons):
        return stop('unexpected_Send')
    candidates = [b for b in buttons if b['text'].strip() == 'Import Gcode 3MF']
    ref = observation.get('window_reference')
    if len(candidates) != 1 or not ref:
        return stop('unique_import_button_not_found')
    box = candidates[0]['bounds']
    if len(box) != 4 or not (0 <= box[0] < box[2] <= ref['width'] and 0 <= box[1] < box[3] <= ref['height']):
        return stop('invalid_button_bounds')
    return {'action': 'confirm_import', 'button': 'Import Gcode 3MF', 'bounds': box, 'can_send': False}


def execute_import(staged, digest, expected, output, result):
    validate_handler()
    if hashlib.sha256(staged.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Staged file changed.')
    # The same run never dispatches a URL twice, even after an unknown outcome.
    with (output / 'url-import.attempted').open('x', encoding='utf-8') as marker:
        json.dump({'file': str(staged), 'sha256': digest}, marker)
    os.startfile(import_uri(staged))
    result['url_dispatched'] = True
    confirmed = False
    seen_window = False
    deadline = time.monotonic() + 90
    for index in range(400):
        decision = output / 'dispatch.decision'
        if decision.exists() and decision.read_text(encoding='utf-8') == 'cancel':
            raise RuntimeError('印刷の送信をキャンセルしました。')
        if time.monotonic() > deadline:
            break
        if index:
            time.sleep(.05)
        try:
            current = observe(output / f'import-{index}', expected)
        except Exception:
            if seen_window:
                raise
            # Read-only startup polling; never relaunch or retry input.
            continue
        seen_window = True
        stage = current['stage_candidate']
        result['last_stage'] = stage
        if stage == 'send_dialog':
            raise RuntimeError('Unexpected existing Send dialog; no preparation input performed.')
        if stage == 'loaded_preview':
            plan = plan_preparation(current, staged.name)
            if plan['action'] != 'open_print_dialog':
                raise RuntimeError('Loaded file could not be matched to this run: ' + plan['reason'])
            if hashlib.sha256(staged.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Staged file changed after import.')
            prepare(SimpleNamespace(file=staged, expected=expected, output=output / 'prepare', execute_open_dialog=True,
                                    initial_observation=current, cancel_file=output / 'dispatch.decision'))
            preparation = json.loads((output / 'prepare/result.json').read_text(encoding='utf-8'))
            result['preparation'] = preparation
            result['status'] = preparation.get('status', 'stopped_before_preparation')
            return
        if stage == 'import_confirmation':
            if confirmed:
                # A completed click can take time; observing again is fine, clicking again is not.
                continue
            plan = plan_import(current, staged.name)
            if plan['action'] != 'confirm_import':
                raise RuntimeError('Import confirmation could not be verified: ' + plan['reason'])
            refreshed = observe(output / 'import-recheck', expected)
            if plan_import(refreshed, staged.name) != plan or refreshed.get('window_reference') != current.get('window_reference'):
                raise RuntimeError('Import screen changed; no confirmation clicked.')
            if hashlib.sha256(staged.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Staged file changed before confirmation.')
            if decision.exists() and decision.read_text(encoding='utf-8') == 'cancel':
                raise RuntimeError('印刷の送信をキャンセルしました。')
            with (output / 'import-confirmation.attempted').open('x', encoding='utf-8') as marker:
                json.dump({'action': 'Import Gcode 3MF', 'sha256': digest}, marker)
            click_import_once(refreshed, plan)
            result['import_clicked'] = True
            confirmed = True
    raise RuntimeError('Import did not reach a verified preview. Stopped without repeating input.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-import-and-prepare', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {'mode': 'execute_import_and_prepare' if args.execute_import_and_prepare else 'dry_run',
              'can_send': False, 'automatic_retry': False}
    try:
        with (output / 'run.started').open('x', encoding='utf-8') as marker:
            marker.write(datetime.now(timezone.utc).isoformat())
        expected = args.expected.resolve(strict=True)
        staged, digest = create_staged_job(args.file, output)
        result.update({'source_file': str(args.file.resolve()), 'staged_file': str(staged),
                       'sha256': digest, 'import_uri': import_uri(staged), 'status': 'planned_no_GUI_actions'})
        if args.execute_import_and_prepare:
            from connect_send_rpa import desktop_lock
            with desktop_lock():
                execute_import(staged, digest, expected, output, result)
    except Exception as exc:
        result.update({'status': 'stopped', 'error': str(exc),
                       'url_attempt_recorded': (output / 'url-import.attempted').exists(),
                       'import_attempt_recorded': (output / 'import-confirmation.attempted').exists(),
                       'print_attempt_recorded': (output / 'prepare/print-dialog.attempted').exists()})
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['status'] == 'stopped':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
