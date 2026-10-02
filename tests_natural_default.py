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
        self.assertEqual(expected,r['corrected'],source)
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
                    ('結果を機論して資料を閉じます。','結果を記録して資料を閉じます。'),
                    ('必要な部分だけを点刷してください。','必要な部分だけを印刷してください。')]:
            with self.subTest(source=a):self.check(a,b)

    def test_native_processes_and_relative_actions(self):
        for source in ('再構成','再変換','再初期化','再評価','器官が再退化する',
                       '取る手段','取れる手段','採る手段','使える方法'):
            with self.subTest(source=source):self.check(source,source)

if __name__=='__main__':unittest.main()
