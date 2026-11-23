# -*- coding: utf-8 -*-
"""行の末尾で候補を自動で出す・オンマウスで候補を出す（auto_candidates・2026-11-21 うにさん・どちらも既定オン）。
候補の窓は焦点を取らず、打った字は本文のカーソルの位置へ入る。アプリを試しの写し（プログラムと同梱の物だけ・作った
例文）で子として起こす。窓は画面の外。"""
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import auto_candidates as AC


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-auto-candidates-test-isolated').is_file()
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                        encoding='utf-8')
    body = '\n'.join(['きょうはいい天気です。', '明日も晴れるでしょう。', '', '雨の日は家で本を読みます。'])
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=body)]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(s, until=None):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
            if until is not None and until():
                return True
        return False
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        import offscreen_window; offscreen_window.hold(root)      # 作る間も見えない所に（画面の置き方に依らない）
        a = app.CorrectNoteApp(root)
        import offscreen_window; offscreen_window.hold(root, '1000x600')               # 画面の外
        pump(60, lambda: not a._foreground_analysis_pending() and len(a.line_results) >= 4 and all(a.line_results[:4]))
        pump(0.5)
        ed = a.editor
        # 試しの窓の置き場に左右されないように（2026-11-21）: この PC では新しい窓が画面の外ではなく縦長の画面へ寄せられ、
        # 本物のマウスが本文の欄の上にあると「マウスの近く」の置き場になって結果が変わった。マウスは欄の外に決めておく
        # （マウスの近くを見る所は、その所で位置を決め直している）。窓の大きさも決めた大きさに揃える
        ed.winfo_pointerxy = lambda: (-20000, -20000)
        # 窓が画面の外にある時、一覧の置き場の枠（窓と画面の作業域の重なり）が空になり、一覧が画面の左端（x=0）へ
        # 寄せられて「メモ欄の中」が測れなかった。画面の作業域は見ないで、窓の中を枠にする（画面の外でも内でも同じ）
        app.monitor_work_area = lambda x, y: None
        offscreen_window.hold(root, '1000x600')
        out['tags'] = AC.TAG in ed.bindtags() and AC.TAG in a.result_view.bindtags()
        focus = {'w': ed}
        with patch.object(root, 'focus_get', lambda: focus['w']):
            # --- 行の末尾 ---
            ed.mark_set('insert', '2.end')
            a._last_edit_at = 0.0
            out['line_end_open'] = AC.line_end_check(a)
            parts = AC.passive(a)
            out['line_end_kind'] = parts and parts.get('passive')
            out['line_end_focus_kept'] = bool(parts) and str(parts['lb']) != str(root.focus_get())
            out['line_end_again'] = AC.line_end_check(a)                      # 同じ所には出し直さない
            # 下の行の字を隠さないよう、重なる行の字の右の余白へ（01:37Z）
            if parts:
                root.update_idletasks()
                dd = parts['dd']
                rights = []
                for r in (3, 4):
                    d = ed.dlineinfo('%d.0' % r)
                    if d:
                        rights.append(ed.winfo_rootx() + d[0] + d[2])
                cur = ed.dlineinfo('2.0')
                out['side_x_ok'] = dd.winfo_rootx() >= max(rights or [0])
                out['side_y_below_row'] = dd.winfo_rooty() >= ed.winfo_rooty() + cur[1] + cur[3] - 1
                memo_right = ed.winfo_rootx() + ed.winfo_width()
                out['inside_memo'] = dd.winfo_rootx() + dd.winfo_width() <= memo_right      # 補正欄を隠さない（05:09Z）
            # 余白が無い時もメモ欄の右端（補正欄は隠さない）
            AC.close(a)
            ed.insert('3.0', 'あ' * 200)
            root.update()
            ed.mark_set('insert', '2.end')
            a._last_edit_at = 0.0
            a._line_end_dismissed = None
            AC.line_end_check(a)
            p2 = AC.passive(a)
            if p2:
                root.update_idletasks()
                out['no_margin_inside_memo'] = (p2['dd'].winfo_rootx() + p2['dd'].winfo_width()
                                                <= ed.winfo_rootx() + ed.winfo_width())
            AC.close(a)
            ed.delete('3.0', '3.200')
            root.update()
            ed.mark_set('insert', '2.end')
            a._line_end_dismissed = None
            AC.line_end_check(a)
            parts = AC.passive(a)
            # 打った字は本文へ（窓は閉じ、キーは素通し）
            out['typed_passes'] = AC.on_key(a, NS(keysym='a', char='a')) is None
            out['typed_closed'] = AC.passive(a) is None
            # Esc で閉じた所には出し直さない
            AC.line_end_check(a, now=time.monotonic() + 1)
            AC.line_end_check(a)
            out['esc'] = AC.on_key(a, NS(keysym='Escape', char=''))
            out['after_esc'] = AC.line_end_check(a)
            # 字を消した後は出す（01:37Z）・打った後は出さない
            AC.close(a); a._line_end_dismissed = None
            ed.mark_set('insert', '4.end')
            a._last_edit_at = time.monotonic()
            AC.on_key(a, NS(keysym='BackSpace', char=''))
            out['after_delete'] = AC.line_end_check(a)
            AC.close(a)
            with patch.dict(os.environ, {'CN_AUTO_AFTER_DELETE': '0'}):
                out['after_delete_off'] = AC.line_end_check(a)
            AC.on_key(a, NS(keysym='a', char='a'))                           # 打った字で消した印は消える
            out['after_type'] = AC.line_end_check(a)
            # 起動・タブの切り替えの直後は出さない（カーソルが一度動くまで）
            a._last_edit_at = 0.0
            AC.settle(a)
            root.update()
            out['settle_now'] = AC.line_end_check(a)
            a._auto_settle['at'] = 0.0
            out['settle_same_place'] = AC.line_end_check(a)
            ed.mark_set('insert', '2.end')
            out['settle_moved'] = AC.line_end_check(a)
            AC.close(a)
            with patch.dict(os.environ, {'CN_AUTO_SIDE': '0'}):
                ed.mark_set('insert', '1.end')
                AC.line_end_check(a)
                p0 = AC.passive(a)
                if p0:
                    root.update_idletasks()
                    cur = ed.dlineinfo('1.0')
                    out['old_below_caret'] = p0['dd'].winfo_rooty() >= ed.winfo_rooty() + cur[1] + cur[3] - 1
                AC.close(a)
            # スクロールした直後は出さない（03:01Z）
            AC.close(a); a._line_end_dismissed = None
            ed.mark_set('insert', '4.end')
            a._close_menu_on_scroll()                                        # ホイール・右ドラッグ・スクロールバーの入口
            out['after_scroll'] = AC.line_end_check(a)
            out['after_scroll_later'] = AC.line_end_check(a, now=time.monotonic() + AC.SCROLL_QUIET_S + 0.1)
            AC.on_press(a, NS(num=3))                                          # 右ボタン（右ドラッグのスクロール）では下ろさない
            out['after_scroll_right_press'] = AC.line_end_check(a, now=time.monotonic() + AC.SCROLL_QUIET_S + 0.1)
            AC.on_press(a, NS(num=1))                                          # 左クリックで下ろす
            out['after_scroll_click'] = AC.line_end_check(a, now=time.monotonic() + AC.SCROLL_QUIET_S + 0.1)
            AC.close(a); a._line_end_dismissed = None
            a._close_menu_on_scroll()
            AC.on_key(a, NS(keysym='Down', char=''))                           # キーで下ろす
            out['after_scroll_key'] = AC.line_end_check(a, now=time.monotonic() + AC.SCROLL_QUIET_S + 0.1)
            AC.close(a)
            with patch.dict(os.environ, {'CN_AUTO_SCROLL_QUIET': '0'}):
                a._auto_scrolled_at = None
                a._close_menu_on_scroll()
                out['after_scroll_off'] = AC.line_end_check(a)
            AC.close(a)
            # 本人のキー・左クリックの後だけ予約する（07:44Z）: プログラムが動かしたカーソルでは予約しない
            AC.close(a); a._line_end_dismissed = None
            a._auto_user_at = None
            AC._cancel(a, '_line_end_job')
            ed.mark_set('insert', '1.end'); a._sync_cursor_line(ed, force=True)
            out['program_move_job'] = getattr(a, '_line_end_job', None) is not None
            AC.on_key(a, NS(keysym='End', char=''))
            ed.mark_set('insert', '2.end'); a._sync_cursor_line(ed, force=True)
            out['user_move_job'] = getattr(a, '_line_end_job', None) is not None
            AC._cancel(a, '_line_end_job')
            a._auto_user_at = None
            with patch.dict(os.environ, {'CN_AUTO_USER_ONLY': '0'}):
                ed.mark_set('insert', '1.end'); a._sync_cursor_line(ed, force=True)
                out['program_move_job_off'] = getattr(a, '_line_end_job', None) is not None
            AC._cancel(a, '_line_end_job')
            # 右に字がある所・打った直後・切り替え・選択中は出さない
            a._line_end_dismissed = None
            ed.mark_set('insert', '1.2')
            out['right_has_text'] = AC.line_end_check(a)
            ed.mark_set('insert', '4.end')
            a._last_edit_at = time.monotonic()
            out['just_typed'] = AC.line_end_check(a)
            a._last_edit_at = 0.0
            with patch.dict(os.environ, {'CN_AUTO_LINE_END': '0'}):
                out['switch_off'] = AC.line_end_check(a)
            a.settings.set('f5_auto_line_end', False)
            out['setting_off'] = AC.line_end_check(a)
            a.settings.set('f5_auto_line_end', True)
            ed.tag_add('sel', '4.0', '4.2')
            out['with_selection'] = AC.line_end_check(a)
            ed.tag_remove('sel', '1.0', 'end')
            out['empty_row'] = AC.line_end_check(a) if (ed.mark_set('insert', '3.0') or True) else None
            AC.close(a)
            # --- オンマウス（分割の補正欄・メモ欄） ---
            for name, w in (('result', a.result_view), ('editor', ed)):
                bbox = w.bbox('1.7')                               # 「天気」の上（同音の語が候補に出る）
                x, y = bbox[0] + 2, bbox[1] + 2
                ev = NS(x=x, y=y, x_root=w.winfo_rootx() + x, y_root=w.winfo_rooty() + y, widget=w, state=0)
                hit = AC._hit(a, w, ev)
                out[name + '_hit'] = bool(hit)
                if not hit:
                    continue
                key = AC._key(hit)
                with patch.object(w, 'winfo_pointerxy', lambda ev=ev: (ev.x_root, ev.y_root)), \
                        patch.object(w, 'winfo_width', lambda: 1000), patch.object(w, 'winfo_height', lambda: 1000):
                    out[name + '_shown'] = AC.hover_show(a, w, key, dict(x=x, y=y, x_root=ev.x_root, y_root=ev.y_root))
                    # 2026-11-22 CN_HOVER_ASYNC: 一覧の中身は子への頼みを待たずに出し、答えが来てから組み立てる。出るまで待つ
                    end_wait = time.monotonic() + 3.0
                    while time.monotonic() < end_wait and (AC.passive(a) or {}).get('passive') != 'hover':
                        pump(0.02)
                    out[name + '_shown'] = bool(out[name + '_shown'] or (AC.passive(a) or {}).get('passive') == 'hover')
                    parts = AC.passive(a)
                    out[name + '_kind'] = parts and parts.get('passive')
                    if not parts:      # 出なかった訳（調べ用）
                        try:
                            a._dropdown_passive = 'hover'
                            (a._open_dropdown if name == 'result' else a._open_editor_dropdown)(ev, hit[1], hit[2])
                            out[name + '_why'] = 'direct:%s %s' % (bool(AC.passive(a)), a.status.cget('text'))
                        except Exception as error:
                            out[name + '_why'] = traceback.format_exc()[-600:]
                        finally:
                            a._dropdown_passive = None
                        out[name + '_busy'] = AC.busy(a, w)
                        AC.close(a)
                    out[name + '_again'] = AC.hover_show(a, w, key, dict(x=x, y=y, x_root=ev.x_root, y_root=ev.y_root))
                    # オンマウスの一覧が出ている間は、行の末尾の予測で置き換えない（06:33Z）
                    ed.mark_set('insert', '2.end')
                    a._last_edit_at = 0.0; a._auto_settle = None; a._auto_scroll_hold = False; a._line_end_dismissed = None
                    out[name + '_line_end_blocked'] = (AC.line_end_check(a) is False
                                                       and (AC.passive(a) or {}).get('passive') == 'hover')
                    if parts:
                        with patch.dict(os.environ, {'CN_HOVER_ARROWS_MOVE_CURSOR': '0'}):     # 前の形: 一覧を選ぶ
                            out[name + '_down'] = AC.on_key(a, NS(keysym='Down', char=''))
                            out[name + '_selected'] = bool(parts['lb'].curselection())
                        out[name + '_down_new'] = AC.on_key(a, NS(keysym='Down', char=''))   # 07:34Z: 閉じて本文へ
                        out[name + '_down_closed'] = AC.passive(a) is None
                        AC.hover_show(a, w, key, dict(x=x, y=y, x_root=ev.x_root, y_root=ev.y_root))
                        end_wait = time.monotonic() + 3.0
                        while time.monotonic() < end_wait and (AC.passive(a) or {}).get('passive') != 'hover':
                            pump(0.02)                                   # 子の答えが来て出るまで（CN_HOVER_ASYNC）
                        parts = AC.passive(a) or parts
                        before = ed.get('1.0', 'end-1c')
                        out[name + '_type'] = AC.on_key(a, NS(keysym='x', char='x'))
                        out[name + '_closed'] = AC.passive(a) is None
                        out[name + '_text_same'] = ed.get('1.0', 'end-1c') == before      # 閉じるだけ（打つのは本文の欄）
            # --- F5 の予測は1つ目を選んで開く・スクロールで一覧を閉じる（2026-11-21 02:59Z） ---
            AC.close(a)
            def open_predict():
                ed.mark_set('insert', '2.end')
                a._close_dropdown()
                ok = a._f5_predict_open(ed, 2, len(ed.get('2.0', '2.end')), 'main')
                root.update_idletasks()
                return ok
            open_predict()
            parts = a._dropdown_parts or {}
            out['predict_first'] = list(parts['lb'].curselection()) if parts else None
            # 上下キーは端で反対の端へ回る（07:36Z・押せない見出しは飛ばす）
            if parts:
                lb0 = parts['lb']
                live = [k for k, (_l, cb) in enumerate(parts['items']) if cb is not None]
                parts['move'](-1)
                out['wrap_up'] = (list(lb0.curselection()), live[-1])
                parts['move'](1)
                out['wrap_down'] = (list(lb0.curselection()), live[0])
            with patch.dict(os.environ, {'CN_F5_PREDICT_WRAP': '0'}):
                open_predict()
                p3 = a._dropdown_parts
                p3['move'](-1)
                out['wrap_off'] = list(p3['lb'].curselection())
            with patch.dict(os.environ, {'CN_F5_PREDICT_SELECT_FIRST': '0'}):
                open_predict()
                out['predict_first_off'] = list(a._dropdown_parts['lb'].curselection())
            outside = (ed.winfo_rootx() + 5, ed.winfo_rooty() + 5)
            wheel = NS(delta=-120, widget=ed, x=5, y=5, x_root=outside[0], y_root=outside[1], state=0)
            open_predict()
            with patch.object(a._dropdown, 'winfo_pointerxy', lambda: outside):
                a._on_wheel(wheel)
            out['wheel_pane_closed'] = a._dropdown is None
            open_predict()
            lb = a._dropdown_parts['lb']
            with patch.object(a._dropdown, 'winfo_pointerxy', lambda: outside):
                out['wheel_list'] = a._on_menu_wheel(NS(delta=-120, widget=lb, x_root=outside[0], y_root=outside[1]))
            out['wheel_list_closed'] = a._dropdown is None
            open_predict()
            dd = a._dropdown
            inside = (dd.winfo_rootx() + 3, dd.winfo_rooty() + 3)
            with patch.object(dd, 'winfo_pointerxy', lambda: inside):
                a._on_menu_wheel(NS(delta=-120, widget=a._dropdown_parts['lb'], x_root=inside[0], y_root=inside[1]))
            out['wheel_on_list_kept'] = a._dropdown is not None                  # 一覧の上のホイールは一覧を動かす
            with patch.object(a._dropdown, 'winfo_pointerxy', lambda: outside):
                a._on_scrollbar('scroll', 1, 'units')
            out['scrollbar_closed'] = a._dropdown is None
            open_predict()
            with patch.object(a._dropdown, 'winfo_pointerxy', lambda: outside):
                a._note_user_scroll()
            out['drag_scroll_closed'] = a._dropdown is None
            open_predict()
            with patch.dict(os.environ, {'CN_CLOSE_MENU_ON_SCROLL': '0'}),                     patch.object(a._dropdown, 'winfo_pointerxy', lambda: outside):
                a._on_wheel(wheel)
                out['wheel_switch_kept'] = a._dropdown is not None
            a._close_dropdown()
            with patch.dict(os.environ, {'CN_HOVER_CANDIDATES': '0'}):
                w = a.result_view
                bbox = w.bbox('4.1')
                ev = NS(x=bbox[0] + 2, y=bbox[1] + 2, x_root=0, y_root=0, widget=w, state=0)
                AC.on_motion(a, ev)
                out['hover_switch_job'] = getattr(a, '_hover_job', None) is not None
            # ボタンを押している間（ドラッグ）は予約しない
            AC.on_motion(a, NS(x=ev.x, y=ev.y, x_root=0, y_root=0, widget=a.result_view, state=0x100))
            out['drag_job'] = getattr(a, '_hover_job', None) is not None
        assert not errors, errors
        print('AUTO_CANDIDATES', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


def run_child(test, env=None):
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-auto-candidates-') as directory:
        dest = Path(directory).resolve()
        for entry in source.iterdir():
            if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                shutil.copy2(entry, dest / entry.name)
        (dest / '.ui-auto-candidates-test-isolated').touch()
        environ = dict(os.environ)
        environ.update(env or {})
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                             cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ,
                             encoding='utf-8', errors='replace', timeout=300)
        test.assertEqual(run.returncode, 0, run.stdout[-3000:])
        line = [l for l in run.stdout.splitlines() if l.startswith('AUTO_CANDIDATES ')]
        test.assertTrue(line, run.stdout[-3000:])
        return json.loads(line[0][len('AUTO_CANDIDATES '):])


