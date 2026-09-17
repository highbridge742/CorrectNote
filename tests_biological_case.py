# -*- coding: utf-8 -*-
import unittest
import morphology as M
import semantic_roles as S

@unittest.skipUnless(M.dictionary_inflections('長生'),'requires native dictionary')
class BiologicalCaseTests(unittest.TestCase):
    def tokens(self,text):
        return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]

    def test_known_objects_conflict_without_using_any_repair_answer(self):
        for noun in ('日程','予定','計画','資料','画面','辞書','機器'):
            for predicate in ('長生','長生き','生存','生息'):
                text=noun+'を'+predicate+'します。'
                with self.subTest(text=text):
                    self.assertTrue(S.conflicting_object_predicates(text,self.tokens(text)))
        for text in ('魚が長生きします。','魚を長生きさせます。','日程を長生すると記録します。',
                     '日程を長生する人の話です。','百年を長生します。','時間を生存します。',
                     'しらゆほを長生します。','長生する予定を確認します。'):
            with self.subTest(text=text):
                self.assertEqual(S.conflicting_object_predicates(text,self.tokens(text)),[])

    def test_adjustment_roles_are_shared_by_normal_contexts(self):
        for noun in ('日程','予定','計画','設定','数値','機器','画面'):
            with self.subTest(noun=noun):self.assertTrue(S.support(noun,'調整'))
        self.assertFalse(S.support('しらゆほ','調整'))
        self.assertFalse(S.conflicting_object_predicates('設定を生存します。',self.tokens('設定を生存します。')))

    def test_native_homophones_restore_schedule_and_keep_controls(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('会議の日程を長生します。','会議の日程を調整します。'),
            ('明日の予定を長生します。','明日の予定を調整します。'),
            ('全体の計画を長生します。','全体の計画を調整します。'),
            ('画面を長生します。','画面を調整します。'),
            ('祖父が長生します。','祖父が長生します。'),
            ('魚を長生きさせます。','魚を長生きさせます。'),
            ('「日程を長生します」という誤記です。','「日程を長生します」という誤記です。')):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],expected);self.assertEqual(r['odd_spans'],[])

if __name__=='__main__':unittest.main()

