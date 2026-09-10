# -*- coding: utf-8 -*-
import unittest
import oddness as O

class ParallelEvidenceTests(unittest.TestCase):
    def tokens(self,partner='動詞',last='詞'):
        return [(partner,'名詞:一般','',0,2,True,''),('と','助詞:並立助詞','と',2,3,True,''),
                ('側','名詞:一般','がわ',3,4,True,''),('置'+last,'名詞:一般','',4,6,False,''),
                ('の','助詞:連体化','の',6,7,True,'')]

    def test_known_partner_supplies_nominal_context(self):
        text='動詞と側置詞の'
        self.assertTrue(O._fragment_has_parallel_noun_context(text,3,6,lambda _:self.tokens()))

    def test_partner_must_share_category_ending(self):
        self.assertFalse(O._fragment_has_parallel_noun_context('動詞と側置語の',3,6,
                         lambda _:self.tokens(last='語')))

    def test_kana_fragment_not_covered_by_nominal_evidence(self):
        self.assertFalse(O._fragment_has_parallel_noun_context('動詞とにゅカミス',3,8,
                         lambda _:self.tokens()))

    def test_without_parallel_context_no_proof(self):
        self.assertFalse(O._fragment_has_parallel_noun_context('側置詞',0,3,
                         lambda _:[('側','名詞:一般','がわ',0,1,True,''),('置詞','名詞:一般','',1,3,False,'')] ))

if __name__=='__main__':unittest.main()
