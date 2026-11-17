"""2026-11-17: ローマ字入力の語の組の直しを戻さない・決まった言い方・宣言した補正の引用（作った例）。"""
import os
import unittest

import dict_word_keep as K
import literal_examples as L


def _result(line, new, src, dst):
    return {'corrected': new, 'changed': True, 'details': [(src, dst, '語の組')]}


class SetPhraseFrame(unittest.TestCase):
    def test_head_noun_before_itasu(self):
        self.assertTrue(K._set_phrase_frame('恐縮いたします。', 0, 2))
        self.assertTrue(K._set_phrase_frame('はい、恐縮です。', 3, 5))

    def test_inside_clause_not(self):
        self.assertFalse(K._set_phrase_frame('大きな恐縮です。', 3, 5))

    def test_switch_off(self):
        os.environ['CN_DICT_WORD_KEEP_SET_PHRASE'] = '0'
        try:
            self.assertFalse(K._set_phrase_frame('恐縮いたします。', 0, 2))
        finally:
            del os.environ['CN_DICT_WORD_KEEP_SET_PHRASE']


class RomajiPairKept(unittest.TestCase):
    line = '週末の買い物の予定を書く。'
    new = '週末の会い物の予定を書く。'

    def test_kana_may_revert(self):
        r = K.keep(self.line, _result(self.line, self.new, '買い物', '会い物'), input_method='kana')
        self.assertIn(r['corrected'], (self.line, self.new))

    def test_romaji_keeps(self):
        r = K.keep(self.line, _result(self.line, self.new, '買い物', '会い物'), input_method='romaji')
        self.assertEqual(r['corrected'], self.new)

    def test_wrapper_reads_input_method(self):
        seen = {}
        orig = K._orig.get('correct_line')
        K._orig['correct_line'] = lambda line, *a, **k: _result(line, self.new, '買い物', '会い物')
        old_keep = K.keep
        K.keep = lambda line, result, input_method='kana': seen.setdefault('im', input_method) and result
        try:
            K.correct_line(self.line, None, None, None, 'romaji')
            self.assertEqual(seen['im'], 'romaji')
        finally:
            K.keep = old_keep
            if orig is None:
                K._orig.pop('correct_line', None)
            else:
                K._orig['correct_line'] = orig


class DeclaredCorrection(unittest.TestCase):
    def test_declared_source_side_open(self):
        line = '「漢字の便秘」は「漢字の変換」に補正します。'
        self.assertEqual(L.protected_ranges(line), [(9, 14)])

    def test_wrong_correction_report_both_kept(self):
        line = '「漢字の便秘」は「漢字の変換」に誤補正されました。'
        self.assertEqual(L.protected_ranges(line), [(1, 6), (9, 14)])
        line = '「漢字の便秘」が「漢字の変換」に変換された例'
        self.assertEqual(L.protected_ranges(line), [(1, 6), (9, 14)])

    def test_switch_off(self):
        os.environ['CN_CHANGE_REPORT_DECLARED'] = '0'
        try:
            line = '「漢字の便秘」は「漢字の変換」に補正します。'
            self.assertEqual(L.protected_ranges(line), [(1, 6), (9, 14)])
        finally:
            del os.environ['CN_CHANGE_REPORT_DECLARED']


if __name__ == '__main__':
    unittest.main()
