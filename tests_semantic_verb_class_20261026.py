"""分類語彙表の動詞（用の類）で語の組を借りる（semantic_class.verb_codes・2026-10-26）。例はすべて作ったもの。"""
import unittest

import collocation_repair as R
import semantic_class as S


class VerbClassBorrowTest(unittest.TestCase):
    def test_verb_codes_loaded(self):
        self.assertTrue(S.verb_codes('食べる'))
        self.assertFalse(S.verb_codes('あいうえ'))

    def test_table_verb_keeps_its_own_nouns(self):
        self.assertIn(('を', '洗う'), R.table()[1])
        self.assertTrue(S.pv_classes('を', '洗う'))

    def test_verb_outside_table_borrows_same_class(self):
        self.assertNotIn(('を', '記す'), R.table()[1])
        self.assertTrue(S.pv_classes('を', '記す'))
        self.assertTrue(S._shares('手紙', 'を', '記す'))
        self.assertFalse(S._shares('林檎', 'を', '記す'))

    def test_unknown_verb_borrows_nothing(self):
        self.assertFalse(S.pv_classes('を', 'あいうえる'))


if __name__ == '__main__':
    unittest.main()
