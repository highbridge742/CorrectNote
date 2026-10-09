import unittest
from unittest.mock import patch
from text_positions import map_column,selection_correction_pair

class EqualTextPositionTests(unittest.TestCase):
 def test_large_unchanged_text_needs_no_diff_for_cursor_or_selection(self):
  text='資料😀ABC0123'*5000
  with patch('difflib.SequenceMatcher',side_effect=AssertionError('Unchanged text does not need diff')):
   for edge in (None,'start','end'):
    for column in (-1,0,1,17,len(text)-1,len(text),len(text)+1):
     self.assertEqual(map_column(text,text,column,edge=edge),min(len(text),max(0,column)))
   for source in (False,True):
    self.assertEqual(selection_correction_pair(text,text,5,23,source),(text[5:23],text[5:23],5,23))
    self.assertIsNone(selection_correction_pair(text,text,5,5,source))
    self.assertIsNone(selection_correction_pair(text,text,-1,5,source))
 def test_changed_text_keeps_different_cursor_and_selection_boundaries(self):
  self.assertEqual(map_column('AB','AxyzB',1),'AxyzB'.index('B'))
  self.assertEqual(map_column('AB','AxyzB',1,edge='start'),4)
  self.assertEqual(map_column('AB','AxyzB',1,edge='end'),1)
  self.assertEqual(selection_correction_pair('甲乙丙','甲AB丙',1,2),('乙','AB',1,3))
  self.assertEqual(map_column('','',2),0)

if __name__=='__main__':unittest.main()
