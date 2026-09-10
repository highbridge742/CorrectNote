# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch,Mock
import reading_segments as R
import corrector as C
class PartialEngineTests(unittest.TestCase):
 def test_detection_does_not_generate_correction(self):
  with patch.object(C,'_chunk_is_intact',return_value=False),patch.object(R,'known_reading_prefix',return_value=('がくしゅう','めにょー','名詞',('学習',))),patch('loanword.katakana_for_hiragana',return_value=None),patch('oddness.is_odd_run',return_value=True),patch('loanword.fix_katakana_word',side_effect=AssertionError('候補より先に異様判定')):
   self.assertEqual(R.odd_partial_loanwords(' がくしゅうめにょー',object(),object(),Mock()),[(1,10,'がくしゅう','めにょー','学習')])
 def test_expressive_tail_is_preserved(self):
  with patch.object(C,'_chunk_is_intact',return_value=False),patch.object(R,'known_reading_prefix',return_value=('かくにん','しゅわー','名詞',('確認',))):
   self.assertEqual(R.odd_partial_loanwords('かくにんしゅわー',object(),object(),Mock()),[])
 def test_quoted_example_is_not_rewritten(self):
  with patch.object(C,'_chunk_is_intact',side_effect=AssertionError('引用の内部を探索しない')):
   self.assertEqual(R.odd_partial_loanwords('「がくしゅうめにょー」という誤入力',object(),object(),Mock()),[])
 def test_no_anomaly_means_no_correction(self):
  with patch.object(R,'odd_partial_loanwords',return_value=[]),patch('loanword.fix_katakana_word',side_effect=AssertionError):
   self.assertEqual(C._partial_loanword_fixes('入力',Mock(),'kana',object(),object()),[])
 def test_final_anomaly_rejects_candidate(self):
  with patch.object(R,'odd_partial_loanwords',return_value=[(0,9,'がくしゅう','めにょー','学習')]),patch('loanword.fix_katakana_word',return_value='メニュー'),patch('oddness.is_odd_run',return_value=True):
   self.assertEqual(C._partial_loanword_fixes('がくしゅうめにょー',Mock(),'kana',object(),object()),[])
if __name__=='__main__':unittest.main()
