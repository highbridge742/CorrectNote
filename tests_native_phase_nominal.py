# -*- coding: utf-8 -*-
"""An instantaneous event can have a before/after phase without ongoing time."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NativePhaseNominalTests(unittest.TestCase):
    def test_event_phase_keeps_the_same_native_noun_and_exact_suffix(self):
        for reading,word in (('さぎょうまえ','作業前'),('さぎょうご','作業後'),
                             ('とうちゃくまえ','到着前'),('とうちゃくご','到着後'),
                             ('しぼうまえ','死亡前'),('かんりょうご','完了後'),
                             ('かいものまえ','買い物前')):
            with self.subTest(text=reading):
                self.assertIn(word,R.native_temporal_nominal_faces(reading))
                self.assertIn(word,R.native_temporal_nominal_faces(word))
                self.assertIn(word,R.native_nominal_phrase_faces(reading))
                self.assertFalse(S.nominal_roles(word)&{'food','place','object'})
        for text in ('ぷねらまえ','ぷねらご','りんごまえ','つくえご',
                     'しぼうちゅう','かんりょうちゅう','作業 前'):
            self.assertFalse(R.native_temporal_nominal_faces(text),text)

    def test_pending_action_is_a_state_noun_with_its_own_native_suffix(self):
        for reading,word in (('にゅうりょくまち','入力待ち'),('しゅつりょくまち','出力待ち'),
                             ('とうちゃくまち','到着待ち'),('へんじまち','返事待ち'),
                             ('しょうにんまち','承認待ち')):
            with self.subTest(text=reading):
                self.assertIn(word,R.native_waiting_nominal_faces(reading))
                self.assertIn(word,R.native_waiting_nominal_faces(word))
                self.assertIn(word,R.native_nominal_phrase_faces(reading))
                self.assertFalse(R.native_temporal_nominal_faces(reading))
                self.assertFalse(R.native_nominal_temporal_prefix(reading+'に'))
                self.assertFalse(S.nominal_roles(word)&{'food','place','object','time','process'})
        for text in ('ぷねらまち','ぷねら待ち','にゅうりょくまつ','にゅうりょくもち',
                     '入力 待ち','りんごまち','つくえまち'):
            self.assertFalse(R.native_waiting_nominal_faces(text),text)
        self.assertFalse(R.completed_native_reading_clause('にゅうりょくまちをたべます',require_object_fit=True))

    def test_pending_action_keeps_original_kana_and_following_clause_scope(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('にゅうりょくまち','にゅうりょくまちです。','しゅつりょくまちです。',
                     'とうちゃくまちです。','へんじまちでした。','しょうにんまちなのでほんをよみます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        self.assertFalse(R.intact_native_reading('にゅうりょくまちなのでぷねらをよみます'))

    def test_phase_adjunct_and_following_predicate_are_independent(self):
        for text in ('さぎょうまえに','さぎょうごに','とうちゃくごに','かいものまえに'):
            self.assertTrue(R.native_nominal_temporal_prefix(text),text)
        self.assertTrue(R.intact_native_reading('さぎょうまえにしりょうをほぞんします'))
        self.assertFalse(R.intact_native_reading('さぎょうまえにぷねらをほぞんします'))
        self.assertFalse(R.completed_native_reading_clause('さぎょうごをたべます',require_object_fit=True))
        self.assertFalse(R.native_nominal_temporal_prefix('しぼうちゅうに'))

    def test_normal_kana_phase_nouns_are_kept_literal_without_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('さぎょうまえ','さぎょうご','さぎょうまえです。','さぎょうごです。',
                     'さぎょうまえにしりょうをほぞんします。',
                     'かんりょうごにしりょうをほぞんします。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)


    def test_inchoative_noun_keeps_its_whole_attested_continuative(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('かきかけ','よみかけ','たべかけ','のみかけ','つくりかけ',
                     '書きかけ','読みかけ','食べかけ','書き掛け'):
            self.assertEqual(R.native_inchoative_nominal_faces(text),(text,))
            self.assertTrue(R._native_written_nominal_faces(text),text)
            self.assertFalse(S.nominal_roles(text)&{'food','call','text','drink'},text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('かきかけです','よみかけです','たべかけです'):
            self.assertTrue(R.completed_native_nominal_predicate(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('たべるかけ','よむかけ','ぷねらかけ','りんごかけ','かききれ','かきかける'):
            self.assertFalse(R.native_inchoative_nominal_faces(text),text)
        for text in ('たべるかけです','ぷねらかけです'):
            self.assertFalse(R.completed_native_nominal_predicate(text),text)

    def test_awaited_person_keeps_a_state_noun_without_person_roles(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ともだちまち','せんせいまち','友達待ち','先生待ち'):
            faces=R.native_waiting_nominal_faces(text)
            self.assertTrue(faces,text)
            self.assertFalse(any(S.nominal_roles(f)&{'person','food','object'} for f in faces),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('ぷねらまち','りんごまち','つくえまち'):
            self.assertFalse(R.native_waiting_nominal_faces(text),text)
        self.assertFalse(R.completed_native_reading_clause('ともだちまちをたべます',require_object_fit=True))

    def test_common_interface_and_spring_keep_roles_distinct_from_food(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('くりっぷぼーどをひらきます。','ばねをかいます。','ばねをはこびます。',
                     'ほぞんしたらばばねをかいます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('くりっぷぼーどをたべます','ばねをたべます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_classified_compound_host_and_later_loan_path_share_source_proof(self):
        import app,corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('いしまち','医師待ち','かんごしまち','看護師待ち',
                     '看護師待ちなので本を読みます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        source='看護師待ちなのでぷねらをよみるます。'
        spans=R.native_context_ranges(source)
        self.assertIn((0,5),spans)
        self.assertFalse(any(a==0 and b>=len(source)-1 for a,b in spans))
        self.assertFalse(R.intact_native_reading(source))
        self.assertFalse(R.native_written_nominal_ranges('ぷねら看護師待ち'))
        for source in ('事故の原因を絶命しました。','方法を絶命します。'):
            start=source.index('絶命')
            self.assertNotIn((start,start+2),R.native_written_nominal_ranges(source))
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source.replace('絶命','説明'))
            self.assertFalse(result.get('odd_spans'),source)
        for source in ('資料を死亡した人物が残しました。','人を死亡させる危険があります。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'),source)
        self.assertTrue(R.native_nominal_phrase_faces('いしまち'))
        self.assertTrue(C._chunk_is_intact('いしまち',tokenize))
        self.assertEqual(R._native_written_nominal_faces('看護師'),('看護師',))
        self.assertIn('看護師待ち',R.native_waiting_nominal_faces('かんごしまち'))
        for text in ('ぷねら師待ち','看護師 待ち','看護師たち待ち'):
            self.assertFalse(R.native_waiting_nominal_faces(text),text)

    def test_nominal_connector_keeps_its_source_scope_and_actual_pos(self):
        for prefix in ('にゅうりょくまちなので','とうちゃくまちだから',
                       '入力待ちなので','承認待ちだから'):
            source=prefix+'しりょうをほぞんしたます。'
            self.assertEqual(R.native_nominal_connective_boundaries(source),(len(prefix),))
            self.assertIn(len(prefix),R.native_completed_clause_boundaries(source))
            self.assertIn((0,len(prefix)),R.native_context_ranges(source))
            self.assertFalse(R.intact_native_reading(source))
        for source in ('入力待ちなのです。','入力待ちなのでしょう。','入力待ちなのである。',
                       'ぷねらなのでほんをよみまうす。','にゅうりょくまちだのでほんをよみまうす。',
                       'にゅうりょくまちますのでほんをよみまうす。','これからほんをよみます。'):
            self.assertFalse(R.native_nominal_connective_boundaries(source),source)
        self.assertFalse(R.completed_native_nominal_predicate('入力待ちな',connective='ので'))
        self.assertTrue(R.completed_native_nominal_predicate('入力待ちな',connective='ので',allow_written=True))

    def test_swallowed_later_clause_shares_anomaly_and_final_validation(self):
        import app,corrector as C,oddness as O
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        prefix='とうちゃくまちだから'
        bad=prefix+'しりょうをほぞんしたます。'
        marks=O.is_odd_run(bad,tokenize,with_spans=True,store=a.store,
                          dict_index=a.dict_index,complete_line=True)
        self.assertTrue(marks)
        self.assertTrue(all(len(prefix)<=lo<hi<=len(bad) for left,right,lo,hi in marks))
        for source,expected in (
                (bad,prefix+'しりょうをほぞんしてます。'),
                ('にゅうりょくまちなのでしりょうをほぞんしたます。','にゅうりょくまちなのでしりょうをほぞんしてます。'),
                ('しょうにんまちなのでしりょうをほぞんしたます。','しょうにんまちなのでしりょうをほぞんしてます。'),
                ('承認待ちだから資料をほぞんしたます。','承認待ちだから資料を保存してます。')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, expected)
            self.assertFalse(result.get('odd_spans'),source)
        for source in ('入力待ちなので本を読みます。','入力待ちなのです。',
                       '入力待ちなのでしょう。','入力待ちなのである。',
                       '入力待ちなので「よみまうす」と入力しました。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'),source)
        for source in ('入力待ちなのでほんをたべまうす。',
                       'とうちゃくまちだからほんをたべまうす。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)
            # Historical auxiliary style is not the semantic anomaly.
            self.assertFalse(R.intact_native_reading(source),source)
        source='にゅうりょくまちなのでもんじにゅうりょくをします。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],source)

if __name__=='__main__':unittest.main()
