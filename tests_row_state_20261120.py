# -*- coding: utf-8 -*-
"""行の状態を見る道具（row_state）と、カーソルの行の2つの直し（2026-11-20 うにさんの報告「140行が直らず紫も無い。2行下の
同じ文は直る」）。
・(a) カーソルを置いた行・候補の窓を開いた行が解き直し待ちなら、その行を先に解き直す（CN_REDO_CURSOR_ROW=0 で前の形）
・(b) 統合表示でカーソルが出た行に、まだ掛かっていない自動反映を掛ける（CN_AUTOFIX_ON_LEAVE=0 で前の形）
アプリを試しの写し（プログラムと同梱の物だけ・作った例文）で子として起こす。"""
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

import row_state as RS

SAME = 'しゅくだいをわすれたのでせんせいにおこられた。'


class Helpers(unittest.TestCase):
    def test_parse_rows(self):
        self.assertEqual(RS.parse_rows('140, 142、20-21', 200), [140, 142, 20, 21])
        self.assertEqual(RS.parse_rows('0, 999, x', 200), [])

    def test_default_range(self):
        from types import SimpleNamespace as NS
        app = NS(editor=NS(index=lambda i: '30.0'))
        self.assertEqual(RS.default_text(app), '1-50')                             # 07:39Z の既定
        self.assertEqual(RS.default_rows_for(app, 200), list(range(1, 51)))
        self.assertEqual(RS.default_rows_for(app, 20), list(range(1, 21)))          # 行が少なければそこまで
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_DEFAULT_RANGE': '0'}):
            self.assertEqual(RS.default_text(app), '28, 29, 30, 31, 32')           # 前の形（カーソルの行と前後2行）

    def test_invisible_differences(self):
        self.assertEqual(RS.normalize('あ い '), RS.normalize('あ' + chr(0x3000) + 'い'))
        self.assertIn('末尾の空白', RS.differences('あい ', 'あい'))
        self.assertIn('ゼロ幅の字', RS.differences('あ' + chr(0x200b) + 'い', 'あい'))
        self.assertIn('全角空白', RS.differences('あ' + chr(0x3000) + 'い', 'あ い'))
        self.assertIn('全角半角・互換の字', RS.differences('ＡＢ', 'AB'))
        self.assertEqual(RS.differences('同じ', '同じ'), [])


class StateLikeTheGutter(unittest.TestCase):
    # 2026-11-21 06:37Z うにさん「行の縦線が消えているのに、行のデバッグを見ると、解析待ち・解き直し待ち・控えから戻した
    # 答え待ち と出る」: 状態を縦線（app._line_analysis_state）と同じ見方にそろえ、待ちでないものを待ちと書かない
    def fake(self, result, gutter, todo=(), live=True, units=False):
        from types import SimpleNamespace as NS
        line = 'あいう'
        return NS(line_results=[result], _analyze_todo=list(todo), _analyze_pos=0, _analyze_units_only=units,
                  _foreground_analysis_pending=lambda: live, _line_analysis_state=lambda row: gutter,
                  editor_source_text=lambda: line, editor=NS(index=lambda i: '1.0', get=lambda a, b: line),
                  _layout_is_unified=lambda: True, _autofix_declined_rows=lambda: set(), decisions=None,
                  choices=None, _editor_changes=[], _autofix_record_for_row=lambda r: None,
                  _nearby_words_for=lambda i: ()), line

    def test_states(self):
        app, line = self.fake(dict(original='あいう', corrected='あいう', deferred_stages=['context']), 'done')
        st = RS.row_state(app, 1)
        self.assertEqual((st['状態'], st['縦線']), ('答えあり・重い確かめ待ち', 'なし'))
        app, line = self.fake(dict(original='あいう', corrected='あいう', _from_file=True, analysis_status='complete'),
                              'done', todo=[0], units=True)
        st = RS.row_state(app, 1)
        self.assertNotIn('解析待ち', st['状態'])                                     # 縦線が無い行は待ちと書かない
        app, line = self.fake(dict(original='あいう', corrected='あいう', pending=True), 'pending')
        st = RS.row_state(app, 1)
        self.assertEqual((st['状態'], st['縦線']), ('解析待ち', 'あり（解析待ち）'))
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_STATE2': '0'}):
            app, line = self.fake(dict(original='あいう', corrected='あいう', deferred_stages=['context']), 'done')
            self.assertIn('解き直し待ち', RS.row_state(app, 1)['状態'])              # 前の形
            self.assertNotIn('縦線', RS.row_state(app, 1))


