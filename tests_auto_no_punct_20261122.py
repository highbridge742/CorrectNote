# -*- coding: utf-8 -*-
"""自動で出す予測（行の末尾の自動の候補・続けて出す予測）に、字の無い記号だけの項目（・・・ … ― など）を出さない
（2026-11-22 うにさん「候補の中にある・・・は…出ないようにしたい」）。「■移動」の後に同梱の表が「・」を次の字に挙げ、
IME が「・」の予測として「・・・」を返していた。うにさんの行頭・文末の候補の並びはそのまま。F5 を押して開く予測もそのまま。
CN_AUTO_NO_PUNCT_ITEMS=0 で前の形。作り物の候補の口と作った例文だけ。tools_local/run_on_desktop.py で回す。"""
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
    from types import SimpleNamespace as NS
    from unittest.mock import Mock, patch
    import app, f5_predict
    from session import new_tab
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='■移動' + chr(10) + '二行目です')]), ensure_ascii=False), encoding='utf-8')
    mode = {'custom': None, 'close': None}
    def provider(a, w, row, col, before):
        a._f5_custom_items = mode['custom']
        a._f5_close_items = mode['close']
        if mode['close']:
            return list(mode['close']) + ['・・・', '後']
        if mode['custom']:
            return list(mode['custom']) + ['・・・', '後']
        return ['後', '・・・', 'する', '…', '―', '・・・は', '→']
    f5_predict.set_provider(provider)
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None), \
            patch.object(f5_predict, 'clipboard_text', lambda app: None):
        a = app.CorrectNoteApp(root)
        root.geometry('900x500+-4000+40')
        end = time.monotonic() + 60
        while time.monotonic() < end and (a._foreground_analysis_pending() or len(a.line_units) < 1):
            pump(0.1)
        ed = a.editor
        with patch.object(root, 'focus_get', lambda: ed):
            def shown():
                parts = getattr(a, '_dropdown_parts', None) or {}
                lb = parts.get('lb')
                got = list(lb.get(0, 'end')) if (lb is not None and a._dropdown is not None) else None
                a._close_dropdown(); pump(0.05)
                return got
            def auto():
                ed.mark_set('insert', '1.end')
                a._dropdown_passive = 'line_end'
                try:
                    a._f5_predict_open(ed, 1, 3, 'main')
                finally:
                    a._dropdown_passive = None
                return shown()
            out['auto'] = auto()
            ed.mark_set('insert', '1.end')
            a._on_f2_candidates(NS(widget=ed, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0)); pump(0.2)
            out['f5'] = shown()
            ed.mark_set('insert', '1.end')
            a._f5_predict_insert(ed, 'main', '', kind=None); pump(0.2)
            out['chain'] = shown()
            mode['custom'] = ['…', '。']
            out['auto_custom'] = auto()
            mode['custom'] = None; mode['close'] = ['」']
            out['auto_close'] = auto()                          # 閉じ括弧は記号だけでも落とさない（17:16Z）
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
    d = Path(tempfile.mkdtemp(prefix='cn-punct-'))
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
    def test_no_symbol_only_items_in_auto_lists(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertEqual(got['auto'], ['後', 'する', '・・・は'], got)          # 行末の自動: 記号だけの項目は出さない
        self.assertEqual(got['chain'], ['後', 'する', '・・・は'], got)         # 続けて出す予測も
        self.assertIn('・・・', got['f5'], got)                               # F5 を押して開く予測はそのまま
        self.assertEqual(got['auto_custom'], ['…', '。', '後'], got)           # 行頭・文末の候補の並びの記号はそのまま
        self.assertEqual(got['auto_close'], ['」', '後'], got)                 # 閉じ括弧はそのまま（CN_PREDICT_CLOSE_BRACKET）

    def test_switch_back(self):
        got = run_child(self, {'CN_AUTO_NO_PUNCT_ITEMS': '0'})
        self.assertIn('・・・', got['auto'], got)


if __name__ == '__main__':
    unittest.main()
