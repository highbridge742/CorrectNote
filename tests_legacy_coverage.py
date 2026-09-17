# -*- coding: utf-8 -*-
import unittest
from dataclasses import replace
import morphology as M
import contextual_repair as C

class LegacyCoverageTests(unittest.TestCase):
    def test_wider_candidate_retains_original_facts_and_context(self):
        text='あぐせすもにたに行きます。'
        target=C.RepairTarget(text,0,4,0,len(text)-1,(('せ','す',2,4),),True,text[4:-1])
        rows=C._legacy_covering_targets([target],[(0,7,'アクセスモニタ')])
        self.assertIn(target,rows)
        self.assertEqual(len(rows),2)
        wide=rows[1]
        self.assertEqual((wide.start,wide.end,wide.text),(0,7,text[:7]))
        self.assertEqual(wide.anomalies,target.anomalies)
        self.assertEqual(wide.context,target.context)
        self.assertEqual(wide.following,text[7:-1])
        self.assertEqual(C._legacy_covering_targets(rows,[(0,7,'アクセスモニタ')]),rows)

    def test_spelling_and_preserved_heads_do_not_expand(self):
        text='原文です。'
        target=C.RepairTarget(text,1,2,0,4,(('原','文',0,2),),True,'です')
        for guarded in (replace(target,preserved_head='文'),replace(target,spelling=('source-fact',))):
            self.assertEqual(C._legacy_covering_targets([guarded],[(0,4,'別表記')]),[guarded])
        self.assertEqual(C._legacy_covering_targets([target],[(0,5,'句点越え')]),[target])

@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class NativeLegacyCoverageTests(unittest.TestCase):
    def test_later_auxiliary_inside_a_loan_is_not_a_predicate_head(self):
        import corrector
        from tests_analysis_async import initial
        a=initial();tk=corrector.make_tokenizer(a.store)
        text='あぐせすもにたに行きます'
        target=C.RepairTarget(text,0,7,0,len(text),(),True,text[7:])
        self.assertFalse(C._source_predicate_context(target,tk))
        text='おくます'
        target=C.RepairTarget(text,0,len(text),0,len(text),(),True,'')
        self.assertTrue(C._source_predicate_context(target,tk))

    def test_wide_loan_and_kana_predicates_share_final_selection(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            ('あぐせすもにたに行きます。','アクセスモニタに行きます。'),
            ('アクセスモニタに行きます。','アクセスモニタに行きます。'),
            ('アクセスも確認します。','アクセスも確認します。'),
            ('まどをしめてからほんをよみんす。','まどをしめてからほんをよみます。'),
            ('おくます。','おきます。')):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],expected);self.assertEqual(r['odd_spans'],[])

if __name__=='__main__':unittest.main()

