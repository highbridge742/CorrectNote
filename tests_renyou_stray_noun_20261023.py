"""動詞の連用形に、語にならない名詞が直に続く形に紫を付ける（2026-10-23・印の付かない取りこぼし）"""
import unittest
from tests_analysis_async import initial
from correction_entry import correct_line


class RenyouStrayNounTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = initial()

    def run_line(self, line):
        return correct_line(line, self.st.store, context_vocab={}, input_method='kana',
                            dict_index=self.st.dict_index, decisions=self.st.decisions)

    def test_katakana_after_stem_is_marked(self):
        r = self.run_line('夜は早く寝クス')
        self.assertEqual(r['corrected'], '夜は早く寝クス')
        self.assertIn((4, 7), [tuple(x) for x in r['odd_spans']])

    def test_noun_ending_line_after_stem_is_marked(self):
        r = self.run_line('夜は早く寝麻酔')
        self.assertTrue(r['odd_spans'])

    def test_compound_nouns_from_stem_are_not_marked(self):
        for line in ('入力の打ち間違い', '開き括弧の後ろ', '夜は早く寝ます', '雨が降り始めた', 'しょくじちゅう', 'かんごしまち'):
            r = self.run_line(line)
            self.assertEqual((r['corrected'], r['odd_spans'], r['unsure_spans']), (line, [], []), line)

    def test_lone_katakana_letter_between_kana_is_marked(self):
        r = self.run_line('今日は雨が降るラはい')
        # IME の対がある PC では行の広い紫に含まれることもある
        self.assertTrue(any(a <= 7 and 8 <= b for a, b in r['odd_spans']), r['odd_spans'])

    def test_katakana_letters_in_terms_are_not_marked(self):
        for line in ('イ形容詞とナ形容詞', '名詞（サ変）を選ぶ', 'そうだよネ', '3ヶ月ぶり'):
            r = self.run_line(line)
            self.assertEqual(r['odd_spans'], [], line)


if __name__ == '__main__':
    unittest.main()
