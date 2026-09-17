# -*- coding: utf-8 -*-
"""Known lexical grammar is tied to the original spelling, reading and coordinates."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import corrector as C


def tokens(items):
    out=[];edge=0
    for item in items:
        surface,pos,reading=item[:3]
        out.append((surface,pos,reading,edge,edge+len(surface),
                    item[4] if len(item)>4 else True,item[3] if len(item)>3 else ''))
        edge+=len(surface)
    return out


def entries(surface):
    return {
        'じょうせき':(('名詞,一般,*,*','*','じょうせき','じょうせき'),),
        'について':(('助詞,格助詞,連語,*','*','について','について'),),
        'の':(('助詞,連体化,*,*','*','の','の'),),
        'と':(('助詞,格助詞,引用,*','*','と','と'),),
        'を':(('助詞,格助詞,一般,*','*','を','を'),),
        'はい':(('感動詞,*,*,*','*','はい','はい'),),
        'ささやか':(('名詞,形容動詞語幹,*,*','*','ささやか','ささやか'),),
        'な':(('助動詞,*,*,*','体言接続','だ','な'),),
        '小さ':(('形容詞,自立,*,*','ガル接続','小さい','ちいさ'),),
        '静か':(('名詞,形容動詞語幹,*,*','*','静か','しずか'),),
        'さ':(('名詞,接尾,特殊,*','*','さ','さ'),),
    }.get(surface,())


class NativePhraseContextTests(unittest.TestCase):
    def phrase(self,parts):
        text=''.join(t[0] for t in parts)
        with patch.object(M,'dictionary_inflections',side_effect=entries):
            return R.native_lexical_phrase(text,lambda _:parts)

    def test_native_noun_and_its_particle_are_one_completed_phrase(self):
        head=('じょうせき','名詞:一般','じょうせき')
        for tail in ([],[('について','助詞:格助詞:連語','について')],
                     [('の','助詞:連体化','の')]):
            self.assertTrue(self.phrase(tokens([head]+tail)))

    def test_unknown_proper_name_and_different_native_reading_are_not_ordinary_noun_proof(self):
        for head in (('未知','名詞:一般','じょうせき'),
                     ('じょうせき','名詞:固有名詞:人名','じょうせき'),
                     ('じょうせき','名詞:一般','じょうせん'),
                     ('じょうせき','名詞:一般','じょうせき','',False)):
            self.assertFalse(self.phrase(tokens([head])))

    def test_coordinates_and_dictionary_absence_do_not_invent_completion(self):
        part=tokens([('じょうせき','名詞:一般','じょうせき')])
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertFalse(R.native_lexical_phrase('じょうせき',lambda _:part))
        shifted=[part[0][:3]+(1,6)+part[0][5:]]
        self.assertFalse(self.phrase(shifted))

    def test_interjection_is_quoted_but_not_reclassified_as_an_ordinary_object(self):
        head=('はい','感動詞','はい')
        self.assertTrue(self.phrase(tokens([head,('と','助詞:格助詞:引用','と')])))
        self.assertFalse(self.phrase(tokens([head,('を','助詞:格助詞:一般','を')])))

    def test_adnominal_na_requires_the_same_native_na_adjective(self):
        parts=tokens([('ささやか','名詞:形容動詞語幹','ささやか'),
                      ('な','助動詞','な','体言接続')])
        self.assertTrue(self.phrase(parts))
        def ordinary(surface):
            if surface=='ささやか':return (('名詞,一般,*,*','*','ささやか','ささやか'),)
            return entries(surface)
        with patch.object(M,'dictionary_inflections',side_effect=ordinary):
            self.assertFalse(R.native_lexical_phrase('ささやかな',lambda _:parts))

    def test_genitive_at_window_head_remains_bound_to_the_original_noun(self):
        body=tokens([('じょうせき','名詞:一般','じょうせき'),('について','助詞:格助詞:連語','について')])
        full=tokens([('説明','名詞:サ変接続','せつめい'),('の','助詞:連体化','の'),
                     ('じょうせき','名詞:一般','じょうせき'),('について','助詞:格助詞:連語','について')])
        source='説明のじょうせきについて'
        def tokenizer(text):return full if text==source else body
        with patch.object(M,'dictionary_inflections',side_effect=entries):
            self.assertTrue(R.native_genitive_context(source,2,len(source),tokenizer))
            self.assertFalse(R.native_genitive_context(source,3,len(source),tokenizer))
            self.assertFalse(R.native_genitive_context('のじょうせきについて',0,10,tokenizer))

    def test_nominalized_adjective_can_begin_before_the_kana_window(self):
        parts=tokens([('小さ','形容詞:自立','ちいさ','ガル接続'),
                      ('さ','名詞:接尾:特殊','さ'),('について','助詞:格助詞:連語','について')])
        with patch.object(M,'dictionary_inflections',side_effect=entries), \
             patch('pos_grammar.explain_kana_run',return_value=True):
            self.assertTrue(R.nominalized_adjective_context('小ささについて',1,7,lambda _:parts))
            self.assertTrue(R.nominalized_adjective_context('小ささについて',0,3,lambda _:parts))
            self.assertFalse(R.nominalized_adjective_context('小ささについて',3,7,lambda _:parts))

    def test_wrong_inflection_is_not_saved_by_two_adjacent_sa(self):
        for pos,form in (('動詞:自立','ガル接続'),('形容詞:自立','連用形')):
            parts=tokens([('小さ',pos,'ちいさ',form),('さ','名詞:接尾:特殊','さ')])
            with patch.object(M,'dictionary_inflections',side_effect=entries):
                self.assertFalse(R.nominalized_adjective_context('小ささ',1,3,lambda _:parts))

    def test_na_adjective_nominalization_requires_native_suffix_evidence(self):
        parts=tokens([('静か','名詞:形容動詞語幹','しずか'),('さ','名詞:接尾:特殊','さ')])
        with patch.object(M,'dictionary_inflections',side_effect=entries):
            self.assertTrue(R.nominalized_adjective_context('静かさ',0,3,lambda _:parts))
        def no_suffix(surface):return () if surface=='さ' else entries(surface)
        with patch.object(M,'dictionary_inflections',side_effect=no_suffix):
            self.assertFalse(R.nominalized_adjective_context('静かさ',0,3,lambda _:parts))

    def test_kango_head_cannot_end_inside_a_known_original_kana_word(self):
        parts=tokens([('こんにちは','感動詞','こんにちは'),('という','助詞:格助詞:連語','という')])
        with patch.object(C,'_convert_odd_kana_run',return_value=('今日はという',4)), \
             patch.object(C,'kana_is_mentioned',return_value=False), \
             patch.object(C,'_is_quoted_whole',return_value=False), \
             patch('seed_japanese.is_unit',return_value=True), \
             patch.object(C,'_dakuten_rival_reading') as later:
            self.assertEqual(C._kango_kana_fixes('こんにちはという',object(),object(),lambda _:parts),[])
            later.assert_not_called()

    def test_kango_head_cannot_split_a_known_mixed_script_word(self):
        parts=tokens([('きちょう面','名詞:一般','きちょうめん')])
        with patch.object(C,'_convert_odd_kana_run',return_value=('貴重',4)), \
             patch.object(C,'kana_is_mentioned',return_value=False), \
             patch.object(C,'_is_quoted_whole',return_value=False), \
             patch('seed_japanese.is_unit',return_value=True), \
             patch.object(C,'_dakuten_rival_reading') as later:
            self.assertEqual(C._kango_kana_fixes('きちょう面',object(),object(),lambda _:parts),[])
            later.assert_not_called()


if __name__=='__main__':
    unittest.main()
