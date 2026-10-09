# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class FirstIMEFunctionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from tests_analysis_async import initial
  import corrector
  cls.a=initial();cls.tok=staticmethod(corrector.make_tokenizer(cls.a.store))
 def test_function_roles_and_explicit_choices(self):
  from ime_spelling import _reinterprets_function_attachment as conflict
  for source,face in (('はい','肺'),('あれ','荒れ'),('それ','逸れ')):
   self.assertTrue(conflict(source,0,len(source),face),(source,face))
   with patch('last_choice.surface_for_reading',return_value=face):
    self.assertFalse(conflict(source,0,len(source),face))
  for source,face in (('かれ','彼'),('おれ','俺'),('おそらく','恐らく')):
   self.assertFalse(conflict(source,0,len(source),face),(source,face))
 def test_both_first_conversion_routes_respect_original_roles(self):
  from ime_language import JapaneseIME
  from ime_spelling import project_first_words
  from ime_full_field import additional_first_words
  with JapaneseIME() as ime:
   if not ime.available:self.skipTest(ime.error)
  a=self.a
  for source in ('はい','あれ'):
   self.assertIsNone(project_first_words(source,a.store,a.dict_index,a.decisions,self.tok))
   self.assertIsNone(additional_first_words(source,None,a.store,a.dict_index,a.decisions,self.tok))
 def test_shape_with_de_supports_nominal_spelling_before_enclosing(self):
  import app
  a=self.a
  for source,expected in (('視覚で囲って\t','四角で囲って\t'),
                          ('しかくでかこって\t','四角で囲って\t'),
                          ('四角で囲って\t','四角で囲って\t'),
                          ('丸で囲って\t','丸で囲って\t'),
                          ('しかくで確認して\t','しかくで確認して\t')):
   with self.subTest(source=source):
    row=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                         decisions=a.decisions,context_vec=None)
    self.assertEqual(row['corrected'],expected)
    self.assertEqual(row['odd_spans'],[])

 def test_nominal_context_can_support_the_other_sense(self):
  from ime_spelling import _reinterprets_function_attachment as conflict
  from semantic_roles import candidate_nominal_spelling_evidence as evidence
  for tail in ('をけんさする','をしらべます'):
   self.assertTrue(evidence('','肺',tail))
   self.assertFalse(conflict('はい'+tail,0,2,'肺'))
  self.assertIsNone(evidence('','肺',''))
  self.assertIsNone(evidence('','肺','\tをけんさする'))
 def test_explicit_fields_keep_responses_but_convert_real_arguments(self):
  import app
  a=self.a
  cases=[('感動詞\tあ、なんと、はい、なるほど、ええと、もしもし、はて、さてと','感動詞\tあ、なんと、はい、なるほど、ええと、もしもし、はて、さてと'),
         ('指示語\tこれ、それ、あれ、この、その、あの、こう、そう、ああ','指示語\tこれ、それ、あれ、この、その、あの、こう、そう、ああ'),
         ('はい\t','はい\t'),('あれ\t','あれ\t'),
         ('はいをけんさする\t','肺を検査する\t'),('かれがきます\t','彼が来ます\t'),
         ('あれをとります\t','あれを取ります\t')]
  for text,expected in cases:
   r=app.correct_line(text,a.store,dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
   self.assertEqual(r['corrected'],expected,text);self.assertEqual(r['odd_spans'],[],text)

if __name__=='__main__':unittest.main()
