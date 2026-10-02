# -*- coding: utf-8 -*-
"""Source yoon structure is shared with repair; native mixed kana stays intact."""
import unittest
import morphology as M
import app,corrector as C,morphology as M,reading_segments as R
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class MixedKanaSpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))
    def test_anomaly_precedes_candidate_search_and_keeps_unknown_candidates(self):
        self.assertEqual(M.source_yoon_spans('モーシろょん'),((3,5),))
        self.assertEqual(M.source_yoon_spans('プネろょん'),((2,4),))
        self.assertFalse(C._chunk_is_intact('モーシろょん',self.tok))
        for text in ('モーシょん','ふュージョン','ゆるキャラ','プネキャング',
                     'イラストだょね','イラストみたょ','おハょー','ダメだょ',
                     '「モーシろょん」と入力します。'):
            with self.subTest(text=text):self.assertEqual(M.source_yoon_spans(text),())
    def test_auxiliary_label_needs_an_actual_colloquial_attachment(self):
        for text in ('セクシつょン','セクシぬょン','ファッシつょン','クッシつょン'):
            self.assertTrue(M.source_yoon_spans(text),text)
        for text in ('イラストだょね','イラストみたょね','イラストだョね','イラストみたョね','プネラだょね','ダメだょン',
                     'イラストだょ','イラストみたょ','おハょー'):
            self.assertEqual(M.source_yoon_spans(text),(),text)

    def test_a_script_boundary_cannot_detach_the_original_small_kana(self):
        for text in ('プロジェクシょン','ソリゅーション','ふュージョン','モーシょン'):
            r=app.correct_line(text,self.a.store,input_method='kana',dict_index=self.a.dict_index,
                               context_vec=None,decisions=self.a.decisions)
            self.assertEqual(r['corrected'],text);self.assertEqual(r.get('odd_spans'),[])
        for text,start,end,value in (('プロジェクシょン',0,6,'プロジェクト'),
                                     ('ソリゅーション',3,7,'モーション')):
            candidate,reason=C._check_replacement(text,(start,end,value,'外来語'),
                self.a.store,self.tok,self.a.dict_index)
            self.assertIsNone(candidate);self.assertEqual(reason,'original_spelling_scope')
        self.assertTrue(M.mixed_kana_syllable_scope('モーシろょん',0,6))
        self.assertTrue(M.mixed_kana_syllable_scope('モーシろョン',3,4))

    def test_native_unchanged_reading_is_shared_by_entry_and_final_check(self):
        for text in ('モーシょん','ふュージョン'):
            with self.subTest(text=text):
                self.assertIn((0,len(text)),R.native_mixed_kana_word_ranges(text))
                self.assertTrue(C._chunk_is_intact(text,self.tok))
                candidate,reason=C._check_replacement(text,(0,len(text),'別語','かな入力'),
                    self.a.store,self.tok,self.a.dict_index,conv_taken=((0,len(text)),))
                self.assertIsNone(candidate,reason)
        self.assertEqual(R.native_mixed_kana_word_ranges('モーシろょん'),())
        self.assertEqual(R.native_mixed_kana_word_ranges('プネキャング'),())
    def test_both_initial_stages_repair_intrusions_and_preserve_normal_variants(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for original,expected in (('モーシろょん','モーション'),
                    ('シミろゅレーション','シミュレーション'),('アクシろョン','アクション'),
                    ('フろゅージョン','フュージョン'),('フつゅージョン','フュージョン'),
                    ('プロジェクシろょン','プロジェクション'),('プロジェクシつょン','プロジェクション'),
                    ('ソリろゅーション','ソリューション'),('ソリつゅーション','ソリューション'),
                    ('モーション','モーション'),('モーシょん','モーシょん'),
                    ('ふュージョン','ふュージョン'),('ゆるキャラ','ゆるキャラ'),
                    ('プネキャング','プネキャング'),('イラストだょね','イラストだょね'),
                    ('おハょー','おハょー'),('「モーシろょん」と入力します。','「モーシろょん」と入力します。')):
                with self.subTest(phase=phase,original=original):
                    r=app.correct_line(original,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r.get('odd_spans'),[])
            for original in ('プネろょん','プネろゅーン','フほゅージョン','ソリほゅーション','プロジェクシぬょン'):
                r=app.correct_line(original,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                self.assertEqual(r['corrected'],original)
                self.assertTrue(r.get('odd_spans'))
    def test_written_and_kana_sources_share_malformed_yoon_evidence(self):
        for source in ('割くばょ','さくばょ','割くばょして'):
            with self.subTest(source=source):
                self.assertTrue(M.source_yoon_spans(source))
        for source in ('今日は暇だょ。','もう寝たょ。','そうだょね','あるょ','だょ','ですょ'):
            with self.subTest(source=source):
                self.assertEqual(M.source_yoon_spans(source),())
        for source,expected in (
                ('割くばょ','削除'),('割くばょして','削除して'),
                ('古い設定を割くばょして保存します。','古い設定を削除して保存します。'),
                ('時間を割けばよい。','時間を割けばよい。'),
                ('分かればよろしくお願いします。','分かればよろしくお願いします。'),
                ('「割くばょ」と入力する。','「割くばょ」と入力する。')):
            with self.subTest(source=source):
                result=app.correct_line(source,self.a.store,input_method='kana',dict_index=self.a.dict_index,
                    context_vec=None,decisions=self.a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])
                self.assertEqual(result.get('analysis_status'),'complete')

if __name__=='__main__':unittest.main()
