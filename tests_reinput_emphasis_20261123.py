# -*- coding: utf-8 -*-
"""再入力変換で開いている範囲の字を大きく見せる・始めた時に入力カーソルを光らせる（2026-11-23 10:40 うにさん
「再入力変換中の範囲を、フォントサイズ1.4倍にして、パラメータに出す。再入力変換開始時に、入力カーソルを移動時と同じように
色を付けて強調する」）。
・開いている間、範囲の字は本文の字の REINPUT_EMPHASIS_PERCENT ％（既定160・デバッグメニュー。はじめ140、2026-11-23 12:01
  うにさん「再入力変換の文字倍率を140から160に変更」）。閉じたら戻る
・範囲の字が変わっても（候補へ替えても）大きいまま
・分割表示の左右の行の高さがそろう・一番上の行が動かない
・始めた時、入力カーソルがカーソル移動の時と同じ色（editor_guides.flash_style）になる
CN_REINPUT_BIG_FONT=0・CN_REINPUT_CARET_FLASH=0 で前の形。作った文だけ。run_on_desktop で回す。"""
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
    import tkinter.font as tkfont
    from unittest.mock import Mock, patch
    import app, reinput, editor_guides
    from session import new_tab
    words = ['会議', '資料', '確認', '連絡', '予定', '作業', '準備', '報告', '検討', '変更']
    big = chr(10).join('%d行目は%sの%sを%sするための作った文です。' % (i + 1, words[i % 10], words[(i * 3 + 1) % 10],
                       words[(i * 7 + 2) % 10]) for i in range(40))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=big)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e))[-600:])
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1300x900+40+40')
        if os.environ.get('PERCENT'):
            a.REINPUT_EMPHASIS_PERCENT = int(os.environ['PERCENT'])
        ed, rv = a.editor, a.result_view
        end = time.monotonic() + 90
        while time.monotonic() < end and getattr(a, '_analyze_pos', 0) < 12:
            pump(0.5)
        pump(1.0)
        root.focus_force(); ed.focus_set(); pump(0.2)
        row = 10
        line = ed.get('%d.0' % row, '%d.end' % row)
        col = line.index('の') + 2                     # 2つ目の語の中
        ed.mark_set('insert', '%d.%d' % (row, col)); ed.see('insert'); pump(0.5)
        top_before = ed.index('@0,0')
        base = tkfont.Font(font=ed.cget('font')).actual('size')
        def sizes():
            got = []
            for tag in ed.tag_names():
                if str(tag).startswith('emph_reinput') and ed.tag_ranges(tag):
                    spec = ed.tag_cget(tag, 'font')
                    if spec:
                        got.append(abs(int(tkfont.Font(font=spec).actual('size'))))
            return got
        def aligned():
            bad = 0
            t = int(ed.index('@0,0').split('.')[0])
            for r in range(t, t + 20):
                d1, d2 = ed.dlineinfo('%d.0' % r), rv.dlineinfo('%d.0' % r)
                if d1 and d2 and abs(d1[1] - d2[1]) > 1:
                    bad += 1
            return bad
        flashes = []
        real_begin = editor_guides.EditorGuides._begin_flash
        def begin(self, pane):
            flashes.append(str(pane))
            real_begin(self, pane)
            flashes.append(str(pane.cget('insertbackground')))
        editor_guides.EditorGuides._begin_flash = begin
        r = a._reinput
        opened = r.start()
        pump(0.05)
        out['opened'] = bool(opened) and r.state is not None
        out['flash'] = list(flashes)
        out['flash_color'] = editor_guides.flash_style(ed)[0]
        out['base'] = abs(int(base))
        out['sizes_open'] = sizes()
        out['range'] = r.current() if r.state is not None else None
        pump(1.0)
        out['aligned_open'] = aligned()
        out['top_open'] = ed.index('@0,0')
        out['top_before'] = top_before
        # 範囲の字を替える（候補へ進めるのと同じく、範囲を書き換える）
        if r.state is not None:
            r._write(r.current() + 'あ')
            pump(0.5)
            out['sizes_changed'] = sizes()
        r.cancel() if r.state is not None else None
        pump(1.0)
        out['sizes_closed'] = sizes()
        out['aligned_closed'] = aligned()
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
    d = Path(tempfile.mkdtemp(prefix='cn-reinputemph-'))
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
    def test_big_while_open_and_flash(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertTrue(got['opened'], got)
        want = round(got['base'] * 1.6)
        self.assertTrue(got['sizes_open'] and all(abs(s - want) <= 1 for s in got['sizes_open']), got)    # 1.6倍（既定160）
        self.assertTrue(got['sizes_changed'] and all(abs(s - want) <= 1 for s in got['sizes_changed']), got)
        self.assertEqual(got['sizes_closed'], [], got)                         # 閉じたら戻る
        self.assertEqual(got['aligned_open'], 0, got)                          # 左右がそろう
        self.assertEqual(got['aligned_closed'], 0, got)
        self.assertEqual(got['top_open'], got['top_before'], got)              # 一番上の行は動かない
        self.assertEqual(got['flash'][1], got['flash_color'], got)            # カーソル移動と同じ色

    def test_parameter(self):
        got = run_child(self, {'PERCENT': '200'})
        self.assertTrue(got['opened'], got)
        want = round(got['base'] * 2.0)
        self.assertTrue(got['sizes_open'] and all(abs(s - want) <= 1 for s in got['sizes_open']), got)

    def test_switch_back(self):
        got = run_child(self, {'CN_REINPUT_BIG_FONT': '0', 'CN_REINPUT_CARET_FLASH': '0'})
        self.assertTrue(got['opened'], got)
        self.assertEqual(got['sizes_open'], [], got)                           # 前の形: 大きくしない
        self.assertEqual(got['flash'], [], got)                                # 前の形: 光らせない


if __name__ == '__main__':
    unittest.main()