class Pure(unittest.TestCase):
    def app(self, **settings):
        return NS(settings=dict(settings), _dropdown=None, _dropdown_parts=None)

    def test_switches_and_settings(self):
        a = self.app()
        self.assertTrue(AC.line_end_on(a) and AC.hover_on(a))                     # 既定オン
        self.assertFalse(AC.line_end_on(a, {'CN_AUTO_LINE_END': '0'}))
        self.assertFalse(AC.hover_on(a, {'CN_HOVER_CANDIDATES': '0'}))
        self.assertFalse(AC.line_end_on(self.app(f5_auto_line_end=False)))
        self.assertFalse(AC.hover_on(self.app(hover_candidates=False)))

    def test_keys_without_a_passive_window_pass(self):
        a = self.app()
        self.assertIsNone(AC.on_key(a, NS(keysym='Down', char='')))
        a._dropdown = object()
        a._dropdown_parts = dict(passive='hover', move=lambda step: None)
        a._close_dropdown = lambda: setattr(a, '_dropdown', None)
        self.assertIsNone(AC.on_key(a, NS(keysym='Shift_L', char='')))             # 修飾キーだけでは閉じない
        self.assertIsNotNone(a._dropdown)


class SidePositionEnds(unittest.TestCase):
    # 2026-11-21 03:50Z うにさん「起動したら重すぎて応答なし」: 窓が文の最後の行より下へかかると、_text_edges が同じ所を
    # 回り続けていた（'@0,y' は最後の行を返すので y が戻る）。短い文の最後の行で置き場を求めて、すぐ戻ることを見る
    def test_short_text_at_the_last_line_returns(self):
        import tkinter as tk
        import time as _t
        root = tk.Tk()
        self.addCleanup(root.destroy)
        import offscreen_window; offscreen_window.hold(root, '600x400')
        t = tk.Text(root)
        t.pack(fill='both', expand=True)
        t.insert('1.0', 'abc' + chr(10) + 'def')
        t.mark_set('insert', '2.end')
        root.update()
        start = _t.monotonic()
        got = AC.side_position(NS(editor=t), 120, 300, (-5000, -5000, 5000, 5000))
        self.assertLess(_t.monotonic() - start, 1.0)
        self.assertIsNotNone(got)
        self.assertLess(_t.monotonic() - start, 1.0)
        right, first = AC._text_edges(t, 10 ** 4, 300, 10 ** 5)                    # 欄より下の所でも止まる
        self.assertEqual((right, first), (right, first))


