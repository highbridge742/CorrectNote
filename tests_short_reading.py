# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock,patch
from reading_segments import known_reading_prefix
class ShortReadingTests(unittest.TestCase):
 def index(self):
  d=Mock();d.is_world_reading.return_value=False;d.surfaces_for_reading.return_value=[];return d
 def test_short_surface_requires_noun_evidence(self):
  with patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*','助詞,特殊,*,*'}):
   self.assertEqual(known_reading_prefix('かなりゅうりょく',self.index(),allow_short=True),('かな','りゅうりょく','名詞',('かな',)))
 def test_short_prefix_is_opt_in(self):
  with patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*'}):
   self.assertIsNone(known_reading_prefix('かなりゅうりょく',self.index()))
 def test_adverb_or_name_does_not_prove_noun(self):
  for positions in ({'副詞,一般,*,*'},{'名詞,固有名詞,人名,名'},None):
   with patch('morphology.dictionary_base_pos',return_value=positions):
    self.assertIsNone(known_reading_prefix('かなりゅうりょく',self.index(),allow_short=True))
 def test_mora_boundary_is_preserved(self):
  with patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*'}):
   self.assertIsNone(known_reading_prefix('かなゅうりょく',self.index(),allow_short=True))
if __name__=='__main__':unittest.main()
