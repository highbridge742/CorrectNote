# -*- coding: utf-8 -*-
import unittest
import morphology as M
from unittest.mock import patch
import app,particle_frames as P,reading_segments as R,contextual_repair as Q
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class InterruptedComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=initial()
    def test_source_frame_does_not_use_a_candidate_or_key_search(self):
        with patch('kana_layout.single_key_drop_adjacency',side_effect=AssertionError('search before anomaly')):
            frames=P.interrupted_comparison_frames('他の行とえ同じです。')
        self.assertEqual(len(frames),1)
        self.assertEqual((frames[0]['start'],frames[0]['extra'],frames[0]['end']),(3,4,7))
        self.assertEqual(P.drop_candidate('他の行とえ同じです。',frames[0])['surface'],'と同じ')
        for text in ('他の行と同じ','前とえ、同じです。','前とええ同じ',
                     '未知蒟とえ同じ','「他の行とえ同じ」と入力します。'):
            with self.subTest(text=text):self.assertEqual(P.interrupted_comparison_frames(text),[])
        frame=P.interrupted_comparison_frames('他の行とあ同じ')[0]
        self.assertIsNone(P.drop_candidate('他の行とあ同じ',frame))
    def test_written_and_kana_comparison_share_the_same_finite_tail(self):
        for text in ('同じです','同じでした','おなじです','他の行と同じです。'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_nominal_predicate(text,allow_written=True))
        for text in ('同じます','同じまし','同じる','同じですです'):
            with self.subTest(text=text):self.assertFalse(R.completed_native_nominal_predicate(text,allow_written=True))
    def test_initial_stages_keep_original_span_and_physical_deletion(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for text,expected in (('他の行とえ同じ','他の行と同じ'),
                    ('他の行とえ同じです。','他の行と同じです。'),('前とえ同じ','前と同じ'),
                    ('色とえ同じです。','色と同じです。'),('他の行と同じ','他の行と同じ'),
                    ('前とえ、同じです。','前とえ、同じです。'),
                    ('「他の行とえ同じ」と入力します。','「他の行とえ同じ」と入力します。')):
                with self.subTest(phase=phase,text=text):
                    result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result.get('odd_spans'),[])
            result=app.correct_line('他の行とあ同じ',a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
            self.assertEqual(result['corrected'],'他の行とあ同じ')
            self.assertTrue(result.get('odd_spans'))
    def test_comma_pause_keeps_its_native_nominal_case_without_reading_search(self):
        from reading_segments import native_paused_nominal_ranges,native_context_ranges
        from ime_inverse_gate import anomalous_source_fields
        from corrector import make_tokenizer
        tok=make_tokenizer(self.a.store)
        cases=('前とえ、同じです。','色とええ、同じです。','前とえー、同じです。',
               '資料をあ、送ります。','資料をええ、送ります。')
        for text in cases:
            end=text.index('、')
            with self.subTest(text=text):
                self.assertIn((0,end),native_paused_nominal_ranges(text))
                self.assertIn((0,end),native_context_ranges(text))
                with patch('ime_language.JapaneseIME',side_effect=AssertionError('pause needs no IME query')):
                    self.assertFalse(anomalous_source_fields(text,tok,self.a.store,self.a.dict_index))
                result=app.correct_line(text,self.a.store,input_method='kana',dict_index=self.a.dict_index)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])
        for text in ('前とえ同じです。','前とえ\t同じです。','未知蒟とえ、同じです。','前とぬ、同じです。'):
            self.assertEqual(native_paused_nominal_ranges(text),(),text)
        text='前とえ、しにうせい'
        self.assertEqual(native_paused_nominal_ranges(text),((0,3),))

if __name__=='__main__':unittest.main()
