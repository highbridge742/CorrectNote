import unittest
from unittest.mock import patch
import morphology as M,oddness as O,corrector as C
from analysis_context import SupersededAnalysis
from tests_negative_polite_context import tokens

class NegativePoliteScopeTests(unittest.TestCase):
    def test_negative_and_polite_need_their_actual_whole_native_forms(self):
        parts=tokens('鍵を抜かなます。');i=next(i for i,t in enumerate(parts) if t[0]=='な');a,b=parts[i:i+2];prior=parts[:i]
        self.assertTrue(O.polite_aux_mismatch(a,b,prior))
        for side,index,value in (('a',2,'ない'),('a',4,a[4]+1),('a',6,'基本形'),
                                 ('b',2,'まし'),('b',4,b[4]+1),('b',6,'連用形'),
                                 ('a',5,False),('b',5,False)):
            changed=list(a if side=='a' else b);changed[index]=value
            args=(tuple(changed),b) if side=='a' else (a,tuple(changed))
            with self.subTest(side=side,index=index,value=value):
                self.assertFalse(O.polite_aux_mismatch(*args,prior))
    def test_real_separators_and_nominal_owner_do_not_borrow_prior_host(self):
        for source in ('本を読ま、なますを作ります。','本を読ま なますを作ります。',
                       '本を読ま「なます」と言います。','本を読まない。なますを作ります。'):
            parts=tokens(source)
            for i,(a,b) in enumerate(zip(parts,parts[1:])):
                if a[0]+b[0]=='なます':
                    with self.subTest(source=source):self.assertFalse(O.polite_aux_mismatch(a,b,parts[:i]))
    def test_unrelated_clause_edit_does_not_own_the_bad_negative_tail(self):
        original='資料を確認する。旗を振らなます。';changed='書類を確認する。旗を振らなます。'
        self.assertTrue(O.changed_auxiliary_chain_allowed(changed,0,2,original))
        self.assertFalse(O.changed_auxiliary_chain_allowed('旗を振らなます。',0,8,'旗を振ります。'))
    def test_native_cancellation_propagates_without_cached_candidate_proof(self):
        original='旗を振ります。';changed='旗を振らなます。';native=M.dictionary_inflections
        O.changed_auxiliary_chain_allowed.cache_clear()
        def dictionary(word):
            if word=='振ら':raise SupersededAnalysis()
            return native(word)
        with patch.object(M,'dictionary_inflections',side_effect=dictionary):
            with self.assertRaises(SupersededAnalysis):O.changed_auxiliary_chain_allowed(changed,0,len(original),original)
        self.assertEqual(O.changed_auxiliary_chain_allowed.cache_info().currsize,0)

if __name__=='__main__':unittest.main()
