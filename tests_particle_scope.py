import unittest
from unittest.mock import patch
import morphology as M
from analysis_context import request_scope,SupersededAnalysis

class ParticleCancellationTests(unittest.TestCase):
    def setUp(self):
        for fn in (M.native_final_particle_tail,M.colloquial_particle_normal_form,
                   M.dictionary_prefix_paradigms,M.dictionary_inflections,M.dictionary_paradigms):fn.cache_clear()
    def test_overlapping_paths_and_reversed_senses_keep_every_native_option(self):
        forms={
            'よ':(('名詞,一般,*,*','*','*','よ','よ'),('助詞,終助詞,*,*','*','*','よ','よ')),
            'よね':(('助詞,終助詞,*,*','*','*','よね','よね'),),
            'ねな':(('助詞,終助詞,*,*','*','*','ねな','ねな'),),
            'な':(('名詞,一般,*,*','*','*','な','な'),),
        }
        for reverse in (False,True):
            def prefixes(text):
                out=[(face,*row) for face,rows in forms.items() if text.startswith(face) for row in rows]
                return tuple(reversed(out)) if reverse else tuple(out)
            M.native_final_particle_tail.cache_clear()
            with patch.object(M,'dictionary_prefix_paradigms',side_effect=prefixes):
                self.assertTrue(M.native_final_particle_tail('よねな'))
                self.assertFalse(M.native_final_particle_tail('よな'))
    def test_unavailable_and_corrupt_native_prefix_retains_exact_fallback(self):
        native_lookup=M._TOKENIZER.sys_dic.lookup
        for error in (SystemExit(1),OSError('synthetic dictionary failure')):
            self.setUp()
            def lookup(value,matcher):
                if value=='ねよね'.encode('utf8'):raise error
                return native_lookup(value,matcher)
            with patch.object(M._TOKENIZER.sys_dic,'lookup',side_effect=lookup):
                self.assertTrue(M.native_final_particle_tail('ねよね'))
        self.setUp()
        with patch.object(M._TOKENIZER.sys_dic,'lookup_extra',return_value=('invalid',)):
            self.assertFalse(M.native_final_particle_tail('ねよね'))
    def test_fallback_cancellation_is_not_a_negative_result(self):
        pending=False
        def exact(piece):
            nonlocal pending
            pending=True
            return (('助詞,終助詞,*,*','*',piece,piece),)
        with request_scope(lambda:pending,poll_interval=600),patch.object(M,'dictionary_prefix_paradigms',return_value=None),patch.object(M,'dictionary_inflections',side_effect=exact):
            with self.assertRaises(SupersededAnalysis):M.native_final_particle_tail('ね')
        self.assertEqual(M.native_final_particle_tail.cache_info().currsize,0)
    def test_small_particle_cancel_after_last_attachment_cannot_publish_changed(self):
        pending=False;native=M._native_small_particle_tail
        def attached(*args):
            nonlocal pending
            result=native(*args);pending=True
            return result
        with request_scope(lambda:pending,poll_interval=600),patch.object(M,'_native_small_particle_tail',side_effect=attached):
            with self.assertRaises(SupersededAnalysis):M.colloquial_particle_normal_form('行くょ')
        self.assertEqual(M.colloquial_particle_normal_form.cache_info().currsize,0)
    def test_small_particle_cancel_after_last_attachment_cannot_publish_unchanged(self):
        pending=False;native=M._native_small_particle_tail
        def attached(*args):
            nonlocal pending
            result=native(*args);pending=True
            return result
        with request_scope(lambda:pending,poll_interval=600),patch.object(M,'_native_small_particle_tail',side_effect=attached):
            with self.assertRaises(SupersededAnalysis):M.colloquial_particle_normal_form('すふょ')
        self.assertEqual(M.colloquial_particle_normal_form.cache_info().currsize,0)


import unittest
from unittest.mock import patch
import morphology as M
from analysis_context import request_scope,SupersededAnalysis

