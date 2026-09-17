# -*- coding: utf-8 -*-
"""Existing anomaly, original native seam, unchanged action context, same policy."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as N
import contextual_repair as R
import oddness as O
import corrector as C


class KanaActionRepairTests(unittest.TestCase):
    def test_native_source_suru_and_following_action_are_seam_evidence(self):
        ts=[('ようせん','名詞:サ変接続','ようせん',0,4,True,''),
            ('し','動詞:自立','し',4,5,True,'連用形'),
            ('て','助詞:接続助詞','て',5,6,True,''),
            ('ほせい','名詞:サ変接続','ほせい',6,9,True,'')]
        with patch.object(M,'dictionary_inflections',return_value=(
                     ('動詞,自立,*,*','連用形','する','し'),)), \
             patch.object(N,'native_bare_action_faces',return_value=('補正',)):
            self.assertEqual(N.native_action_note_seams('ようせんしてほせい',ts),(4,))
            self.assertEqual(N.native_action_note_seams('用船してほせい',ts),())
            changed=list(ts);changed[1]=('し','名詞:一般','し',4,5,True,'')
            self.assertEqual(N.native_action_note_seams('ようせんしてほせい',changed),())

    def test_a_seam_without_an_existing_anomaly_never_opens_repair(self):
        with patch.object(N,'native_action_note_seams',return_value=(4,)), \
             patch.object(O,'is_odd_run',return_value=[]), \
             patch.object(C,'_kana_run_is_odd_by_grammar',return_value=False):
            self.assertEqual(R.targets_for_line('ようせんしてほせい',lambda s:[],None,None),[])

    def test_the_same_whole_kana_judgment_preserves_original_context(self):
        with patch.object(N,'native_action_note_seams',return_value=(4,)), \
             patch.object(O,'is_odd_run',return_value=[]), \
             patch.object(C,'_kana_run_is_odd_by_grammar',return_value=True):
            ts=R.targets_for_line('ようせんしてほせい',lambda s:[],None,None)
        self.assertEqual([(t.text,t.following,t.context,t.structural) for t in ts],
                         [('ようせん','してほせい','ようせんしてほせい',True)])

    def test_normal_replacement_acceptor_and_native_whole_proof_both_apply(self):
        target=R.RepairTarget('ようせんしてほせい',0,4,0,9,
                            (('文法','異様',0,9),),True,'してほせい','kana_action_note')
        with patch.object(C,'_check_replacement',return_value=(None,'blocked')), \
             patch.object(N,'completed_native_action_note') as complete:
            self.assertEqual(R.validate(target,'ゆうせん',C,lambda s:[],None,None,
                                         expected_reading='ゆうせん'),(False,'blocked'))
            complete.assert_not_called()
        with patch.object(C,'_check_replacement',return_value=((0,4,'ゆうせん','かな入力'),None)), \
             patch.object(O,'structural_anomaly_in_range',return_value=False), \
             patch.object(N,'completed_native_action_note',return_value=True) as complete:
            self.assertTrue(R.validate(target,'ゆうせん',C,lambda s:[],None,None,
                                       expected_reading='ゆうせん')[0])
            complete.assert_called_once_with('ゆうせんしてほせい')
            self.assertFalse(R.validate(target,'優先',C,lambda s:[],None,None,
                                        expected_reading='ゆうせん')[0])


if __name__=='__main__':unittest.main()