class HoverLight(unittest.TestCase):
    # 2026-11-21 08:17Z（軽量化）: 動きの知らせでは語を見分けない（前は知らせごとに _hit・メモ欄で1回 15ms）。止まってから1回
    def test_motion_does_not_look_up_words(self):
        import tkinter as tk
        from unittest import mock
        root = tk.Tk(); root.withdraw()
        self.addCleanup(root.destroy)
        text = tk.Text(root)
        text.insert('1.0', 'きょうはいい天気です。')
        app = NS(settings={}, root=root, editor=text, _dropdown=None, _dropdown_parts=None)
        calls = []
        with mock.patch.object(AC, '_hit', lambda app, w, e: calls.append(1)),                 mock.patch.object(AC, 'hover_show', lambda *a: True):
            for x in range(0, 200, 4):
                AC.on_motion(app, NS(x=x, y=5, x_root=x, y_root=5, widget=text, state=0))
            self.assertEqual(calls, [])                                          # 知らせごとには見分けない
            self.assertIsNotNone(app._hover_job)                                 # 止まるのを待つ
            AC._cancel(app, '_hover_job')
            AC._hover_rest(app, text, dict(x=10, y=5, x_root=10, y_root=5))
            self.assertEqual(calls, [1])                                         # 止まって1回
            with mock.patch.dict(os.environ, {'CN_HOVER_LIGHT': '0'}):
                AC.on_motion(app, NS(x=10, y=5, x_root=10, y_root=5, widget=text, state=0))
                self.assertEqual(len(calls), 2)                                  # 前の形: 知らせごとに見分ける
            AC._cancel(app, '_hover_job')


