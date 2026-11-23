# -*- coding: utf-8 -*-
"""最終行ボタンで最終行を窓の真ん中に寄せた後、打っても本文の位置が動かない（2026-11-22 02:53Z うにさん「最終行を押した
時点と、そこからスペースを押した画像です。縦がずれている。補正は済んでいる」）。真ん中に寄せるために足した下の余白を
打鍵のたびに外していたので、末尾の空行が窓の半分より少ない時は表示が詰まって、本文が下へずれた。余白は打っても残し、
スクロールで外す。CN_NAV_EDIT_KEEP_VIEW=0 で前の形。作った例文だけ。run_on_desktop で回す。"""
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
    app.CorrectNoteApp.TRAILING_BLANK_LINES = 5          # 末尾の空行が窓の半分より少ない形（うにさんの窓は縦に長い）
    body = chr(10).join('%d行目の本文です。' % i for i in range(1, 58))
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
        def y(w=ed, row=55):
            d = w.dlineinfo('%d.0' % row)
            return d[1] if d else None
        a.last_line_btn.invoke(); pump(0.5)
        out['insert'] = ed.index('insert')
        out['padded'] = bool(a._navigation_padding_active and ed.tag_ranges('navigation_tail'))
        out['y_button'] = [y(), y(a.result_view)]
        ys = []
        for seq, keysym, code, ch in (('<KeyPress>', 'space', 32, ' '), ('<KeyPress>', 'a', 65, 'a'),
                                      ('<Return>', 'Return', 13, '\r'), ('<Return>', 'Return', 13, '\r'),
                                      ('<BackSpace>', 'BackSpace', 8, ''), ('<KeyPress>', 'b', 66, 'b')):
            deliver_key(ed, seq, keysym, code, char=ch)
            pump(0.8)
            ys.append([y(), y(a.result_view)])
        pump(2.0)
        ys.append([y(), y(a.result_view)])
        out['ys'] = ys
        out['typed'] = ed.get('58.0', '60.end')
        out['tail_after_typing'] = [str(i) for i in ed.tag_ranges('navigation_tail')]
        out['last_row'] = str(ed.index('end-2c linestart'))
        a._on_wheel_units(-1); pump(0.5)                 # スクロールすれば寄せを外す（前と同じ）
        out['after_wheel'] = dict(active=bool(a._navigation_padding_active), tail=[str(i) for i in ed.tag_ranges('navigation_tail')],
                                  head=[str(i) for i in ed.tag_ranges('navigation_head')])
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
    d = Path(tempfile.mkdtemp(prefix='cn-navkeep-'))
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
        self.assertEqual(got['insert'], '58.0', got)
        self.assertTrue(got['padded'], got)                                   # 真ん中に寄せた形（余白で支えている）
        self.assertEqual(got['typed'], ' a\nb\n', got)                      # 改行2つ → BackSpace → b
        panes = 2 if layout == 'split' else 1
        for row in got['ys']:
            for k in range(panes):
                self.assertLessEqual(abs(row[k] - got['y_button'][k]), 1, got)   # 打っても・改行しても本文は動かない
        self.assertEqual(got['tail_after_typing'][0], got['last_row'], got)  # 余白は最終行に付け直してある
        self.assertEqual(got['after_wheel'], dict(active=False, tail=[], head=[]), got)

    def test_split(self):
        self.check('split')

    def test_unified(self):
        self.check('unified')

    def test_switch_back(self):
        got = run_child(self, {'LAYOUT': 'split', 'CN_NAV_EDIT_KEEP_VIEW': '0'})
        self.assertGreater(max(abs(r[0] - got['y_button'][0]) for r in got['ys']), 1, got)   # 前の形: 打つと下へずれる


if __name__ == '__main__':
    unittest.main()
