# -*- coding: utf-8 -*-
"""An altered object cannot leave its unchanged quantity and predicate unexplained."""
import unittest
import morphology as M
import contextual_repair as R


@unittest.skipUnless(M.dictionary_inflections('買う'), 'requires native dictionary')
class QuantityObjectValidationTests(unittest.TestCase):
    def test_changed_object_needs_positive_fit_to_the_same_predicate(self):
        source='ほきんをにさつかいます。'
        for candidate,expected in (('ほん',True),('本',True),('ほんき',False),
                                   ('本気',False),('きほん',False)):
            with self.subTest(candidate=candidate):
                self.assertEqual(R.object_predicate_candidate_allowed(source,0,3,candidate),expected)
        for source,start,end,candidate in (
                ('りふごをみっつかいます。',0,3,'りんご'),
                ('ふでをにほんかいます。',0,2,'鉛筆')):
            with self.subTest(source=source,candidate=candidate):
                self.assertTrue(R.object_predicate_candidate_allowed(source,start,end,candidate))

    def test_unreadable_source_token_can_contain_the_unchanged_case(self):
        for source,candidate in (('ほんゃをにさつかいます。','本社'),
                                 ('つしりょうをにまいよみます。','質量')):
            end=source.index('を')
            with self.subTest(source=source):
                self.assertTrue(R._original_counted_object_slots(source))
                self.assertFalse(R.object_predicate_candidate_allowed(source,0,end,candidate))
        self.assertTrue(R.object_predicate_candidate_allowed('ほんゃをにさつかいます。',0,3,'ほん'))

    def test_wider_replacement_uses_the_same_original_case_and_counter(self):
        source='ほきんをにさつかいます。'
        for end,candidate in ((4,'ほんきを'),(len(source),'ほんきをにさつかいます。')):
            with self.subTest(end=end):
                self.assertFalse(R.object_predicate_candidate_allowed(source,0,end,candidate))
        source='ほきんをにさつかいなす。'
        self.assertFalse(R.object_predicate_candidate_allowed(source,0,len(source),
            'ほんきをにさつかいます。'))
        self.assertTrue(R.object_predicate_candidate_allowed(source,0,len(source),
            'ほんをにさつかいます。'))

    def test_deletion_at_the_noun_case_seam_still_changes_the_object(self):
        self.assertFalse(R.object_predicate_candidate_allowed('ほやんをにさつかいます。',0,3,'ほや'))
        self.assertFalse(R.object_predicate_candidate_allowed('ほやんをにさつかいます。',2,3,''))
        self.assertTrue(R.object_predicate_candidate_allowed('ほんゃをにさつかいます。',0,3,'ほん'))
        self.assertTrue(R.object_predicate_candidate_allowed('きかいてをにだいならべます。',0,4,'機械'))

    def test_case_and_counter_do_not_certify_an_unknown_or_broken_predicate(self):
        for source in ('ほきんをにさつかいなす。','ほきんをにさつしらゆほます。'):
            with self.subTest(source=source):
                self.assertFalse(R.object_predicate_candidate_allowed(source,0,3,'ほん'))

    def test_missing_nominal_frame_is_not_candidate_proof(self):
        for source,candidate in (('へほんをにさつかいます。','へらん'),
                                 ('ほゆんをにさつかいます。','ほらん'),
                                 ('りんこばをみっつかいます。','りこんば'),
                                 ('しれょうをにまいよみます。','しれよう'),
                                 ('しねょうをにまいよみます。','死ねよう'),
                                 ('しめょうをにまいよみます。','しめよう')):
            with self.subTest(source=source):
                end=source.index('を')
                self.assertFalse(R.object_predicate_candidate_allowed(source,0,end,candidate))
                changed=candidate+source[end:]
                self.assertFalse(R.object_predicate_candidate_allowed(source,0,len(source),changed))

    def test_an_independent_later_object_does_not_constrain_this_edit(self):
        for source in ('よみなす、ほんをにさつかいます。',
                       'よみなす。ほんをにさつかいます。',
                       'よみなすがほんをにさつかいます。',
                       'よみなすがほきんをにさつかいます。'):
            with self.subTest(source=source):
                self.assertTrue(R.object_predicate_candidate_allowed(source,0,4,'よみます'))

    def test_legacy_wrong_object_is_rejected_at_the_shared_final_check(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        accepted,reason=C._check_replacement('ほきんをにさつかいます。',
            (0,3,'ほんき','かな入力'),a.store,tk,a.dict_index,a.decisions)
        self.assertIsNone(accepted)
        self.assertEqual(reason,'unproven_original_object_predicate')


if __name__=='__main__':unittest.main()
