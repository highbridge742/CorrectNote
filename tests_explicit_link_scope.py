import unittest
from unittest.mock import patch
import corrector as C,literal_examples as L,halfwidth,text_links

RAW='d).ek-c@y'

class ReachedExistingGate(Exception):pass

class ExplicitLinkScopeTests(unittest.TestCase):
    def test_both_edges_are_external_but_crossing_a_link_is_not(self):
        source='前 C:\\資料'+RAW+' 後'
        a,b=L.explicit_link_ranges(source)[0]
        for start,end in ((a,a+1),(b-1,b),(a-1,a+1),(b-1,b+1),(a+2,a+2)):
            with self.subTest(span=(start,end)):
                accepted,reason=C._check_replacement(source,(start,end,'X','かな入力'),None,None)
                self.assertIsNone(accepted);self.assertEqual(reason,'original_explicit_link')
        for edge in (a,b):
            with self.subTest(edge=edge),patch.object(halfwidth,'original_ascii_expression',return_value=False),patch('romaji_source.candidate_evidence',side_effect=ReachedExistingGate):
                with self.assertRaises(ReachedExistingGate):C._check_replacement(source,(edge,edge,'X','かな入力'),None,None)

    def test_multiple_links_original_ancestors_and_external_duplicate_keep_positions(self):
        ancestor='しょるいをほぞんします\t👩🏽‍💻 https://x.test/資料'+RAW+'、C:\\メモ'+RAW+'\t'+RAW
        current='書類を保存します\t👩🏽‍💻 🔗資料'+RAW+'、C:\\メモ'+RAW+'\t'+RAW
        ranges=L.explicit_link_ranges(ancestor)
        self.assertEqual(len(ranges),2)
        self.assertEqual([ancestor[a:b] for a,b in ranges],['https://x.test/資料'+RAW,'C:\\メモ'+RAW])
        starts=[];offset=0
        while True:
            offset=current.find(RAW,offset)
            if offset<0:break
            starts.append(offset);offset+=len(RAW)
        token=C._CORRECTION_PATH.set((ancestor,))
        try:
            for index,start in enumerate(starts):
                mappings=list(C._candidate_source_ranges(current,start,start+len(RAW)))
                self.assertTrue(any(src==ancestor and src[a:b]==RAW for src,a,b in mappings))
                if index<2:
                    accepted,reason=C._check_replacement(current,(start,start+len(RAW),'書類の保存','かな入力'),None,None)
                    self.assertIsNone(accepted);self.assertEqual(reason,'original_explicit_link')
                else:
                    with patch.object(halfwidth,'original_ascii_expression',return_value=False),patch('romaji_source.candidate_evidence',side_effect=ReachedExistingGate):
                        with self.assertRaises(ReachedExistingGate):C._check_replacement(current,(start,start+len(RAW),'書類の保存','かな入力'),None,None)
        finally:C._CORRECTION_PATH.reset(token)

    def test_cancel_after_cache_hit_copy_cannot_return_ranges(self):
        from analysis_context import request_scope,SupersededAnalysis
        from ime_session import resource_scope,retain
        source='👩🏽‍💻 C:\\資料'+RAW;stale=[False]
        with resource_scope():
            self.assertTrue(L.explicit_link_ranges(source));cache,_=retain(L._ExplicitLinkRanges())
            def copy_then_cancel(values):
                result=list(values);stale[0]=True;return result
            with request_scope(lambda:stale[0],poll_interval=1000),patch.object(L,'list',side_effect=copy_then_cancel,create=True):
                with self.assertRaises(SupersededAnalysis):L.explicit_link_ranges(source)
        self.assertEqual(cache.ranges,{})

    def test_plain_scope_and_link_scope_do_not_reuse_each_others_result(self):
        from ime_session import resource_scope,retain
        link='https://example.test/資料'+RAW;plain='資料'+RAW
        finder=text_links.find_links
        with patch.object(text_links,'find_links',wraps=finder) as calls:
            with resource_scope():
                self.assertEqual(L.explicit_link_ranges(plain),[])
                self.assertEqual(L.explicit_link_ranges(link),[(0,len(link))])
                self.assertEqual(L.explicit_link_ranges(plain),[])
                cache,_=retain(L._ExplicitLinkRanges());self.assertEqual(calls.call_count,2)
            self.assertEqual(cache.ranges,{})
            with resource_scope():self.assertEqual(L.explicit_link_ranges(plain),[])
            self.assertEqual(calls.call_count,3)

if __name__=='__main__':unittest.main()
