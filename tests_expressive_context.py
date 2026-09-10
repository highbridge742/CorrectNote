# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import morphology as M
import corrector as C

class ExpressiveContextTests(unittest.TestCase):
    def tokens(self,word='フワー',known=False,predpos='形容詞',gap=0):
        n=len(word)
        return [M.Token(word,'名詞',word,word,0,n,known,'一般'),
                M.Token('と','助詞','と','と',n,n+1,True,'並立助詞'),
                M.Token('明るい',predpos,'明るい','あかるい',n+1+gap,n+4+gap,True,'自立')]

    def test_phonetic_form_and_predicate_restore_adverb(self):
        for word in ('ピュー','フワー','スー','ピタッ'):
            out=M._contextualize_expressive_adverbs(self.tokens(word))
            self.assertEqual(out[0].pos_sub,'擬音文脈')
            self.assertFalse(out[0].has_reading)
            self.assertEqual(out[0].surface,word)
            self.assertEqual(out[1].pos_sub,'格助詞:一般')

    def test_known_noun_long_word_and_missing_predicate_not_reclassified(self):
        with patch.object(M,'dictionary_base_pos',return_value=None):
            for toks in (self.tokens('シャワー',True),self.tokens('キーボード'),
                         self.tokens(predpos='名詞'),self.tokens(gap=1)):
                self.assertEqual(M._contextualize_expressive_adverbs(toks),toks)

    def test_adjectival_noun_requires_dictionary_evidence(self):
        toks=self.tokens(predpos='名詞')
        with patch.object(M,'dictionary_base_pos',return_value={'名詞,形容動詞語幹,*,*'}):
            out=M._contextualize_expressive_adverbs(toks)
        self.assertEqual(out[0].pos_sub,'擬音文脈')
        self.assertEqual(out[2].pos_sub,'形容動詞語幹')

    def test_chunk_uses_source_context_not_another_occurrence(self):
        # 公開テストには引用ではなく、この検査のために作った例文を使う。
        source='移動フワーと軽快'
        toks=[('移動','名詞:サ変接続','いどう',0,2,True,''),
              ('フワー','副詞:擬音文脈','ふわー',2,5,False,'')]
        key=C._CORRECTION_SOURCE.set(source)
        try:
            self.assertTrue(C._chunk_is_intact('移動フワー',lambda x:toks))
        finally:C._CORRECTION_SOURCE.reset(key)

if __name__=='__main__':unittest.main()
