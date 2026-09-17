# -*- coding: utf-8 -*-
"""Conversion and repairs retain the native grammatical suffix of the input."""
import unittest
from unittest.mock import patch
import corrector as C
import contextual_repair as CR
import morphology as M
import oddness as O
import reading_segments as R
import semantic_roles as S
from tests_native_phrase_context import tokens


class PredicateConversionTests(unittest.TestCase):
    def setUp(self):
        S.classified_nominal_action.cache_clear()
        # These tests replace the native dictionary/tokenizer, so every
        # cached reading proof must belong to the same synthetic fixture.
        # Prior real-dictionary application tests must not supply evidence.
        for value in vars(R).values():
            clear=getattr(value,'cache_clear',None)
            if clear and getattr(value,'__module__',None)==R.__name__:clear()
        CR._productive_predicate.cache_clear()
        CR._modern_te_allowed.cache_clear()

    def tearDown(self):
        self.setUp()

    def completed(self,text,head_pos='名詞,サ変接続,*,*',reading='せんたく',finite=True):
        def entries(surface):
            return {
                '選択':((head_pos,'*','選択',reading),),
                'し':(('動詞,自立,*,*','連用形','する','し'),),
                'ます':(('助動詞,*,*,*','基本形','ます','ます'),),
            }.get(surface,())
        parts=[M.Token('選択','名詞','選択','せんたく',0,2,True,'サ変接続'),
               M.Token('し','動詞','する','し',2,3,True,'自立','連用形'),
               M.Token('ます','助動詞','ます','ます',3,5,True,'','基本形' if finite else '連用形')]
        if text.endswith('し'):
            parts=parts[:2]
        with patch.object(C,'table_surfaces_for_reading',side_effect=lambda s,limit: ['選択'] if s=='せんたく' else []), \
             patch.object(M,'dictionary_inflections',side_effect=entries), \
             patch.object(M,'native_suru_form',side_effect=lambda sf,form,rd,*args:(sf,form,rd)==('し','連用形','し')), \
             patch.object(M,'tokenize',return_value=parts):
            return R.completed_sahen_reading(text)

    def test_native_action_reading_with_unchanged_finite_suffix_is_complete(self):
        self.assertTrue(self.completed('せんたくします'))

    def test_unclassified_ordinary_noun_or_wrong_reading_does_not_prove_suru(self):
        # Ordinary POS alone is insufficient; independent action knowledge
        # is a separate positive source introduced in 48-AGH.
        with patch.object(S,'classified_nominal_action',return_value=False):
            self.assertFalse(self.completed('せんたくします',head_pos='名詞,一般,*,*'))
        self.setUp()
        self.assertFalse(self.completed('せんたくします',reading='せんたくし'))

    def test_classified_ordinary_action_reuses_finite_suffix(self):
        self.assertTrue(self.completed('せんたくします',head_pos='名詞,一般,*,*'))

    def test_unfinished_native_form_or_malformed_tail_is_not_completion(self):
        self.assertFalse(self.completed('せんたくします',finite=False))
        self.setUp()
        self.assertFalse(self.completed('せんたくし'))
        self.assertFalse(self.completed('せんたくしたます'))

    def test_no_native_dictionary_does_not_invent_a_positive_answer(self):
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertFalse(R.completed_sahen_reading('せんたくします'))

    def test_old_compound_repair_reaches_common_completion_before_search(self):
        with patch.object(C,'_chunk_is_intact',return_value=True) as entry:
            self.assertIsNone(C._fix_known_head_compound('せんたくしません',None,lambda _:[],None))
        entry.assert_called_once()

    def test_old_word_pair_conversion_reaches_common_completion_before_lookup(self):
        with patch.object(C,'_chunk_is_intact',return_value=True) as entry, \
             patch.object(C,'make_tokenizer',return_value=lambda _:[]):
            self.assertEqual(C._kana_run_hand_fixes('せんたくしました。',None,dict_index=object()),[])
        entry.assert_called_once()

    def test_shared_structural_check_uses_affected_range_and_original_options(self):
        with patch.object(O,'is_odd_run',return_value=[('x','reason',3,5)]) as check:
            self.assertFalse(O.structural_anomaly_in_range('abcdef',0,3,None))
            self.assertTrue(O.structural_anomaly_in_range('abcdef',2,4,None))
        self.assertTrue(check.call_args.kwargs['skip_join'])
        self.assertTrue(check.call_args.kwargs['complete_line'])

    @staticmethod
    def bound_entries(surface):
        return {
            'し':(('動詞,自立,*,*','連用形','する','し'),),
            '直し':(('動詞,非自立,*,*','連用形','直す','なおし'),
                   ('動詞,自立,*,*','連用形','直す','なおし')),
            '読み':(('動詞,自立,*,*','連用形','読む','よみ'),),
            '読み直し':(('動詞,自立,*,*','連用形','読み直す','よみなおし'),),
        }.get(surface,())

    def test_unchanged_bound_verb_cannot_become_independent_after_a_noun(self):
        original=tokens([('選択','名詞:サ変接続','せんたく'),('し','動詞:自立','し','連用形'),
                         ('直し','動詞:非自立','なおし','連用形')])
        changed=tokens([('選択肢','名詞:一般','せんたくし'),('直し','動詞:自立','なおし','連用形')])
        with patch.object(M,'dictionary_inflections',side_effect=self.bound_entries):
            self.assertFalse(O.preserves_bound_verb('選択し直し',3,'選択肢直し',3,
                lambda text: original if text=='選択し直し' else changed))
            self.assertTrue(O.preserves_bound_verb('選択し直し',3,'選択し直し',3,lambda _:original))

    def test_native_compound_may_integrate_the_unchanged_suffix_into_one_verb(self):
        original=tokens([('読み','動詞:自立','よみ','連用形'),('直し','動詞:非自立','なおし','連用形')])
        integrated=tokens([('読み直し','動詞:自立','よみなおし','連用形')])
        with patch.object(M,'dictionary_inflections',side_effect=self.bound_entries):
            results=iter((original,integrated))
            self.assertTrue(O.preserves_bound_verb('読み直し',2,'読み直し',2,
                lambda _:next(results)))

    def test_missing_native_form_leaves_the_bound_verb_constraint_unproven(self):
        parts=tokens([('し','動詞:自立','し','連用形'),('直し','動詞:非自立','なおし','連用形')])
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertTrue(O.preserves_bound_verb('し直し',1,'肢直し',1,lambda _:parts))

    def test_common_te_completion_obeys_the_same_native_euphony_as_candidates(self):
        parts=tokens([('さい','動詞:自立','さい','連用タ接続'),
                      ('で','助詞:接続助詞','で'),('いか','動詞:非自立','いか','未然形')])
        with patch.object(CR,'_modern_te_allowed',return_value=False):
            self.assertFalse(C._chunk_is_intact('さいでいか',lambda _:parts))
        with patch.object(CR,'_modern_te_allowed',return_value=True):
            self.assertTrue(C._chunk_is_intact('さいでいか',lambda _:parts))

    def clause(self,case='を',unknown=False,noun=True,shift=False):
        text='がぞう'+case+'ほぞんします'
        def entries(surface):
            return {
                '画像':(('名詞,一般,*,*','*','画像','がぞう'),) if noun else (),
                'を':(('助詞,格助詞,一般,*','*','を','を'),),
                'の':(('助詞,格助詞,一般,*','*','の','の'),
                     ('助詞,連体化,*,*','*','の','の')),
            }.get(surface,())
        if unknown:
            original=[M.Token(text,'名詞',text,text,0,len(text),False,'一般')]
        else:
            original=[M.Token('がぞう','名詞','がぞう','がぞう',0,3,True,'一般'),
                      M.Token(case,'助詞',case,case,4 if shift else 3,5 if shift else 4,True,
                              '連体化' if case=='の' else '格助詞:一般')]
        def tokenize(s):
            if s==text:return original
            if s=='画像'+case:
                return [M.Token('画像','名詞','画像','がぞう',0,2,True,'一般'),
                        M.Token(case,'助詞',case,case,2,3,True,
                                '連体化' if case=='の' else '格助詞:一般')]
            return []
        with patch.object(R,'completed_sahen_reading',side_effect=lambda s,**kwargs:s=='ほぞんします'), \
             patch.object(C,'table_surfaces_for_reading',side_effect=lambda s,limit:['画像'] if s=='がぞう' else []), \
             patch.object(M,'dictionary_inflections',side_effect=entries), \
             patch.object(M,'tokenize',side_effect=tokenize):
            return R.completed_native_reading_clause(text)

    def test_native_noun_reading_and_original_nominal_case_form_a_clause(self):
        self.assertTrue(self.clause())

    def test_known_adnominal_no_does_not_borrow_a_dictionary_nominative_sense(self):
        self.assertFalse(self.clause(case='の'))

    def test_unknown_swallowed_case_is_checked_after_the_proven_native_noun(self):
        self.assertTrue(self.clause(unknown=True))
        self.setUp()
        self.assertFalse(self.clause(case='の',unknown=True))

    def test_missing_native_noun_or_wrong_source_case_coordinates_do_not_prove_clause(self):
        self.assertFalse(self.clause(noun=False))
        self.setUp()
        self.assertFalse(self.clause(shift=True))

    def test_modern_native_support_is_independent_of_classical_homograph_order(self):
        modern=('動詞,自立,*,*','サ変・スル','連用形','する','し')
        classical=('動詞,自立,*,*','文語・サ変','連用形','す','し')
        for forms in ((modern,classical),(classical,modern)):
            CR._modern_te_allowed.cache_clear()
            with patch.object(M,'dictionary_paradigms',return_value=forms):
                self.assertIs(CR._modern_te_allowed('し','し','た'),True)

    def test_unclassified_homograph_remains_unjudged_when_no_modern_proof_exists(self):
        modern=('動詞,自立,*,*','サ変・スル','連用形','する','し')
        classical=('動詞,自立,*,*','文語・サ変','連用形','す','し')
        for forms in ((classical,),(modern,classical),(classical,modern)):
            CR._modern_te_allowed.cache_clear()
            with patch.object(M,'dictionary_paradigms',return_value=forms):
                self.assertIsNone(CR._modern_te_allowed('し','し','だ'))
        CR._modern_te_allowed.cache_clear()
        with patch.object(M,'dictionary_paradigms',return_value=(modern,)):
            self.assertIs(CR._modern_te_allowed('し','し','だ'),False)

    def test_unclassified_euphony_cannot_certify_positive_functional_completion(self):
        parts=tokens([('が','助詞:格助詞:一般','が'),('し','動詞:自立','し','連用形'),
                      ('た','助動詞','た','基本形')])
        for answer in (None,False,True):
            with patch.object(M,'dictionary_inflections',side_effect=lambda word: {
                    'し':(('動詞,自立,*,*','連用形','する','し'),),
                    'た':(('助動詞,*,*,*','基本形','た','た'),),
                 }.get(word,())), \
                 patch.object(CR,'_modern_te_allowed',return_value=answer), \
                 patch.object(CR,'_allows_grammatical_tail',return_value=True), \
                 patch.object(CR,'_productive_predicate',return_value=True):
                self.assertEqual(R._native_nominal_functional_tail(parts),answer is True)


    def explicit_case_tail(self,case='を',head='み',lemma='みる',native=True,explicit=True):
        parts=tokens([(case,'助詞:格助詞:一般',case),(head,'動詞:自立',head,'連用形'),
                      ('ます','助動詞','ます','基本形')])
        def entries(word):
            return {
                head:(('動詞,自立,*,*','連用形',lemma,head),) if native else (),
                lemma:(('動詞,自立,*,*','基本形',lemma,lemma),),
                'ます':(('助動詞,*,*,*','基本形','ます','ます'),),
            }.get(word,())
        with patch.object(M,'dictionary_inflections',side_effect=entries), \
             patch.object(CR,'_allows_grammatical_tail',return_value=True), \
             patch.object(CR,'_productive_predicate',return_value=True):
            return R._native_nominal_functional_tail(parts,explicit_nominal_case=explicit)

    def test_explicit_native_nominal_case_can_complete_a_one_kana_basic_stem(self):
        self.assertTrue(self.explicit_case_tail())
        self.assertFalse(self.explicit_case_tail(explicit=False))
        self.assertTrue(self.explicit_case_tail(case='が',head='い',lemma='いる'))

    def test_accusative_completion_requires_a_basic_verb_with_that_case_frame(self):
        self.assertFalse(self.explicit_case_tail(head='あり',lemma='ある'))
        self.assertFalse(self.explicit_case_tail(head='い',lemma='いる'))
        self.assertTrue(self.explicit_case_tail(head='つかい',lemma='つかう'))

    def test_unknown_stem_does_not_gain_a_native_lemma_from_its_reading(self):
        self.assertFalse(self.explicit_case_tail(native=False))

    def test_actual_nominal_case_is_not_a_sequence_of_incompatible_cases(self):
        text='こぶんがをみます'
        parts=tokens([('こぶん','名詞:一般','こぶん'),('が','助詞:格助詞:一般','が'),
                      ('を','助詞:格助詞:一般','を'),('み','動詞:自立','み','連用形'),
                      ('ます','助動詞','ます','基本形')])
        def entries(word):
            return (('助詞,格助詞,一般,*','*',word,word),) if word in ('が','を') else ()
        with patch.object(M,'dictionary_inflections',side_effect=entries), \
             patch.object(R,'_native_nominal_reading_faces',side_effect=lambda rd:('古文',) if rd=='こぶん' else ()), \
             patch.object(R,'native_adnominal_reading_parts',return_value=()), \
             patch.object(R,'_native_nominal_functional_tail',return_value=True) as completion:
            self.assertFalse(R.native_nominal_reading_context(text,0,len(text),lambda _:parts))
            completion.assert_not_called()

