# -*- coding: utf-8 -*-
"""起動のとき、開いているタブの行を別の子2つで先に解析する（analysis_async.start_startup_parse・2026-11-01・処理の負荷）。

3,600行のタブの最初の準備（prepare）は、英単語の覚え直しの答えのあとに janome で 2.9秒かかっていた。開いているタブの子は
それまで表の先読みで手がふさがっている。子2つが半分ずつ公の辞書だけで解析し（Runtime.warm_lines）、最初の準備がその行を
使う（準備 2.9 → 0.13秒）。作る行は準備が自分で作るものと同じ（答えは同じ）。"""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import analysis_async
import analysis_worker
import morphology


class _Worker:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.closed, self.tasks = result, error, False, []

    def submit(self, task, state=None):
        self.tasks.append(task)
        return len(self.tasks)

    def poll(self, job):
        if self.error:
            raise RuntimeError(self.error)
        return self.result

    def close(self):
        self.closed = True


def _app(jobs):
    return SimpleNamespace(_startup_parse=dict(jobs=[(w, 1) for w in jobs], results=[None] * len(jobs), since=None),
                           _closing=False)


class StartupParseWaitTests(unittest.TestCase):
    def test_waits_until_every_part_has_come_then_hands_the_rows_on(self):
        first, second = _Worker(dict(blob=b'a')), _Worker()
        app = _app([first, second])
        self.assertTrue(analysis_async.startup_parse_waiting(app))
        second.result = dict(blob=b'b')
        self.assertFalse(analysis_async.startup_parse_waiting(app))
        self.assertEqual(app._startup_parsed, dict(blobs=[b'a', b'b']))   # 本体はほどかずに渡すだけ
        self.assertTrue(first.closed and second.closed)
        self.assertIsNone(app._startup_parse)

    def test_gives_up_after_the_wait_or_a_failure(self):
        late = _Worker()
        app = _app([late])
        self.assertTrue(analysis_async.startup_parse_waiting(app))
        app._startup_parse['since'] = time.monotonic() - analysis_async.STARTUP_PARSE_WAIT_S - 1
        self.assertFalse(analysis_async.startup_parse_waiting(app))
        self.assertTrue(late.closed)
        self.assertIsNone(getattr(app, '_startup_parsed', None))
        broken = _Worker(error='boom')
        app = _app([broken])
        with patch('traceback.print_exc'):
            self.assertFalse(analysis_async.startup_parse_waiting(app))
        self.assertTrue(broken.closed)

    def test_children_follow_free_memory_and_processors(self):
        # 2026-11-01 うにさん「メモリに余裕があるなら使うとよい…メモリ高以外でも」: 段階を問わず、空きと CPU で数を決める
        count = analysis_async.startup_parse_children
        self.assertEqual([count(1600, cpus, 20000) for cpus in (16, 8, 6, 4)], [3, 2, 1, 0])
        self.assertEqual([count(1600, 16, free) for free in (2100, 1800, 1600)], [3, 1, 0])
        with patch.object(analysis_async, '_free_memory_mb', lambda: None):
            self.assertEqual(count(1600, 16), 0)            # 空きが分からなければ足さない
        self.assertEqual(count(500, 16, 20000), 1)          # 短いタブは janome を読む手間に見合う数だけ

    def test_a_long_tab_at_any_memory_setting_and_the_switch(self):
        editor = SimpleNamespace(get=lambda a, b: '\n'.join('行%d' % i for i in range(1000)))
        jobs = []
        root = SimpleNamespace(after=lambda ms, fn: jobs.append((ms, fn)))
        app = SimpleNamespace(editor=editor, root=root)
        made = []
        with patch.object(analysis_async, 'Worker', lambda: made.append(_Worker()) or made[-1]),                 patch.object(analysis_async, 'startup_parse_children', lambda lines: 3):
            with patch.object(analysis_async, 'STARTUP_PARSE_ENABLED', False):
                analysis_async.start_startup_parse(app)      # CN_STARTUP_PARSE=0 で止める
            self.assertIsNone(app._startup_parse)
            analysis_async.start_startup_parse(app)
            self.assertEqual([len(w.tasks[0]['lines']) for w in made], [334, 333, 333])
            self.assertEqual(jobs[0][0], analysis_async.STARTUP_PARSE_MAX_MS)
            jobs[0][1]()                                     # 使われないまま時間が来たら閉じる
            self.assertEqual({ms for ms, _fn in jobs[1:]}, {analysis_async.STARTUP_PARSE_CLOSE_MS})
            for _ms, fn in jobs[1:]:
                fn()                                         # 終わるのを待たずに頼み、少しあとで閉じる
            self.assertTrue(all(w.closed for w in made))
            self.assertIsNone(app._startup_parse)
            app.editor = SimpleNamespace(get=lambda a, b: '短い\n')
            analysis_async.start_startup_parse(app)
            self.assertIsNone(app._startup_parse)