class InputClues(unittest.TestCase):
    # 2026-11-21: 140行と142行は同じ字でどちらも済み・一致なのに 142 だけ直る。行ごとに補正へ渡す手がかり（打った読み・
    # 計算・近くの語・上の行の続き）と答えの出どころを、中身を出さずに見る（CN_ROW_STATE_INPUTS=0 で前の形）
    def fake(self, results, lines):
        from types import SimpleNamespace as NS
        return NS(line_results=results, _nearby_words_for=lambda i: (), editor_source_text=lambda: chr(10).join(lines))

    def test_same_text_rows_with_different_readings(self):
        lines = ['前の文、', SAME, 'x', SAME]
        sig_typed = ((), (('しゅくだい', 0, 3),), (), '前の文、')
        sig_plain = ((), (), ())
        results = [None, dict(original=SAME, corrected=SAME, _input_signature=sig_typed),
                   None, dict(original=SAME, corrected='宿題を忘れたので先生に怒られた。', _input_signature=sig_plain,
                              unsure_spans=[(0, 2)])]
        app = self.fake(results, lines)
        a = RS.input_columns(app, 1, lines, results[1], [4])
        self.assertEqual(a['答えの出どころ'], '解析（子）')
        self.assertTrue(a['手がかり'].startswith('読み1・計算0・近くの語0・上の行の続きあり（答えの時）'), a)
        self.assertIn('渡したが補正は使わない', a['手がかり'])                     # batch672 から補正は使わない
        self.assertEqual(a['直し'], 'なし')
        self.assertEqual(a['同じ字の行との違い'], '4: 違う（読み・上の行）')
        b = RS.input_columns(app, 3, lines, results[3], [2])
        self.assertEqual((b['直し'], b['紫']), ('あり', '1'))
        for v in list(a.values()) + list(b.values()):
            self.assertNotIn('しゅくだい', str(v))                       # 中身は出さない
            self.assertNotIn('宿題', str(v))

    # 2026-11-21 05:22Z: 画面に紫があるのに「紫」が 0。紫は odd_spans（異様の印）にもある（前は unsure_spans だけ数えた）
    def test_purple_counts_odd_spans_and_reasons(self):
        line = '値総尺です'
        r = dict(original=line, corrected=line, odd_spans=[(0, 3)], unsure_spans=[(0, 3), (3, 4)],
                 odd_reasons=[(0, 3, '異様だと見たが、直し先を決められなかった')], _input_signature=((), (), ()))
        app = self.fake([r], [line])
        got = RS.input_columns(app, 0, [line], r, [])
        self.assertEqual(got['紫'], '2')                                          # 重ならない2つ（同じ所は1つ）
        self.assertIn('直し先を決められなかった', got['紫の訳'])
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_TEXT': '0'}):
            self.assertEqual(RS.input_columns(app, 0, [line], r, [])['紫の訳'], '0-3')   # 字を出さない形では位置だけ
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_PURPLE': '0'}):
            self.assertEqual(RS.input_columns(app, 0, [line], r, [])['紫'], '2')        # 前の形（unsure_spans だけ）
            self.assertEqual(RS.purple_count(dict(odd_spans=[(0, 3)])), 0)
        self.assertEqual(RS.purple_count(dict(odd_spans=[(0, 3)])), 1)
        with mock.patch.dict(os.environ, {'CN_PREV_LINE_OFF': '0', 'CN_NEARBY_WORDS_OFF': '0'}):
            self.assertEqual(RS.unused_note(), '')

    def test_file_source_and_switch(self):
        import os
        from unittest import mock
        lines = [SAME, SAME]
        results = [dict(original=SAME, corrected=SAME, _from_file=True), dict(original=SAME, corrected=SAME, _input_signature=((), (), ()))]
        app = self.fake(results, lines)
        with mock.patch('analysis_work_app.line_readings', lambda app, i, lines: ()),                 mock.patch('analysis_work_app.line_calculations', lambda app, i, lines: ()):
            a = RS.input_columns(app, 0, lines, results[0], [2])
        self.assertEqual(a['答えの出どころ'], '控え（ファイル）')
        self.assertIn('出どころ', a['同じ字の行との違い'])
        self.assertIn('同じ字の行との違い', RS.columns())
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_INPUTS': '0'}):
            self.assertFalse(set(RS.INPUT_COLUMNS) & set(RS.columns()))
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_INPUTS': '0', 'CN_ROW_STATE_RECORDS': '0', 'CN_ROW_STATE_TEXT': '0',
                                          'CN_ROW_STATE_STATE2': '0'}):
            self.assertEqual(RS.columns(), RS.COLUMNS_OLD)


