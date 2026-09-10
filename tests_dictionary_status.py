# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import corrector as C
import dict_index as D


class DictionaryStatusTests(unittest.TestCase):
    def result(self):
        return dict(original='文章',corrected='文章',changed=False,details=[],spans=[],
                    original_spans=[],odd_spans=[],odd_reasons=[],unsure_spans=[])

    def test_missing_dependency_never_reports_success_on_second_call(self):
        index=D.DictIndex()
        with patch.object(D,'HAS_JANOME',False),patch.object(index,'_load_cache',return_value=False):
            self.assertFalse(index.ensure_built())
            self.assertFalse(index.ensure_built())
            self.assertEqual(index.resource_status,{'state':'missing_dependency','readings':0})

    def test_empty_build_is_not_success(self):
        index=D.DictIndex()
        def empty(*args):index._by_reading={};index._by_surface={}
        with patch.object(D,'HAS_JANOME',True),patch.object(index,'_load_cache',return_value=False), \
             patch.object(index,'_build',side_effect=empty),patch.object(index,'_save_cache'):
            self.assertFalse(index.ensure_built())
            self.assertEqual(index.resource_status['state'],'empty')

    def test_available_index_and_uninitialized_index_are_distinct(self):
        index=D.DictIndex()
        self.assertEqual(index.resource_status['state'],'not_initialized')
        index._by_reading={'よみ':['読み']}
        self.assertTrue(index.ensure_built())
        self.assertEqual(index.resource_status,{'state':'available','readings':1})

    def test_missing_index_limits_result_without_claiming_candidate_zero(self):
        out=C._line_result_contract('文章',self.result(),None,D.DictIndex())
        self.assertEqual(out['analysis_status'],'limited')
        self.assertEqual(out['diagnosis']['judgement'],'undetermined')
        self.assertEqual(out['diagnosis']['missing_resources'],['dictionary_index'])
        self.assertEqual(out['diagnosis']['resource_status']['dictionary_index']['state'],
                         'not_initialized')

    def test_missing_index_does_not_erase_detected_anomaly_or_interruption(self):
        result=self.result();result.update(odd_spans=[(0,2)],analysis_status='incomplete',
                                          stop_reason='depth_limit')
        out=C._line_result_contract('文章',result,None,D.DictIndex())
        self.assertEqual(out['analysis_status'],'incomplete')
        self.assertEqual(out['stop_reason'],'depth_limit')
        self.assertEqual(out['diagnosis']['judgement'],'anomaly_detected')

    def test_root_wrapper_forwards_positional_and_keyword_index(self):
        @C._with_line_result
        def dummy(line,*args,**kwargs):return self.result()
        index=D.DictIndex()
        for result in (dummy('文章',None,None,dict_index=index),
                       dummy('文章',None,None,None,1.6,None,None,'kana',None,index)):
            self.assertEqual(result['analysis_status'],'limited')
            self.assertIn('dictionary_index',result['diagnosis']['missing_resources'])


if __name__=='__main__':unittest.main()
