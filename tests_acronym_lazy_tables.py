# -*- coding: utf-8 -*-
"""Lines without an acronym run do not prepare unused English tables."""
import unittest
from unittest.mock import patch
import loanword as L
from vocabulary import VocabularyStore


class AcronymLazyTablesTests(unittest.TestCase):
    def test_no_acronym_run_avoids_both_tables(self):
        store=VocabularyStore();revision=store.revision()
        for text in ('','資料を保存しました。','かなとカタカナ','abcde','ＡＢＣ','A は B',   # 2字の大文字（AB）は 2026-10-19 から略語の並びとして見る
                     'A1B2C','AbC','A\tB','処理がじゃのになっていないだろうか。'):
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


    def test_two_letter_runs_and_general_table(self):
        # 同梱の略語の表（2〜5字）と2字の扱い（2026-10-19）: OC→PC・UD→ID・YSB→USB。国・地域の符号（AU・US）、
        # 英語の短い語（IS・ON・AM）、知っている略語（CV・AI）は触らない。直し先が2つ以上（GOS→GPS/GIS）は触らない
        store=VocabularyStore()
        for text,expected in (('OCを買う',[(0,2,'PC')]),('UDを入れる',[(0,2,'ID')]),('YSBメモリ',[(0,3,'USB')]),
                              ('HTNLを書く',[(0,4,'HTML')]),('AUを使う',[]),('USに行く',[]),('ISを見る',[]),
                              ('ONにする',[]),('CVに入れる',[]),('AIを使う',[]),('GOSで測る',[])):
            with self.subTest(text=text):self.assertEqual(L.find_miskeyed_acronym(text,store),expected)


if __name__=='__main__':unittest.main()
