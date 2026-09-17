# -*- coding: utf-8 -*-
"""Verified phonetics, unchanged variant words and complete native tails."""
import unittest
import morphology

@unittest.skipUnless(morphology.HAS_JANOME,'native Janome dictionary')
class NativeReadingDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial()

    def correct(self,text,decisions=None):
        import app
        return app.correct_line(text,self.a.store,input_method='kana',
            dict_index=self.a.dict_index,decisions=decisions or self.a.decisions)

    def test_verified_on_readings_are_not_word_evidence(self):
        from kanji_onkun import readings_of
        for ch in '桿灌莞諫邯銜檻鉗':
            with self.subTest(character=ch):
                self.assertIn('かん',readings_of(ch))
                result=self.correct('あります'+ch)
                self.assertEqual(result['corrected'],'ありますか')
                self.assertFalse(result['odd_spans'])
        # 閂 means the bar of a gate; its reading is not kan.
        self.assertNotIn('かん',readings_of('閂'))
        self.assertEqual(self.correct('閂を閉めます。')['corrected'],'閂を閉めます。')

    def test_variant_words_keep_their_original_characters(self):
        for text in ('畑に灌水します。','君主に諫言します。','田を灌漑する。',
                     '船を繫留します。','港で繫船します。','鷗を見た。'):
            with self.subTest(text=text):
                parts=morphology.tokenize(text)
                self.assertEqual(''.join(t.surface for t in parts),text)
                self.assertTrue(all(text[t.start:t.end]==t.surface for t in parts))
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
        for text in ('灌 水します。','諫 言します。','灌あ水します。'):
            self.assertNotIn('灌水',[t.surface for t in morphology.tokenize(text)])
            self.assertNotIn('諫言',[t.surface for t in morphology.tokenize(text)])

    def test_same_reading_is_not_orthographic_identity(self):
        from kanji_onkun import orthographic_variants
        self.assertIn('潅水',orthographic_variants('灌水'))
        self.assertNotIn('冠水',orthographic_variants('灌水'))
        self.assertNotIn('還元',orthographic_variants('諫言'))
        self.assertFalse(orthographic_variants('制度'))

    def test_native_voice_spelling_is_retained(self):
        from reading_segments import intact_native_reading
        for text in ('ほんをよんでくださぃ。','しりょうをよんでくださぃ。',
                     'まどをあけてくださぃ。','おちゃをのんでくださぃ。'):
            with self.subTest(text=text):
                self.assertTrue(intact_native_reading(text))
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
        self.assertFalse(intact_native_reading('ほんをよむでくださぃ。'))
        self.assertFalse(intact_native_reading('みかんをよんでくださぃ。'))

    def test_native_excess_and_manner_connections(self):
        from contextual_repair import _productive_predicate
        from reading_segments import intact_native_reading
        for text,head in (('のみすぎないようにします','のみ'),
                          ('よむようにしています','よむ')):
            self.assertTrue(_productive_predicate(text,head))
        for text,head in (('のむすぎます','のむ'),('よんすぎます','よん'),
                          ('よみますようにします','よみ'),
                          ('よむようにしせます','よむ')):
            self.assertFalse(_productive_predicate(text,head))
        for text in ('おちゃをのみすぎないようにします。','なさすぎます。',
                     'よさすぎます。','静かすぎます。'):
            with self.subTest(text=text):
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
        self.assertFalse(intact_native_reading('ほんをのむようにします。'))

    def test_rare_character_repair_obeys_user_rejection(self):
        from decisions import DecisionStore
        ledger=DecisionStore();ledger.reject('ます灌','ますか')
        self.assertEqual(self.correct('あります灌',ledger)['corrected'],'あります灌')
        result=self.correct('あります灌')
        self.assertTrue(result['spans'])
        self.assertTrue(all(0<=a<b<=len('あります灌') for a,b in result['spans']))
        self.assertIn(('ます灌','ますか','かな入力'),result['details'])


    def test_compound_case_keeps_a_native_locative_verb(self):
        from reading_segments import completed_native_reading_clause
        for text in ('そのはこはここにおいてあります。',
                     'そのほんはそこにおいてあります。',
                     'このはこをここにおいてください。',
                     '学校において行事を行う。'):
            with self.subTest(text=text):
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
        self.assertFalse(completed_native_reading_clause('ここにおいてますます。'))

    def test_excess_repair_keeps_the_original_adjective(self):
        for original,expected in (
            ('たかいすぎます。','たかすぎます。'),
            ('やすいすぎます。','やすすぎます。'),
            ('おおきいすぎます。','おおきすぎます。'),
            ('ちいさいすぎます。','ちいさすぎます。'),
            ('あついすぎます。','あつすぎます。'),
            ('高いすぎます。','高すぎます。'),
            ('大きいすぎます。','大きすぎます。'),
            ('小さいすぎます。','小さすぎます。')):
            with self.subTest(original=original):
                result=self.correct(original)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(self.correct(expected)['corrected'],expected)
        for text in ('高い杉です。','大きい杉を見ました。','安い椅子を買います。',
                     '静かすぎます。','やすすぎます。','なさすぎます。'):
            with self.subTest(normal=text):
                self.assertEqual(self.correct(text)['corrected'],text)

    def test_grammatical_repeat_does_not_enable_extra_key_deletion(self):
        import corrector
        from reading_segments import native_degree_expression
        self.assertTrue(native_degree_expression('やすすぎます'))
        self.assertTrue(corrector._native_degree_repeat('やすすぎます。',2))
        self.assertFalse(corrector._native_degree_repeat('やすすすぎます。',2))
        tok=corrector.make_tokenizer(self.a.store)
        for original,repaired,reason in (
            ('もんじにゅうりょく','もじにゅうりょく','nonadjacent_original_key_deletion'),
            ('やすすすぎます','やすすぎます','duplicate_repair_disabled')):
            with self.subTest(original=original):
                accepted,why=corrector._check_replacement(original,
                    (0,len(original),repaired,'かな入力'),self.a.store,tok,self.a.dict_index)
                self.assertIsNone(accepted)
                self.assertEqual(why,reason)

    def test_adnominal_topic_requires_an_actual_following_predicate(self):
        from particle_frames import adnominal_topic_frames
        for original,expected in (
            ('きりがないようなも思えます。','きりがないようにも思えます。'),
            ('そのようなも感じます。','そのようにも感じます。'),
            ('不思議なようなも見えます。','不思議なようにも見えます。'),
            ('そのようなは思えません。','そのようには思えません。')):
            with self.subTest(original=original):
                result=self.correct(original)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(self.correct(expected)['corrected'],expected)
        for text in ('きりがないようなものです。','そのようなものも見ました。',
                     'そのようなもんです。','きりがないようなも','そのようなも、',
                     'そのようなもという文字列。','静かな森を歩きます。',
                     '「そのようなも」と書きました。'):
            with self.subTest(normal=text):
                self.assertFalse(adnominal_topic_frames(text))
                self.assertEqual(self.correct(text)['corrected'],text)

    def test_adverbial_particle_correction_obeys_the_same_ledger(self):
        from decisions import DecisionStore
        text='そのようなも思えます。'
        ledger=DecisionStore();ledger.reject('なも','にも')
        self.assertEqual(self.correct(text,ledger)['corrected'],text)
        result=self.correct(text)
        self.assertIn(('な','に','かな入力'),result['details'])
        self.assertTrue(all(0<=a<b<=len(text) for a,b in result['spans']))

    def test_legacy_reading_rank_and_following_clause(self):
        import corrector
        from vocabulary import find_known_readings_flex
        tok=corrector.make_tokenizer(self.a.store)
        for original,expected in (
            ('明日の会期是は午前十時から始まります。','明日の会議は午前十時から始まります。'),
            ('明日の会期背は午前十時から始まります。','明日の会議は午前十時から始まります。'),
            ('キーを売つ。','キーを打つ。'),
            ('結果を記録まして資料を閉じます。','結果を記録して資料を閉じます。'),
            ('文章を入力まして内容を確認します。','文章を入力して内容を確認します。')):
            with self.subTest(original=original):
                result=corrector.correct_line(original,self.a.store,tok,find_known_readings_flex,
                    input_method='kana',dict_index=self.a.dict_index)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(self.correct(original)['corrected'],expected)

    def test_written_object_keeps_its_negative_degree_predicate(self):
        for text in ('お茶を飲まなさすぎます。','紅茶を飲まなさすぎます。',
                     '麦茶を飲まなさすぎます。','本を読まなさすぎます。',
                     '本を読まなすぎます。','本を読みすぎないようにします。'):
            with self.subTest(text=text):
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])

    def test_written_object_cannot_borrow_another_objects_meaning(self):
        from reading_segments import completed_written_object_clause
        for text in ('お茶を読みます。','本を飲まなさすぎます。',
                     'お茶を飲むすぎます。','本を読みますです。',
                     'お茶を読むようにします。','未知単語を飲みます。','キーを売つ。'):
            with self.subTest(text=text):
                self.assertFalse(completed_written_object_clause(text))

    def test_degree_subject_does_not_turn_nasa_into_another_verb(self):
        from reading_segments import native_degree_subject_clause
        for text in ('仕事がなさすぎます。','時間がなさすぎます。',
                     '水が足りなさすぎます。','人が来なさすぎます。',
                     'この仕事がなさすぎます。','この本を読まなさすぎます。',
                     'この人は来なさすぎます。','この本も読まなさすぎます。',
                     '値段が高すぎます。','しごとがなさすぎます。'):
            with self.subTest(text=text):
                self.assertEqual(self.correct(text)['corrected'],text)
                self.assertFalse(self.correct(text)['odd_spans'])
        for text in ('本が飲みすぎます。','仕事がないすぎます。','仕事がなさすぎ'):
            with self.subTest(text=text):
                self.assertFalse(native_degree_subject_clause(text))

    def test_completed_degree_ranges_keep_context_but_not_a_later_error(self):
        from reading_segments import native_degree_context_ranges
        for text in ('例えば、本を読まなさすぎます。','仕事がなさすぎますが、明日は調整します。',
                     '「水が足りなさすぎます」と書きました。','人が来なさすぎます。明日は調整します。'):
            with self.subTest(text=text):
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
        for text in ('仕事がないすぎます。','本が飲みすぎます。','キーを売つ。'):
            self.assertFalse(native_degree_context_ranges(text))
        text='本を読まなさすぎます。キーを売つ。'
        self.assertEqual(self.correct(text)['corrected'],'本を読まなさすぎます。キーを打つ。')
        ranges=native_degree_context_ranges(text)
        self.assertTrue(ranges)
        self.assertTrue(all(end<text.index('キー') for start,end in ranges))

    def test_native_written_excess_keeps_its_same_reading_and_original_spelling(self):
        for head in ('本を読まなさ過ぎます','水が足りなさ過ぎます','人が来なさ過ぎます',
                     '仕事が無さ過ぎます','この本を読み過ぎます','安過ぎます'):
            for text in (head+'。','例えば、'+head+'。'):
                with self.subTest(text=text):
                    result=self.correct(text)
                    self.assertEqual(result['corrected'],text)
                    self.assertFalse(result['odd_spans'])
        from contextual_repair import _native_negative_degree_predicate
        self.assertFalse(_native_negative_degree_predicate('読むなさ過ぎます','読む'))
        self.assertFalse(_native_negative_degree_predicate('読まなさ過ぎますです','読ま'))

if __name__=='__main__':unittest.main()
