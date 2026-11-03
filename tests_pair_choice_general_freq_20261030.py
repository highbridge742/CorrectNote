"""語の組の段は、一般の文でよく使う名詞（改行・位置）を例文に組が無いだけで替えない（2026-10-30・補正担当。例文は作った文）"""
import unittest
import pair_choice as P


class PairChoiceGeneralFreqTests(unittest.TestCase):
    def test_common_technical_nouns_kept(self):
        for line in ('段落の終わりで改行したい', '画面の右上の位置へ移った'):
            self.assertEqual(P.propose(line), [], line)

    def test_rare_homophone_still_marked(self):
        self.assertTrue(P.propose('友達に変心を書く'))


if __name__ == '__main__':
    unittest.main()
