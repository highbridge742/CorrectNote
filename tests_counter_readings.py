# -*- coding: utf-8 -*-
"""Native numeral/counter identity and conventional allomorphs preserve kana."""
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('個'), 'requires native dictionary')
class CounterReadingTests(unittest.TestCase):
    def test_regular_composition_and_counter_specific_sound_changes(self):
        readings=R.native_counter_readings()
        for reading,face in (('ごこ','五個'),('じゅうごこ','十五個'),
            ('にじゅういっこ','二十一個'),('ろっこ','六個'),('じっこ','十個'),
            ('さんぼん','三本'),('ろっぽん','六本'),('よんじゅっぽん','四十本'),
            ('ろくさつ','六冊'),('さんまい','三枚'),('にだい','二台'),
            ('ふたり','二人'),('じゅうよにん','十四人'),('にじゅういちにん','二十一人')):
            with self.subTest(reading=reading):self.assertIn(face,readings[reading])
        for reading in ('いちこ','さんぽん','ろっさつ','にじゅうひとり','さんこまい'):
            with self.subTest(reading=reading):self.assertNotIn(reading,readings)
        # An unsupported large numeral has no affirmative proof, rather than
        # being classified as abnormal solely because this table omits it.
        self.assertNotIn('ひゃくごこ',readings)

    def test_quantity_keeps_the_unchanged_nominal_head(self):
        for text,head in (('ごこのきのう','機能'),('さんさつのほん','本'),
                          ('にじゅういっこのはこ','箱')):
            with self.subTest(text=text):self.assertIn(head,R.native_nominal_phrase_faces(text))
        self.assertFalse(R.native_nominal_phrase_faces('ごこのしらゆほ'))
        self.assertFalse(R.native_nominal_phrase_faces('ごこまいのはこ'))
        self.assertIn('にじゅうよじ',R.native_clock_readings())
        self.assertIn('ごごしちじはん',R.native_clock_readings())
        self.assertNotIn('にじゅうごじ',R.native_clock_readings())

    def test_normal_quantity_and_homographic_words_are_preserved(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('ごこのきのうをつかいます。','にじゅういっこのはこをはこびます。',
                     'さんさつのほんをかいます。','さんぼんのえんぴつをかいます。',
                     'にじゅういちにんのせいとがいます。','日本の風景を描きます。',
                     '昨日の天気を調べます。','この機能を使います。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions,input_method='kana')
                self.assertEqual(r['corrected'],text);self.assertEqual(r['odd_spans'],[])

    def test_proved_quantity_noun_is_not_an_unrelated_auxiliary_chain(self):
        import oddness as O
        text='さんまいのしりょうをよみます。'
        self.assertTrue(O.changed_auxiliary_chain_allowed(text,5,9))
        # The nominal proof stops before the predicate and does not
        # excuse a genuinely broken past-auxiliary connection after it.
        broken='さんまいのしりょうを買おき。'
        self.assertFalse(O.changed_auxiliary_chain_allowed(broken,10,13))

    def test_adjacent_substitution_and_intrusion_repair_the_same_reading(self):
        import app
        from tests_analysis_async import initial
        from kana_layout import single_key_drop_adjacency,single_key_drop_is_duplicate
        a=initial();a.context_vec=None
        expected='さんまいのしりょうをよみます。'
        intrusion='さんまいのしりょいうをよみます。'
        self.assertTrue(single_key_drop_adjacency(intrusion,expected))
        self.assertFalse(single_key_drop_is_duplicate(intrusion,expected))
        for text in ('さんまいのしりょいをよみます。',intrusion):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions,input_method='kana')
                # 48-AJF also compares the grammatical lexical repair 資料.
                # Both preserve the intended noun; unchanged kana sources
                # are still required to remain byte-for-byte above.
                self.assertIn(r['corrected'],(expected,expected.replace('しりょう','資料')))
                self.assertEqual(r['odd_spans'],[])


if __name__=='__main__':unittest.main()
