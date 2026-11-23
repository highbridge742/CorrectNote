# -*- coding: utf-8 -*-
"""F5 の予測の枠組み（2026-11-20 うにさん「F5の再変換を、カーソルの右側に文字がない時に実行すると…次に続く文字の候補を
出す。この状態から再度F5を押したり、左キーを押せば左の単語がフォーカスされ、これまでと同じ挙動をする…一度範囲を動かし
たら、予告の候補には切り替わらない。一度再変換を閉じてまたひらけば予測は出る」）。候補の中身はまだ無いので、試験は
作り物の候補の口（f5_predict.set_provider）で確かめる。アプリを試しの写し（プログラムと同梱の物だけ・作った例文）で子
として起こし、F5 の手続きを直に呼ぶ。CN_F5_PREDICT=0 で前の形。"""
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
from unittest import mock

# 行頭（全角あり）の既定は 16:44Z の指定の並び（画像）。前の形は手間の順（CN_F5_HEAD_ORDER=0）
# 2026-11-21 01:55Z から ・ ※ ◆ ■ > ＞ ○ ● ▼ と罫線3つ（画像）。前の並びは CN_F5_HEAD_DEFAULT2=0
HEAD = ['・', '※', '◆', '■', '>', '＞', '○', '●', '▼', chr(0x3000) + '└', chr(0x3000) * 2 + '└', chr(0x3000) + '├']
HEAD_1120 = ['・', '※', '◆', '■', '●', '▼', chr(0x3000) + '└', chr(0x3000) * 2 + '└', chr(0x3000) + '├']


_IME_PATCH = None


def setUpModule():
    # うに 11-21 16:52Z 仕様変更: 全角・半角の一覧は IME の形で選ぶ（CN_PREDICT_CUSTOM_BY_IME）。ここの試験はタブの字で
    # 選ぶ形（IME の形が分からない時の選び方）を見るので、IME の形は「分からない」にする。試験の机の IME の形に左右されない。
    # IME の形で選ぶのは tests_predict_custom_by_ime_20261122 で見る
    global _IME_PATCH
    import ime_watch
    _IME_PATCH = mock.patch.object(ime_watch, 'wide_input', lambda hwnd: None)
    _IME_PATCH.start()


def tearDownModule():
    if _IME_PATCH is not None:
        _IME_PATCH.stop()


def no_clip_nouns(test):
    # この組の試験は、行頭の候補の下に足すクリップボードと周りの名詞（01:55Z）を外して見る（ClipNouns で見る）
    p = mock.patch.dict(os.environ, {'CN_F5_CLIP_NOUNS': '0'})
    p.start()
    test.addCleanup(p.stop)


