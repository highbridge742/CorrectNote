# -*- coding: utf-8 -*-
"""Redo only the rows that used what moved (2026-10-24・うにさん 10-23「A 関係する行だけ」・used_keys).

A row's answer says which vocabulary and choice keys it looked up, whether it read the recent words and whether
it read a whole store (used_keys). This process notes which keys changed (used_changes, memory only). The rows
kept after one change must be exactly what a whole new analysis gives: the test analyses made-up text in a real
analysis process, changes one thing, keeps the rows result_compatible keeps, analyses everything again from the
new state and compares (no windows, the bundled vocabulary only)."""
import time
import unittest

import analysis_context, analysis_worker, used_changes
from analysis_worker import state_key, same_model_state, result_compatible, model_moved

SENTENCES = ['作業が官僚しました。', '寒ぃ日だ。', '今日も良い天気です。', '書類を作成しました。', '会議の資料を配ります。',
             '橋を渡ります。', 'よいでしょぅか。', '新しい計画を立てる。', '駅まで歩いて行きました。', '明日は雨が降るそうです。',
             'メールを送信しました。', '資料を保存しました。', '本を読む。', '記録を残します。', '電車が遅れています。',
             '予定を確認してください。', '昼ご飯を食べた。', '窓を開けて換気する。', '問題が解決しました。', '手紙を書きました。']
LINES = ['%d %s' % (i, SENTENCES[i % len(SENTENCES)]) for i in range(40)]


def _app():
    from tests_analysis_async import initial
    from context_vec import RecentWords
    a = initial()
    a.recent_words = RecentWords()
    return a


def _analyse(a):
    worker = analysis_worker.Worker()
    try:
        def wait(ident):
            end = time.monotonic() + 300
            while time.monotonic() < end:
                got = worker.poll(ident)
                if got is not None:
                    return got
                time.sleep(.01)
            raise AssertionError('worker timed out')
        prepared = wait(worker.submit(dict(kind='prepare', lines=LINES), analysis_worker.snapshot(a)))
        out = []
        for line in LINES:
            got = wait(worker.submit(dict(kind='line', line=line, context=prepared['context'], input_method='kana',
                                          attested=prepared['attested'])))
            out.append(analysis_context.completed(got))
        return out
    finally:
        worker.close()


def _answer(r):
    return r['corrected'], [list(x) for x in r.get('odd_spans') or ()], [list(x) for x in r.get('details') or ()]


class ChangedKeysTests(unittest.TestCase):
    def test_the_keys_between_two_revisions_or_none(self):
        class Store:
            _revision = 0

            def revision(self):
                return self._revision

            def add(self, reading, surface):
                self._revision += 1
                if reading == 'なか':                     # a call inside another one
                    self.add('うち', '内')
        used_changes._wrap(Store, 'add', lambda reading, surface, *a, **k: (reading, surface))
        s = Store()
        s.add('あめ', '雨')
        s.add('なか', '中')
        self.assertEqual(used_changes.changed(s, 0, 1), {'あめ', '雨'})
        self.assertEqual(used_changes.changed(s, 0, 3), {'あめ', '雨', 'なか', '中', 'うち', '内'})
        self.assertEqual(used_changes.changed(s, 1, 1), frozenset())
        s._revision += 1                                    # moved by something not noted (a load)
        self.assertIsNone(used_changes.changed(s, 0, 4))
        self.assertIsNone(used_changes.changed(None, 0, 1))


class RowReuseTests(unittest.TestCase):
    """Each change: the kept rows equal a whole new analysis."""

    @classmethod
    def setUpClass(cls):
        cls.base_app = _app()
        cls.base = _analyse(cls.base_app)
        cls.kept_counts = {}

    def check(self, name, change, expect_some_kept=True, expect_some_redone=True):
        a = self.base_app
        previous = state_key(a)
        change(a)
        current = state_key(a)
        self.assertTrue(same_model_state(previous, current))
        kept = [i for i, r in enumerate(self.base) if result_compatible(a, r, previous, current)]
        fresh = _analyse(a)
        diffs = [i for i in kept if _answer(self.base[i]) != _answer(fresh[i])]
        self.kept_counts[name] = (len(kept), len(LINES))
        self.assertEqual(diffs, [], name)                                  # 残した行と全部やり直した結果の違い 0
        if expect_some_kept:
            self.assertTrue(kept, name)
        if expect_some_redone:
            self.assertLess(len(kept), len(LINES), name)
        # the base for the next change is the new state (all rows answer from it)
        type(self).base = fresh

    def test_1_a_word_not_in_the_text(self):
        self.check('vocab_elsewhere', lambda a: a.store.add('てすとごい', '試語彙', category='その他'),
                   expect_some_redone=False)

    def test_2_a_word_in_the_text(self):
        self.check('vocab_in_text', lambda a: a.store.add('しりょう', '試料', category='その他'))

    def test_3_a_choice(self):
        self.check('choice', lambda a: a.choices.remember('資料', '資料', reading='しりょう', store=a.store,
                                                          dict_index=a.dict_index))

    def test_4_a_recent_word(self):
        self.check('recent', lambda a: a.recent_words.add('資料'))

    def test_5_an_ime_reading(self):
        self.check('ime', lambda a: a.ime_readings.remember('資料', 'しりょう'))

    def test_6_a_katakana_word(self):
        # used_keys loan (2026-10-24): rows that used the loanword / English tables are redone only for a word that
        # can be in them
        self.check('loan_word', lambda a: a.store.add('てすとめーる', 'テストメール', category='その他'),
                   expect_some_redone=False)

    def test_7_the_loan_rows_stay_for_a_word_in_kanji(self):
        import used_keys
        self.assertTrue(used_keys.is_loan_change('てすとめーる', 'テストメール'))
        self.assertFalse(used_keys.is_loan_change('しりょう', '試料'))
        loan_rows = [r for r in self.base if (r.get('used_keys') or {}).get('loan')
                     and not (r.get('used_keys') or {}).get('whole')]
        self.assertTrue(loan_rows)                         # the made-up text has rows that used the tables

    def test_8_the_saved_tab_is_not_completed_when_the_store_moved(self):
        a = self.base_app
        previous = state_key(a)
        a.store.add('てすとごいに', '試語彙二', category='その他')
        self.assertTrue(model_moved(previous, state_key(a)))
        self.assertFalse(model_moved(previous, previous))

    @classmethod
    def tearDownClass(cls):
        print('\nkept rows:', cls.kept_counts)


if __name__ == '__main__':
    unittest.main()
