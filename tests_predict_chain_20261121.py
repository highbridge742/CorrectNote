# -*- coding: utf-8 -*-
"""予測を選んで字が入ったら、次の予測を続けて出す（2026-11-21 09:58Z うにさん・predict_chain）。CN_PREDICT_CHAIN=0 で
前の形。作り物の候補の口（f5_predict.set_provider）と作った例文だけ。アプリは写しの中の子で、窓は画面の外。"""
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
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='今日は本を読みました\n二行目です')]), ensure_ascii=False), encoding='utf-8')
    asked = []
    def provider(a, w, row, col, before):
        asked.append(before)
        return [] if before.endswith('予測B') else ['予測A', '予測B']
    f5_predict.set_provider(provider)
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
        import offscreen_window; offscreen_window.hold(root, '900x600')
        end = time.monotonic() + 60
        while time.monotonic() < end and (a._foreground_analysis_pending() or len(a.line_units) < 1 or not a.line_units[0]):
            pump(0.1)
        ed = a.editor
        with patch.object(root, 'focus_get', lambda: ed):
            def f5():
                a._on_f2_candidates(NS(widget=ed, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0)); pump(0.2)
            def state():
                parts = getattr(a, '_dropdown_parts', None) or {}
                lb = parts.get('lb')
                sel = list(lb.curselection()) if lb is not None and a._dropdown is not None else None
                return dict(open=a._dropdown is not None and a._f5_predict is not None, sel=sel,
                            passive=parts.get('passive') if a._dropdown is not None else None)
            # 1) F5 で開いた予測を選ぶ → 入れた後ろで、同じ形（1つ目を選んだ形）で続けて出る
            ed.mark_set('insert', '1.end'); f5()
            out['f5'] = state()
            a._close_dropdown(); a._f5_predict_insert(ed, 'main', '予測A', kind=None); pump(0.2)
            out['chain_f5'] = state(); out['chain_f5_asked'] = asked[-1]
            out['text1'] = ed.get('1.0', '1.end')
            # 2) 続けて出た一覧は、その上で押していない離しでは決めない
            lb = (getattr(a, '_dropdown_parts', None) or {}).get('lb')
            if lb is not None:
                lb.event_generate('<ButtonRelease-1>', x=5, y=5); pump(0.1)
            out['stray_release_text'] = ed.get('1.0', '1.end'); out['stray_release_open'] = state()['open']
            # 3) Esc で止まる
            a._close_dropdown(); pump(0.3)                     # Esc と同じ閉じ方
            out['after_esc'] = state()['open']
            # 4) 行末の自動の形（焦点を取らない）で選ぶ → 同じ自動の形で続けて出る（選ばない）
            ed.mark_set('insert', '1.end')
            a._dropdown_passive = 'line_end'
            a._f5_predict_open(ed, 1, len(ed.get('1.0', '1.end')), 'main')
            a._dropdown_passive = None
            a._close_dropdown(); a._f5_predict_insert(ed, 'main', '予測A', kind='line_end'); pump(0.2)
            out['chain_passive'] = state()
            out['chain_passive_where'] = (AC.passive(a) or {}).get('where') == AC._where(ed)
            a._close_dropdown(); pump(0.1)
            # 5) 入れた直後に別のキーでカーソルが動いた → 出さない
            ed.mark_set('insert', '1.end')
            a._f5_predict_insert(ed, 'main', '予測A', kind=None)
            ed.mark_set('insert', '1.0'); pump(0.2)
            out['moved_before'] = state()['open']
            a._close_dropdown(); pump(0.1)
            # 6) 予測が無い時は出さない
            ed.mark_set('insert', '1.end')
            a._f5_predict_insert(ed, 'main', '予測B', kind=None); pump(0.2)
            out['no_candidates'] = state()['open']
            a._close_dropdown(); pump(0.1)
            # 7) 行頭の予測（右に字が残る）でも続けて出す
            ed.mark_set('insert', '2.0')
            a._f5_predict_insert(ed, 'main', '・', kind=None); pump(0.2)
            out['chain_head'] = state(); out['chain_head_asked'] = asked[-1]
            a._close_dropdown(); pump(0.1)
            # 8) スクロールの後の止めが立っていれば出さない
            a._auto_scroll_hold = True
            ed.mark_set('insert', '1.end')
            a._f5_predict_insert(ed, 'main', '予測A', kind=None); pump(0.2)
            out['scroll_hold'] = state()['open']
            a._auto_scroll_hold = False
            a._close_dropdown(); pump(0.1)
            # 9) 一番上で上キー → カスタム候補（行頭の候補の並び）の一番下（14:39Z・CN_F5_WRAP_TO_CUSTOM）。
            #    本物の候補の口で、行頭の候補の下にクリップボードと周りの名詞を並べる
            f5_predict.set_provider(None)
            with patch.object(f5_predict, 'clipboard_text', lambda app: 'クリップの字'),                     patch.object(f5_predict, 'around_nouns', lambda w, row, *a, **k: ['名詞あ', '名詞い']):
                ed.mark_set('insert', '2.0')
                # 待ち方を条件で（2026-11-22）: 重い時に、前のカーソルの動きで予約された行の末尾の自動の候補が F5 の前に開き、
                # F5 がそちらを相手にして落ちた。F5 の前に予約を取り消して一覧が無いのを確かめ、F5 の後は予測の一覧が開くまで待つ
                AC._cancel(a, '_line_end_job'); AC._cancel(a, '_hover_job'); AC.close(a); a._close_dropdown()
                end = time.monotonic() + 5.0
                while time.monotonic() < end and a._dropdown is not None:
                    pump(0.05)
                a._on_f2_candidates(NS(widget=ed, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0))
                end = time.monotonic() + 5.0
                while time.monotonic() < end and not (a._dropdown is not None and a._f5_predict is not None):
                    pump(0.05)
                pump(0.1)
                parts = getattr(a, '_dropdown_parts', None) or {}
                lb = parts.get('lb')
                items = list(lb.get(0, 'end')) if lb is not None else []
                import f5_predict_window as _FW
                custom = [_FW.marked(c) for c in (getattr(a, '_f5_custom_items', None) or ())]   # 一覧は空白を印で見せる
                out['wrap_items'] = len(items)
                hits = [i for i, c in enumerate(items) if c in custom]
                out['wrap_custom_last'] = max(hits) if hits else None
                out['wrap_debug'] = dict(passive=parts.get('passive'), custom=len(custom), first=items[:3])
                out['wrap_has_clip'] = 'クリップの字' in items
                if parts.get('move') is not None:
                    lb.selection_clear(0, 'end'); lb.selection_set(0)
                    parts['move'](-1)
                    out['wrap_up_to'] = list(lb.curselection())
                    lb.selection_clear(0, 'end'); lb.selection_set(len(items) - 1)
                    parts['move'](1)
                    out['wrap_down_to'] = list(lb.curselection())
                a._close_dropdown(); pump(0.1)
            f5_predict.set_provider(provider)
        out['errors'] = errors
        import offscreen_window; out['on_screen'] = offscreen_window.on_a_screen(root)
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
    d = Path(tempfile.mkdtemp(prefix='cn-chain-'))
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
    def test_chain(self):
        got = run_child(self)
        self.assertEqual(got['errors'], [], got)
        self.assertTrue(got['f5']['open'], got)
        self.assertTrue(got['chain_f5']['open'], got)                         # 選んで入れたら続けて出る
        # 続けて出す一覧は、F5 で開いた後でも焦点を取らず候補も選んでいない形（14:36Z うにさん「予測決定後に出す予測は、
        # 候補がフォーカスしていない状態にする」・CN_PREDICT_CHAIN_NO_FOCUS）。前は F5 の形（1つ目を選んだ形）
        self.assertEqual(got['chain_f5']['sel'], [], got)
        self.assertEqual(got['chain_f5']['passive'], 'line_end', got)
        self.assertEqual(got['f5']['sel'], [0], got)                          # F5 を押して最初に開く時は今のまま1つ目
        # 一番上で上キー → カスタム候補の一番下（クリップボード・名詞の上）。一番下で下キー → 一番上（14:39Z）
        self.assertTrue(got['wrap_has_clip'], got)
        self.assertLess(got['wrap_custom_last'], got['wrap_items'] - 1, got)
        self.assertEqual(got['wrap_up_to'], [got['wrap_custom_last']], got)
        self.assertEqual(got['wrap_down_to'], [0], got)
        self.assertEqual(got['chain_f5_asked'], '今日は本を読みました予測A')    # 入った後ろの位置で
        self.assertEqual(got['stray_release_text'], got['text1'], got)         # 押していない離しでは決めない
        self.assertTrue(got['stray_release_open'], got)
        self.assertFalse(got['after_esc'], got)                               # Esc で止まる
        self.assertTrue(got['chain_passive']['open'], got)
        self.assertEqual(got['chain_passive']['passive'], 'line_end', got)    # 自動の形は自動の形で
        self.assertEqual(got['chain_passive']['sel'], [], got)                # 自動の形は選ばない（Enter は改行）
        self.assertTrue(got['chain_passive_where'], got)
        self.assertFalse(got['moved_before'], got)                            # 別のキーで動いたら出さない
        self.assertFalse(got['no_candidates'], got)                           # 予測が無ければ出さない
        # 2026-11-22 01:56Z うにさん「右に文字があるときは出さない」（CN_PREDICT_CHAIN_RIGHT_EMPTY）: 行頭の予測を入れた後でも、
        # 右に字が残っていれば続けて出さない（前は出していた）
        self.assertFalse(got['chain_head']['open'], got)
        self.assertFalse(got['scroll_hold'], got)                             # スクロールの後は出さない
        self.assertFalse(got['on_screen'], got)                               # 試しの窓は画面に出ない

    def test_right_text_old_form(self):
        got = run_child(self, {'CN_PREDICT_CHAIN_RIGHT_EMPTY': '0'})
        self.assertTrue(got['chain_head']['open'], got)                       # 前の形: 右に字があっても出す
        self.assertEqual(got['chain_head_asked'], '・', got)

    def test_switch_back(self):
        got = run_child(self, {'CN_PREDICT_CHAIN': '0'})
        self.assertFalse(got['chain_f5']['open'], got)
        self.assertFalse(got['chain_head']['open'], got)

    def test_old_focus_and_wrap(self):
        got = run_child(self, {'CN_PREDICT_CHAIN_NO_FOCUS': '0', 'CN_F5_WRAP_TO_CUSTOM': '0'})
        self.assertEqual(got['chain_f5']['sel'], [0], got)                    # 前の形: F5 の形は1つ目を選ぶ
        self.assertEqual(got['wrap_up_to'], [got['wrap_items'] - 1], got)     # 前の形: 一覧の一番下へ


if __name__ == '__main__':
    unittest.main()
