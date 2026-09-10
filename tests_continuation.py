# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import ngram_yomi as N
class ContinuationTests(unittest.TestCase):
 def test_conditional_probability_not_raw_frequency(self):
  with patch.object(N,'TRIGRAMS',{'あいう':90,'あいえ':10,'かきく':900,'かきけ':9100}):
   N._all_next_distributions.cache_clear()
   self.assertLess(N.continuation_cost('あいう'),N.continuation_cost('かきく'))
  N._all_next_distributions.cache_clear()
 def test_unknown_context_is_no_evidence(self):
  with patch.object(N,'TRIGRAMS',{}):
   N._all_next_distributions.cache_clear()
   self.assertIsNone(N.continuation_cost('あいう'))
  N._all_next_distributions.cache_clear()
 def test_equal_key_cost_uses_prediction_without_changing_cost(self):
  from unittest.mock import Mock
  import vocabulary as V
  words={'あいう','あいえ'};store=Mock()
  store.all_readings.return_value=words;store.reading_trie.return_value=V._ReadingTrie(words)
  def nearby(ch,**kwargs):return [('う',1.0),('え',1.0)] if ch=='お' else [(ch,0.0)]
  with patch.object(V,'nearby_candidates',side_effect=nearby),patch.object(N,'continuation_cost',side_effect=lambda r:0.1 if r=='あいう' else 5.0):
   rows=V._find_known_readings_flex_uncached('あいお',store,max_edits=1,input_method='kana')
  self.assertEqual(rows,[('あいう',1.0,1),('あいえ',1.0,1)])
 def test_field_offsets_and_no_answer_lookup(self):
  import corrector as C
  # 子区間の判定を既存の関数へ渡したことを観測する。
  original=C._particle_boundary_fixes
  seen=[]
  def local(text,*args):
   seen.append(text);return [(0,1,'X','かな入力')]
  with patch.object(C,'_particle_boundary_fixes',side_effect=local):
   result=original('ああ　　いい',lambda s:[], 'kana',object(),object())
  self.assertEqual(seen,['ああ','いい'])
  self.assertEqual(result,[(0,1,'X','かな入力'),(4,5,'X','かな入力')])
if __name__=='__main__':unittest.main()
