# -*- coding: utf-8 -*-
"""最終行で打った時、終端の二重罫線を字の上に1コマも重ねない（2026-11-23 うにさん「最終行で文字を打って表示された際に、
二重罫線が文字の上に一瞬映るのが残ってます」）。
罫線は欄の上に place で置いた2本の Frame（_end_rule_line・_end_rule_second_line。字と一緒には動かない）。
打鍵・IME の確定の道（tk::TextInsert）・まとめて入れる（貼り付けと同じ insert）の直後から 1.5 秒、Tk の知らせを
1つ処理するごとに、両方の欄で「罫線の Frame の実際の位置（winfo_y・高さ）」と「字のある行の表示の位置（dlineinfo）」を比べ、
重なった回数を数える。場面: 罫線の行（最後の字の行の次の空行）で打つ・最後の字の行の末尾で打って折り返す・改行してから打つ。
CN_END_RULE_HIDE_BEFORE=0 で前の形。作った文だけ。run_on_desktop で回す。"""
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
    import _tkinter
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    from tests_tk_keys import deliver_key
    body = chr(10).join('%d行目の本文です。' % i for i in range(1, 13))
    (here / 'settings.json').write_text(json.dumps(dict(layout=os.environ.get('LAYOUT', 'split'), input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {'cases': []}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+40+40')
        pump(6)
        ed = a.editor
        root.focus_get = lambda: ed
        panes = [w for w in (ed, getattr(a, 'result_view', None)) if w is not None]
        def overlaps():
            hits = []
            for w in panes:
                try:
                    if not w.winfo_ismapped():
                        continue
                    frames = [f for f in (getattr(w, '_end_rule_line', None), getattr(w, '_end_rule_second_line', None))
                              if f is not None and f.winfo_ismapped()]
                    if not frames:
                        continue
                    last = int(str(w.index('end-1c')).split('.')[0])
                    top = int(str(w.index('@0,0')).split('.')[0])
                    for r in range(max(1, top), last + 1):
                        d = w.dlineinfo('%d.0' % r)
                        if d is None:
                            continue
                        if not w.get('%d.0' % r, '%d.end' % r).strip():
                            continue
                        # 行の全部の表示行（折り返し）: 行頭の dlineinfo から行末の dlineinfo まで
                        e = w.dlineinfo('%d.end' % r) or d
                        y0, y1 = d[1], e[1] + e[3]
                        for f in frames:
                            fy, fh = f.winfo_y(), f.winfo_height()
                            if fy < y1 - 1 and fy + fh > y0 + 1:
                                hits.append((w is ed, r, fy, y0, y1))
                except tk.TclError:
                    pass
            return hits
        def watch(seconds):
            seen = []
            end = time.monotonic() + seconds
            n = 0
            while time.monotonic() < end:
                if not root.tk.dooneevent(_tkinter.DONT_WAIT):
                    time.sleep(0.002)
                n += 1
                h = overlaps()
                if h:
                    seen.append(h[0])
            return seen, n
        def settle_rule():
            end = time.monotonic() + 15
            while time.monotonic() < end:
                f = ed._end_rule_line
                if f.place_info():
                    break
                pump(0.1)
            pump(0.5)
        def typed(chars):
            for ch in chars:
                deliver_key(ed, '<KeyPress>', ch, 0, char=ch)
        def ime(text):
            root.tk.call('tk::TextInsert', ed._w, text)
        def bulk(text):
            ed.insert('insert', text)
            ed.event_generate('<<Modified>>')
        def last_text():
            return max(r for r in range(1, int(ed.index('end-1c').split('.')[0]) + 1) if ed.get('%d.0' % r, '%d.end' % r).strip())
        cases = [
            ('rule_row_key', lambda: ed.mark_set('insert', '%d.0' % (last_text() + 1)), lambda: typed('かいぎ')),
            ('rule_row_ime', lambda: ed.mark_set('insert', '%d.0' % (last_text() + 1)), lambda: ime('会議の資料')),
            ('rule_row_bulk', lambda: ed.mark_set('insert', '%d.0' % (last_text() + 1)), lambda: bulk('貼り付けた行です。' * 3)),
            ('last_row_wrap', lambda: ed.mark_set('insert', '%d.end' % last_text()), lambda: ime('長い字を足して折り返す。' * 12)),
            ('enter_then_type', lambda: ed.mark_set('insert', '%d.end' % last_text()),
             lambda: (deliver_key(ed, '<KeyPress>', 'Return', 13, char=chr(13)), typed('あ'))),
        ]
        for name, place, act in cases:
            place()
            for w in panes:
                w.yview_moveto(0.0)
            ed.see('insert')
            ed.focus_force()
            pump(0.4)
            settle_rule()
            ready = [bool(ed._end_rule_line.place_info()), str(ed.index('insert'))]
            act()
            hits, n = watch(float(os.environ.get("WATCH_S", "6")))
            out['cases'].append(dict(name=name, ready=ready, hits=len(hits), first=hits[:3], loops=n,
                                     shown_after=bool(ed._end_rule_line.place_info())))
            pump(0.5)
        out['errors'] = errors[:3]
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
    d = Path(tempfile.mkdtemp(prefix='cn-endflash-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    with open(d / 'child_err.txt', 'w', encoding='utf-8', errors='replace') as err:
        r = subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=240,
                           stdout=subprocess.DEVNULL, stderr=err)
    if not (d / 'child_out.json').exists():
        case.fail('child rc=%s %s' % (r.returncode, (d / 'child_err.txt').read_text(encoding='utf-8', errors='replace')[-3000:]))
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    if os.environ.get('CN_PROBE_OUT'):
        Path(os.environ['CN_PROBE_OUT']).write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding='utf-8')
    return got


class NoFlash(unittest.TestCase):
    def check(self, layout):
        got = run_child(self, {'LAYOUT': layout})
        self.assertEqual(got['errors'], [], got)
        for c in got['cases']:
            self.assertTrue(c['ready'][0], c)                       # 罫線が出ている所から打ち始める
            self.assertEqual(c['hits'], 0, c)                       # 1コマも字に重ならない
        return got

    def test_split(self):
        self.check('split')

    def test_unified(self):
        self.check('unified')


if __name__ == '__main__':
    unittest.main()
