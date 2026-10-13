# -*- coding: utf-8 -*-
"""The original native negative cannot borrow a noun homophone before masu."""
import unittest
from unittest.mock import patch
import morphology as M, oddness as O, corrector as C, reading_segments as R

def tokens(text):
    return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class NativeNegativePoliteTests(unittest.TestCase):
    def test_actual_irrealis_negative_cannot_borrow_nominal_masu(self):
        for source in ('本を読まなます。','手紙を書かなます。','荷物を持たなます。'):
            parts=tokens(source); i=next(n for n,t in enumerate(parts) if t[0]=='な')
            a,b=parts[i:i+2]
            self.assertTrue(O._kana_nominal_alternative(a[0]+b[0]))
            self.assertTrue(O.polite_aux_mismatch(a,b,parts[:i]),source)
            self.assertFalse(O.polite_aux_mismatch(a,b),source)
            self.assertIn((a[0],b[0],a[3],b[4]),O.is_odd_run(source,tokens,with_spans=True,complete_line=True))

    def test_missing_evidence_and_unrelated_predecessor_keep_prior_result(self):
        parts=tokens('本を読まなます。');i=3;a,b=parts[i:i+2];prior=parts[:i]
        for index,value in ((5,False),(3,prior[-1][3]+1),(4,prior[-1][4]-1),(6,'未然ウ接続'),(1,'動詞:接尾')):
            changed=list(prior[-1]);changed[index]=value
            self.assertFalse(O.polite_aux_mismatch(a,b,prior[:-1]+[tuple(changed)]))
        native=M.dictionary_inflections
        for missing in ('読ま','な','ます'):
            with patch.object(M,'dictionary_inflections',side_effect=lambda word,missing=missing: None if word==missing else native(word)):
                self.assertFalse(O.polite_aux_mismatch(a,b,prior),missing)

    def test_real_nouns_normal_negatives_and_classical_tails_keep_grammar(self):
        sources=('なますを作ります。','「なます」を読みます。',
            '本を読まないです。','読まなかったので帰ります。','読まなあかん。',
            '読まなあきません。','書かざるため戻ります。','読まなすぎます。','読まなさすぎます。',
            'であります。','ございません。','読み続けます。')
        for source in sources:
            parts=tokens(source)
            self.assertFalse(any(O.polite_aux_mismatch(a,b,parts[:i]) for i,(a,b) in enumerate(zip(parts,parts[1:]))),source)

    def test_candidate_chain_and_actual_common_gate_share_preceding_native_host(self):
        for source,bad in (('本を読みます。','本を読まなます。'),('手紙を書きます。','手紙を書かなます。')):
            self.assertFalse(O.changed_auxiliary_chain_allowed(bad,0,len(source),source))
            accepted,reason=C._check_replacement(source,(0,len(source),bad,'かな入力'),None,tokens)
            self.assertIsNone(accepted,(source,bad,reason))
            self.assertEqual(reason,'native_auxiliary_chain')
        for source,changed in (('本を読まないです。','本を読んだです。'),('しなため','したため')):
            self.assertFalse(R.preserves_native_negative_auxiliary(source,changed))

if __name__=='__main__':unittest.main()