class HoverNoChildAsk(unittest.TestCase):
    # 2026-11-21（軽量化）: オンマウスでは、控えに単位の無い行で解析の子に尋ねない（尋ねると子が解いている行を取り消す）
    def test_rows_without_units_are_skipped(self):
        import tkinter as tk
        from unittest import mock
        root = tk.Tk(); root.withdraw()
        self.addCleanup(root.destroy)
        text = tk.Text(root)
        text.insert('1.0', 'あいう')
        asked = []
        # 語の切れ目の控えにその語がある形（2026-11-22 CN_HOVER_WORD_ONLY: 控えに無い語＝空白で区切った塊は出さない）
        app = NS(editor=text, result_view=None, _layout_is_unified=lambda: False, _suspect_units_cache={},
                 _units_for_row=lambda row: [dict(text='あいう', start=0, end=3)],
                 _editor_unit_under_pointer=lambda e: asked.append(1) or (1, dict(text='あいう', start=0, end=3)))
        ev = NS(x=2, y=2, x_root=0, y_root=0, widget=text, state=0)
        import ui_projection
        with mock.patch.object(ui_projection, 'results', lambda app: [dict(original='あいう', corrected='あいう')]):
            self.assertIsNone(AC._hit(app, text, ev))
            self.assertEqual(asked, [])                                          # 子に尋ねる道へ行かない
            app._suspect_units_cache[('あいう', 'あいう', False)] = ('x', [])
            self.assertIsNotNone(AC._hit(app, text, ev))                          # 控えがあれば出す
            app._suspect_units_cache.clear()
            with mock.patch.dict(os.environ, {'CN_HOVER_NO_CHILD_ASK': '0'}):
                self.assertIsNotNone(AC._hit(app, text, ev))                      # 前の形


