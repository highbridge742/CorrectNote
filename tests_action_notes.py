# -*- coding: utf-8 -*-
"""Shared usage knowledge and grammatical/semantic evidence for action notes."""
import unittest
from unittest.mock import patch
import kango_tier as K
import morphology as M
import reading_segments as R
import semantic_roles as S


class ActionNoteTests(unittest.TestCase):
    @unittest.skipUnless(M.HAS_JANOME,'native action endings and horizontal-key evidence')
    def test_action_endings_keep_horizontal_completed_expectations(self):
        import app,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        cases=(('しい','して','かくにんしいほぞんしてしゅうりょう','確認して保存して終了'),
               ('しくす','します','ぶんしょうをにゅうりょくしくす。','文章を入力します。'))
        try:
            for typed,reading,source,expected in cases:
                with self.subTest(source=source):
                    self.assertTrue(any(row.reading==reading and row.operation=='adjacent_substitution'
                                        for row in Q.key_repairs(typed)))
                    a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    @unittest.skipUnless(M.HAS_JANOME,'excluded directions, literal input and common final gate')
    def test_action_endings_preserve_old_negatives_quotes_and_common_gate(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        cases=(('しあ','して','かくにんしあほぞんしてしゅうりょう','かくにんしあほぞんしてしゅうりょう'),
               ('しんす','します','ぶんしょうをにゅうりょくしんす。','文章をにゅうりょくしんす。'))
        try:
            for typed,reading,source,expected in cases:
                with self.subTest(source=source):
                    for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                                      Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
                        self.assertNotIn(reading,{row.reading for row in generator(typed)})
                    a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],expected)
                    self.assertTrue(r['odd_spans'])
                    self.assertEqual(r['analysis_status'],'complete')
            for text,normal in (('かくにんしいほぞんしてしゅうりょう','確認して保存して終了'),
                                ('ぶんしょうをにゅうりょくしくす。','文章を入力します。')):
                for source in ('「'+text+'」と入力します。',normal):
                    a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],source)
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['analysis_status'],'complete')
                a=initial()
                with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],text)
                self.assertTrue(r['odd_spans'])
                self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    @unittest.skipUnless(M.HAS_JANOME,'native action and horizontal-key evidence')
    def test_object_action_fixtures_keep_complete_horizontal_repairs(self):
        import app,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        cases=(('せすり','せいり','しりょうをせすりしてください。','資料を整理してください。'),
               ('せいれ','せいり','しりょうをせいれしてください。','資料を整理してください。'),
               ('かきにん','かくにん','きろくをかきにんしてほぞんします。','記録を確認して保存します。'))
        try:
            for typed,reading,source,expected in cases:
                with self.subTest(source=source):
                    self.assertTrue(any(r.reading==reading and r.operation=='adjacent_substitution'
                                        for r in Q.key_repairs(typed)))
                    a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    @unittest.skipUnless(M.HAS_JANOME,'native action and excluded original directions')
    def test_object_action_fixtures_keep_old_direction_negatives(self):
        import app,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        cases=(('せあり','せいり','しりょうをせありしてください。'),
               ('せいる','せいり','しりょうをせいるしてください。'),
               ('かんにん','かくにん','きろくをかんにんしてほぞんします。'))
        try:
            for typed,reading,source in cases:
                with self.subTest(source=source):
                    for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,
                                      Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
                        self.assertNotIn(reading,{r.reading for r in generator(typed)})
                    a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                    unchanged_action={
                        'しりょうをせありしてください。':'資料をせありしてください。',
                        'しりょうをせいるしてください。':'しりょうをせいるしてください。',
                        'きろくをかんにんしてほぞんします。':'記録をかんにんしてほぞんします。'}
                    self.assertEqual(r['corrected'],unchanged_action[source])
                    self.assertTrue(r['odd_spans'])
                    self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    @unittest.skipUnless(M.HAS_JANOME,'literal input and common final gate')
    def test_object_action_horizontal_fixtures_keep_quotes_and_final_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            for text in ('しりょうをせすりしてください。','しりょうをせいれしてください。',
                         'きろくをかきにんしてほぞんします。'):
                source='「'+text+'」と入力します。';a=initial()
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source)
                self.assertEqual(r['odd_spans'],[])
                a=initial()
                with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],text)
        finally:set_active(None)

    @unittest.skipUnless(M.HAS_JANOME,'native action and physical-key evidence')
    def test_action_comparison_uses_horizontal_inputs_and_preserves_old_exclusions(self):
        import app,contextual_repair as Q,kana_layout as L
        from tests_analysis_async import initial
        from last_choice import set_active
        positives=(('かくなん','かくにん','確認して保存'),('かくせん','かくらん','撹乱して保存'))
        try:
            for typed,reading,expected in positives:
                with self.subTest(source=typed):
                    self.assertEqual(L.kana_key_distance(typed[2],reading[2]),1)
                    self.assertTrue(any(r.reading==reading and r.operation=='adjacent_substitution' for r in Q.key_repairs(typed)))
                    a=initial();source=typed+'してほぞん'
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['analysis_status'],'complete')
            for typed in ('かくゆん','かくよん','かくのん','かくわん','かくりん'):
                with self.subTest(source=typed):
                    for generator in (Q.key_repairs,Q.nonadjacent_key_repairs,Q.adjacent_shift_key_repairs,Q.neighbor_shift_key_repairs):
                        self.assertFalse({'かくにん','かくらん'} & {r.reading for r in generator(typed)})
                    a=initial();source=typed+'してほぞん'
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(r['corrected'],source)
                    self.assertTrue(r['odd_spans'])
                    self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    @unittest.skipUnless(M.HAS_JANOME,'native action and common candidate validation')
    def test_horizontal_action_keeps_literal_input_and_shared_candidate_rejection(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            for source in ('「かくなんしてほぞん」と入力します。','「かくせんしてほぞん」と入力します。'):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source)
                self.assertEqual(r['odd_spans'],[])
            for source in ('かくなんしてほぞん','かくせんしてほぞん'):
                a=initial()
                with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source)
                self.assertTrue(r['odd_spans'])
        finally:set_active(None)

    @unittest.skipUnless(M.HAS_JANOME,'native comparative meaning')
    def test_blocked_comparative_action_keeps_source_and_unresolved_mark(self):
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        a.decisions.reject('用船','優先')
        result=app.correct_line('用船して補正',a.store,input_method='kana',
            dict_index=a.dict_index,decisions=a.decisions)
        self.assertEqual(result['corrected'],'用船して補正')
        self.assertEqual(result['odd_spans'],[(0,2)])
        self.assertEqual(result['analysis_status'],'complete')
        self.assertEqual(a.store.revision(),revision)

    @unittest.skipUnless(M.HAS_JANOME,'native phrase selection')
    def test_bare_specialist_action_retains_whole_phrase_choice(self):
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        a.choices._readings['ようせんしてほせい']='用船して補正'
        cases=(('用船して補正','用船して補正'),
               ('\t\tようせんしてほせい⇒\t\t','\t\t用船して補正⇒\t\t'))
        for source,expected in cases:
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',
                    dict_index=a.dict_index,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
        self.assertEqual(a.store.revision(),revision)

    @unittest.skipUnless(M.HAS_JANOME,'native action and physical-key evidence')
    def test_reviewed_bare_specialist_action_compares_with_control_reading(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        cases=(
            ('用船して補正','優先して補正'),
            ('ようせんしてほせい','優先して補正'),
            ('ゆうせんしてほせい','優先して補正'),
            ('\t\tようせんしてほせい⇒\t\t','\t\t優先して補正⇒\t\t'),
            ('船を用船して補正','船を用船して補正'),
            ('用船して出港','用船して出港'),
            ('用船契約を確認','用船契約を確認'),
            ('用船','用船'),
            ('用船して補正します','用船して補正します'),
            ('「用船して補正」という誤入力です。','「用船して補正」という誤入力です。'),
            ('用船して\t補正','用船して\t補正'))
        revision=a.store.revision()
        for source,expected in cases:
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',
                    dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
        self.assertEqual(a.store.revision(),revision)
        # A fixture representing an explicit last spelling changes only this
        # in-memory initial store; no personal choice file is loaded or saved.
        a.choices._readings['ようせん']='用船'
        result=app.correct_line('用船して補正',a.store,input_method='kana',
            dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'用船して補正')
        self.assertFalse(result['odd_spans'])

    def tearDown(self):
        for f in (K._explicit_reading_faces,R._native_nominal_reading_faces,
                  R.native_bare_action_faces,R.native_nominal_phrase_faces,R._native_action_note_heads,
                  R.completed_native_action_note,R.completed_native_reading,
                  R.completed_sahen_reading,R.completed_native_reading_clause):
            f.cache_clear()

    def test_older_positive_usage_has_native_reading_evidence_too(self):
        def native(word):
            entries={'既存':(('名詞,サ変接続,*,*','*','既存','きそん'),),
                     '追加':(('名詞,サ変接続,*,*','*','追加','ついか'),)}
            return entries.get(word,())
        K._explicit_reading_faces.cache_clear()
        with patch('public_nominal_cache.load',return_value=None), \
             patch.object(K,'_load',return_value={}), \
             patch.object(K,'_TABLE',{'既存':1,'未分類':3}), \
             patch.object(K,'_USAGE',{'追加':2,'辞書不在':1}), \
             patch.object(K,'_READING_USAGE',{}), \
             patch.object(M,'dictionary_inflections',side_effect=native):
            self.assertEqual(K._explicit_reading_faces(),{'きそん':{'既存'},'ついか':{'追加'}})

    def test_bare_action_requires_native_nominal_reading_and_sahen(self):
        forms={'保存':(('名詞,サ変接続,*,*','*','保存','ほぞん'),),
               '普通':(('名詞,一般,*,*','*','普通','ふつう'),)}
        with patch.object(R,'_native_nominal_reading_faces',side_effect=lambda rd:tuple(forms)), \
             patch.object(M,'dictionary_inflections',side_effect=lambda w:forms.get(w,())):
            self.assertEqual(R.native_bare_action_faces('ほぞん'),('保存',))
            self.assertEqual(R.native_bare_action_faces('ふつう'),())
            self.assertEqual(R.native_bare_action_faces('べつよみ'),())

    def test_note_reuses_proven_action_and_passes_following_meaning(self):
        calls=[]
        def clause(text,**kwargs):
            calls.append((text,kwargs))
            return '確認' if text=='ないようをかくにんして' else False
        with patch.object(R,'native_bare_action_faces',side_effect=lambda s:('保存',) if s=='ほぞん' else ()), \
             patch.object(R,'completed_native_reading_clause',side_effect=clause):
            self.assertTrue(R.completed_native_action_note('ないようをかくにんしてほぞん'))
        text,kwargs=next(r for r in calls if r[0]=='ないようをかくにんして')
        self.assertTrue(kwargs['require_object_fit'])
        self.assertTrue(kwargs['return_action'])
        self.assertEqual(kwargs['action_note_following'],('保存',))

    def test_incomplete_or_adnominal_tail_is_not_an_action_note(self):
        with patch.object(R,'native_bare_action_faces',return_value=('保存',)), \
             patch.object(R,'completed_native_reading_clause',return_value='確認'):
            for text in ('かくにんしたほぞん','かくにんするほぞん',
                         'かくにんしほぞん','かくにんてほぞん'):
                self.assertFalse(R.completed_native_action_note(text),text)

    def test_unproven_left_clause_does_not_gain_evidence_from_right_action(self):
        with patch.object(R,'native_bare_action_faces',return_value=('保存',)), \
             patch.object(R,'completed_native_reading_clause',return_value=False):
            self.assertFalse(R.completed_native_action_note('かくにんしてほぞん'))

    def test_shared_action_roles_require_positive_linkage(self):
        for a,b in (('確認','保存'),('優先','補正'),('入力','終了'),
                    ('起動','確認'),('掃除','洗濯'),('集計','保存')):
            self.assertTrue(S.action_note_support(a,b),(a,b))
        with patch.object(S,'predicate_roles',side_effect=lambda s:
                frozenset(('information',)) if s=='保存' else frozenset()):
            self.assertFalse(S.action_note_support('堪忍','保存'))
            self.assertFalse(S.action_note_support('収賄','保存'))
            self.assertFalse(S.action_note_support('未分類','終了'))

    def test_activity_link_does_not_invent_an_accusative_frame(self):
        self.assertTrue(S.action_note_support('訓練','上達'))
        self.assertTrue(S.action_note_support('運動','補給'))
        self.assertTrue(S.action_note_support('補給','休息'))
        self.assertFalse(S.action_note_support('収賄','保存'))
        with patch.object(S,'_action_head',return_value='上達'):
            e=S.candidate_evidence('人','上達','します')
            self.assertFalse(e['shared_roles'])

    def test_introductory_word_needs_its_native_role_and_unchanged_action(self):
        word=M.Token('そして','接続詞','そして','そして',0,3,True,'*','')
        R.native_action_note_introduction.cache_clear()
        with patch.object(M,'tokenize',return_value=[word]), \
             patch.object(R,'native_bare_action_faces',side_effect=lambda rd:('保存',) if rd=='ほぞん' else ()):
            self.assertTrue(R.native_action_note_introduction('そしてほぞん'))
            self.assertFalse(R.native_action_note_introduction('そしてほぞんしたます'))
        R.native_action_note_introduction.cache_clear()
        wrong=M.Token('そして','名詞','そして','そして',0,3,True,'一般','')
        with patch.object(M,'tokenize',return_value=[wrong]), \
             patch.object(R,'native_bare_action_faces',return_value=('保存',)):
            self.assertFalse(R.native_action_note_introduction('そしてほぞん'))
        R.native_action_note_introduction.cache_clear()


    def test_native_conjunction_outside_the_modifier_list_keeps_its_action_note(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        import app
        from tests_analysis_async import initial
        state=initial()
        for source,expected in (('こうしてほぞん','こうして保存'),
                                ('そうしてほぞん','そうして保存')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
    def test_conjunction_does_not_supply_an_unknown_or_unfinished_action(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        for source in ('そうしてぷねら','こうしてほぞんし','ぷねらほぞん'):
            with self.subTest(source=source):
                self.assertFalse(R.native_action_note_introduction(source))
                self.assertFalse(R.completed_native_action_note(source,require_link=False))

    def test_attested_modifier_note_finishes_its_whole_action_word(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        import app
        from tests_analysis_async import initial
        state=initial()
        for source,expected in (('しかしほぞん','しかし保存'),
                                ('またほぞん','また保存'),('まずほぞん','まず保存'),
                                ('それからほぞん','それから保存')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
    def test_note_spelling_keeps_kana_choice_and_unresolved_source(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        import app
        from tests_analysis_async import initial
        state=initial()
        def line(source):
            return app.correct_line(source,state.store,input_method='kana',
                dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:rd if rd=='ほぞん' else None):
            self.assertEqual(line('まずほぞん')['corrected'],'まずほぞん')
        for source in ('文字列「まずほぞん」','またほぞんし'):
            self.assertEqual(line(source)['corrected'],source)
        source='しかしぷねら';result=line(source)
        self.assertEqual(result['corrected'],source);self.assertTrue(result['odd_spans'])

    def test_source_grammar_can_list_unrelated_actions_without_licensing_candidates(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        for text in ('とうろくしてさんぽ','そうじしてべんきょう','かくにんしてにゅうよく'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_action_note(text,require_link=False))
                self.assertFalse(R.completed_native_action_note(text))
                self.assertIn((0,len(text)),R.native_context_ranges(text))
        for text in ('とうろくしさんぽ','とうろくしたさんぽ','とうろくしてさんぽしたます',
                     'とうろくしてしらゆほ','りんごをにゅうりょくしてさんぽ',
                     'がぞうにほぞんしてさんぽ'):
            self.assertFalse(R.completed_native_action_note(text,require_link=False),text)

    def test_original_unrelated_tasks_keep_their_actions_without_anomaly(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for text,expected in (('とうろくしてさんぽ','登録して散歩'),
                              ('そうじしてべんきょう','掃除して勉強')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result['odd_spans'])
        self.assertEqual(a.store.revision(),revision)


    def test_classified_compound_action_reuses_native_suffix_and_suru(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        from contextual_repair import _allows_grammatical_tail,_productive_predicate
        self.assertEqual(M.native_sahen_compound_reading('暗号化'),'あんごうか')
        self.assertEqual(M.dictionary_inflections('暗号化'),())
        self.assertIn('暗号化',R.native_bare_action_faces('あんごうか'))
        self.assertTrue(S.classified_nominal_action('暗号化','あんごうか'))
        self.assertFalse(S.classified_nominal_action('暗号化','あんごか'))
        for tail in ('して','します','しました','しません','すれば'):
            self.assertTrue(_allows_grammatical_tail((),tail,'あんごうか','暗号化'),tail)
            self.assertTrue(_productive_predicate('暗号化'+tail,'暗号化'),tail)
        for tail in ('ました','しますした','されば'):
            self.assertFalse(_productive_predicate('暗号化'+tail,'暗号化'),tail)
        self.assertFalse(M.native_sahen_compound_reading('資料化'))
        self.assertFalse(M.native_sahen_compound_reading('プネラ化'))
        self.assertTrue(R.completed_native_action_note('あんごうかしてほぞん'))

    def test_unchanged_compound_action_reaches_original_application_guard(self):
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for text in ('あんごうかしてほぞん','あんごうかします','暗号化して保存'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result['odd_spans'],text)
        self.assertEqual(a.store.revision(),revision)



    @unittest.skipUnless(M.HAS_JANOME,'requires native attachment grammar')
    def test_readable_tokens_cannot_certify_a_broken_sahen_attachment(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        a=initial();tok=C.make_tokenizer(a.store)
        for source,bad,reading in (('かくりんしてほぞん','隔離んしてほじん','かくりんしてほじん'),
                                  ('かくにんしうほぞんしてしゅうりょう','確認しほうぞんしてしゅうりょう','かくにんしほうぞんしてしゅうりょう')):
            target=next(t for t in Q.targets_for_line(source,tok,a.store,a.dict_index) if t.boundary_kind=='sahen_tail')
            self.assertEqual(Q.validate(target,bad,C,tok,a.store,a.dict_index,a.decisions,
                expected_reading=reading),(False,'unproven_sahen_attachment'))

if __name__=='__main__':unittest.main()