def child():
    import tkinter as tk
    from types import SimpleNamespace as NS
    from unittest.mock import Mock, patch
    import app
    import f5_predict
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-f5-predict-test-isolated').is_file()
    line = '今日は本を読みました'
    (here / 'settings.json').write_text(json.dumps(dict(layout='split', input_method='kana', input_method_auto=False)),
                                        encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=line + '\n二行目です')]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(s):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
    out = {}
    asked = []
    if os.environ.get('F5_TEST_PROVIDER') == 'empty':
        f5_predict.set_provider(lambda a, w, row, col, before: [])           # 候補が無い時: 見た目は今までどおり
    else:
        f5_predict.set_provider(lambda a, w, row, col, before: asked.append(before) or ['予測A', '予測B'])
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        import offscreen_window; offscreen_window.hold(root)      # 作る間も見えない所に（どの画面の置き方でも）
        a = app.CorrectNoteApp(root)
        offscreen_window.hold(root, '900x600')     # 画面の外（うにさんの画面を占めない）
        end = time.monotonic() + 60
        while time.monotonic() < end and (a._foreground_analysis_pending() or len(a.line_units) < 1 or not a.line_units[0]):
            pump(0.1)
        ed = a.editor
        ed.focus_force(); pump(0.1)

        def f5():
            a._on_f2_candidates(NS(widget=ed, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0))
            # 解析の子が行を解いている間の F5 は、子の答えが届いてから開く（f5_async・2026-11-23）。人が押して一覧を
            # 待つのと同じく、開くまで待つ（決まった時間ではなく）
            end = time.monotonic() + 8
            while time.monotonic() < end and getattr(a, '_f5_wait', None) is not None:
                pump(0.02)
            pump(0.2)

        def target():
            cyc = getattr(a, '_f2_cycle', None)
            if not cyc or cyc.get('idx') is None:
                return None
            return [cyc['row'], cyc['units'][cyc['idx']].get('text')]

        ed.mark_set('insert', '1.end')
        f5()
        out['open'] = dict(predict=a._f5_predict is not None, dropdown=a._dropdown is not None, target=target(),
                           asked=list(asked))
        f5()                                                                    # 予測から F5 → 左の語
        out['f5_again'] = dict(predict=a._f5_predict is not None, target=target())
        first_word = target()
        f5()                                                                    # さらに遡る
        out['f5_third'] = dict(predict=a._f5_predict is not None, target=target())
        for _ in range(4):                                                      # 右へ戻しても予測には戻らない
            a._on_dropdown_horizontal(1); pump(0.1)
        out['right_back'] = dict(predict=a._f5_predict is not None)
        a._close_dropdown(); pump(0.1)
        ed.mark_set('insert', '1.end')
        f5()                                                                    # 閉じて開き直すと、また予測
        out['reopen'] = dict(predict=a._f5_predict is not None)
        a._on_dropdown_horizontal(-1); pump(0.2)                                # 予測から左キー → 左の語
        out['left'] = dict(predict=a._f5_predict is not None, target=target(), same_as_f5=target() == first_word)
        a._close_dropdown(); pump(0.1)
        ed.mark_set('insert', '1.end')
        f5()
        a._f5_predict_insert(ed, 'main', '予測A'); pump(0.1)                    # 選ぶとカーソルの位置へ入る
        out['inserted'] = ed.get('1.0', '1.end')
        ed.edit_undo(); pump(0.1)
        out['undone'] = ed.get('1.0', '1.end')
        a._close_dropdown(); pump(0.1)
        ed.mark_set('insert', '1.2')                                            # 右に字がある: 今までどおり
        f5()
        out['middle'] = dict(predict=a._f5_predict is not None)
        a._close_dropdown(); pump(0.1)
        # 行頭: 右に字があっても行頭の候補で開く。そこから F5 → 前の行の末の語（今までの行頭の動き）
        ed.mark_set('insert', '2.0')
        f5()
        out['line_start'] = dict(predict=a._f5_predict is not None)
        f5()
        out['line_start_then'] = dict(predict=a._f5_predict is not None, target=target())
        a._close_dropdown(); pump(0.1)
        # 簡易入力
        try:
            a._show_quick_capture(); pump(0.5)
            q = a._quick_text
            q.insert('1.0', 'テスト')
            q.mark_set('insert', '1.end')
            q.focus_force(); pump(0.1)
            # 解析の答えが揃った形にする（字を入れると解析の予約が立つので、F5 の直前に）
            if getattr(a, '_quick_after_id', None):
                a.root.after_cancel(a._quick_after_id)
            a._quick_units_text = q.get('1.0', 'end-1c'); a._quick_units = [[]]
            a._quick_after_id = None
            a._on_quick_f2(NS(widget=q, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0)); pump(0.2)
            out['quick_open'] = dict(predict=a._f5_predict is not None, owner=a._dropdown_owner)
            a._on_quick_f2(NS(widget=q, keysym=a.CANDIDATE_KEY, char='', state=0, keycode=0)); pump(0.2)
            out['quick_again'] = dict(predict=a._f5_predict is not None)
            a._close_dropdown()
            a._close_quick_capture(); pump(0.2)
        except Exception as e:
            out['quick_error'] = repr(e)
        assert not errors, errors
        print('F5_PREDICT', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


def run_child(test, env=None):
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-f5-predict-') as directory:
        dest = Path(directory).resolve()
        for entry in source.iterdir():
            if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                shutil.copy2(entry, dest / entry.name)
        (dest / '.ui-f5-predict-test-isolated').touch()
        environ = dict(os.environ)
        environ.update(env or {})
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                             cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ,
                             encoding='utf-8', errors='replace', timeout=240)
        test.assertEqual(run.returncode, 0, run.stdout[-3000:])
        line = [l for l in run.stdout.splitlines() if l.startswith('F5_PREDICT ')]
        test.assertTrue(line, run.stdout[-3000:])
        return json.loads(line[0][len('F5_PREDICT '):])


def fake_ime(query):
    """f5_predict._open_query の代わり（作り物の IME の問い合わせ）。"""
    import contextlib
    return lambda: contextlib.nullcontext(query)


