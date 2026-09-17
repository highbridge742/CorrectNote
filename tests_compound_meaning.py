# -*- coding: utf-8 -*-
"""Source meaning is judged first and its context survives range construction."""
import unittest
from unittest.mock import patch
import semantic_roles as S
import contextual_repair as R
import oddness as O


def noun(word,start,sub='一般',known=True):
    return (word,'名詞:'+sub,word,start,start+len(word),known,'')


class CompoundMeaningTests(unittest.TestCase):
    def test_source_categories_judge_a_relationship_without_candidates(self):
        ts=[noun('画面',0),noun('繁栄',2,'サ変接続')]
        self.assertEqual(S.conflicting_nominal_compounds('画面繁栄',ts),[('画面','繁栄',2,4)])
        self.assertEqual(S.conflicting_nominal_compounds('経済繁栄',
                         [noun('経済',0),ts[1]]),[])
        self.assertEqual(S.conflicting_nominal_compounds('画面反映',
                         [ts[0],noun('反映',2,'サ変接続')]),[])

    def test_source_boundaries_and_reading_evidence_are_required(self):
        for text,ts in (
            ('画面 繁栄',[noun('画面',0),noun('繁栄',3,'サ変接続')]),
            ('画面繁栄',[noun('画面',0,known=False),noun('繁栄',2,'サ変接続')]),
            ('画面繁栄',[noun('画面',0,'固有名詞'),noun('繁栄',2,'サ変接続')]),
            ('画面繁栄',[noun('画面',0),noun('繁栄',2,'固有名詞')])):
            self.assertEqual(S.conflicting_nominal_compounds(text,ts),[],text)

    def test_native_noun_parts_keep_the_whole_context_word(self):
        ts=[noun('表示',0,'サ変接続'),noun('面',2,'接尾:一般'),noun('繁栄',3,'サ変接続')]
        self.assertEqual(S.conflicting_nominal_compounds('表示面繁栄',ts),[('表示面','繁栄',3,5)])

    def test_literal_error_example_uses_the_existing_protection(self):
        ts=[noun('画面',1),noun('繁栄',3,'サ変接続')]
        self.assertEqual(S.conflicting_nominal_compounds('「画面繁栄」という誤字',ts),[])
        self.assertEqual(S.conflicting_nominal_compounds('「画面繁栄」',ts),[('画面','繁栄',3,5)])

    def test_candidate_meaning_uses_shared_positive_roles(self):
        for left in ('画面','表示面','描画面','プレビュー'):
            for operation in ('反映','描画','更新','同期','拡大','縮小','確認'):
                self.assertTrue(S.support(left,operation),(left,operation))
            for other in ('根性','繁栄','判じよう','未知の語'):
                self.assertFalse(S.support(left,other),(left,other))
        # Missing positive candidate evidence is not a new source anomaly.
        self.assertFalse(S.conflicting_nominal_compounds('画面共有',
                         [noun('画面',0),noun('共有',2,'サ変接続')]))

    def test_repair_range_keeps_the_classified_left_noun_as_context(self):
        ts=[noun('画面',0),noun('繁栄',2,'サ変接続')]
        with patch.object(O,'is_odd_run',return_value=[('画面','繁栄',2,4)]):
            targets=R.targets_for_line('画面繁栄',lambda text:ts,None,None)
        self.assertEqual([(t.start,t.end,t.text,t.structural) for t in targets],
                         [(2,4,'繁栄',True)])
        self.assertEqual(targets[0].boundary_kind,'nominal_meaning')


if __name__=='__main__':unittest.main()
