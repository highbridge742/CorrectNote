# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""同音異義語の対の表（homophone_pairs 版8・2026-10-25、版9 で degree_adverb.py に移した・2026-10-26）: 対に「直前の語」の手がかりを足せる。
思→重い は直前が程度の副詞（とても・かなり…）なら手がかり語が無くても 重い。名詞の 思い（思いが強い）・
後ろの門（ます・やり・込）はそのまま守る。未解決タブ とても思い→とても重い。例は作ったもの。"""
import unittest

import app as C
import homophone_pairs
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


class DegreeAdverbHomophoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        cls.index = DictIndex()
        cls.index.ensure_built()

    def _run(self, line):
        return C.correct_line(line, self.store, input_method='kana', dict_index=self.index)['corrected']

    def test_find_fix_no_longer_holds_an_adverb_list(self):
        # 版9（2026-10-26）: 程度の副詞の一覧は対の表から外し、degree_adverb.py が品詞で見る
        self.assertIsNone(homophone_pairs.find_fix('思い', (), after='', prev='とても',
                                                   source='とても思い'))

    def test_degree_adverb_line_is_repaired(self):
        self.assertEqual(self._run('とても思い'), 'とても重い')
        self.assertEqual(self._run('箱がかなり思いので休んだ'), '箱がかなり重いので休んだ')

    def test_noun_and_compound_forms_untouched(self):
        for line in ('彼はとても思いが強い', 'とても思います', 'とても思いやりがある',
                     '少し思い出した', '本当に思い込みだ'):
            with self.subTest(line=line):
                self.assertEqual(self._run(line), line)


if __name__ == '__main__':
    unittest.main()
