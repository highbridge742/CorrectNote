# -*- coding: utf-8 -*-
"""Whole native readings do not enumerate unused pair-protection ranges."""
import unittest
from unittest.mock import patch
import morphology as M
import oddness as O
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class LazyNativeProtectionTests(unittest.TestCase):
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

    def test_complete_kana_reading_needs_no_pair_ranges(self):
        for text in ('しりょうをほぞんしました。','ほんをよみます。',
                     'みたらねる。','かいてあるほんをよむ。'):
            self.assertTrue(R.intact_native_reading(text),text)
            for with_spans in (False,True):
                with self.subTest(text=text,with_spans=with_spans),patch.object(
                        R,'native_context_ranges',side_effect=AssertionError('unused range expansion')):
                    reasons={}
                    self.assertFalse(O.is_odd_run(text,self.tokenize,with_spans=with_spans,
                        preserve_unknown_source=True,store=self.app.store,
                        dict_index=self.app.dict_index,reading_reasons_out=reasons))
                    self.assertFalse(reasons)

    def test_unproved_reading_keeps_pair_protection_and_source_reason(self):
        text='処理がじゃのになっていないだろうか。'
        self.assertFalse(R.intact_native_reading(text))
        for with_spans in (False,True):
            with self.subTest(with_spans=with_spans),patch.object(
                    R,'native_context_ranges',wraps=R.native_context_ranges) as ranges:
                reasons={}
                rows=O.is_odd_run(text,self.tokenize,with_spans=with_spans,
                    store=self.app.store,dict_index=self.app.dict_index,
                    reading_reasons_out=reasons)
                expected=('名詞化の接続','節のない非自立名詞')
                self.assertEqual(rows,[expected+(3,6)] if with_spans else [expected])
                self.assertEqual(reasons,{(3,6):'名詞化する「の」の前が接続詞だけで、名詞化する節がありません'})
                # The existing source-specific reason needs no pair range.
                # Only the span-output filter enumerates its protection.
                if with_spans:ranges.assert_called_once_with(text)
                else:ranges.assert_not_called()


if __name__=='__main__':unittest.main()
