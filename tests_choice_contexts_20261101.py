# -*- coding: utf-8 -*-
"""補正欄で同音の語を選び直したら、補正欄の表示が替わる（2026-11-01 うにさん「補正欄で再変換の候補を
選んでも何も起きないが、変換した履歴だけは残っている」）。

同音の語どうしの選び直しは、前後の語ごと覚える（last_choice._contexts）。表示の組み立て
（units._find_choice_ranges）は originals() の語を本文から探すので、そこに _contexts の語も入れる。
解析の子へ渡す控え（analysis_worker.snapshot）にも _contexts を入れる（入れないと子の表示で戻る）。"""
import inspect
import os
import tempfile
import unittest

import analysis_worker
import last_choice
import units


class ChoiceContextsTests(unittest.TestCase):
    TOKENS = [('会議', '名詞', 'かいぎ', 0, 2), ('の', '助詞', 'の', 2, 3), ('資料', '名詞', 'しりょう', 3, 5),
              ('を', '助詞', 'を', 5, 6), ('作成', '名詞', 'さくせい', 6, 8)]
    TEXT = '会議の資料を作成'

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = last_choice.LastChoiceStore(os.path.join(self.folder.name, 'last_choice.json'))

    def tearDown(self):
        self.folder.cleanup()

    def _record(self):
        prev, next_ = units._token_before(self.TOKENS, 3), units._token_after(self.TOKENS, 5)
        self.store.record('資料', '史料', 'しりょう', prev, next_)
        return prev, next_

    def test_a_homophone_choice_is_among_the_originals(self):
        prev, next_ = self._record()
        self.assertTrue(self.store._contexts)                 # 前後の語ごと覚えた
        self.assertIn('資料', self.store.originals())
        self.assertEqual(self.store.lookup('資料', prev, next_), '史料')

    def test_the_display_finds_the_choice_in_the_line(self):
        self._record()
        self.assertEqual(units._find_choice_ranges(self.TEXT, self.TOKENS, self.store), [(3, 5, '資料', '史料')])

    def test_another_context_keeps_the_written_word(self):
        self._record()
        other = [('古い', '形容詞', 'ふるい', 0, 2), ('資料', '名詞', 'しりょう', 2, 4), ('だ', '助動詞', 'だ', 4, 5)]
        self.assertEqual(units._find_choice_ranges('古い資料だ', other, self.store), [])

    def test_reset_forgets_the_context_choice(self):
        # 補正欄の「元に戻す」（app._forget_choice → forget / forget_all）が前後の語ごとの記録も消す
        prev, next_ = self._record()
        self.assertTrue(self.store.forget('資料', prev, next_))
        self.assertIsNone(self.store.lookup('資料', prev, next_))
        self._record()
        self.store.record('資料', '史料', 'しりょう', 'この', 'が')
        self.assertTrue(self.store.forget_all('資料'))
        self.assertFalse(self.store._contexts)
        self.assertNotIn('資料', self.store.originals())

    def test_the_worker_receives_the_contexts(self):
        self.assertIn("'_contexts'", inspect.getsource(analysis_worker.snapshot))


if __name__ == '__main__':
    unittest.main()
