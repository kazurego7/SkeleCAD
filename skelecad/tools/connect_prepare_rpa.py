"""Connect preparation trial: default read-only; opt-in can click Print once, NEVER Send."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time


def plan_preparation(observation, filename, now=None):
    def stop(reason):
        return {'action': 'stop', 'reason': reason, 'can_send': False}
    if observation.get('source_kind') != 'live_window_capture':
        return stop('saved_image')
    try:
        age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(observation['observed_at'])).total_seconds()
        if not 0 <= age <= 20:
            return stop('expired_observation')
    except (KeyError, TypeError, ValueError):
        return stop('invalid_time')
    if observation.get('stage_candidate') == 'send_dialog':
        return stop('send_dialog_reached')
    if observation.get('stage_candidate') != 'loaded_preview':
        return stop('open_expected_file_manually')
    if observation.get('blocking_message_candidates'):
        return stop('error_visible')
    lines = observation.get('filename_line_candidates', [])
    # Exact basename plus an optional dropdown glyph, never substring matching.
    if len(lines) != 1 or not lines[0].startswith(filename) or lines[0][len(filename):].strip() not in ('', 'v', '∨', '⌄'):
        return stop('filename_mismatch_or_ambiguous')
    buttons = observation.get('green_button_candidates', [])
    if any(button['text'].strip() == 'Send' for button in buttons):
        return stop('send_visible_in_unexpected_state')
    candidates = [b for b in buttons if b['text'].strip() == 'Print']
    ref = observation.get('window_reference')
    if len(candidates) != 1 or not ref:
        return stop('unique_Print_or_window_not_found')
    box = candidates[0]['bounds']
    if len(box) != 4 or not (0 <= box[0] < box[2] <= ref['width'] and 0 <= box[1] < box[3] <= ref['height']):
        return stop('invalid_button_bounds')
    return {'action': 'open_print_dialog', 'button': 'Print', 'bounds': box, 'can_send': False}


def observe(directory, expected):
    from analyze_connect_screen import inspect_screen
    return inspect_screen(directory, expected)


def click_print_once(observation, plan):
    """Only used by an explicit local --execute-open-dialog invocation."""
    if plan.get('action') != 'open_print_dialog' or plan.get('button') != 'Print':
        raise RuntimeError('Only opening the Print dialog is supported.')
    _click_preparation_button(observation, plan)


def click_import_once(observation, plan):
    if plan.get('action') != 'confirm_import' or plan.get('button') != 'Import Gcode 3MF':
        raise RuntimeError('Only the file import confirmation is supported.')
    _click_preparation_button(observation, plan)


def _click_preparation_button(observation, plan):
    allowed = {('open_print_dialog', 'Print'): 'loaded_preview',
               ('confirm_import', 'Import Gcode 3MF'): 'import_confirmation'}
    required_stage = allowed.get((plan.get('action'), plan.get('button')))
    if required_stage is None or observation.get('stage_candidate') != required_stage:
        raise RuntimeError('Unsupported action or unexpected screen. Send is never supported.')
    _click_verified_button(observation, plan, required_stage)


def _click_verified_button(observation, plan, required_stage, verify_dialog=False):
    if observation.get('stage_candidate') != required_stage:
        raise RuntimeError('Unexpected screen before input.')
    from pywinauto.application import Application
    ref = observation['window_reference']
    expected_exe = Path(os.environ['LOCALAPPDATA']) / 'Programs/bambu-connect/Bambu Connect.exe'
    if os.path.normcase(ref['executable']) != os.path.normcase(str(expected_exe)):
        raise RuntimeError('Unexpected executable.')
    app = Application(backend='win32', allow_magic_lookup=False).connect(handle=ref['handle'])
    window = app.window(handle=ref['handle']).wrapper_object()
    if window.process_id() != ref['process_id'] or not window.is_visible() or not window.is_enabled() or window.is_minimized():
        raise RuntimeError('Target window changed or is unavailable.')
    rect = window.rectangle()
    if (rect.left, rect.top, rect.width(), rect.height()) != (ref['left'], ref['top'], ref['width'], ref['height']):
        raise RuntimeError('Window moved or resized; start a fresh inspection.')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    if user32.GetForegroundWindow() != ref['handle']:
        raise RuntimeError('Bring Connect to the foreground yourself; this tool does not activate it.')
    left, top, right, bottom = plan['bounds']
    x, y = ref['left'] + (left + right) // 2, ref['top'] + (top + bottom) // 2
    if user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(x, y)), 2) != ref['handle']:
        raise RuntimeError('Another window covers the Print button.')
    # Require the currently visible screen to match the inspected button and surroundings.
    from PIL import Image, ImageChops, ImageGrab, ImageStat
    with Image.open(observation['source_image']) as capture:
        area = (max(0, left - 16), max(0, top - 16), min(ref['width'], right + 16), min(ref['height'], bottom + 16))
        if verify_dialog:
            scope = observation.get('decision_scope', {})
            if scope.get('kind') != 'active_dialog' or scope.get('title') != 'Send to print':
                raise RuntimeError('Verified Send dialog is required.')
            area = tuple(scope['bounds'])
        expected = capture.convert('RGB').crop(area)
    screen = ImageGrab.grab(bbox=(ref['left'] + area[0], ref['top'] + area[1], ref['left'] + area[2], ref['top'] + area[3]), all_screens=True).convert('RGB')
    if screen.size != expected.size or max(ImageStat.Stat(ImageChops.difference(screen, expected)).mean) > 2:
        raise RuntimeError('Visible button changed; refusing stale coordinates.')
    if verify_dialog:
        diff = ImageChops.difference(screen, expected)
        channels = diff.split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        if maximum.point(lambda value: 255 if value > 24 else 0).getbbox() is not None:
            raise RuntimeError('Send dialog pixels changed after validation; no click performed.')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(observation['observed_at'])).total_seconds()
    if not 0 <= age <= 20 or user32.GetForegroundWindow() != ref['handle']:
        raise RuntimeError('Observation expired or foreground changed.')
    # Caller validates the action; never retry input after an uncertain result.
    from pywinauto.timings import Timings
    from pywinauto import mouse
    previous_wait = Timings.after_clickinput_wait
    try:
        Timings.after_clickinput_wait = .01
        # Public mouse API avoids the wrapper's redundant set_focus/logging path.
        # Foreground, target window and current pixels were checked just above.
        mouse.click(button='left', coords=(x, y))
    finally:
        Timings.after_clickinput_wait = previous_wait


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    job = args.file.resolve(strict=True)
    if not job.name.lower().endswith('.gcode.3mf'):
        raise ValueError('Select the sliced .gcode.3mf file.')
    digest = hashlib.sha256(job.read_bytes()).hexdigest()
    observation = getattr(args, 'initial_observation', None) or observe(output / 'before', args.expected.resolve(strict=True))
    plan = plan_preparation(observation, job.name)
    result = {'mode': 'execute_open_dialog' if args.execute_open_dialog else 'dry_run',
              'file': str(job), 'sha256': digest, 'plan': plan, 'can_send': False,
              'preflight': observation.get('preflight')}
    if args.execute_open_dialog and plan['action'] == 'open_print_dialog':
        # A second fresh observation must independently agree before any input.
        refreshed = observe(output / 'recheck', args.expected.resolve())
        fresh_plan = plan_preparation(refreshed, job.name)
        if fresh_plan != plan or refreshed.get('window_reference') != observation.get('window_reference'):
            raise RuntimeError('Screen changed between observations; no click performed.')
        if hashlib.sha256(job.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Job file changed; no click performed.')
        cancel_file = getattr(args, 'cancel_file', None)
        if cancel_file and cancel_file.exists() and cancel_file.read_text(encoding='utf-8') == 'cancel':
            raise RuntimeError('印刷の送信をキャンセルしました。')
        # Durable attempt marker: even an uncertain outcome is never automatically retried.
        with (output / 'print-dialog.attempted').open('x', encoding='utf-8') as attempt:
            json.dump({'action': 'Print', 'sha256': digest, 'time': datetime.now(timezone.utc).isoformat()}, attempt)
        click_print_once(refreshed, fresh_plan)
        result['clicked'] = 'Print'
        result['status'] = 'outcome_unknown_no_retry'
        (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        deadline = time.monotonic() + 12
        for index in range(120):
            if time.monotonic() > deadline:
                break
            if cancel_file and cancel_file.exists() and cancel_file.read_text(encoding='utf-8') == 'cancel':
                raise RuntimeError('印刷の送信をキャンセルしました。')
            if index:
                time.sleep(.05)
            after = observe(output / f'after-{index}', args.expected.resolve())
            result['after_stage'] = after['stage_candidate']
            result['preflight'] = after.get('preflight')
            if after['blocking_message_candidates']:
                result['status'] = 'error_after_Print_no_retry'
                break
            if after['stage_candidate'] == 'send_dialog' and after.get('preflight', {}).get('live_observation_matches') is True:
                result['status'] = 'stopped_before_Send'
                result['send_observation_directory'] = str(output / f'after-{index}')
                break
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-open-dialog', action='store_true', help='User opt-in: click only Print; stop before Send.')
    args = parser.parse_args()
    try:
        if args.execute_open_dialog:
            from connect_send_rpa import desktop_lock
            with desktop_lock():
                run(args)
        else:
            run(args)
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        attempted = (args.output / 'print-dialog.attempted').exists()
        failure = {'status': 'outcome_unknown_no_retry' if attempted else 'stopped',
                   'error': str(exc), 'print_dialog_attempt_recorded': attempted,
                   'can_send': False, 'automatic_retry': False}
        (args.output / 'result.json').write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