class OpenedFileTests(unittest.TestCase):
    def test_an_opened_file_shares_the_lines_with_the_idle_open_tab_child(self):
        # 2026-11-02: 5,000行のファイルを開くと、最初の準備まで 6.9秒 → 3.3秒（開いているタブの子も1つ分を受け持つ）
        lines = '\n'.join('行%d' % i for i in range(1000))
        own = _Worker(); own.process = SimpleNamespace(is_alive=lambda: True)
        app = SimpleNamespace(editor=SimpleNamespace(get=lambda a, b: lines), root=SimpleNamespace(after=lambda ms, fn: None),
                              _correction_worker=own, _async_request=None)
        made = []
        with patch.object(analysis_async, 'Worker', lambda: made.append(_Worker()) or made[-1]),                 patch.object(analysis_async, 'startup_parse_children', lambda lines: 3):
            analysis_async.start_startup_parse(app, own_share=True)
        self.assertEqual([len(w.tasks[0]['lines']) for w in made], [250, 250, 250])
        self.assertEqual((own.tasks[0]['kind'], len(own.tasks[0]['lines'])), ('warmup', 250))
        self.assertGreater(app._startup_parse['wait'], analysis_async.STARTUP_PARSE_WAIT_S - 0.01)
        app._async_request = ('busy', 1); own.tasks = []      # 子が働いているときは受け持たせない
        with patch.object(analysis_async, 'Worker', lambda: _Worker()),                 patch.object(analysis_async, 'startup_parse_children', lambda lines: 3):
            analysis_async.start_startup_parse(app, own_share=True)
        self.assertEqual(own.tasks, [])


class VeryLongTextTests(unittest.TestCase):
    def test_children_take_only_what_they_parse_in_a_few_seconds(self):
        # 上限より待ちが長くなると、見に行く予約が消えて解析が止まる。とても長い本文の残りは、準備が自分で解析する
        lines = '\n'.join('行%d' % i for i in range(30000))
        app = SimpleNamespace(editor=SimpleNamespace(get=lambda a, b: lines), root=SimpleNamespace(after=lambda ms, fn: None))
        made = []
        with patch.object(analysis_async, 'Worker', lambda: made.append(_Worker()) or made[-1]), \
                patch.object(analysis_async, 'startup_parse_children', lambda lines: 3):
            analysis_async.start_startup_parse(app)
        self.assertEqual([len(w.tasks[0]['lines']) for w in made], [analysis_async.STARTUP_PARSE_LINES_PER_PART] * 3)
        self.assertLess(app._startup_parse['wait'] * 1000, analysis_async.STARTUP_PARSE_MAX_MS)


