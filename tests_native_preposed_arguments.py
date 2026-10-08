# -*- coding: utf-8 -*-
"""Unchanged preposed arguments and their original object share one action."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R

@unittest.skipUnless(M.dictionary_inflections('先生'),'requires native dictionary')
class NativePreposedArgumentTests(unittest.TestCase):
    def test_topic_frame_shares_only_its_proved_whole_nominal_start(self):
        import kana_spelling as K
        from unittest.mock import patch
        source='教師はないようをかきます';members=set()
        self.assertIn((3,7),K._lexical_units(source,M.tokenize(source),members))
        self.assertIn((3,7),members)
        with patch.object(R,'native_preposed_object_parts',return_value=()):
            members=set();K._lexical_units(source,M.tokenize(source),members)
            self.assertNotIn((3,7),members)
        for source in ('ぷねらはないようをかきます','教師はないようをぷねらします'):
            start=source.index('ないよう');members=set()
            K._lexical_units(source,M.tokenize(source),members)
            self.assertNotIn((start,start+4),members)

    def test_topic_with_separate_object_keeps_its_actual_marker(self):
        for text,marker in (('教師はないようをかきます','は'),('講師もないようをよみます','も'),
                            ('学生達は内容を読みます','は')):
            parts=R.native_preposed_object_parts(text,True)
            self.assertTrue(parts,text)
            self.assertTrue(any(case==marker and edge==text.index(marker)+1
                and cut==text.index('を')+1 for edge,case,nouns,cut,objects in parts),text)
            self.assertTrue(any(R.native_object_predicate_proof(text,cut,objects)
                for edge,case,nouns,cut,objects in parts),text)
        for text in ('内容は先生が書きます','箱は内容をかきます','教師はりんごをよみます',
                     'ぷねらは内容をかきます','教師は内容をぷねらします','教師は内容をかきま',
                     '私ももじをかいています','教師の内容をかきます'):
            self.assertFalse(R.native_preposed_object_parts(text,True),text)

    def test_topic_object_frame_requires_source_marker_and_subject_support(self):
        import copy,semantic_roles as S
        from unittest.mock import patch
        source='教師はないようをかきます';parts=M.tokenize(source);tokenize=M.tokenize
        for field,value in (('has_reading',False),('pos_sub','格助詞:一般'),('reading','が'),('start',1),('end',4)):
            altered=[copy.copy(t) for t in parts];setattr(next(t for t in altered if t.start==2),field,value)
            with self.subTest(field=field),patch.object(M,'tokenize',side_effect=lambda text:
                    altered if text==source else tokenize(text)):
                self.assertFalse(R.native_preposed_object_parts.__wrapped__(source,True))
        support=S.proved_action_case_support
        # Broad topic support may include object roles; it cannot replace
        # the separate positive subject role required beside explicit wo.
        with patch.object(S,'proved_action_case_support',side_effect=lambda noun,case,action,**kwargs:
                False if case=='が' else support(noun,case,action,**kwargs)):
            self.assertFalse(R.native_preposed_object_parts.__wrapped__(source,True))
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertFalse(R.native_preposed_object_parts.__wrapped__(source,True))
        with patch.object(R,'native_nominal_case_boundary',return_value=None):
            self.assertFalse(R.native_preposed_object_parts.__wrapped__(source,True))

    def test_topic_whole_object_spelling_keeps_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        source='教師はないようをかきます。';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((replacement[2],result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):result=analyze(source)
            self.assertEqual(result['corrected'],'教師は内容を書きます。')
            self.assertEqual(result['odd_spans'],[]);self.assertEqual(result['analysis_status'],'complete')
            self.assertIn(('内容',True),seen);self.assertIn(('書き',True),seen)
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                self.assertEqual(analyze(source)['corrected'],source)
            quote='入力は「'+source+'」です。';self.assertEqual(analyze(quote)['corrected'],quote)
        finally:set_active(None)

    def test_nominative_boundary_does_not_lend_unproved_object_scope(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        for source in ('私達がぶんしょうをよみま','私達がぶんしょうをぷねらします'):
            changed=source[:3]+'文章'+source[8:]
            self.assertFalse(R.native_preposed_object_parts(changed,True),source)
        try:
            source='私達がぶんしょうをぷねらします。';a=initial()
            result=app.correct_line(source,a.store,input_method='kana',
                dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertEqual(result['odd_spans'],[(2,15)])
            self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_nominative_preposed_argument_keeps_the_whole_source_case(self):
        from unittest.mock import patch
        for text in ('私達がぶんしょうをよみます','私達が文章をよみます',
                     '先生が文章を読みます','私たちが本を読みました'):
            parts=R.native_preposed_object_parts(text,True)
            self.assertTrue(parts,text)
            self.assertTrue(any(case=='が' and edge==text.index('が')+1
                and cut==text.index('を')+1 for edge,case,faces,cut,objects in parts),text)
            self.assertTrue(any(R.native_object_predicate_proof(text,cut,objects)
                for edge,case,faces,cut,objects in parts),text)
        for text in ('ぷねらが文章を読みます','私 達が文章を読みます',
                     '私\t達が文章を読みます','私達がを読みます','私達が文章を'):
            self.assertFalse(R.native_preposed_object_parts(text,True),text)
        with patch.object(R,'native_nominal_case_boundary',return_value=None):
            self.assertFalse(R.native_preposed_object_parts.__wrapped__('私達が文章をよみます',True))

    def test_nominative_preposed_proof_keeps_both_meanings_and_finite_tail(self):
        import semantic_roles as S
        from unittest.mock import patch
        for text in ('箱が文章をよみます','私達がりんごをよみます',
                     '私達が文章をよみま','私達が文章をぷねらします'):
            frames=R.native_object_predicate_frames(text,True)
            self.assertFalse(any(R.native_object_predicate_proof(text,cut,faces)
                                 for cut,faces in frames),text)
        text='私達が文章をよみます';cut=text.index('を')+1
        with patch.object(S,'proved_action_case_support',return_value=False):
            self.assertFalse(R.native_object_predicate_proof.__wrapped__(text,cut,('文章',)))

    def test_nominative_object_spelling_preserves_common_final_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        source='私達がぶんしょうをよみます。';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs)
            seen.append((replacement[2],result[0] is not None))
            return result
        try:
            a=initial()
            with patch.object(C,'_check_replacement',side_effect=observed):
                result=app.correct_line(source,a.store,input_method='kana',
                    dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],'私達が文章を読みます。')
            self.assertEqual(result['odd_spans'],[])
            self.assertEqual(result['analysis_status'],'complete')
            self.assertIn(('文章',True),seen)
            self.assertIn(('読み',True),seen)
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                result=app.correct_line(source,a.store,input_method='kana',
                    dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            quote='入力は「私達がぶんしょうをよみます」です。';a=initial()
            result=app.correct_line(quote,a.store,input_method='kana',
                dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],quote)
        finally:set_active(None)

    def test_photo_fixture_keeps_horizontal_keys_and_the_old_direction_negative(self):
        import app,corrector as C,contextual_repair as Q,kana_layout as K
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        self.assertEqual(K.kana_key_distance('と','し'),1)
        self.assertTrue(any(r.reading=='しゃしん' and r.operation=='adjacent_substitution'
                            for r in Q.key_repairs('しゃとん')))
        for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                          Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
            self.assertNotIn('しゃしん',{r.reading for r in generator('しゃしま')})
        try:
            source='あしたまでにしゃしまをならべます。';a=initial()
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertTrue(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            source='あしたまでにしゃとんをならべます。';a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
        finally:set_active(None)



    def test_marked_member_uses_original_particle_and_whole_neighbor(self):
        import contextual_repair as Q,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            a=initial();tok=C.make_tokenizer(a.store)
            for source,start in (('書庫にゅ稿を保管します。',3),('ゅ稿と書類を並べます。',0)):
                with self.subTest(source=source):
                    targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
                    target=next(t for t in targets if t.text=='ゅ稿')
                    self.assertEqual((target.start,target.end),(start,start+2))
                    self.assertEqual(Q._lexical_syllable_start(target),start)
                    self.assertEqual(target.following,source[target.end:target.context_end])
                    self.assertTrue(any(x[2:]==(start,start+2) for x in target.anomalies))
            self.assertNotIn(3,Q._native_marked_prefix_edges('ぽねにゅ稿を保管します。'))
            source='ゅ稿とぽねを並べます。'
            self.assertFalse(any(t.text=='ゅ稿' for t in Q.targets_for_line(source,tok,a.store,a.dict_index)))
        finally:set_active(None)

    def test_marked_member_reaches_application_with_original_context(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            for source,expected in (('書庫にゅ稿を保管します。','書庫に手稿を保管します。'),
                                    ('ゅ稿と書類を並べます。','手稿と書類を並べます。')):
                with self.subTest(source=source):
                    a=initial()
                    result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_marked_member_preserves_normal_input_and_shared_rejection(self):
        import app,contextual_repair as Q,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        try:
            for source in ('書庫にゅ稿を保管します。','ゅ稿と書類を並べます。'):
                a=initial();tok=C.make_tokenizer(a.store)
                target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='ゅ稿')
                with patch.object(C,'_check_replacement',return_value=(None,'forced_common_rejection')) as gate:
                    selected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                    self.assertIsNone(selected);self.assertTrue(gate.called)
            for source in ('書庫に手稿を保管します。','手稿と書類を並べます。',
                           '「書庫にゅ稿を保管します」と入力します。','「ゅ稿と書類」と入力します。',
                           'ニュースを読みます。','資料の入力を確認します。'):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['odd_spans'],[])
        finally:set_active(None)

    def test_missing_prefix_keys_do_not_respelling_an_unchanged_written_noun(self):
        import contextual_repair as Q
        for original,reading,wrong,expected in (('ゅ稿','ゅこう','首肯','しゅこう'),
                ('ゅ給','ゅきゅう','守旧','しゅきゅう'),('ょ庫','ょこ','チョコ','ちょこ')):
            rd=Q.Reading(reading,'contextual_token_sequence',0)
            self.assertTrue(Q._omission_changes_unedited_nominal_tail(original,wrong,rd,expected))
        rd=Q.Reading('ゅきゅう','contextual_token_sequence',0)
        self.assertFalse(Q._omission_changes_unedited_nominal_tail('ゅ給','受給',rd,'じゅきゅう'))
        self.assertFalse(Q._omission_changes_unedited_nominal_tail('ゅ給','授業',rd,'じゅぎょう'))
        self.assertFalse(Q._omission_changes_unedited_nominal_tail('ゅ給','予約',rd,'よやく'))
        self.assertFalse(Q._omission_changes_unedited_nominal_tail('しゅ給','守旧',Q.Reading('しゅきゅう','native',0),'しゅきゅう'))

    def test_attested_whole_prefix_word_reaches_omission_candidate(self):
        import contextual_repair as Q,corrector as C,reading_segments as R,app
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            source='彼はょ字を練習しました。';a=initial();tok=C.make_tokenizer(a.store)
            target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='ょ字')
            self.assertIn('しょじ',R.native_attested_prefix_noun_readings('書字'))
            selected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
            rows={r['surface']:r for r in diag.get('candidates',())}
            self.assertIn('書字',rows)
            self.assertLess(rows['書字']['rank_evidence']['written_boundary'],0)
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
            self.assertEqual(result['corrected'],'彼は書字を練習しました。')
            self.assertEqual(result['odd_spans'],[])
        finally:set_active(None)

    def test_attested_prefix_generation_keeps_the_common_check(self):
        import contextual_repair as Q,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        try:
            a=initial();tok=C.make_tokenizer(a.store);source='彼はょ字を練習しました。'
            target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='ょ字')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_rejection')) as gate:
                selected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                self.assertIsNone(selected);self.assertTrue(gate.called)
            selected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
            self.assertTrue(all(row['surface'].endswith('字') for row in diag.get('candidates',())
                               if row['rank_evidence'].get('written_boundary',0)<0))
        finally:set_active(None)

    def test_attested_suffix_head_keeps_whole_source_identity(self):
        import reading_segments as R,semantic_roles as S,kango_tier as K
        from unittest.mock import patch
        before={word:(S.nominal_roles(word),K.known_usage_tier(word))
                for word in ('編集者','作業員')}
        for word in before:
            with self.subTest(word=word):
                self.assertEqual(R.native_written_derived_nominal_faces(word),(word,))
                self.assertEqual(R.native_surface_nominal_heads(word),(word,))
                self.assertEqual((S.nominal_roles(word),K.known_usage_tier(word)),before[word])
        R.native_written_derived_nominal_faces.cache_clear()
        try:
            with patch('seed_japanese.is_unit',return_value=None):
                self.assertEqual(R.native_written_derived_nominal_faces('編集者'),())
        finally:R.native_written_derived_nominal_faces.cache_clear()
        for word in ('石員','未知ぽね者','へんしゅうしゃ','編集者ます','編集者を'):
            with self.subTest(word=word):
                self.assertEqual(R.native_written_derived_nominal_faces(word),())

    def test_attested_suffix_head_reaches_marked_noun_without_giving_it_meaning(self):
        import app,contextual_repair as Q,corrector as C,semantic_roles as S
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            source='編集者はょ評を書きます。';a=initial();tok=C.make_tokenizer(a.store)
            targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
            target=next(t for t in targets if t.text=='ょ評')
            self.assertEqual((target.start,target.end),(4,6))
            self.assertEqual(Q._lexical_syllable_start(target),4)
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
            self.assertEqual(result['corrected'],'編集者は書評を書きます。')
            self.assertEqual(result['odd_spans'],[])
            self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

    def test_attested_suffix_keeps_common_gate_and_source_tail(self):
        import contextual_repair as Q,corrector as C,app
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        try:
            source='編集者はょ評を書きます。';a=initial();tok=C.make_tokenizer(a.store)
            target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='ょ評')
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_rejection')) as gate:
                selected,diagnosis=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                self.assertIsNone(selected)
                self.assertTrue(gate.called)
            for source in ('編集者は書評を書きます。','作業員は資料を読みます。',
                           '「編集者はょ評を書きます」と入力します。'):
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['odd_spans'],[])
        finally:set_active(None)

    def test_marked_noun_uses_independent_whole_prefix_boundary(self):
        import contextual_repair as Q,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            a=initial();tok=C.make_tokenizer(a.store)
            for source,raw in (('生徒はゅ語を探しました。','ゅ語'),
                               ('生徒はゅ業を受けます。','ゅ業'),
                               ('部品のゅ命を調べます。','ゅ命'),
                               ('端末はゅ信を開始します。','ゅ信'),
                               ('図書館はょ庫を整理しました。','ょ庫'),
                               ('確認済み。生徒はゅ語を探しました。','ゅ語'),
                               ('このょ名を読みます。','ょ名'),
                               ('そのゅ題を変えます。','ゅ題')):
                with self.subTest(source=source):
                    edge=source.index(raw)
                    targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
                    target=next(t for t in targets if t.text==raw)
                    self.assertIn(edge-target.context_start,Q._native_marked_prefix_edges(target.context))
                    self.assertEqual((target.start,target.end),(edge,edge+len(raw)))
                    self.assertEqual(Q._lexical_syllable_start(target),edge)
        finally:set_active(None)

    def test_marked_prefix_requires_an_intact_whole_head(self):
        import contextual_repair as Q
        for source in ('未知ぽねはゅ語を探します。','はゅ語を探します。',
                       '生徒は主語を探します。',
                       'しゅみを調べます。','資料を読むはゅ語'):
            with self.subTest(source=source):
                self.assertEqual(Q._native_marked_prefix_edges(source),())

    def test_marked_prefix_repair_reaches_application_and_common_check(self):
        import contextual_repair as Q,corrector as C,app,ime_language,ime_candidates
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                for source,raw,face in (('生徒はゅ語を探しました。','ゅ語','主語'),
                                        ('図書館はょ庫を整理しました。','ょ庫','書庫')):
                    with self.subTest(source=source):
                        a=initial();tok=C.make_tokenizer(a.store)
                        target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text==raw)
                        reading,repair,_=next(r for r in Q._whole_written_nominal_omissions(raw) if r[2]==face)
                        ok,reason=Q.validate(target,face,C,tok,a.store,a.dict_index,a.decisions,repair.reading,source_reading=reading)
                        self.assertTrue(ok,reason)
                        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                            self.assertEqual(Q.validate(target,face,C,tok,a.store,a.dict_index,a.decisions,repair.reading,source_reading=reading),(False,'test_reject'))
                        r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                        self.assertEqual(r['corrected'],source.replace(raw,face))
                        self.assertEqual(r['odd_spans'],[])
                        self.assertEqual(r['analysis_status'],'complete')
                for source in ('生徒は主語を探しました。','図書館は書庫を整理しました。',
                               '未知ぽねは資料を運びます。','「生徒はゅ語」と入力しました。'):
                    a=initial()
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],source)
                    self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_missing_prefix_keeps_the_written_tail_in_final_selection(self):
        import app,contextual_repair as Q,corrector as C,ime_language,ime_candidates
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                for source,expected,wrong,rd in (('彼女はゅ稿を保管します。','彼女は手稿を保管します。','首肯','しゅこう'),
                        ('彼女はゅ給を申請します。','彼女はゅ給を申請します。','守旧','しゅきゅう'),
                        ('彼はょ庫を整理しました。','彼は書庫を整理しました。','チョコ','ちょこ')):
                    with self.subTest(source=source):
                        a=initial();tok=C.make_tokenizer(a.store)
                        target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text in ('ゅ稿','ゅ給','ょ庫'))
                        tail={'ゅ稿':'こう','ゅ給':'きゅう','ょ庫':'こ'}[target.text]
                        reading=Q.Reading(target.text[0]+tail,'contextual_token_sequence',0)
                        ok,reason=Q.validate(target,wrong,C,tok,a.store,a.dict_index,a.decisions,rd,source_reading=reading)
                        self.assertEqual((ok,reason),(False,'unedited_written_nominal_tail'))
                        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                        self.assertEqual(result['corrected'],expected)
                        self.assertEqual(result['analysis_status'],'complete')
                        if expected==source:self.assertTrue(result['odd_spans'])
                        else:self.assertEqual(result['odd_spans'],[])
        finally:set_active(None)

    def test_missing_voiced_onset_keeps_both_physical_presses_and_source_shift(self):
        import contextual_repair as Q,kana_layout as K
        from unittest.mock import patch
        rows=Q._whole_written_nominal_omissions('ゅ給')
        reading,repair,face=next(row for row in rows if row[2]=='受給')
        self.assertEqual(reading.text,'ゅきゅう')
        self.assertEqual(repair.reading,'じゅきゅう')
        self.assertEqual(repair.operation,'marked_omission')
        self.assertEqual(repair.intended,'し゛')
        self.assertEqual(repair.cost,2*K.MISSING_KEY_COST)
        self.assertEqual([(s.position,s.pressed,s.intended) for s in repair.steps],[(0,'','し'),(0,'','゛')])
        source=tuple(k for c in reading.text for k in K.keystrokes(c))
        self.assertEqual(Q._render(tuple(repair.intended)+source),repair.reading)
        self.assertEqual(source[0],'ゅ')
        with patch.object(K,'mark_slip_enabled',return_value=False):
            self.assertEqual(Q._whole_written_nominal_omissions('ゅ給'),())
            self.assertTrue(any(f=='所見' for rd,r,f in Q._whole_written_nominal_omissions('ょ見')))
        for source in ('受給','じゅ給','ゆ給','ゅ稿','ゅ給です'):
            self.assertEqual(Q._whole_written_nominal_omissions(source),(),source)

    def test_marked_nominal_omission_still_needs_meaning_and_the_common_gate(self):
        import contextual_repair as Q,corrector as C,ime_language,ime_candidates
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        source='彼女はゅ給を申請します。'
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                a=initial();tok=C.make_tokenizer(a.store)
                target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='ゅ給')
                reading,repair,face=next(row for row in Q._whole_written_nominal_omissions(target.text) if row[2]=='受給')
                accepted,reason=Q.validate(target,face,C,tok,a.store,a.dict_index,a.decisions,repair.reading,source_reading=reading)
                self.assertTrue(accepted,reason)
                accepted,reason=Q.validate(target,'読み',C,tok,a.store,a.dict_index,a.decisions,'よみ',source_reading=reading)
                self.assertEqual((accepted,reason),(False,'unproven_whole_nominal_completion'))
                with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                    accepted,reason=Q.validate(target,face,C,tok,a.store,a.dict_index,a.decisions,repair.reading,source_reading=reading)
                self.assertEqual((accepted,reason),(False,'test_reject'))
                selected,diagnostic=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                self.assertGreater(diagnostic['rejected'].get('unproven_two_key_context',0),0)
                self.assertNotIn('受給',[r['surface'] for r in diagnostic['candidates']])
        finally:set_active(None)

    def test_whole_noun_reading_reaches_a_tail_without_forging_single_glyph_readings(self):
        import contextual_repair as Q
        before={x:M.dictionary_inflections(x) for x in ('見','斎')}
        for source,reading,expected in (('ょ見','しょけん','所見'),('ょ斎','しょさい','書斎')):
            rows=Q._whole_written_nominal_omissions(source)
            self.assertTrue(any(repair.reading==reading and face==expected for rd,repair,face in rows))
            for rd,repair,face in rows:
                self.assertEqual(rd.source,'native_nominal_completion')
                self.assertEqual(repair.operation,'omission')
                self.assertTrue(face.endswith(source[1:]))
        for source in ('所見','書斎','しょ見','ぽね','ょ見\t書見','ABC見','ょ見です'):
            self.assertEqual(Q._whole_written_nominal_omissions(source),(),source)
        # A matching beginning of the whole reading does not establish
        # its internal written boundary (ょ斎 is not 精進潔斎).
        for source,unproved in (('ょ斎','精進潔斎'),('ょ見','一寸見'),('ょ見','了見')):
            self.assertFalse(any(face==unproved for rd,repair,face in Q._whole_written_nominal_omissions(source)))
        for face,reading in (('見','うけん'),('斎','うじんけっさい'),('一寸','ちょ')):
            self.assertFalse(Q._native_written_reading_matches(face,reading))
        self.assertEqual(before,{x:M.dictionary_inflections(x) for x in before})

    def test_whole_noun_completion_is_bound_to_its_candidate_and_common_gate(self):
        import app,contextual_repair as Q,corrector as C,ime_language,ime_candidates
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                for source,expected in (('私はょ見を記録しました。','私は所見を記録しました。'),
                        ('彼女はょ斎を片付けます。','彼女は書斎を片付けます。')):
                    a=initial();tok=C.make_tokenizer(a.store)
                    target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text in ('ょ見','ょ斎'))
                    rd,repair,face=next(row for row in Q._whole_written_nominal_omissions(target.text) if row[2] in ('所見','書斎'))
                    accepted,reason=Q.validate(target,'読み',C,tok,a.store,a.dict_index,a.decisions,'よみ',source_reading=rd)
                    self.assertFalse(accepted);self.assertEqual(reason,'unproven_whole_nominal_completion')
                    result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
                    self.assertEqual(result['analysis_status'],'complete')
                    with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                        accepted,reason=Q.validate(target,face,C,tok,a.store,a.dict_index,a.decisions,repair.reading,source_reading=rd)
                    self.assertFalse(accepted);self.assertEqual(reason,'test_reject')
        finally:set_active(None)

    def test_original_written_boundary_precedes_only_broad_role_support(self):
        import app,contextual_repair as Q,corrector as C,ime_language,ime_candidates
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        source='彼はょ庫を整理しました。'
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                a=initial();tok=C.make_tokenizer(a.store)
                target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='ょ庫')
                selected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                rows={r['surface']:r for r in diag['candidates']}
                self.assertEqual(selected,'書庫')
                self.assertEqual(rows['書庫']['rank_evidence']['meaning'],0)
                self.assertEqual(rows['読み']['rank_evidence']['meaning'],-1)
                self.assertEqual(rows['読み']['rank_evidence']['written_boundary'],0)
                self.assertEqual(rows['書庫']['rank_evidence']['written_boundary'],-1)
                # A specific proved source relation retains its priority.
                from copy import deepcopy
                alternatives=deepcopy([rows['書庫'],rows['読み']])
                alternatives[1]['rank_evidence']['source_relation']=-1
                self.assertEqual(Q.rank_candidates(alternatives)[0]['surface'],'読み')
                a=initial()
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],'彼は書庫を整理しました。')
                self.assertEqual(result['odd_spans'],[])
                with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                    rejected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                self.assertIsNone(rejected)
        finally:set_active(None)

    def test_retained_written_tail_requires_native_word_reading_and_unchanged_keys(self):
        import contextual_repair as Q
        from types import SimpleNamespace
        from dataclasses import replace
        target=SimpleNamespace(text='ょ庫');reading=Q.Reading('ょこ','native',0)
        repair=Q.KeyRepair('しょこ','omission',0,'','し',2.8)
        self.assertTrue(Q._retained_written_nominal_tail(target,'書庫',reading,repair))
        for text,face,rd,change in (
            ('ょ庫','チョコ',reading,replace(repair,reading='ちょこ',intended='ち')),
            ('ょ庫','ヨコ',reading,replace(repair,reading='よこ',operation='shift')),
            ('ょ庫','書庫',reading,replace(repair,reading='しょく')),
            ('ょ庫','書庫',reading,replace(repair,position=2)),
            ('ょ庫','書庫',Q.Reading('ょく','guessed',9),repair),
            ('ょく','書庫',Q.Reading('ょく','source',0),repair),
            ('ょ庫\t書庫','書庫',Q.Reading('ょこしょこ','native',0),repair),
            ('ょ庫','書庫',reading,replace(repair,operation='substitution')),
        ):
            with self.subTest(text=text,face=face,repair=change):
                self.assertFalse(Q._retained_written_nominal_tail(SimpleNamespace(text=text),face,rd,change))

    def test_retained_written_tail_selects_only_after_common_candidate_checks(self):
        import contextual_repair as Q,corrector as C,ime_language,ime_candidates
        from tests_analysis_async import initial
        from last_choice import set_active
        from unittest.mock import patch
        source='彼はょ庫を開けます。'
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                a=initial();tok=C.make_tokenizer(a.store)
                target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.text=='ょ庫')
                selected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                self.assertEqual(selected,'書庫')
                rows={row['surface']:row for row in diag['candidates']}
                self.assertNotIn('チョコ',rows)
                self.assertLess(rows['書庫']['rank_evidence']['written_native'],0)
                accepted,reason=Q.validate(target,'チョコ',C,tok,a.store,a.dict_index,a.decisions,
                    'ちょこ',source_reading=Q.Reading('ょこ','contextual_token_sequence',0))
                self.assertEqual((accepted,reason),(False,'unedited_written_nominal_tail'))
                # No new meaning is invented from the retained printed noun.
                self.assertEqual(rows['書庫']['rank_evidence']['meaning'],0)
                with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                    rejected,diag=Q.resolve(target,C,tok,a.store,a.dict_index,a.decisions)
                self.assertIsNone(rejected)
        finally:set_active(None)

    def test_native_written_tail_supplies_missing_lexical_entry_without_band(self):
        import contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        try:
            tails=Q._source_written_nominal_tails('ょ庫','ょこ')
            self.assertIn(('庫','こ'),tails)
            self.assertIn('書庫',Q._native_written_nominal_readings()['しょこ'])
            repairs=Q.lexical_omission_repairs('ょこ',a.dict_index,native_tails=tails)
            self.assertTrue(any(r.reading=='しょこ' and r.operation=='omission' and r.position==0
                                and r.intended=='し' for r in repairs))
            for text,reading in (('ょ庫','ょやく'),('ABC庫','えーびーしーこ'),
                                 ('書庫','しょこ'),('ょ庫\t書庫','ょこしょこ')):
                self.assertEqual(Q._source_written_nominal_tails(text,reading),(),(text,reading))
            self.assertFalse(Q._source_written_nominal_tails('ょ庫','ょく'))
        finally:set_active(None)

    def test_native_omission_spelling_reaches_common_check_without_forcing_selection(self):
        import app,corrector as C,ime_language,ime_candidates
        from unittest.mock import patch
        from tests_analysis_async import initial
        from last_choice import set_active
        source='彼はょ庫を開けます。';check=C._check_replacement;seen=[]
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs)
            seen.append((replacement,result))
            return result
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                a=initial()
                with patch.object(C,'_check_replacement',side_effect=observed):
                    result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertTrue(any(tuple(replacement[:3])==(2,4,'書庫') for replacement,value in seen),seen)
                self.assertEqual(result['analysis_status'],'complete')
                a=initial()
                with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                    result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertTrue(result['odd_spans'])
        finally:set_active(None)


    def test_pronoun_case_is_source_evidence_before_an_unknown_noun(self):
        import corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            for source in ('わたしはょ類を送信しました。','ぼくはょ類を送信しました。',
                           '私はょ類を送信しました。','わたしはしはょ類を送信しました。'):
                edge=source.index('は')+1;end=source.index('を')
                with self.subTest(source=source):
                    self.assertIn((edge-1,edge),R.native_pronoun_case_ranges(source))
                    targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
                    self.assertTrue(any(t.start==edge and t.end==end for t in targets),targets)
                    wrong=source[:edge-1]+'書類'+source[end:]
                    self.assertFalse(R.preserves_native_pronoun_case(source,wrong))
                    self.assertTrue(R.preserves_native_pronoun_case(source,source[:edge]+'書類'+source[end:]))
                    self.assertEqual(C._check_replacement(source,(edge-1,end,'書類','かな入力'),
                        a.store,tok,a.dict_index,a.decisions),(None,'original_pronoun_case'))
            for source in ('資料はょ類です','ぷねらはょ類です','書類を送信しました。'):
                self.assertEqual(R.native_pronoun_case_ranges(source),(),source)
            # Only the particle is owned; independent spelling and the next
            # missing onset can change without editing it or another column.
            for source,changed in (('わたしのものです','私のものです'),
                                   ('ぼくもょ類を見ます','僕も書類を見ます'),
                                   ('私は書類を見ます\tょ類','私は書類を見ます\t書類')):
                self.assertTrue(R.preserves_native_pronoun_case(source,changed),(source,changed))
        finally:set_active(None)

    def test_pronoun_particle_survives_lexical_repair_and_independent_spelling(self):
        import app,ime_language,ime_candidates
        from unittest.mock import patch
        from tests_analysis_async import initial
        from last_choice import set_active
        cases=(('わたしはょ類を送信しました。','私は書類を送信しました。'),
               ('ぼくはょ類を送信しました。','僕は書類を送信しました。'),
               ('私はょ類を送信しました。','私は書類を送信しました。'),
               ('わたしはしはょ類を送信しました。','私は書類を送信しました。'),
               ('わたしはょ類\t書類','私は書類\t書類'),
               ('「わたしはょ類」と入力します。','「わたしはょ類」と入力します。'))
        try:
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self):
                for source,expected in cases:
                    with self.subTest(source=source):
                        a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                            decisions=a.decisions,context_vec=None)
                        self.assertEqual(r['corrected'],expected)
                        self.assertEqual(r['odd_spans'],[])
                        self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_pronoun_boundary_still_requires_the_common_candidate_check(self):
        import app,corrector as C,ime_language,ime_candidates
        from unittest.mock import patch
        from tests_analysis_async import initial
        from last_choice import set_active
        source='わたしはょ類を送信しました。'
        try:
            a=initial()
            with patch.object(ime_language,'_factory',None),patch.object(ime_candidates.SearchCandidates,'__enter__',lambda self:self),patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            self.assertTrue(r['odd_spans'])
        finally:set_active(None)


    def test_short_written_arguments_keep_the_same_native_case_boundary(self):
        import contextual_repair as Q
        for text,written in (('鍋に水をいれる',False),('皿に肉を置く',True),
                             ('子に本を読む',True),('箱に本を置く',True)):
            with self.subTest(text=text):
                parts=R.native_preposed_object_parts(text,written)
                self.assertTrue(parts,text)
                self.assertTrue(any(cut==text.index('を')+1
                                    for edge,case,receiver,cut,objects in parts),text)
        for text in ('鍋に水を','鍋にをいれる','ぷねらに本を読む'):
            self.assertFalse(R.native_preposed_object_parts(text,True),text)
        for line,face in (('なべに水をいれます','鍋'),('さらに水をいれます','皿')):
            self.assertTrue(Q._changed_object_slot_allowed(line,0,2,face),(line,face))

    def test_source_ranges_include_written_and_kana_arguments(self):
        for text in ('せんせいにしりょうをおきります','先生に資料をおきります',
                     'ともだちにてがみをおきります','友達に手紙をおきります'):
            frames=R.native_object_predicate_frames(text)
            self.assertTrue(frames,text)
            self.assertTrue(any(cut==text.index('を')+1 for cut,faces in frames),text)
            for cut,faces in frames:
                self.assertFalse(R.native_object_predicate_proof(text,cut,faces),text)
                normal=text.replace('おきります','おくります')
                self.assertTrue(R.native_object_predicate_proof(normal,cut,faces),normal)
                self.assertTrue(R.native_object_predicate_proof(normal+'。',cut,faces),normal)

    def test_every_argument_keeps_its_written_meaning(self):
        for text in ('精度に資料をおくります','制度に資料をおくります','水に資料をおくります',
                     '先生に精度をおくります','先生に制度をよみます','先生に飼料をよみます'):
            frames=R.native_object_predicate_frames(text)
            self.assertTrue(frames,text)
            self.assertFalse(any(R.native_object_predicate_proof(text,cut,faces)
                                 for cut,faces in frames),text)

    def test_classified_whole_readings_keep_family_and_human_arguments(self):
        import semantic_roles as S
        for reading,face in (('かぞく','家族'),('わたし','私'),('おきゃくさま','お客様'),
                             ('とまと','トマト'),('しりょう','史料')):
            self.assertIn(face,R.native_nominal_phrase_faces(reading),reading)
        for text in ('かぞくにしりょうをおくります','わたしにほんをよんでくれます',
                     'おきゃくさまにおちゃをだします'):
            frames=R.native_object_predicate_contexts(text)
            self.assertTrue(frames,text)
            self.assertTrue(any(R.native_object_predicate_proof(text[begin:],cut-begin,faces)
                                for begin,cut,faces in frames),text)
        for noun in ('私','僕','彼女','お客様','父','母'):
            self.assertIn('person',S.nominal_roles(noun),noun)
        for noun in ('これ','それ','あれ','水','精度'):
            self.assertNotIn('person',S.nominal_roles(noun),noun)
        # 48-AMP: classified one-kana nouns retain exact native evidence.
        self.assertIn('子',R._classified_nominal_readings().get('こ',()))
        self.assertIn('目',R._classified_nominal_readings().get('め',()))
        # Lexical evidence is independent of a positive semantic-role inventory.
        self.assertTrue(R.native_common_noun_reading('木','き'))
        self.assertNotIn('木',R._classified_nominal_readings().get('き',()))
        self.assertFalse(R.completed_native_reading_clause('こをのみます',require_object_fit=True))

    def test_nominal_reading_with_adverbial_ni_keeps_positive_case_proof(self):
        for text in ('あににおちゃをだします','兄にお茶をだします',
                     'あににしりょうをおくります'):
            frames=R.native_object_predicate_contexts(text)
            self.assertTrue(frames,text)
            self.assertTrue(any(R.native_object_predicate_proof(text[begin:],cut-begin,faces)
                                for begin,cut,faces in frames),text)
        source='あににおちゃをだします'
        boundary=R.native_nominal_case_boundary(source,M.tokenize(source),2,'に',('兄',),
                                                allow_known_noun=True)
        self.assertEqual(boundary,('兄',True))
        for text in ('あににおちゃをのみます','あににせいどをだします',
                     'あににおちゃをだしますです','さらにおちゃをだします'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_written_receiver_shares_whole_original_intactness(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        for text in ('兄におちゃをだします。','姉におちゃをだします。',
                     '弟におちゃをだします。','妹におちゃをだします。',
                     '彼におちゃをだします。','彼女におちゃをだします。'):
            self.assertIn((0,len(text)-1),R.native_context_ranges(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=a.context_vec,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertEqual(result.get('odd_spans'),[])
        for text in ('兄におちゃをのみます','水におちゃをだします',
                     '兄におちゃをだしますです','兄にぷねらをだします'):
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)

    def test_written_predicate_cannot_borrow_a_fitting_homophone_to_hide_a_source_conflict(self):
        for text in ('意見を繁栄します','騒動を収集します','人質を開放します',
                     '画面を長生します','ひらがなを漢字に返還します'):
            frames=R.native_object_predicate_contexts(text,allow_written_predicate=True)
            self.assertTrue(frames,text)
            for begin,cut,faces in frames:
                self.assertFalse(R.native_object_predicate_proof(text[begin:],cut-begin,faces),text)
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)
        for text in ('意見を反映します','資料を収集します','人質を解放します',
                     '画面を調整します','ひらがなを漢字に変換します'):
            self.assertIn((0,len(text)),R.native_context_ranges(text),text)

    def test_written_predicate_shares_positive_source_proof_without_expanding_targets(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ほんをにさつ読みます。','本をにさつ読みます。',
                     '資料をにさつ読みます。','しりょうをにさつ読みます。',
                     'おきゃくさまにしりょうを送ります。'):
            self.assertIn((0,len(text)-1),R.native_context_ranges(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertEqual(result.get('odd_spans'),[])
        for text in ('ほんをにさつ飲みます','本をにさつ読みますです',
                     'おきゃくさまにしりょうを起きります'):
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)
        self.assertFalse(R.native_object_predicate_contexts('ほんをにさつ読みます'))
        self.assertTrue(R.native_object_predicate_contexts('ほんをにさつ読みます',allow_written_predicate=True))

    def test_provision_uses_the_same_object_and_recipient_roles(self):
        import semantic_roles as S
        for noun in ('茶','水','料理','資料','手紙','お金'):
            self.assertTrue(S.support(noun,'出す'),noun)
        for person in ('客','お客様','先生','友人'):
            self.assertTrue(S.case_action_support(person,'に','出す'),person)
        self.assertFalse(S.case_action_support('水','に','出す'))
        self.assertFalse(S.case_action_support('精度','に','出す'))
        self.assertFalse(S.support('飼料','読む'))

    def test_marked_object_reuses_its_original_adverb_boundary(self):
        import app
        import contextual_repair as X
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for prefix in ('あしたまでに','しめきりまでに','じぶんで'):
            source=prefix+'しゃとんをならべます。'
            targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
            self.assertTrue(any(t.start==len(prefix) and t.text=='しゃとん'
                                and t.boundary_kind=='nominal_object' for t in targets),source)
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, (prefix+'しゃしんをならべます。',prefix+'写真をならべます。'))
            self.assertFalse(result.get('odd_spans'),source)
            normal=prefix+'しゃしんをならべます。'
            result=app.correct_line(normal,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], normal)
            self.assertFalse(result.get('odd_spans'),normal)
        source='ぷねらまでにしゃとんをならべます。'
        targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
        self.assertFalse(any(t.start==len('ぷねらまでに') and t.text=='しゃとん' for t in targets))
        # Retain the original incomplete-polite and quoted counterexamples.
        # The horizontal fixture replaces only the completed object examples.
        for source in ('あしたまでにしゃしま','「あしたまでにしゃしま」と入力しました。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)

    def test_temporal_prefix_keeps_its_separate_adverb_boundary(self):
        text='あさにつくったしりょうをせんせいにおきります'
        self.assertFalse(R.native_preposed_object_parts(text))
        self.assertTrue(R.native_object_predicate_contexts(text))

    def test_original_receiver_cannot_be_replaced_by_a_wider_predicate_proposal(self):
        import contextual_repair as C
        text='先生に資料をおきります'
        self.assertTrue(C.object_predicate_candidate_allowed(text,6,len(text),'おくります'))
        self.assertFalse(C.object_predicate_candidate_allowed(text,0,len(text),'水に資料をおくります'))
        self.assertFalse(C.object_predicate_candidate_allowed(text,0,len(text),'生徒に資料をおくります'))

    def test_wide_final_proposals_keep_the_same_source_arguments_and_action(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('先生に資料をおきります','先生に資料をおきります。',
                     'せんせいにしりょうをおきります。'):
            good=text.replace('おき','おく')
            value,reason=C._check_replacement(text,(0,len(text),good,'かな入力'),
                a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNotNone(value,reason)
            for bad in (good.replace('先生','水').replace('せんせい','みず'),
                        good.replace('先生','生徒').replace('せんせい','せいと'),
                        text.replace('おき','のみ')):
                value,reason=C._check_replacement(text,(0,len(text),bad,'かな入力'),
                    a.store,tokenize,a.dict_index,a.decisions)
                self.assertIsNone(value,bad)

    def test_independent_clause_can_change_without_repairing_old_bad_predicate(self):
        import contextual_repair as C
        text='今日は休みです。先生に資料をおきります。'
        changed=text.replace('今日','明日')
        self.assertTrue(C.object_predicate_candidate_allowed(text,0,len(text),changed))
        changed=text.replace('今日は休みです。','明日です。').replace('おき','おく')
        self.assertTrue(C.object_predicate_candidate_allowed(text,0,len(text),changed))
        self.assertFalse(C.object_predicate_candidate_allowed(text,0,len(text),
            changed.replace('先生','水')))

    def test_earlier_source_clause_does_not_hide_the_marked_actions_own_object(self):
        import app,corrector as C
        from tests_analysis_async import initial
        import contextual_repair as Q,reading_segments as R
        source='集めて資料をならぺ手内容を比べます。'
        clause=source.rstrip('。')
        self.assertIn(3,R.native_completed_clause_boundaries(clause))
        self.assertIn((3,6,10,('資料',)),Q._source_actions_before_owned_objects(clause))
        a=initial();tok=C.make_tokenizer(a.store)
        targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
        self.assertTrue(any((t.start,t.end,t.text)==(6,10,'ならぺ手') for t in targets))
        for text in ('集めて資料を並べて内容を比べます。',
                     'ぽねて資料をならぺ手内容を比べます。',
                     '集めてをならぺ手内容を比べます。'):
            self.assertFalse(Q._source_actions_before_owned_objects(text.rstrip('。')),text)

    def test_later_marked_action_keeps_its_own_meaning_and_common_validation(self):
        import app,corrector as C
        from tests_analysis_async import initial
        import contextual_repair as Q
        from unittest.mock import patch
        from last_choice import set_active
        source='集めて資料をならぺ手内容を比べます。'
        try:
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(r['corrected'],'集めて資料を並べて内容を比べます。')
            self.assertEqual(r['odd_spans'],[])
            self.assertEqual(r['analysis_status'],'complete')
            bad='集めて資料をたぺ手内容を比べます。'
            a=initial();r=app.correct_line(bad,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertNotIn('資料を食べて',r['corrected'])
            self.assertEqual(r['analysis_status'],'complete')
            for text in ('集めて資料を並べて内容を比べます。',
                         '「'+source+'」と入力します。'):
                a=initial();r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])
                self.assertEqual(r['analysis_status'],'complete')
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
            self.assertEqual(r['corrected'],source)
            self.assertTrue(r['odd_spans'])
            self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_following_object_bounds_marked_action_without_lending_its_role(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from unittest.mock import patch
        from last_choice import set_active
        for source,expected,head in (
                ('資料をならぺて内容を比べます。','資料を並べて内容を比べます。','ならぺて'),
                ('集めた資料をならぺ手内容を比べます。','集めた資料を並べて内容を比べます。','ならぺ手')):
            with self.subTest(source=source):
                a=initial();tok=C.make_tokenizer(a.store)
                targets=Q.targets_for_line(source,tok,a.store,a.dict_index)
                self.assertTrue(any(t.text==head for t in targets))
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
                self.assertEqual(r['analysis_status'],'complete')
                a=initial()
                with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source)
        for source in ('資料を並べて内容を比べます。','資料をならべて内容を比べます。',
                       '「資料をならぺて内容を比べます。」と入力しました。'):
            with self.subTest(normal=source):
                a=initial();tok=C.make_tokenizer(a.store)
                self.assertFalse(any(t.text=='ならぺて' for t in Q.targets_for_line(source,tok,a.store,a.dict_index)))
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source.replace('ならべて','並べて'))
                self.assertEqual(r['odd_spans'],[])
        set_active(None)

    def test_following_object_does_not_license_a_mismatched_first_predicate(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        source='資料をたぺて内容を比べます。'
        a=initial();tok=C.make_tokenizer(a.store)
        self.assertTrue(any(t.text=='たぺて' for t in Q.targets_for_line(source,tok,a.store,a.dict_index)))
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        set_active(None)

    def test_changed_note_scope_keeps_original_key_direction_exclusion(self):
        import contextual_repair as X
        import kana_layout as L
        self.assertEqual(L.kana_key_distance('ほ','へ'),1)
        self.assertTrue(any(r.reading=='へんこう' and r.operation=='adjacent_substitution'
                            for r in X.key_repairs('ほんこう')))
        for generator in (X.key_repairs,X.nonadjacent_key_repairs,
                          X.adjacent_shift_key_repairs,X.neighbor_shift_key_repairs):
            self.assertNotIn('へんこう',{r.reading for r in generator('せんこう')})

    def test_completed_clause_and_action_note_keep_their_source_scope(self):
        import contextual_repair as C
        import app
        from tests_analysis_async import initial
        source='せつめいをきいてからじぶんてためしてみます。'
        self.assertTrue(C.object_predicate_candidate_allowed(source,13,14,'で'))
        self.assertTrue(C.object_predicate_candidate_allowed(source,0,len(source),source.replace('じぶんて','じぶんで')))
        note='ないようをほんこうしてほぞん'
        self.assertTrue(C.object_predicate_candidate_allowed(note,0,9,'ないようをへんこう'))
        self.assertTrue(C.object_predicate_candidate_allowed(note,0,len(note),note.replace('ほんこう','へんこう')))
        self.assertFalse(C.object_predicate_candidate_allowed(note,0,len(note),'ねこをへんこうしてほぞん'))
        self.assertFalse(C.object_predicate_candidate_allowed(note,0,len(note),'ないようをこうこうしてほぞん'))
        a=initial()
        for text,expected in (('せつめいをきいてからじぶん゛てためしてみます。',source.replace('じぶんて','じぶんで')),
                ('こどもにえほんをよんであうげます。','こどもにえほんを読んであげます。'),
                (note,note.replace('ほんこう','へんこう'))):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, expected)
            self.assertEqual(result.get('odd_spans'),[])

    def test_actual_repairs_and_normal_second_pass(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('せんせいにしりょうをおきります。','先生に資料をおきります。',
                     'ともだちにてがみをおきります。','友達に手紙をおきります。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            expected=text.replace('おきります','送ります')
            assert_reviewed_source_spelling(self, result['corrected'], expected, text)
            normal=app.correct_line(expected,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, normal['corrected'], expected)
            self.assertEqual(normal.get('odd_spans'),[],expected)

    def test_unknown_quoted_and_unmatched_receiver_remain_literal(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('精度に資料をおきります。','みずにしりょうをおきります。',
                     '「せんせいにしりょうをおきります」という例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            expected='水にしりょうをおきります。' if text=='みずにしりょうをおきります。' else text
            self.assertEqual(result['corrected'],expected)

    def test_unknown_receiver_keeps_its_name_without_freezing_known_object(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        result=app.correct_line('ぷねらに資料をおきります。',a.store,input_method='kana',
            dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'ぷねらに資料を送ります。')
        unchanged=app.correct_line('ぷねらに資料を送ります。',a.store,input_method='kana',
            dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['odd_spans'],unchanged['odd_spans'])

    def test_nominal_slot_keeps_existing_source_mark_without_broad_request(self):
        import app,corrector as C,contextual_repair as X
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for prefix in ('さぎょうまえに','さぎょうごに'):
            source=prefix+'しゃとんをならべます。'
            targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
            self.assertFalse(any(t.boundary_kind=='kana_request' for t in targets))
            narrow=[t for t in targets if t.boundary_kind=='nominal_object'
                    and t.start==len(prefix) and t.text=='しゃとん']
            self.assertEqual(len(narrow),1)
            self.assertTrue(narrow[0].anomalies)
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, (prefix+'しゃしんをならべます。',prefix+'写真をならべます。'))
            self.assertFalse(result.get('odd_spans'))
            normal=prefix+'しゃしんをならべます。'
            self.assertFalse(X.targets_for_line(normal,tokenize,a.store,a.dict_index))
            result=app.correct_line(normal,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], normal)
            self.assertFalse(result.get('odd_spans'))
        for source in ('さぎょうまえにぷねらをならべます。','さぎょうまえにしゃとんをたべます。',
                       '「さぎょうまえにしゃとんをならべます」という入力例です。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)

if __name__=='__main__':unittest.main()
