# -*- coding: utf-8 -*-
"""最終行に打つ・貼ると、終端の二重罫線（欄に置いた枠）をその場で罫線の行の今の位置へ置き直す（2026-11-22 20:08 JST うにさん
「文字をペーストした時、またはタイピングして入力して文字が出た際に、文字の中央に横に帯が一瞬見えるような気がする。最終行で
入力している」）。前は打鍵の約 0.1 秒後の描き直しまで前の高さに残り、最終行が折り返して1段増えると、増えた段の字の真ん中に
罫線が重なっていた。CN_END_RULE_FOLLOW_EDIT=0 で前の形。作った例文だけ（貼り付けはクリップボードを使わない）。
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
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+40+40')          # 見えない机の上で回す（run_on_desktop）。画面の外だと罫線を置かない
        pump(6)
        ed = a.editor
        root.focus_get = lambda: ed
        ed.mark_set('insert', '12.end')
        for w in (ed, a.result_view):
            w.yview_moveto(0.0)                    # 1行目から（20行と罫線の行が見えている）
        pump(1.0)
        line = ed._end_rule_line
        def place_y():
            info = line.place_info()
            return int(info['y']) if info else None
        def rule_bottom():
            d = ed.dlineinfo('13.0')
            return d[1] + d[3] - a._end_rule_metrics()[0] if d else None
        end = time.monotonic() + 15                # 罫線が置かれるまで待つ（解析・行の高さ揃えの後に置く）
        while time.monotonic() < end and not (place_y() is not None and place_y() == rule_bottom()):
            pump(0.1)
        out['before'] = [place_y(), rule_bottom(), [str(i) for i in ed.tag_ranges('end_rule')]]
        out['dbg'] = [ed.winfo_ismapped(), ed.winfo_height(), ed.winfo_width(), str(ed.index('@0,0')), str(ed.index('@0,%d' % (ed.winfo_height() - 1))), a._layout_is_unified()]
        # 貼り付け（クリップボードの代わりに字を返す）で最終行を折り返させる
        long_text = 'あ' * 60
        root.tk.eval('proc ::tk::GetSelection {w sel} { if {$sel eq "CLIPBOARD"} { return "%s" }; error none }' % long_text)
        ed.event_generate('<<Paste>>')
        # 描く前（ほかの後の仕事が走る前）の罫線の高さと、罫線の行の今の下端
        n = ed.count('12.0', '13.0', 'displaylines')
        out['paste'] = [place_y(), rule_bottom(), n[0] if isinstance(n, tuple) else n]
        root.update_idletasks()                    # 字を並べ直した後（CN_END_RULE_HIDE_BEFORE は隠して、ここで置き直す）
        out['paste_idle'] = [place_y(), rule_bottom()]
        pump(1.0)
        out['paste_settled'] = [place_y(), rule_bottom()]
        deliver_key(ed, '<KeyPress>', 'a', 65, char='a')
        out['key'] = [place_y(), rule_bottom()]
        root.update_idletasks()
        out['key_idle'] = [place_y(), rule_bottom()]
        pump(0.5)
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
    d = Path(tempfile.mkdtemp(prefix='cn-endrule-'))
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
        self.assertEqual(got['before'][0], got['before'][1], got)            # 罫線は罫線の行の下端
        self.assertGreater(got['paste'][2], 1, got)                         # 貼った行は折り返した（段が増えた）
        self.assertGreater(got['paste'][1], got['before'][1], got)          # 罫線の行は下へ動いた
        # 貼ったその場は、隠す（2026-11-24 CN_END_RULE_HIDE_BEFORE: 前の位置に残さない）か、新しい位置に付いていく
        self.assertIn(got['paste'][0], (None, got['paste'][1]), got)
        self.assertEqual(got['paste_idle'][0], got['paste_idle'][1], got)   # 字を並べ直したら、新しい位置に置く
        self.assertEqual(got['paste_settled'][0], got['paste_settled'][1], got)
        self.assertIn(got['key'][0], (None, got['key'][1]), got)
        self.assertEqual(got['key_idle'][0], got['key_idle'][1], got)

    def test_split(self):
        self.check('split')

    def test_unified(self):
        self.check('unified')

    def test_switch_back(self):
        got = run_child(self, {'CN_END_RULE_FOLLOW_EDIT': '0'})
        self.assertEqual(got['paste'][0], got['before'][0], got)            # 前の形: 前の高さ（折り返した段の中）に残る
        self.assertNotEqual(got['paste'][0], got['paste'][1], got)


if __name__ == '__main__':
    unittest.main()