class StopRecordsTextCompare(unittest.TestCase):
    """2026-11-21: 補正を止めうる記録の種類を全部拾う（140行は再変換メニューの「元に戻す」「使わない」があった）・表に
    メモ欄と補正欄の字（見えない字は印）・「この行を比べて解く」（使い捨ての子で4通り）。どれも作った例文だけ。"""

    def fake(self, line, row=1, **kw):
        from types import SimpleNamespace as NS
        from decisions import DecisionStore
        from last_choice import LastChoiceStore
        d = DecisionStore()
        app = NS(_editor_changes=[], decisions=d, choices=LastChoiceStore(),
                 _autofix_record_for_row=lambda r: None, _autofix_declined_rows=lambda: set())
        for k, v in kw.items():
            setattr(app, k, v)
        return app

    def test_all_kinds_of_records(self):
        line = 'きょうはいい天気です。'
        app = self.fake(line)
        self.assertEqual(RS.stop_records(app, 5, line), ([], []))
        app._editor_changes.append(dict(row=5, start=0, before='今日', after='きょう'))
        app._autofix_record_for_row = lambda r: dict(manual=True) if r == 5 else None
        app._autofix_declined_rows = lambda: {line}
        app.decisions.reject('天気', '転機')
        app.decisions.protect('いい天気')
        rows, words = RS.stop_records(app, 5, line)
        self.assertEqual(rows, ['選び直しの履歴（メニューの元に戻す）', '自動反映を手で戻した控え', '断った印（Ctrl+Z で戻した字）'])
        self.assertEqual(words, ['使わない（直しの拒否）', '守る語'])
        self.assertEqual(RS.stop_records(app, 6, line)[0], ['断った印（Ctrl+Z で戻した字）'])     # 履歴は行ごと
        for kind in rows + words:
            self.assertNotIn('天気', kind)                                                # 字は入れない

    def test_chosen_spelling_memory(self):
        line = '書類を変える。'
        app = self.fake(line)
        app.choices._units['かえる'] = '変える'
        self.assertIn('選んだ表記の記憶', RS.stop_records(app, 1, line)[1])
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_RECORDS': '0'}):
            self.assertNotIn('止める記録', RS.columns())

    def test_visible_marks(self):
        W = chr(0x3000)
        self.assertEqual(RS.visible('あ' + W + 'い' + chr(0x200b) + 'う' + chr(9) + 'え  '), 'あ␣い⟨ゼロ幅⟩う[Tab]え˽˽')
        self.assertEqual(RS.visible('a b'), 'a b')
        self.assertIn('メモ欄の字', RS.columns())
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_TEXT': '0'}):
            self.assertNotIn('メモ欄の字', RS.columns())

    def test_empty_learning_keeps_the_original(self):
        state = dict(entries=[dict(word='x')], revision=3, decisions={'_rejected': {1: 2}, '_protected': {}},
                     choices={'_units': {'a': 'b'}}, choice_revision=4, ime={'k': ['v']})
        out = RS.empty_learning(state)
        self.assertEqual((out['entries'], out['decisions'], out['choices']), ([], {'_rejected': {}, '_protected': {}}, {'_units': {}}))
        self.assertEqual(out['ime'], {'k': ['v']})                        # IME の記録は外さない
        self.assertEqual(state['entries'], [dict(word='x')])                # 元は変えない

    def test_compare_runs_variants_one_at_a_time(self):
        line = 'しゅくだいをわすれた。'
        sent = []

        class FakeWorker:
            def __init__(self):
                self.closed = False
                self.n = 0

            def submit(self, task, state=None):
                self.n += 1
                sent.append((task, state))
                if state is not None:
                    self.state = state
                self.asked = (task, self.state)
                return self.n

            def poll(self, ident):
                task, state = self.asked
                fixed = '宿題を忘れた。' if (task['nearby'] and state['entries']) else line
                return dict(result=dict(corrected=fixed, unsure_spans=[] if fixed != line else [(0, 2)]))

            def close(self):
                self.closed = True

        class Root:
            def __init__(self):
                self.jobs = []

            def after(self, ms, fn):
                self.jobs.append(fn)

        root = Root()
        base = dict(kind='line', line=line, nearby=('語',), recent=('語',), defer_heavy=True, previous_line='上の行、')
        from types import SimpleNamespace as NS
        app = NS(root=root, _prev_lines=[line], line_results=[None])
        got = []
        with mock.patch('analysis_async.line_task', lambda app, i, res, u: dict(base)), \
                mock.patch('analysis_worker.snapshot', lambda app: dict(entries=[1], decisions={}, choices={})):
            job = RS.Compare(app, 1, got.append, worker_factory=FakeWorker)
            job.start()
            for _ in range(20):
                if not root.jobs:
                    break
                root.jobs.pop(0)()
        self.assertTrue(job.closed and job.worker.closed)
        self.assertEqual([r[0] for r in got[0]], ['今のまま', '上の行の続きなし', '上下の行の語なし',
                                                  '上の行の続きも上下の語もなし', '学習・決めた語なし'])
        self.assertEqual(len(sent), 5)
        self.assertEqual([bool(s) for _t, s in sent], [True, False, False, False, True])    # 材料は替わる時だけ送る
        self.assertEqual([t['nearby'] for t, _s in sent], [('語',), ('語',), (), (), ('語',)])
        self.assertEqual([t['previous_line'] for t, _s in sent], ['上の行、', None, '上の行、', None, '上の行、'])
        self.assertTrue(all(t['defer_heavy'] is False for t, _s in sent))
        self.assertEqual(got[0][0][1:3], ('あり', '0'))
        self.assertEqual(got[0][2][1:3], ('なし', '1'))
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_COMPARE_PREV': '0'}):
            self.assertEqual(len(RS.compare_variants()), 4)                           # 前の4通り
        text = RS.compare_text(1, got[0], show_text=False)
        self.assertNotIn('宿題', text)
        with mock.patch.dict(os.environ, {'CN_ROW_STATE_COMPARE': '0'}):
            self.assertFalse(RS.compare_on())


