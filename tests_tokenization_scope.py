# -*- coding: utf-8 -*-
"""Native parse reuse is transient, isolated and safe from mutable callers."""
import unittest
from unittest.mock import patch
from contextvars import Context
import morphology as M


class TokenizationScopeTests(unittest.TestCase):
    def native(self,text):
        return [M.Token(text,'名詞',text,'よみ',0,len(text),True,'一般','')]

    def test_reuses_only_inside_one_analysis_and_copies_mutable_tokens(self):
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=self.native) as parse:
            with M.tokenization_scope():
                first=M.tokenize('原文');first[0].reading='汚染';first.clear()
                second=M.tokenize('原文');second[0].surface='別の語'
                self.assertEqual(M.tokenize('原文')[0].surface,'原文')
                self.assertEqual(M.tokenize('原文')[0].reading,'よみ')
                self.assertEqual(parse.call_count,1)
            self.assertIsNone(M._TOKENIZATION_CACHE.get())
            M.tokenize('原文')
            with M.tokenization_scope():M.tokenize('原文')
            self.assertEqual(parse.call_count,3)

    def test_nested_calls_reuse_scope_but_other_context_does_not(self):
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=self.native) as parse:
            with M.tokenization_scope():
                M.tokenize('原文')
                with M.tokenization_scope():M.tokenize('原文')
                def other():
                    self.assertIsNone(M._TOKENIZATION_CACHE.get())
                    with M.tokenization_scope():M.tokenize('原文')
                Context().run(other)
                M.tokenize('原文')
            self.assertEqual(parse.call_count,2)

    def test_exception_releases_scope(self):
        with self.assertRaises(ValueError):
            with M.tokenization_scope():raise ValueError('synthetic failure')
        self.assertIsNone(M._TOKENIZATION_CACHE.get())

    def test_capacity_is_bounded_without_changing_output(self):
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=self.native) as parse,patch.object(M,'_TOKENIZATION_CACHE_LIMIT',2):
            with M.tokenization_scope():
                for source in ('一','二','三','一'):
                    self.assertEqual(M.tokenize(source)[0].surface,source)
                    self.assertLessEqual(len(M._TOKENIZATION_CACHE.get()),2)
            self.assertEqual(parse.call_count,4)

    def test_engine_entry_and_final_contract_share_the_scope(self):
        import corrector as C
        def body(line,*args,**kwargs):
            self.assertIsNotNone(M._TOKENIZATION_CACHE.get())
            M.tokenize(line)
            return dict(original=line,corrected=line)
        def contract(line,result,*args):
            M.tokenize(line)
            return result
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=self.native) as parse,patch.object(C,'_line_result_contract',side_effect=contract):
            self.assertEqual(C._with_line_result(body)('原文')['corrected'],'原文')
            self.assertEqual(parse.call_count,1)
        self.assertIsNone(M._TOKENIZATION_CACHE.get())

    @unittest.skipUnless(M.HAS_JANOME,'actual native parser')
    def test_real_tokens_and_column_coordinates_are_unchanged(self):
        def values(tokens):return [tuple(getattr(t,k) for k in M.Token.__slots__) for t in tokens]
        for source in ('資料を確認しました。','入力\tしゅうりょう⇒終了','ふあいるをひらきます','書くことかあります'):
            before=values(M.tokenize(source))
            with M.tokenization_scope():
                self.assertEqual(values(M.tokenize(source)),before)
                self.assertEqual(values(M.tokenize(source)),before)

if __name__=='__main__':unittest.main()
