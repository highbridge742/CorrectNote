# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock
from kana_layout import additional_kana_keys,kana_repair_cost
from vocabulary import _ReadingTrie,_find_known_readings_flex_uncached
class MissingKeyPriorityTests(unittest.TestCase):
 def test_key_counts(self):
  for typed,fixed,n in [('か','が',1),('かせ','が',0),('は','ぱ',1),('カ','ガ',1),('みも','も',0),('あい','いあ',0)]:
   self.assertEqual(additional_kana_keys(typed,fixed),n)
 def test_known_whole_word_is_protected_before_window_split(self):
  import corrector as C
  with __import__('unittest.mock',fromlist=['patch']).patch('seed_japanese.is_unit',return_value=True):
   self.assertTrue(C._chunk_is_intact('とびうお',None,context_only=True))
 def test_added_key_is_expensive(self):
  self.assertEqual(kana_repair_cost('か','が',0.5),2.8)
  self.assertEqual(kana_repair_cost('みも','も',0.5),0.5)
  self.assertEqual(kana_repair_cost('か','が',0.5,'romaji'),0.5)
 def test_beam_keeps_insertion_as_fallback(self):
  store=Mock();store.all_readings.return_value={'あいう'};store.reading_trie.return_value=_ReadingTrie({'あいう'})
  results=_find_known_readings_flex_uncached('あう',store,max_edits=1,input_method='kana')
  self.assertTrue(results)
  self.assertEqual(results[0][0],'あいう');self.assertGreaterEqual(results[0][1],2.8)
 def test_transposition_precedes_insertion(self):
  store=Mock();store.all_readings.return_value={'うあ','あいう'};store.reading_trie.return_value=_ReadingTrie({'うあ','あいう'})
  results=_find_known_readings_flex_uncached('あう',store,max_edits=1,input_method='kana')
  self.assertEqual([r[0] for r in results],['うあ','あいう'])
class MarkSlipSearchTests(unittest.TestCase):
 def search(self,typed,words,method='kana',edits=1):
  store=Mock();store.all_readings.return_value=set(words);store.reading_trie.return_value=_ReadingTrie(set(words))
  return _find_known_readings_flex_uncached(typed,store,max_edits=edits,input_method=method)
 def test_neighbor_of_mark_is_one_existing_key_error(self):
  for typed,fixed in [('たふせ','たぶ'),('かせ','が'),('はへ','ぱ'),('はほ','ば')]:
   with self.subTest(typed=typed):
    found=[r for r in self.search(typed,[fixed]) if r[0]==fixed]
    self.assertTrue(found)
    self.assertEqual(found[0][2],1)
    self.assertLessEqual(found[0][1],1.05)
 def test_long_vowel_keeps_physical_position_after_composition(self):
  found=self.search('たふせー',['たぶー'])
  self.assertTrue(found)
  self.assertEqual(found[0][0],'たぶー')
  self.assertEqual(found[0][2],1)
  self.assertEqual(self.search('たふせー',['たーぶ'],edits=2),[])
 def test_disabled_setting_applies_to_core_and_trie_and_cache(self):
  import os,corrector as C,vocabulary as V
  from unittest.mock import patch
  store=Mock();store._by_reading={'たぶ':{}};store.all_readings.return_value={'たぶ'};store.reading_trie.return_value=_ReadingTrie({'たぶ'})
  V._FLEX_CACHE.clear()
  with patch.dict(os.environ,{'CN_MARK_SLIP':'1'}):
   self.assertTrue(V.find_known_readings_flex('たふせ',store,max_edits=1,input_method='kana'))
  with patch.dict(os.environ,{'CN_MARK_SLIP':'0'}):
   self.assertEqual(V.find_known_readings_flex('たふせ',store,max_edits=1,input_method='kana'),[])
   self.assertEqual(C._mark_slip_repairs('さへいりょう'),())
  V._FLEX_CACHE.clear()
 def test_distant_key_is_not_a_mark(self):
  from kana_layout import mark_slip_candidates
  self.assertEqual(mark_slip_candidates('か','な'),())
  self.assertEqual(self.search('かな',['が']),[])
 def test_already_voiced_and_two_stroke_pressed_key_are_not_one_error(self):
  from kana_layout import mark_slip_candidates
  self.assertEqual(mark_slip_candidates('が','せ'),())
  self.assertEqual(mark_slip_candidates('か','べ'),())
 def test_explicit_romaji_does_not_take_kana_mark_route(self):
  self.assertEqual(self.search('たふせ',['たぶ'],'romaji'),[])
 def test_zero_edit_budget_and_unknown_word(self):
  self.assertEqual(self.search('たふせ',['たぶ'],edits=0),[])
  self.assertEqual(self.search('たふせ',['ねこ']),[])
 def test_intended_dakuten_is_not_classified_as_neighbor_error(self):
  from kana_layout import mark_slip_candidates
  self.assertEqual(mark_slip_candidates('か','゛'),())

if __name__=='__main__':unittest.main()
