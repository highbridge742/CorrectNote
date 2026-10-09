# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
import literal_lines as L

ROWS=['',' ','\t\t',' \t　 ', 'https://example.test/a?x=1',r'C:\Synthetic\file.txt',r'"C:\Synthetic Folder\file.txt"',r'\\server\share\file.txt',' https://a.test/\tC:/Synthetic/file.txt ']


class LiteralLinesTests(unittest.TestCase):
    def test_exact_coverage_only_leaves_mixed_text_and_invalid_paths_for_analysis(self):
        for line in ROWS:
            with self.subTest(line=line):self.assertTrue(L.literal_only(line))
        for line in ('文章を確認します。','https://a.test/ を開く','前 C:/a.txt','https://','C:relative','www.example.test','https://a.test/。','https://a.test/\n文'):
            with self.subTest(line=line):self.assertFalse(L.literal_only(line))
    def test_entry_and_units_do_not_initialize_nlp_or_change_text(self):
        import correction_entry as E,units
        tokenize=Mock(side_effect=AssertionError('literal row tokenized'))
        with patch.object(E.corrector,'make_tokenizer',side_effect=AssertionError('tokenizer created')):
            for line in ROWS:
                result=E.correct_line(line,None)
                self.assertEqual(result['original'],line);self.assertEqual(result['corrected'],line)
                self.assertEqual(result['analysis_status'],'complete');self.assertFalse(result['odd_spans'])
                self.assertEqual(units.build_line_units(result,tokenize,None,None),(line,[]))
                self.assertEqual(units.build_suspect_units(result,tokenize,None,None),(line,[]))
        tokenize.assert_not_called()
    def test_worker_prepare_and_quick_literal_rows_need_no_initialized_store(self):
        from analysis_worker import Runtime
        r=Runtime();r.prepare_tables=Mock(side_effect=AssertionError('tables loaded'))
        expected=L.prepared(ROWS)
        self.assertEqual(r.execute(dict(kind='prepare',lines=ROWS)),expected)
        # No Runtime.set_state and no tokenizer: none of these rows need them.
        value=r.quick(dict(lines=ROWS,attested=(),input_method='kana',calculations={}))
        self.assertEqual(value['results'][0],None)
        for index,line in enumerate(ROWS[1:],1):
            self.assertEqual(value['results'][index]['corrected'],line)
            self.assertEqual(value['corrected_units'][index],(line,[]))
    def test_foreground_and_background_do_not_submit_literal_rows(self):
        import analysis_async as A,analysis_work_app,analysis_worker
        a=N(store=None,settings={'input_method':'kana'},_work_epoch=1,root=Mock(),status=Mock(),_analyze=Mock())
        a._analyze_work=analysis_work_app.token(a);a._analyze_dependencies=analysis_worker.state_key(a)
        a._analyze_todo=list(range(len(ROWS)));a._analyze_pos=0;a._prev_lines=ROWS
        a.line_results=[dict(original=s,corrected=s,pending=True) for s in ROWS]
        with patch.object(A,'_request',side_effect=AssertionError('literal queued')):
            self.assertEqual(A.context(a,'\n'.join(ROWS),ROWS),L.prepared(ROWS))
            A.line_step(a,len(ROWS));self.assertEqual(a._analyze_pos,len(ROWS))
            for result in a.line_results:self.assertEqual(result['analysis_status'],'complete')
            st=dict(ctx=None,pos=0,lines=ROWS,results=[None]*len(ROWS))
            A.background_step(a,st);self.assertEqual(st['pos'],len(ROWS))
            self.assertEqual(st['ctx'],{});self.assertEqual(st['words'],L.prepared(ROWS)['words'])
    def test_all_literal_replacement_cancels_only_obsolete_owned_requests(self):
        import analysis_async as A
        a=N(_async_request=('old',1),_async_background_request=('other',2))
        foreground=Mock();background=Mock()
        for worker in (foreground,background):
            worker.closed=False;worker.process.is_alive.return_value=True
        a._correction_worker=foreground;a._prefetch_worker=background
        self.assertEqual(A.context(a,'\n'.join(ROWS),ROWS),L.prepared(ROWS))
        foreground.submit.assert_called_once_with({'kind':'cancel'})
        background.submit.assert_not_called();foreground.close.assert_not_called()
        self.assertIsNone(a._async_request);self.assertEqual(a._async_background_request,('other',2))
        A.context(a,'\n'.join(ROWS),ROWS);self.assertEqual(foreground.submit.call_count,1)
        st=dict(ctx=None,pos=0,lines=ROWS,results=[None]*len(ROWS))
        A.background_step(a,st)
        background.submit.assert_called_once_with({'kind':'cancel'});background.close.assert_not_called()
        self.assertIsNone(a._async_background_request);self.assertEqual(st['pos'],len(ROWS))
        # Empty documents without a pending task must keep optional prewarm alive.
        A.context(a,'',['']);self.assertEqual(foreground.submit.call_count,1)

    def test_mixed_document_only_extracts_the_ordinary_row(self):
        from analysis_worker import Runtime
        r=Runtime();r.store=object();r.tokenize=Mock()
        def build(lines,store,cache,attested_out,tokenize_fn):
            self.assertEqual(lines,['通常の本文']);return {'context':'preserved'}
        with patch('vocabulary.build_context_vocab_cached',side_effect=build),patch('context_vec.extract_content_words',return_value=['本文']) as words:
            value=r.prepare(ROWS+['通常の本文'])
            words.assert_called_once_with(r.tokenize,'通常の本文')
            self.assertEqual(value['context'],{'context':'preserved'})
            self.assertEqual(value['words']['通常の本文'],['本文'])
            self.assertTrue(all(not v for k,v in value['words'].items() if k!='通常の本文'))


if __name__=='__main__':unittest.main()
