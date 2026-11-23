# -*- coding: utf-8 -*-
"""簡易入力でも長押しで語を選ぶ・選んだ範囲をドラッグで移す（2026-11-20 うにさん「簡易入力でも、長押し選択とドラッグ移動が
できるようにする」・drag_move）。アプリを試しの写し（プログラムと同梱の物だけ・作った例文）で子として起こし、簡易入力の窓を
開いて、その欄の束縛の手続きを直に呼ぶ。指の押しは、その欄の窓へだけ指の印付きの知らせを送って確かめる（ほかの窓へは
送らない・クリップボードは触らない）。"""
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


def child():
    import tkinter as tk
    from types import SimpleNamespace as NS
    from unittest.mock import Mock, patch
    import app
    import drag_move
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-quick-longpress-test-isolated').is_file()
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                        encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='本文の作り物です。')]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x600+40+40')
        pump(1.0)
        a._show_quick_capture()
        pump(0.5)
        t = a._quick_text
        d = getattr(t, '_cn_drag_move', None)
        out['installed'] = d is not None
        tags = list(t.bindtags())
        out['order'] = [x for x in tags if x in ('CnMouse', drag_move.TAG, str(t), 'Text')]
        if d is not None:
            out['body'] = d.body
            out['on_change_none'] = d.on_change is None
            t.delete('1.0', 'end')
            t.insert('1.0', 'alpha beta gamma delta')
            t.edit_separator()
            pump(0.2)
            calls = []
            a._on_change = lambda *x: calls.append(1)            # 本文の解き直しを呼ばない
            # 本文のタイトルにカーソルがあっても、簡易入力の長押しは効く（本文の決まりを持ち込まない）
            a._title_toc = NS(inline=True, has_cursor=lambda: True)
            x, y, w, h = t.bbox('1.7')
            with patch.object(drag_move, 'LONGPRESS_MS', 30):
                d.press(NS(x=x + 2, y=y + h // 2, state=0))
                pump(0.15)
            out['long_press'] = t.get('sel.first', 'sel.last') if t.tag_ranges('sel') else ''
            d.release(NS(x=x + 2, y=y + h // 2, state=0))
            # 掴んで行末へ移す
            x, y, w, h = t.bbox('1.7')
            grab = NS(x=x + w // 2, y=y + h // 2, state=0)
            out['grab'] = d.press(grab)
            d.motion(NS(x=grab.x + 30, y=grab.y, state=0, x_root=t.winfo_rootx() + grab.x + 30,
                        y_root=t.winfo_rooty() + grab.y))
            out['dragging'] = d.state
            x, y, w, h = t.bbox('1.21')
            d.release(NS(x=x + w + 1, y=y + h // 2, state=0))
            out['moved'] = t.get('1.0', 'end-1c')
            t.edit_undo()
            out['undone'] = t.get('1.0', 'end-1c')
            out['main_on_change_calls'] = len(calls)
            # 指の押し: 窓の手続きが覚えた印で、掴まない・長押しの時計を立てない
            if sys.platform == 'win32':
                import paper_window as P
                user32 = P._load()[1]
                t.tag_remove('sel', '1.0', 'end')
                t.tag_add('sel', '1.6', '1.10')
                with patch.object(user32, 'GetMessageExtraInfo', lambda: 0xFF515780):
                    user32.PostMessageW(int(t.winfo_id()), P.WM_LBUTTONDOWN, 0, ((300 & 0xFFFF) << 16) | 300)
                    pump(0.1)
                out['touch_seen'] = P.press_is_touch(t)
                x, y, w, h = t.bbox('1.7')
                out['touch_grab'] = d.press(NS(x=x + w // 2, y=y + h // 2, state=0))
                out['touch_timer'] = d.timer is not None
                with patch.object(user32, 'GetMessageExtraInfo', lambda: 0):
                    user32.PostMessageW(int(t.winfo_id()), P.WM_LBUTTONDOWN, 0, ((300 & 0xFFFF) << 16) | 300)
                    pump(0.1)
                out['mouse_seen'] = P.press_is_touch(t)
        assert not errors, errors
        print('QUICK_DRAG', json.dumps(out), flush=True)
        a._close_quick_capture()
        pump(0.2)
        a._on_close()


def run_child(test, env=None):
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-quick-longpress-') as directory:
        dest = Path(directory).resolve()
        for entry in source.iterdir():
            if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                shutil.copy2(entry, dest / entry.name)
        (dest / '.ui-quick-longpress-test-isolated').touch()
        environ = dict(os.environ)
        environ.update(env or {})
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                             cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ,
                             encoding='utf-8', errors='replace', timeout=240)
        test.assertEqual(run.returncode, 0, run.stdout[-3000:])
        line = [l for l in run.stdout.splitlines() if l.startswith('QUICK_DRAG ')]
        test.assertTrue(line, run.stdout[-3000:])
        return json.loads(line[0][len('QUICK_DRAG '):])


class QuickLongPressDrag(unittest.TestCase):
    def test_quick_window_selects_and_moves_like_the_body(self):
        got = run_child(self)
        self.assertTrue(got['installed'], got)
        self.assertEqual(got['order'][:2], ['CnMouse', 'CnDragMove'], got)        # 本文の欄と同じ束縛の順
        self.assertFalse(got['body'], got)
        self.assertTrue(got['on_change_none'], got)
        self.assertEqual(got['long_press'].strip(), 'beta', got)                  # 長押しで語（タイトルの決まりは見ない）
        self.assertEqual(got['grab'], 'break', got)
        self.assertEqual(got['dragging'], 'dragging', got)
        self.assertEqual(got['moved'], 'alpha  gamma deltabeta', got)
        self.assertEqual(got['undone'], 'alpha beta gamma delta', got)            # Undo 1回で戻る
        self.assertEqual(got['main_on_change_calls'], 0, got)                     # 本文の解き直しは呼ばない
        if sys.platform == 'win32':
            self.assertTrue(got['touch_seen'], got)
            self.assertIsNone(got['touch_grab'], got)                             # 指の押しは掴まない
            self.assertFalse(got['touch_timer'], got)                             # 長押しの時計も立てない
            self.assertFalse(got['mouse_seen'], got)

    def test_switch_back(self):
        got = run_child(self, {'CN_QUICK_DRAG': '0'})
        self.assertFalse(got['installed'], got)
        self.assertNotIn('CnDragMove', got['order'], got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
