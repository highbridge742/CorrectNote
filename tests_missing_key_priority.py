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
 def test_prediction_values_do_not_leak_into_a_later_search(self):
  from unittest.mock import patch
  import ngram_yomi
  words={'あいう','あえう'};store=Mock();store.all_readings.return_value=words;store.reading_trie.return_value=_ReadingTrie(words)
  def run(preferred):
   def order(prefix,chars):
    return sorted(((ch,10 if ch==preferred else 1,2) for ch in chars),key=lambda x:(-x[1],x[0]))
   with patch.object(ngram_yomi,'order_next',side_effect=order):
    return _find_known_readings_flex_uncached('あう',store,max_edits=1,input_method='kana')
  first=run('い');second=run('え')
  self.assertEqual(first[0][0],'あいう');self.assertEqual(second[0][0],'あえう')
  self.assertEqual(first[0][1],2.8);self.assertEqual(second[0][1],2.8)
  self.assertEqual({r for r,c,e in first},words);self.assertEqual({r for r,c,e in second},words)
 def test_failed_prediction_keeps_all_fallback_branches_and_retries(self):
  from unittest.mock import patch
  import ngram_yomi
  words={'あいう','あえう'};store=Mock();store.all_readings.return_value=words;store.reading_trie.return_value=_ReadingTrie(words)
  calls=[]
  def unavailable(prefix,chars):
   calls.append((prefix,tuple(chars)));raise OSError('prediction unavailable')
  with patch.object(ngram_yomi,'order_next',side_effect=unavailable):
   results=_find_known_readings_flex_uncached('あう',store,max_edits=1,input_method='kana')
  self.assertEqual({r for r,c,e in results},words)
  self.assertTrue(all((c,e)==(3.25,1) for r,c,e in results),results)
  # With one edit, later visits have no insertion budget. Exercise an
  # actual eligible retry with two edits, preserving the same fallback result.
  calls.clear()
  with patch.object(ngram_yomi,'order_next',side_effect=unavailable):
   retried=_find_known_readings_flex_uncached('あう',store,max_edits=2,input_method='kana')
  self.assertEqual(retried,results)
  self.assertGreater(len(calls),len(set(calls)))
 def test_zero_edit_budget_does_not_request_insertion_predictions(self):
  from unittest.mock import patch
  import ngram_yomi
  words={'あい','あう','あいう'};store=Mock();store.all_readings.return_value=words;store.reading_trie.return_value=_ReadingTrie(words)
  with patch.object(ngram_yomi,'order_next',side_effect=AssertionError('insertion budget exhausted')) as predict:
   results=_find_known_readings_flex_uncached('あい',store,max_edits=0,input_method='kana')
  self.assertEqual(results,[('あい',0.0,0)])
  predict.assert_not_called()
class MarkSlipSearchTests(unittest.TestCase):
 def search(self,typed,words,method='kana',edits=1):
  store=Mock();store.all_readings.return_value=set(words);store.reading_trie.return_value=_ReadingTrie(set(words))
  return _find_known_readings_flex_uncached(typed,store,max_edits=edits,input_method=method)
 def test_neighbor_of_mark_is_one_existing_key_error(self):
  for typed,fixed in [('たふせ','たぶ'),('かせ','が')]:
   with self.subTest(typed=typed):
    found=[r for r in self.search(typed,[fixed]) if r[0]==fixed]
    self.assertTrue(found)
    self.assertEqual(found[0][2],1)
    self.assertLessEqual(found[0][1],1.05)
 def test_vertical_and_diagonal_mark_substitutions_are_excluded(self):
  for typed,fixed in [('はへ','ぱ'),('はほ','ば')]:
   with self.subTest(typed=typed):
    self.assertEqual(self.search(typed,[fixed]),[])
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
