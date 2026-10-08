# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_result_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('冊'),'requires native dictionary')
class CountedNominalTests(unittest.TestCase):
    def test_ordinals_preserve_whole_native_reading_and_do_not_become_quantities(self):
        for reading,face in (('さんさつめ','三冊目'),('ふたりめ','二人目'),
                             ('にだいめ','二台目'),('ひとつめ','一つ目')):
            with self.subTest(reading=reading):
                self.assertIn(face,R.native_ordinal_readings()[reading])
                self.assertIn(face,R.native_nominal_phrase_faces(reading))
                self.assertNotIn(reading,R.native_counter_readings())
                self.assertNotIn('quantity',S.nominal_roles(face))
        for text in ('はんさつめ','さんさつはんめ','とおめ','さんさつめめ','しらゆほめ'):
            self.assertNotIn(text,R.native_ordinal_readings())

    def test_units_have_independent_meaning_and_original_case(self):
        for text in ('三冊','さんさつ','三冊目','さんさつめ','半冊'):
            with self.subTest(text=text):self.assertIn('text',S.nominal_roles(text))
        self.assertIn('device',S.nominal_roles('にだいめ'))
        self.assertIn('person',S.nominal_roles('二人目'))
        self.assertIn('quantity',S.nominal_roles('二冊'))
        for text in ('二本','二枚','二個','二つ','しらゆほ冊'):
            with self.subTest(text=text):self.assertNotIn('text',S.nominal_roles(text))
        for text in ('さんさつをよみます','さんさつめをよみます','にさつにわけます',
                     'ほんをにさつにわけます','ふたりめにてがみをわたします'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,require_nominal=True,
                    require_object_fit=True))
        for text in ('さんさつめをよみんす','さんさつめめをよみます','にほんをよみます'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_clause(text,require_nominal=True,
                    require_object_fit=True))

    def test_decimal_spellings_share_only_an_attested_complete_counter(self):
        for text,reading in (('2冊','にさつ'),('２冊','にさつ'),
                             ('2人','ふたり'),('２つ','ふたつ'),('2冊目','にさつめ')):
            self.assertIn(reading,R.native_counted_surface_readings()[text],text)
            tokens=M.tokenize(text)
            self.assertEqual(len(tokens),1,text)
            self.assertEqual(tokens[0].surface,text)
            self.assertEqual(tokens[0].reading,reading)
            self.assertTrue(tokens[0].has_reading)
        for text in ('2冊','２冊','二冊'):
            self.assertEqual(S.counted_object_roles(text),frozenset(('text','reference')))
        for text in ('2冊目','２冊目','二冊目'):
            self.assertIsNone(S.counted_object_roles(text))
            self.assertFalse(R._native_counter_prefixes(text+'からよみます',M.tokenize(text+'からよみます')))
        for text in ('2X冊','2.5冊','02冊','２X冊','第2冊','2 冊','やっつける'):
            self.assertNotIn(text,R.native_counted_surface_readings(),text)
        tokens=M.tokenize('子供に本を渡します')
        self.assertFalse(any(t.surface=='に本' for t in tokens))

    def test_large_digit_counts_keep_literal_value_without_a_guessed_reading(self):
        for quantity in ('0冊','00冊','100冊','１２３冊','1000冊'):
            self.assertEqual(S.counted_object_roles(quantity),frozenset(('text','reference')),quantity)
            self.assertNotIn(quantity,R.native_counted_surface_readings())
            self.assertTrue(R.native_object_predicate_proof('ほんを'+quantity+'よみます',3,('本',)))
            self.assertFalse(R.native_object_predicate_proof('ほんきを'+quantity+'ください',4,('本気',)))
        for quantity in ('100冊目','１２３冊目'):
            self.assertIsNone(S.counted_object_roles(quantity))
            self.assertFalse(R._native_counter_prefixes(quantity+'からよみます',M.tokenize(quantity+'からよみます')))
        for quantity in ('2X冊','2..5冊','2 冊','第100冊'):
            self.assertFalse(R.native_counted_nominal_evidence(quantity),quantity)
        tokens=M.tokenize('ほんを１２３冊よみます')
        self.assertFalse(any(t.surface=='２３冊' for t in tokens))
        for text in ('ほんを100冊しらゆほます','ほんを100冊かいなす'):
            self.assertFalse(R.native_object_predicate_proof(text,3,('本',)),text)

    def test_numeric_punctuation_does_not_split_a_proven_quantity(self):
        for quantity in ('1,000冊','１，０００冊','2.5冊','２．５冊','1,000.5冊'):
            self.assertEqual(S.counted_object_roles(quantity),frozenset(('text','reference')),quantity)
            source='ほんを'+quantity+'よみます'
            self.assertEqual(list(R._native_source_clauses(source+'。あと')),
                             [(0,source),(len(source)+1,'あと')])
            self.assertTrue(R.native_object_predicate_proof(source,3,('本',)),source)
            self.assertFalse(any(t.surface in ('5冊','５冊') for t in M.tokenize(source)),source)
        for quantity in ('1,00冊','1,,000冊','1,000,00冊','2..5冊','2.冊','.5冊','2.5冊目'):
            self.assertFalse(R.native_counted_nominal_evidence(quantity),quantity)
        self.assertEqual(list(R._native_source_clauses('ほんをよみます,あと')),
                         [(0,'ほんをよみます'),(8,'あと')])

    def test_written_large_kanji_counts_share_type_without_inventing_readings(self):
        for quantity in ('百冊','千冊','百二十三冊','一万冊','十二万三千冊','一億二万三千冊'):
            self.assertEqual(S.counted_object_roles(quantity),frozenset(('text','reference')),quantity)
            self.assertTrue(R.native_object_predicate_proof('ほんを'+quantity+'よみます',3,('本',)),quantity)
            self.assertFalse(R.native_object_predicate_proof('ほんきを'+quantity+'ください',4,('本気',)),quantity)
        for quantity in ('百百冊','十百冊','一万万冊','万一億冊','一万十百冊','数百冊','第三百冊'):
            self.assertFalse(R.native_counted_nominal_evidence(quantity),quantity)
        for quantity in ('百冊目','千冊目','一万冊目'):
            self.assertIsNone(S.counted_object_roles(quantity))
            self.assertFalse(R._native_counter_prefixes(quantity+'からよみます',M.tokenize(quantity+'からよみます')))

    def test_retired_neighbor_directions_do_not_return_as_physical_repairs(self):
        from contextual_repair import key_repairs,neighbor_shift_key_repairs
        # The semantic/counting fixtures below now use horizontal slips.
        # Retain these former vertical/diagonal slips as negative controls.
        for original,wanted in (('よみまぇ','よみます'),('つやいます','つかいます'),
                                ('はまして','さまして')):
            with self.subTest(original=original):
                self.assertNotIn(wanted,{r.reading for r in key_repairs(original)})
                self.assertNotIn(wanted,{r.reading for r in neighbor_shift_key_repairs(original)})
        for original,wanted in (('よみまか','よみます'),('つすいます','つかいます'),
                                ('そまして','さまして')):
            with self.subTest(original=original):
                self.assertIn(wanted,{r.reading for r in key_repairs(original)})

    def test_normal_and_adjacent_repairs_share_counted_noun_evidence(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('さんさつめをよみます。','さんさつめをよみます。'),
            ('ほんをにさつにわけます。','ほんをにさつにわけます。'),
            ('ふたりめにてがみをわたします。','ふたりめにてがみをわたします。'),
            ('さんさつめをよみまか。',('さんさつめを読みます。','さんさつめをよみます。')),
            ('にだいめをつすいます。','にだいめを使います。'),
            ('二枚目は俳優です。','二枚目は俳優です。'),
            ('一つ目の妖怪です。','一つ目の妖怪です。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                assert_reviewed_result_spelling(self, result, expected)
                self.assertEqual(result['odd_spans'],[])


if __name__=='__main__':unittest.main()
