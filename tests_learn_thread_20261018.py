# -*- coding: utf-8 -*-
"""Automatic learning tokenizes new lines on another thread (2026-10-18): the
same words are learned as before, typing is not blocked meanwhile, and closing
finishes what is pending."""
import copy
import time
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import app
import janome_import
from seed_vocabulary import load_seed
from vocabulary import VocabularyStore


def store():
    s = VocabularyStore()
    load_seed(s)
    return s


TEXT = '\n'.join(['図書館で資料を探して、新しい企画書を書きました。',
                  '会議室の予約は来週の月曜日に変更になりました。',
                  '駅前の喫茶店で打ち合わせをしてから帰宅します。'] * 40)


@unittest.skipUnless(janome_import.HAS_JANOME, 'janome')
class LearnThreadTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.store = store()
        a._learned_lines = set()
        a._learn_after_id = None
        a._analyze_text = ''
        a.line_results = []
        a._learn_english_now = Mock()
        a._update_status = Mock()
        a._invalidate_analysis_cache = Mock()
        a._retain_finished_rows_after_auto_learning = Mock()

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root')

    def pump_until(self, predicate, seconds=60):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update()
            if predicate():
                return
            time.sleep(0.005)
        self.fail('timed out')

    def test_the_same_words_are_learned_as_learning_at_once(self):
        expected = store()
        added = janome_import.learn_from_text(expected, TEXT)
        self.assertGreater(added, 0)
        with patch.object(self.a.store, 'save_in_background') as save:
            self.a._learn_now(TEXT)
            self.assertIsNotNone(self.a._learn_thread)          # not on this thread
            self.pump_until(lambda: self.a._learn_thread is None)
        self.assertEqual(self.a.store.to_list(), expected.to_list())
        save.assert_called_once_with()
        self.a._invalidate_analysis_cache.assert_called_once_with()
        self.a._retain_finished_rows_after_auto_learning.assert_called_once_with()
        # the same lines are not learned again
        before = copy.deepcopy(self.a.store.to_list())
        self.a._learn_now(TEXT + '\n')
        self.assertIsNone(getattr(self.a, '_learn_thread', None))
        self.assertEqual(self.a.store.to_list(), before)

    def test_this_thread_keeps_running_while_tokenizing(self):
        ticks = []

        def tick():
            ticks.append(time.monotonic())
            self.root.after(10, tick)
        long_text = '\n'.join('%d行目の本文を書き足して、新しい言葉を覚えさせます。' % i for i in range(1500))
        start = time.monotonic()
        with patch.object(self.a.store, 'save_in_background'):
            self.root.after(10, tick)
            self.a._learn_now(long_text)
            called = time.monotonic() - start
            self.pump_until(lambda: self.a._learn_thread is None, 120)
        took = time.monotonic() - start
        self.assertLess(called, 0.5, 'tokenizing ran on the UI thread')
        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        self.assertGreater(len(ticks), 5, (took, len(ticks)))
        # Without the thread there would be one gap as long as the whole tokenizing.
        self.assertLess(max(gaps), max(0.5, took / 2), (took, max(gaps)))

    def test_order_is_kept_and_closing_finishes_pending_learning(self):
        first, second = TEXT, '\n'.join(['新幹線の切符を窓口で受け取りました。'] * 30)
        expected = store()
        janome_import.learn_from_text(expected, first)
        janome_import.learn_from_text(expected, second)
        with patch.object(self.a.store, 'save_in_background'):
            self.a._learn_now(first)
            self.a._learn_now(second)
            self.assertEqual(len(self.a._learn_queue), 1)
            self.a._closing = True
            self.a._finish_learning_now()
        self.assertIsNone(self.a._learn_thread)
        self.assertEqual(self.a._learn_queue, [])
        self.assertEqual(self.a.store.to_list(), expected.to_list())


@unittest.skipUnless(janome_import.HAS_JANOME, 'janome')
class LearningTokensTests(unittest.TestCase):
    def key(self, token):
        return (token.surface, token.part_of_speech, getattr(token, 'base_form', ''),
                getattr(token, 'infl_form', ''), getattr(token, 'reading', ''))

    def test_the_same_tokens_as_one_janome_call(self):
        import learning_tokens
        from pathlib import Path
        manual = Path(__file__).with_name('CorrectNote_説明書.html').read_text(encoding='utf-8')[:60000]
        for text in (TEXT, manual, 'Python と 図書館 2026年10月18日。' + chr(10) * 2 + '次の行'):
            with janome_import._janome_lock():
                expected = [self.key(t) for t in janome_import.Tokenizer().tokenize(text)]
            self.assertEqual([self.key(t) for t in learning_tokens.tokenize(text)], expected)
        self.assertIsNone(learning_tokens.tokenize(''))

    def test_learn_is_learn_from_text_and_puts_the_tokenizer_back(self):
        import learning_tokens
        real = janome_import.Tokenizer
        expected = store()
        a, b = store(), store()
        self.assertEqual(learning_tokens.learn(a, TEXT, learning_tokens.tokenize(TEXT)),
                         janome_import.learn_from_text(expected, TEXT))
        self.assertEqual(a.to_list(), expected.to_list())
        self.assertIs(janome_import.Tokenizer, real)
        self.assertEqual(learning_tokens.learn(b, TEXT, None), 0)
        with patch.object(janome_import, 'learn_from_text', side_effect=RuntimeError('x')):
            with self.assertRaises(RuntimeError):
                learning_tokens.learn(b, TEXT, [])
        self.assertIs(janome_import.Tokenizer, real)

    def test_janome_import_keeps_the_pinned_source(self):
        # public_nominal_cache pins janome_import.py; the learning thread must not need it changed
        import importlib.util
        import public_nominal_cache as P
        origin = importlib.util.find_spec('janome_import').origin
        self.assertEqual(P._digest(origin), P.CODE_SHA256['janome_import'])


if __name__ == '__main__':
    unittest.main()
