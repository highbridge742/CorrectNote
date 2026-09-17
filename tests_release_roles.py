# -*- coding: utf-8 -*-
"""Physical access and a person's release have different explicit arguments."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('開放'),'requires native dictionary')
class ReleaseRoleTests(unittest.TestCase):
    def tokens(self,text):
        return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
                for t in M.tokenize(text)]

    def test_negative_evidence_uses_written_action_and_actual_person(self):
        for noun in ('人質','捕虜','囚人','奴隷','人','子供'):
            text=noun+'を開放します。'
            with self.subTest(text=text):
                self.assertTrue(S.conflicting_object_predicates(text,self.tokens(text)))
                self.assertTrue(S.support(noun,'解放'))
                self.assertFalse(S.support(noun,'開放'))

    def test_source_places_objects_and_open_scopes_are_retained(self):
        for text in ('教室を開放します。','扉を開放します。','校庭を開放します。',
                     '心を開放します。','メモリを開放します。','しらゆほを開放します。',
                     '人質に部屋を開放します。','人質を開放させます。',
                     '人質を開放すると記録します。','人質を開放する人です。',
                     '人質が開放します。'):
            with self.subTest(text=text):
                self.assertEqual(S.conflicting_object_predicates(text,self.tokens(text)),[])

    def test_closed_connected_predicate_uses_the_same_category(self):
        text='人質を開放して扉を閉めます。'
        self.assertEqual(S.conflicting_object_predicates(text,self.tokens(text)),[('人質','開放',3,5)])
        reason=S.object_predicate_conflict_reason('人質','開放')
        self.assertIn('人を直接の対象',reason)
        self.assertNotIn('費用',reason)

    def test_application_repairs_the_homophone_and_keeps_correct_uses(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (
                ('人質を開放します。','人質を解放します。'),
                ('捕虜を開放します。','捕虜を解放します。'),
                ('人質を開放して扉を閉めます。','人質を解放して扉を閉めます。'),
                ('教室を開放します。','教室を開放します。'),
                ('扉を開放します。','扉を開放します。'),
                ('人質を解放します。','人質を解放します。'),
                ('「人質を開放します」という誤記です。','「人質を開放します」という誤記です。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
