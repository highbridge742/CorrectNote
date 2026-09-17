# -*- coding: utf-8 -*-
"""A printed voiced kana cannot disguise remote physical key deletions."""
import unittest
from unittest.mock import patch
import kana_layout as K
import corrector as C


class MultipleKeyDeletionTests(unittest.TestCase):
    def test_each_removed_key_needs_an_original_neighbor(self):
        self.assertFalse(K.multiple_key_drop_adjacency('かえぎで','かえで'))
        self.assertTrue(K.multiple_key_drop_adjacency('かきくにん','かにん'))
        self.assertFalse(K.multiple_key_drop_adjacency('かきく゛にん','かにん'))
        for source,target in (('が','か'),('あ、','あ'),('あ、。','あ'),
                              ('せつめ','せつめい'),('もんじ','もじ'),('かえぎ','かいぎ')):
            self.assertIsNone(K.multiple_key_drop_adjacency(source,target),(source,target))

    def test_legacy_and_common_final_share_the_physical_proof(self):
        with patch.object(C,'_ADJ_GATE',True):
            self.assertFalse(C._adj_ok_one_char('かえぎで','かえで','kana'))
            self.assertTrue(C._adj_ok_one_char('かえぎで','かえで','romaji'))
        token=C._CORRECTION_INPUT_METHOD.set('kana')
        try:
            for replacement in ((0,4,'かえで','かな入力'),(2,3,'','かな入力')):
                self.assertEqual(C._check_replacement('かえぎで',replacement,None,None),
                                 (None,'nonadjacent_original_key_deletion'))
            def native(text):return [(text,'名詞:一般','かえで',0,len(text),True,'')]
            self.assertEqual(C._check_replacement('かえぎで',(0,4,'楓','かな入力'),None,native),
                             (None,'nonadjacent_original_key_deletion'))
        finally:C._CORRECTION_INPUT_METHOD.reset(token)

    def test_unchanged_punctuation_does_not_hide_key_deletion(self):
        self.assertFalse(K.multiple_key_drop_adjacency('「かえぎで」','「かえで」'))
        self.assertTrue(K.multiple_key_drop_adjacency('かきくにん。','かにん。'))


if __name__=='__main__':unittest.main()