class ParticleScanScopeTests(unittest.TestCase):
    def setUp(self):
        M.native_final_particle_tail.cache_clear();M.colloquial_particle_normal_form.cache_clear()
    def test_empty_duplicate_prefix_and_mixed_fallback_visit_each_boundary_once(self):
        particle='助詞,終助詞,*,*'
        row=lambda face:(face,particle,'*','*',face,face)
        source='ねよなねよな'
        def run(use_heap):
            calls=[]
            def prefix(tail):
                start=len(source)-len(tail);calls.append(('prefix',start))
                if start==0:return (row('ねよな'),row('ね'),row(''),row('ね'),row('ねよな'))
                if start==1:return None
                if start==2:return (row('なね'),row('なね'))
                if start==3:return ()
                if start==4:return (row('よな'),row('よな'))
                return ()
            def exact(piece):
                calls.append(('exact',piece))
                return ((particle,'*',piece,piece),) if piece in ('よ','よな') else None
            if use_heap:
                with patch.object(M,'dictionary_prefix_paradigms',side_effect=prefix),patch.object(M,'dictionary_inflections',side_effect=exact):
                    result=M.native_final_particle_tail(source)
            else:
                reachable={0}
                for start in range(len(source)):
                    if start not in reachable:continue
                    entries=prefix(source[start:])
                    if entries is None:
                        for end in range(start+1,len(source)+1):
                            piece=source[start:end]
                            if any(pos.startswith('助詞,終助詞,') and rd==piece for pos,form,base,rd in exact(piece) or ()):reachable.add(end)
                    else:
                        reachable.update(start+len(face) for face,pos,kind,form,base,rd in entries if face and pos.startswith('助詞,終助詞,') and rd==face)
                result=len(source) in reachable
            return result,calls
        result,calls=run(True)
        self.assertEqual((result,calls),run(False))
        self.assertTrue(result)
        self.assertEqual([r[1] for r in calls if r[0]=='prefix'],[0,1,2,3,4])
    def test_known_empty_prefix_is_distinct_from_unavailable_backend(self):
        with patch.object(M,'dictionary_prefix_paradigms',return_value=()),patch.object(M,'dictionary_inflections',side_effect=AssertionError('known empty prefix must not fall back')):
            self.assertFalse(M.native_final_particle_tail('ねよ'))
        M.native_final_particle_tail.cache_clear()
        with patch.object(M,'dictionary_prefix_paradigms',return_value=None),patch.object(M,'dictionary_inflections',return_value=None) as exact:
            self.assertFalse(M.native_final_particle_tail('ねよ'))
            self.assertEqual([x.args[0] for x in exact.call_args_list],['ね','ねよ'])
    def test_combining_control_and_nonmapped_katakana_keep_original_suffixes(self):
        for source in ('𠮷 行くょネ\u0301\t読むょね','行くょ\u3099。あるょね','行くょ\x00読むょネ','行くょ\u2028戻るょネ','行くょ\u2060\t帰るょね','行くょヷ。来るょね','行くょ\ufe0f、行くょヶ','\u034fょね\u0085行くょね'):
            with self.subTest(source=source):
                expected=[]
                with patch.object(M,'native_final_particle_tail',side_effect=lambda s:expected.append(s) or False):
                    for i,c in enumerate(source):
                        if c=='ょ':M._small_particle_tail_possible(source,i)
                actual=[]
                with patch.object(M,'native_final_particle_tail',side_effect=lambda s:actual.append(s) or False),patch.object(M,'_tokenize_janome',side_effect=AssertionError('no proof')):
                    self.assertEqual(M.colloquial_particle_normal_form(source),source)
                self.assertEqual(actual,expected)
    def test_cancel_during_whole_normalization_is_checked_before_native_or_publication(self):
        native=M.katakana_to_hiragana
        for source in ('行くょネ','行くょ資料'):
            with self.subTest(source=source):
                self.setUp();cancelled=[False]
                def normalize(text):
                    result=native(text)
                    if text==source:cancelled[0]=True
                    return result
                with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(M,'katakana_to_hiragana',side_effect=normalize),patch.object(M,'dictionary_prefix_paradigms',side_effect=AssertionError('stale native query')),patch.object(M,'_tokenize_janome',side_effect=AssertionError('stale whole tokenize')):
                    with self.assertRaises(SupersededAnalysis):M.colloquial_particle_normal_form(source)
                self.assertEqual(M.colloquial_particle_normal_form.cache_info().currsize,0)


if __name__=='__main__':unittest.main()
