# -*- coding: utf-8 -*-
"""デバッグメニュー（2026-10-18）: 保存と読み込み・範囲の丸め・既定へ戻す・
変えた値が実際に使われること・窓（数値の欄とスライダーが連動する）。"""
import json
import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import analysis_async
import analysis_input
import app
import debug_menu
import quick_analysis
from settings import Settings


def bare_app(settings):
    a = object.__new__(app.CorrectNoteApp)
    a.settings = settings
    return a


class DebugTimingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'settings.json')
        self.before = (analysis_input.DISPLAY_QUIET_MS, analysis_input.DISPLAY_QUIET_IME_MS,
                       analysis_async.PREPARE_POLL_MS, quick_analysis.DISPLAY_QUIET_MS)

    def tearDown(self):
        debug_menu.apply(bare_app(Settings()), {})
        self.assertEqual(self.before, (analysis_input.DISPLAY_QUIET_MS, analysis_input.DISPLAY_QUIET_IME_MS,
                                       analysis_async.PREPARE_POLL_MS, quick_analysis.DISPLAY_QUIET_MS))
        self.dir.cleanup()

    def test_defaults_are_the_code_values_and_the_slider_maximum(self):
        a = bare_app(Settings())
        self.assertEqual(debug_menu.default('key_quiet', a), analysis_input.DISPLAY_QUIET_MS)
        self.assertEqual(debug_menu.default('ime_quiet', a), analysis_input.DISPLAY_QUIET_IME_MS)
        self.assertEqual(debug_menu.default('ime_poll_active', a), app.CorrectNoteApp._IME_POLL_ACTIVE_MS)
        self.assertEqual(debug_menu.default('busy_gap', a), app.CorrectNoteApp.ANALYZE_BUSY_GAP_MS)
        # タブのホイールの既定と上限（2026-10-18 うにさんの指定）
        self.assertEqual([debug_menu.default(k, a) for k in
                          ('tab_wheel_step', 'tab_wheel_same', 'tab_wheel_reverse', 'tab_wheel_release')],
                         [120, 47, 20, 20])
        self.assertEqual([debug_menu.maximum(k, a) for k in
                          ('tab_wheel_step', 'tab_wheel_same', 'tab_wheel_reverse', 'tab_wheel_release')],
                         [300, 200, 300, 300])
        for key in debug_menu.KEYS:
            self.assertLessEqual(debug_menu.minimum(key), debug_menu.default(key, a), key)
            self.assertLessEqual(debug_menu.default(key, a), debug_menu.maximum(key, a), key)
            if not key.startswith('tab_wheel'):
                # 待ちの上限は今の既定
                self.assertEqual(debug_menu.maximum(key, a), debug_menu.default(key, a), key)
            # 繰り返して見に行くものは 0 にしない（空回り）
            if key.endswith('poll') or key.startswith('ime_poll'):
                self.assertGreaterEqual(debug_menu.minimum(key), 1, key)
        self.assertEqual(debug_menu.values(a)['key_quiet'], 300)

    def test_save_and_load_at_the_next_start(self):
        s = Settings(self.path)
        a = bare_app(s)
        self.assertEqual(debug_menu.set_value(a, 'key_quiet', 120), 120)
        self.assertEqual(debug_menu.set_value(a, 'busy_gap', 2), 2)
        self.assertEqual(debug_menu.set_value(a, 'tab_wheel_step', 40), 40)
        with open(self.path, encoding='utf-8') as f:
            saved = json.load(f)['debug_timings']
        self.assertEqual(saved, {'key_quiet': 120, 'busy_gap': 2, 'tab_wheel_step': 40})
        # 次の起動（モジュールの定数は一度既定へ戻してから読む）
        debug_menu.apply(bare_app(Settings()), {})
        self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 300)
        b = bare_app(Settings(self.path))
        debug_menu.apply(b)
        self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 120)
        self.assertEqual(b.ANALYZE_BUSY_GAP_MS, 2)
        self.assertEqual(b.TAB_WHEEL_STEP, 40)
        # 窓の値はそのインスタンスだけ（クラスの既定は変えない）
        self.assertEqual(app.CorrectNoteApp.ANALYZE_BUSY_GAP_MS, 30)
        self.assertEqual(app.CorrectNoteApp.TAB_WHEEL_STEP, 120)

    def test_out_of_range_and_broken_values_fall_back_to_defaults(self):
        a = bare_app(Settings())
        self.assertEqual(debug_menu.parse('key_quiet', '5000', a), 300)
        self.assertEqual(debug_menu.parse('key_quiet', '-3', a), 0)
        self.assertEqual(debug_menu.parse('ime_poll_active', '0', a), 1)
        self.assertEqual(debug_menu.parse('busy_gap', '5', a), 5)
        self.assertEqual(debug_menu.parse('poll', '0', a), 1)
        self.assertEqual(debug_menu.parse('key_quiet', ' 42 ', a), 42)
        for text in ('abc', '', '1.5', None, '12ms'):
            self.assertIsNone(debug_menu.parse('key_quiet', text, a), text)
        self.assertEqual(debug_menu.normalize(
            {'key_quiet': -5, 'ime_poll_active': 0, 'ime_poll_idle': 3, 'unknown': 1,
             'busy_gap': True, 'poll': '10', 'ime_quiet': 100, 'bg_gap': 9999}, a),
            {'ime_poll_idle': 3})
        self.assertEqual(debug_menu.normalize(['key_quiet', 1], a), {})
        # 上限が既定より上の項目（タブのホイール）: 既定と同じものは残さない
        self.assertEqual(debug_menu.normalize(
            {'tab_wheel_step': 120, 'tab_wheel_same': 47, 'tab_wheel_reverse': 300,
             'tab_wheel_release': 301, 'tab_wheel_step_x': 1}, a),
            {'tab_wheel_reverse': 300})
        self.assertEqual(debug_menu.parse('tab_wheel_step', '500', a), 300)
        self.assertEqual(debug_menu.parse('tab_wheel_step', '0', a), 1)
        # 壊れたファイル・形の違う値
        for body in ('{', json.dumps({'debug_timings': [1, 2]}),
                     json.dumps({'debug_timings': {'key_quiet': 'x', 'ime_poll_active': -1}})):
            with open(self.path, 'w', encoding='utf-8') as f:
                f.write(body)
            b = bare_app(Settings(self.path))
            debug_menu.apply(b)
            self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 300, body)
            self.assertNotIn('_IME_POLL_ACTIVE_MS', b.__dict__)
            self.assertEqual(debug_menu.values(b)['ime_poll_active'], 30, body)
        # 範囲の外の値は丸めて入れる
        self.assertEqual(debug_menu.set_value(a, 'ime_quiet', 999, save=False), 100)
        self.assertNotIn('ime_quiet', a.settings.get('debug_timings'))
        self.assertEqual(debug_menu.set_value(a, 'ime_poll_active', -1, save=False), 1)
        self.assertEqual(a._IME_POLL_ACTIVE_MS, 1)

    def test_reset_to_default_restores_the_code_value(self):
        s = Settings(self.path)
        a = bare_app(s)
        debug_menu.set_value(a, 'key_quiet', 50)
        debug_menu.set_value(a, 'busy_gap', 1)
        debug_menu.set_value(a, 'quick_quiet', 10)
        self.assertEqual(quick_analysis.DISPLAY_QUIET_MS, 10)
        debug_menu.set_value(a, 'key_quiet', debug_menu.default('key_quiet', a))
        debug_menu.set_value(a, 'busy_gap', debug_menu.default('busy_gap', a))
        self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 300)
        self.assertNotIn('ANALYZE_BUSY_GAP_MS', a.__dict__)
        self.assertEqual(a.settings.get('debug_timings'), {'quick_quiet': 10})
        debug_menu.set_value(a, 'quick_quiet', 250)
        self.assertEqual(quick_analysis.DISPLAY_QUIET_MS, 250)
        self.assertEqual(Settings(self.path).get('debug_timings'), {})
        # DEFAULTS の空の辞書を共有して書き換えていない
        import settings as S
        self.assertEqual(S.DEFAULTS['debug_timings'], {})

    def test_an_empty_save_leaves_patched_module_constants_alone(self):
        a = bare_app(Settings())
        with patch.object(analysis_input, 'DISPLAY_QUIET_MS', 77):
            debug_menu.apply(a)
            self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 77)

    def test_changed_values_are_used(self):
        a = bare_app(Settings())
        # 表示の待ち（1字・IME の確定）
        debug_menu.set_value(a, 'key_quiet', 40, save=False)
        debug_menu.set_value(a, 'ime_quiet', 7, save=False)
        host = SimpleNamespace(editor_source_text=lambda: 'あ', _ime_comp='')
        self.assertEqual(analysis_input.quiet_ms(host), 40)
        host._ime_comp = 'か'
        self.assertEqual(analysis_input.quiet_ms(host), 7)
        # 打った行の答えを見に行く間隔（窓から外した項目・コードの 5ms のまま）
        gaps = []
        a.root = SimpleNamespace(after=lambda ms, fn: gaps.append(ms) or 'job')
        a._interacting = lambda: False
        a._typed_row_pending = lambda: True
        with patch('analysis_work_app.token', return_value=1):
            a._schedule_analysis_chunk()
            a._typed_row_pending = lambda: False
            # 既定（入力していない 20ms・入力中 30ms）はそのまま
            a._schedule_analysis_chunk()
            a._interacting = lambda: True
            a._schedule_analysis_chunk()
            # 20ms 未満も効く（もとの下限 max(20, …) を外した・2026-10-18）
            debug_menu.set_value(a, 'busy_gap', 4, save=False)
            a._schedule_analysis_chunk()
            debug_menu.set_value(a, 'poll', 3, save=False)
            a._interacting = lambda: False
            a._schedule_analysis_chunk()
        self.assertEqual(gaps, [5, 20, 30, 4, 3])

    def wheel_host(self):
        nav = object.__new__(app.CorrectNoteApp)
        nav.settings = Settings()
        nav._next_tab = Mock(); nav._close_dropdown = Mock(); nav._drag_release = Mock()
        nav._on_tab_wheel_press(None)
        return nav

    def event(self, tick, delta=-120):
        return SimpleNamespace(time=tick, delta=delta, state=0x0400, widget=None)

    def test_tab_wheel_defaults_and_changed_values_are_used(self):
        clock = [10.0]
        A = app.CorrectNoteApp
        with patch.object(app, 'wheel_message_time', side_effect=lambda e: e.time),                 patch.object(app, 'time', Mock(wraps=time, monotonic=lambda: clock[0])):
            # 量の既定は 120: ふつうの1目盛り（120）で1回。半目盛りでは切り替わらない
            nav = self.wheel_host()
            nav._tab_wheel(self.event(1000, -60), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 0)
            nav._tab_wheel(self.event(1100, -60), over_tabs=True)
            self.assertEqual(nav._next_tab.call_args_list, [((1,),)])
            nav = self.wheel_host()
            nav._tab_wheel(self.event(1000), over_tabs=True)
            self.assertEqual(nav._next_tab.call_args_list, [((1,),)])
            # 変えた量が使われる
            nav = self.wheel_host(); debug_menu.apply(nav, {'tab_wheel_step': 60})
            nav._tab_wheel(self.event(1000, -60), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 1)
            nav = self.wheel_host(); debug_menu.apply(nav, {'tab_wheel_step': 300})
            nav._tab_wheel(self.event(1000, -150), over_tabs=True)
            nav._tab_wheel(self.event(1100, -120), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 0)
            # 同じ向きは 47ms、逆向きは 20ms のあいだ受け付けない（境目の両側）
            step = A.TAB_WHEEL_STEP
            nav = self.wheel_host()
            nav._tab_wheel(self.event(2000, -step), over_tabs=True)
            nav._tab_wheel(self.event(2046, -step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 1)
            nav._tab_wheel(self.event(2047, -step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 2)
            nav._tab_wheel(self.event(2066, step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 2)
            nav._tab_wheel(self.event(2067, step), over_tabs=True)
            self.assertEqual([c[0] for c in nav._next_tab.call_args_list], [(1,), (1,), (-1,)])
            # 変えた待ちが使われる（逆向き 300ms）
            nav = self.wheel_host(); debug_menu.apply(nav, {'tab_wheel_reverse': 300})
            nav._tab_wheel(self.event(3000, -step), over_tabs=True)
            nav._tab_wheel(self.event(3299, step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 1)
            nav._tab_wheel(self.event(3300, step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 2)
            # 右ボタンを離したあと、逆向きは 20ms のあいだ受け付けない
            nav = self.wheel_host()
            clock[0] = 20.0
            nav._tab_wheel(self.event(4000, -step), over_tabs=True)
            nav._tab_wheel_hold_direction = 1
            nav._finish_tab_wheel_gesture()
            clock[0] = 20.019
            nav._tab_wheel(self.event(4500, step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 1)
            clock[0] = 20.021
            nav._tab_wheel(self.event(4600, step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 2)
            nav = self.wheel_host(); debug_menu.apply(nav, {'tab_wheel_release': 300})
            clock[0] = 30.0
            nav._tab_wheel(self.event(5000, -step), over_tabs=True)
            nav._tab_wheel_hold_direction = 1
            nav._finish_tab_wheel_gesture()
            clock[0] = 30.2
            nav._tab_wheel(self.event(5500, step), over_tabs=True)
            self.assertEqual(nav._next_tab.call_count, 1)

    def test_items_order_and_headings(self):
        # うにさんの指定（2026-10-18）: 4項目を外し、【解析】11項目・【タブ移動】4項目
        names = [item[1] for item in debug_menu.ITEMS]
        self.assertEqual(names, [
            'IME の確定から、補正を出すまでの待ち', '1字打ってから、補正を出すまでの待ち',
            '入力中に他の行の補正結果を認識する間隔', '補正結果を反映する間隔（入力中は無効）',
            '最後の操作から、入力中とみなす長さ', '見えている行の補正を、途中で出す間隔',
            '打った行を出したあと、周りの行を出す間隔', 'IME の変換中を見張る間隔',
            'IME の変換が始まったかを見張る間隔', '裏のタブの補正を始めるまで',
            '簡易入力：打ってから、補正を出すまでの待ち',
            'タブを切り替えるホイールの量（1目盛り＝120）', 'タブを切り替えたあと、同じ向きを受け付けるまで',
            'タブを切り替えたあと、逆向きを無視する間', '右ボタンを離したあと、逆向きを無視する間'])
        self.assertEqual(debug_menu.SECTIONS, (('ime_quiet', '【解析】'), ('tab_wheel_step', '【タブ移動】')))

    def test_removed_items_ignore_old_saved_values(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump({'debug_timings': {'compute_delay': 0, 'prepare_poll': 1, 'typed_poll': 1,
                                         'quick_compute': 0, 'key_quiet': 120}}, f)
        a = bare_app(Settings(self.path))
        debug_menu.apply(a)
        self.assertEqual((analysis_input.COMPUTE_DELAY_MS, analysis_async.PREPARE_POLL_MS,
                          a.ANALYZE_TYPED_POLL_MS, quick_analysis.COMPUTE_DELAY_MS), (1, 5, 5, 1))
        self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 120)
        # 次に保存するとき、外した項目の値は書かない
        debug_menu.set_value(a, 'ime_quiet', 50)
        self.assertEqual(Settings(self.path).get('debug_timings'), {'key_quiet': 120, 'ime_quiet': 50})

    def test_menu_has_the_debug_window(self):
        source = Path(app.__file__).read_text(encoding='utf-8')
        about = source.index("_make_menubutton('このアプリについて')")
        entry = source.index("m_about.add_command(label='デバッグメニュー…'")
        self.assertLess(about, entry)
        self.assertLess(entry, source.index("_make_menubutton('学習')"))


class DebugWindowTkTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'settings.json')
        self.root = tk.Tk(); self.root.geometry('200x100+0+0')
        self.errors = []; self.root.report_callback_exception = lambda *a: self.errors.append(a)
        self.a = bare_app(Settings(self.path)); self.a.root = self.root
        self.a._place_dialog = lambda dlg, w, h: dlg.geometry('%dx%d+0+0' % (w, h))

    def tearDown(self):
        debug_menu.apply(bare_app(Settings()), {})
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root', 'dlg')
        self.dir.cleanup()

    def settle(self):
        for _ in range(20):
            self.root.update(); time.sleep(0.01)

    def test_entry_and_slider_are_linked_and_saved(self):
        self.dlg = dlg = self.a.open_debug_menu()
        self.settle()
        self.assertEqual(dlg.title(), 'デバッグメニュー')
        self.assertIs(self.a.open_debug_menu(), dlg)   # 2つ目は開かない
        self.assertEqual(len(dlg._debug_rows), 15)
        def texts(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Label):
                    yield child, child.cget('text')
                yield from texts(child)
        heads = [(w, t) for w, t in texts(dlg) if t in ('【解析】', '【タブ移動】')]
        self.assertEqual([t for _, t in heads], ['【解析】', '【タブ移動】'])
        # 見出しは項目名より大きい太字で、【タブ移動】の前は1行あける
        self.assertIn('bold', str(heads[0][0].cget('font')))
        self.assertGreater(int(heads[1][0].grid_info()['pady'][0] if isinstance(heads[1][0].grid_info()['pady'], tuple)
                               else str(heads[1][0].grid_info()['pady']).split()[0]), 0)
        self.assertLess(heads[1][0].winfo_y(), dlg._debug_rows['tab_wheel_step']['entry'].master.winfo_y())
        row = dlg._debug_rows['key_quiet']
        self.assertEqual((row['text'].get(), row['number'].get()), ('300', 300))
        self.assertEqual((float(row['scale'].cget('from')), float(row['scale'].cget('to'))), (0.0, 300.0))
        # スライダー → 数値の欄・当てる
        row['scale'].set(120); self.settle()
        self.assertEqual(row['text'].get(), '120')
        self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 120)
        # 数値の欄 → スライダー（範囲の外は丸める・数でなければ戻す）
        row['text'].set('9999'); row['from_entry']()
        self.assertEqual((row['text'].get(), row['number'].get()), ('300', 300))
        row['text'].set('80'); row['from_entry'](); self.settle()
        self.assertEqual((row['number'].get(), analysis_input.DISPLAY_QUIET_MS), (80, 80))
        row['text'].set('abc'); row['from_entry']()
        self.assertEqual(row['text'].get(), '80')
        # 1ms 未満にできない項目
        poll = dlg._debug_rows['ime_poll_active']
        poll['text'].set('0'); poll['from_entry']()
        self.assertEqual((poll['text'].get(), self.a._IME_POLL_ACTIVE_MS), ('1', 1))
        # 閉じたら保存される（次の起動で読む）
        dlg.destroy(); self.settle()
        self.assertIsNone(self.a._debug_window)
        self.assertEqual(Settings(self.path).get('debug_timings'), {'key_quiet': 80, 'ime_poll_active': 1})
        # デフォルトに戻す
        self.dlg = dlg = self.a.open_debug_menu(); self.settle()
        dlg._debug_rows['key_quiet']['button'].invoke()
        self.assertEqual(analysis_input.DISPLAY_QUIET_MS, 300)
        self.assertEqual(dlg._debug_rows['key_quiet']['text'].get(), '300')
        dlg._debug_reset_all()
        self.assertNotIn('_IME_POLL_ACTIVE_MS', self.a.__dict__)
        dlg.destroy(); self.settle()
        self.assertEqual(Settings(self.path).get('debug_timings'), {})
        # 上限が既定より上の項目: スライダーは 1〜300、既定 120
        self.dlg = dlg = self.a.open_debug_menu(); self.settle()
        step = dlg._debug_rows['tab_wheel_step']
        self.assertEqual((float(step['scale'].cget('from')), float(step['scale'].cget('to'))), (1.0, 300.0))
        self.assertEqual(step['number'].get(), 120)
        step['text'].set('250'); step['from_entry'](); self.settle()
        self.assertEqual(self.a.TAB_WHEEL_STEP, 250)
        step['button'].invoke()
        self.assertEqual((self.a.TAB_WHEEL_STEP, step['text'].get()), (120, '120'))
        dlg.destroy(); self.settle()
        self.assertEqual(Settings(self.path).get('debug_timings'), {})
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