class Cases(unittest.TestCase):
    """候補の中身（f5_predict.predict・2026-11-20 13:55Z・13:57Z うにさんの仕様）。自分の Text の窓だけ・作った例文。"""
    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.w = tk.Text(self.root)
        import f5_predict
        f5_predict.set_provider(None)
        self.F = f5_predict
        no_clip_nouns(self)

    def tearDown(self):
        self.root.destroy()

    def at_end(self, text):
        self.w.delete('1.0', 'end')
        self.w.insert('1.0', text)
        self.w.mark_set('insert', 'end-1c')
        before = self.w.get('insert linestart', 'insert')
        return self.F.candidates(None, self.w, 1, len(before), before)

    def test_sentence_end_wide_default_order(self):
        # 2026-11-20 15:30Z うにさんの指定で、文末（全角あり）の既定は ！ ？ !? … 、 。（!? は半角）の順のまま
        # （前は手間の多い順の ！？ … ！ ？ 、 。）。CN_F5_END_ORDER=0 で前の形
        # 2026-11-21 14:26Z うにさん「文末のデフォルトを、画像の並びにする」: ？ ！ … ～ !? 、 。 → ⇒ ␣⇒␣ に変えた
        # （CN_F5_TAIL_DEFAULT2）。前の ！ ？ !? … 、 。 は CN_F5_TAIL_DEFAULT2=0 で確かめる
        got = self.at_end('今日は本を読みました')
        self.assertEqual(got, ['？', '！', '…', '～', '!?', '、', '。', '→', '⇒', ' ⇒ '])
        import os as _os
        from unittest import mock as _mock
        with _mock.patch.dict(_os.environ, {'CN_F5_TAIL_DEFAULT2': '0'}):
            self.assertEqual(self.at_end('今日は本を読みました'), ['！', '？', '!?', '…', '、', '。'])
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {'CN_F5_END_ORDER': '0'}):
            self.assertEqual(self.at_end('今日は本を読みました'), ['！？', '…', '！', '？', '、', '。'])

    def test_unclosed_brackets_come_first(self):
        got = self.at_end('彼は「そうです')
        self.assertEqual(got[0], '」')
        got = self.at_end('彼は「本当に『そうです')
        self.assertEqual(got[:2], ['』', '」'])                               # 内側から

    def test_sentence_end_narrow(self):
        # 2026-11-21 14:30Z うにさん「半角はこう。ピリオドの下はカンマ」: ? ! !? ... . , & // に変えた（CN_F5_TAIL_DEFAULT2）
        self.assertEqual(self.at_end('I read the book'), ['?', '!', '!?', '...', '.', ',', '&', '//'])
        with mock.patch.dict(os.environ, {'CN_F5_TAIL_DEFAULT2': '0'}):
            self.assertEqual(self.at_end('I read the book'), ['!?', '...', '!', '?', '.'])   # 前の既定（「,」は無い）
        self.assertEqual(self.at_end('He said (yes')[0], ')')

    def test_line_head(self):
        self.assertEqual(self.at_end('一行目\n'), HEAD)
        self.assertEqual(self.at_end('■見出し\n本文\n'), HEAD)                # 使っている字でも並べ替えない
        with mock.patch.dict(os.environ, {'CN_F5_HEAD_ORDER': '0'}):
            self.assertEqual(self.at_end('一行目\n'), ['◆', '■', '●', '▼', '※', '【', '・'])
            self.assertEqual(self.at_end('■見出し\n本文\n')[0], '■')
        self.assertEqual(self.at_end('line one\n'), ['#', '*', '>', '+', '-'])
        with mock.patch.dict(os.environ, {'CN_F5_HEAD_ORDER': '0'}):
            got = self.at_end('■見出し\n本文\n')                             # 前の形: 同じ手間なら、使っている字を先に
            self.assertEqual(got[0], '■')

    def test_conjunctions_from_the_previous_sentence(self):
        # 2026-11-23 うにさん「接続詞の候補は無しにする」から、既定では出さない（tests_predict_no_conj_20261123）。
        # 前の形（CN_PREDICT_NO_CONJUNCTIONS=0）の接続詞の並べ方は、ここで今までどおり見る
        p = mock.patch.dict(os.environ, {'CN_PREDICT_NO_CONJUNCTIONS': '0'})
        p.start()
        self.addCleanup(p.stop)
        got = self.at_end('雨が降ったので、試合は中止になりました。')
        self.assertEqual(got[0], 'だから')
        self.assertLessEqual(len(got), 7)
        got = self.at_end('準備はできていない\nと思います。')                  # 前の文が前の行にまたがる
        self.assertEqual(got[0], 'しかし')
        self.assertIn('そして', self.at_end('本を読み、'))

    def test_next_chars_and_phrases(self):
        from unittest import mock
        with mock.patch.object(self.F, '_open_query', fake_ime(lambda r: None)):     # IME が取れない時の表の句
            got = self.at_end('補正の')
        self.assertTrue(1 <= len(got) <= 7, got)
        self.assertEqual(len({g[0] for g in got}), len(got))                   # それぞれ違う字で始まる
        firsts = self.F.next_chars('補正の')
        self.assertEqual([g[0] for g in got], firsts)

    # 2026-11-21 うにさん「自動で並べ替えはしないので、ボタンと判定は不要です」: 既定の並びのまま（手間で並べ替えない・
    # 使っている字を先にもしない）。CN_F5_FIXED_ORDER=0 で前の形
    def test_fixed_order_without_effort_sorting(self):
        self.assertEqual(self.at_end('line one' + chr(10)), ['#', '*', '>', '+', '-'])
        self.assertEqual(self.at_end('*item' + chr(10) + 'text' + chr(10)), ['#', '*', '>', '+', '-'])   # 使っている字を先にしない
        with mock.patch.dict(os.environ, {'CN_F5_FIXED_ORDER': '0'}):
            self.assertEqual(self.at_end('*item' + chr(10) + 'text' + chr(10))[0], '*')               # 前の形
        self.assertEqual(self.F.default_list('end_narrow'), ['?', '!', '!?', '...', '.', ',', '&', '//'])   # 14:30Z の既定
        with mock.patch.dict(os.environ, {'CN_F5_TAIL_DEFAULT2': '0'}):
            self.assertEqual(self.F.default_list('end_narrow'), ['!?', '...', '!', '?', '.'])          # 前の既定

    def test_effort_table_text(self):
        text = self.F.effort_text()
        # 決めた順のまま（手間で並べ替えない）。文末（全角）の既定は 14:26Z に変えた（CN_F5_TAIL_DEFAULT2）
        self.assertIn('文末（全角）: ' + '  '.join('%s=%d' % (c, self.F.EFFORT.get(c, 2))
                                                  for c in self.F.default_list('end_wide')), text)
        with mock.patch.dict(os.environ, {'CN_F5_TAIL_DEFAULT2': '0'}):
            self.assertIn('文末（全角）: ！=2  ？=2  !?=4  …=4  、=1  。=1', self.F.effort_text())     # 前の既定
        self.assertIn('。=1', text)


