# -*- coding: utf-8 -*-
import unittest
from dataclasses import replace
import morphology as M
import contextual_repair as C


@unittest.skipUnless(M.dictionary_inflections('読み'),'requires native dictionary')
class NativeVerbPrefixTests(unittest.TestCase):
    def target(self,source='読み乳力します'):
        return C.RepairTarget(source,0,4,0,len(source),(('力','し',3,5),),True,source[4:])

    def test_same_source_facts_and_wide_candidate_are_retained(self):
        original=self.target()
        targets=C._native_verb_prefix_targets([original])
        self.assertIn(original,targets)
        self.assertEqual(len(targets),2)
        narrow=next(t for t in targets if t.start==2)
        self.assertEqual(narrow.text,'乳力')
        self.assertEqual(narrow.anomalies,original.anomalies)
        self.assertEqual(narrow.context,original.context)
        self.assertEqual(narrow.following,original.following)
        self.assertEqual(C._native_verb_prefix_targets(targets),targets)

    def test_changed_prefix_and_owned_spelling_do_not_supply_a_seam(self):
        original=self.target()
        for target in (replace(original,anomalies=(('読み','乳',0,3),)),
                       replace(original,spelling=('source-fact',)),
                       replace(original,preserved_head='読み'),
                       replace(original,boundary_kind='kana_predicate'),
                       self.target('読む乳力します'),self.target('読み退見ます')):
            with self.subTest(target=target):
                self.assertEqual(C._native_verb_prefix_targets([target]),[target])

    def test_native_prefix_keeps_its_text_when_following_homophone_is_repaired(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('隣のキーを巻き込み乳力してしまいます。','隣のキーを巻き込み入力してしまいます。'),
            ('文字を読み乳力します。','文字を読み入力します。'),
            ('文章を選び乳力します。','文章を選び入力します。'),
            ('隣のキーを巻き込み入力してしまいます。','隣のキーを巻き込み入力してしまいます。'),
            ('文字を読み入力します。','文字を読み入力します。'),
            ('書類を読み入籍します。','書類を読み入籍します。'),
            ('乳牛の乳を搾ります。','乳牛の乳を搾ります。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
        text='雨が降る前に洗濯物を取り退見ます。'
        result=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(result['corrected'],text)
        self.assertTrue(result['odd_spans'])
        result=app.correct_line('荷物を受け市取って住所を確かめます。',a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(result['corrected'],'荷物を受け取って住所を確かめます。')
        self.assertEqual(result['odd_spans'],[])


if __name__=='__main__':unittest.main()
