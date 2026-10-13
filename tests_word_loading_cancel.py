# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
# -*- coding: utf-8 -*-
"""Cancellation cannot publish partial public dictionary or absence evidence."""
import collections,gzip,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import word_table as W,oddness as O,seed_japanese as J
from analysis_context import request_scope,SupersededAnalysis

def reference(path):
    marked=set();unmarked=set()
    with gzip.open(path,'rt',encoding='utf8') as stream:
        for line in stream:
            word=line.rstrip('\n')
            if not word:continue
            (marked if word.startswith('*') else unmarked).add(word[1:] if word.startswith('*') else word)
    return frozenset(marked|unmarked),frozenset(marked)

class WordLoadingCancelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='reader-contract-',dir=str(Path(__file__).parent))
        self.addCleanup(self.temp.cleanup);self.dir=Path(self.temp.name)
        W._cached.cache_clear();self.addCleanup(W._cached.cache_clear)
        self.old=(O._WORDS,O._LEFT,O._RIGHT,O._PAIR,O._LOADED,J._WIDE,J._NARROW,J._MISSING)
        self.addCleanup(self.restore)
        O._WORDS=O._LEFT=O._RIGHT=O._PAIR=None;O._LOADED=False
        J._WIDE=J._NARROW=None;J._MISSING=False
    def restore(self):
        O._WORDS,O._LEFT,O._RIGHT,O._PAIR,O._LOADED,J._WIDE,J._NARROW,J._MISSING=self.old
    def source(self,text,name='seed_japanese.txt.gz'):
        path=self.dir/name;path.write_bytes(gzip.compress(text.encode('utf8'),mtime=0));return path
    def snapshot(self):return O._WORDS,O._LEFT,O._RIGHT,O._PAIR,O._LOADED
    def test_reference_word_sets_keep_markers_crlf_blank_and_unterminated_tail(self):
        for index,text in enumerate(('', '資料\r\n確認\r\n\r\n資料確認',
            '*資料\n資料\n*確認\n', '*資料\n確認\n*', '*'+('字'*300000)+'\n\t項目\n終端')):
            path=self.source(text,str(index)+'.gz')
            self.assertEqual(W.read_word_sets(path),reference(path))
            self.assertEqual(W.read_word_sets(path),reference(path))
    def test_obsolete_entry_does_not_read_or_cache_the_dictionary(self):
        path=self.source('*資料\n')
        with request_scope(lambda:True),patch.object(W.gzip,'open') as opened:
            with self.assertRaises(SupersededAnalysis):W.read_word_sets(path)
        opened.assert_not_called();self.assertEqual(W._cached.cache_info().currsize,0)
    def test_mid_parse_cancellation_discards_local_partial_sets_and_can_retry(self):
        path=self.source('\n'.join('*資料'+str(i) for i in range(2000)))
        stale=[False];added=[0]
        class TrackingSet(set):
            def add(self,value):
                super().add(value);added[0]+=1
                if added[0]>=450:stale[0]=True
        with request_scope(lambda:stale[0]),patch.object(W,'set',TrackingSet,create=True):
            with self.assertRaises(SupersededAnalysis):W.read_word_sets(path)
        self.assertLess(added[0],2000);self.assertEqual(W._cached.cache_info().currsize,0)
        self.assertEqual(W.read_word_sets(path),reference(path))
    def test_empty_eof_cancellation_is_not_a_completed_empty_dictionary(self):
        path=self.source('');stale=[False]
        class Stream(io.StringIO):
            def read(self,size=-1):
                result=super().read(size)
                if not result:stale[0]=True
                return result
        with patch.object(W.gzip,'open',return_value=Stream('')),request_scope(lambda:stale[0]):
            with self.assertRaises(SupersededAnalysis):W.read_word_sets(path)
        self.assertEqual(W._cached.cache_info().currsize,0)
        self.assertEqual(W.read_word_sets(path),(frozenset(),frozenset()))
    def test_cancel_after_complete_reader_cannot_publish_into_its_lru(self):
        path=self.source('*資料\n確認');old=W._read;stale=[False]
        def completed(*args):
            value=old(*args);stale[0]=True;return value
        with patch.object(W,'_read',side_effect=completed),request_scope(lambda:stale[0]):
            with self.assertRaises(SupersededAnalysis):W.read_word_sets(path)
        self.assertEqual(W._cached.cache_info().currsize,0)
        self.assertEqual(W.read_word_sets(path),reference(path))
    def test_cancelled_cache_hit_keeps_the_previous_completed_immutable_entry(self):
        path=self.source('*資料\n確認');expected=W.read_word_sets(path);old=W._cached;stale=[False]
        def cached(*args):
            value=old(*args);stale[0]=True;return value
        with patch.object(W,'_cached',side_effect=cached),request_scope(lambda:stale[0]):
            with self.assertRaises(SupersededAnalysis):W.read_word_sets(path)
        self.assertEqual(old.cache_info().currsize,1);self.assertIs(W.read_word_sets(path),expected)
    def odd_path(self):
        self.source('*資料\n*確認\n*資料確認')
        return patch.object(O,'__file__',str(self.dir/'oddness.py'))
    def test_cancel_after_compound_lookup_publishes_none_of_the_five_globals(self):
        words=frozenset(('資料','確認','資料確認'));derived=(collections.Counter({'資料':1}),collections.Counter({'確認':1}),{('資料','確認')})
        before=self.snapshot();stale=[False]
        def ready(*args):stale[0]=True;return derived
        with self.odd_path(),patch.object(O,'MIN_WORDS',2),patch.object(W,'read_word_sets',return_value=(words,words)),patch.object(W,'read_compound_tables',side_effect=ready),request_scope(lambda:stale[0]):
            with self.assertRaises(SupersededAnalysis):O._load()
        self.assertEqual(self.snapshot(),before)
        with self.odd_path(),patch.object(O,'MIN_WORDS',2),patch.object(W,'read_word_sets',return_value=(words,words)),patch.object(W,'read_compound_tables',return_value=derived):
            self.assertEqual(O._load(),words);self.assertEqual((O._LEFT,O._RIGHT,O._PAIR),derived);self.assertTrue(O._LOADED)
    def test_cancel_in_fallback_compound_scan_discards_partial_counts(self):
        stale=[False]
        class Words(frozenset):
            def __iter__(self):
                for index,word in enumerate(super().__iter__()):
                    if index==200:stale[0]=True
                    yield word
        words=Words(chr(0x4e00+i)+'字' for i in range(1000));before=self.snapshot()
        with self.odd_path(),patch.object(O,'MIN_WORDS',2),patch.object(W,'read_word_sets',return_value=(words,words)),patch.object(W,'read_compound_tables',return_value=None),request_scope(lambda:stale[0]):
            with self.assertRaises(SupersededAnalysis):O._load()
        self.assertEqual(self.snapshot(),before)
        with self.odd_path(),patch.object(O,'MIN_WORDS',2),patch.object(W,'read_word_sets',return_value=(frozenset(words),frozenset(words))),patch.object(W,'read_compound_tables',return_value=None):
            self.assertEqual(O._load(),words);self.assertEqual(O._LEFT,{});self.assertEqual(O._RIGHT,{})
    def test_normal_failure_preserves_previous_counter_failure_behavior(self):
        O._LEFT=collections.Counter({'kept':3});O._RIGHT=collections.Counter({'kept':4});O._PAIR={('kept','pair')}
        before=(O._LEFT,O._RIGHT,O._PAIR)
        with self.odd_path(),patch.object(O,'MIN_WORDS',2),patch.object(W,'read_word_sets',return_value=(frozenset(('資料','確認')),frozenset())),patch.object(W,'read_compound_tables',side_effect=ValueError('synthetic corrupt index')):
            self.assertIsNone(O._load())
        self.assertEqual((O._LEFT,O._RIGHT,O._PAIR),before);self.assertTrue(O._LOADED)
    def test_seed_cancellation_never_becomes_missing_and_retry_is_complete(self):
        stale=[False];wide=frozenset(('資料','確認'));narrow=frozenset(('資料',))
        def ready(*args):stale[0]=True;return wide,narrow
        with patch.object(W,'read_word_sets',side_effect=ready),request_scope(lambda:stale[0]):
            with self.assertRaises(SupersededAnalysis):J._load()
        self.assertEqual((J._WIDE,J._NARROW,J._MISSING),(None,None,False))
        with patch.object(W,'read_word_sets',return_value=(wide,narrow)):
            self.assertEqual(J._load(),wide);self.assertEqual(J._NARROW,narrow);self.assertFalse(J._MISSING)
    def test_unavailable_seed_keeps_its_previous_none_result(self):
        with patch.object(W,'read_word_sets',side_effect=FileNotFoundError('synthetic missing source')):
            self.assertIsNone(J._load())
        self.assertEqual((J._WIDE,J._NARROW,J._MISSING),(None,None,True))
    def test_compound_decode_cancellation_cannot_return_missing_or_partial_tables(self):
        path=self.source('*資料\n');source_sha=hashlib.sha256(path.read_bytes()).hexdigest()
        value=dict(schema=1,source_sha256=source_sha,left={'資料':1},right={'確認':1},pairs=[['資料','確認']])
        index=self.dir/'compound.gz';index.write_bytes(gzip.compress(json.dumps(value).encode(),mtime=0));index_sha=hashlib.sha256(index.read_bytes()).hexdigest();stale=[False];decode=json.loads
        def parsed(*args,**kwargs):
            result=decode(*args,**kwargs);stale[0]=True;return result
        with patch.object(W,'_COMPOUND_SOURCE_SHA256',source_sha),patch.object(W,'_COMPOUND_INDEX_SHA256',index_sha):
            with patch('json.loads',side_effect=parsed),request_scope(lambda:stale[0]):
                with self.assertRaises(SupersededAnalysis):W.read_compound_tables(path,index)
            self.assertEqual(W.read_compound_tables(path,index),(collections.Counter(value['left']),collections.Counter(value['right']),set(map(tuple,value['pairs']))))
if __name__=='__main__':unittest.main()