class NounWarm(unittest.TestCase):
    # 2026-11-21（軽量化）: 行頭の予測の周りの名詞を、待ちの間に少しずつ数えて控える（答えは同じ関数・同じ行）
    def test_warm_fills_the_memo_in_steps(self):
        import tkinter as tk
        import f5_predict
        root = tk.Tk(); root.withdraw()
        self.addCleanup(root.destroy)
        text = tk.Text(root)
        text.insert('1.0', chr(10).join('会議%dの資料を作る' % i for i in range(1, 30)) + chr(10))
        text.mark_set('insert', 'end-1c')                                       # 空の最後の行（行頭の候補を出す所）
        app = NS(root=root, settings={})
        f5_predict._NOUN_MEMO.clear()
        AC.warm_nouns(app, text)
        self.assertIsNotNone(app._noun_warm_job)
        end = time.monotonic() + 5
        while app._noun_warm_job is not None and time.monotonic() < end:
            root.update()
        lines = [text.get('%d.0' % r, '%d.end' % r) for r in range(1, 30)]
        self.assertTrue(all(line in f5_predict._NOUN_MEMO for line in lines))    # 上の行は全部控えた
        f5_predict._NOUN_MEMO.clear()
        text.mark_set('insert', '5.3')                                           # 字の途中
        with mock.patch.dict(os.environ, {'CN_AUTO_NOUN_WARM_ANYWHERE': '0'}):
            AC.warm_nouns(app, text)
            self.assertIsNone(getattr(app, '_noun_warm_job', None))              # 前の形: 行頭でなければ始めない
        AC.warm_nouns(app, text)
        self.assertIsNotNone(app._noun_warm_job)                                 # 2026-11-22 からはどこでも始める
        AC._cancel(app, '_noun_warm_job')
        text.mark_set('insert', 'end-1c')
        with mock.patch.dict(os.environ, {'CN_AUTO_NOUN_WARM': '0'}):
            AC.warm_nouns(app, text)
            self.assertIsNone(app._noun_warm_job)


