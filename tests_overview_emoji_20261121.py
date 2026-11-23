# -*- coding: utf-8 -*-
"""縮小表示（overview_fast）の中の絵文字も色付きで（2026-11-21 うにさん・overview_emoji）。CN_OVERVIEW_EMOJI=0 で前の形。
作った例文と自分で入れた絵文字だけ。アプリは写しの中の子で、窓は画面の外。"""
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
    from session import new_tab
    rows = []
    for i in range(1, 301):
        rows.append(('%d行目の本文です' % i) + ('\U0001F600と\U0001F431' if i % 3 == 0 else ''))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=chr(10).join(rows))]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        import offscreen_window; offscreen_window.hold(root)      # 作る間も見えない所に（画面の置き方に依らない）
        a = app.CorrectNoteApp(root)
        import offscreen_window; offscreen_window.hold(root, '1000x700')
        pump(4)
        import overview_fast as O
        import overview_emoji as E
        O.right_button_down = lambda app=None: True
        ov = O.install(a)
        ed = a.editor
        ed.yview('100.0'); pump(0.5)
        # 元の字の大きさのままの行: ブックマーク（102・105・180・183）とタイトル・目次の印（cn_head_*・108）。どれも絵文字の行
        a.bookmarks = {102, 105, 180, 183}
        ed.tag_add('cn_head_test', '108.0', '109.0')
        ev = NS(x=100, y=200, x_root=ed.winfo_rootx() + 100, y_root=ed.winfo_rooty() + 200, widget=ed, state=0)
        t = time.perf_counter(); ov.enter(ev, ed); root.update_idletasks(); out['enter_ms'] = round((time.perf_counter() - t) * 1000, 1)
        keep = getattr(ov, '_peer_emoji', None) or {}
        out['shown_at_enter'] = sum(len(g.shown) for g in keep.values())     # 入る時の重さに足さない（少し後に重ねる）
        t = time.perf_counter(); pump(0.3)
        out['peers'] = len(keep)
        left = ov._left()
        got = keep.get(left)
        out['labels'] = len(got.shown) if got else 0
        if got and got.shown:
            pump(0.4)                                                        # 後から字の並びが動いても付いていく
            x, y, w, h, text, bg, idx = got.shown[0]
            box = [int(v) for v in root.tk.splitlist(root.tk.call(left, 'bbox', idx))]
            out['label_on_emoji'] = (box[0], box[1]) == (x, y)
            out['size_of_box'] = h == box[3]                                    # その行の字の大きさ
            out['rows'] = sorted({int(str(it[6]).split('.')[0]) for it in got.shown})
            raw = set()      # 分身の行（タイトルの見出しの分だけ本文の行番号とずれる）でタグの付いている行
            for tag in ('cn_ov_bookmark', 'cn_head_test'):
                r = [str(v) for v in root.tk.splitlist(root.tk.call(left, 'tag', 'ranges', tag))]
                for a0, b0 in zip(r[::2], r[1::2]):
                    raw.update(range(int(a0.split('.')[0]), int(b0.split('.')[0]) + (0 if b0.endswith('.0') else 1)))
            out['head_rows_raw'] = sorted(raw)
            out['only_head_rows'] = set(out['rows']) <= raw
            out['head_cn_row'] = sorted(int(a0.split('.')[0]) for a0 in [str(v) for v in root.tk.splitlist(
                root.tk.call(left, 'tag', 'ranges', 'cn_head_test'))][::2])
            lab = got.labels[0]
            out['label_mapped'] = bool(lab.winfo_ismapped())
            t = time.perf_counter()
            for _ in range(10):
                got.shown = []; got.refresh()
            out['refresh_ms'] = round((time.perf_counter() - t) * 100, 2)
            t = time.perf_counter()
            for _ in range(10):
                got.watch_job = None; got._watch()
            out['watch_ms'] = round((time.perf_counter() - t) * 100, 3)          # 見張りの1回（動いていない時）
            t = time.perf_counter(); got.clear(); out['clear_ms'] = round((time.perf_counter() - t) * 1000, 2)
            t = time.perf_counter(); E._any_emoji(got); out['any_ms'] = round((time.perf_counter() - t) * 1000, 2)
            got.refresh()
            root.tk.call(left, 'yview', 'scroll', 1, 'units')
            E.moved(ov)
            t = time.perf_counter()
            for _ in range(10):
                root.tk.call(left, 'yview', 'scroll', 1, 'units'); E.moved(ov)
            out['moved_again_ms'] = round((time.perf_counter() - t) * 100, 2)        # 掴んで動かしている間の1回
            root.tk.call(left, 'yview', 'scroll', -11, 'units'); pump(0.3)
        before = list(got.shown) if got else []
        root.tk.call(left, 'yview', 'scroll', 40, 'units')
        t = time.perf_counter(); E.moved(ov); out['moved_ms'] = round((time.perf_counter() - t) * 1000, 2)
        out['hidden_while_moving'] = bool(got) and got.shown == []          # 動かしている間は外す
        pump(0.3)
        out['moved_changed'] = bool(got) and got.shown != before and len(got.shown) > 0
        ov.exit(); pump(0.3)
        t = time.perf_counter(); ov.enter(ev, ed); root.update_idletasks(); out['enter2_ms'] = round((time.perf_counter() - t) * 1000, 1)
        pump(0.3); ov.exit(); pump(0.3)
        out['after_exit_mapped'] = [bool(l.winfo_ismapped()) for g in keep.values() for l in g.labels if l.winfo_exists()].count(True)
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
    if sys.platform != 'win32':
        case.skipTest('Windows だけ')
    d = Path(tempfile.mkdtemp(prefix='cn-ovemoji-'))
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
    def test_overview_emoji_in_colour(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertGreaterEqual(got['peers'], 1, got)
        self.assertEqual(got['shown_at_enter'], 0, got)
        self.assertGreater(got['labels'], 0, got)                 # 見えている絵文字に色付きの絵
        self.assertTrue(got['label_on_emoji'], got)               # 絵文字の枠の上
        self.assertTrue(got['size_of_box'], got)                  # その行の字の大きさ
        self.assertTrue(got['only_head_rows'], got)               # タイトル・目次・ブックマークの行だけ（小さい本文は白黒）
        self.assertGreaterEqual(len(got['rows']), 3, got)
        self.assertIn(got['head_cn_row'][0], got['rows'], got)    # タイトル・目次の行も
        self.assertTrue(got['label_mapped'], got)
        self.assertTrue(got['hidden_while_moving'], got)          # 動かしている間は外す（ずれた絵を見せない）
        self.assertTrue(got['moved_changed'], got)                # 止まったら付け直す
        self.assertEqual(got['after_exit_mapped'], 0, got)        # 出たら外す
        self.assertLess(got['moved_again_ms'], 5, got)              # 動かしている間の2回目からは軽い
        print('overview emoji (head only): enter %sms, enter2 %sms, refresh %sms, first move %sms, next moves %sms, '
              'watch %sms, labels %s' % (got['enter_ms'], got['enter2_ms'], got.get('refresh_ms'), got['moved_ms'],
                                         got['moved_again_ms'], got['watch_ms'], got['labels']))

    def test_all_rows_switch(self):
        got = run_child(self, {'CN_OVERVIEW_EMOJI_HEAD_ONLY': '0'})
        self.assertEqual(got['errors'], [], got)
        self.assertFalse(got['only_head_rows'], got)              # 前の形: 小さい本文の行の絵文字にも重ねる
        self.assertTrue(got['label_on_emoji'], got)
        print('overview emoji (all rows): enter %sms, enter2 %sms, refresh %sms, first move %sms, next moves %sms, '
              'watch %sms, labels %s' % (got['enter_ms'], got['enter2_ms'], got.get('refresh_ms'), got['moved_ms'],
                                         got['moved_again_ms'], got['watch_ms'], got['labels']))

    def test_switch_back(self):
        got = run_child(self, {'CN_OVERVIEW_EMOJI': '0'})
        self.assertEqual(got['peers'], 0, got)
        print('overview emoji off: enter %sms, enter2 %sms, moved %sms' % (got['enter_ms'], got['enter2_ms'], got['moved_ms']))


if __name__ == '__main__':
    unittest.main()
