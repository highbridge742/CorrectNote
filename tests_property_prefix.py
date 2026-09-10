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

if __name__=='__main__':unittest.main()
