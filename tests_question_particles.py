# -*- coding: utf-8 -*-
"""Closed polite questions: original grammar, physical slips and UI ranges."""
import unittest
from unittest.mock import patch
import morphology

@unittest.skipUnless(morphology.HAS_JANOME,'native Janome dictionary')
class QuestionParticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial()

    def correct(self,text,decisions=None):
        import app
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            input_method='kana',decisions=decisions or self.a.decisions)

    def test_native_readings_restore_closed_questions(self):
        for prefix in ('あります','本があります','読みます','泳ぎます','元気です','しりょうがあります'):
            for tail in ('間','冠','かん'):
                with self.subTest(prefix=prefix,tail=tail):
                    result=self.correct(prefix+tail+'？')
                    self.assertEqual(result['corrected'],prefix+'か？')
                    self.assertFalse(result['odd_spans'])
                    again=self.correct(result['corrected'])
                    self.assertEqual(again['corrected'],result['corrected'])
                    self.assertFalse(again['odd_spans'])

    def test_terminal_without_question_mark(self):
        from particle_frames import closed_question_frames
        for prefix in ('あります','資料があります','読みます','元気です','しりょうがあります'):
            for tail in ('間','冠','かん'):
                for ending in ('','。','！','?','\t別の列','  '):
                    with self.subTest(prefix=prefix,tail=tail,ending=ending):
                        text=prefix+tail+ending
                        result=self.correct(text)
                        self.assertEqual(result['corrected'],prefix+'か'+ending)
                        self.assertFalse(result['odd_spans'])
                        self.assertTrue(all(0<=f['start']<f['end']<=f['context_end']<=len(text)
                                            for f in closed_question_frames(text)))

    def test_question_mark_and_natural_boundaries(self):
        from particle_frames import closed_question_frames
        for text in ('ありますか？','ありますかね？','ありますかい？','ありますかな？',
                     'ありますが？','ありますかぁ？','ありますもの？','ありますもん？',
                     'あります、冠？','缶はありますか？','冠もありますか？',
                     '読みます時？','行きます人は誰ですか？','あります感？',
                     'あります冠という店','あります間に確認する','「あります冠？」という文字列。','「あります間？」という文字列？',
                     '「あります間」という表記！','「ありますかん」という綴り?'):
            with self.subTest(text=text):
                self.assertFalse(closed_question_frames(text))
                self.assertEqual(self.correct(text)['corrected'],text)

    def test_homophones_ignore_best_parse_part_of_speech(self):
        # Native suffixes, proper names, verb/adjective stems and characters
        # without a standalone dictionary word share the same question frame.
        for prefix in ('あります','元気です'):
            for tail in '館管観官寒関漢刊患監環看寛閑還簡慣換緩歓艦棺':
                for ending in ('','？'):
                    with self.subTest(prefix=prefix,tail=tail,ending=ending):
                        result=self.correct(prefix+tail+ending)
                        self.assertEqual(result['corrected'],prefix+'か'+ending)
                        self.assertFalse(result['odd_spans'])

    def test_clause_and_nominal_suffix_hosts_are_distinct(self):
        from particle_frames import closed_question_frames
        from semantic_roles import finite_clause_suffix,nominal_host_suffix
        self.assertEqual(finite_clause_suffix('感')['role'],'impression')
        self.assertEqual(nominal_host_suffix('館')['role'],'building')
        self.assertIsNone(nominal_host_suffix('顔'))
        self.assertIsNone(nominal_host_suffix('未知'))
        for text in ('あります感','あります顔','あります圧','あります説',
                     'あります論','あります分','読みます人','元気です風','元気です体',
                     'しりょうがありますもの？','ありがとうございます寛',
                     'よろしくお願いします寛','感謝します寛','失礼します館',
                     '館は元気です','朝刊を読みます','看護師です','緩やかです',
                     '棺があります','箱があります','瓶があります','袋があります','筒があります',
                     '「あります館」という文字列。','あります、館','あります\t館'):
            with self.subTest(text=text):
                self.assertFalse(closed_question_frames(text))
                self.assertEqual(self.correct(text)['corrected'],text)
        # An interjection elsewhere is not a greeting/name connection.
        self.assertTrue(closed_question_frames('あれ、本があります館'))

    def test_anomalous_stem_uses_attested_character_readings(self):
        import corrector,contextual_repair as cr
        fn=corrector.make_tokenizer(self.a.store)
        for glyph in ('看','緩'):
            text='あります'+glyph
            with self.subTest(glyph=glyph):
                with patch.object(cr,'key_repairs',side_effect=AssertionError('premature search')):
                    targets=cr.targets_for_line(text,fn,self.a.store,self.a.dict_index)
                    target=next(t for t in targets if t.boundary_kind=='question_particle')
                    readings=cr.reading_evidence(target,fn,self.a.dict_index)
                self.assertIn('ますかん',[r.text for r in readings])
                self.assertEqual(self.correct(text)['corrected'],'ありますか')

    def test_original_anomaly_precedes_key_search(self):
        import corrector,contextual_repair as cr
        text='本があります冠？';fn=corrector.make_tokenizer(self.a.store)
        with patch.object(cr,'key_repairs',side_effect=AssertionError('premature search')):
            targets=cr.targets_for_line(text,fn,self.a.store,self.a.dict_index)
        self.assertTrue(any(t.boundary_kind=='question_particle' for t in targets))
        with patch.object(corrector,'_chunk_is_intact',wraps=corrector._chunk_is_intact) as entry, \
             patch.object(corrector,'_check_replacement',wraps=corrector._check_replacement) as final:
            self.assertEqual(self.correct(text)['corrected'],'本がありますか？')
        self.assertTrue(any(c.kwargs.get('repair_context') and c.kwargs['repair_context'].boundary_kind=='question_particle' for c in entry.call_args_list))
        self.assertTrue(any(c.args[1][2]=='ますか' for c in final.call_args_list))

    def test_ledger_and_nonempty_clickable_ranges(self):
        from decisions import DecisionStore
        for bad in ('ます冠','ますかん','ます館','ます看','ます患'):
            text='本があり'+bad+'？';ledger=DecisionStore();ledger.reject(bad,'ますか')
            self.assertEqual(self.correct(text,ledger)['corrected'],text)
            result=self.correct(text)
            self.assertIn((bad,'ますか','かな入力'),result['details'])
            self.assertTrue(all(a<b for a,b in result['spans']))
        ledger=DecisionStore();ledger.leave_odd_alone('ます冠')
        self.assertEqual(self.correct('本があります冠？',ledger)['corrected'],'本がありますか？')

    def test_neighbor_rule_is_not_relaxed(self):
        from contextual_repair import key_repairs
        self.assertTrue(any(r.reading=='ますか' and r.operation=='adjacent_intrusion' for r in key_repairs('ますかん')))
        for bad in ('ますかあ','ますかか'):
            self.assertFalse(any(r.reading=='ますか' for r in key_repairs(bad)))

    def test_worker_prepares_and_builds_units_for_comparison_columns(self):
        from analysis_worker import Runtime,snapshot
        runtime=Runtime();runtime.set_state(snapshot(self.a))
        lines=['歩いてくたせさぃ。\t歩いてください。','本があります冠？\t本がありますかん？\t本がありますか？']
        expected=['歩いてください。\t歩いてください。','本がありますか？\t本がありますか？\t本がありますか？']
        prepared=runtime.prepare(lines)
        for source,wanted in zip(lines,expected):
            value=runtime.execute(dict(kind='line',line=source,input_method='kana',context=prepared['context'],attested=prepared['attested']))
            self.assertEqual(value['result']['corrected'],wanted)
            self.assertTrue(value['original_units'][1])
            self.assertTrue(value['corrected_units'][1])

if __name__=='__main__':unittest.main()
