# -*- coding: utf-8 -*-
from tests_spelling_reference import assert_reviewed_result_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import contextual_repair as C
import reading_segments as R

@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class OriginalCaseStyleTests(unittest.TestCase):
    def test_counter_restoration_retains_original_nominal_case(self):
        for text in ('こどもにほんをよんでもらいます','せんせいにほんをよんでもらいます'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,True,True,True))
                self.assertTrue(any(t.surface=='に' and t.pos=='助詞' for t in M.tokenize(text)))
        for text in ('ほんをにさつよみます','かみをさんまいかさねます'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,True,True,True))

    def test_original_frame_supplies_style_for_every_candidate_path(self):
        import corrector
        from tests_analysis_async import initial
        a=initial();tk=corrector.make_tokenizer(a.store)
        text='まどをしめてからほんをよみんす'
        for kind in ('kana_predicate','lexical','auxiliary_connection'):
            target=C.RepairTarget(text,11,len(text),0,len(text),(),True,'',kind)
            self.assertTrue(C._source_predicate_context(target,tk))
        text='よみんす'
        target=C.RepairTarget(text,0,len(text),0,len(text),(),True,'','lexical')
        self.assertFalse(C._source_predicate_context(target,tk))

    def test_later_clause_keeps_horizontal_repair_and_excluded_shift_tail(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        source='まどをしめてからほんをよみまか。'
        r=app.correct_line(source,a.store,dict_index=a.dict_index,decisions=a.decisions,context_vec=None,input_method='kana')
        assert_reviewed_result_spelling(self,r,'まどをしめてからほんを読みます。')
        self.assertEqual(r['odd_spans'],[])
        for generator in (C.key_repairs,C.nonadjacent_key_repairs):
            self.assertNotIn('よみます',{r.reading for r in generator('よみまぇ')})
        source='まどをしめてからほんをよみまぇ。'
        r=app.correct_line(source,a.store,dict_index=a.dict_index,decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertIn(r['corrected'],(source,'まどをしめてから本をよみまぇ。','窓をしめてから本をよみまぇ。'))
        self.assertTrue(r['odd_spans'])
        self.assertEqual(r['analysis_status'],'complete')

    def test_later_clause_repairs_keep_original_kana_and_earlier_object(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('まどをしめてからほんをよみまもす。','まどをしめてからほんを読みます。'),
            ('てがみをかいてからほへんをよみます。','てがみをかいてから本をよみます。'),
            ('こどもにほんをよんでもらいます。','こどもにほんをよんでもらいます。')):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                assert_reviewed_result_spelling(self, r, expected);self.assertEqual(r['odd_spans'],[])

    def test_later_nominal_intrusion_keeps_original_mark_keys_and_common_gate(self):
        import app,corrector
        from unittest.mock import patch
        from tests_analysis_async import initial
        from last_choice import set_active
        old='てがみをかいてから゛んをよみます。'
        for generator in (C.key_repairs,C.nonadjacent_key_repairs,
                          C.adjacent_shift_key_repairs,C.neighbor_shift_key_repairs):
            for reading,expected in (('゛ん','ほん'),('から゛ん','からほん')):
                with self.subTest(generator=generator.__name__,reading=reading):
                    self.assertNotIn(expected,{r.reading for r in generator(reading)})
        proof=next(r for r in C.key_repairs('ほへん') if r.reading=='ほん')
        self.assertEqual((proof.operation,proof.position,proof.pressed,proof.intended),
                         ('adjacent_intrusion',1,'へ',''))
        try:
            a=initial();tk=corrector.make_tokenizer(a.store)
            targets=C.targets_for_line(old,tk,a.store,a.dict_index)
            self.assertEqual({(t.start,t.end,t.boundary_kind) for t in targets},
                             {(0,11,'nominal_object'),(7,11,'nominal_object'),(9,11,'lexical')})
            target=next(t for t in targets if (t.start,t.end)==(9,11))
            readings=C.reading_evidence(target,tk,a.dict_index)
            self.assertEqual({r.text for r in readings},{'゛ん'})
            self.assertTrue(all(r.segments==((0,1,'゛','literal_mark_key'),(1,2,'ん','literal_kana')) for r in readings))
            # The old finalせん output remains in the diagnosis; it is not
            # adopted here as a newly correct expected spelling.
            source='てがみをかいてからほへんをよみます。'
            a=initial()
            with patch.object(corrector,'_check_replacement',return_value=(None,'forced_common_gate')):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                        decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertTrue(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            for source in ('手紙を書いてから本を読みます。','「てがみをかいてからほへんをよみます。」という文字列です。'):
                with self.subTest(source=source):
                    a=initial();result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],source)
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

if __name__=='__main__':unittest.main()

