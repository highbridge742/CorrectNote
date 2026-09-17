# -*- coding: utf-8 -*-
"""Quotation and productive position suffixes retain their existing grammatical roles."""
import unittest
from unittest.mock import patch
import oddness as O
import pos_grammar as P


def parts(items):
    out=[];edge=0
    for surface,pos,reading in items:
        out.append((surface,pos,reading,edge,edge+len(surface),True,''))
        edge+=len(surface)
    return out


class QuotationAndPositionTests(unittest.TestCase):
    def test_native_quotation_type_is_distinct_from_case_and_parallel_particles(self):
        self.assertTrue(P.is_quotative_particle('と','助詞:格助詞:引用'))
        self.assertTrue(P.is_quotative_particle('という','助詞:格助詞:連語'))
        for surface,pos in (('と','助詞:格助詞:一般'),('と','助詞:並立助詞'),
                            ('を','助詞:格助詞:一般'),('という','名詞:一般'),
                            ('という','助詞:格助詞:一般'),('と',None)):
            self.assertFalse(P.is_quotative_particle(surface,pos))

    def test_interjection_quotation_has_no_case_mismatch_in_either_judgement_mode(self):
        for word in ('はい','エイ','ありがとう'):
            for particle,pos in (('と','助詞:格助詞:引用'),('という','助詞:格助詞:連語')):
                tokens=parts([(word,'感動詞',word),(particle,pos,particle)])
                with patch.object(O,'_load',return_value=set()):
                    for skip in (False,True):
                        self.assertEqual(O.is_odd_run(word+particle,lambda _:tokens,
                                                    with_spans=True,skip_join=skip),[])

    def test_position_suffixes_can_attach_to_an_already_suffixed_nominal(self):
        for head,suffix in (('形容詞','句'),('報告','書')):
            for place in ('内','外','前','後'):
                tokens=parts([(head,'名詞:一般',head),
                             (suffix,'名詞:接尾:一般',suffix),
                             (place,'名詞:接尾:一般',place)])
                with patch.object(O,'_load',return_value=set()):
                    for skip in (False,True):
                        self.assertEqual(O.is_odd_run(head+suffix+place,lambda _:tokens,
                                                    with_spans=True,skip_join=skip),[])

    def test_unexplained_suffix_pair_still_reports_the_same_original_range(self):
        tokens=parts([('簡易','名詞:一般','かんい'),('流','名詞:接尾:一般','りゅう'),
                     ('力','名詞:接尾:一般','りょく')])
        with patch.object(O,'_load',return_value=set()),patch.object(O,'_run_is_word',return_value=False):
            for skip in (False,True):
                self.assertIn(('流','力',2,4),O.is_odd_run('簡易流力',lambda _:tokens,
                                                       with_spans=True,skip_join=skip))


if __name__=='__main__':
    unittest.main()
