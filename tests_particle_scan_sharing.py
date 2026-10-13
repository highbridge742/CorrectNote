import unittest
from unittest.mock import patch
import morphology as M
from analysis_context import request_scope,SupersededAnalysis


def reference(reading,prefix,exact):
    reachable={0}
    for start in range(len(reading)):
        if start not in reachable:continue
        entries=prefix(reading[start:])
        if entries is None:
            for end in range(start+1,len(reading)+1):
                piece=reading[start:end]
                if any(pos.startswith('助詞,終助詞,') and rd==piece
                       for pos,form,base,rd in exact(piece) or ()):
                    reachable.add(end)
        else:
            reachable.update(start+len(surface)
                for surface,pos,kind,form,base,rd in entries
                if surface and pos.startswith('助詞,終助詞,') and rd==surface)
    return len(reading) in reachable


class ParticleScanSharingTests(unittest.TestCase):
    def setUp(self):
        M.native_final_particle_tail.cache_clear()
        M.colloquial_particle_normal_form.cache_clear()
    def test_every_reachable_boundary_keeps_prefix_and_fallback_query_order(self):
        particle='助詞,終助詞,*,*';noun='名詞,一般,*,*'
        entries=(('ねえ',particle,'*','*','ねえ','ねえ'),
                 ('ね',noun,'*','*','ね','ね'),('ね',particle,'*','*','ね','ね'),
                 ('よ',particle,'*','*','よ','よ'),('え',particle,'*','*','え','え'),
                 ('な',particle,'*','*','な','な'),('なあ',particle,'*','*','なあ','ちがう'))
        for text in ('ねえよねえな','ねえよねえなあ','なあ','ねえ?','ねよね'):
            for fallback in (False,True):
                with self.subTest(text=text,fallback=fallback):
                    def run(function):
                        calls=[]
                        def prefix(tail):
                            calls.append(('prefix',tail))
                            return None if fallback and tail.startswith('よ') else tuple(e for e in entries if tail.startswith(e[0]))
                        def exact(piece):
                            calls.append(('exact',piece))
                            return tuple((pos,form,base,rd) for face,pos,kind,form,base,rd in entries if face==piece)
                        value=function(text,prefix,exact)
                        return value,calls
                    expected=run(reference)
                    def current(text,prefix,exact):
                        M.native_final_particle_tail.cache_clear()
                        with patch.object(M,'dictionary_prefix_paradigms',side_effect=prefix),patch.object(M,'dictionary_inflections',side_effect=exact):
                            return M.native_final_particle_tail(text)
                    self.assertEqual(run(current),expected)
    def test_prepared_tail_has_same_script_and_actual_text_boundary(self):
        sources=('👩🏽‍💻 行くょネ。𠮷さんも行くょね','行くょネ。戻るょナ','行くょねABC','しりょうょね。行くょね',
                 '行くょね👩‍💻','行くょね\t来るょね','行くょねー','行くょ、来るょネ',
                 '行くョね','行くょね⇒来るょね','行くょね）来るょね','行くょ\r\n来るょね')
        for source in sources:
            expected=[]
            with patch.object(M,'native_final_particle_tail',side_effect=lambda tail:expected.append(tail) or False):
                for i,char in enumerate(source):
                    if char=='ょ':M._small_particle_tail_possible(source,i)
            actual=[]
            with patch.object(M,'native_final_particle_tail',side_effect=lambda tail:actual.append(tail) or False),patch.object(M,'_tokenize_janome',side_effect=AssertionError('unproved tail')):
                self.assertEqual(M.colloquial_particle_normal_form(source),source)
            self.assertEqual(actual,expected,source)
    def test_one_kana_run_is_scanned_once_without_skipping_any_candidate(self):
        class Counted(str):
            reads=0
            def __getitem__(self,key):
                if isinstance(key,int):self.reads+=1
                return super().__getitem__(key)
        source=Counted('しりょう'*768+'にいきます')
        with patch.object(M,'dictionary_prefix_paradigms',return_value=()) as lookup,patch.object(M,'_tokenize_janome',side_effect=AssertionError('no final particle')):
            self.assertEqual(M.colloquial_particle_normal_form(source),source)
        self.assertEqual(lookup.call_count,768)
        self.assertLess(source.reads,10*len(source))
        self.assertEqual([call.args[0] for call in lookup.call_args_list],
                         [str(source)[i+1:] for i,c in enumerate(source) if c=='ょ'])
    def test_cancellation_during_shared_scan_prevents_native_query_and_cache(self):
        cancelled=[False]
        class Cancelling(str):
            reads=0
            def __getitem__(self,key):
                if isinstance(key,int):
                    self.reads+=1
                    if self.reads==500:cancelled[0]=True
                return super().__getitem__(key)
        source=Cancelling('しりょう'*768+'にいきます')
        with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(M,'dictionary_prefix_paradigms',side_effect=AssertionError('stale query')):
            with self.assertRaises(SupersededAnalysis):M.colloquial_particle_normal_form(source)
        self.assertEqual(M.colloquial_particle_normal_form.cache_info().currsize,0)
    def test_cancellation_during_reachable_query_prevents_tail_cache(self):
        cancelled=[False]
        def prefix(text):
            cancelled[0]=True
            return ((text,'助詞,終助詞,*,*','*','*',text,text),)
        with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(M,'dictionary_prefix_paradigms',side_effect=prefix):
            with self.assertRaises(SupersededAnalysis):M.native_final_particle_tail('ねえ')
        self.assertEqual(M.native_final_particle_tail.cache_info().currsize,0)

if __name__=='__main__':unittest.main()
