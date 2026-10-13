import unittest
from unittest.mock import patch
import corrector as C,romaji_repair as R,romaji_source as K
from correction_entry import correct_line
from tests_analysis_async import initial
from last_choice import set_active
from analysis_context import SupersededAnalysis

RAW='shiryouwohozinshimasu';FACE='資料を保存します'

class RomajiDetachedSymbolTests(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.addCleanup(set_active,None)
    def run_line(self,source,mode='romaji'):
        a=self.a
        return correct_line(source,a.store,input_method=mode,decisions=a.decisions,
                            dict_index=a.dict_index,context_vec=None)
    def test_existing_detached_separator_cannot_discard_other_original_syntax(self):
        for source in ('💡 '+RAW,'💡 👩🏽‍💻 '+RAW+' ©',RAW+' 💡','前欄\t💡 '+RAW+'\t次欄'):
            a=source.index(RAW);self.assertTrue(R._whole_field(source,a,a+len(RAW)),source)
        for source in ('💡'+RAW,RAW+'©','💡 fn( '+RAW+' )','fn( 💡 '+RAW+' )',
                       'note 💡 '+RAW,'💡 '+RAW+' = 1','💡 C:\\Notes\\'+RAW+'.txt',
                       '💡 https://example.test/'+RAW,'💡 '+RAW+' + other'):
            a=source.index(RAW);self.assertFalse(R._whole_field(source,a,a+len(RAW)),source)
    def test_unicode_symbols_keep_only_original_ascii_replacement_ranges(self):
        prefix='💡 👩🏽‍💻 ';source=prefix+RAW+' ©'
        row=self.run_line(source)
        self.assertEqual(row['corrected'],prefix+FACE+' ©')
        self.assertEqual(row['original_spans'],[(len(prefix),len(prefix)+len(RAW))])
        self.assertEqual(row['spans'],[(len(prefix),len(prefix)+len(FACE))])
        self.assertEqual(row['odd_spans'],[])
        self.assertEqual(row['diagnosis']['language_state'],'anomaly_repaired')
    def test_shortened_prior_field_preserves_physical_and_final_original_checks(self):
        prefix='mojinyuuryoku\t👩🏽‍💻 ';source=prefix+RAW+' ©';key=K.checked_source_keys;gate=C._check_replacement;key_calls=[];final=[]
        def keys(typed,reading,**kwargs):
            value=key(typed,reading,**kwargs)
            if typed==RAW:key_calls.append((typed,reading,kwargs,value.proved))
            return value
        def checked(line,edit,*args,**kwargs):
            value=gate(line,edit,*args,**kwargs)
            if edit[2]==FACE:final.append((line,edit))
            return value
        with patch.object(K,'checked_source_keys',side_effect=keys),patch.object(C,'_check_replacement',side_effect=checked):
            row=self.run_line(source)
        self.assertEqual(row['corrected'],'文字入力\t👩🏽‍💻 '+FACE+' ©')
        a=len(prefix);b=a+len(RAW)
        self.assertTrue(any(kw.get('source')==source and (kw.get('start'),kw.get('end'))==(a,b) and proved for typed,reading,kw,proved in key_calls))
        self.assertTrue(any(line==source and edit[:3]==(a,b,FACE) for line,edit in final))
        self.assertIn([a,b],row['diagnosis']['replaced_odd_spans'])
    def test_partial_protection_is_not_bypassed_by_detached_symbol(self):
        source='💡 '+RAW;self.a.decisions.protect('hozin')
        with patch.object(R,'one_key_readings',side_effect=AssertionError('protected original span')):
            row=self.run_line(source)
        self.assertIn('hozin',row['corrected'])
        a=source.index('hozin');b=a+len('hozin')
        self.assertTrue(all(y<=a or b<=x for x,y in row['original_spans']))
    def test_final_pair_rejection_keeps_original_ascii_and_anomaly(self):
        source='💡 '+RAW;self.a.decisions.reject(RAW,FACE)
        row=self.run_line(source)
        self.assertEqual(row['corrected'],source)
        self.assertEqual(row['odd_spans'],[(2,len(source))])
        self.assertEqual(C.visible_odd_spans(source,row['odd_spans'],self.a.decisions),[])
    def test_unknown_english_and_kana_mode_do_not_get_new_key_search(self):
        with patch.object(R,'one_key_readings',side_effect=AssertionError('independent anomaly required')):
            for source in ('💡 hello','💡 tanhonotunagari','💡 yubinkyoku','💡 ｓｈｉｒｙｏｕｗｏｈｏｚｉｎｓｈｉｍａｓｕ'):
                self.assertEqual(self.run_line(source)['corrected'],source)
            self.assertEqual(self.run_line('💡 '+RAW,'kana')['corrected'],'💡 '+RAW)
    def test_stops_and_empty_completion_keep_original_anomaly_coordinate(self):
        prefix='👩🏽‍💻 ';source=prefix+RAW
        for state,status in (('state_limit','limited'),('input_limit','limited'),('complete','complete')):
            with self.subTest(state=state),patch.object(R,'one_key_readings',return_value=R.ReadingSearch(state,1,())):
                row=self.run_line(source)
            self.assertEqual(row['corrected'],source)
            self.assertEqual(row['odd_spans'],[(len(prefix),len(source))])
            self.assertEqual(row['analysis_status'],status)
            self.assertEqual(bool(row.get('search_reports')),state!='complete')
            self.assertIsNone(R._DIAGNOSTICS.get());self.assertIsNone(R._READINGS.get())
    def test_other_field_anomaly_stays_at_original_position_after_completion(self):
        phrase='処理がじゃのになっていないだろうか';prefix='👩🏽‍💻 '+RAW+'\t'
        before=self.run_line(phrase);after=self.run_line(prefix+phrase)
        self.assertTrue(before['odd_spans'])
        self.assertEqual(after['corrected'],'👩🏽‍💻 '+FACE+'\t'+phrase)
        self.assertEqual(after['odd_spans'],[(a+len(prefix),b+len(prefix)) for a,b in before['odd_spans']])
        reports=[dict(r,start=r['start']+len(prefix),end=r['end']+len(prefix))
                 for r in before['diagnosis']['search_reports']]
        self.assertEqual(after['diagnosis']['search_reports'],reports)
        self.assertEqual(after['analysis_status'],before['analysis_status'])
    def test_outer_abort_and_cancel_do_not_publish_relocated_result(self):
        prefix='mojinyuuryoku\t💡 ';source=prefix+RAW
        for exception,reason in ((C._CorrectionLimit,'depth_limit'),(C._CorrectionCycle,'cycle')):
            with self.subTest(reason=reason),patch.object(R,'one_key_readings',side_effect=exception):
                row=self.run_line(source)
            self.assertEqual(row['corrected'],source)
            self.assertEqual(row['original_spans'],[])
            self.assertEqual(row['odd_spans'],[(len(prefix),len(source))])
            self.assertEqual(row['analysis_status'],'incomplete');self.assertEqual(row['stop_reason'],reason)
        with patch.object(R,'one_key_readings',side_effect=SupersededAnalysis):
            with self.assertRaises(SupersededAnalysis):self.run_line(source)
        self.assertIsNone(R._DIAGNOSTICS.get());self.assertIsNone(R._READINGS.get())
        self.assertIsNone(K._LIMITS.get());self.assertIsNone(C._CORRECTION_SOURCE.get())

if __name__=='__main__':unittest.main()
