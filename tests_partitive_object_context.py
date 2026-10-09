# -*- coding: utf-8 -*-
"""Explicit subsets keep their original noun, case, and predicate evidence."""
import copy,unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class PartitiveObjectContextTests(unittest.TestCase):
    def test_owned_native_subset_uses_existing_roles(self):
        for source,face in (('本の残りを数える。','残り'),('資料の残部を読む。','残部'),
                            ('水の一部を飲む。','一部'),('資料の部分を読む。','部分'),
                            ('紙の部分を読む。','部分')):
            with self.subTest(source=source):
                edge=source.index('を')+1
                self.assertTrue(R._native_partitive_object_projections(source,edge,(face,)))
                self.assertTrue(R.native_object_predicate_proof(source,edge,(face,)))
        self.assertEqual(S.nominal_roles('残り'),frozenset(('partitive',)))

    def test_unproved_existing_left_meaning_is_not_invented(self):
        # The current role data do not establish reading the material paper.
        # The subset relation must not manufacture the missing text sense.
        self.assertFalse(S.nominal_role_matches('紙',S.predicate_roles('読む')))
        self.assertFalse(R.native_object_predicate_proof('紙を読む。',2,('紙',)))
        source='紙の残りを読む。';edge=source.index('を')+1
        self.assertTrue(R._native_partitive_object_projections(source,edge,('残り',)))
        self.assertFalse(R.native_object_predicate_proof(source,edge,('残り',)))

    def test_unchanged_native_particle_coordinates_are_required(self):
        source='本の残りを数える。';edge=source.index('を')+1
        original=M.tokenize(source)
        probe=R._native_partitive_object_projections.__wrapped__
        for i in (1,3):
            for field,value in (('has_reading',False),('reading','べつ'),('start',original[i].start+1)):
                modified=list(original);modified[i]=copy.copy(original[i]);setattr(modified[i],field,value)
                with self.subTest(i=i,field=field),patch('morphology.tokenize',return_value=modified):
                    self.assertFalse(probe(source,edge,('残り',)))
        with patch('semantic_roles.genitive_nominal_support',return_value=False):
            self.assertFalse(probe(source,edge,('残り',)))
        for position in (edge-1,edge+1,len(source)):
            self.assertFalse(probe(source,position,('残り',)))

    def test_partitive_and_whole_noun_belong_to_this_source(self):
        for source,face in (('本の残部を数える。','残り'),('本の居間を数える。','残り'),
                            ('残りを数える。','残り'),('未知語の残りを数える。','残り'),
                            ('本の\t残りを数える。','残り'),('本の、残りを数える。','残り'),
                            ('本\t残りを数える。','残り'),('本。残りを数える。','残り'),
                            ('「本」の残りを数える。','残り')):
            with self.subTest(source=source,face=face):
                edge=source.index('を')+1
                self.assertFalse(R._native_partitive_object_projections(source,edge,(face,)))
        self.assertFalse(R.native_object_predicate_proof('本の残部を数える。',5,('残り',)))

    def test_actual_predicate_and_complete_tail_keep_common_validation(self):
        for source in ('本の残りを食べる。','食事の残りを読む。','水の残りを読む。',
                       '本の残りを数え','本の残りを数えますだ。','本の残りを数得る。'):
            with self.subTest(source=source):
                edge=source.index('を')+1
                self.assertTrue(R._native_partitive_object_projections(source,edge,('残り',)))
                self.assertFalse(R.native_object_predicate_proof(source,edge,('残り',)))
        self.assertFalse(R._native_partitive_object_projections('本の残りに数える。',5,('残り',)))

    def test_temporal_link_retains_boolean_and_action_modes(self):
        for whole,subset,face in (('本を読んでから','本の残りを読んでから','本'),
                                   ('資料をよんでから','資料の残りをよんでから','資料')):
            whole_edge=whole.index('を')+1;subset_edge=subset.index('を')+1
            with self.subTest(subset=subset):
                self.assertTrue(R.native_object_predicate_proof(whole,whole_edge,(face,),allow_link=True))
                self.assertTrue(R.native_object_predicate_proof(subset,subset_edge,('残り',),allow_link=True))
                self.assertFalse(R.native_object_predicate_proof(subset,subset_edge,('残り',)))
                # The existing action API does not claim an action for a
                # temporal link alone; projection must keep that contract.
                self.assertFalse(R.native_object_predicate_proof(whole,whole_edge,(face,),allow_link=True,return_action=True))
                self.assertFalse(R.native_object_predicate_proof(subset,subset_edge,('残り',),allow_link=True,return_action=True))

    def test_same_source_and_candidate_reach_shared_final_gate(self):
        import corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            for source in ('本ののこりを数える。','資料ののこりを数える。'):
                start=source.index('のこり')
                accepted,reason=C._check_replacement(source,(start,start+3,'残り','かな入力'),a.store,tok,a.dict_index,a.decisions,
                    spelling=True,conv_taken=[(start,start+3)])
                self.assertEqual(accepted,(start,start+3,'残り','かな入力'))
                self.assertEqual(reason,'accepted')
            for source in ('のこりを数える。','本ののこりを食べる。','食事ののこりを読む。'):
                start=source.index('のこり')
                accepted,reason=C._check_replacement(source,(start,start+3,'残り','かな入力'),a.store,tok,a.dict_index,a.decisions,
                    spelling=True,conv_taken=[(start,start+3)])
                self.assertIsNone(accepted)
                self.assertEqual(reason,'unproven_original_object_predicate')
        finally:set_active(None)

    def test_runtime_spellings_retain_explicit_context_in_both_initial_states(self):
        import analysis_worker
        from tests_analysis_async import initial
        from last_choice import set_active
        from janome_import import import_from_janome
        try:
            for fresh in (False,True):
                a=initial()
                if fresh:import_from_janome(a.store)
                revision=a.store.revision()
                runtime=analysis_worker.Runtime();runtime.set_state(analysis_worker.snapshot(a))
                sources=('本ののこりを数える。','資料ののこりを数える。')
                context=runtime.execute(dict(kind='prepare',lines=sources))
                for source in sources:
                    result=runtime.execute(dict(kind='line',line=source,input_method='kana',
                        context=context['context'],attested=context['attested']))['result']
                    self.assertEqual(result['corrected'],source.replace('のこり','残り'))
                    self.assertEqual(result['analysis_status'],'complete')
                    self.assertFalse(result['odd_spans'])
                self.assertEqual(a.store.revision(),revision)
        finally:set_active(None)

    def test_neighbors_and_literal_input_do_not_supply_a_missing_whole(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        try:
            for source in ('本の残りを数える。\tのこりを数える。',
                           'のこりを数える。\t本の残りを数える。',
                           '本を数える。のこりを数える。',
                           '「本ののこりを数える」と入力します。',
                           '「本ののこりを数える」という文字列です。'):
                with self.subTest(source=source):
                    result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                            context_vec=None,decisions=a.decisions)
                    self.assertEqual(result['corrected'],source)
                    self.assertEqual(result['analysis_status'],'complete')
                    self.assertFalse(result['odd_spans'])
        finally:set_active(None)


if __name__=='__main__':unittest.main()
