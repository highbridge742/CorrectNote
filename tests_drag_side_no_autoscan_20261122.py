# -*- coding: utf-8 -*-
"""左ドラッグの選択で、マウスが欄の横（行番号の欄）へ出ても、選択を消して付け直す繰り返しをしない（2026-11-22 20:02 JST
うにさん「左クリックをドラッグして範囲選択しつつ、ひとつ上の行の行番号のところにカーソルを持ってくると、範囲が高速で
点滅していた」）。前は Tk の自動スクロール（tk::TextAutoScan）が 50ms ごとに横へ送り（折り返す欄なので動かない）、選択を
全部外して付け直していた。上下へ出た時の送りは今のまま。CN_DRAG_SIDE_NO_AUTOSCAN=0 で前の形。作った例文だけ。
run_on_desktop で回す。"""
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
    body = chr(10).join('%d行目の本文です。ここは作った文です。' % i for i in range(1, 80))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.002)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+-4000+40')
        pump(6)
        for name in ('editor', 'result_view'):
            w = getattr(a, name)
            g = a.editor_gutter if name == 'editor' else a.result_gutter
            root.focus_get = lambda w=w: w
            d10 = w.dlineinfo('10.0'); d9 = w.dlineinfo('9.0')
            x0, y0 = d10[0] + 60, d10[1] + d10[3] // 2
            y9 = d9[1] + d9[3] // 2
            gx = g.winfo_rootx() - w.winfo_rootx() + g.winfo_width() // 2      # 行番号の欄の上（欄の左の外）
            w.event_generate('<ButtonPress-1>', x=x0, y=y0)
            pump(0.05)
            for k in range(1, 6):
                w.event_generate('<B1-Motion>', x=x0 + 10 * k, y=y0, state=0x100)
                pump(0.02)
            calls = []
            cb = root.register(lambda *args: calls.append(' '.join(args[0].split()[1:4])))
            w.tk.call('trace', 'add', 'execution', w._w, 'enter', cb)
            w.event_generate('<B1-Motion>', x=gx, y=y9, state=0x100)
            w.event_generate('<B1-Leave>', x=gx, y=y9, state=0x100)
            starts = set()
            end = time.monotonic() + 1.0
            while time.monotonic() < end:
                root.update(); time.sleep(0.002)
                if w.tag_ranges('sel'):
                    starts.add(str(w.index('sel.first')))
            w.tk.call('trace', 'remove', 'execution', w._w, 'enter', cb)
            out[name] = dict(gx=gx, starts=sorted(starts), xscroll=sum(1 for c in calls if c.startswith('xview scroll')),
                             reselect=sum(1 for c in calls if c.startswith('tag remove sel')),
                             last=str(w.index('sel.last')) if w.tag_ranges('sel') else None)
            w.event_generate('<ButtonRelease-1>', x=gx, y=y9, state=0x100)
            pump(0.2)
            w.tag_remove('sel', '1.0', 'end')
        # 上へ出た時の送りは今のまま（Tk の自動スクロール）
        w = a.editor
        root.focus_get = lambda: w
        w.yview_moveto(0.3); pump(0.3)
        top = str(w.index('@0,0'))
        d = w.dlineinfo(top + ' +3l')
        w.event_generate('<ButtonPress-1>', x=d[0] + 60, y=d[1] + 5)
        pump(0.05)
        w.event_generate('<B1-Motion>', x=d[0] + 80, y=-20, state=0x100)
        w.event_generate('<B1-Leave>', x=d[0] + 80, y=-20, state=0x100)
        pump(0.6)
        out['up_top_before'] = top
        out['up_top_after'] = str(w.index('@0,0'))
        w.event_generate('<ButtonRelease-1>', x=d[0] + 80, y=-20, state=0x100)
        pump(0.2)
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
    d = Path(tempfile.mkdtemp(prefix='cn-dragside-'))
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
    def test_side_drag_does_not_repeat(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        for name in ('editor', 'result_view'):
            g = got[name]
            self.assertLess(g['gx'], 0, got)                       # 欄の左の外（行番号の欄の上）
            self.assertEqual(g['xscroll'], 0, got)                 # 横へ送る繰り返しが無い
            self.assertLessEqual(g['reselect'], 4, got)            # 選択を付け直すのは動いた時だけ（1回に tag remove が2つ）
            self.assertEqual(g['starts'], ['9.0'], got)            # マウスの行（9行目）まで伸びたまま
            self.assertEqual(g['last'], '10.5', got)
        self.assertNotEqual(got['up_top_after'], got['up_top_before'], got)   # 上へ出た時は今までどおり送る

    def test_switch_back(self):
        got = run_child(self, {'CN_DRAG_SIDE_NO_AUTOSCAN': '0'})
        self.assertGreater(got['editor']['xscroll'], 3, got)       # 前の形: 50ms ごとに横へ送って選び直していた
        self.assertGreater(got['editor']['reselect'], 3, got)


if __name__ == '__main__':
    unittest.main()
