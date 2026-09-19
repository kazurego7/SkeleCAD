"""Close only idle confirmation dialogs before a new URL import."""
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def plan_cleanup(screen):
    stage = screen.get('stage_candidate')
    if stage not in ('import_confirmation', 'send_dialog'):
        return None
    if screen.get('source_kind') != 'live_window_capture':
        raise RuntimeError('確認画面の状態を取得できません。')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(screen['observed_at'])).total_seconds()
    scope = screen.get('decision_scope', {})
    title = 'Import file' if stage == 'import_confirmation' else 'Send to print'
    if not 0 <= age <= 20 or scope.get('kind') != 'active_dialog' or scope.get('title') != title:
        raise RuntimeError('確認画面を特定できません。')
    label = 'Import Gcode 3MF' if stage == 'import_confirmation' else 'Send'
    if screen.get('send_button_loading'):
        return 'busy'
    if sum(b.get('text') == label for b in screen.get('green_button_candidates', [])) != 1:
        return 'busy'
    candidates = screen.get('cancel_button_candidates', [])
    if len(candidates) != 1 or screen.get('blocking_message_candidates'):
        raise RuntimeError('前回の確認画面を安全に閉じられません。')
    box = candidates[0]['bounds']
    left, top, right, bottom = scope['bounds']
    if not (left <= box[0] < box[2] <= right and top <= box[1] < box[3] <= bottom):
        raise RuntimeError('キャンセルボタンの位置を確認できません。')
    return {'action': 'cancel_previous_dialog', 'button': 'Cancel', 'bounds': [int(v) for v in box]}


def cleanup_previous_dialog(output, expected):
    from pywinauto import Desktop
    import win32api
    import win32process
    import pywintypes
    executable = os.path.normcase(str(Path(os.environ['LOCALAPPDATA']) / 'Programs/bambu-connect/Bambu Connect.exe'))
    windows = []
    for window in Desktop(backend='win32').windows():
        try:
            handle = win32api.OpenProcess(0x410, False, window.process_id())
            try:
                path = win32process.GetModuleFileNameEx(handle, 0)
            finally:
                handle.Close()
            if os.path.normcase(path) == executable and window.is_visible() and window.window_text().startswith('Bambu Connect'):
                windows.append(window)
        except (pywintypes.error, OSError):
            continue
    if not windows:
        return
    if len(windows) != 1:
        raise RuntimeError('Bambu Connectのウィンドウを1つにしてください。')
    # Establish the foreground before capturing, so activation cannot change button pixels.
    windows[0].set_focus()
    # Keep cursor hover/highlight overlays away from the buttons being compared.
    from pywinauto import mouse
    rect = windows[0].rectangle()
    mouse.move(coords=(rect.left + 32, rect.top + 12))
    from connect_prepare_rpa import observe, _click_verified_button
    clicked = False
    deadline = time.monotonic() + 30
    for index in range(30):
        if time.monotonic() > deadline:
            break
        current = observe(output / f'cleanup-{index}', expected)
        plan = plan_cleanup(current)
        if plan is None:
            return
        if plan == 'busy':
            raise RuntimeError('Bambu Connectで送信処理中です。完了してからもう一度お試しください。')
        if clicked:
            time.sleep(.1)
            continue
        fresh = observe(output / f'cleanup-{index}-recheck', expected)
        if plan_cleanup(fresh) != plan or fresh.get('window_reference') != current.get('window_reference'):
            continue
        (output / 'previous-dialog-close.attempted').write_text('Cancel', encoding='utf-8')
        _click_verified_button(fresh, plan, fresh['stage_candidate'])
        clicked = True
    raise RuntimeError('Bambu Connectが処理中、または前回の画面を閉じられません。送信が終わってから再実行してください。')
