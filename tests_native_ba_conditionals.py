# -*- coding: utf-8 -*-
"""Native hypothetical stems do not borrow a finite verb or object identity."""
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NativeBaConditionalTests(unittest.TestCase):
    def test_actual_hypothetical_forms_and_swallowed_sahen_share_finite_proof(self):
        for text in ('ほぞんすれば','しりょうをほぞんすれば','しりょうをよめば',
                     'しりょうをよまなければ','りんごをたべれば','ほんをよめば',
                     'かくにんすれば'):
            with self.subTest(text=text):
                self.assertTrue(R.native_ba_finite_forms(text))
                self.assertTrue(R.completed_native_reading_link(text))

    def test_another_form_or_lexical_ba_is_not_a_modern_hypothetical(self):
        for text in ('よむば','よまば','よみば','ほぞんするば','ほぞんしまば',
                     'ほぞんしたば','たらば','たらばがに','すればね','ぷねらば',
                     'ほぞんするたらば','しりょうをほぞんするたらば','たべるたらば',
                     'しりょうをよむたらば','資料だならば','しりょうだならば'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_link(text))

    def test_same_written_object_survives_the_finite_projection(self):
        self.assertTrue(R.completed_native_reading_link('しりょうをほぞんすれば',
            require_nominal=True,nominal_constraint=('しりょう',('資料',))))
        # 飼料 has a food sense; that must not be lent to the written 資料.
        self.assertTrue(R.completed_native_reading_link('しりょうをたべれば'))
        self.assertFalse(R.completed_native_reading_link('しりょうをたべれば',
            require_nominal=True,nominal_constraint=('しりょう',('資料',))))
        self.assertTrue(R.completed_native_reading_link('しりょうをたべれば',
            require_nominal=True,nominal_constraint=('しりょう',('飼料',))))
        self.assertFalse(R.completed_native_reading_link('ぷねらをたべれば'))

    def test_finite_projection_cannot_merge_a_prefix_into_another_verb(self):
        # Source: filler あ + hypothetical おえ (おう); the shorter string
        # あおう also parses as the volitional of 会う, a different verb.
        self.assertFalse(R.native_ba_finite_forms('あおえば'))
        self.assertFalse(R.completed_native_reading_link('あおえば',allow_unclassified=True))
        self.assertTrue(R.completed_native_reading_link('しりょうをほぞんすれば'))
        self.assertTrue(R.completed_native_reading_link('ほんをよめば'))

    def test_conditional_alone_does_not_complete_a_generated_clause(self):
        for text in ('ほぞんすれば','ほんをよめば'):
            self.assertTrue(R.completed_native_reading_link(text))
            self.assertFalse(R.completed_native_link_clause(text))

    def test_application_keeps_complete_normal_conditionals(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ほぞんすればれんらくします。','しりょうをほぞんすればれんらくします。',
                     'ほんをよめばほぞんします。','しりょうをよまなければれんらくします。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                       context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], text)
                self.assertFalse(result.get('odd_spans'))


if __name__=='__main__':unittest.main()
