# -*- coding: utf-8 -*-
"""A worker row releases read-only resources after correction and display units."""
import correction_entry
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import morphology as M
import ime_session as I
from analysis_context import SupersededAnalysis
from analysis_worker import Runtime

class WorkerScopeTests(unittest.TestCase):
    def exercise(self,kind='line',error=None):
        import app,units,corrector
        events=[];resources=[];seen=[]
        class Handle:
            def close(self):events.append('closed')
        def visit(label,line):
            handle,retained=I.retain(Handle())
            self.assertTrue(retained,label);resources.append(handle)
            tokens=M.tokenize(line);self.assertEqual(tokens[0].surface,line)
            tokens[0].surface='locally mutated'
            seen.append((label,M._TOKENIZATION_CACHE.get()))
        def correct(line,*args,**kw):
            # The ordinary correction entry owns nested scopes itself.
            with M.tokenization_scope(),I.resource_scope():visit('correct',line)
            return dict(original=line,corrected=line,changed=False,odd_spans=[],analysis_status='complete')
        def display(result,*args,**kw):
            visit('display',result['original'])
            if error:raise error
            return result['original'],[]
        def suspect(result,*args,**kw):
            visit('suspect',result['original']);return result['original'],[]
        runtime=Runtime();runtime.store=SimpleNamespace(has_reading=lambda text:False)
        runtime.choices=runtime.index=runtime.decisions=runtime.context_vec=None;runtime.tokenize=M.tokenize
        task=dict(kind=kind,line='資料',context={},input_method='kana',result=dict(original='資料',corrected='資料'),lines=['資料','資料'],calculations={})
        if kind=='units':task.pop('lines')
        groups=2 if kind=='quick' else 1
        with patch.object(correction_entry,'correct_line',side_effect=correct),patch.object(corrector,'correct_line',side_effect=correct),patch.object(units,'build_line_units',side_effect=display),patch.object(units,'build_suspect_units',side_effect=suspect),patch.object(M,'HAS_JANOME',True),patch.object(M,'_tokenize_uncached',side_effect=lambda line:[M.Token(line,'名詞',line,'しりょう',0,len(line),True,'一般','')]) as parse:
            if error:
                with self.assertRaises(type(error)):runtime.execute(task)
            else:
                value=runtime.execute(task);self.assertEqual(value['corrected_units'],[('資料',[])]*2 if kind=='quick' else ('資料',[]))
            self.assertEqual(parse.call_count,groups)
        self.assertTrue(resources)
        if kind=='quick':
            self.assertIsNot(resources[0],resources[3]);self.assertIsNot(seen[0][1],seen[3][1])
            for start in (0,3):
                self.assertTrue(all(x is resources[start] for x in resources[start:start+3]))
                self.assertTrue(all(cache is seen[start][1] for _,cache in seen[start:start+3]))
        else:
            self.assertTrue(all(x is resources[0] for x in resources))
            self.assertTrue(all(cache is seen[0][1] for _,cache in seen))
        self.assertEqual(events,['closed']*groups)
        self.assertIsNone(M._TOKENIZATION_CACHE.get());self.assertIsNone(I._CURRENT.get())
        return seen

    def test_correction_and_both_unit_views_share_one_readonly_scope(self):
        self.assertEqual([name for name,_ in self.exercise()],['correct','display','suspect'])

    def test_quick_lines_share_within_each_row_and_release_between_rows(self):
        self.assertEqual([name for name,_ in self.exercise(kind='quick')],['correct','suspect','display']*2)

    def test_cached_result_units_share_scope_without_recorrecting(self):
        self.assertEqual([name for name,_ in self.exercise(kind='units')],['display','suspect'])

    def test_error_and_newer_input_release_every_owned_resource(self):
        for error in (ValueError('unit failed'),SupersededAnalysis()):
            with self.subTest(error=type(error)):self.exercise(error=error)

if __name__=='__main__':unittest.main()
