"""Explicit print execution through the official Connect UI. Never retries Send."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

from analyze_connect_screen import evaluate_visible_fields
from connect_import_rpa import create_staged_job, execute_import
from connect_prepare_rpa import observe, _click_verified_button
from connect_print import PROJECT, validate_profile, compatible_copy


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def check_cancel(output):
    decision = output / 'dispatch.decision'
    if decision.exists() and decision.read_text(encoding='utf-8') == 'cancel':
        raise RuntimeError('印刷の送信をキャンセルしました。')


@contextmanager
def desktop_lock():
    # Shared by server and shortcuts; kernel releases the byte lock after a crash.
    import msvcrt
    path = PROJECT / '.runtime/connect-desktop.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.write(b'0'); handle.flush(); handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('別のConnect印刷操作が進行中です。') from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def plan_send(observation, expected):
    fields = evaluate_visible_fields(observation, expected)
    if not fields['live_observation_matches']:
        raise RuntimeError('送信画面の設定が一致しません: ' + ', '.join(fields['live_observation_failures']))
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(observation['observed_at'])).total_seconds()
    if not 0 <= age <= 20:
        raise RuntimeError('送信画面の確認が期限切れです。')
    scope = observation.get('decision_scope', {})
    if scope.get('kind') != 'active_dialog' or scope.get('title') != 'Send to print':
        raise RuntimeError('送信ダイアログを特定できません。')
    ref = observation['window_reference']
    box = next(b['bounds'] for b in observation['green_button_candidates'] if b['text'].strip() == 'Send')
    if len(box) != 4 or not (0 <= box[0] < box[2] <= ref['width'] and 0 <= box[1] < box[3] <= ref['height']):
        raise RuntimeError('Sendの位置を確認できません。')
    return {'action': 'send', 'button': 'Send', 'bounds': box}


def classify_outcome(observation, filename, printer):
    """Only a matching job on the selected printer is evidence of a start.

    Closing the dialog, an old job or a generic success message is insufficient.
    """
    if observation.get('source_kind') != 'live_window_capture':
        return 'unknown'
    if observation.get('stage_candidate') == 'send_dialog':
        return 'unknown'
    text = '\n'.join(observation.get('visible_text_lines', []))
    stem = filename.removesuffix('.gcode.3mf')
    if (observation.get('printer_label_candidates') == [printer]
            and re.search(r'(?<![A-Za-z0-9-])' + re.escape(stem) + r'(?![A-Za-z0-9-])', text)):
        if re.search(r'\b(failed|error|cancelled|canceled)\b', text, re.I):
            return 'failed'
        if re.search(r'\b(printing|preparing|running)\b', text, re.I):
            return 'started'
    return 'unknown'


def send_once(staged, digest, expected_path, output, preparation, result):
    expected = validate_profile(json.loads(expected_path.read_text(encoding='utf-8-sig')))
    # Bind Send to the filename verified immediately before this run's Print click.
    if (preparation.get('status') != 'stopped_before_Send'
            or preparation.get('clicked') != 'Print'
            or preparation.get('file') != str(staged.resolve())
            or preparation.get('sha256') != digest):
        raise RuntimeError('今回のファイルの印刷確認画面に到達していません。')
    previous = json.loads((Path(preparation['send_observation_directory']) / 'analysis.json').read_text(encoding='utf-8'))
    plan = plan_send(previous, expected)
    check_cancel(output)
    fresh = observe(output / 'send-recheck', expected_path)
    if plan_send(fresh, expected) != plan or fresh['window_reference'] != previous['window_reference']:
        raise RuntimeError('送信画面が変わりました。送信を停止しました。')
    if hashlib.sha256(staged.read_bytes()).hexdigest() != digest:
        raise RuntimeError('送信するファイルが変更されています。')
    check_cancel(output)
    # Atomically race cancellation against dispatch. Whichever wins is definitive.
    with (output / 'dispatch.decision').open('x', encoding='utf-8') as decision:
        decision.write('send'); decision.flush()
        import os
        os.fsync(decision.fileno())
    result.update(status='unknown', send_attempted=True)
    save(output / 'result.json', result)
    _click_verified_button(fresh, plan, 'send_dialog', verify_dialog=True)
    result.update(send_clicked=True, message='Sendを押しました。プリンターの状態を確認しています…')
    save(output / 'result.json', result)
    deadline = time.monotonic() + 180
    for index in range(180):
        if time.monotonic() > deadline:
            break
        if index:
            time.sleep(1)
        after = observe(output / f'sent-{index}', expected_path)
        result['observed_stage'] = after['stage_candidate']
        outcome = classify_outcome(after, staged.name, expected['printer_label'])
        if outcome != 'unknown':
            result['status'] = outcome
            break
        if after.get('blocking_message_candidates') and after['stage_candidate'] == 'send_dialog':
            result['send_errors'] = after['blocking_message_candidates']
            break
    result['message'] = {'started': 'プリンターで今回の印刷開始を確認しました。',
                         'failed': '今回の印刷の停止・失敗を検出しました。プリンターを確認してください。'}.get(
        result['status'], 'Sendを押しました。開始結果はBambu Handyまたはプリンター本体で確認してください。自動再送はしません。')


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {'mode': 'execute_print' if args.execute_print else 'dry_run', 'automatic_retry': False,
              'send_clicked': False, 'status': 'preparing'}
    try:
        with (output / 'run.started').open('x', encoding='utf-8') as started:
            started.write(datetime.now(timezone.utc).isoformat())
        expected = args.expected.resolve(strict=True)
        profile = validate_profile(json.loads(expected.read_text(encoding='utf-8-sig')))
        compatible = compatible_copy(args.file.resolve(strict=True), output / 'compatible.gcode.3mf')
        staged, digest = create_staged_job(compatible, output)
        result.update(staged_file=str(staged), sha256=digest, printer=profile['printer_label'])
        if args.execute_print:
            with desktop_lock():
                check_cancel(output)
                execute_import(staged, digest, expected, output, result)
                send_once(staged, digest, expected, output, result.get('preparation', {}), result)
        else:
            result.update(status='planned_no_GUI_actions', message='取り込み・Sendは実行していません。')
    except Exception as exc:
        attempted = (output / 'dispatch.decision').exists() and (output / 'dispatch.decision').read_text(encoding='utf-8') != 'cancel'
        result.update(status='unknown' if attempted else 'failed', error=str(exc),
                      message=('開始結果が不明です。再送せずBambu Handyまたは本体を確認してください。' if attempted else str(exc)))
        if (output / 'dispatch.decision').exists() and not attempted:
            result.update(status='cancelled', message='送信をキャンセルしました。')
    save(output / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-print', action='store_true', help='Import, Print and Send once; starts the real printer.')
    result = run(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] in ('planned_no_GUI_actions', 'started') else 1)
