# -*- coding: utf-8 -*-
"""Noun candidates share the same case roles as repaired predicates."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('戻る'),'requires native dictionary')
class CandidateCaseRoleTests(unittest.TestCase):
    def test_adjacent_intrusion_keeps_the_origin_before_return(self):
        import app
        from tests_analysis_async import initial
        state=initial()
        for source in ('も水戸に戻ります\t','もみとにもどります\t',
                       'もとにもどります\t'):
            with self.subTest(source=source):
                row=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(row['corrected'],'元に戻ります\t')
                self.assertEqual(row['odd_spans'],[])

    def test_return_destinations_and_other_cases_share_exact_predicate_roles(self):
        for noun,following,role,case in (
                ('もと','に戻ります','origin','に'),('元','へ帰ります','origin','へ'),
                ('図書館','に戻ります','place','に'),('学校','へ向かいます','place','へ'),
                ('友達','に話します','person','に'),('辞書','で調べます','reference','で'),
                ('資料','を読みます','text','を')):
            with self.subTest(noun=noun,following=following):
                proof=S.candidate_object_evidence(noun,following)
                self.assertIsNotNone(proof)
                self.assertIn(role,proof['shared_roles'])
                self.assertEqual(proof['case'],case)

    def test_later_quoted_or_unknown_predicates_do_not_supply_fit(self):
        for following in ('に。戻ります','に「戻ります」',
                          'に置いてから戻ります','にしらゆほます','ので戻ります'):
            with self.subTest(following=following):
                proof=S.candidate_object_evidence('元',following)
                self.assertFalse(proof and proof['shared_roles'])
        proof=S.candidate_object_evidence('身元','に戻ります')
        self.assertFalse(proof and proof['shared_roles'])
        self.assertFalse('origin' in S.nominal_roles('身元'))

    def test_initial_application_uses_return_meaning_and_preserves_normal_context(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        result=app.correct_line('も水戸に戻ります',a.store,input_method='kana',
            dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
        self.assertIn(result['corrected'],('もとに戻ります','元に戻ります'))
        self.assertEqual(result.get('odd_spans'),[])
        for text in ('もとに戻ります。','元に戻ります。','図書館へ戻ります。',
                     'これも水戸の名物です。','身元を確認します。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],
                                 '元に戻ります。' if text=='もとに戻ります。' else text)
                self.assertEqual(result.get('odd_spans'),[])

    def test_ambiguous_origin_retains_the_actual_destination_sense(self):
        import app
        from tests_analysis_async import initial
        for source,expected in (
                ('もとにかえります。','元に帰ります。'),
                ('もとに帰ります。','元に帰ります。'),
                ('元に帰ります。','元に帰ります。'),
                ('下に帰ります。','下に帰ります。')):
            with self.subTest(source=source):
                state=initial()
                row=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(row['corrected'],expected)
                self.assertEqual(row['odd_spans'],[])
                self.assertEqual(row['analysis_status'],'complete')

    def test_recipient_and_placement_keep_the_written_case_and_native_auxiliary(self):
        import reading_segments as R
        for text,cut,faces in (
                ('本を友人に貸しました',2,('本',)),('友人に本を貸しました',5,('本',)),
                ('机の上に書類を並べました',7,('書類',)),
                ('書類を机の上に並べました',3,('書類',)),
                ('先生に本を読んでもらいました',5,('本',)),
                ('友人に本を読んであげます',5,('本',)),
                ('薬を呑みました',2,('薬',))):
            with self.subTest(text=text):
                self.assertTrue(R.native_object_predicate_proof(text,cut,faces))
        # Missing positive meaning is not a declaration that the source
        # sentence is impossible; these must not borrow a homophone's case.
        for text,cut,faces in (
                ('本を友人に課しました',2,('本',)),
                ('本を友人に歌詞ました',2,('本',)),
                ('本をぷねらに貸しました',2,('本',))):
            with self.subTest(text=text):
                self.assertFalse(R.native_object_predicate_proof(text,cut,faces))

    def test_written_action_survives_narrow_and_whole_clause_attachment_repairs(self):
        from contextual_repair import changed_native_action_attachment_allowed
        source='友人を招待して話ました。'
        for old,new,allowed in (('話','話し',True),('話','放し',False),
                               ('話ました','話しました',True),
                               ('話ました','放しました',False),
                               (source,'友人を招待して話しました。',True),
                               (source,'友人を招待して放しました。',False)):
            with self.subTest(old=old,new=new):
                start=source.index(old)
                self.assertEqual(changed_native_action_attachment_allowed(
                    source,start,start+len(old),new),allowed)
        source='友人と話しました。'
        self.assertTrue(changed_native_action_attachment_allowed(source,3,5,'放し'))

    def test_original_written_polite_mismatch_cannot_become_a_reading_only_intact(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (('本を友人に歌詞ました。','本を友人に貸しました。'),
                              ('友人を招待して話ました。','友人を招待して話しました。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',
                    dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])
        for text in ('薬を呑みました。','子どもに宿題を課しました。',
                     '先生に本を読んでもらいました。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])

        # The unknown reference still has baseline purple. Preserve its
        # text here; the local comparison reports that unresolved purple
        # separately instead of declaring it a source-protection success.
        text='ぷねらに本を貸しました。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],text)




    def test_written_completed_clause_owns_its_object_before_a_later_bad_head(self):
        import reading_segments as R
        import contextual_repair as CR
        for prefix in ('友人を招待して','資料を保存したが',
                       '資料を保存したので','資料を保存するから'):
            source=prefix+'話ました'
            self.assertIn(len(prefix),R.native_completed_clause_boundaries(source),source)
            self.assertIsNone(CR._source_object_predicate_frame(source,len(prefix),len(source)),source)
            self.assertFalse(R.native_object_predicate_contexts(source),source)
        self.assertFalse(R.native_completed_clause_boundaries('患者を保存して話ました'))
        for text in ('本を友人に男子ました','資料を沿うて男子ました'):
            self.assertTrue(R.native_object_predicate_contexts(text),text)
            self.assertFalse(R.native_object_predicate_cuts(text),text)
        for text in ('本を友人に貸しました','本を友人に田中ました','本をぷねらに男子ました'):
            self.assertFalse(R.native_object_predicate_contexts(text),text)

    def test_indirect_written_mismatch_stops_bad_candidate_without_losing_other_clauses(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        # An adjacent intrusion is now attested for the whole そうてだんし
        # reading. The actual schedule object supports consultation; the
        # other contexts still cannot borrow that action's meaning.
        text='旅行の日程を沿うて男子ました。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],'旅行の日程を相談しました。')
        self.assertFalse(result.get('odd_spans'))
        for text in ('資料を沿うて男子ました。','本を友人に男子ました。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertTrue(result.get('odd_spans'),text)
        for text,expected in (
                ('本を友人に歌詞ました。','本を友人に貸しました。'),
                ('机の上に書類を並べ背ました。','机の上に書類を並べました。'),
                ('友人を招待して話ました。','友人を招待して話しました。'),
                ('資料を保存したが話ました。','資料を保存したが話しました。')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result.get('odd_spans'),text)

    def test_previous_unclassified_meaning_does_not_supply_a_later_predicate_object(self):
        import reading_segments as R
        import app
        from tests_analysis_async import initial
        a=initial()
        for prefix in ('患者を保存して','計画を熟考して','動画を編集して'):
            text=prefix+'話ました。'
            self.assertIn(len(prefix),R.native_predicate_link_boundaries(text,3),text)
            self.assertFalse(R.native_object_predicate_contexts(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],prefix+'話しました。')
        # Argument ownership is not proof of the complete source's meaning.
        self.assertFalse(R.native_completed_clause_boundaries('患者を保存して話ました'))
        self.assertFalse(R.native_predicate_link_boundaries('資料を沿うて男子ました',3))
        self.assertTrue(R.native_object_predicate_contexts('資料を沿うて男子ました'))

    def test_completed_source_seam_keeps_the_full_original_conflict(self):
        import reading_segments as R
        import app
        from tests_analysis_async import initial
        a=initial()
        text='騒動を収集して事情を説明します。'
        self.assertTrue(R._native_written_predicate_conflicts(text))
        self.assertFalse(R.native_completed_clause_boundaries(text))
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],'騒動を収拾して事情を説明します。')
        self.assertFalse(result.get('odd_spans'))
        normal='資料を収集して事情を説明します。'
        self.assertFalse(R._native_written_predicate_conflicts(normal))
        self.assertIn(len('資料を収集して'),R.native_completed_clause_boundaries(normal))
        # The first completed normal clause still ends before a later anomaly.
        later='資料を保存して騒動を収集します。'
        self.assertIn(len('資料を保存して'),R.native_completed_clause_boundaries(later))
        # Ownership can be known without calling an unclassified first clause intact.
        self.assertTrue(R.native_predicate_link_boundaries('患者を保存して話ました',3))
        self.assertFalse(R.native_completed_clause_boundaries('患者を保存して話ました'))

if __name__=='__main__':unittest.main()
