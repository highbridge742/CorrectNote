import unittest
from unittest.mock import patch
import morphology as M,corrector as C
from tests_analysis_async import initial
from last_choice import set_active

class ContextualVerbScopeTests(unittest.TestCase):
    def test_unicode_original_questions_and_real_negative_in_their_own_field(self):
        a=initial()
        try:
            tok=C.make_tokenizer(a.store)
            for source,part,face,allowed in (
                    ('💡 資料⇒あるかと聞きます','あるか','歩か',False),
                    ('💡 資料⇒あれはとどか','とどか','届か',False),
                    ('前半\tあるかないか','あるか','歩か',False),
                    ('あるかないか分かりません','あるか','歩か',False),
                    ('💡 前半⇒書類がとどかなかった','とどか','届か',True)):
                with self.subTest(source=source):
                    start=source.index(part);end=start+len(part)
                    accepted,reason=C._check_replacement(source,(start,end,face,'かな入力'),a.store,tok,a.dict_index,a.decisions,spelling=True,conv_taken=((start,end),))
                    self.assertEqual(accepted is not None,allowed,(accepted,reason))
                    if accepted:self.assertEqual(accepted[:2],(start,end))
        finally:set_active(None)

    def test_following_proof_does_not_borrow_negative_across_field_whitespace(self):
        self.assertFalse(M.native_spelling_only('あるか','歩か'))
        self.assertTrue(M.native_spelling_only('あるか','歩か',following='なかった'))
        for tail in ('\r\nなかった',' ⇒ なかった','  なかった','\u2003なかった','ないか','ないか分かりません'):
            with self.subTest(tail=tail):
                self.assertFalse(M.native_spelling_only('あるか','歩か',following=tail))

    def test_cancellation_during_original_native_boundary_cannot_publish(self):
        from analysis_context import request_scope,SupersededAnalysis
        native=M.tokenize
        original='あるかなかった';valid=native(original)
        native('歩か');native('歩かなかった')
        for answer in (valid,[]):
            stale=False;seen=[]
            def mark_stale(text):
                nonlocal stale
                if text==original:
                    seen.append(text);stale=True;return answer
                return native(text)
            with request_scope(lambda:stale,poll_interval=1000),patch.object(M,'tokenize',mark_stale):
                with self.assertRaises(SupersededAnalysis):
                    M.native_spelling_only('あるか','歩か',following='なかった')
            self.assertTrue(seen)

    def test_original_ascii_gate_rejection_cannot_be_bypassed_after_local_completion(self):
        from correction_entry import correct_line
        a=initial();source='💡 kouendearukanakatta\tshoruiwohozonshimasu'
        native=C._check_replacement;blocked=[]
        def reject_first_original(*args,**kwargs):
            text,replacement=args[:2]
            if text==source and replacement[0]<21 and replacement[1]>2:
                blocked.append(replacement)
                return None,'independent_original_field_reject'
            return native(*args,**kwargs)
        try:
            with patch.object(C,'_check_replacement',reject_first_original):
                result=correct_line(source,a.store,input_method='romaji',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertTrue(blocked)
            self.assertEqual(result['corrected'],'💡 kouendearukanakatta\t書類を保存します')
            self.assertEqual(result['original_spans'],[(22,42)])
            self.assertEqual(result['odd_spans'],[])
            self.assertEqual(result['analysis_status'],'complete')
        finally:set_active(None)

if __name__=='__main__':unittest.main()