def child(phase):
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    here = Path.cwd().resolve()
    assert (here / '.ui-row-state-test-isolated').is_file()
    rows = ['%d 行目の作り物の文です。' % i for i in range(1, 31)]
    rows[9] = SAME
    rows[11] = SAME
    rows[14] = 'あい '                                # 15行と16行は見えない字だけ違う
    rows[15] = 'あい'
    layout = 'unified' if phase == 'unified' else 'split'
    (here / 'settings.json').write_text(json.dumps(dict(layout=layout, input_method='kana', input_method_auto=False,
                                                        unified_autofix=True)), encoding='utf-8')
    (here / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text='\n'.join(rows))]),
                                                  ensure_ascii=False), encoding='utf-8')
    root = tk.Tk(); errors = []
    root.report_callback_exception = lambda *e: errors.append(''.join(traceback.format_exception(*e)))

    def pump(s, stop=None):
        end = time.monotonic() + s
        while time.monotonic() < end:
            root.update(); time.sleep(0.005)
            if stop is not None and stop():
                return True
        return False
    out = {}
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *a: None), \
            patch.object(app.CorrectNoteApp, '_first_run_setup', lambda *a: None):
        import offscreen_window; offscreen_window.hold(root)      # 作る間も見えない所に（どの画面の置き方でも）
        a = app.CorrectNoteApp(root)
        offscreen_window.hold(root, '1000x600')     # 画面の外（うにさんの画面を占めない）
        ed = a.editor
        if phase == 'unified':
            ed.mark_set('insert', '10.3')               # 解析が終わる前から10行にカーソル
            a._sync_cursor_line(ed, force=True)

        def finished():
            return (not a._foreground_analysis_pending() and a._analyze_pos >= len(a._analyze_todo)
                    and len(a.line_results) >= 30 and all(a.line_results[:30]))
        assert pump(240, finished), 'not finished'
        pump(1.5)
        if phase == 'split':
            ed.mark_set('insert', '10.0'); a._sync_cursor_line(ed, force=True)
            # 2026-11-21 から表にメモ欄・補正欄の字を出す（うにさんの指定・アプリの画面の中だけ）。CN_ROW_STATE_TEXT=0 で前の形
            with patch.dict(os.environ, {'CN_ROW_STATE_TEXT': '0'}):
                text = RS.table(a, [10, 12, 15, 16])
            out['table'] = text
            out['leak'] = any(t in text for t in (SAME, '作り物', 'あい'))
            out['shows_text'] = RS.visible(SAME) in RS.table(a, [10, 12, 15, 16])
            st = RS.row_state(a, 10)
            out['row10'] = st
            out['row15'] = RS.row_state(a, 15)
            # (a) 解き直し待ちの行にカーソルを置く → その行を先に解き直す
            i = 21
            a.line_results[i] = dict(a.line_results[i], deferred_stages=['context'])
            out['before_a'] = RS.row_state(a, i + 1)['状態']
            ed.mark_set('insert', '%d.0' % (i + 1)); a._sync_cursor_line(ed)
            pump(20, lambda: not (a.line_results[i] or {}).get('deferred_stages'))
            out['after_a'] = bool((a.line_results[i] or {}).get('deferred_stages'))
            # 表示準備中などで先に入れられない時: 終わったら一番先に
            j = 25
            a.line_results[j] = dict(a.line_results[j], deferred_stages=['context'])
            with patch.object(a, '_foreground_analysis_pending', lambda: True), \
                    patch.object(a, '_put_heavy_redo_first', lambda rows: False):
                a._redo_row_now(j)
            out['first_rows'] = list(getattr(a, '_redo_first_rows', []))
            k = 27
            a.line_results[k] = dict(a.line_results[k], deferred_stages=['context'])
            a._last_edit_at = 0.0
            with patch.object(a, '_schedule_analysis_chunk', lambda: None):
                a._flush_heavy_redo()
            out['flush_first'] = (a._analyze_todo or [None])[0]
            # 窓の表（コピー付き）
            dlg = RS.open_window(a)
            out['window_has_copy'] = 'copy' in dlg._row_state
            _cur = int(str(ed.index('insert')).split('.')[0])           # 既定の行（1-50）にカーソルの行も入る
            out['window_shows_text'] = RS.visible(ed.get('%d.0' % _cur, '%d.end' % _cur)) in dlg._row_state['text'].get('1.0', 'end')
            out['window_has_compare'] = 'compare' in dlg._row_state
            dlg.destroy()
        else:
            out['row10_text_before'] = ed.get('10.0', '10.end') == SAME            # カーソルの行は後回し
            out['row12_text_before'] = ed.get('12.0', '12.end') == SAME            # ほかの行は自動反映済み
            out['row10_state'] = RS.row_state(a, 10)['統合で後回し']
            ed.mark_set('insert', '20.0'); a._sync_cursor_line(ed)                 # カーソルが10行を出る
            pump(3, lambda: ed.get('10.0', '10.end') != SAME)
            out['row10_text_after'] = ed.get('10.0', '10.end') == SAME
        assert not errors, errors
        print('ROW_STATE', json.dumps(out, ensure_ascii=False), flush=True)
        a._on_close()


