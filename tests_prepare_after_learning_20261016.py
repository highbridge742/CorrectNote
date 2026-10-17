# -*- coding: utf-8 -*-
"""A learned word resets the worker state, but not the native parse of each line.

morphology.tokenize reads only the versioned public dictionaries. After the
vocabulary changes, the document context must equal a brand-new worker's,
and no unchanged line may be parsed again (3000 lines took 4.4 s).
"""
from collections import Counter
from unittest.mock import patch
import unittest
import morphology as M
import analysis_worker
from analysis_worker import Runtime
from tests_analysis_async import initial

LINES = ['前の資料を確認します。', '書庫の棚を整理した。', '', '提灯を飾った。',
         '書庫の棚を整理した。', 'https://example.com/', '蝸牛がゆっくり進む。',
         '工場の機械を点検した。', 'また機会があれば行きます。']


def fresh_prepare(a, lines):
    r = Runtime()
    r.set_state(analysis_worker.snapshot(a))
    return r.prepare(lines)


@unittest.skipUnless(M.HAS_JANOME, 'native dictionary required')
class PrepareAfterLearningTests(unittest.TestCase):
    def setUp(self):
        self.a = initial()
        self.r = Runtime()
        self.r.set_state(analysis_worker.snapshot(self.a))
        self.first = self.r.prepare(LINES)

    def prepare_counting(self, lines):
        native = M._tokenize_uncached
        counts = Counter()

        def parse(s):
            counts[s] += 1
            return native(s)
        with patch.object(M, '_tokenize_uncached', side_effect=parse):
            got = self.r.prepare(lines)
        return got, counts

    def test_learned_word_gives_the_new_worker_context_without_parsing_again(self):
        self.assertFalse(self.a.store.has_reading('しょこ'))
        self.a.store.add('しょこ', '書庫')
        self.r.set_state(analysis_worker.snapshot(self.a))
        got, counts = self.prepare_counting(LINES)
        self.assertEqual(got, fresh_prepare(self.a, LINES))
        self.assertEqual(counts, Counter())
        # The vocabulary really did change what the context holds.
        self.assertIn('しょこ', got['context'])
        self.assertNotIn('しょこ', self.first['context'])

    def test_removed_word_leaves_the_context_like_a_new_worker(self):
        self.a.store.add('しょこ', '書庫')
        self.r.set_state(analysis_worker.snapshot(self.a))
        self.assertIn('しょこ', self.r.prepare(LINES)['context'])
        self.a.store.remove('しょこ', '書庫')
        self.r.set_state(analysis_worker.snapshot(self.a))
        got, counts = self.prepare_counting(LINES)
        self.assertEqual(got, fresh_prepare(self.a, LINES))
        self.assertNotIn('しょこ', got['context'])
        self.assertEqual(counts, Counter())

    def test_edited_line_after_learning_is_the_only_line_parsed(self):
        self.a.store.add('しょこ', '書庫')
        self.r.set_state(analysis_worker.snapshot(self.a))
        changed = LINES[:]
        changed[3] = '提灯を軒先に飾った。'
        got, counts = self.prepare_counting(changed)
        self.assertEqual(got, fresh_prepare(self.a, changed))
        self.assertEqual(counts, Counter({changed[3]: 1}))

    def test_rows_are_kept_only_for_lines_in_use(self):
        other = ['別の文書の行です。', '書庫の棚を整理した。']
        self.r.prepare(other)
        self.assertEqual(set(self.r.line_tokens), set(other))
        self.assertEqual(set(self.r.content_words), set(other))

    def test_kept_rows_are_not_shared_mutable_tokens(self):
        self.a.store.add('しょこ', '書庫')
        self.r.set_state(analysis_worker.snapshot(self.a))
        from vocabulary import build_context_vocab_cached
        seen = []

        def spy(lines, store, cache, attested_out=None, tokenize_fn=None):
            def wrapped(line):
                toks = tokenize_fn(line)
                for t in toks:
                    t.surface = 'X'      # a caller that mutates must not reach the kept rows
                seen.append(line)
                return tokenize_fn(line)
            return build_context_vocab_cached(lines, store, cache, attested_out=attested_out, tokenize_fn=wrapped)
        with patch('vocabulary.build_context_vocab_cached', side_effect=spy):
            got = self.r.prepare(LINES)
        self.assertTrue(seen)
        self.assertEqual(got, fresh_prepare(self.a, LINES))

    def test_row_parsed_after_a_janome_failure_is_not_kept(self):
        # A one-off janome failure makes the simple splitter stand in. A new
        # process would parse the line properly, so a reset forgets the row.
        target = '提灯を軒先に飾った。'
        changed = LINES[:]
        changed[3] = target
        real = M._TOKENIZER.tokenize
        failed = []

        def flaky(line, *a, **k):
            if line == target and not failed:
                failed.append(line)
                raise RuntimeError('synthetic janome failure')
            return real(line, *a, **k)
        with patch.object(M._TOKENIZER, 'tokenize', side_effect=flaky):
            self.r.prepare(changed)
        self.assertEqual(failed, [target])
        self.assertIn(target, self.r.unsteady)
        self.assertNotIn(target, self.r.line_tokens)
        self.a.store.add('しょこ', '書庫')
        self.r.set_state(analysis_worker.snapshot(self.a))
        self.assertNotIn(target, self.r.content_words)
        got, counts = self.prepare_counting(changed)
        self.assertEqual(got, fresh_prepare(self.a, changed))
        self.assertEqual(counts, Counter({target: 1}))

    def test_decisions_or_index_change_alone_matches_a_new_worker(self):
        self.a.decisions.protect('提灯')
        self.r.set_state(analysis_worker.snapshot(self.a))
        got, counts = self.prepare_counting(LINES)
        self.assertEqual(got, fresh_prepare(self.a, LINES))
        self.assertEqual(counts, Counter())
        self.r.index_key = None          # the dictionary index is built again
        self.r.set_state(analysis_worker.snapshot(self.a))
        got, counts = self.prepare_counting(LINES)
        self.assertEqual(got, fresh_prepare(self.a, LINES))
        self.assertEqual(counts, Counter())

    def test_store_gets_the_tokenizer_on_both_paths(self):
        data = analysis_worker.snapshot(self.a)
        data['_state_identity'] = analysis_worker.state_key(self.a)
        self.r.set_state(data)                      # full reset
        self.assertIs(self.r.store._tokenize_fn, self.r.tokenize)
        store = self.r.store
        self.a.ime_readings.remember('資料', 'しりょう')
        data = analysis_worker.snapshot(self.a)
        data['_state_identity'] = analysis_worker.state_key(self.a)
        self.r.set_state(data)                      # only the readings changed
        self.assertIs(self.r.store, store)
        self.assertIs(self.r.store._tokenize_fn, self.r.tokenize)
        self.assertEqual(self.r.prepare(LINES), fresh_prepare(self.a, LINES))

    def test_prepared_and_context_lines_are_built_again(self):
        self.r.prepare(LINES)
        self.assertTrue(self.r.prepared and self.r.context_lines)
        self.a.store.add('しょこ', '書庫')
        self.r.set_state(analysis_worker.snapshot(self.a))
        self.assertFalse(self.r.prepared)
        self.assertFalse(self.r.context_lines)

    def test_fallback_splitter_follows_the_store(self):
        with patch.object(M, 'HAS_JANOME', False):
            self.r.set_state(analysis_worker.snapshot(self.a))
        self.assertFalse(self.r.line_tokens)
        self.assertFalse(self.r.content_words)


if __name__ == '__main__':
    unittest.main()