class ImeAndCustom(unittest.TestCase):
    """IME の予測（TSF の検索候補・問い合わせだけ）と、行頭・文末の候補のカスタム（2026-11-20 14:21Z うにさん）。"""
    def setUp(self):
        import tkinter as tk
        import f5_predict
        f5_predict.set_provider(None)
        self.F = f5_predict
        self.root = tk.Tk()
        self.root.withdraw()
        self.w = tk.Text(self.root)
        no_clip_nouns(self)

    def tearDown(self):
        self.root.destroy()

    def test_ime_predictions_with_a_made_up_ime(self):
        asked = []

        def query(reading):
            asked.append(reading)
            return {'ほん': ['本文', '本当に', '翻訳', '本'], 'の': ['ノート', 'のです']}.get(reading, [])
        got = self.F.ime_predictions('今日は本', query=query)
        self.assertEqual(asked[0], 'ほん')                                   # (a) 直前の語の読み
        self.assertEqual(got[:2], ['文', '当に'])                            # その語で始まる候補の続き（翻訳・本は入れない）
        self.assertTrue(len(asked) >= 2)                                     # (b) 次に多い字の読みも問い合わせる
        self.assertIsNone(self.F.ime_predictions('今日は本', query=lambda r: None))     # 取れない
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {'CN_F5_IME': '0'}):
            self.assertIsNone(self.F.ime_predictions('今日は本', query=query))

    def test_real_ime_query_does_not_commit(self):
        # 本物の IME（TSF の検索候補）に問い合わせるだけ。欄・キー・確定は使わない
        from ime_candidates import SearchCandidates
        with SearchCandidates() as search:
            available = search.available
        got = self.F.ime_predictions('今日は本')
        if available:
            self.assertTrue(got, got)
            self.assertTrue(all(isinstance(x, str) and x for x in got))
        else:
            self.assertIsNone(got)

    def test_predict_uses_ime_then_falls_back_to_the_table(self):
        from unittest import mock
        self.w.insert('1.0', '補正の')
        self.w.mark_set('insert', 'end-1c')
        with mock.patch.object(self.F, '_open_query', fake_ime(lambda r: ['のです', 'のでしょうか'] if r == 'の' else [])):
            self.assertEqual(self.F.candidates(None, self.w, 1, 3, '補正の')[:2], ['です', 'でしょうか'])
        with mock.patch.object(self.F, '_open_query', fake_ime(lambda r: None)):           # IME が取れない: 表の句
            got = self.F.candidates(None, self.w, 1, 3, '補正の')
            self.assertEqual([g[0] for g in got], self.F.next_chars('補正の'))

    def test_line_start_with_text_on_the_right(self):
        self.w.insert('1.0', '一行目' + chr(10) + '二行目')
        self.w.mark_set('insert', '2.0')
        self.assertTrue(self.F.opens_here(self.w))
        self.assertEqual(self.F.candidates(None, self.w, 2, 0, ''), HEAD)
        self.w.mark_set('insert', '2.1')
        self.assertFalse(self.F.opens_here(self.w))

    def test_custom_lists_win(self):
        from types import SimpleNamespace as NS
        lists = {'head_wide': ['★', '◆'], 'end_wide': ['。', '！']}
        app = NS(settings=NS(get=lambda k: lists if k == 'f5_predict_lists' else None))
        self.w.insert('1.0', '一行目' + chr(10))
        self.w.mark_set('insert', 'end-1c')
        self.assertEqual(self.F.candidates(app, self.w, 2, 0, ''), ['★', '◆'])        # 並べた順のまま
        self.w.delete('1.0', 'end'); self.w.insert('1.0', '彼は「読みました'); self.w.mark_set('insert', 'end-1c')
        self.assertEqual(self.F.candidates(app, self.w, 1, 8, '彼は「読みました'), ['」', '。', '！'])

    def test_editor_window_add_move_delete(self):
        import f5_predict_window as FW
        from types import SimpleNamespace as NS
        store = {}
        saved = []
        app = NS(root=self.root, settings=NS(get=lambda k: store.get(k), set=lambda k, v: store.__setitem__(k, v),
                                             save=lambda: saved.append(1)))
        dlg = FW.open_window(app, 'end')
        f = dlg._f5
        # 一覧は空白を印で見せる（f5_predict_window.marked）。文末の既定に空白つきの「 ⇒ 」が入ったので（14:26Z
        # CN_F5_TAIL_DEFAULT2）、見せる形で比べる。1行目も既定の1つ目（前は ！・今は ？）
        self.assertEqual(list(f['listbox'].get(0, 'end')), [FW.marked(c) for c in self.F.default_list('end_wide')])
        f['listbox'].selection_set(0)
        f['entry'].insert(0, '★')
        f['add']()                                                           # 選んだ行の下へ
        self.assertEqual(store['f5_predict_lists']['end_wide'][:2], [self.F.default_list('end_wide')[0], '★'])
        f['listbox'].selection_clear(0, 'end'); f['listbox'].selection_set(1)
        f['move'](-1)                                                        # 上へ
        self.assertEqual(store['f5_predict_lists']['end_wide'][:2], ['★', self.F.default_list('end_wide')[0]])   # 既定の1つ目（14:26Z から ？）
        f['listbox'].selection_clear(0, 'end'); f['listbox'].selection_set(0)
        f['delete']()
        self.assertNotIn('★', store['f5_predict_lists'].get('end_wide', []))
        f['which'].set('end_narrow'); f['refresh']()                        # 半角だけの組
        self.assertEqual(list(f['listbox'].get(0, 'end')), self.F.default_list('end_narrow'))
        self.assertTrue(saved)
        dlg.destroy()

    # 2026-11-20 15:30Z うにさん「ダークモードに対応し…規定に戻すを削除。選択して候補の字を変更してエンターしたら、変更にする。
    # エスケープキーで閉じる。絵文字が扱えるなら対応する」
    def open_end(self, colors=None):
        import f5_predict_window as FW
        from types import SimpleNamespace as NS
        self.store = {}
        app = NS(root=self.root, settings=NS(get=lambda k: self.store.get(k),
                                             set=lambda k, v: self.store.__setitem__(k, v), save=lambda: None))
        return FW.open_window(app, 'end', colors)

    def test_window_dark_colors_and_no_reset_button(self):
        dark = dict(bg='#1e2124', ink='#e6e4dd', panel='#25292d', muted='#8a8577', sel='#3a4a55')
        dlg = self.open_end(dark)
        f = dlg._f5
        self.assertEqual(str(f['listbox'].cget('bg')), '#25292d')
        self.assertEqual(str(f['listbox'].cget('fg')), '#e6e4dd')
        self.assertEqual(str(f['entry'].cget('bg')), '#25292d')
        texts = []

        def walk(w):
            for c in w.winfo_children():
                if c.winfo_class() == 'Button':
                    texts.append(c.cget('text'))
                    self.assertEqual(str(c.cget('bg')), '#25292d')
                walk(c)
        walk(dlg)
        self.assertNotIn('既定に戻す', texts)
        self.assertIn('変更', texts)
        dlg.destroy()

    def test_enter_changes_the_selected_row_and_escape_closes(self):
        dlg = self.open_end()
        f = dlg._f5
        f['listbox'].selection_set(2)                                          # 3つ目
        f['entry'].delete(0, 'end'); f['entry'].insert(0, '‼')
        f['enter']()
        self.assertEqual(self.store['f5_predict_lists']['end_wide'][2], '‼')    # 変更（足していない）
        # 既定の数（前は6・14:26Z の既定で10）と同じ＝足していない
        self.assertEqual(len(self.store['f5_predict_lists']['end_wide']), len(self.F.default_list('end_wide')))
        f['listbox'].selection_clear(0, 'end')
        f['entry'].delete(0, 'end'); f['entry'].insert(0, '？！')
        f['enter']()                                                         # 選んでいなければ追加
        self.assertIn('？！', self.store['f5_predict_lists']['end_wide'])
        f['entry'].focus_force()
        self.root.update()
        f['entry'].event_generate('<Escape>')
        self.root.update()
        self.assertFalse(int(dlg.winfo_exists()))

    def test_emoji_candidates_are_kept_and_inserted(self):
        emoji = ['😀', '👍🏽', '👨' + chr(0x200d) + '👩' + chr(0x200d) + '👧', '❤' + chr(0xfe0f)]
        dlg = self.open_end()
        f = dlg._f5
        for e in emoji:
            f['listbox'].selection_clear(0, 'end')
            f['entry'].delete(0, 'end'); f['entry'].insert(0, e)
            f['enter']()
        kept = self.store['f5_predict_lists']['end_wide']
        for e in emoji:
            self.assertIn(e, kept)                                              # 色付き・組み合わせ・異体字セレクタのまま
        self.assertEqual([x for x in f['listbox'].get(0, 'end') if x in emoji], emoji)
        dlg.destroy()
        import json
        self.assertEqual(json.loads(json.dumps(kept, ensure_ascii=False)), kept)     # 設定の保存の形でも同じ
        from text_edit import undo_group
        self.w.configure(undo=True)
        self.w.insert('1.0', '本文')
        with undo_group(self.w):
            self.w.insert('end-1c', emoji[2])
        self.assertEqual(self.w.get('1.0', 'end-1c'), '本文' + emoji[2])          # 本文へ正しく入る
        self.w.edit_undo()
        self.assertEqual(self.w.get('1.0', 'end-1c'), '本文')


