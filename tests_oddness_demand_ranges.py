# -*- coding: utf-8 -*-
"""Protect actual anomaly scopes without expanding unused source ranges."""
import unittest
from unittest.mock import patch
import morphology as M
import oddness as O
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class DemandSourceRangesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        import corrector
        cls.app=initial()
        cls.tokenize=staticmethod(corrector.make_tokenizer(cls.app.store))

    @classmethod
    def tearDownClass(cls):
        from last_choice import set_active
        set_active(None)

    def rows(self,text,with_spans,**options):
        return O.is_odd_run(text,self.tokenize,with_spans=with_spans,
            store=self.app.store,dict_index=self.app.dict_index,**options)

    def test_normal_written_connection_has_no_range_to_protect(self):
        for text in ('資料を保存しました。','設定を再確認しました。'):
            self.assertFalse(R.intact_native_reading(text))
            for spans in (False,True):
                with self.subTest(text=text,spans=spans),patch.object(
                        R,'native_context_ranges',side_effect=AssertionError('unused range expansion')):
                    self.assertFalse(self.rows(text,spans))

    def test_three_token_mark_keeps_its_original_two_token_protection_scope(self):
        text='平ね仮名'
        for spans in (False,True):
            expected=('平ね','仮名')+((0,4) if spans else ())
            with self.subTest(spans=spans),patch.object(R,'native_context_ranges',return_value=()):
                self.assertEqual(self.rows(text,spans),[expected])
            # The old pair guard checked 0:2 before forming the 0:4 mark.
            # Delaying that guard must not accidentally use the wider output.
            with patch.object(R,'native_context_ranges',return_value=((0,2),)):
                self.assertFalse(self.rows(text,spans))

    def test_ranges_do_not_merge_or_protect_only_part_of_a_bad_pair(self):
        text='赤いだ。'
        for spans in (False,True):
            expected=('赤い','だ')+((0,3) if spans else ())
            with self.subTest(spans=spans),patch.object(
                    R,'native_context_ranges',return_value=((0,2),(2,3))):
                self.assertEqual(self.rows(text,spans),[expected])
            with patch.object(R,'native_context_ranges',return_value=((0,3),)) as ranges:
                self.assertFalse(self.rows(text,spans))
                ranges.assert_called_once_with(text)

    def test_optional_opaque_object_range_keeps_the_same_pair_boundary(self):
        text='赤いだ。'
        for preserve in (False,True):
            with self.subTest(preserve=preserve),patch.object(
                    R,'native_context_ranges',return_value=()),patch.object(
                    R,'source_opaque_object_ranges',return_value=((0,2,3),)):
                actual=self.rows(text,True,preserve_unknown_source=preserve)
                self.assertEqual(actual,[] if preserve else [('赤い','だ',0,3)])


if __name__=='__main__':unittest.main()
