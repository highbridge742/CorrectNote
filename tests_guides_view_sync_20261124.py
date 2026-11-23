# -*- coding: utf-8 -*-
"""ルーラー（行の下に引く線）と終端の二重罫線を、行の高さが変わったら今の位置へ引き直す（2026-11-23 うにさん「ルーラーも帯が
重なってました。27行目 何秒もずっと」）。どちらも欄の上に place した Frame で、字と一緒には動かない。
・上の行に字を足して折り返した（メモ欄）・上の行の字を大きくした（補正欄・品詞の字と同じタグの字の大きさ）の後、
  字を並べ直したら（Tk の知らせを流しきったら）、線は線の行の下端にある（前の高さに残らない）
CN_GUIDES_VIEW_SYNC=0 で前の形。作った文だけ。run_on_desktop で回す。"""
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
    body = chr(10).join('%d行目の本文です。' % i for i in range(1, 13))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    def drain(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            if not root.tk.dooneevent(_tkinter.DONT_WAIT):
                time.sleep(0.002)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1100x700+40+40')
        pump(6)
        ed, rv = a.editor, a.result_view
        root.focus_get = lambda: ed
        g = a._editor_guides
        g.set_ruler_rows({8})
        g.enabled = True
        g.queue_draw()
        pump(1.0)
        def ruler(w):
            line = g.lines.get((w, 8))
            if line is None or not line.place_info():
                return None
            return int(line.place_info()['y'])
        def want(w):
            d = w.dlineinfo('8.end')
            from editor_guides import ruler_width
            return d[1] + d[3] - ruler_width() if d else None
        def end_rule(w):
            info = w._end_rule_line.place_info()
            return int(info['y']) if info else None
        def end_want(w):
            d = w.dlineinfo('13.0')
            return d[1] + d[3] - a._end_rule_metrics()[0] if d else None
        end = time.monotonic() + 15
        while time.monotonic() < end and end_rule(ed) is None:
            pump(0.1)
        out['before'] = [ruler(ed), want(ed), ruler(rv), want(rv), end_rule(rv), end_want(rv)]
        # 補正欄の上の行の字を大きくする（字は変えない・行の高さだけ変わる）
        rv.tag_configure('zz_big', font=('Yu Gothic UI', 26))
        rv.tag_add('zz_big', '3.0', '3.end')
        drain(1.0)
        out['taller'] = [ruler(rv), want(rv), end_rule(rv), end_want(rv)]
        # メモ欄の上の行に字を足して折り返す
        ed.insert('4.end', '長い字を足して折り返す。' * 12)
        drain(0.3)
        out['wrapped'] = [ruler(ed), want(ed)]
        # 罫線が文書の途中の空行に残った形（途中まで描かれた補正欄に引いた後、下の行が描かれた等）を作り、確かめ直しで消える／
        # 正しい行へ引き直されるか。メモ欄に空行を1つ作り、そこへ罫線のタグと線を置く
        ed.insert('6.0', chr(10)); pump(1.0)
        ed.tag_remove('end_rule', '1.0', 'end'); ed.tag_add('end_rule', '6.0', '7.0')
        d6 = ed.dlineinfo('6.0'); wd = a._end_rule_metrics()[0]
        ed._end_rule_line.place(x=2, y=d6[1] + d6[3] - wd, width=100, height=wd)
        stale = end_rule(ed)
        ed.event_generate('<<WidgetViewSync>>', data='1')
        right_after = end_rule(ed)
        pump(1.0)
        low = max(r for r in range(1, int(ed.index('end-1c').split('.')[0]) + 1) if ed.get('%d.0' % r, '%d.end' % r).strip())
        d = ed.dlineinfo('%d.0' % (low + 1))
        out['below'] = [stale, right_after, end_rule(ed), (d[1] + d[3] - wd) if d else None, low]
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
    d = Path(tempfile.mkdtemp(prefix='cn-guidesync-'))
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
    return got


class GuidesFollowRowHeights(unittest.TestCase):
    def test_lines_move_with_the_rows(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        b = got['before']
        self.assertEqual(b[0], b[1], got)                    # ルーラーは8行目の下端
        self.assertEqual(b[2], b[3], got)
        self.assertEqual(b[4], b[5], got)                    # 罫線は13行目の下端
        t = got['taller']
        self.assertGreater(t[1], b[3], got)                  # 補正欄の8行目は下へ動いた
        self.assertEqual(t[0], t[1], got)                    # ルーラーも付いていく
        self.assertEqual(t[2], t[3], got)                    # 罫線も
        stale, right_after, y, good, low = got['below']
        self.assertIsNotNone(stale, got)
        self.assertIsNone(right_after, got)                  # 文書の途中の罫線は、確かめ直しで隠す
        self.assertEqual(y, good, got)                       # 描き直しで最後の字の行の次の空行へ
        w = got['wrapped']
        self.assertGreater(w[1], b[1], got)
        self.assertEqual(w[0], w[1], got)

    def test_switch_back(self):
        got = run_child(self, {'CN_GUIDES_VIEW_SYNC': '0'})
        t = got['taller']
        stale, right_after = got['below'][:2]
        # 前の形: どれかが前の高さに残る（行の高さの変化は、別の描き直しが先に追いつく時もあるので、途中に残った罫線でも見る）
        self.assertTrue(t[0] != t[1] or t[2] != t[3] or right_after is not None, got)


if __name__ == '__main__':
    unittest.main()