class WindowSpaces(unittest.TestCase):
    """候補の窓: 追加した字を欄に残す・空にして変更で削除・スペースだけ／タブだけの候補・前後の空白を削らない・Tab でタブの字・
    一覧ではスペースとタブを印で見せる（2026-11-20 15:42Z うにさん）。CN_F5_WINDOW_SPACES=0 で前の形。"""
    def setUp(self):
        import tkinter as tk
        import f5_predict_window as FW
        from types import SimpleNamespace as NS
        self.FW = FW
        self.root = tk.Tk()
        self.root.withdraw()
        self.store = {}
        self.app = NS(root=self.root, settings=NS(get=lambda k: self.store.get(k),
                                                  set=lambda k, v: self.store.__setitem__(k, v), save=lambda: None))
        no_clip_nouns(self)

    def tearDown(self):
        self.root.destroy()

    def type_and_enter(self, f, text, select=None):
        f['listbox'].selection_clear(0, 'end')
        if select is not None:
            f['listbox'].selection_set(select)
        f['entry'].delete(0, 'end')
        f['entry'].insert(0, text)
        f['enter']()

    def test_spaces_tabs_and_markers(self):
        dlg = self.FW.open_window(self.app, 'head')
        f = dlg._f5
        self.type_and_enter(f, ' ')
        self.assertEqual(f['entry'].get(), ' ')                              # 足した字を欄に残す
        self.type_and_enter(f, chr(0x3000))
        self.type_and_enter(f, 'a  ')                                         # 末尾のスペースも残す
        f['listbox'].selection_clear(0, 'end')
        f['entry'].delete(0, 'end')
        f['entry'].focus_force(); self.root.update()
        self.assertEqual(f['tab'](), 'break')                                 # Tab はタブの字（焦点を移さない）
        self.assertEqual(f['entry'].get(), '\t')
        f['enter']()
        kept = self.store['f5_predict_lists']['head_wide']
        for c in (' ', chr(0x3000), 'a  ', '\t'):
            self.assertIn(c, kept)
        shown = list(f['listbox'].get(0, 'end'))
        # 印は 16:10Z の指定（全角空白 ␣・半角空白 ˽・タブ [Tab]。前は ␣ □ →）。16:44Z から印は後ろに字の無い空白だけ
        self.assertIn('˽', shown)
        self.assertIn('␣', shown)
        self.assertIn('a˽˽', shown)
        self.assertIn('[Tab]', shown)
        self.assertIn(chr(0x3000) + '└', shown)                               # 後ろに字がある空白は印にしない
        n = len(kept)
        f['listbox'].selection_clear(0, 'end')
        f['entry'].delete(0, 'end')
        f['enter']()                                                         # 空は足さない
        self.assertEqual(len(self.store['f5_predict_lists']['head_wide']), n)
        at = kept.index(' ')
        self.type_and_enter(f, '', select=at)                                # 選んで欄を空にして Enter → 削除
        self.assertNotIn(' ', self.store['f5_predict_lists']['head_wide'])
        at = self.store['f5_predict_lists']['head_wide'].index('a  ')
        f['listbox'].selection_clear(0, 'end'); f['listbox'].selection_set(at)
        f['entry'].delete(0, 'end')
        f['change']()                                                        # 変更のボタンでも削除
        self.assertNotIn('a  ', self.store['f5_predict_lists']['head_wide'])
        dlg.destroy()
        # 予測の候補にも本物の字のまま渡る（窓の印は表示だけ）
        import f5_predict as F
        F.set_provider(None)
        import tkinter as tk
        w = tk.Text(self.root)
        w.insert('1.0', '一行目' + chr(10))
        w.mark_set('insert', 'end-1c')
        got = F.candidates(self.app, w, 2, 0, '')
        self.assertIn('\t', got)
        self.assertIn(chr(0x3000), got)
        self.assertEqual(self.FW.marked(' ' + '\t' + chr(0x3000)), '˽[Tab]␣')

    def test_marks_only_where_nothing_follows(self):
        # 16:44Z うにさん「後ろに文字があるときは各記号を出さずただの空白表現にする。後ろに文字がないところだけ、␣などを書く」
        W = chr(0x3000)
        self.assertEqual(self.FW.marked(W + '└'), W + '└')
        self.assertEqual(self.FW.marked(W + W + '└'), W + W + '└')
        E = chr(0x2002)                                                            # 後ろに字がある半角は全角の半分の幅（EN SPACE）
        self.assertEqual(self.FW.marked(' a b '), E + 'a' + E + 'b˽')
        self.assertEqual(self.FW.marked('\tx'), W + E + 'x')                         # タブは全角の1.5個分
        self.assertEqual(self.FW.marked('a' + W + ' \t'), 'a␣˽[Tab]')
        self.assertEqual(self.FW.marked(W), '␣')
        self.assertEqual(self.FW.marked(''), '')
        with mock.patch.dict(os.environ, {'CN_F5_MARK_TRAILING_ONLY': '0'}):
            self.assertEqual(self.FW.marked(W + '└'), '␣└')                       # 前の形
        with mock.patch.dict(os.environ, {'CN_F5_PLAIN_WIDTH': '0'}):
            self.assertEqual(self.FW.marked('\tx a'), '    x a')                       # 前の形（タブ＝半角4つ）

    def test_plain_space_widths(self):
        # 2026-11-21 うにさん: 全角空白を1として タブ 1.5・半角 0.5 の幅（候補の窓・編集の窓の字 Yu Gothic UI）
        import tkinter as tk
        from tkinter import font as tkfont
        root = tk.Tk(); root.withdraw()
        try:
            for size in (10, 12):
                f = tkfont.Font(root=root, family='Yu Gothic UI', size=size)
                w = lambda s: f.measure('x' + s + 'x') - f.measure('xx')
                full = w(chr(0x3000))
                self.assertAlmostEqual(w(self.FW.marked(chr(9) + 'x')[:-1]), full * 1.5, delta=1)
                self.assertAlmostEqual(w(self.FW.marked(' x')[:-1]), full * 0.5, delta=1)
        finally:
            root.destroy()

    def test_switch_back_strips_and_clears(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {'CN_F5_WINDOW_SPACES': '0'}):
            dlg = self.FW.open_window(self.app, 'head')
            f = dlg._f5
            self.type_and_enter(f, ' x ')
            self.assertIn('x', self.store['f5_predict_lists']['head_wide'])
            self.assertEqual(f['entry'].get(), '')
            dlg.destroy()


