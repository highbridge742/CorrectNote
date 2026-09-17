"""Modern まい uses native conjugation and keeps the source auxiliary role."""
import unittest
from unittest.mock import patch
import morphology as M
import contextual_repair as R
import oddness as O


class MaiConnectionTests(unittest.TestCase):
    def tearDown(self):
        R._native_mai_connection.cache_clear()

    def check_form(self, kind, form, surface, expected, base='読む'):
        R._native_mai_connection.cache_clear()
        row=('動詞,自立,*,*',kind,form,base,surface)
        with patch.object(M,'dictionary_paradigms',return_value=(row,)):
            self.assertIs(R._native_mai_connection(surface,surface),expected)

    def test_godan_needs_finite_form(self):
        self.check_form('五段・マ行','基本形','よむ',True)
        self.check_form('五段・マ行','連用形','よみ',False)
        self.check_form('五段・マ行','未然形','よま',False)

    def test_ichidan_has_negative_stem_and_finite_forms(self):
        self.check_form('一段','基本形','とじる',True,'閉じる')
        self.check_form('一段','未然形','とじ',True,'閉じる')
        self.check_form('一段','命令ｒｏ','とじろ',False,'閉じる')

    def test_suru_and_kuru_variants(self):
        self.check_form('サ変・スル','基本形','する',True,'する')
        self.check_form('サ変・スル','未然形','し',True,'する')
        self.check_form('サ変・スル','文語基本形','す',True,'する')
        self.check_form('カ変・クル','体言接続特殊２','く',True,'くる')

    def test_unknown_and_other_reading_do_not_supply_proof(self):
        with patch.object(M,'dictionary_paradigms',return_value=()):
            self.assertIsNone(R._native_mai_connection('未知','みち'))
        R._native_mai_connection.cache_clear()
        row=('動詞,自立,*,*','五段・カ行','基本形','開く','あく')
        with patch.object(M,'dictionary_paradigms',return_value=(row,)):
            self.assertIsNone(R._native_mai_connection('開く','ひらき'))

    def test_actual_auxiliary_cannot_borrow_a_homographic_verb(self):
        rows=(('動詞,非自立,*,*','一段','体言接続特殊','る','ん'),
              ('助動詞,*,*,*','不変化型','基本形','ん','ん'))
        with patch.object(M,'dictionary_paradigms',return_value=rows):
            self.assertIsNone(R._native_mai_connection('ん','ん','助動詞'))
            self.assertFalse(R._native_mai_connection('ん','ん','動詞'))
        R._native_mai_connection.cache_clear()
        rows=(('動詞,自立,*,*','サ変・−スル','未然形','まする','まし'),
              ('助動詞,*,*,*','特殊・マス','連用形','ます','まし'))
        with patch.object(M,'dictionary_paradigms',return_value=rows):
            self.assertTrue(R._native_mai_connection('まし','まし','動詞'))
            self.assertFalse(R._native_mai_connection('まし','まし','助動詞'))

    def test_past_and_copula_do_not_take_mai(self):
        for surface,base in (('た','た'),('だ','だ'),('です','です'),('でし','です')):
            self._check_aux(surface,base,False)
        self._check_aux('ます','ます',True)
        self._check_aux('ある','ある',None)
        self._check_aux('ん','ん',None)

    def test_native_aru_auxiliary_can_take_mai(self):
        row=('助動詞,*,*,*','五段・ラ行アル','基本形','ある','ある')
        with patch.object(M,'dictionary_paradigms',return_value=(row,)):
            self.assertTrue(R._native_mai_connection('ある','ある','助動詞'))

    def _check_aux(self,surface,base,expected):
        R._native_mai_connection.cache_clear()
        row=('助動詞,*,*,*','*','基本形',base,surface)
        with patch.object(M,'dictionary_paradigms',return_value=(row,)):
            self.assertIs(R._native_mai_connection(surface,surface,'助動詞'),expected)

    def test_count_suffix_is_not_a_negative_auxiliary(self):
        a=('さん','名詞:数','さん',0,2,True,'')
        b=('まい','名詞:接尾:助数詞','まい',2,4,True,'')
        with patch.object(R,'_native_mai_connection',return_value=False) as connection:
            self.assertFalse(O.mai_aux_mismatch(a,b))
            connection.assert_not_called()


if __name__=='__main__':unittest.main()
