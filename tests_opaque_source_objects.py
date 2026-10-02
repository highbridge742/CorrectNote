# -*- coding: utf-8 -*-
"""An unknown source name supplies no word or candidate completion proof."""
import unittest
from unittest.mock import patch

import corrector as C
import contextual_repair as Q
import oddness as O
import pos_grammar as P
import reading_segments as R
from tests_analysis_async import initial


class OpaqueSourceObjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = initial()
        cls.tok = staticmethod(C.make_tokenizer(cls.a.store))

    def test_original_case_and_finite_predicate_keep_unknown_name_out_of_search(self):
        for text in ('ぷねらを保存します。', 'ぷねらをよみます。',
                     'ぷねらを保存した。', 'ぷねらを保存している。'):
            with self.subTest(text=text):
                self.assertTrue(R.source_opaque_object_ranges(text))
                self.assertFalse(O.odd_spans(text, self.tok,
                    store=self.a.store, dict_index=self.a.dict_index,
                    preserve_unknown_source=True))
                self.assertFalse(P.odd_kana_spans(text, self.a.dict_index, self.a.store))
                token = C._CORRECTION_SOURCE.set(text)
                try:
                    self.assertTrue(C._chunk_is_intact(text[:-1], self.tok))
                    self.assertTrue(C._chunk_is_intact('ぷねら', self.tok))
                finally:
                    C._CORRECTION_SOURCE.reset(token)
                self.assertFalse(Q.targets_for_line(text,self.tok,self.a.store,self.a.dict_index))

    def test_unchanged_unknown_is_not_a_completed_generated_word(self):
        text = 'ぷねらを保存します。'
        self.assertFalse(R.native_surface_nominal_heads('ぷねら'))
        self.assertTrue(O.odd_spans(text,self.tok,store=self.a.store,dict_index=self.a.dict_index))
        self.assertTrue(P.odd_kana_spans(text,self.a.dict_index,self.a.store,
                                       preserve_unknown_source=False))
        self.assertFalse(Q._productive_predicate(text[:-1], 'ぷねら'))

    def test_malformed_and_incomplete_predicates_supply_no_protection(self):
        for text in ('ぷねらをよむます。', 'ぷねらを保存だました。',
                     'ぷねらを保存するたら。', 'ぷねらを保存すると。',
                     'ぷねらを保存したら。', 'ぷねらを保存し。',
                     'ぷねらを保存。', 'ぷねらを資料。', 'もじにゅうりをく',
                     'ぷねらをを読みます。', 'ぷねらをふを読みます。'):
            with self.subTest(text=text):
                self.assertFalse(R.source_opaque_object_ranges(text))
        text = 'ぷねらを保存だました。'
        self.assertTrue(O.odd_spans(text,self.tok,store=self.a.store,
            dict_index=self.a.dict_index,preserve_unknown_source=True))

    def test_actual_predicate_must_independently_attest_the_accusative(self):
        for predicate in ('眠ります','眠る','生きます','繁栄します','休む'):
            with self.subTest(predicate=predicate):
                self.assertFalse(R.source_opaque_object_ranges('ぷねらを'+predicate+'。'))
        for predicate in ('通ります','見つけます','探します'):
            with self.subTest(predicate=predicate):
                self.assertTrue(R.source_opaque_object_ranges('ぷねらを'+predicate+'。'))

    def test_unchanged_kana_sahen_has_the_same_finite_predicate_evidence(self):
        for tail in ('ほぞんします','ほぞんした','ほぞんする','ほぞんしない',
                     'ほぞんしましたか','ほぞんするよ','ほぞんしよう',
                     'かくにんします','へんしゅうします'):
            text='ぷねらを'+tail+'。'
            with self.subTest(text=text):
                self.assertTrue(R.source_opaque_object_ranges(text))
                self.assertFalse(P.odd_kana_spans(text,self.a.dict_index,self.a.store))
                self.assertTrue(P.odd_kana_spans(text,self.a.dict_index,self.a.store,
                    preserve_unknown_source=False))

    def test_sahen_reading_does_not_complete_unknown_open_or_malformed_tails(self):
        for tail in ('ほぞんしたら','ほぞんして','ほぞんし','ほぞんだました',
                     'ほぞんするたら','ほぞんするた','ほぞんしだら',
                     'ほぞんしてが','はってんします','ぬめるします'):
            with self.subTest(tail=tail):
                self.assertFalse(R.source_opaque_object_ranges('ぷねらを'+tail+'。'))

    def test_unfinished_mora_is_not_certified_by_an_opaque_noun_boundary(self):
        for noun in ('ゅしうかいどう','ょちうせい','ぇふすてぃばる','ぴっぁ','ぴつっぁ'):
            with self.subTest(noun=noun):
                self.assertFalse(R.source_opaque_object_ranges(noun+'をみます。'))
        # Names with ordinary mora boundaries do not become dictionary words.
        for noun in ('ぷねら','ぴむね','ぷにめろ','ぴこるん'):
            with self.subTest(noun=noun):
                self.assertTrue(R.source_opaque_object_ranges(noun+'を保存します。'))

    def test_final_validation_preserves_same_source_across_edit_widths(self):
        text = 'ぷねらを保存します。'
        for start,end,surface in ((0,3,'ぶねら'),(0,len(text),'ぶねらを保存します。')):
            with self.subTest(end=end):
                candidate,reason=C._check_replacement(text,(start,end,surface,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((start,end),))
                self.assertIsNone(candidate)
                self.assertEqual(reason,'opaque_original_object')
        source = '資料を保存だました。ぷねらを保存します。'
        self.assertTrue(R.preserves_opaque_source_object(source,
            '資料を保存しました。ぷねらを保存します。'))
        # Two separate edits must both inspect the same source ranges.
        self.assertFalse(R.preserves_opaque_source_object(source,
            '資料を保存しました。ぷねらを保存する。'))
        source = 'ぷねらを読んだ。ぷねらを保存します。'
        self.assertFalse(R.preserves_opaque_source_object(source,
            'ぷねらを読んだ。ぶねらを保存します。'))


    def test_independent_native_prefix_keeps_the_whole_unchanged_source(self):
        for prefix in ('あとで','あした','ひとりで','じぶんで','ほぞんしたら',
                'しりょうをほぞんしたら','ほぞんすれば','ほぞんして','ほぞんしたので'):
            text=prefix+'ぴむねをよみます。'
            with self.subTest(text=text):
                self.assertIn((0,len(prefix)+4,len(text)-1),R.source_opaque_object_ranges(text))
                self.assertFalse(P.odd_kana_spans(text,self.a.dict_index,self.a.store))
                self.assertFalse(Q.targets_for_line(text,self.tok,self.a.store,self.a.dict_index))

    def test_an_opaque_noun_cannot_absorb_the_rest_of_a_proved_longer_adjunct(self):
        for prefix in ('しゅっぱつまえに','しゅっぱつごに','とうちゃくまえに','とうちゃくごに'):
            with self.subTest(prefix=prefix):
                self.assertFalse(R.source_opaque_object_ranges(prefix+'しゃしまをならべます。'))
                self.assertTrue(R.source_opaque_object_ranges(prefix+'ぴむねをならべます。'))

    def test_unknown_source_does_not_complete_a_bad_prefix_or_predicate(self):
        for text in ('ほぞんするたらぴむねをよみます。','ほぞんしてがぴむねをよみます。',
                'しりょうをよむますぴむねをよみます。','ほぞんすればぴむねをよむます。',
                'ほぞんしたらぴむねをよみま。','ほぞんしたらぴむねををよみます。',
                'ほぞんしたらぴむねを眠ります。'):
            with self.subTest(text=text):
                self.assertFalse(R.source_opaque_object_ranges(text))
        # A finite modifier is not silently turned into a connective prefix.
        self.assertFalse(R.source_opaque_object_ranges('ほぞんしたぴむねをよみます。'))

    def test_source_only_prefix_proof_is_not_generated_word_evidence(self):
        text='ほぞんしたらぴむねをよみます。'
        self.assertFalse(R.native_surface_nominal_heads('ぴむね'))
        self.assertTrue(P.odd_kana_spans(text,self.a.dict_index,self.a.store,
                                       preserve_unknown_source=False))
        # Unknown is not itself an anomaly. The candidate path must not
        # borrow the source exemption, irrespective of other grammar marks.
        with patch.object(R,'source_opaque_object_ranges',side_effect=AssertionError('source-only proof')):
            O.odd_spans(text,self.tok,store=self.a.store,dict_index=self.a.dict_index)
        self.assertFalse(Q._productive_predicate(text[:-1],'ぴむね'))

    def test_prefix_does_not_lend_a_homophones_meaning_to_written_object(self):
        self.assertTrue(R.source_opaque_object_ranges('しりょうをたべたらぴむねをよみます。'))
        self.assertFalse(R.source_opaque_object_ranges('資料を食べたらぴむねをよみます。'))
        self.assertFalse(R.source_opaque_object_ranges('資料を食べればぴむねをよみます。'))

    def test_prefixed_source_protection_keeps_other_clause_anomalies_visible(self):
        import app
        good='ほぞんすればぴむねをよみます。'
        bad='資料を保存だました。'
        result=app.correct_line(good+bad,self.a.store,input_method='kana',
            dict_index=self.a.dict_index,context_vec=None,decisions=self.a.decisions)
        self.assertEqual(result['corrected'],good+bad)
        self.assertTrue(result['odd_spans'])
        self.assertTrue(all(a>=len(good) for a,b in result['odd_spans']))
        for start,end,surface in ((len('ほぞんすれば'),len('ほぞんすれば')+3,'ぴむな'),
                (0,len(good),'ほぞんすればぴむなをよみます。')):
            with self.subTest(end=end):
                self.assertEqual(C._check_replacement(good,(start,end,surface,'かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((start,end),)),
                    (None,'opaque_original_object'))


if __name__ == '__main__':
    unittest.main()
