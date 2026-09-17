# -*- coding: utf-8 -*-
"""A known original semantic conflict cannot become an unrelated native word."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('収集'),'requires native dictionary')
class ConflictRepairFitTests(unittest.TestCase):
    def test_changed_action_must_fit_its_own_object(self):
        for old,new in (
                ('混乱を収集します。','混乱を収拾します。'),
                ('人質を開放します。','人質を解放します。'),
                ('費用を生産します。','費用を清算します。'),
                ('日程を長生します。','日程を調整します。'),
                ('混乱を収集して事情を説明します。','混乱を収拾して事情を説明します。')):
            with self.subTest(new=new):
                self.assertTrue(S.changed_object_conflict_allowed(old,new))
        for new in ('混乱を修習します。','混乱を集収します。',
                    '混乱をします。'):
            with self.subTest(new=new):
                self.assertFalse(S.changed_object_conflict_allowed('混乱を収集します。',new))
        self.assertFalse(S.changed_object_conflict_allowed(
            '混乱を収集して資料を収集します。','混乱を修習して資料を収集します。'))

    def test_ordinary_unknown_and_quoted_sources_create_no_requirement(self):
        for old,new in (
                ('しらゆほを収集します。','しらゆほを修習します。'),
                ('情報を収集します。','情報を集収します。'),
                ('「混乱を収集します」という誤記です。','「混乱を修習します」という誤記です。'),
                ('混乱を収集します。','この混乱を収集します。')):
            with self.subTest(old=old):
                self.assertTrue(S.changed_object_conflict_allowed(old,new))

    def test_common_final_checks_wide_and_narrow_edits(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();text='この混乱を収集します。'
        def tokens(value):
            return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
                    for t in M.tokenize(value)]
        start=text.index('収集')
        for replacement in ((start,start+2,'修習','文脈'),
                            (0,len(text),'この混乱を修習します。','文脈')):
            with self.subTest(replacement=replacement):
                result,reason=C._check_replacement(text,replacement,a.store,tokens,a.dict_index)
                self.assertIsNone(result)
                self.assertEqual(reason,'unproven_semantic_conflict_repair')


if __name__=='__main__':unittest.main()
