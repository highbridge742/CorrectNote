import unittest
from unittest.mock import patch
import corrector as C

class AncestorLinkInsertTests(unittest.TestCase):
 def test_scheme_removed_internal_insertion_keeps_original_protection(self):
  current='資料abc';ancestor='C:\\資料abc';point=3
  token=C._CORRECTION_PATH.set((ancestor,))
  try:
   # The existing next gate is only a sentinel: it must not be reached here.
   with patch('halfwidth.original_ascii_expression',return_value=True):
    result=C._check_replacement(current,(point,point,'X','かな入力'),None,None)
   self.assertEqual(result,(None,'original_explicit_link'))
  finally:C._CORRECTION_PATH.reset(token)

 def test_reused_ascii_guard_keeps_old_nonempty_views_only(self):
  import difflib
  source='資料abc\tはし';ancestor='C:\\'+source;start=source.rindex('はし');seen=[]
  token=C._CORRECTION_PATH.set((ancestor,))
  try:
   def ascii_guard(text,a,b):
    seen.append((text,a,b));return text==ancestor
   with patch('halfwidth.original_ascii_expression',side_effect=ascii_guard), \
        patch.object(C,'_candidate_source_ranges',wraps=C._candidate_source_ranges) as ranges, \
        patch.object(difflib,'SequenceMatcher',wraps=difflib.SequenceMatcher) as matcher:
    result=C._check_replacement(source,(start,start+2,'橋','かな入力'),None,None)
   self.assertEqual(result,(None,'original_ascii_expression'))
   self.assertEqual(seen,[(source,start,start+2),(ancestor,start+3,start+5)])
   self.assertEqual(ranges.call_count,1);self.assertEqual(matcher.call_count,1)
  finally:C._CORRECTION_PATH.reset(token)
  current='??\\資料abc';ancestor='C:\\資料abc';seen=[]
  token=C._CORRECTION_PATH.set((ancestor,))
  class NextGate(Exception):pass
  try:
   with patch('halfwidth.original_ascii_expression',side_effect=lambda *args:seen.append(args) or False), \
        patch('romaji_source.candidate_evidence',side_effect=NextGate):
    with self.assertRaises(NextGate):C._check_replacement(current,(0,0,'X','かな入力'),None,None)
   self.assertEqual(seen,[(current,0,0)])
  finally:C._CORRECTION_PATH.reset(token)

 def test_original_link_endpoints_continue_to_existing_gate(self):
  current='??\\資料abc';ancestor='C:\\資料abc'
  token=C._CORRECTION_PATH.set((ancestor,))
  try:
   with patch('halfwidth.original_ascii_expression',return_value=True):
    for point in (0,len(current)):
     self.assertEqual(C._check_replacement(current,(point,point,'X','かな入力'),None,None),
                      (None,'original_ascii_expression'))
    self.assertEqual(C._check_replacement(current,(5,5,'X','かな入力'),None,None),
                     (None,'original_explicit_link'))
  finally:C._CORRECTION_PATH.reset(token)

 def test_two_repeated_links_keep_unicode_original_coordinates(self):
  ancestor='👩🏽‍💻 C:\\資料abc\tD:\\資料abc'
  current=ancestor.replace('C:','cc').replace('D:','dd')
  token=C._CORRECTION_PATH.set((ancestor,))
  try:
   with patch('halfwidth.original_ascii_expression',return_value=True):
    for point in (current.index('abc')+1,current.rindex('abc')+1):
     ranges=list(C._candidate_source_ranges(current,point,point,allow_empty=True))
     self.assertIn((ancestor,point,point),ranges)
     self.assertEqual(C._check_replacement(current,(point,point,'X','かな入力'),None,None),
                      (None,'original_explicit_link'))
  finally:C._CORRECTION_PATH.reset(token)

 def test_default_mapping_and_ambiguous_deletion_boundary_do_not_change(self):
  ancestor='C:\\資料abc';current='資料abc'
  token=C._CORRECTION_PATH.set((current,ancestor))
  try:
   self.assertEqual(list(C._candidate_source_ranges(current,3,3)),[(current,3,3)])
   self.assertEqual(list(C._candidate_source_ranges(current,3,3,allow_empty=True)),
                    [(current,3,3),(ancestor,6,6)])
   # The deleted scheme's left and right original boundaries both map here.
   self.assertEqual(list(C._candidate_source_ranges(current,0,0,allow_empty=True)),[(current,0,0)])
   old=list(C._candidate_source_ranges(current,2,4))
   self.assertEqual(old,list(C._candidate_source_ranges(current,2,4,allow_empty=True)))
  finally:C._CORRECTION_PATH.reset(token)
  token=C._CORRECTION_PATH.set(('C:\\xyz',))
  try:
   self.assertEqual(list(C._candidate_source_ranges(current,3,3,allow_empty=True)),[(current,3,3)])
  finally:C._CORRECTION_PATH.reset(token)

if __name__=='__main__':unittest.main()
