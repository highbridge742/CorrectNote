import unittest
from unittest.mock import patch
import literal_examples as L

RAW='d).ek-c@y'
DOC='d).et@ss@gjr'

class ExplicitLinkRangesTests(unittest.TestCase):
 def test_complete_lexical_ranges_keep_external_text_and_quotes(self):
  for link in ('C:\\資料'+RAW,'https://example.test/資料'+RAW,'\\\\server\\共有'+RAW):
   source='👩🏽‍💻 前文 '+link+' 後文\t'+RAW
   start=source.index(link)
   with self.subTest(link=link):
    self.assertEqual(L.explicit_link_ranges(source),[(start,start+len(link))])
    self.assertIn((start,start+len(link)),L.protected_ranges(source))
    self.assertFalse(L.overlaps(source.rindex(RAW),len(source),L.explicit_link_ranges(source)))
  self.assertEqual(L.explicit_link_ranges('https://a b'),[(0,9)])
  link='C:\\メモ 資料'+RAW;source='前文 「'+link+'」 後文'
  start=source.index(link)
  self.assertEqual(L.explicit_link_ranges(source),[(start,start+len(link))])

 def test_unrecognized_markers_are_not_new_protection(self):
  for source in ('https://','https:///','C:relative','../'+RAW,'www.example.test',
                 '\\\\?\\C:\\資料'+RAW,'javascript:alert(1)'):
   with self.subTest(source=source):self.assertEqual(L.explicit_link_ranges(source),[])

 def test_common_c_rejects_partial_and_original_ancestor_link_change(self):
  import corrector as C
  source='mojinyuuryoku\t👩🏽‍💻 C:\\資料'+RAW+'\t'+RAW
  first=source.index(RAW)
  for a,b,face in ((first,first+len(RAW),'書類の保存'),(first+2,first+4,'X'),(first+2,first+2,'X')):
   accepted,reason=C._check_replacement(source,(a,b,face,'IT・PC操作'),None,None)
   self.assertIsNone(accepted);self.assertEqual(reason,'original_explicit_link')
  restored='文字入力\t👩🏽‍💻 C:\\資料しょるいの保存\t'+RAW
  a=restored.index('しょるいの保存');ranges=L.explicit_link_ranges
  token=C._CORRECTION_PATH.set((source,))
  try:
   # Force the original-ancestor proof instead of relying on the current view.
   with patch.object(L,'explicit_link_ranges',side_effect=lambda text: [] if text==restored else ranges(text)):
    accepted,reason=C._check_replacement(restored,(a,a+len('しょるいの保存'),'書類の保存','かな入力'),None,None)
   self.assertIsNone(accepted);self.assertEqual(reason,'original_explicit_link')
  finally:C._CORRECTION_PATH.reset(token)


class ExplicitLinkRuntimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from tests_analysis_async import initial
  from last_choice import set_active
  cls.a=initial();cls.addClassCleanup(set_active,None)
 def run_line(self,source,mode='kana'):
  from correction_entry import correct_line
  a=self.a
  return correct_line(source,a.store,input_method=mode,dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
 def test_emoji_path_url_unc_and_quoted_spaces_stay_literal(self):
  for link in ('C:\\資料'+RAW,'https://example.test/資料'+RAW,'\\\\server\\共有'+RAW,'"C:\\メモ 資料'+RAW+'"'):
   source='👩🏽‍💻 '+link
   with self.subTest(source=source):
    row=self.run_line(source)
    self.assertEqual(row['corrected'],source);self.assertEqual(row['original_spans'],[])
    self.assertEqual(row['odd_spans'],[]);self.assertEqual(row['analysis_status'],'complete')
 def test_same_ascii_in_other_fields_keeps_its_own_completion_and_positions(self):
  for mode,raw,face in (('kana',RAW,'書類の保存'),('romaji','shoruiwohozonshimasu','書類を保存します')):
   link='C:\\資料'+raw
   source=raw+'\t👩🏽‍💻 '+link+'\t'+raw
   with self.subTest(mode=mode):
    row=self.run_line(source,mode)
    self.assertEqual(row['corrected'],face+'\t👩🏽‍💻 '+link+'\t'+face)
    self.assertEqual(row['original_spans'],[(0,len(raw)),(source.rindex(raw),len(source))])
    self.assertEqual(row['odd_spans'],[]);self.assertEqual(row['analysis_status'],'complete')
 def test_protected_other_field_does_not_borrow_same_link_text(self):
  source='👩🏽‍💻 C:\\資料'+DOC+'\t'+DOC
  decisions=self.a.decisions;original=decisions.blocks
  def blocked(source,face):return DOC in source or original(source,face)
  with patch.object(decisions,'blocks',side_effect=blocked):row=self.run_line(source)
  self.assertEqual(row['corrected'],source)
  self.assertEqual(row['original_spans'],[])


class ExplicitLinkCacheTests(unittest.TestCase):
 def test_cache_belongs_to_one_request_and_returns_independent_ranges(self):
  import text_links
  from ime_session import resource_scope,retain
  source='💡 C:\\資料'+RAW;finder=text_links.find_links
  with patch.object(text_links,'find_links',wraps=finder) as counted:
   with resource_scope():
    first=L.explicit_link_ranges(source);cache,_=retain(L._ExplicitLinkRanges())
    first.clear()
    with resource_scope():self.assertTrue(L.explicit_link_ranges(source))
    self.assertEqual(counted.call_count,1)
   self.assertEqual(cache.ranges,{})
   with resource_scope():self.assertTrue(L.explicit_link_ranges(source))
   self.assertEqual(counted.call_count,2)
 def test_cancelled_detection_and_cache_hit_do_not_publish(self):
  import text_links
  from ime_session import resource_scope,retain
  from analysis_context import request_scope,SupersededAnalysis
  source='💡 C:\\資料'+RAW;finder=text_links.find_links;stale=[False]
  def cancelled(text):
   result=finder(text);stale[0]=True;return result
  with resource_scope(),request_scope(lambda:stale[0]):
   cache,_=retain(L._ExplicitLinkRanges())
   with patch.object(text_links,'find_links',side_effect=cancelled):
    with self.assertRaises(SupersededAnalysis):L.explicit_link_ranges(source)
   self.assertEqual(cache.ranges,{})
   stale[0]=False;self.assertTrue(L.explicit_link_ranges(source));stale[0]=True
   with self.assertRaises(SupersededAnalysis):L.explicit_link_ranges(source)
  self.assertEqual(cache.ranges,{})
 def test_no_link_does_not_repeat_source_mapping_or_lexical_scan(self):
  import corrector as C,text_links,halfwidth
  from ime_session import resource_scope
  source='文'*3990+'alpha';token=C._CORRECTION_PATH.set((source+'前',))
  try:
   with resource_scope(),patch.object(text_links,'find_links',wraps=text_links.find_links) as finder, \
        patch.object(C,'_candidate_source_ranges',wraps=C._candidate_source_ranges) as ranges, \
        patch.object(halfwidth,'original_ascii_expression',return_value=True):
    for _ in range(20):
     accepted,reason=C._check_replacement(source,(3990,3995,'書類','かな入力'),None,None)
     self.assertIsNone(accepted);self.assertEqual(reason,'original_ascii_expression')
    self.assertEqual(finder.call_count,2)
    self.assertEqual(ranges.call_count,20)
  finally:C._CORRECTION_PATH.reset(token)

if __name__=='__main__':unittest.main()
