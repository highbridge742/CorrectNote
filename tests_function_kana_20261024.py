# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""かなで書いた形式名詞・補助の動詞・接続詞を、同じ読みの漢字に替えるだけの直しを戻す（2026-10-24）。作った文だけ。"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import correction_entry as CE


def answer(line, corrected):
    return {'corrected': corrected, 'changed': True, 'details': [['x', corrected, 't']], 'spans': [], 'original_spans': []}


class FunctionKanaTest(unittest.TestCase):
    def check(self, line, corrected, expected):
        self.assertEqual(CE._keep_function_kana(line, answer(line, corrected))['corrected'], expected)

    def test_formal_noun_stays_kana(self):
        self.check('雨がやんだところで出かけた', '雨がやんだ処で出かけた', '雨がやんだところで出かけた')
        self.check('見たことがある', '見た事がある', '見たことがある')

    def test_auxiliary_verb_stays_kana(self):
        self.check('書いてみる', '書いて見る', '書いてみる')

    def test_conjunction_stays_kana(self):
        self.check('ところで、明日は', '所で、明日は', 'ところで、明日は')

    def test_ordinary_words_still_converted(self):
        self.check('あめがふる', '雨が降る', '雨が降る')
        self.check('みたことがある', '見たことがある', '見たことがある')

    def test_typo_fix_kept(self):
        self.check('雨がやんだとこりで出かけた', '雨がやんだところで出かけた', '雨がやんだところで出かけた')

    def test_kana_word_not_split_by_same_reading_kanji(self):
        # かなの1語の一部だけを同じ読みの漢字にして語を割らない（くだい→く台）。送り仮名の語は今までどおり
        self.check('読んでくだい。', '読んでく台。', '読んでくだい。')
        self.check('たべたい', '食べたい', '食べたい')


if __name__ == '__main__':
    unittest.main()
