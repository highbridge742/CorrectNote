# -*- coding: utf-8 -*-
"""メモリの控え（中で12タブ）から落ちたタブへ戻った時、ディスクの解析の控えから答えを戻す（2026-11-15 うにさん
「全体的なものは5分前に起きた、今最後に開いたタブです」: 19タブ開いていて、戻ったタブを大きく解き直していた）。
枠は増やさない。落としたタブはディスクに残し、戻った時に起動の時と同じ照合で読む。途中で離れたタブの済んだ行も残す。
既定はオン（CN_ANALYSIS_DISK_KEEP=0 で前の形・2026-11-15）。作った値だけ（一時フォルダ）。"""
import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import analysis_cache as C
import app

FP = {'cache_version': 'test'}


def result(line):
    return {'original': line, 'corrected': line, 'changed': False, 'details': [], 'odd_spans': [], 'spans': []}


def tab_text(i, n=5):
    return '\n'.join('タブ%d の %d 行目' % (i, k) for k in range(n))


class DiskKeep(unittest.TestCase):
    def setUp(self):
        os.environ['CN_ANALYSIS_DISK_KEEP'] = '1'
        self.addCleanup(os.environ.pop, 'CN_ANALYSIS_DISK_KEEP', None)
        self.path = os.path.join(tempfile.mkdtemp(), 'analysis_cache.json')

    def full(self, i):
        text = tab_text(i)
        return text, [result(l) for l in text.split('\n')]

    def test_tabs_left_out_of_the_new_write_are_kept_while_open(self):
        tabs = dict(self.full(i) for i in range(13))
        self.assertTrue(C.save(self.path, FP, tabs))
        # 次に書く時、メモリには新しい12タブ（0番は落ちた）しか無い
        newer = {k: v for k, v in tabs.items() if k != tab_text(0)}
        C.save(self.path, FP, newer, keep_texts=set(tabs))
        got = C.lookup(self.path, FP, tab_text(0))
        self.assertIsNotNone(got)
        self.assertEqual([r['original'] for r in got], tab_text(0).split('\n'))
        self.assertTrue(all(r.get('_from_file') for r in got))      # 起動の時と同じ「控えから戻した行」の印

    def test_closed_tabs_are_not_kept(self):
        tabs = dict(self.full(i) for i in range(3))
        C.save(self.path, FP, tabs)
        C.save(self.path, FP, {tab_text(1): tabs[tab_text(1)]}, keep_texts={tab_text(1)})
        self.assertIsNone(C.lookup(self.path, FP, tab_text(0)))        # 閉じたタブ（開いていない）は残さない

    def test_other_fingerprint_is_not_used(self):
        C.save(self.path, FP, dict([self.full(0)]))
        self.assertIsNone(C.lookup(self.path, {'cache_version': 'other'}, tab_text(0)))
        C.save(self.path, {'cache_version': 'other'}, dict([self.full(1)]), keep_texts={tab_text(0), tab_text(1)})
        self.assertIsNone(C.lookup(self.path, {'cache_version': 'other'}, tab_text(0)))   # 指紋が違う欄は持ち越さない

    def test_partial_rows_are_kept(self):
        text = tab_text(5)
        rows = [result(l) if k < 3 else None for k, l in enumerate(text.split('\n'))]
        C.save(self.path, FP, {}, partial={text: rows})
        C.save(self.path, FP, dict([self.full(1)]), keep_texts={text, tab_text(1)})
        got = C.lookup(self.path, FP, text)
        self.assertEqual([r is not None for r in got], [True, True, True, False, False])

    def test_switch_off(self):
        tabs = dict(self.full(i) for i in range(2))
        C.save(self.path, FP, tabs)
        with mock.patch.dict(os.environ, {'CN_ANALYSIS_DISK_KEEP': '0'}):
            C.save(self.path, FP, {tab_text(1): tabs[tab_text(1)]}, keep_texts=set(tabs))
        self.assertIsNone(C.lookup(self.path, FP, tab_text(0)))


class AppSide(unittest.TestCase):
    def setUp(self):
        os.environ['CN_ANALYSIS_DISK_KEEP'] = '1'
        self.addCleanup(os.environ.pop, 'CN_ANALYSIS_DISK_KEEP', None)
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'analysis_cache.json')

    def fake(self):
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.store = NS(saved_revision=1, revision=lambda: 1)
        a._analysis_partial = {}
        a._analysis_partial_state = None
        a._analysis_cache_fingerprint = lambda: FP
        return a

    def test_back_to_a_tab_out_of_memory_reads_the_disk(self):
        text = tab_text(0)
        C.save(self.path, FP, {text: [result(l) for l in text.split('\n')]})
        a = self.fake()
        with mock.patch.object(app, 'ANALYSIS_CACHE_FILE', self.path), \
                mock.patch.object(app.analysis_async, 'state_key', lambda s: ('s',) * 10):
            self.assertTrue(a._load_tab_from_disk_cache(text))
        self.assertEqual(len(a._analysis_partial[text]), 5)
        self.assertIsNotNone(a._analysis_partial_state)

    def test_not_while_words_are_unsaved_or_switched_off(self):
        text = tab_text(0)
        C.save(self.path, FP, {text: [result(l) for l in text.split('\n')]})
        a = self.fake()
        a.store = NS(saved_revision=1, revision=lambda: 2)
        with mock.patch.object(app, 'ANALYSIS_CACHE_FILE', self.path):
            self.assertFalse(a._load_tab_from_disk_cache(text))
            a.store = NS(saved_revision=1, revision=lambda: 1)
            with mock.patch.dict(os.environ, {'CN_ANALYSIS_DISK_KEEP': '0'}):
                self.assertFalse(a._load_tab_from_disk_cache(text))

    def test_eviction_keeps_the_tab_until_the_next_write(self):
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._analysis_cache = {}
        a._analysis_cache_dependencies = {}
        a._analysis_stale = set()
        a._schedule_analysis_cache_autosave = mock.Mock()
        a._prune_analysis_cache = lambda keep=None: None
        a._analysis_cache_tabs = lambda: 12
        for i in range(13):
            text = tab_text(i)
            a._analyze_text = text
            a.line_results = [result(l) for l in text.split('\n')]
            a._analyze_dependencies = ('s',) * 10
            with mock.patch('analysis_work_app.has_local_evidence', lambda s: False), \
                    mock.patch('analysis_work_app.token', lambda s: None), \
                    mock.patch.object(app.tab_analysis, 'remember', lambda s: None):
                a._analyze_work = None
                a._auto_learning_deferred_owner = 'x'
                with mock.patch('analysis_work_app.owner', lambda s: 'y'):
                    app.CorrectNoteApp._remember_tab_results(a)
        self.assertEqual(len(a._analysis_cache), 12)
        self.assertIn(tab_text(0), a._analysis_evicted)                # 落ちた0番は、次に書くまで持つ
        a._schedule_analysis_cache_autosave.assert_called()


if __name__ == '__main__':
    unittest.main()
