# -*- coding: utf-8 -*-
"""行の末尾の自動の候補が出ている時の F5 は、同じ位置・同じ中身のまま焦点を移して1つ目を選ぶ（2026-11-21 17:48Z うにさん
「左に出た候補の欄が右に移動したのがよくなかった。同じ個所でF5フォーカスさせる」）。もう一度 F5 で今までどおり左の語へ。
CN_F5_FOCUS_IN_PLACE=0 で前の形。作り物の候補の口と作った例文だけ。tools_local/run_on_desktop.py で回す。"""
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
    import auto_candidates as AC
    from session import new_tab
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='今日は本を読みました' + chr(10) + '二行目です')]), ensure_ascii=False), encoding='utf-8')
    f5_predict.set_provider(lambda a, w, row, col, before: ['予測A', '予測B', '予測C'])
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
        root.geometry('900x500+-4000+40')
        end = time.monotonic() + 60
        while time.monotonic() < end and (a._foreground_analysis_pending() or len(a.line_units) < 1 or not a.line_units[0]):
            pump(0.1)
        ed = a.editor
        ed.winfo_pointerxy = lambda: (-20000, -20000)
        with patch.object(root, 'focus_get', lambda: ed):
            ed.mark_set('insert', '1.end')
            a._dropdown_passive = 'line_end'
            a._f5_predict_open(ed, 1, 10, 'main')
            a._dropdown_passive = None
            pump(0.2)
            dd = a._dropdown
            parts = a._dropdown_parts
            out['opened'] = dd is not None and parts.get('passive') == 'line_end'
            before_geo = (dd.winfo_rootx(), dd.winfo_rooty(), dd.winfo_width(), dd.winfo_height()) if dd else None
            items_before = list(parts['lb'].get(0, 'end')) if parts else []
            f5 = NS(widget=ed, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0)
            AC.on_key(a, f5)                                    # 本物の F5 と同じく、先に auto_candidates が見る
            a._on_f2_candidates(f5); pump(0.2)
            parts2 = a._dropdown_parts or {}
            lb = parts2.get('lb')
            out['same_window'] = a._dropdown is dd and dd is not None
            try:
                out['same_place'] = (dd.winfo_rootx(), dd.winfo_rooty(), dd.winfo_width(), dd.winfo_height()) == before_geo
            except Exception:
                out['same_place'] = False                          # 前の形: 閉じて別の所に開き直した
            if lb is None:
                out.update(same_items=False, focused=False, selected=None, passive_after=parts2.get('passive'),
                           inserted=ed.get('1.0', '1.end'), plain_f5=None, errors=errors)
                open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False)); os._exit(0)
            out['same_items'] = (list(lb.get(0, 'end')) if lb is not None else None) == items_before
            out['focused'] = lb is not None and str(lb.tk.call('focus', '-lastfor', lb._w)) == lb._w
            out['selected'] = list(lb.curselection()) if lb is not None else None
            out['passive_after'] = parts2.get('passive')
            # Enter で1つ目が入る
            if not out['same_window']:
                out.update(inserted=ed.get('1.0', '1.end'), plain_f5=None, errors=errors)
                open('child_out.json', 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False)); os._exit(0)
            lb.event_generate('<Return>'); pump(0.2)
            out['inserted'] = ed.get('1.0', '1.end')
            a._close_dropdown(); pump(0.1)
            # 一覧が出ていない時の F5 は今まで通り（予測で開き、選んだ形）
            ed.mark_set('insert', '2.end')
            a._on_f2_candidates(NS(widget=ed, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0)); pump(0.2)
            p3 = a._dropdown_parts or {}
            out['plain_f5'] = [a._dropdown is not None, p3.get('passive'), list(p3['lb'].curselection()) if p3.get('lb') is not None else None]
            a._close_dropdown(); pump(0.1)
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
    d = Path(tempfile.mkdtemp(prefix='cn-f5place-'))
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
    def test_f5_focuses_the_list_in_place(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertTrue(got['opened'], got)
        self.assertTrue(got['same_window'], got)                 # 閉じて開き直さない
        self.assertTrue(got['same_place'], got)                  # 同じ位置
        self.assertTrue(got['same_items'], got)                  # 同じ中身
        self.assertTrue(got['focused'], got)                     # 焦点を移す
        self.assertEqual(got['selected'], [0], got)              # 1つ目を選んだ形
        self.assertIsNone(got['passive_after'], got)
        self.assertEqual(got['inserted'], '今日は本を読みました予測A', got)   # Enter で入る
        self.assertEqual(got['plain_f5'], [True, None, [0]], got)            # 一覧が出ていない時の F5 は今まで通り

    def test_switch_back(self):
        got = run_child(self, {'CN_F5_FOCUS_IN_PLACE': '0'})
        self.assertFalse(got['same_window'] and got['focused'], got)


if __name__ == '__main__':
    unittest.main()
