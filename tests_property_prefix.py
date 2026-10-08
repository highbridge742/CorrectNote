# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock,patch
import oddness as O

class PropertyPrefixTests(unittest.TestCase):
    def tokens(self,head='主',body='同調',offset=0):
        return [(head,'接頭詞:名詞接続','しゅ',offset,offset+1,True,''),
                (body,'名詞:サ変接続','どうちょう',offset+1,offset+3,True,''),
                ('性','名詞:接尾:一般','せい',offset+3,offset+4,True,'')]

    def test_unbacked_ranked_property_is_marked(self):
        with patch.object(O,'_load',return_value={'文章'}):
            self.assertEqual(O.ranked_property_prefix_spans('主同調性',self.tokens()),[('主','同調性',0,4)])

    def test_original_position_is_retained_after_separator(self):
        with patch.object(O,'_load',return_value={'文章'}):
            self.assertEqual(O.ranked_property_prefix_spans(' 主同調性を',self.tokens(offset=1)),
                             [('主','同調性',1,5)])

    def test_existing_base_or_whole_is_preserved(self):
        for words in ({'主同調'},{'主同調性'},{'副同調'}):
            with patch.object(O,'_load',return_value=words):
                self.assertEqual(O.ranked_property_prefix_spans('主同調性',self.tokens()),[])

    def test_other_complete_word_boundary_is_preserved(self):
        with patch.object(O,'_load',return_value={'主従','属性'}):
            self.assertEqual(O.ranked_property_prefix_spans('主従属性',self.tokens(body='従属')),[])

    def test_dictionary_compound_proves_prefix_and_cache_tracks_resource(self):
        for words,expected in (({'副交感神経系'},[]),({'主交感神経系'},[]),({'文章'},[('副','交感性',0,4)])):
            with patch.object(O,'_load',return_value=words):
                self.assertEqual(O.ranked_property_prefix_spans('副交感性',self.tokens('副','交感')),expected)

    def test_larger_compound_and_spacing_are_not_cut(self):
        with patch.object(O,'_load',return_value={'文章'}):
            for text,toks in (('主同調性因子',self.tokens()),('低主同調性',self.tokens(offset=1)),
                              ('主 同調性',self.tokens())):
                self.assertEqual(O.ranked_property_prefix_spans(text,toks),[])

    def test_solid_surface_evidence_preserves_personal_term(self):
        for surface in ('主同調','主同調性'):
            store=Mock();store.lookup.return_value=[{'surface':surface,'solid':True}]
            with patch.object(O,'_load',return_value={'文章'}):
                self.assertEqual(O.ranked_property_prefix_spans('主同調性',self.tokens(),store),[])

    def test_no_resources_or_unconfirmed_part_of_speech_does_not_assert(self):
        with patch.object(O,'_load',return_value=None):
            self.assertEqual(O.ranked_property_prefix_spans('主同調性',self.tokens()),[])
        with patch.object(O,'_load',return_value={'文章'}):
            for pos,known in (('名詞:一般',True),('名詞:サ変接続',False)):
                ts=self.tokens();t=ts[1];ts[1]=(t[0],pos,t[2],t[3],t[4],known,'')
                self.assertEqual(O.ranked_property_prefix_spans('主同調性',ts),[])


    def test_whole_source_prefix_belongs_to_derived_nominal_range(self):
        import morphology as M,reading_segments as R
        if not M.HAS_JANOME:self.skipTest('native dictionary')
        for source in ('主同調性','主同調性を変更する'):
            self.assertNotIn((1,4),R.native_written_nominal_ranges(source))
            self.assertTrue(R.preserves_native_written_derivation(source,source.replace('主同調性','手動調整')))
        for word in ('同調性','補正付き','編集者'):
            self.assertIn((0,len(word)),R.native_written_nominal_ranges(word))
            self.assertFalse(R.preserves_native_written_derivation(word,word[1:]))
            self.assertTrue(R.preserves_native_written_derivation(word+'を確認します',word+'を確認しました'))

    def test_whole_property_repair_keeps_ci_source_and_common_gate(self):
        import morphology as M,corrector as C
        if not M.HAS_JANOME:self.skipTest('native dictionary')
        from vocabulary import VocabularyStore,find_known_readings_flex
        from seed_vocabulary import load_seed
        from janome_import import import_from_janome
        from dict_index import DictIndex
        store=VocabularyStore();load_seed(store);import_from_janome(store)
        tok=C.make_tokenizer(store);idx=DictIndex(cache_path=None);idx.ensure_built()
        for source,expected in (('主同調性','手動調整'),('主同調性を変更する','手動調整を変更する'),
                                ('副交感性','副交感性'),('主作用性','主作用性'),
                                ('主従属性','主従属性'),('主導性','主導性')):
            with self.subTest(source=source):
                value=C.correct_line(source,store,tok,find_known_readings_flex,input_method='kana',dict_index=idx)
                self.assertEqual(value['corrected'],expected)
                self.assertEqual(value['odd_spans'],[])
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            value=C.correct_line('主同調性',store,tok,find_known_readings_flex,input_method='kana',dict_index=idx)
        self.assertEqual(value['corrected'],'主同調性')
        self.assertTrue(value['odd_spans'])

    def test_native_compound_merge_retains_original_affix_witnesses(self):
        import morphology as M
        if not M.HAS_JANOME:self.skipTest('native dictionary')
        for text,expected in (('主同調性',[('主','同調性',0,4)]),
                              ('副交感性',[]),('主作用性',[]),('主従属性',[])):
            tokens=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
                    for t in M.tokenize(text)]
            self.assertEqual(O.ranked_property_prefix_spans(text,tokens),expected,text)

if __name__=='__main__':unittest.main()
