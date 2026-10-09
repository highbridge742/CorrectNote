# -*- coding: utf-8 -*-
"""Context extractors share native work, without sharing mutable tokens across rows."""
from collections import Counter
from unittest.mock import patch
import unittest
import morphology as M
from analysis_worker import Runtime
from analysis_context import SupersededAnalysis

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class ContextPreparationTests(unittest.TestCase):
    def fresh(self):
        import corrector
        from vocabulary import VocabularyStore
        r=Runtime();r.store=VocabularyStore();r.tokenize=corrector.make_tokenizer(r.store)
        return r
    def reference(self,r,lines):
        from vocabulary import build_context_vocab_cached
        from context_vec import extract_content_words
        attested={};context=build_context_vocab_cached(lines,r.store,{},attested_out=attested)
        words={s:extract_content_words(r.tokenize,s) for s in dict.fromkeys(lines) if s.strip()}
        return dict(context=context,attested=attested,words=words)
    def test_first_rows_and_a_single_edit_parse_only_once_and_preserve_outputs(self):
        lines=['前の資料を確認します。','次の資料を点検します。','','前の資料を確認します。']
        r=self.fresh();expected=self.reference(self.fresh(),lines);native=M._tokenize_uncached;counts=Counter()
        def parse(s):counts[s]+=1;return native(s)
        with patch.object(M,'_tokenize_uncached',side_effect=parse):
            self.assertEqual(r.prepare(lines),expected)
            self.assertEqual(counts,Counter({s:1 for s in lines if s}))
            counts.clear();changed=lines[:];changed[1]='次の資料を再点検します。'
            actual=r.prepare(changed);self.assertEqual(counts,Counter({changed[1]:1}))
        self.assertEqual(actual,self.reference(self.fresh(),changed))
        self.assertIsNone(M._TOKENIZATION_CACHE.get());self.assertIsNone(M._NATIVE_TOKENIZATION_CACHE.get())
    def test_cached_context_with_missing_content_words_uses_original_extractor(self):
        from vocabulary import build_context_vocab_cached
        r=self.fresh();lines=['資料を確認します。','別の記録です。']
        build_context_vocab_cached(lines,r.store,r.context_lines,attested_out={})
        self.assertFalse(r.content_words)
        self.assertEqual(r.prepare(lines),self.reference(self.fresh(),lines))
    def test_native_values_are_released_between_rows_and_when_preparation_fails(self):
        import context_vec
        r=self.fresh();seen=[];extract=context_vec.extract_content_words
        def collect(fn,line):
            cache=M._TOKENIZATION_CACHE.get();self.assertIsNotNone(cache)
            self.assertEqual(set(cache),{line});seen.append(cache)
            return extract(fn,line)
        with patch.object(context_vec,'extract_content_words',side_effect=collect):
            r.prepare(['資料を確認します。','記録を調べます。'])
        self.assertIsNot(seen[0],seen[1]);self.assertIsNone(M._TOKENIZATION_CACHE.get())
        for error in (ValueError('synthetic error'),SupersededAnalysis()):
            r=self.fresh()
            with patch.object(context_vec,'extract_content_words',side_effect=error):
                with self.assertRaises(type(error)):r.prepare(['資料を確認します。'])
            self.assertFalse(r.prepared);self.assertFalse(r.content_words)
            self.assertIsNone(M._TOKENIZATION_CACHE.get());self.assertIsNone(M._NATIVE_TOKENIZATION_CACHE.get())
    def test_old_callers_and_native_dictionary_unavailable_path_are_preserved(self):
        from vocabulary import build_context_vocab_cached
        r=self.fresh();lines=['資料を確認します。']
        self.assertEqual(build_context_vocab_cached(lines,r.store,{}),self.reference(r,lines)['context'])
        with patch.object(M,'HAS_JANOME',False):
            self.assertEqual(build_context_vocab_cached(lines,r.store,{},tokenize_fn=lambda line:self.fail('native callback ran')), {})

if __name__=='__main__':unittest.main()