class ClipNouns(unittest.TestCase):
    """2026-11-21 01:55Z うにさん: 行頭の候補を入れた後はクリップボード → 周りの名詞。行頭の候補にもカスタムの下に。
    クリップボードは読むだけ（作り物の口で渡す・本物のクリップボードは触らない）。カスタムの窓の「戻す」。"""
    def setUp(self):
        import tkinter as tk
        import f5_predict
        from types import SimpleNamespace as NS
        f5_predict.set_provider(None)
        self.F = f5_predict
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        self.clip = {'text': 'コピーした字'}

        def clipboard_get():
            if self.clip['text'] is None:
                raise tk.TclError('CLIPBOARD selection does not exist')
            return self.clip['text']
        self.store = {}
        self.app = NS(root=NS(clipboard_get=clipboard_get), settings=NS(get=lambda k: self.store.get(k)))

    def put(self, text, row):
        self.w.insert('1.0', text)
        self.w.mark_set('insert', '%d.end' % row)

    def test_after_a_head_mark(self):
        self.put('会議の資料を作る。' + chr(10) + '会議は明日。資料も送る。' + chr(10) + '会議室' + chr(10) + '・', 4)
        got = self.F.candidates(self.app, self.w, 4, 1, '・')
        self.assertEqual(got[0], 'コピーした字')                                   # クリップボードが先
        self.assertEqual(got[1], '会議')                                           # 周りで数の多い名詞
        self.assertIn('資料', got[1:])
        self.clip['text'] = None                                                    # 文字列でない・空
        self.assertEqual(self.F.candidates(self.app, self.w, 4, 1, '・')[0], '会議')
        got = self.F.candidates(self.app, self.w, 4, 2, chr(0x3000) + '└')          # 罫線の候補の後も
        self.assertEqual(got[0], '会議')

    def test_head_list_has_clip_and_nouns_below_the_custom(self):
        self.put('会議の資料を作る。' + chr(10) + '会議は明日。' + chr(10), 3)
        got = self.F.candidates(self.app, self.w, 3, 0, '')
        self.assertEqual(got[:len(HEAD)], HEAD)
        self.assertEqual(got[len(HEAD)], 'コピーした字')
        self.assertIn('会議', got[len(HEAD):])
        self.store['f5_predict_lists'] = {'head_wide': ['★']}
        got = self.F.candidates(self.app, self.w, 3, 0, '')
        self.assertEqual(got[:2], ['★', 'コピーした字'])                           # カスタムの下

    def test_clipboard_shape(self):
        self.clip['text'] = '一行目の字' + chr(10) + '二行目'
        self.assertEqual(self.F.clipboard_text(self.app), '一行目の字')             # 入れるのは最初の行（改行なし）
        long = 'あ' * 40
        self.clip['text'] = long
        self.assertEqual(self.F.clipboard_text(self.app), long)
        self.assertEqual(self.F.label(long), 'あ' * self.F.CLIP_SHOW + '…')        # 一覧では頭だけ
        self.clip['text'] = 'い' * (self.F.CLIP_MAX + 1)
        self.assertIsNone(self.F.clipboard_text(self.app))                          # 長すぎる行は出さない

    def test_switches(self):
        self.put('会議の資料。' + chr(10) + '・', 2)
        with mock.patch.dict(os.environ, {'CN_F5_CLIP_NOUNS': '0'}):
            self.assertNotIn('コピーした字', self.F.candidates(self.app, self.w, 2, 1, '・'))
            self.assertEqual(self.F.candidates(self.app, self.w, 2, 0, ''), HEAD)
        with mock.patch.dict(os.environ, {'CN_F5_CLIP_NOUNS': '0', 'CN_F5_HEAD_DEFAULT2': '0'}):
            self.assertEqual(self.F.candidates(self.app, self.w, 2, 0, ''), HEAD_1120)

    def test_window_undo(self):
        import f5_predict_window as FW
        from types import SimpleNamespace as NS
        store = {}
        app = NS(root=self.root, settings=NS(get=lambda k: store.get(k), set=lambda k, v: store.__setitem__(k, v),
                                             save=lambda: None))
        dlg = FW.open_window(app, 'head')
        f = dlg._f5
        f['entry'].delete(0, 'end'); f['entry'].insert(0, '★'); f['add']()
        self.assertIn('★', store['f5_predict_lists']['head_wide'])
        f['listbox'].selection_clear(0, 'end'); f['listbox'].selection_set(0); f['move'](1)
        f['undo']()                                                                   # 下へ を戻す
        self.assertEqual(store['f5_predict_lists']['head_wide'].index('・'), 0)
        f['undo']()                                                                   # 追加 を戻す
        self.assertNotIn('★', store.get('f5_predict_lists', {}).get('head_wide', HEAD))
        self.assertEqual(f['undo'](), 'break')                                        # 積みが空でも落ちない
        dlg.destroy()


