# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import morphology as M
import pos_grammar as P


class SmallVowelTests(unittest.TestCase):
    def setUp(self):
        M.colloquial_adjective_forms.cache_clear()
        self.addCleanup(M.colloquial_adjective_forms.cache_clear)

    def test_adjective_pos_is_restored_without_changing_surface_or_offsets(self):
        normal = [M.Token('寒い','形容詞','寒い','さむい',0,2,True,'自立','基本形')]
        original = [M.Token('寒','名詞','寒','かん',0,1), M.Token('ぃ','名詞','ぃ','',1,2,False)]
        with patch.object(M,'HAS_JANOME',True), patch.object(M,'_tokenize_janome',return_value=normal):
            out=M._restore_colloquial_adjectives('寒ぃ',original)
        self.assertEqual([(t.surface,t.pos,t.start,t.end,t.reading) for t in out],
                         [('寒ぃ','形容詞',0,2,'さむい')])
        self.assertEqual([t.surface for t in original], ['寒','ぃ'])

    def test_unknown_or_nonadjective_is_not_promoted(self):
        for pos,known,infl in [('名詞',True,''),('形容詞',False,'基本形'),('形容詞',True,'連用形')]:
            M.colloquial_adjective_forms.cache_clear()
            tok=M.Token('寒い',pos,'寒い','さむい',0,2,known,'自立',infl)
            with patch.object(M,'HAS_JANOME',True), patch.object(M,'_tokenize_janome',return_value=[tok]):
                self.assertEqual(M.colloquial_adjective_forms('寒ぃ'), ())

    def test_no_dictionary_does_not_invent_evidence(self):
        with patch.object(M,'HAS_JANOME',False):
            self.assertEqual(M.colloquial_adjective_forms('寒ぃ'), ())

    def test_internal_small_vowels_are_not_all_normalized(self):
        tok=M.Token('かわいい','形容詞','かわいい','かわいい',0,4,True,'自立','基本形')
        with patch.object(M,'HAS_JANOME',True), patch.object(M,'_tokenize_janome',return_value=[tok]):
            self.assertEqual(M.colloquial_adjective_forms('かわぃぃ'), ())

    def test_no_small_vowel_avoids_extra_analysis(self):
        with patch.object(M,'colloquial_adjective_forms') as lookup:
            self.assertEqual(M._restore_colloquial_adjectives('寒い',[]),[])
            lookup.assert_not_called()

    def test_previous_character_alone_does_not_condemn_small_vowels(self):
        for vowel in 'ぁぃぅぇぉ':
            self.assertEqual(P.odd_kana_spans('字'+vowel), [])
        self.assertIn((0,2),P.odd_kana_spans('二ゅ力'))

    def test_literal_character_object_uses_text_action_context(self):
        for char in 'ぁぃぅぇぉ':
            src=[M.Token(char+'を','名詞',char+'を','',3,5,False),
                 M.Token('書く','動詞','書く','かく',5,7,True,'自立','基本形')]
            out=M._split_literal_character_objects(src)
            self.assertEqual([(t.surface,t.pos,t.start,t.end) for t in out],
                             [(char,'名詞',3,4),('を','助詞',4,5),('書く','動詞',5,7)])

    def test_literal_character_requires_local_and_known_text_predicate(self):
        first=M.Token('ぁを','名詞','ぁを','',0,2,False)
        for verb,start,known in [('食べる',2,True),('書く',3,True),('書く',2,False)]:
            src=[first,M.Token(verb,'動詞',verb,'',start,start+len(verb),known,'自立','基本形')]
            self.assertEqual(M._split_literal_character_objects(src),src)

    def test_known_word_is_not_resplit_as_a_character(self):
        src=[M.Token('ぁを','名詞','ぁを','ぁを',0,2,True),
             M.Token('書く','動詞','書く','かく',2,4,True,'自立','基本形')]
        self.assertEqual(M._split_literal_character_objects(src),src)

    def test_auxiliary_recovery_splits_unknown_tail_and_keeps_original(self):
        normal=[M.Token('よい','形容詞','よい','よい',0,2,True,'自立','基本形'),
                M.Token('でしょ','助動詞','です','でしょ',2,5,True,'','未然形'),
                M.Token('う','助動詞','う','う',5,6,True,'','基本形'),
                M.Token('か','助詞','か','か',6,7,True,'終助詞')]
        original=[normal[0],M.Token('でし','助動詞','です','でし',2,4),
                  M.Token('ょぅか','名詞','ょぅか','',4,7,False)]
        M.colloquial_auxiliary_forms.cache_clear()
        self.addCleanup(M.colloquial_auxiliary_forms.cache_clear)
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_janome',return_value=normal):
            out=M._restore_colloquial_auxiliaries('よいでしょぅか',original)
        self.assertEqual([(t.surface,t.pos,t.start,t.end) for t in out],
            [('よい','形容詞',0,2),('でしょ','助動詞',2,5),('ぅ','助動詞',5,6),('か','助詞',6,7)])
        self.assertEqual(out[2].reading,'う')
        self.assertEqual(original[-1].surface,'ょぅか')

    def test_auxiliary_requires_actual_inflection_and_bounded_ending(self):
        for first_pos,form,known,next_pos in (
                ('動詞','未然形',True,'助詞'),('助動詞','連用形',True,'助詞'),
                ('助動詞','未然形',False,'助詞'),('助動詞','未然形',True,'名詞'),
                ('助動詞','未然形',True,'動詞')):
            M.colloquial_auxiliary_forms.cache_clear()
            self.addCleanup(M.colloquial_auxiliary_forms.cache_clear)
            ts=[M.Token('でしょ',first_pos,'です','でしょ',0,3,known,'',form),
                M.Token('う','助動詞','う','う',3,4,True,'','基本形'),
                M.Token('か',next_pos,'か','か',4,5,True)]
            with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_janome',return_value=ts):
                self.assertEqual(M.colloquial_auxiliary_forms('でしょぅか'),())

    def test_auxiliary_unrelated_small_vowel_is_not_normalized(self):
        M.colloquial_auxiliary_forms.cache_clear()
        self.addCleanup(M.colloquial_auxiliary_forms.cache_clear)
        ts=[M.Token('ふう','名詞','ふう','ふう',0,2,True),
            M.Token('でしょ','助動詞','です','でしょ',2,5,True,'','未然形'),
            M.Token('う','助動詞','う','う',5,6,True,'','基本形')]
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_janome',return_value=ts):
            self.assertEqual(M.colloquial_auxiliary_normal_form('ふぅでしょぅ'),'ふぅでしょう')

    def test_auxiliary_no_small_vowel_or_no_dictionary_is_unchanged(self):
        M.colloquial_auxiliary_forms.cache_clear()
        self.addCleanup(M.colloquial_auxiliary_forms.cache_clear)
        with patch.object(M,'_tokenize_janome') as parse:
            self.assertEqual(M.colloquial_auxiliary_normal_form('そうでしょう'),'そうでしょう')
            parse.assert_not_called()
        with patch.object(M,'HAS_JANOME',False):
            self.assertEqual(M.colloquial_auxiliary_normal_form('そうでしょぅ'),'そうでしょぅ')


if __name__ == '__main__':
    unittest.main()
