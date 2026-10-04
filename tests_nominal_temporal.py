# -*- coding: utf-8 -*-
"""A source adjunct edge does not approve its unexplained following text."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('前'), 'requires native dictionary')
class NominalTemporalTests(unittest.TestCase):
    def test_nominal_reading_and_both_particles_are_required(self):
        # ANH: native action+前 is also a temporal noun; the old isolated
        # genitive rule's negative かいものまえに is now a positive control.
        for text in ('かいもののまえに','しょくじのあとに','かいぎののちに',
                     'つくえのまえに','もののまえに','かいものまえに'):
            with self.subTest(text=text):self.assertTrue(R.native_nominal_temporal_prefix(text))
        for text in ('ぷねらのまえに','かいもののまえを',
                     'かいもののぜんに','かいもののごに','のまえに',
                     'かったのまえに','かうのあとに','かいもののまえには'):
            with self.subTest(text=text):self.assertFalse(R.native_nominal_temporal_prefix(text))

    def test_same_edge_exposes_only_the_actual_following_nominal_frame(self):
        text='かいもののまえにさいふをたしかめます'
        self.assertIn(8,R.native_adverbial_reading_cuts(text))
        self.assertIn((8,12,('財布',)),R.native_object_predicate_contexts(text))
        self.assertIn((8,12),R.native_context_ranges(text))
        text='しょくじのあとにしりょうをよみます'
        self.assertIn(8,R.native_adverbial_reading_cuts(text))
        self.assertIn((8,13),R.native_context_ranges(text))

    def test_adjunct_does_not_certify_unknown_nouns_or_broken_predicates(self):
        for text in ('かいもののまえにぷねらをたしかめます',
                     'かいもののまえにさいふをたしかます'):
            with self.subTest(text=text):
                self.assertFalse(R.intact_native_reading(text))
                self.assertNotIn((0,len(text)),R.native_context_ranges(text))
        self.assertNotIn(9,R.native_adverbial_reading_cuts('ぷねらもののまえにさいふをたしかめます'))

    def test_application_retains_normal_source_without_false_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('かいもののまえにさいふをたしかめます。',
                     'しょくじのあとにしりょうをよみます。',
                     'つくえのまえにほんをならべます。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], text)
                self.assertEqual(result.get('odd_spans'),[])


    def test_standalone_adverbial_time_noun_keeps_its_case(self):
        for text in ('あさに','よるに','ごぜんに','ごごに'):
            self.assertTrue(R.native_nominal_temporal_prefix(text),text)
        for text in ('ぷねらに','しりょうに','へやに','あさを','あさには'):
            self.assertFalse(R.native_nominal_temporal_prefix(text),text)
        text='あさにつくったしりょうをせんせいにおきります'
        self.assertIn(3,R.native_adverbial_reading_cuts(text))
        # The old fixture assumed 資料 was the only same-reading noun.
        # The source modifier may also fit 史料; keep 資料 as evidence too.
        # A proved 朝に adjunct can now stay inside the whole relative
        # noun phrase (朝に作った資料), or precede the shorter same frame.
        # Both retain the original object endpoint and the malformed tail.
        self.assertTrue(any(begin in (0,3) and cut==12 and '資料' in faces
                            for begin,cut,faces in R.native_object_predicate_contexts(text)))
        self.assertFalse(R.intact_native_reading(text))

    def test_temporal_limit_keeps_the_following_object_independent(self):
        for text in ('あしたまでに','きょうまでに','よるまでに','らいしゅうまでに'):
            self.assertTrue(R.native_nominal_temporal_prefix(text),text)
        for text in ('がっこうまでに','しりょうまでに','ぷねらまでに','までに','あしたまでには','あしたに','らいしゅうに'):
            self.assertFalse(R.native_nominal_temporal_prefix(text),text)
        text='あしたまでにぶんしょうをなおします'
        self.assertIn(6,R.native_adverbial_reading_cuts(text))
        self.assertTrue(any(begin==6 and cut==12 and '文章' in heads
            for begin,cut,heads in R.native_object_predicate_contexts(text)))
        for text in ('あしたまでにぷねらをなおします','あしたまでにぶんしょうをなおしなす'):
            self.assertFalse(R.intact_native_reading(text),text)
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('あすたまでにぶんしょうをなおします。','あそたまでにぶんしょうをなおします。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, 'あしたまでにぶんしょうをなおします。')
            self.assertFalse(result['odd_spans'])

    def test_source_time_and_recipient_survive_the_action_repair(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for time in ('あさに','よるに'):
            text=time+'つくったしりょうをせんせいにおきります。'
            expected=text.replace('おきります','おくります')
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, expected)
            self.assertEqual(result.get('odd_spans'),[],text)
            normal=app.correct_line(expected,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, normal['corrected'], expected)
            self.assertEqual(normal.get('odd_spans'),[],expected)


    def test_ongoing_nominal_has_temporal_adjunct_not_arbitrary_time_object_role(self):
        import semantic_roles as S
        for text in ('にゅうりょくちゅうに','さぎょうちゅうに','べんきょうちゅうに'):
            self.assertTrue(R.native_nominal_temporal_prefix(text),text)
        for text in ('しぼうちゅうに','かんりょうちゅうに','ぷねらちゅうに',
                     'にゅうりょくじゅうに','にゅうりょくちゅうを','にゅうりょくちゅうまでに'):
            self.assertFalse(R.native_nominal_temporal_prefix(text),text)
        self.assertNotIn('time',S.nominal_roles('入力中'))
        self.assertFalse(R.completed_native_reading_clause('にゅうりょくちゅうをのみます',require_object_fit=True))
        for text,cut in (('にゅうりょくちゅうにとまりました',10),
                         ('にゅうりょくちゅうもほぞんします',10),
                         ('さぎょうちゅうはしずかです',8)):
            self.assertIn(cut,R.native_adverbial_reading_cuts(text),text)
            self.assertTrue(R.intact_native_reading(text),text)

    def test_ongoing_time_adjunct_keeps_unknown_following_argument_unproved(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('にゅうりょくちゅうにとまりました。','にゅうりょくちゅうもほぞんします。',
                     'さぎょうちゅうはしずかです。','にゅうりょくちゅうほぞんします。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('にゅうりょくちゅうにぷねらをよみます',
                     'にゅうりょくちゅうにほんをよみるます'):
            self.assertFalse(R.intact_native_reading(text),text)

    def test_explicit_deadline_particle_does_not_make_ordinary_nouns_bare_adverbs(self):
        import semantic_roles as S,app
        from tests_analysis_async import initial
        for noun in ('期限','締切','締切り','締め切り','デッドライン','タイムリミット'):
            self.assertIn('time',S.nominal_roles(noun),noun)
            self.assertFalse(S.support(noun,'食べる'),noun)
        self.assertNotIn('time',S.nominal_roles('閉め切り'))
        for text in ('しめきりまでに','きげんまでに','きじつまでに','きじつに'):
            self.assertTrue(R.native_nominal_temporal_prefix(text),text)
        for text in ('がめんまでに','ぷねらまでに','にゅうりょくちゅうまでに'):
            self.assertFalse(R.native_nominal_temporal_prefix(text),text)
        self.assertFalse(R._native_adverbial_faces('しめきり'))
        a=initial()
        for text in ('しめきりまでにしりょうをほぞんします。','きげんまでにしりょうをほぞんします。',
                     'きじつにしりょうをほぞんします。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'),text)
        self.assertFalse(R.intact_native_reading('しめきりまでにぷねらをほぞんします'))

    def test_relative_time_shares_native_ending_and_written_argument_proof(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('しりょうをほぞんしたときにれんらくします。',
                     '資料を保存したときに連絡します。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], text)
                self.assertEqual(result.get('odd_spans'),[])
        self.assertTrue(R.native_object_predicate_proof('資料を保存したときに連絡します',3,('資料',)))
        self.assertFalse(R.native_object_predicate_proof('患者を保存したときに連絡します',3,('患者',)))
        for text in ('しりょうをほぞんしてときにれんらくします',
                     'しりょうをほぞんしときにれんらくします',
                     'しりょうをほぞんしですときにれんらくします',
                     'しりょうをほぞんしたときにぷねらます'):
            self.assertFalse(R.completed_native_temporal_clause(text),text)


    def test_only_the_proved_temporal_ni_is_shared_with_written_case_validation(self):
        for text in ('資料を保存したときに寝ます','資料を読んだときに寝ます',
                     '資料を保存した後に寝ます','資料を保存する前に寝ます',
                     '資料を保存したときに歩きます',
                     '資料を保存したときに本を友人に貸しました'):
            self.assertTrue(R.native_object_predicate_proof(text,3,('資料',)),text)
        for text in ('資料を保存したときに本を友人に課しました',
                     '資料を保存したときに本を紙に貸しました',
                     '資料を保存してときに寝ます'):
            self.assertFalse(R.native_object_predicate_proof(text,3,('資料',)),text)

if __name__=='__main__':unittest.main()
