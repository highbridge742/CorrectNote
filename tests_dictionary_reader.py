# -*- coding: utf-8 -*-
"""Public dictionary reading and cooperative cancellation contracts."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import janome_import as J

class DictionaryReaderTests(unittest.TestCase):
    def test_reading_is_distinct_from_pronunciation_and_layout_fallback(self):
        pairs=[(('名詞,一般,*,*','*','*','学校','ガッコウ','ガッコー'),'ガッコウ'),
               (('名詞,一般,*,*','*','*','コーヒー','コーヒー','コーヒー'),'コーヒー'),
               (('東京',('トウキョウ','トーキョー')),'トウキョウ'),
               (('カ',('キ',),'ク'),'キ'),(('カ',),'カ'),
               (('カ','*'),'カ'),((None,12,['*','漢字']),'')]
        for entry,wanted in pairs:
            with self.subTest(entry=entry):self.assertEqual(J._parse_extra(entry),wanted)

    def test_exact_character_range_including_unicode_boundaries(self):
        for code in range(0x10000):
            char=chr(code);wanted=(0x30a1<=code<=0x30f6 or char=='ー')
            self.assertEqual(J._is_katakana_word(char),wanted,hex(code))
        for text in ('','カ\n','カA','カ😀','カ\u0301','ｶ','ヷ','ヽ'):
            self.assertFalse(J._is_katakana_word(text),repr(text))
        self.assertTrue(J._is_katakana_word('ヴヵヶー'))

    def test_nested_and_flat_layouts_keep_reverse_traversal_reading(self):
        import random
        rng=random.Random(981)
        atoms=['ガッコウ','ガッコー','カ','キ','*','漢字','名詞,一般,*,*',None,12,'', 'カ\n']
        def entry(depth):
            if depth==0 or rng.random()<.5:return rng.choice(atoms)
            values=[entry(depth-1) for _ in range(rng.randrange(7))]
            return tuple(values) if rng.random()<.5 else values
        for _ in range(1000):
            value=entry(3)
            got=[s for s in J._extract_strings(value) if s and s!='*' and all('ァ'<=c<='ヶ' or c=='ー' for c in s)]
            expected=got[1] if len(got)>=2 else got[0] if got else ''
            self.assertEqual(J._parse_extra(value),expected,repr(value))

    def test_katakana_translation_keeps_exact_codepoints_and_nonletters(self):
        text=''.join(chr(code) for code in range(0x10000))+'😀𠮷'
        expected=''.join(chr(ord(ch)-0x60) if 'ァ'<=ch<='ヶ' else ch for ch in text)
        self.assertEqual(J.katakana_to_hiragana(text),expected)
        self.assertEqual(J.katakana_to_hiragana(''),'')
        self.assertEqual(J.katakana_to_hiragana('ヴヵヶヷヺー・ヽヾｶカ\u3099'),'ゔゕゖヷヺー・ヽヾｶか\u3099')

    def test_compact_known_and_fallback_shapes_keep_surface_pos_and_cost(self):
        cases=[(('資料',1,2,-400),('資料','',-400)),
               (['資料',True,2,False],('資料','',False)),
               (('資料',1,2,1.5),('資料','',2)),
               ((('名詞,一般,*,*','資料'),7),('資料','名詞,一般,*,*',7)),
               ((1,2,3),('','',3)),(None,('','',None))]
        for value,expected in cases:
            self.assertEqual(J._parse_compact(value),expected,repr(value))

    def test_superseded_scan_discards_partial_cached_index_and_can_retry(self):
        import contextual_repair as R
        from analysis_context import request_scope,SupersededAnalysis
        compact={i:('資料'+str(i)+'字',1,1,1000) for i in range(1600)}
        extra={i:('名詞,一般,*,*','*','*','資料','シリョウ','シリョー') for i in compact}
        def module(name):
            if name.endswith('0'):
                return SimpleNamespace(DATA=extra if 'extra' in name else compact)
            return SimpleNamespace(DATA={})
        calls=[0]
        def newer():
            calls[0]+=1;return calls[0]>=2
        R._native_written_nominal_readings.cache_clear()
        try:
            with patch.object(J,'HAS_JANOME',True),patch.object(J.importlib,'import_module',side_effect=module):
                with request_scope(newer),self.assertRaises(SupersededAnalysis):
                    R._native_written_nominal_readings()
                self.assertEqual(R._native_written_nominal_readings.cache_info().currsize,0)
                complete=R._native_written_nominal_readings()
                self.assertEqual(complete,{'しりょう':tuple(sorted(v[0] for v in compact.values()))})
        finally:R._native_written_nominal_readings.cache_clear()

if __name__=='__main__':unittest.main()
