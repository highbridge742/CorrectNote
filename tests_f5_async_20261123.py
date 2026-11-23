# -*- coding: utf-8 -*-
"""F5（語の候補）を、解析の子を本体で待たずに開く（2026-11-23・決まり「マウス・キーから呼ばれる本体の処理は解析の子を
同期で待たない」。前は解析の途中の F5 で本体が約 0.3秒止まった）。CN_F5_ASYNC=0 で前の形。
・作り物のアプリで: 待つ条件・押し直しの数え方・やめる条件・解析を待たせる条件と外れ方
・写しのアプリで: 押し直し1〜3回の候補と印の位置が前の形と同じ・押した時に本体がほとんど止まらない（run_on_desktop）"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import auto_candidates as AC
import f5_async


class FakeText:
    def __init__(self):
        self.insert = '5.6'
        self.sel = ()
        self._correctnote_whole_text = {'changes': 3}

    def index(self, what):
        return self.insert if what == 'insert' else '1.0'

    def get(self, a, b=None):
        return getattr(self, 'right', '字')         # カーソルの右の字（無ければ予測で開く）

    def tag_ranges(self, tag):
        return self.sel


def fake_app():
    ed = FakeText()
    app = NS(editor=ed, result_view=object(), _dropdown=None, _f2_cycle=None, _f2_focus_target=None,
             session=NS(active=0), _async_request=('line',), _async_background_request=None,
             root=NS(focus_get=lambda: ed, after=lambda ms, fn: 'job', after_cancel=lambda job: None))
    return app, ed


class Logic(unittest.TestCase):
    def test_defers_only_while_the_child_solves_a_row(self):
        app, ed = fake_app()
        ev = NS(widget=ed)
        self.assertTrue(f5_async.defer(app, ev))
        self.assertEqual(app._f5_wait['presses'], 1)
        self.assertTrue(f5_async.defer(app, ev))                       # 押し直しは数えるだけ
        self.assertEqual(app._f5_wait['presses'], 2)
        f5_async.cancel(app)
        app._async_request = None
        self.assertFalse(f5_async.defer(app, ev))                      # 子が空いている: 今までどおりその場で
        app._async_request = ('line',)
        app._dropdown = object()
        self.assertFalse(f5_async.defer(app, ev))                      # 遡りの途中は今までどおり
        app._dropdown = None
        ed.right = ''
        self.assertFalse(f5_async.defer(app, ev))                      # 右に字が無い: 予測（子に尋ねない）はその場で
        ed.right = '字'
        with mock.patch.dict(os.environ, {'CN_F5_ASYNC': '0'}):
            self.assertFalse(f5_async.defer(app, ev))

    def test_other_input_or_moves_cancel(self):
        app, ed = fake_app()
        ev = NS(widget=ed)
        f5_async.defer(app, ev)
        f5_async.note_input(app, NS(keysym='Shift_L'))
        self.assertTrue(f5_async.pending(app))                         # 修飾キーではやめない
        f5_async.note_input(app, NS(keysym='a'))
        self.assertFalse(f5_async.pending(app))                        # ほかのキー
        f5_async.defer(app, ev)
        f5_async.note_input(app, NS(keysym='Escape'))
        self.assertFalse(f5_async.pending(app))                        # Esc
        f5_async.defer(app, ev)
        ed.insert = '5.7'                                              # カーソルが動いた
        self.assertFalse(f5_async.defer(app, ev))
        self.assertFalse(f5_async.pending(app))
        f5_async.defer(app, ev)
        ed._correctnote_whole_text['changes'] = 4                      # 本文が変わった
        app._cn_in_analyze_slice = True
        app._async_request = None
        self.assertFalse(f5_async.run_waiting(app))
        self.assertFalse(f5_async.pending(app))

    def test_timeout(self):
        app, ed = fake_app()
        f5_async.defer(app, NS(widget=ed))
        app._f5_wait['since'] = time.monotonic() - f5_async.TIMEOUT_S - 1
        app._cn_in_analyze_slice = True
        app._async_request = None
        self.assertFalse(f5_async.run_waiting(app))
        self.assertFalse(f5_async.pending(app))

    def test_hold_comes_off(self):
        alive = NS(closed=False, process=NS(is_alive=lambda: True))

        def waiting(**kw):
            app, ed = fake_app()
            f5_async.defer(app, NS(widget=ed))
            app._async_request = None
            app._correction_worker = alive
            app._analyze_work = 'W'
            app._f5_wait['asks'] = dict(pending={'k': 1}, got={}, done={}, worker=alive, work='W')
            for k, v in kw.items():
                setattr(app, k, v)
            return app
        self.assertTrue(f5_async.hold(waiting()))
        self.assertFalse(f5_async.hold(waiting(_correction_worker=NS(closed=False, process=NS(is_alive=lambda: True)))))
        self.assertFalse(f5_async.hold(waiting(_analyze_work='W2')))   # タブを替えた・段取りが変わった
        self.assertFalse(f5_async.hold(waiting(_async_request=('line',))))
        app = waiting()
        app._f5_wait['since'] = time.monotonic() - f5_async.TIMEOUT_S - 1
        self.assertFalse(f5_async.hold(app))
        self.assertFalse(f5_async.pending(app))

    def test_preempt_cancels_the_row_and_the_hold_always_comes_off(self):
        # 人が今押した F5 を先に: 子が解いている本体の行を取り消して頼みを出す。取り消した行の答えは待たない
        # （_async_request を外す）ので、F5 の答え・待ちの外れのあと、解析はその行をもう一度頼む
        app, ed = fake_app()
        alive = NS(closed=False, process=NS(is_alive=lambda: True), submit=lambda task, state=None: 41, serial=40)
        app._correction_worker = alive
        app._async_request = (('line', 'W', 'D', 'T', 7, False), 40)
        app._analyze_work = 'W'
        cancelled = []
        import analysis_async
        with mock.patch.object(analysis_async, 'cancel_foreground_request',
                               lambda a: (cancelled.append(a._async_request), setattr(a, '_async_request', None))),                 mock.patch.object(f5_async, '_attempt', lambda a, w: w.update(asks=dict(pending={'k': 41}, got={}, done={},
                                                                                      worker=alive, work='W')) or 'deferred'):
            self.assertTrue(f5_async.defer(app, NS(widget=ed)))
        self.assertEqual(len(cancelled), 1)                                # 本体の行を取り消した
        self.assertIsNone(app._async_request)                              # その答えは待たない（行は後で頼み直す）
        self.assertEqual(app._f5_wait['preempted'][4], 7)                  # 取り消した行を控えた
        self.assertTrue(f5_async.hold(app))                                # F5 の答えを待つ間は次の行を頼まない
        app._f5_wait['asks']['pending'].clear()
        self.assertFalse(f5_async.hold(app))                               # 答えが来たら外れる
        app._f5_wait['asks']['pending']['k'] = 41
        app._f5_wait['since'] = time.monotonic() - f5_async.TIMEOUT_S - 1
        self.assertFalse(f5_async.hold(app))                               # 待ちの外れでも外れる
        self.assertFalse(f5_async.pending(app))
        with mock.patch.dict(os.environ, {'CN_F5_ASYNC_PREEMPT': '0'}):
            app2, ed2 = fake_app()
            app2._async_request = (('line',), 1)
            with mock.patch.object(analysis_async, 'cancel_foreground_request', lambda a: cancelled.append('x')):
                self.assertTrue(f5_async.defer(app2, NS(widget=ed2)))
            self.assertEqual(len(cancelled), 1)                            # 取り消さない形（子の合間を待つ）

    def test_right_click_defers_and_replays_the_opener(self):
        app, ed = fake_app()
        opened = []
        with mock.patch.object(f5_async, '_preempt', lambda a: False):
            self.assertTrue(f5_async.defer_action(app, ed, lambda: opened.append(1)))
        self.assertTrue(f5_async.pending(app))
        app._close_dropdown = lambda: None
        app._clear_f2_target = lambda: None
        with mock.patch('reinput.hide_cursor_for_reconvert', lambda a: None):
            self.assertEqual(f5_async._attempt(app, app._f5_wait), 'done')
        self.assertEqual(opened, [1])                                       # 一覧を開く関数をそのまま呼び直す
        app._async_request = None
        self.assertFalse(f5_async.defer_action(app, ed, lambda: None))     # 子が空いている: その場で
        app._async_request = ('line',)
        with mock.patch.dict(os.environ, {'CN_RIGHT_CLICK_ASYNC': '0'}):
            self.assertFalse(f5_async.defer_action(app, ed, lambda: None))

    def test_quick_f2_defers_counts_and_replays(self):
        app, ed = fake_app()
        quick = FakeText()
        app._quick_text = quick
        app._f2q_cycle = None
        quick.tag_remove = lambda *a: None
        with mock.patch.object(f5_async, '_preempt', lambda a: False):
            self.assertTrue(f5_async.defer_quick(app, NS(widget=quick)))
            self.assertTrue(f5_async.defer_quick(app, NS(widget=quick)))       # 押し直しは数えるだけ
        self.assertEqual(app._f5_wait['presses'], 2)
        calls = []
        app._close_dropdown = lambda: calls.append('close')
        app._clear_f2_target = lambda: calls.append('clear')
        app._on_quick_f2_open = lambda event: calls.append('open')
        with mock.patch('reinput.hide_cursor_for_reconvert', lambda a: None):
            self.assertEqual(f5_async._attempt(app, app._f5_wait), 'done')
        self.assertEqual(calls, ['close', 'clear', 'open', 'open'])          # まっさらにして押した回数だけ
        quick.right = ''
        self.assertFalse(f5_async.defer_quick(app, NS(widget=quick)))         # 予測で開く所はその場で
        quick.right = '字'
        with mock.patch.dict(os.environ, {'CN_QUICK_F2_ASYNC': '0'}):
            self.assertFalse(f5_async.defer_quick(app, NS(widget=quick)))
        app._async_request = None
        self.assertFalse(f5_async.defer_quick(app, NS(widget=quick)))         # 子が空いている: その場で

    def test_replays_the_presses_from_a_fresh_state(self):
        app, ed = fake_app()
        f5_async.defer(app, NS(widget=ed))
        f5_async.defer(app, NS(widget=ed))
        f5_async.defer(app, NS(widget=ed))
        calls = []
        app._close_dropdown = lambda: calls.append('close')
        app._clear_f2_target = lambda: calls.append('clear')
        app._on_f2_candidates_open = lambda event: calls.append('open')
        with mock.patch('reinput.hide_cursor_for_reconvert', lambda a: None):
            self.assertEqual(f5_async._attempt(app, app._f5_wait), 'done')
        self.assertEqual(calls, ['close', 'clear', 'open', 'open', 'open'])     # まっさらにして押した回数だけ
        self.assertFalse(f5_async.pending(app))


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
    words = ['会議', '資料', '確認', '連絡', '予定', '作業', '準備', '報告', '検討', '変更']
    big = chr(10).join('%d行目は%sの%sを%sするための作った文です。' % (i + 1, words[i % 10], words[(i * 3 + 1) % 10],
                       words[(i * 7 + 2) % 10]) for i in range(120))
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=big)]), ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e))[-500:])
    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.003)
    out = {'cases': []}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1300x900+40+40')
        ed = a.editor
        root.focus_get = lambda: ed
        end = time.monotonic() + 150
        while time.monotonic() < end and getattr(a, '_analyze_pos', 0) < 25:
            pump(0.5)
        ev = NS(widget=ed, keysym='F5', char='', state=0, keycode=116, x=0, y=0, x_root=0, y_root=0)
        for row, col, presses in ((8, 9, 2), (12, 4, 1), (15, 10, 3)):
            a._close_dropdown(); a._clear_f2_target(); a._f2_cycle = None; pump(0.3)
            ed.mark_set('insert', '%d.%d' % (row, col)); pump(0.2)
            call_ms = 0.0
            busy = a._async_request is not None
            for _ in range(presses):
                t = time.perf_counter()
                a._on_f2_candidates_widget(ev)
                call_ms = max(call_ms, (time.perf_counter() - t) * 1000)
                root.update()
            t1 = time.monotonic()
            while time.monotonic() - t1 < 10:
                root.update()
                if getattr(a, '_dropdown', None) is not None and not getattr(a, '_f5_wait', None):
                    break
                time.sleep(0.003)
            pump(0.3)
            parts = getattr(a, '_dropdown_parts', None) or {}
            lb = parts.get('lb')
            items = [str(x) for x in lb.get(0, 'end')] if lb is not None else None
            cur = [int(i) for i in lb.curselection()] if lb is not None else None
            tgt = getattr(a, '_f2_focus_target', None) or {}
            out['cases'].append(dict(row=row, presses=presses, busy=busy, call_ms=round(call_ms, 1), items=items, cur=cur,
                                     target=[tgt.get('row'), tgt.get('start'), tgt.get('end')]))
        a._close_dropdown()
        # 右クリックの候補も（f5_async.defer_action・CN_RIGHT_CLICK_ASYNC）
        a._warp_pointer = lambda widget, x, y: 'sync'
        out['right'] = []
        base = int(time.monotonic() * 1000)
        for k, (row, col) in enumerate(((18, 6), (21, 9))):
            a._close_dropdown(); a._clear_f2_target(); a._f2_cycle = None; pump(0.3)
            ed.see('%d.0' % row); pump(0.2)
            bb = ed.bbox('%d.%d' % (row, col))
            x, y = bb[0] + 2, bb[1] + bb[3] // 2
            busy = a._async_request is not None
            t = time.perf_counter()
            ed.event_generate('<ButtonPress-3>', x=x, y=y, time=base + k * 5000)
            ed.event_generate('<ButtonRelease-3>', x=x, y=y, time=base + k * 5000 + 60)
            call_ms = (time.perf_counter() - t) * 1000
            t1 = time.monotonic()
            while time.monotonic() - t1 < 10 and (getattr(a, '_dropdown', None) is None or getattr(a, '_f5_wait', None)):
                root.update(); time.sleep(0.003)
            pump(0.3)
            parts = getattr(a, '_dropdown_parts', None) or {}
            lb = parts.get('lb')
            out['right'].append(dict(row=row, busy=busy, call_ms=round(call_ms, 1),
                                     items=[str(v) for v in lb.get(0, 'end')] if lb is not None else None))
        a._close_dropdown()
        pos = a._analyze_pos
        pump(6.0)
        out['progress_after'] = a._analyze_pos - pos           # 取り消した行も頼み直して、解析は進み続ける
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
    d = Path(tempfile.mkdtemp(prefix='cn-f5async-'))
    for e in here.iterdir():
        if e.is_file() and e.name not in ('settings.json', 'session.json', 'vocabulary.json', 'last_choice.json'):
            shutil.copy2(e, d / e.name)
    (d / 'zz_child.py').write_text(CHILD, encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None); env.update(env_extra or {})
    subprocess.run([sys.executable, '-B', '-X', 'utf8', 'zz_child.py'], cwd=d, env=env, timeout=300,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    got = json.loads((d / 'child_out.json').read_text(encoding='utf-8'))
    shutil.rmtree(d, ignore_errors=True)
    case.assertNotIn('error', got, got.get('error'))
    return got


class InTheApp(unittest.TestCase):
    def test_same_list_and_place_as_before_without_blocking(self):
        new = run_child(self)
        old = run_child(self, {'CN_F5_ASYNC': '0'})                          # 右クリックも前の形（同期）になる
        self.assertEqual(new['errors'], [], new)
        for n, o in zip(new['cases'], old['cases']):
            self.assertEqual((n['items'], n['cur'], n['target']), (o['items'], o['cur'], o['target']), (n, o))
            self.assertTrue(n['items'], n)                                  # 一覧が開いた
            if n['busy']:
                self.assertLess(n['call_ms'], 50, n)                        # 押した時に本体がほとんど止まらない
        self.assertGreater(new['progress_after'], 0, new)                   # 取り消した行を頼み直して解析が進む
        for n, o in zip(new['right'], old['right']):                        # 右クリックの候補も前の形と同じ中身
            self.assertEqual(n['items'], o['items'], (n, o))
            self.assertTrue(n['items'], n)
            if n['busy']:
                self.assertLess(n['call_ms'], 50, n)


if __name__ == '__main__':
    unittest.main()
