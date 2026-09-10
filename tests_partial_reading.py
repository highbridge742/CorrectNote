# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock,patch
from reading_segments import known_reading_prefix
class PartialReadingTests(unittest.TestCase):
 def index(self):
  idx=Mock();idx.is_world_reading.return_value=False
  idx.surfaces_for_reading.side_effect=lambda r,**kw:['学習'] if r=='がくしゅう' else []
  return idx
 def test_longest_supported_prefix_and_remaining_span(self):
  with patch('morphology.dictionary_base_pos',return_value={'名詞,サ変接続,*,*'}):
   self.assertEqual(known_reading_prefix('がくしゅうめにょー',self.index()),('がくしゅう','めにょー','名詞',('学習',)))
 def test_complete_reading_is_not_cut(self):
  idx=self.index();idx.is_world_reading.return_value=True
  self.assertIsNone(known_reading_prefix('がくしゅうめにょー',idx))
  idx.surfaces_for_reading.assert_not_called()
 def test_no_dictionary_pos_or_proper_name_is_no_evidence(self):
  for pos in (None,{'名詞,固有名詞,人名,*'},{'助詞,格助詞,*,*'}):
   with patch('morphology.dictionary_base_pos',return_value=pos):
    self.assertIsNone(known_reading_prefix('がくしゅうめにょー',self.index()))
 def test_small_kana_cannot_start_remaining_span(self):
  with patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*'}):
   self.assertIsNone(known_reading_prefix('がくしゅうゃー',self.index()))
if __name__=='__main__':unittest.main()
