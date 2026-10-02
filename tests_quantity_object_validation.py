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

    def test_typed_counter_constrains_a_generic_request_object(self):
        import semantic_roles as S
        import reading_segments as RS
        self.assertEqual(S.counted_object_roles('にさつ'),frozenset(('text','reference')))
        self.assertEqual(S.counted_object_roles('二台'),frozenset(('device',)))
        for text in ('にこ','二枚','二本','二つ','二冊目','しらゆほ冊'):
            self.assertIsNone(S.counted_object_roles(text),text)
        source='ほきんをにさつください。'
        for candidate in ('ほん','本','資料','絵本'):
            self.assertTrue(R.object_predicate_candidate_allowed(source,0,3,candidate),candidate)
        for candidate in ('保菌','本気','基本','保管','鉛筆','先生'):
            for end,surface in ((3,candidate),(len(source),candidate+source[3:])):
                self.assertFalse(R.object_predicate_candidate_allowed(source,0,end,surface),(candidate,end))
        for text in ('ほんをにさつください','きかいをにだいください'):
            self.assertTrue(RS.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('ほきんをにさつください','えんぴつをにさつください','ほんをにだいください'):
            self.assertFalse(RS.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_written_quantity_uses_the_same_original_object_validation(self):
        import reading_segments as RS
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        for quantity in ('二冊','にさつ','0冊','100冊','１２３冊'):
            source='ほきんを'+quantity+'ください。'
            for candidate in ('本気','保菌','基本','本社'):
                self.assertFalse(R.object_predicate_candidate_allowed(source,0,3,candidate),candidate)
                value,reason=C._check_replacement(source,(0,3,candidate,'かな入力'),
                    a.store,tk,a.dict_index,a.decisions)
                self.assertIsNone(value,(source,candidate,reason))
            self.assertTrue(R.object_predicate_candidate_allowed(source,0,3,'ほん'),source)
        for text in ('二冊ください','二台かいます','にさつください'):
            self.assertTrue(RS._native_counter_prefixes(text,M.tokenize(text)),text)
        for text in ('二冊目からよみます','にさつめからよみます','三冊目をください'):
            self.assertFalse(RS._native_counter_prefixes(text,M.tokenize(text)),text)
        # No predicate is supplied by a bare object/count note.
        self.assertFalse(R.object_predicate_candidate_allowed('ほきんを二冊',0,3,'本気'))
        self.assertTrue(R.object_predicate_candidate_allowed('よみなす。ほんを二冊',0,4,'よみます'))

    def test_one_homophone_must_fit_both_the_counter_and_the_predicate(self):
        import reading_segments as RS
        faces=RS.native_nominal_phrase_faces('しりょう')
        self.assertIn('資料',faces)
        self.assertIn('飼料',faces)
        for quantity in ('にさつ','二冊','2冊','100冊','1,000冊','百冊','一万冊'):
            source='しりょうを'+quantity+'たべます'
            self.assertFalse(RS.native_object_predicate_proof(source,5,faces),source)
            self.assertFalse(R.object_predicate_candidate_allowed('しりょにうを'+quantity+'たべます。',0,5,'しりょう'),quantity)
            self.assertTrue(RS.native_object_predicate_proof('しりょうを'+quantity+'よみます',5,faces),quantity)
        self.assertTrue(RS.completed_native_reading_clause('しりょうをたべます',require_object_fit=True))
        self.assertFalse(RS.completed_native_reading_clause('しりょうをにさつたべます',require_object_fit=True))
        self.assertTrue(RS.completed_native_reading_clause('しりょうをにさつよみます',require_object_fit=True))

    def test_request_repairs_the_noun_without_rewriting_unclassified_titles(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source in ('ほきんをにさつください。','ほきんをにさつかいます。','ほきんをにさつよみます。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source.replace('ほきん','本'))
            self.assertEqual(result.get('odd_spans'),[])
        for text in ('「保菌」を二冊ください。','「本気」を二冊ください。',
                     '「ほきんをにさつください」を入力しました。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)

    def test_changed_unexplained_noun_keeps_its_complete_original_predicate(self):
        for source,start,end,bad,good in (
                ('かぼちんをにます。',0,4,'かぼたん','かぼちゃ'),
                ('ぶろっこりへをゆでます。',0,6,'ブロッコリーへ','ブロッコリー')):
            self.assertFalse(R.object_predicate_candidate_allowed(source,start,end,bad),source)
            self.assertTrue(R.object_predicate_candidate_allowed(source,start,end,good),source)
        self.assertFalse(R.object_predicate_candidate_allowed('かぼちんをにます。',1,4,'ぼたん'))
        self.assertFalse(R.object_predicate_candidate_allowed('ぶろっこりへをゆでます。',0,5,'ブロッコリー'))
        # Previous 35/36 contract rejected 郷里 solely because its semantic
        # role was unclassified. That is not affirmative evidence of error.
        for source,candidate in (('きようりをきります。','きょうり'),
                ('まぢあわせをみます。','まちあわせ'),
                ('ぴっぁをみます。','ピッツァ'),
                ('るでにうむをみます。','るてにうむ'),
                ('ごじごしをみます。','ごしごし')):
            end=source.index('を')
            self.assertTrue(R.object_predicate_candidate_allowed(source,0,end,candidate),source)
        # No new judgment for unfinished predicates or an independent edit.
        self.assertTrue(R.object_predicate_candidate_allowed('かぼちんをにま',1,4,'ぼたん'))
        self.assertTrue(R.object_predicate_candidate_allowed('かぼちんをにます。よみなす。',9,13,'よみます'))

    def test_legacy_wrong_object_is_rejected_at_the_shared_final_check(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        accepted,reason=C._check_replacement('ほきんをにさつかいます。',
            (0,3,'ほんき','かな入力'),a.store,tk,a.dict_index,a.decisions)
        self.assertIsNone(accepted)
        self.assertEqual(reason,'unproven_original_object_predicate')


if __name__=='__main__':unittest.main()
