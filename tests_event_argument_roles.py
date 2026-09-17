# -*- coding: utf-8 -*-
"""An event setting and distributed content keep independent case roles."""
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('配る'),'requires native dictionary')
class EventArgumentRoleTests(unittest.TestCase):
    def test_positive_roles_are_case_specific(self):
        for noun in ('資料','写真','食料','お金'):
            self.assertTrue(S.support(noun,'配る'),noun)
        for noun in ('会議','教室'):
            self.assertTrue(S.case_action_support(noun,'で','配布'),noun)
        self.assertFalse(S.support('会議','配る'))
        self.assertFalse(S.case_action_support('懐疑','で','配布'))
        self.assertFalse(S.case_action_support('しらゆほ','で','配布'))

    def test_native_unchanged_arguments_share_the_same_predicate(self):
        for text in ('しりょうをくばります','かいぎでしりょうをくばります',
                     'あしたのかいぎでしりょうをくばります',
                     'きょうしつでしりょうをはいふします',
                     'かいぎでけっかをほうこくします'):
            self.assertTrue(R.completed_native_reading_clause(text,
                require_nominal=True,require_object_fit=True),text)
        for text in ('かいぎでしりょうをたべます','かいぎをくばります',
                     'ぷねらでしりょうをくばります'):
            self.assertFalse(R.completed_native_reading_clause(text,
                require_nominal=True,require_object_fit=True),text)


if __name__=='__main__':unittest.main()
