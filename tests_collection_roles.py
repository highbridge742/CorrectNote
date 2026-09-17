# -*- coding: utf-8 -*-
"""Literal gathering and resolving disorder keep their separate meanings."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('収集'),'requires native dictionary')
class CollectionRoleTests(unittest.TestCase):
    def tokens(self,text):
        return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]

    def test_actual_disorder_argument_conflicts_with_literal_gathering(self):
        for noun in ('混乱','騒動','紛糾','混迷'):
            text=noun+'を収集します。'
            with self.subTest(text=text):
                self.assertTrue(S.conflicting_object_predicates(text,self.tokens(text)))
                self.assertTrue(S.support(noun,'収拾'))
                self.assertFalse(S.support(noun,'収集'))
        self.assertIn('集める',S.object_predicate_conflict_reason('混乱','収集'))

    def test_existing_gathering_sense_and_other_case_owners_remain_valid(self):
        for noun in ('情報','資料','写真','記録'):
            self.assertTrue(S.support(noun,'収集'))
            self.assertTrue(S.support(noun,'収拾'))
        for text in ('混乱の記録を収集します。','混乱に関する情報を収集します。',
                     '資料を収拾します。','問題を収集します。','しらゆほを収集します。',
                     '混乱を収集させます。','混乱を収集すると書きました。',
                     '混乱を収集する人です。'):
            with self.subTest(text=text):
                self.assertEqual(S.conflicting_object_predicates(text,self.tokens(text)),[])

    def test_application_repairs_same_reading_without_changing_valid_uses(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (
                ('この混乱を収集します。','この混乱を収拾します。'),
                ('騒動を収集します。','騒動を収拾します。'),
                ('騒動を収集して事情を説明します。','騒動を収拾して事情を説明します。'),
                ('資料を収拾します。','資料を収拾します。'),
                ('情報を収集します。','情報を収集します。'),
                ('混乱に関する情報を収集します。','混乱に関する情報を収集します。'),
                ('こんらんをしゅうしゅうします。','こんらんをしゅうしゅうします。'),
                ('「混乱を収集します」という誤記です。','「混乱を収集します」という誤記です。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])

    def test_original_rejection_ledger_remains_authoritative(self):
        import app
        from decisions import DecisionStore
        from tests_analysis_async import initial
        a=initial();ledger=DecisionStore();ledger.reject('収集','収拾')
        text='混乱を収集します。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=ledger)
        self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