class InTheApp(unittest.TestCase):
    def test_line_end_and_hover(self):
        got = run_child(self)
        self.assertTrue(got['tags'], got)
        self.assertTrue(got['line_end_open'], got)
        self.assertEqual(got['line_end_kind'], 'line_end')
        self.assertTrue(got['line_end_focus_kept'])
        self.assertFalse(got['line_end_again'])
        self.assertTrue(got['typed_passes'] and got['typed_closed'], got)
        self.assertEqual(got['esc'], 'break')
        self.assertFalse(got['after_esc'])
        self.assertTrue(got['side_x_ok'] and got['side_y_below_row'], got)        # 右の余白・下の行の横
        self.assertTrue(got['inside_memo'] and got.get('no_margin_inside_memo'), got)   # 分割で補正欄を隠さない
        self.assertTrue(got['after_delete'], got)                                  # 消した後は出す
        self.assertFalse(got['after_delete_off'])
        self.assertFalse(got['after_type'])
        self.assertEqual((got['settle_now'], got['settle_same_place'], got['settle_moved']), (False, False, True), got)
        self.assertTrue(got.get('old_below_caret'), got)
        self.assertFalse(got['program_move_job'], got)                           # プログラムが動かした: 予約しない
        self.assertTrue(got['user_move_job'], got)                                # 本人のキーの後: 予約する
        self.assertTrue(got['program_move_job_off'], got)
        self.assertFalse(got['after_scroll'], got)                                 # スクロールした直後は出さない
        self.assertFalse(got['after_scroll_later'], got)                           # 1秒たっても、動かすまで出さない（05:16Z）
        self.assertFalse(got['after_scroll_right_press'], got)
        self.assertTrue(got['after_scroll_click'], got)
        self.assertTrue(got['after_scroll_key'], got)
        self.assertTrue(got['after_scroll_off'], got)
        for k in ('right_has_text', 'just_typed', 'switch_off', 'setting_off', 'with_selection'):
            self.assertFalse(got[k], (k, got))
        self.assertTrue(got['empty_row'], got)                                     # 行頭（空の行）でも
        for name in ('result', 'editor'):                                          # 分割の両欄で
            self.assertTrue(got[name + '_hit'], (name, got))
            self.assertTrue(got[name + '_shown'], (name, got))
            self.assertEqual(got[name + '_kind'], 'hover')
            self.assertFalse(got[name + '_again'])                                 # 同じ語では出し直さない
            self.assertTrue(got[name + '_line_end_blocked'], (name, got))          # オンマウスの一覧を予測で消さない
            self.assertEqual(got[name + '_down'], 'break')
            self.assertTrue(got[name + '_selected'])
            self.assertIsNone(got[name + '_down_new'])                              # 上下キーは本文のカーソル移動へ
            self.assertTrue(got[name + '_down_closed'])
            self.assertIsNone(got[name + '_type'])                                 # 打った字は本文の欄へ素通し
            self.assertTrue(got[name + '_closed'] and got[name + '_text_same'])
        self.assertEqual(got['predict_first'], [0], got)                         # F5 の予測は1つ目を選んで開く
        self.assertEqual(got['predict_first_off'], [], got)
        self.assertEqual(got['wrap_up'][0], [got['wrap_up'][1]], got)          # 上の端から上 → 下の端
        self.assertEqual(got['wrap_down'][0], [got['wrap_down'][1]], got)      # 下の端から下 → 上の端
        self.assertEqual(got['wrap_off'], [0], got)                             # 前の形（端で止まる）
        for k in ('wheel_pane_closed', 'wheel_list_closed', 'wheel_on_list_kept', 'scrollbar_closed',
                  'drag_scroll_closed', 'wheel_switch_kept'):
            self.assertTrue(got[k], (k, got))
        self.assertEqual(got['wheel_list'], 'break')
        self.assertFalse(got['hover_switch_job'])
        self.assertFalse(got['drag_job'])


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        unittest.main()
