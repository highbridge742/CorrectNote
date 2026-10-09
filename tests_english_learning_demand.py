"""English registration keeps its admission rules without preparing unused words."""
import copy
import unittest
from unittest.mock import Mock,patch
import loanword as L
from vocabulary import VocabularyStore
from seed_vocabulary import load_seed


def initial_store():
    store=VocabularyStore();load_seed(store)
    return store


class EnglishLearningDemandTests(unittest.TestCase):
    def test_non_candidates_do_not_request_vocabulary(self):
        for text in ('今日は資料を読みます。','a pen HTTP utf8','Python3 2rendered one.two-name@scope/path:token'):
            with self.subTest(text=text):
                store=initial_store();before=copy.deepcopy(store._by_reading)
                with patch.object(L,'_english_vocabulary',side_effect=AssertionError('Unused English vocabulary')) as vocab:
                    self.assertEqual(L.learn_english_words(text,store),0)
                vocab.assert_not_called()
                self.assertEqual(store._by_reading,before)

    def test_mixed_input_keeps_known_words_typo_gate_and_registration(self):
        store=initial_store()
        store.add(L.english_reading('Planetarium'),'Planetarium','英語',solid=True)
        text='資料 Planetarium Pplanetarium Python3 rendered RENDERED。'
        self.assertEqual(L.learn_english_words(text,store),1)
        self.assertFalse(store.lookup(L.english_reading('Pplanetarium')))
        self.assertFalse(store.lookup(L.english_reading('Python')))
        self.assertEqual(store.lookup(L.english_reading('rendered'))[0]['surface'],'rendered')
        before=copy.deepcopy(store._by_reading)
        self.assertEqual(L.learn_english_words(text,store),0)
        self.assertEqual(store._by_reading,before)

    def test_vocabulary_error_keeps_the_existing_registration_fallback(self):
        store=initial_store();real=L._english_vocabulary;called=[False]
        def once(*args,**kwargs):
            if not called[0]:
                called[0]=True;raise RuntimeError('Synthetic unavailable vocabulary')
            return real(*args,**kwargs)
        with patch.object(L,'_english_vocabulary',side_effect=once):
            self.assertEqual(L.learn_english_words('日本語 rendered',store),1)
        self.assertTrue(store.lookup(L.english_reading('rendered')))

    def test_unchanged_app_text_still_registers_english_without_japanese_relearning(self):
        import app,janome_import
        a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.store=initial_store();a._last_learned_text='rendered';a._learn_after_id='synthetic'
        a._invalidate_analysis_cache=Mock();a._retain_finished_rows_after_auto_learning=Mock()
        with patch.object(a.store,'save') as save,patch.object(janome_import,'learn_from_text') as japanese:
            a._learn_now('rendered')
            self.assertTrue(a.store.lookup(L.english_reading('rendered')))
            self.assertIsNone(a._learn_after_id)
            japanese.assert_not_called();save.assert_called_once_with()
            a._learn_now('rendered')
            save.assert_called_once_with();japanese.assert_not_called()
        a._invalidate_analysis_cache.assert_called_once_with()
        a._retain_finished_rows_after_auto_learning.assert_called_once_with()


if __name__=='__main__':unittest.main()
