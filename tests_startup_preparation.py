"""Startup stores are prepared without a discarded snapshot of document text."""
import threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

class StartupPreparationTests(unittest.TestCase):
    def test_parent_prepares_stores_without_parsing_or_reading_the_document(self):
        import app,seed_japanese,oddness,context_vec,vocabulary,analysis_async
        a=SimpleNamespace(store=SimpleNamespace(),dict_index=Mock(),_poll_warmup=Mock())
        a.editor=Mock();a.editor.get.side_effect=AssertionError('startup must not snapshot the old document')
        cv=Mock();cv.ensure_seeded.return_value=False
        threads=[];native_thread=threading.Thread
        def create_thread(*args,**kwargs):
            thread=native_thread(*args,**kwargs);threads.append(thread);return thread
        interval=app.sys.getswitchinterval()
        try:
            with patch.object(analysis_async,'prewarm') as worker,patch.object(app.corrector,'make_tokenizer',return_value='tokenizer'),patch.object(seed_japanese,'available'),patch.object(oddness,'available'),patch.object(context_vec,'ContextVectorStore',return_value=cv),patch.object(vocabulary,'build_context_vocab_cached') as parent_parse,patch.object(threading,'Thread',side_effect=create_thread):
                app.CorrectNoteApp._start_warmup(a)
                for thread in threads:thread.join(3);self.assertFalse(thread.is_alive())
                self.assertTrue(a._warmup['done']);self.assertNotIn('error',a._warmup)
                self.assertIs(a._warmup['context_vec'],cv)
                self.assertEqual(a.store._tokenize_fn,'tokenizer')
                a.dict_index.ensure_built.assert_called_once_with()
                worker.assert_called_once_with(a);a.editor.get.assert_not_called();parent_parse.assert_not_called()
        finally:
            for thread in threads:thread.join(3)
            app.CorrectNoteApp._restore_warmup_scheduler(a)
        self.assertEqual(app.sys.getswitchinterval(),interval)
    def test_completion_keeps_store_finalization_before_current_document_planning(self):
        from app import CorrectNoteApp
        for existing in (None,object()):
            with self.subTest(already_has_context=existing is not None):
                prepared=object();calls=[]
                a=SimpleNamespace(_warmup=dict(done=True,context_vec=prepared),context_vec=existing,status=Mock(),
                    _restore_warmup_scheduler=lambda:calls.append('scheduler'),
                    _learn_english_from_tabs=lambda:calls.append('finalize'),
                    _load_analysis_cache=lambda:calls.append('cache'),
                    _warm_then_analyze=lambda:calls.append('current-document'))
                CorrectNoteApp._poll_warmup(a)
                self.assertEqual(calls,['scheduler','finalize','cache','current-document'])
                self.assertIsNone(a._warmup)
                self.assertIs(a.context_vec,prepared if existing is None else existing)
                self.assertEqual(a._analyze_cause,'起動')

if __name__=='__main__':unittest.main()
