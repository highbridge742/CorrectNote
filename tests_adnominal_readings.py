# -*- coding: utf-8 -*-
"""Native readings prove a modifier and noun without choosing output kanji."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import corrector as C
import morphology as M
import reading_segments as R


class AdnominalReadingTests(unittest.TestCase):
    def setUp(self):
        for fn in (R._native_nominal_reading_faces,R.native_adnominal_reading_parts,R.completed_native_reading,
                   R.completed_native_reading_clause,R.completed_sahen_reading):
            fn.cache_clear()

    def tearDown(self):
        self.setUp()

    def proof(self,text='しずかなしょるい',modifier='名詞,形容動詞語幹,*,*',
              noun='名詞,一般,*,*',reading='しょるい',copula=True,form='基本形'):
        faces={'しずか':['静か'],'しょるい':['書類'],'あたらしい':['新しい'],'ちいさな':['小さな']}
        entries={
            '静か':((modifier,'*','静か','しずか'),),
            '書類':((noun,'*','書類',reading),),
            'な':(('助動詞,*,*,*','体言接続','だ','な'),) if copula else (),
            '新しい':(('形容詞,自立,*,*',form,'新しい','あたらしい'),),
            '小さな':(('連体詞,*,*,*','*','小さな','ちいさな'),),
        }
        with patch.object(C,'table_surfaces_for_reading',side_effect=lambda s,limit:faces.get(s,[])), \
             patch.object(M,'dictionary_inflections',side_effect=lambda s:entries.get(s,())):
            return R.native_adnominal_reading_parts(text)

    def test_same_native_readings_cover_the_entire_nominal_phrase(self):
        parts=self.proof()
        self.assertEqual(''.join(p[4] for p in parts),'しずかなしょるい')
        self.assertEqual([p[0] for p in parts],['静か','な','書類'])

    def test_na_requires_both_an_adjectival_noun_and_its_native_copula(self):
        self.assertEqual(self.proof(modifier='名詞,一般,*,*'),())
        self.setUp()
        self.assertEqual(self.proof(copula=False),())

    def test_native_basic_adjective_and_adnominal_are_both_available(self):
        for text in ('あたらしいしょるい','ちいさなしょるい'):
            self.assertTrue(self.proof(text))

    def test_nonbasic_inflection_is_not_reinterpreted_as_an_adjective(self):
        self.assertEqual(self.proof('あたらしいしょるい',form='連用テ接続'),())

    def test_proper_names_suffixes_and_other_readings_are_not_noun_proof(self):
        for noun in ('名詞,固有名詞,人名,一般','名詞,接尾,一般,*','名詞,非自立,一般,*'):
            self.setUp()
            self.assertEqual(self.proof(noun=noun),())
        self.setUp()
        self.assertEqual(self.proof(reading='しゅるい'),())

    def test_unknown_tail_or_missing_copula_is_not_a_nominal_phrase(self):
        for text in ('しずかぬぉ','しずかしょるい','しずかなぬぉ',
                     'しずかなしょるいがを','しずかなしょるいします'):
            self.assertEqual(self.proof(text),(),text)

    def test_original_structural_anomaly_precedes_the_positive_reading_entry(self):
        target=SimpleNamespace(text='しずかなしょるい',structural=True,anomalies=((0,3),))
        with patch.object(R,'completed_native_reading',return_value=True) as proof:
            self.assertFalse(C._chunk_is_intact(target.text,lambda _:[],repair_context=target))
            proof.assert_not_called()


    def basic_clause(self,particle='が',case_sub='格助詞:一般',known=True,complete=True):
        text='しりょう'+particle+'あります'
        parts=[M.Token('しりょう','名詞','資料','しりょう',0,4,True,'一般'),
               M.Token(particle,'助詞',particle,particle,4,5,True,case_sub),
               M.Token('あり','動詞','ある','あり',5,7,known,'自立','連用形'),
               M.Token('ます','助動詞','ます','ます',7,9,True,'','基本形')]
        entries={'資料':(('名詞,一般,*,*','*','資料','しりょう'),),
                 particle:(('助詞,'+case_sub.replace(':',',')+',*','*',particle,particle),)}
        with patch.object(C,'table_surfaces_for_reading',side_effect=lambda s,limit:['資料'] if s=='しりょう' else []), \
             patch.object(M,'dictionary_inflections',side_effect=lambda s:entries.get(s,())), \
             patch.object(M,'tokenize',return_value=parts), \
             patch.object(R,'completed_sahen_reading',return_value=False), \
             patch.object(R,'_native_nominal_functional_tail',return_value=complete) as proof:
            result=R.completed_native_reading_clause(text)
            return result,proof

    def test_actual_nominative_tail_reuses_native_functional_completion(self):
        result,proof=self.basic_clause()
        self.assertTrue(result)
        tail=proof.call_args.args[0]
        self.assertEqual([t[0] for t in tail],['が','あり','ます'])
        self.assertEqual([t[3:5] for t in tail],[(4,5),(5,7),(7,9)])
        self.assertEqual([t[6] for t in tail],['','連用形','基本形'])

    def test_topic_uses_the_actual_original_particle(self):
        result,_=self.basic_clause(particle='は',case_sub='係助詞')
        self.assertTrue(result)

    def test_other_cases_and_clausal_homographs_do_not_assert_basic_completion(self):
        for particle,sub in (('の','連体化'),('が','接続助詞')):
            self.setUp()
            result,proof=self.basic_clause(particle=particle,case_sub=sub)
            self.assertFalse(result)
            proof.assert_not_called()

    def test_accusative_requires_shared_native_case_frame_proof(self):
        # AAB delegates the accusative/native basic-verb frame to the shared
        # tail proof. A mocked unconditional True no longer represents ある.
        # Real native accusative/intransitive contrasts are exercised below
        # and in the native smoke suite.
        result,proof=self.basic_clause(particle='を',complete=False)
        self.assertFalse(result)
        proof.assert_called()
        self.assertTrue(proof.call_args.kwargs.get('explicit_nominal_case'))

    def test_unknown_predicate_or_shared_inflection_rejection_gives_no_completion(self):
        result,proof=self.basic_clause(known=False)
        self.assertFalse(result)
        proof.assert_not_called()
        self.setUp()
        result,proof=self.basic_clause(complete=False)
        self.assertFalse(result)
        proof.assert_called()


    def unknown_case(self,source_known=False,projected_known=True,projected_surface='あっ',punctuation=False):
        bare='しりょうがあった'
        source=bare+('。' if punctuation else '')
        def nominal_tail(offset,head):
            return [M.Token(head,'名詞','資料','しりょう',0,offset,True,'一般'),
                    M.Token('が','助詞','が','が',offset,offset+1,True,'格助詞:一般'),
                    M.Token(projected_surface,'動詞','ある',projected_surface,offset+1,offset+3,
                            projected_known,'自立','連用タ接続'),
                    M.Token('た','助動詞','た','た',offset+3,offset+4,True,'','基本形')]
        original=[M.Token(bare,'名詞',bare,bare,0,len(bare),source_known,'一般')]
        if punctuation:
            original=nominal_tail(4,'しりょう')+[M.Token('。','記号','。','。',len(bare),len(source),True,'句点')]
        def tokenize(text):
            if text==source:return original
            if text=='資料が':return nominal_tail(2,'資料')[:2]
            if text=='資料があった':return nominal_tail(2,'資料')
            return []
        entries={'資料':(('名詞,一般,*,*','*','資料','しりょう'),),
                 'が':(('助詞,格助詞,一般,*','*','が','が'),)}
        with patch.object(C,'table_surfaces_for_reading',side_effect=lambda s,limit:['資料'] if s=='しりょう' else []), \
             patch.object(M,'dictionary_inflections',side_effect=lambda s:entries.get(s,())), \
             patch.object(M,'tokenize',side_effect=tokenize) as tokenizer, \
             patch.object(R,'completed_sahen_reading',return_value=False), \
             patch.object(R,'_native_nominal_functional_tail',return_value=True) as proof:
            result=R.completed_native_reading_clause(source)
            return result,proof,tokenizer

    def test_original_punctuation_is_kept_when_obtaining_case_and_inflection(self):
        result,proof,tokenizer=self.unknown_case(punctuation=True)
        self.assertTrue(result)
        self.assertIn(('しりょうがあった。',),[call.args for call in tokenizer.call_args_list])
        self.assertNotIn(('しりょうがあった',),[call.args for call in tokenizer.call_args_list])
        self.assertEqual([t[0] for t in proof.call_args.args[0]],['が','あっ','た'])

    def test_proven_unknown_case_reconstructs_only_the_unchanged_suffix_and_offsets(self):
        result,proof,_=self.unknown_case()
        self.assertTrue(result)
        tail=proof.call_args.args[0]
        self.assertEqual(''.join(t[0] for t in tail),'があった')
        self.assertEqual([t[3:5] for t in tail],[(4,5),(5,7),(7,8)])

    def test_known_source_word_cannot_be_split_by_unknown_case_fallback(self):
        result,proof,_=self.unknown_case(source_known=True)
        self.assertFalse(result)
        proof.assert_not_called()

    def test_reconstructed_unknown_or_altered_suffix_is_not_positive_evidence(self):
        result,proof,_=self.unknown_case(projected_known=False)
        self.assertFalse(result)
        proof.assert_not_called()
        self.setUp()
        result,proof,_=self.unknown_case(projected_surface='なっ')
        self.assertFalse(result)
        proof.assert_not_called()


    def test_native_adjective_role_must_be_independent_and_basic(self):
        for pos,form in (('形容詞,接尾,*,*','基本形'),('形容詞,非自立,*,*','基本形'),
                         ('形容詞,自立,*,*','文語基本形')):
            self.assertFalse(M.native_independent_adjective(pos,form,'よい'))
        for lemma in ('いい','よい','ええ','こい','すい','うい','ない'):
            self.assertTrue(M.native_independent_adjective('形容詞,自立,*,*','基本形',lemma))

    def test_unverified_native_adjective_entry_is_not_a_new_word_boundary(self):
        self.assertFalse(M.native_independent_adjective('形容詞,自立,*,*','基本形','くい'))
        self.assertFalse(M.native_independent_adjective('動詞,自立,*,*','連用形','くう'))

    def test_original_first_known_word_cannot_be_cut_into_a_shorter_modifier(self):
        crossed=M.Token('しずかなし','接続詞','しずかなし','しずかなし',0,5,True)
        with patch.object(M,'tokenize',return_value=[crossed]):
            self.assertEqual(self.proof(),())

    def test_later_accidental_fragment_does_not_override_whole_modifier_proof(self):
        first=M.Token('し','名詞','し','し',0,1,True,'一般')
        crossed=M.Token('ずかなし','形容詞','ずかなし','ずかなし',1,5,True,'自立','文語基本形')
        with patch.object(M,'tokenize',return_value=[first,crossed]):
            self.assertTrue(self.proof())

    def test_native_predicate_homograph_needs_case_context_not_all_demonstratives(self):
        def entries(word):
            return {
                'ある':(('連体詞,*,*,*','*','ある','ある'),
                        ('動詞,自立,*,*','基本形','ある','ある')),
                'この':(('連体詞,*,*,*','*','この','この'),),
                '書類':(('名詞,一般,*,*','*','書類','しょるい'),),
            }.get(word,())
        with patch.object(C,'table_surfaces_for_reading',side_effect=lambda s,limit:['書類'] if s=='しょるい' else []), \
             patch.object(M,'dictionary_inflections',side_effect=entries), \
             patch.object(M,'tokenize',return_value=[]):
            self.assertEqual(R.native_adnominal_reading_parts('あるしょるい'),())
            self.assertTrue(R.native_adnominal_reading_parts('あるしょるい',allow_predicative=True))
            self.assertTrue(R.native_adnominal_reading_parts('このしょるい'))


if __name__=='__main__':
    unittest.main()
