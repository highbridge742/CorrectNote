from pathlib import Path
import unittest
from unittest.mock import patch
import reading_segments as R
from analysis_context import request_scope,SupersededAnalysis

# Captured pre-change rule for differential checks against real native tables.
def reference(surface):
    """Exact native count, or numeric spelling with an attested counter.

    48-ALO: digit quantities keep their written value. Their unit supplies
    meaning without inventing a Japanese pronunciation for large numbers.
    """
    found=R._counted_nominal_index().get(surface,())
    if found:return found
    match=R._numeric_counted_spelling_pattern().fullmatch(surface)
    if match:
        number,unit,ordinal=match.groups()
        if ordinal and any(c in '.．' for c in number):return ()
    else:
        import re
        match=re.fullmatch(r'([〇零一二三四五六七八九十百千万億兆]+)([個枚冊本台人])(目?)',surface)
        if not match:return ()
        number,unit,ordinal=match.groups()
        if not R._native_kanji_number_spelling(number):return ()
    # Reuse the native paradigm's evidence for this suffix and ordinal.
    return R._counted_nominal_index().get('二'+unit+ordinal,())
kana=lambda value:bool(value) and all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in value)

class CountedReadingDemandTests(unittest.TestCase):
    def test_all_actual_readings_and_written_variants_equal_original(self):
        index=R._counted_nominal_index()
        forms=set(index)|set(R.native_counter_readings())|set(R.native_ordinal_readings())
        forms.update(('ゆびんきょくにいきます','ほぞんします','しょるい','とお','ょ','ー','いっぽん','ふたり','さんにんめ','はんこ','にこはん','', '二個','２個','2個','1,234.5個','１，２３４個','一億二千万個','1.5個目','1,23個','二個め','二個目','二個半'))
        for surface in sorted(forms):
            self.assertEqual(R.native_counted_nominal_evidence(surface),reference(surface),surface)
        Path('counted87_equivalence.txt').write_text(str(len(forms))+' complete keys and controls equal\n',encoding='utf8')
    def test_written_variants_cannot_overlap_the_kana_reading_column(self):
        count=0
        for table in (R.native_counter_readings(),R.native_ordinal_readings()):
            for faces in table.values():
                for face in faces:
                    for written in R._native_counter_spelling_variants(face):
                        self.assertFalse(kana(written),written);count+=1
        self.assertGreater(count,0)
    def test_kana_queries_do_not_build_digit_alias_index(self):
        with patch.object(R,'_counted_nominal_index',side_effect=AssertionError('irrelevant digit aliases')):
            self.assertEqual(R.native_counted_nominal_evidence('ふたり'),(('人',False),))
            self.assertEqual(R.native_counted_nominal_evidence('ふたりめ'),(('人',True),))
            self.assertEqual(R.native_counted_nominal_evidence('ゆびんきょくにいきます'),())
    def test_every_sense_is_retained_and_missing_tables_have_no_proof(self):
        with patch.object(R,'native_counter_readings',return_value={'あ':('二枚','二個','二人','二個')}),patch.object(R,'native_ordinal_readings',return_value={'あ':('二人目','二冊目')}):
            self.assertEqual(R.native_counted_nominal_evidence('あ'),tuple(sorted({('枚',False),('個',False),('人',False),('人',True),('冊',True)})))
        with patch.object(R,'native_counter_readings',return_value={}),patch.object(R,'native_ordinal_readings',return_value={}):
            self.assertEqual(R.native_counted_nominal_evidence('ふたり'),())
    def test_cancelled_entry_and_final_query_never_publish(self):
        with request_scope(lambda:True),patch.object(R,'native_counter_readings',side_effect=AssertionError('stale load')):
            with self.assertRaises(SupersededAnalysis):R.native_counted_nominal_evidence('ふたり')
        cancelled=[False]
        class Canceled(dict):
            def get(self,key,default=None):
                cancelled[0]=True
                return super().get(key,default)
        for table in ({'ふたり':('二人',)},{}):
            cancelled[0]=False
            with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(R,'native_counter_readings',return_value=Canceled(table)),patch.object(R,'native_ordinal_readings',return_value={}):
                with self.assertRaises(SupersededAnalysis):R.native_counted_nominal_evidence('ふたり')
    def test_ascii_alone_is_absent_from_every_native_column_and_numeric_form(self):
        for surface in R._counted_nominal_index():
            self.assertFalse(surface.isascii(),surface)
        controls=('abc','yubinkyokuniikimasu','shoruiwohozonshimasu','0','99','1,000','-1','123.45','[]','a b','\t','\x00')
        for surface in controls:
            self.assertEqual(reference(surface),(),surface)
        with patch.object(R,'_counted_nominal_index',side_effect=AssertionError('irrelevant numeric aliases')),patch.object(R,'native_counter_readings',side_effect=AssertionError('no Japanese unit')):
            for surface in controls:self.assertEqual(R.native_counted_nominal_evidence(surface),(),surface)
            with request_scope(lambda:True):
                with self.assertRaises(SupersededAnalysis):R.native_counted_nominal_evidence('abc')
    def test_cancellation_from_native_backend_propagates(self):
        with patch.object(R,'native_counter_readings',side_effect=SupersededAnalysis()):
            with self.assertRaises(SupersededAnalysis):R.native_counted_nominal_evidence('ふたり')

if __name__=='__main__':unittest.main()