class F5Predict(unittest.TestCase):
    def test_predict_state_and_back_to_the_left_word(self):
        got = run_child(self)
        self.assertEqual(got['open']['predict'], True, got)                       # 右に字が無い: 予測で開く
        self.assertTrue(got['open']['dropdown'], got)
        self.assertIsNone(got['open']['target'], got)                             # 範囲は空（語を選んでいない）
        self.assertEqual(got['open']['asked'], ['今日は本を読みました'], got)       # 候補の口にカーソルより前の字
        self.assertFalse(got['f5_again']['predict'], got)                         # F5 → 左の語（今の動き）
        self.assertIsNotNone(got['f5_again']['target'], got)
        self.assertFalse(got['f5_third']['predict'], got)
        self.assertNotEqual(got['f5_third']['target'], got['f5_again']['target'], got)   # さらに左へ遡る
        self.assertFalse(got['right_back']['predict'], got)                       # 動かしたら予測へは戻らない
        self.assertTrue(got['reopen']['predict'], got)                            # 閉じて開き直すと予測
        self.assertFalse(got['left']['predict'], got)                             # 左キー → 左の語
        self.assertTrue(got['left']['same_as_f5'], got)                           # F5 と同じ語
        self.assertEqual(got['inserted'], '今日は本を読みました予測A', got)
        self.assertEqual(got['undone'], '今日は本を読みました', got)              # Undo 1回で消える
        self.assertFalse(got['middle']['predict'], got)                           # 右に字がある: 今までどおり
        self.assertTrue(got['line_start']['predict'], got)                        # 行頭は右に字があっても予測
        self.assertFalse(got['line_start_then']['predict'], got)
        self.assertEqual(got['line_start_then']['target'][0], 1, got)             # F5 → 前の行の末の語
        self.assertNotIn('quick_error', got, got)
        self.assertEqual(got['quick_open'], dict(predict=True, owner='quick'), got)   # 簡易入力も
        self.assertFalse(got['quick_again']['predict'], got)

    def test_no_candidates_and_switch_keep_the_old_form(self):
        got = run_child(self, {'F5_TEST_PROVIDER': 'empty'})                         # 候補の口が空: 見た目は今までどおり
        self.assertFalse(got['open']['predict'], got)
        self.assertIsNotNone(got['open']['target'], got)
        got = run_child(self, {'CN_F5_PREDICT': '0'})
        self.assertFalse(got['open']['predict'], got)
        self.assertIsNotNone(got['open']['target'], got)                          # 前の形: 1回目の F5 で左の語
        self.assertFalse(got['quick_open']['predict'], got)


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()