class PastedLinesTests(unittest.TestCase):
    def setUp(self):
        self.prev = ['前%d' % i for i in range(100)]
        self.lines = self.prev + ['新%d' % i for i in range(3000)]
        text = "\n".join(self.lines)
        self.app = SimpleNamespace(editor=SimpleNamespace(get=lambda a, b: text), root=SimpleNamespace(after=lambda ms, fn: None),
                                   _prev_lines=self.prev, _analyze_work=('tab', 1), _async_request=None)
        self.made = []

    def run_it(self, token=('tab', 2)):
        with patch.object(analysis_async, 'Worker', lambda: self.made.append(_Worker()) or self.made[-1]),                 patch.object(analysis_async, 'startup_parse_children', lambda lines: 3),                 patch.object(analysis_async.input_work, 'token', lambda a: token):
            analysis_async._parse_pasted_lines(self.app, self.lines)

    def test_only_the_new_lines_and_once(self):
        self.run_it()
        sent = [line for w in self.made for line in w.tasks[0]['lines']]
        self.assertEqual(len(self.made), 3)
        self.assertTrue(sent and all(line.startswith('新') for line in sent))
        analysis_async._close_startup_parse(self.app); n = len(self.made)
        self.run_it()                                      # 準備の答えが出るまで1回だけ
        self.assertEqual(len(self.made), n)

    def test_not_on_a_tab_switch_or_a_small_edit(self):
        self.app._analyze_work = ('other tab', 1)
        self.run_it()
        self.assertEqual(self.made, [])
        self.app._analyze_work = ('tab', 1); self.lines = self.prev + ['新']
        self.run_it()
        self.assertEqual(self.made, [])


class WaitThenAnalyseTests(unittest.TestCase):
    def test_the_first_prepare_waits_then_analyses_once(self):
        # 控え（analysis_cache）の行は待たずに出る: 待つのは準備を送るところだけ
        jobs = []
        root = SimpleNamespace(after=lambda ms, fn: jobs.append(fn) or len(jobs), after_cancel=lambda job: None)
        worker = _Worker()
        analysed = []
        app = _app([worker])
        app.root, app._analyze = root, lambda: analysed.append(1)
        app.status = SimpleNamespace(config=lambda **k: None)
        with patch.object(analysis_async, 'state_key', lambda a: 'state'),                 patch.object(analysis_async.input_work, 'token', lambda a: 'token'),                 patch.object(analysis_async, 'cached_context', lambda a, t: None),                 patch('ime_speculation.waiting', lambda a: False),                 patch('ime_speculation.context_for', lambda a, t: None):
            self.assertIsNone(analysis_async.context(app, '行', ['行']))
            self.assertIsNone(analysis_async.context(app, '行', ['行']))
            self.assertEqual(len(jobs), 1)                    # 見に行く予約は1つだけ
            jobs.pop()()
            self.assertEqual((len(jobs), analysed), (1, []))  # まだ答えが無い
            worker.result = dict(blob=b'x')
            jobs.pop()()
        self.assertEqual(analysed, [1])
        self.assertEqual(app._startup_parsed['blobs'], [b'x'])
        self.assertIsNone(app._startup_parse_poll)


class ParsedRowsTests(unittest.TestCase):
    def test_a_prepare_with_the_parsed_rows_is_the_same(self):
        if not morphology.HAS_JANOME:
            self.skipTest('janome')
        lines = ['今日は天気が良いので散歩に行った。', '明日は雨が降るらしい。', '', '同じ行', '同じ行']
        helper = analysis_worker.Runtime()
        import pickle
        blob = helper.execute(dict(kind='parse_lines', lines=lines[:2]))['blob']
        self.assertEqual(sorted(pickle.loads(blob)[0]), sorted(lines[:2]))
        parsed = dict(blobs=[blob])
        from tests_analysis_async import initial
        state = analysis_worker.snapshot(initial())
        plain = analysis_worker.Runtime()
        plain.set_state(state)
        plain.prepare_tables = lambda: None
        expected = plain.execute(dict(kind='prepare', lines=lines))
        reused = analysis_worker.Runtime()
        reused.set_state(state)
        reused.prepare_tables = lambda: None
        calls = []
        real = morphology.tokenize
        with patch.object(morphology, 'tokenize', lambda line, *a, **k: calls.append(line) or real(line, *a, **k)):
            got = reused.execute(dict(kind='prepare', lines=lines, parsed=parsed))
        self.assertEqual(got['words'], expected['words'])
        self.assertEqual(got['attested'], expected['attested'])
        self.assertEqual(got['context'], expected['context'])
        self.assertNotIn(lines[0], calls)
        self.assertEqual(reused.line_tokens[lines[0]], plain.line_tokens[lines[0]])


if __name__ == '__main__':
    unittest.main()
