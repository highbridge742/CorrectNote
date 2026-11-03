"""普通の名詞を解析が固有名詞と読んでも、普通の名詞としてつながるなら紫にしない（2026-10-30・補正担当。例文は作った文）"""
import unittest
import oddness


class ProperNounCommonJoinTests(unittest.TestCase):
    def test_common_pos_of_dual_word(self):
        self.assertIn('名詞:副詞可能', oddness._common_noun_pos('毎日'))

    def test_pure_proper_has_none(self):
        self.assertEqual(oddness._common_noun_pos('田中'), ())


if __name__ == '__main__':
    unittest.main()
