import unittest
from unittest.mock import patch
import public_nominal_cache
public_nominal_cache.load=lambda *_args,**_kwargs:None
import corrector as C,romaji_repair as R,romaji_source as K
from correction_entry import correct_line
from tests_analysis_async import initial
from last_choice import set_active
from analysis_context import request_scope,SupersededAnalysis

RAW='shiryouwohozinshimasu';FACE='資料を保存します'

class RomajiSymbolScopeTests(unittest.TestCase):
    def run_line(self,source):
        a=initial()
        try:return correct_line(source,a.store,input_method='romaji',decisions=a.decisions,dict_index=a.dict_index,context_vec=None)
        finally:set_active(None)

    def test_scope_keeps_ascii_japanese_and_combining_content_inside_symbol_run(self):
        for marker in ('💡a','💡あ','💡\u0301','💡\u20e3','💡_','💡1','💡\u200da','©a'):
            source=marker+' '+RAW;a=source.index(RAW)
            self.assertFalse(R._whole_field(source,a,a+len(RAW)),repr(marker))
        for separator in ('\t','⇒','→','\n','\r\n'):
            for source in ('fn('+RAW+')'+separator+'💡 '+RAW,'💡 '+RAW+separator+'fn('+RAW+')'):
                a=source.index(RAW) if source.startswith('💡') else source.rindex(RAW)
                self.assertTrue(R._whole_field(source,a,a+len(RAW)),source)
                b=source.rindex(RAW) if source.startswith('💡') else source.index(RAW)
                self.assertFalse(R._whole_field(source,b,b+len(RAW)),source)
        source='💡 '+RAW+' + '+RAW
        for a in (source.index(RAW),source.rindex(RAW)):
            self.assertFalse(R._whole_field(source,a,a+len(RAW)))

    def test_repeated_raw_field_final_rejection_is_owned_by_its_original_offset(self):
        source='💡 '+RAW+'\t© '+RAW;first=source.index(RAW);second=source.rindex(RAW)
        real=C._check_replacement;gates=[]
        def checked(line,edit,*args,**kwargs):
            if line==source and edit[2]==FACE:
                gates.append(edit[:3])
                if edit[0]==first:return None,'independent_review_first_field_rejection'
            return real(line,edit,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=checked):row=self.run_line(source)
        self.assertEqual(row['corrected'],'💡 '+RAW+'\t© '+FACE)
        self.assertIn((first,first+len(RAW),FACE),gates)
        self.assertIn((second,second+len(RAW),FACE),gates)
        self.assertEqual(row['original_spans'],[(second,second+len(RAW))])
        self.assertIn((first,first+len(RAW)),row['odd_spans'])

    def test_superseded_request_after_new_scope_proof_cannot_publish_partial_result(self):
        source=RAW+'\t💡 '+RAW;real=R._whole_field;state={'cancel':False,'eligible':[]}
        def whole(line,start,end):
            result=real(line,start,end)
            if result and '💡' in line[:start]:
                state['eligible'].append((line,start,end));state['cancel']=True
            return result
        with request_scope(lambda:state['cancel']),patch.object(R,'_whole_field',side_effect=whole):
            with self.assertRaises(SupersededAnalysis):self.run_line(source)
        self.assertTrue(state['eligible'])
        self.assertIsNone(C._CORRECTION_SOURCE.get())
        self.assertIsNone(R._DIAGNOSTICS.get());self.assertIsNone(R._READINGS.get());self.assertIsNone(K._LIMITS.get())

if __name__=='__main__':unittest.main()
