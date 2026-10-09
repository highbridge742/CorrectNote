# -*- coding: utf-8 -*-
"""Lines without an acronym run do not prepare unused English tables."""
import unittest
from unittest.mock import patch
import loanword as L
from vocabulary import VocabularyStore


class AcronymLazyTablesTests(unittest.TestCase):
    def test_no_acronym_run_avoids_both_tables(self):
        store=VocabularyStore();revision=store.revision()
        for text in ('','資料を保存しました。','かなとカタカナ','abcde','ＡＢＣ','AB は CD',
                     'A1B2C','AbC','AB\tCD','処理がじゃのになっていないだろうか。'):
            with self.subTest(text=text),patch.object(L,'_english_targets') as targets,patch.object(L,'_english_seed_all') as all_words:
                self.assertEqual(L.find_miskeyed_acronym(text,store),[])
                targets.assert_not_called();all_words.assert_not_called()
        self.assertEqual(store.revision(),revision)

    def test_deferred_tables_still_prepare_for_a_later_real_run(self):
        store=VocabularyStore()
        with patch.object(L,'_english_targets',wraps=L._english_targets) as targets,patch.object(L,'_english_seed_all',wraps=L._english_seed_all) as all_words:
            self.assertEqual(L.find_miskeyed_acronym('資料を保存しました。',store),[])
            self.assertEqual(L.find_miskeyed_acronym('YRLは',store),[(0,3,'URL')])
            self.assertEqual(targets.call_count,1)
            self.assertEqual(all_words.call_count,1)
        for text,expected in (('IMEは',[]),('ABC1',[]),('1YRL',[]),('xYRL',[]),
                              ('YRLx',[]),('YRLは YRLへ',[(0,3,'URL'),(5,8,'URL')])):
            with self.subTest(text=text):self.assertEqual(L.find_miskeyed_acronym(text,store),expected)

    def test_matching_run_keeps_empty_vocabulary_contract(self):
        with patch.object(L,'_english_targets',return_value={}) as targets,patch.object(L,'_english_seed_all') as all_words:
            self.assertEqual(L.find_miskeyed_acronym('YRLは',VocabularyStore()),[])
            targets.assert_called_once();all_words.assert_not_called()


if __name__=='__main__':unittest.main()
