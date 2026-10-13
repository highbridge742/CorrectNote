# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Quick navigation shares row parsing and never reruns completed corrections."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import morphology as M,corrector as C,analysis_context as A,ime_session as I
from analysis_worker import Runtime

class QuickNavigationScopeTests(unittest.TestCase):
    def runtime(self):
        r=Runtime();r.store=SimpleNamespace(has_reading=lambda text:False)
        r.choices=r.index=r.decisions=r.context_vec=None;r.tokenize=C.make_tokenizer(r.store)
        return r
    def task(self,lines):return dict(kind='quick',lines=lines,calculations={},readings={},input_method='kana')
    def parsed(self,text):return [M.Token(text,'名詞',text,'しりょう',0,len(text),True,'一般','')]
    def test_navigation_reuses_the_correction_row_native_cache(self):
        import units
        r=self.runtime();task=self.task(['資料','資料']);seen=[]
        def correct(text,*args,**kwargs):
            r.tokenize(text);seen.append(M._TOKENIZATION_CACHE.get())
            return dict(original=text,corrected=text,analysis_status='complete')
        def displayed(result,*args,**kwargs):r.tokenize(result['original']);return result['original'],[]
        with patch.object(C,'correct_line',side_effect=correct),patch.object(units,'build_line_units',side_effect=displayed),patch.object(units,'build_suspect_units',side_effect=displayed),patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=self.parsed) as parse:
            value=r.execute(task)
            # The ordinary legacy adapter already retains this repeated text.
            self.assertEqual(parse.call_count,1)
        # 区切りの印は文字の色を使わないので、2番目の欄（品詞の色塗りの範囲）は空（v113_ctrl_boundary_marker 以降）
        self.assertIsNot(seen[0],seen[1]);self.assertEqual(value['navigation'],{'資料':((0,2),(),(('名詞',0,2),))})
        self.assertIsNone(M._TOKENIZATION_CACHE.get());self.assertIsNone(I._CURRENT.get())
    def test_navigation_shares_native_scope_when_legacy_adapter_cache_is_cold(self):
        import units
        r=self.runtime();task=self.task(['資料','資料'])
        def correct(text,*args,**kwargs):
            r.tokenize(text)
            return dict(original=text,corrected=text,analysis_status='complete')
        def displayed(result,*args,**kwargs):
            r.tokenize(result['original'])
            # A new production adapter represents a miss of its bounded cache.
            # Its native reader must still use this unchanged row's lower cache.
            r.tokenize=C.make_tokenizer(r.store)
            return result['original'],[]
        with patch.object(C,'correct_line',side_effect=correct),patch.object(units,'build_line_units',side_effect=displayed),patch.object(units,'build_suspect_units',side_effect=displayed),patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=self.parsed) as parse:
            value=r.execute(task);self.assertEqual(parse.call_count,2)
        # 区切りの印は文字の色を使わないので、2番目の欄（品詞の色塗りの範囲）は空（v113_ctrl_boundary_marker 以降）
        self.assertEqual(value['navigation'],{'資料':((0,2),(),(('名詞',0,2),))})
        self.assertIsNone(M._TOKENIZATION_CACHE.get());self.assertIsNone(I._CURRENT.get())
    def test_reused_rows_keep_navigation_without_any_new_correction(self):
        from quick_row_reuse import row_key
        r=self.runtime();task=self.task(['資料','資料',' \t　'])
        source=dict(original='資料',corrected='資料',analysis_status='complete')
        task['reuse']={i:(row_key(task,i),(source,[],('資料',[]))) for i in (0,1)}
        with patch.object(C,'correct_line',side_effect=AssertionError('completed row was recorrected')),patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=self.parsed) as parse:
            value=r.execute(task);parse.assert_called_once_with('資料')
        # 区切りの印は文字の色を使わないので、2番目の欄（品詞の色塗りの範囲）は空（v113_ctrl_boundary_marker 以降）
        self.assertEqual(value['navigation'],{'資料':((0,2),(),(('名詞',0,2),))})
        self.assertEqual(value['corrected_units'][:2],[('資料',[]),('資料',[])])
    def test_cancelled_reused_navigation_closes_scopes_without_publishing_values(self):
        from quick_row_reuse import row_key
        r=self.runtime();task=self.task(['資料']);source=dict(original='資料',corrected='資料',analysis_status='complete')
        task['reuse']={0:(row_key(task,0),(source,[],('資料',[])))};pending=[False]
        def parsed(text):pending[0]=True;return self.parsed(text)
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=parsed),A.request_scope(lambda:pending[0]):
            with self.assertRaises(A.SupersededAnalysis):r.execute(task)
        self.assertIsNone(M._TOKENIZATION_CACHE.get());self.assertIsNone(I._CURRENT.get());self.assertIsNone(A._REQUEST_CHECK.get())

if __name__=='__main__':unittest.main()
