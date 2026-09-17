# -*- coding: utf-8 -*-
"""A dictionary alternative must retain the same word and its actual attachment."""
import unittest
from unittest.mock import patch
import morphology as M


def changed(token, **fields):
    values={name:getattr(token,name) for name in token.__slots__}
    values.update(fields)
    return M.Token(**values)


class NativeAdverbialTests(unittest.TestCase):
    def setUp(self):
        M._native_adverbial_noun.cache_clear()

    def tearDown(self):
        M._native_adverbial_noun.cache_clear()

    @staticmethod
    def entries(surface):
        return {'通り': (('名詞,副詞可能,*,*', '*', '通り', 'とおり'),),
                'どおり': (('名詞,副詞可能,*,*', '*', 'どおり', 'どおり'),),
                '明日': (('名詞,副詞可能,*,*', '*', '明日', 'あした'),)}.get(surface, ())

    def transform(self, tokens):
        with patch.object(M, 'dictionary_inflections', side_effect=self.entries):
            return M._contextualize_adverbial_nominals(tokens)

    def test_nominal_suffix_retains_its_original_fields_and_adds_native_role(self):
        tokens=[M.Token('予定','名詞','予定','よてい',0,2,True,'サ変接続'),
                M.Token('どおり','名詞','どおり','どおり',2,5,True,'接尾:一般'),
                M.Token('進め','動詞','進める','すすめ',5,7,True,'自立','連用形')]
        result=self.transform(tokens)
        self.assertEqual(result[1].pos_sub, '接尾:一般:副詞可能')
        for name in ('surface','pos','base_form','reading','start','end','has_reading','infl_form'):
            self.assertEqual(getattr(result[1],name),getattr(tokens[1],name))
        self.assertEqual(tokens[1].pos_sub,'接尾:一般')

    def test_rendaku_requires_an_attached_known_nominal(self):
        suffix=M.Token('通り','名詞','通り','どおり',2,4,True,'接尾:一般')
        verb=M.Token('進む','動詞','進む','すすむ',4,6,True,'自立','基本形')
        head=M.Token('予定','名詞','予定','よてい',0,2,True,'サ変接続')
        self.assertIn('副詞可能',self.transform([head,suffix,verb])[1].pos_sub)
        for prefix in ([],[M.Token('予定','名詞','予定','よてい',0,2,False,'一般')],
                       [M.Token('予定','名詞','予定','よてい',0,1,True,'一般')]):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.transform(prefix+[suffix,verb])[-2],suffix)

    def test_another_reading_is_not_evidence_for_this_word(self):
        noun=M.Token('明日','名詞','明日','みょうにち',0,2,True,'一般')
        verb=M.Token('行く','動詞','行く','いく',2,4,True,'自立','基本形')
        self.assertEqual(self.transform([noun,verb]),[noun,verb])

    def test_unknown_proper_spaced_and_nonpredicate_uses_are_untouched(self):
        base=M.Token('明日','名詞','明日','あした',0,2,True,'一般')
        verb=M.Token('行く','動詞','行く','いく',2,4,True,'自立','基本形')
        noun=M.Token('予定','名詞','予定','よてい',2,4,True,'サ変接続')
        rows=([changed(base,has_reading=False),verb],
              [changed(base,pos_sub='固有名詞:人名'),verb],
              [base,changed(verb,start=3,end=5)], [base,noun])
        for tokens in rows:
            with self.subTest(tokens=tokens):
                self.assertEqual(self.transform(tokens),tokens)

    def test_missing_dictionary_and_idempotence(self):
        tokens=[M.Token('明日','名詞','明日','あした',0,2,True,'一般'),
                M.Token('行く','動詞','行く','いく',2,4,True,'自立','基本形')]
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertEqual(M._contextualize_adverbial_nominals(tokens),tokens)
        M._native_adverbial_noun.cache_clear()
        result=self.transform(tokens)
        self.assertIn('副詞可能',result[0].pos_sub)
        self.assertEqual(self.transform(result),result)


if __name__=='__main__':
    unittest.main()
