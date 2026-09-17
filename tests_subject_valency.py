# -*- coding: utf-8 -*-
"""Keep predicate meaning separate from its otherwise valid conjugation."""
import unittest
from unittest.mock import patch
import morphology as M
import semantic_roles as S


class SubjectValencyTests(unittest.TestCase):
    def setUp(self):
        # These span tests provide a native サ変 fixture independently of
        # the installed dictionary; exact paradigm identity has its own tests.
        native=patch.object(M,'native_suru_form',side_effect=lambda surface,form,reading,*args:
            any(base=='する' and f==form and rd==reading for pos,f,base,rd in self.forms(surface)))
        native.start();self.addCleanup(native.stop)

    @staticmethod
    def tokens(tail=()):
        return [('理由','名詞:一般','りゆう',0,2,True,''),
                ('を','助詞:格助詞:一般','を',2,3,True,''),
                ('絶命','名詞:サ変接続','ぜつめい',3,5,True,''),
                ('し','動詞:自立','し',5,6,True,'連用形')] + list(tail)

    @staticmethod
    def forms(surface):
        entries = {
            'し': ('動詞,自立,*,*','連用形','する','し'),
            'まし': ('助動詞,*,*,*','連用形','ます','まし'),
            'た': ('助動詞,*,*,*','基本形','た','た'),
            'ます': ('助動詞,*,*,*','基本形','ます','ます'),
        }
        return (entries[surface],) if surface in entries else ()

    def test_semantic_span_does_not_label_the_normal_suru_tail_as_broken(self):
        tail = [('まし','助動詞','まし',6,8,True,'連用形'),
                ('た','助動詞','た',8,9,True,'基本形'),
                ('。','記号:句点','。',9,10,True,'')]
        with patch.object(M,'dictionary_inflections',side_effect=self.forms):
            self.assertEqual(S.subject_only_predicate_spans('理由を絶命しました。',self.tokens(tail)),
                             [('理由','絶命',3,5)])

    def test_relative_and_subordinate_clauses_keep_object_attachment_open(self):
        for surface,pos in (('人','名詞:一般'),('て','助詞:接続助詞'),
                            ('から','助詞:格助詞'),('と','助詞:格助詞:引用'),
                            ('、','記号:読点')):
            tail=[(surface,pos,surface,6,6+len(surface),True,'')]
            with patch.object(M,'dictionary_inflections',side_effect=self.forms):
                self.assertEqual(S.subject_only_predicate_spans('理由を絶命し'+surface,self.tokens(tail)),[])

    def test_causative_and_passive_are_not_the_same_argument_frame(self):
        for surface,base in (('させ','させる'),('され','する')):
            parts=self.tokens()[:-1]+[(surface,'動詞:接尾',surface,5,7,True,'連用形')]
            # A causative changes the native lemma; a passive must be a native suffix.
            forms=(('動詞,接尾,*,*','連用形',base,surface),)
            if surface=='され':
                forms=(('動詞,自立,*,*','未然レル接続','する','さ'),)
            with patch.object(M,'dictionary_inflections',return_value=forms):
                self.assertEqual(S.subject_only_predicate_spans('理由を絶命'+surface,parts),[])

    def test_no_object_or_an_unknown_name_supplies_no_claim(self):
        for noun in (('理由','名詞:一般','りゆう',0,2,False,''),
                     ('理由','名詞:固有名詞','りゆう',0,2,True,'')):
            parts=[noun]+self.tokens()[1:]
            with patch.object(M,'dictionary_inflections',side_effect=self.forms):
                self.assertEqual(S.subject_only_predicate_spans('理由を絶命し',parts),[])
        parts=self.tokens()
        parts[1]=('が','助詞:格助詞:一般','が',2,3,True,'')
        with patch.object(M,'dictionary_inflections',side_effect=self.forms):
            self.assertEqual(S.subject_only_predicate_spans('理由が絶命し',parts),[])

    def test_native_dictionary_absence_is_no_evidence(self):
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertEqual(S.subject_only_predicate_spans('理由を絶命し',self.tokens()),[])

    def test_legacy_six_field_tokens_have_no_inflection_evidence(self):
        parts=[token[:6] for token in self.tokens()]
        with patch.object(M,'dictionary_inflections',side_effect=self.forms):
            self.assertEqual(S.subject_only_predicate_spans('理由を絶命し',parts),[])
            self.assertEqual(S.subject_only_predicate_spans('理由を絶命し',self.tokens()[:-1]+parts[-1:]),[])

    def test_incomplete_conjugation_does_not_assert_a_final_argument_scope(self):
        with patch.object(M,'dictionary_inflections',side_effect=self.forms):
            self.assertEqual(S.subject_only_predicate_spans('理由を絶命し',self.tokens()),[])
            tail=[('まし','助動詞','まし',6,8,True,'連用形')]
            self.assertEqual(S.subject_only_predicate_spans('理由を絶命しまし',self.tokens(tail)),[])

    def test_nominal_use_does_not_claim_the_predicate_frame(self):
        parts=self.tokens()[:-1]+[('の','助詞:連体化','の',5,6,True,'')]
        with patch.object(M,'dictionary_inflections',side_effect=self.forms):
            self.assertEqual(S.subject_only_predicate_spans('理由を絶命の',parts),[])

    def test_alternative_native_verb_sense_is_not_ruled_out(self):
        parts=self.tokens()[:2]+[('亡くなり','動詞:自立','なくなり',3,7,True,'連用形')]
        forms=(('動詞,自立,*,*','連用形','亡くなる','なくなり'),
               ('動詞,自立,*,*','連用形','別の動詞','なくなり'))
        with patch.object(M,'dictionary_inflections',return_value=forms):
            self.assertEqual(S.subject_only_predicate_spans('理由を亡くなり',parts),[])


if __name__ == '__main__':
    unittest.main()
