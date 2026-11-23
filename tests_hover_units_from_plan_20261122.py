# -*- coding: utf-8 -*-
"""控えから戻した行（答えはあるが語の切れ目の控えが空の行）でも、オンマウスは品詞のフォントの控えの切れ目で語1つを出す
（2026-11-22・CN_HOVER_UNITS_FROM_PLAN）。解析の子には尋ねず、解き直しも起こさない。控えが無ければ今どおり出さない。
作った例文だけ。tools_local/run_on_desktop.py で回す。"""
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
    import app, analysis_async
    import auto_candidates as AC
    from session import new_tab
    body = chr(10).join(['きょうはいい天気です。', '会議の資料を作る', 'まだ解いていない行'])
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    redo = []
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_redo_row_now', lambda self, i: redo.append(i) or False):
        a = app.CorrectNoteApp(root)
        root.geometry('1000x500+-4000+40')
        end = time.monotonic() + 60
        while time.monotonic() < end and (a._foreground_analysis_pending() or len(a.line_results) < 2 or not all(a.line_results[:2])):
            pump(0.1)
        pump(1.5)
        ed = a.editor
        import boundary_colors
        out['plan_ready'] = boundary_colors.plan_for(a, ed, 2, ed.get('2.0', '2.end')) is not None
        # 控えから戻した行の形: 答えはあるが、語の切れ目の控えが空
        a._suspect_units_cache = {}
        asked = []
        real_ask = analysis_async.ask_child
        def at(index):
            ed.see(index); root.update_idletasks()
            box = ed.bbox(index)
            return NS(x=box[0] + 2, y=box[1] + 2, x_root=ed.winfo_rootx() + box[0] + 2, y_root=ed.winfo_rooty() + box[1] + 2,
                      widget=ed, state=0)
        # 語の切れ目（suspect_units）を子に尋ねたかを見る（一覧の候補を作る問い合わせは、ふだんのオンマウスと同じ）
        def _rec_ask(*a2, **k):
            req = a2[1] if len(a2) > 1 else k.get('request')
            if isinstance(req, dict) and req.get('kind') == 'suspect_units':
                asked.append(1)
            return real_ask(*a2, **k)
        with patch.object(analysis_async, 'ask_child', _rec_ask):
            ev = at('2.1')
            hit = AC._hit(a, ed, ev)
            out['word'] = hit[2].get('text') if hit else None
            out['from_plan'] = bool(hit and hit[2].get('_from_plan'))
            # 語の上で止まった: 一覧を開いても、解析の子に尋ねず、解き直しも起こさない
            redo.clear()                                   # 起動の時のカーソルの行の分は数えない
            if hit:
                ed.winfo_pointerxy = lambda: (ev.x_root, ev.y_root)
                AC.hover_show(a, ed, AC._key(hit), dict(x=ev.x, y=ev.y, x_root=ev.x_root, y_root=ev.y_root))
                pump(0.2)
                AC.close(a); a._close_dropdown()
            out['asked'] = len(asked)
            out['redo'] = list(redo)
            out['redo_restored'] = '_redo_row_now' not in a.__dict__
            # 品詞の控えが無い行（まだ解いていない）: 出さない
            a._ctrl_boundary_plans = {}
            for w in (ed,):
                colors = getattr(w, '_correctnote_boundary_colors', None)
                if colors is not None:
                    colors._painted.clear(); colors._last_plans.clear()
            hit = AC._hit(a, ed, at('3.1'))
            out['no_plan'] = hit[2].get('text') if hit else None
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
    d = Path(tempfile.mkdtemp(prefix='cn-hoverplan-'))
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
    def test_word_from_the_pos_plan(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertTrue(got['plan_ready'], got)
        self.assertTrue(got['from_plan'], got)                     # 語の切れ目の控えが空でも、品詞の控えの切れ目で
        self.assertTrue(got['word'] and len(got['word']) <= 4, got)  # 語1つ（行まるごとではない）
        self.assertEqual(got['asked'], 0, got)                     # 解析の子に尋ねない
        self.assertEqual(got['redo'], [], got)                     # 解き直しを起こさない
        self.assertTrue(got['redo_restored'], got)
        self.assertIsNone(got['no_plan'], got)                     # 品詞の控えも無い行は今どおり出さない

    def test_switch_back(self):
        got = run_child(self, {'CN_HOVER_UNITS_FROM_PLAN': '0'})
        self.assertIsNone(got['word'], got)


if __name__ == '__main__':
    unittest.main()
