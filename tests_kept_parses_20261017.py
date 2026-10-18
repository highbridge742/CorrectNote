# -*- coding: utf-8 -*-
"""The child keeps native parses across row requests (2026-10-17, speed).

While a row is typed, each keystroke parsed the same fragments again. A kept
parse is the parse a new request would make (morphology.tokenize reads only
the public dictionaries), so answers stay those of a fresh child. A row janome
failed on, and another text, are not kept. A newer request still stops a
prepare that checks the request queue on the 5ms cadence only.
"""
from collections import Counter
from unittest.mock import patch
import unittest
import morphology as M
import analysis_worker
from analysis_worker import Runtime
from analysis_context import request_scope, SupersededAnalysis
from tests_analysis_async import initial

ROWS = ['前の資料を確認します。', '書庫の棚を整理した。', '提灯を飾った。', '工場の機械を点検した。']
TYPED = ['今日は図書館', '今日は図書館でしりょう', '今日は図書館でしりょうをさがした。']


def task(prepared, line):
    return dict(kind='line', line=line, result=None, context=prepared['context'], input_method='kana',
                keyboard=None, nearby=(), recent=(), readings=(), calculations=(), attested=prepared['attested'])


def answer(value):
    value = dict(value)
    value.pop('ime_evidence', None)          # which IME readings were asked: history, not the answer
    return value


@unittest.skipUnless(M.HAS_JANOME, 'native dictionary required')
class KeptParsesTests(unittest.TestCase):
    def setUp(self):
        self.a = initial()

    def runtime(self):
        r = Runtime()
        r.set_state(analysis_worker.snapshot(self.a))
        return r

    def run_typed(self, r, counts=None):
        out = []
        for line in TYPED:
            rows = ROWS + [line]
            prepared = r.prepare(rows)
            native = M._tokenize_uncached

            def parse(s):
                if counts is not None:
                    counts[line][s] += 1
                return native(s)
            with patch.object(M, '_tokenize_uncached', side_effect=parse):
                out.append(answer(r.execute(task(prepared, line))))
        return out

    def test_typing_a_row_reuses_parses_and_answers_like_a_fresh_child(self):
        counts = {line: Counter() for line in TYPED}
        kept = self.run_typed(self.runtime(), counts)
        for line, expected in zip(TYPED, kept):
            fresh = self.runtime()
            self.assertEqual(answer(fresh.execute(task(fresh.prepare(ROWS + [line]), line))), expected)
        # The second keystroke parsed fragments the first one had not.
        again = set(counts[TYPED[0]]) & set(counts[TYPED[1]])
        self.assertEqual(again, set())

    def test_a_row_janome_failed_on_leaves_nothing_kept(self):
        r = self.runtime()
        prepared = r.prepare(ROWS + [TYPED[0]])
        r.execute(task(prepared, TYPED[0]))
        self.assertTrue(r._parses[0])
        raw = M._TOKENIZER.tokenize

        def failing(line, *args, **kwargs):
            raise RuntimeError('janome failed')
        prepared = r.prepare(ROWS + [TYPED[1]])
        with patch.object(M._TOKENIZER, 'tokenize', side_effect=failing):
            r.execute(task(prepared, TYPED[1]))
        self.assertEqual(r._parses, ({}, {}))

    def test_another_text_is_not_kept(self):
        r = self.runtime()
        prepared = r.prepare(ROWS + [TYPED[0]])
        r.execute(task(prepared, TYPED[0]))
        self.assertTrue(r._parses[0])
        r.prepare(['まったく別の文書です。', '二行目もちがいます。', 'さんぎょうめ。'])
        self.assertEqual(r._parses, ({}, {}))
        r.prepare(ROWS + [TYPED[0]])                      # one row changed: still the same text
        r.execute(task(r.prepare(ROWS + [TYPED[1]]), TYPED[1]))
        self.assertTrue(r._parses[0])

    def test_a_newer_request_still_stops_a_long_prepare(self):
        r = self.runtime()
        rows = ['%d行目の作り話です。' % i for i in range(3000)]
        r.prepare(rows)                                   # parsed once: the next prepare only walks rows
        changed = list(rows)
        changed[5] += 'あ'
        with self.assertRaises(SupersededAnalysis):
            with request_scope(lambda: True, poll_interval=.005):
                r.prepare(changed)


if __name__ == '__main__':
    unittest.main()
