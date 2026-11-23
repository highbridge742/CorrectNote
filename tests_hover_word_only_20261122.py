# -*- coding: utf-8 -*-
"""オンマウスは語1つの時だけ・URL の上では出さない（2026-11-22 うにさん「未解析行にオンマウスすると行全体が選択されて、
長い分析が出る。単語単体にできないのであれば出さない。／URLのオンマウスで、品詞の分析は要らない」）。
CN_HOVER_WORD_ONLY=0・CN_HOVER_URL_NO_POS=0 で前の形。作った例文だけ。tools_local/run_on_desktop.py で回す。"""
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
    import app
    import auto_candidates as AC
    from session import new_tab
    body = chr(10).join(['きょうはいい天気です。', 'https://example.com/path/to/page?x=1', '会議の資料を作る'])
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
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
        root.geometry('1000x500+-4000+40')
        end = time.monotonic() + 60
        while time.monotonic() < end and (a._foreground_analysis_pending() or len(a.line_results) < 3 or not all(a.line_results[:3])):
            pump(0.1)
        pump(1.0)
        def at(widget, index):
            widget.see(index); root.update_idletasks()
            box = widget.bbox(index)
            return NS(x=box[0] + 2, y=box[1] + 2, x_root=0, y_root=0, widget=widget, state=0)
        ed, rv = a.editor, a.result_view
        # 解析の済んだ行の語: 出す
        a._editor_line_units(1)                                          # 控えを作る（子に尋ねる道）
        pump(0.5)
        hit = AC._hit(a, ed, at(ed, '1.4'))
        out['word'] = hit[2].get('text') if hit else None
        # URL の上: 出さない（メモ欄・補正欄）
        a._editor_line_units(2); pump(0.5)
        hit = AC._hit(a, ed, at(ed, '2.10'))
        out['url_editor'] = hit[2].get('text') if hit else None
        hit = AC._hit(a, rv, at(rv, '2.10'))
        out['url_result'] = hit[2].get('text') if hit else None
        # 語の切れ目の控えに無い所（空白で区切った塊＝行まるごと）: 出さない
        unit = a._fallback_unit(3, 2)
        hit = unit
        out['fallback_text'] = (unit[1] if isinstance(unit, tuple) else unit or {}).get('text') if unit else None
        u = unit[1] if isinstance(unit, tuple) else unit
        out['fallback_ok'] = AC._word_like(a, ed, 'editor', 3, u) if u else None
        out['long_ok'] = AC._word_like(a, rv, 'result', 3, dict(text='会議の資料を作る' * 4, start=0, end=32))
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
    d = Path(tempfile.mkdtemp(prefix='cn-hoverword-'))
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
    def test_word_only_and_no_url(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertTrue(got['word'], got)                                  # 語1つは今まで通り出す
        self.assertLess(len(got['word']), 12, got)
        self.assertIsNone(got['url_editor'], got)                          # URL の上は出さない
        self.assertIsNone(got['url_result'], got)
        self.assertFalse(got['fallback_ok'], got)                          # 空白で区切った塊（行まるごと）は出さない
        self.assertFalse(got['long_ok'], got)                              # 長すぎる単位も出さない

    def test_switch_back(self):
        got = run_child(self, {'CN_HOVER_WORD_ONLY': '0', 'CN_HOVER_URL_NO_POS': '0'})
        self.assertTrue(got['fallback_ok'], got)
        self.assertTrue(got['long_ok'], got)


if __name__ == '__main__':
    unittest.main()
