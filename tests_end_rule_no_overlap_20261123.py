# -*- coding: utf-8 -*-
"""最終行（最後の字の行の次の空行＝終端の二重罫線の行）に字を打った時、罫線を打った字の上に重ねない（2026-11-23 うにさん
「最終行で黒い帯が出る件は、二重罫線が重なっていた。重ならないようにする」）。前は打ったその場で罫線を同じ行へ置き直して
いた（_end_rule_follow）ので、次の描き直しまで打った字の上に二重罫線が残った。打った行に字がある時は隠し、描き直しで
新しい空行へ引く。CN_LAST_LINE_RULE_NO_OVERLAP=0 で前の形。作った文だけ。run_on_desktop で回す。"""
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
        def rows_bottom(r):
            d = ed.dlineinfo('%d.0' % r)
            return d[1] + d[3] - a._end_rule_metrics()[0] if d else None
        def shown():
            return bool(line.place_info()) and line.winfo_ismapped()
        ed.mark_set('insert', '13.0')
        ed.focus_force(); pump(0.2)
        deliver_key(ed, '<KeyPress>', 'a', 65, char='a')
        out['typed_row'] = ed.get('13.0', '13.end')
        out['right_after'] = [shown(), place_y(), rows_bottom(13)]
        pump(1.5)
        out['settled'] = [shown(), place_y(), rows_bottom(14), [str(i) for i in ed.tag_ranges('end_rule')]]
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
    d = Path(tempfile.mkdtemp(prefix='cn-endrule2-'))
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
        self.assertEqual(got['before'][0], got['before'][1], got)            # 罫線は罫線の行（13行目）の下端
        self.assertTrue(got['typed_row'].strip(), got)                      # 罫線の行に字を打った
        shown, y, bottom13 = got['right_after']
        self.assertFalse(shown and y == bottom13, got)                      # 打った字の上に重ねない
        shown2, y2, bottom14, tag = got['settled']
        self.assertTrue(shown2, got)                                        # 描き直しで次の空行へ引く
        self.assertEqual(y2, bottom14, got)

    def test_split(self):
        self.check('split')

    def test_unified(self):
        self.check('unified')

    def test_switch_back(self):
        got = run_child(self, {'CN_LAST_LINE_RULE_NO_OVERLAP': '0', 'CN_END_RULE_HIDE_BEFORE': '0'})
        shown, y, bottom13 = got['right_after']
        self.assertTrue(shown and y == bottom13, got)                       # 前の形: 打った字の行に重なって残る


if __name__ == '__main__':
    unittest.main()
