# -*- coding: utf-8 -*-
"""予測の一覧の横幅を、いちばん長い候補の字の幅に合わせて詰める（2026-11-23 うにさん「予測候補は横幅に余白があるなら、
横を短くする」）。前は「・」「※」のような短い候補でも、ほかの一覧と同じ半角20字ぶんの幅だった。
・行頭の予測（短い記号の候補）は前より狭い。どの候補の字も見切れない（一覧の字体で測った幅が収まる）
・語の再変換の一覧（予測でない一覧）は今までどおり
CN_PREDICT_FIT_WIDTH=0 で前の形。作った文だけ。run_on_desktop で回す。"""
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
    import app
    from session import new_tab
    text = '1行目は会議の資料を確認するための作った文です。' + chr(10) + chr(10) + '3行目です。'
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e))[-400:])
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+40+40')
        pump(4)
        ed = a.editor
        root.focus_get = lambda: ed
        root.clipboard_get = lambda **k: (_ for _ in ()).throw(tk.TclError('none'))   # クリップボードの字を候補に入れない
        def opened():
            parts = getattr(a, '_dropdown_parts', None) or {}
            lb = parts.get('lb')
            if lb is None:
                return None
            font = tkfont.Font(font=lb.cget('font'))
            labels = [str(x) for x in lb.get(0, 'end')]
            return dict(width=int(lb.cget('width')), labels=labels,
                        px_need=max(font.measure(x) for x in labels) if labels else 0,
                        px_have=lb.winfo_reqwidth())
        ed.mark_set('insert', '2.0'); pump(0.2)                 # 空の行の行頭 → 行頭の予測
        a._close_dropdown()
        out['opened'] = a._f5_predict_open(ed, 2, 0, 'main')
        pump(0.3)
        out['predict'] = opened()
        a._close_dropdown(); pump(0.2)
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
    d = Path(tempfile.mkdtemp(prefix='cn-fitwidth-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=200,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class FitWidth(unittest.TestCase):
    def test_predict_list_is_as_wide_as_its_longest_item(self):
        new = run_child(self)
        old = run_child(self, {'CN_PREDICT_FIT_WIDTH': '0'})
        self.assertEqual(new['errors'], [], new)
        self.assertTrue(new['opened'] and old['opened'], (new, old))
        self.assertEqual(new['predict']['labels'], old['predict']['labels'])          # 中身は同じ
        self.assertEqual(old['predict']['width'], 20, old)                            # 前の形: いつも半角20字ぶん以上
        self.assertLess(new['predict']['width'], old['predict']['width'], (new, old))  # 詰めた
        self.assertGreaterEqual(new['predict']['px_have'], new['predict']['px_need'], new)   # どの候補も見切れない


if __name__ == '__main__':
    unittest.main()
