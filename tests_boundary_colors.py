# -*- coding: utf-8 -*-
import unittest
from text_navigation import boundary_spans,text_boundaries,text_edge

def token(word,pos,a):return (word,pos,word,a,a+len(word),True)

class BoundarySpanTests(unittest.TestCase):
    def test_compound_function_word_particle_and_terminal_pos(self):
        text='とはいえ、私は進む。'
        parts=[token('とはいえ','接続詞',0),token('、','記号',4),token('私','名詞',5),
               token('は','助詞',6),token('進む','動詞',7),token('。','記号',9)]
        self.assertEqual(boundary_spans(text,parts),((0,5),(6,7),(7,10)))
        stops=text_boundaries(text,parts)
        self.assertEqual(stops,(0,5,7,10))
        for col in range(len(text)+1):
            self.assertEqual(text_edge(text,col,1,parts),next((z for z in stops if z>col),len(text)))
            self.assertEqual(text_edge(text,col,-1,parts),next((z for z in stops[::-1] if z<col),0))

    def test_symbols_closed_brackets_and_runs_include_previous_pos(self):
        text='（文章）次へ！？'
        parts=[token('（','記号',0),token('文章','名詞',1),token('）','記号',3),
               token('次','名詞',4),token('へ','助詞',5),token('！？','記号',6)]
        self.assertEqual(boundary_spans(text,parts),((1,4),(5,8)))
        # A generic symbol at the line edge extends the whole preceding POS.
        self.assertEqual(boundary_spans('日本語★',[token('日本語','名詞',0),token('★','記号',3)]),((0,4),))
        self.assertEqual(boundary_spans('文。「」',[token('文','名詞',0),token('。','記号',1),token('「','記号',2),token('」','記号',3)]),((0,2),))

    def test_whitespace_unknown_no_token_and_unpaired_opening_do_not_guess(self):
        self.assertEqual(boundary_spans(' \t　',[token(' \t　','記号',0)]),())
        self.assertEqual(boundary_spans('「」',[token('「','記号',0),token('」','記号',1)]),())
        self.assertEqual(boundary_spans('文（',[token('文','名詞',0),token('（','記号',1)]),((0,1),))
        self.assertEqual(boundary_spans('日本語。'),())

    def test_unicode_offsets_and_multichar_pos_are_python_offsets(self):
        text='😀資料について、確認する。'
        parts=[token('😀','記号',0),token('資料','名詞',1),token('について','助詞',3),
               token('、','記号',7),token('確認','名詞',8),token('する','動詞',10),token('。','記号',12)]
        self.assertEqual([(a,z,text[a:z]) for a,z in boundary_spans(text,parts)],
                         [(3,8,'について、'),(10,13,'する。')])


    def test_long_symbol_run_merges_same_pos_without_changing_stops(self):
        text='文章'+')'*3000
        self.assertEqual(boundary_spans(text,[token('文章','名詞',0)]),((0,len(text)),))
        self.assertEqual(len(text_boundaries(text)),3001)

class BoundaryWorkerValueTests(unittest.TestCase):
    def test_deduplicated_values_skip_all_literal_rows(self):
        from boundary_colors import plans
        from unittest.mock import Mock
        fn=Mock(return_value=[token('資料','名詞',0),token('を','助詞',2)])
        value=plans(['資料を','資料を','', ' \t　','https://example.test/','C:\\資料\\メモ.txt','x'*4001],fn)
        fn.assert_called_once_with('資料を')
        self.assertEqual(value,{'資料を':((0,3),(),
            (('名詞',0,2),('助詞',2,3)))})

    def test_render_plans_skip_legacy_pos_wide_highlight_calculation(self):
        from text_navigation import plans
        from unittest.mock import patch
        parts=[token('資料','名詞',0),token('を','助詞',2)]
        with patch('text_navigation.boundary_spans',side_effect=AssertionError('unused highlight span')):
            value=plans(['資料を'],lambda text:parts)
        self.assertEqual(value['資料を'][0],(0,3))
        self.assertEqual(value['資料を'][1],())

    def test_marker_ranges_are_only_the_character_before_each_stop(self):
        from boundary_colors import boundary_marker_spans
        text='😀資料について、確認する。'
        stops=(0,1,3,7,8,10,13)
        spans=boundary_marker_spans(text,stops)
        self.assertEqual(spans,tuple((stop-1,stop) for stop in stops[1:-1]))
        self.assertEqual([text[a:z] for a,z in spans],
                         ['😀','料','て','、','認'])

    def test_cancelled_plan_never_publishes_a_partial_value(self):
        from boundary_colors import plans
        from analysis_context import request_scope,SupersededAnalysis
        pending=[False]
        def parse(text):
            pending[0]=True
            return [token(text,'名詞',0)]
        with request_scope(lambda:pending[0],poll_interval=0):
            with self.assertRaises(SupersededAnalysis):plans(['資料'],parse)

    def test_volatile_cache_is_bounded_by_count_and_total_characters(self):
        from boundary_colors import remember,ready_for,PLAN_CACHE_ROWS,PLAN_CACHE_CHARS
        from types import SimpleNamespace
        a=SimpleNamespace()
        value=((0,3),((2,3),))
        self.assertGreaterEqual(PLAN_CACHE_ROWS,3000)
        remember(a,{str(i):value for i in range(PLAN_CACHE_ROWS+72)})
        self.assertEqual(len(a._ctrl_boundary_plans),PLAN_CACHE_ROWS)
        self.assertFalse(ready_for(a,'0'));self.assertTrue(ready_for(a,str(PLAN_CACHE_ROWS+71)))
        remember(a,{str(i)+'x'*4000:value for i in range(PLAN_CACHE_CHARS//4000+10)})
        self.assertLessEqual(sum(map(len,a._ctrl_boundary_plans)),PLAN_CACHE_CHARS)
        self.assertLessEqual(len(a._ctrl_boundary_plans),PLAN_CACHE_ROWS)

    def test_actual_runtime_navigation_matches_native_and_keeps_result(self):
        from tests_analysis_async import initial
        from analysis_worker import Runtime,snapshot
        from unittest.mock import patch
        from boundary_colors import plans
        import correction_entry
        a=initial();r=Runtime();r.set_state(snapshot(a))
        text='😀資料について、確認する。'
        result=correction_entry.correct_line(text,a.store,dict_index=a.dict_index,decisions=a.decisions)
        with patch.object(correction_entry,'correct_line',side_effect=AssertionError('units reran correction')):
            value=r.execute(dict(kind='units',result=result,lines=[text]))
        self.assertIs(value['result'],result)
        displayed=[result['original'],result['corrected'],value['original_units'][0],value['corrected_units'][0]]
        self.assertEqual(value['navigation'],plans(displayed,r.tokenize))
        self.assertTrue(value['navigation'][text][0])

if __name__=='__main__':unittest.main()
