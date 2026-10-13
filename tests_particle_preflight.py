import unittest,itertools
from unittest.mock import patch
import morphology as M
from analysis_context import request_scope,SupersededAnalysis

def exhaustive(reading):
 if not reading:return True
 reachable={0}
 for start in range(len(reading)):
  if start not in reachable:continue
  for end in range(start+1,len(reading)+1):
   piece=reading[start:end]
   if any(pos.startswith('助詞,終助詞,') and rd==piece for pos,form,base,rd in M.dictionary_inflections(piece) or ()):
    reachable.add(end)
 return len(reading) in reachable

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class ParticlePreflightTests(unittest.TestCase):
 def setUp(self):
  M.native_final_particle_tail.cache_clear();M.colloquial_particle_normal_form.cache_clear()
 def test_native_all_prefix_senses_match_exhaustive_segmentation(self):
  for length in range(5):
   for pieces in itertools.product(('ね','よ','な','あ','る','し','う','か'),repeat=length):
    text=''.join(pieces)
    self.assertEqual(M.native_final_particle_tail(text),exhaustive(text),text)
 def test_missing_prefix_backend_uses_original_exact_lookup(self):
  cases=('ねえ','ねえよ','るい','しょるい','ね','よな','ねですよ')
  expected=[exhaustive(x) for x in cases]
  with patch.object(M,'dictionary_prefix_paradigms',return_value=None):
   self.assertEqual([M.native_final_particle_tail(x) for x in cases],expected)
 def test_no_final_tail_does_not_tokenize_long_source(self):
  for source in ('しりょう'*768+'にいきます','とってもつょい','しょるいを保存します','しょるい'):
   with patch.object(M,'_tokenize_janome',side_effect=AssertionError('unneeded full parse')):
    self.assertEqual(M.colloquial_particle_normal_form(source),source)
 def test_real_final_particle_still_uses_original_native_attachment(self):
  for source,expected in (('行くょね','行くよね'),('あるょねえ','あるよねえ'),('とってもつょい','とってもつょい'),('すふょ','すふょ'),('行くょ資料','行くょ資料'),('行くょね。しょるい','行くよね。しょるい')):
   self.assertEqual(M.colloquial_particle_normal_form(source),expected,source)
 def test_cancelled_native_prefix_result_is_never_published(self):
  cancelled=[False];native=M.dictionary_prefix_paradigms
  def looked(text):
   result=native(text);cancelled[0]=True;return result
  with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(M,'dictionary_prefix_paradigms',side_effect=looked):
   with self.assertRaises(SupersededAnalysis):M.native_final_particle_tail('ね')
  self.assertEqual(M.native_final_particle_tail.cache_info().currsize,0)
 def test_cancelled_entry_never_queries_native_prefix(self):
  with request_scope(lambda:True),patch.object(M,'dictionary_prefix_paradigms',side_effect=AssertionError('native')):
   with self.assertRaises(SupersededAnalysis):M.native_final_particle_tail('ね')
   with self.assertRaises(SupersededAnalysis):M.colloquial_particle_normal_form('しょるい')
 def test_nonparticle_prefix_senses_never_supply_reachable_boundary(self):
  entries=(('ねえ','名詞,一般,*,*','*','*','ねえ','ねえ'),('ね','助詞,終助詞,*,*','*','*','ね','ね'),('え','感動詞,*,*,*','*','*','え','え'))
  with patch.object(M,'dictionary_prefix_paradigms',side_effect=lambda text:tuple(e for e in entries if text.startswith(e[0]))):
   self.assertFalse(M.native_final_particle_tail('ねえ'));self.assertTrue(M.native_final_particle_tail('ね'))

if __name__=='__main__':unittest.main()
