# -*- coding: utf-8 -*-
"""Native nominalized adjectives and attributive endings share their grammar."""
import unittest
import morphology as M
import reading_segments as R
import oddness as O
import contextual_repair as CR
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('大き'),'requires native dictionary')
class NominalizedReadingTests(unittest.TestCase):
    def test_nominalized_attributes_are_readings_without_choosing_kanji(self):
        for text in ('おおきさ','ながさ','あつさ','たかさ','おもさ'):
            with self.subTest(text=text):
                self.assertIn(text,R.native_nominal_phrase_faces(text))
                self.assertIn('attribute',S.nominal_roles(text))
        for text in ('おおきと','たかいさ','ぷねらさ'):
            self.assertFalse(R.native_nominal_phrase_faces(text),text)
        self.assertTrue(R.completed_native_reading_clause('おおきさをかえます',
            require_nominal=True,require_object_fit=True))
        self.assertTrue(R.completed_native_reading_sequence('しゃしんをならべておおきさをかえます'))

    def test_past_auxiliary_cannot_follow_a_volitional_stem(self):
        for text in ('かおき','買おき'):
            parts=M.tokenize(text)
            legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in parts]
            self.assertEqual(len(legacy),2)
            self.assertTrue(O.past_auxiliary_mismatch(*legacy))
            self.assertFalse(CR._productive_predicate(text,parts[0].surface))
        for text in ('かおう','ありき','ありし','せし','かきし'):
            parts=M.tokenize(text)
            legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                     t.start,t.end,t.has_reading,t.infl_form) for t in parts]
            self.assertFalse(any(O.past_auxiliary_mismatch(a,b) for a,b in zip(legacy,legacy[1:])),text)

    def test_literary_finite_and_attributive_forms_are_distinct(self):
        for text in ('ありき','よみけり','かおき'):
            self.assertFalse(R.native_attributive_predicate_end(text),text)
        for text in ('ありし','よみける','せし','かきし','かった'):
            self.assertTrue(R.native_attributive_predicate_end(text),text)
        self.assertFalse(R.completed_native_reading_sequence('しゃしんをならべてかおきとをかえます'))

    def test_application_repairs_and_preserves_native_expressions(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        rows=[('しゃしんをならべておおきとをかえます。','しゃしんをならべておおきさをかえます。')]
        rows.extend((text,text) for text in (
            'しゃしんをならべておおきさをかえます。','ひものながさをはかります。',
            '温かさを感じます。','ありし日の写真を見ます。','本を買おう。',
            '本を買いました。'))
        for text,expected in rows:
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
