# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class ReopenedNominalScopeTests(unittest.TestCase):
 def setUp(self):
  from tests_analysis_async import initial
  from last_choice import set_active
  self.a=initial();self.addCleanup(set_active,None)
 def project(self,transform):
  import reading_segments as R,ime_spelling as I,corrector as C
  original=R.native_reopened_verb_case_frames;gate=C._check_replacement;calls=[]
  def frames(text):
   rows=original(text)
   return tuple(transform(row) for row in rows) if text=='学生がこうえんであるきます' else rows
  def check(*a,**k):calls.append((a[0],a[1]));return gate(*a,**k)
  with patch.object(R,'native_reopened_verb_case_frames',side_effect=frames),patch.object(C,'_check_replacement',side_effect=check):
   result=I.project_first_words('学生がこうえんであるきます',self.a.store,self.a.dict_index,self.a.decisions,C.make_tokenizer(self.a.store))
  return result,calls
 def test_ambiguous_original_faces_do_not_replace_existing_first(self):
  result,calls=self.project(lambda r:r[:5]+(('公園','講演'),))
  self.assertFalse(any(p[2]=='公園' for _,p in calls),calls)
 def test_different_reading_is_not_a_nominal_answer(self):
  result,calls=self.project(lambda r:r[:5]+(('道路',),))
  self.assertFalse(any(p[2] in ('道路','公園') for _,p in calls),calls)
 def test_other_original_range_does_not_donate_its_nominal(self):
  result,calls=self.project(lambda r:(r[0],r[1],r[2]+1,r[3],r[4],r[5]))
  self.assertFalse(any(p[2]=='公園' for _,p in calls),calls)
 def test_unique_native_face_still_needs_original_final_gate(self):
  from correction_entry import correct_line
  import corrector as C
  source='gakuseigakouendearukimasu';original=C._check_replacement;denied=[]
  def gate(text,proposal,*a,**k):
   if text==source and '公園' in proposal[2]:denied.append(proposal);return None,'independent_original_rejection'
   return original(text,proposal,*a,**k)
  with patch.object(C,'_check_replacement',side_effect=gate):
   r=correct_line(source,self.a.store,input_method='romaji',dict_index=self.a.dict_index,decisions=self.a.decisions,context_vec=None)
  self.assertTrue(denied);self.assertNotIn('公園',r['corrected'])
  self.assertEqual(r['analysis_status'],'complete')

if __name__=='__main__':unittest.main()
