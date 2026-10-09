# -*- coding: utf-8 -*-
"""Missing-Shift trials must have a full-size source key to replace."""
import unittest
from unittest.mock import Mock,patch
import ime_missing_shift as S

class ShiftPreflightTests(unittest.TestCase):
    def test_no_replaceable_key_needs_no_anomaly_or_native_query(self):
        # Includes already-small letters and を: this path cannot turn any
        # of them into a smaller kana, regardless of the language service.
        for source in ('ねこをみます','ほん','すしです','ちょっとまちます',
                       'りんご','みます','る','ぁぃぅぇぉっゃゅょ','ー','を'):
            with self.subTest(source=source),patch('pos_grammar.odd_kana_spans') as odd,patch('ime_language.JapaneseIME') as ime:
                ime.return_value.__enter__.return_value.available=False
                self.assertIsNone(S.complete_field(source,source,Mock(),Mock(),Mock(),Mock()))
                odd.assert_not_called();ime.assert_not_called()

    def test_every_full_size_shift_position_keeps_the_existing_entry(self):
        # These are physical key pairs, not a list of words to fix.
        for source in ('あ','い','う','え','お','つ','や','ゆ','よ'):
            with self.subTest(source=source),patch('pos_grammar.odd_kana_spans',return_value=[]) as odd,patch('ime_language.JapaneseIME') as ime:
                ime.return_value.__enter__.return_value.available=False
                self.assertIsNone(S.complete_field(source,source,Mock(),Mock(),Mock(),Mock()))
                odd.assert_called_once();ime.assert_called_once()

if __name__=='__main__':unittest.main()
