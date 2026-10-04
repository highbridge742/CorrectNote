# -*- coding: utf-8 -*-
import unittest
import app
from tests_analysis_async import initial

from morphology import HAS_JANOME

@unittest.skipUnless(HAS_JANOME, "Requires real Janome; run with the native integration suite")
class NaturalDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.state=initial()
    def check(self,source,expected):
        s=self.state
        r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                           decisions=s.decisions,context_vec=None)
        self.assertIn(r['corrected'],expected if isinstance(expected,tuple) else (expected,),source)
        self.assertFalse(r.get('odd_spans'),source)
        self.assertEqual('complete',r.get('analysis_status'),source)

    def test_independent_key_and_written_fields(self):
        for source in ('と照る手段','とてるしゅだん','とれるしゅだん'):
            with self.subTest(source=source):self.check(source+'\t','取れる手段\t')

    def test_familiar_process_keeps_original_semantic_category(self):
        for source in ('再退化','さいたいか','さいだいか'):
            with self.subTest(source=source):self.check(source+'\t','最大化\t')

    def test_parser_cost_is_not_semantic_naturalness(self):
        for a,b in [('約束の時間に土地宇着しました。','約束の時間に到着しました。'),
                    ('海上を世や菊して人数を伝えます。','会場を予約して人数を伝えます。'),
                    ('結果を機論して資料を閉じます。',('結果を記録して資料を閉じます。','結果を議論して資料を閉じます。')),
                    ('必要な部分だけを点刷してください。','必要な部分だけを印刷してください。')]:
            with self.subTest(source=a):self.check(a,b)

    def test_native_processes_and_relative_actions(self):
        for source in ('再構成','再変換','再初期化','再評価','器官が再退化する',
                       '取る手段','取れる手段','採る手段','使える方法'):
            with self.subTest(source=source):self.check(source,source)


    def test_native_inflection_keeps_its_source_reading_and_own_usage(self):
        for source,expected in (
                ('キーボードで文字を売ちます。','キーボードで文字を打ちます。'),
                ('キーボードで文字を打ちます。','キーボードで文字を打ちます。'),
                ('キーボードで文字を打てます。','キーボードで文字を打てます。')):
            with self.subTest(source=source):self.check(source,expected)

    def test_inverse_scope_keeps_proved_nominal_prefix_and_real_limits(self):
        import corrector,ime_inverse_gate
        s=self.state;tok=corrector.make_tokenizer(s.store)
        for source,expected in (
                ('必要な部分だけを点刷してください。','必要な部分だけを印刷してください。'),
                ('重要な資料を点刷します。','重要な資料を印刷します。')):
            with self.subTest(source=source):
                result=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                    decisions=s.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
                self.assertTrue(result.get('search_reports'))
                edge=source.index('を')+1
                self.assertTrue(all(report['start']>=edge for report in result['search_reports']))
                self.assertTrue(all(not v.get('unexplored') for report in result['search_reports']
                                    for v in report.get('limits',{}).values()))
        for source in ('未知語ぽねを点刷します','必要で部分を点刷します','を点刷します',
                       '必要な部分だけ','資料を'):
            with self.subTest(source=source):self.assertEqual(ime_inverse_gate._native_argument_prefix(source,tok),0)

    def test_weak_inverse_reading_keeps_attested_inflection(self):
        import corrector,contextual_repair as Q
        tok=corrector.make_tokenizer(self.state.store)
        parts=tok('悪けれ')
        weak=Q.Reading('あくけれ','ime_reverse',0,((0,1,'あく','ime_reverse_word'),
            (1,2,'け','ime_reverse_word'),(2,3,'れ','ime_reverse_word')))
        self.assertFalse(Q._keeps_native_inflection_readings(weak,parts))
        native=Q.Reading('わるけれ','token_sequence',0,((0,3,'わるけれ','analyzed_word'),))
        self.assertTrue(Q._keeps_native_inflection_readings(native,parts))
        self.assertTrue(Q._keeps_native_inflection_readings(Q.Reading('あくけれ','current_ime_occurrence',0),parts))
        self.assertTrue(Q._keeps_native_inflection_readings(Q.Reading('あくけれ','ime_first_roundtrip',0),parts))
        for source in ('悪けれではないでしょうか。','高けれではないでしょうか。'):
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
            with self.subTest(source=source):
                self.assertEqual(result['corrected'],source)
                # The malformed connection stays unresolved; no invented success.
                self.assertTrue(result['odd_spans'])


if __name__=='__main__':unittest.main()
