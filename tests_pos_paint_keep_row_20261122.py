# -*- coding: utf-8 -*-
"""品詞ごとのフォントを後から付けて行の高さが変わっても、カーソルの行を画面の同じ高さに残す（2026-11-22 01:56Z うにさん
「最終行ボタンを押してから、文字を打ち始めると位置が動く」）。飛んだ先の行は区切りの控えが後から届き、付いた所で行が伸びて、
カーソルの行が最大 28px 下へずれていた。CN_POS_PAINT_KEEP_CURSOR_ROW=0 で前の形。作った例文だけ。run_on_desktop で回す。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHILD = r'''
import json, os, sys, time, traceback
from pathlib import Path
def main():
    here = Path.cwd().resolve()
    assert not (here / 'vocabulary.json').exists()
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    from tests_tk_keys import deliver_key
    body = chr(10).join('%d行目の本文です。' % i for i in range(1, 301))
    (here / 'settings.json').write_text(json.dumps(dict(layout=os.environ.get('LAYOUT', 'split'), input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+-4000+40')
        pump(8)
        ed = a.editor
        root.focus_get = lambda: ed
        def y():
            d = ed.dlineinfo('insert')
            return d[1] if d else None
        def has_pos(r):
            # 字の無い行（最終行の後の空行など）はフォントが付きようがないので数えない（2026-11-23: その1行が
            # 「付いていない行」として最後まで残り、前置きの比べが時々成り立たなかった）
            if not ed.get('%d.0' % r, '%d.end' % r).strip():
                return True
            return any(str(t).startswith('pos_font') for t in ed.tag_names('%d.1' % r))
        a.last_line_btn.invoke(); pump(0.3)
        out['y_button'] = y()
        top = int(ed.index('@0,0').split('.')[0])
        out['bare_rows_after_jump'] = sum(1 for r in range(top, top + 10) if not has_pos(r))   # 後から付く行がある形か
        ys = []
        for letter in 'abcde':
            deliver_key(ed, '<KeyPress>', letter, ord(letter.upper()), char=letter)
            pump(0.6)
            ys.append(y())
        # 見えている行に後からフォントが付くまで待つ（決まった時間ではなく）
        end = time.monotonic() + 20
        while time.monotonic() < end and sum(1 for r in range(top, top + 10) if not has_pos(r)) > 2:
            pump(0.2)
            ys.append(y())
        pump(0.5)
        out['bare_rows_at_end'] = sum(1 for r in range(top, top + 10) if not has_pos(r))
        out['ys'] = ys
        out['y_settle'] = y()
        out['errors'] = errors
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False))
        os._exit(0)
if __name__ == '__main__':
    try:
        main()
    except Exception:
        open('child_out.json', 'w', encoding='utf-8').write(json.dumps({'error': traceback.format_exc()}))
        os._exit(1)
'''


def run_child(case, env_extra=None):
    here = Path(__file__).resolve().parent
    if here == Path(r'C:\CorrectNote') or (here / 'vocabulary.json').exists():
        case.skipTest('写しの中で回す')
    d = Path(tempfile.mkdtemp(prefix='cn-keeprow-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=240,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class InTheApp(unittest.TestCase):
    def check(self, layout):
        got = run_child(self, {'LAYOUT': layout})
        self.assertEqual(got['errors'], [], got)
        # 飛んだ先の行に後からフォントが付く形の時は、付いたことも見る。飛んだ時点で見えている行がもう塗られている時
        # （控えの答えで塗れた時）は、後から付く行が無いので、カーソルの行が動かないことだけを見る（2026-11-23）
        if got['bare_rows_after_jump'] > 0:
            self.assertLess(got['bare_rows_at_end'], got['bare_rows_after_jump'], got)   # 付いた（付いた後でも見る）
        self.assertLessEqual(got['bare_rows_at_end'], 1, got)               # 残るのは打っている行（答えを待つ間）だけ
        for v in got['ys'] + [got['y_settle']]:
            self.assertLessEqual(abs(v - got['y_button']), 1, got)            # カーソルの行は同じ高さのまま

    def test_split(self):
        self.check('split')

    def test_unified(self):
        self.check('unified')

    def test_switch_back(self):
        got = run_child(self, {'LAYOUT': 'unified', 'CN_POS_PAINT_KEEP_CURSOR_ROW': '0'})
        self.assertGreater(max(abs(v - got['y_button']) for v in got['ys'] + [got['y_settle']]), 1, got)   # 前の形: ずれる


if __name__ == '__main__':
    unittest.main()