def run_child(test, phase, env=None):
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='correctnote-row-state-') as directory:
        dest = Path(directory).resolve()
        for entry in source.iterdir():
            if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                shutil.copy2(entry, dest / entry.name)
        (dest / '.ui-row-state-test-isolated').touch()
        environ = dict(os.environ)
        environ.update(env or {})
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child', phase],
                             cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ,
                             encoding='utf-8', errors='replace', timeout=300)
        test.assertEqual(run.returncode, 0, run.stdout[-3000:])
        line = [l for l in run.stdout.splitlines() if l.startswith('ROW_STATE ')]
        test.assertTrue(line, run.stdout[-3000:])
        return json.loads(line[0][len('ROW_STATE '):])


class InTheApp(unittest.TestCase):
    def test_table_and_redo_the_cursor_row(self):
        got = run_child(self, 'split')
        self.assertFalse(got['leak'], got['table'])                               # CN_ROW_STATE_TEXT=0: 行の字は出さない
        self.assertTrue(got['shows_text'])                                         # 既定: 表にメモ欄の字
        self.assertTrue(got['window_shows_text'])
        self.assertTrue(got['window_has_compare'])
        self.assertTrue(got['window_has_copy'])
        self.assertEqual(got['row10']['答えと字'], '一致', got)
        self.assertEqual(got['row10']['同じ字の行'], '12', got)
        self.assertEqual(got['row10']['カーソルの行'], 'はい', got)
        self.assertEqual(got['row10']['右の欄'], '一致', got)
        self.assertIn('16（末尾の空白）', got['row15']['見えない字だけ違う行'], got)
        # 06:37Z から「答えあり・重い確かめ待ち」（答えは出ていて見せている・縦線は無い）。前は「解き直し待ち」
        self.assertIn('重い確かめ待ち', got['before_a'], got)
        self.assertFalse(got['after_a'], got)                                     # (a) 置いた行を先に解き直した
        self.assertEqual(got['first_rows'][0], 25, got)
        self.assertEqual(got['flush_first'], 25, got)                             # 終わったら一番先に

    def test_unified_cursor_row_gets_the_autofix_when_left(self):
        got = run_child(self, 'unified')
        self.assertTrue(got['row10_text_before'], got)                            # カーソルの行は後回し（今までどおり）
        self.assertFalse(got['row12_text_before'], got)                           # 同じ文の別の行は直る
        self.assertEqual(got['row10_state'], 'はい', got)
        self.assertFalse(got['row10_text_after'], got)                            # (b) 出たら掛かる

    def test_unified_switch_back(self):
        got = run_child(self, 'unified', {'CN_AUTOFIX_ON_LEAVE': '0'})
        self.assertTrue(got['row10_text_after'], got)                             # 前の形: 出ても掛からない


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[sys.argv.index('--child') + 1])
    else:
        unittest.main()
