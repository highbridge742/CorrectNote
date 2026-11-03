"""意味の分類の表を文字列で持っても、引いた答えの形は同じ（2026-10-30・補正担当）"""
import unittest
import semantic_class as S


class SemanticClassCompactTests(unittest.TestCase):
    def test_shapes(self):
        self.assertIsInstance(S.codes('返事'), frozenset)
        self.assertEqual(S.codes('存在しない見出し語'), frozenset())
        self.assertIsInstance(S.words_read('てんき'), tuple)
        self.assertEqual(S.words_read('存在しない読み'), ())
        self.assertIsInstance(S.verb_codes('飲む'), frozenset)

    def test_stored_as_strings(self):
        words = S._data()[0]
        self.assertTrue(all(isinstance(v, str) for v in list(words.values())[:100]))


if __name__ == '__main__':
    unittest.main()
