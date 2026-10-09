import unittest
from contextlib import contextmanager
from unittest.mock import patch
import corrector as C,ime_homophone as H
from tests_analysis_async import initial
from last_choice import set_active

@contextmanager
def search_fixture(available,hits=()):
    class Search:
        def __init__(self):self.available=available
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def candidates(self,reading):return hits
    with patch('ime_candidates.SearchCandidates',Search):yield

class ReadingEvidence:
    """Only the external service boundary; dictionary and meaning stay real."""
    def __init__(self,prefix,prefix_reading,reading='かえします'):
        self.prefix=prefix;self.prefix_reading=prefix_reading;self.reading=prefix_reading+reading
    def reverse_words(self,first):
        import morphology as M
        head=next((p for p in M.tokenize(first) if p.start==len(self.prefix)),None)
        if not head:return None
        # The original native boundary is the same service descriptor used
        # by the production helper; other descriptors are irrelevant here.
        return self.reading,((len(self.prefix),head.end,len(self.prefix_reading),len(self.prefix_reading)+len(head.reading),203,3),)
    def phonetic(self,surface):
        import morphology as M
        return ''.join(p.reading for p in M.tokenize(surface))

class SuppliedHomophoneEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=initial();cls.tk=staticmethod(C.make_tokenizer(cls.a.store))
    @classmethod
    def tearDownClass(cls):set_active(None)
    def resolve(self,source,first,reading,supplied=(),ime=None):
        return H.positive_predicate_alternatives(source,first,reading,self.tk,
            ime or ReadingEvidence('本を図書館に','ほんをとしょかんに'),supplied=supplied)
    def test_supplied_candidate_keeps_same_proof_with_or_without_search(self):
        got=[]
        for available,hits in ((False,()),(True,()),(True,('返します','還します'))):
            with search_fixture(available,hits):
                got.append(self.resolve('本を図書館にかぇします','本を図書館に還します',
                    'ほんをとしょかんにかえします',('本を図書館に返します',)))
        self.assertEqual(got[0],got[1]);self.assertEqual(got[0],got[2])
        self.assertEqual(len(got[0]),1)
        surface,noun,proof=got[0][0]
        self.assertEqual((surface,noun),('本を図書館に返します','本'))
        self.assertEqual(proof['shared_roles'],['text'])
        with search_fixture(False):
            self.assertEqual(self.resolve('本を図書館にかぇします','本を図書館に還します',
                'ほんをとしょかんにかえします'),())
    def test_supplied_candidate_needs_its_original_prefix_and_reading(self):
        with search_fixture(False):
            for supplied in ('本を学校に返します','本を図書館に渡します','本を図書館に返した',
                             '本を図書館に返します\t別欄'):
                with self.subTest(supplied=supplied):
                    self.assertEqual(self.resolve('本を図書館にかぇします','本を図書館に還します',
                        'ほんをとしょかんにかえします',(supplied,)),())
            self.assertEqual(self.resolve('本を学校にかぇします','本を図書館に還します',
                'ほんをとしょかんにかえします',('本を図書館に返します',)),())
            self.assertEqual(self.resolve('本を図書館にかぇします','本を図書館に還します',
                'ほんをとしょかんにかえした',('本を図書館に返します',)),())
    def test_supplied_candidate_needs_positive_source_arguments_in_same_field(self):
        with search_fixture(False):
            for prefix,reading in (('ぷねらに','ぷねらに'),('本を図書館に\t','ほんをとしょかんに\t')):
                with self.subTest(prefix=prefix):
                    self.assertEqual(self.resolve(prefix+'かぇします',prefix+'還します',reading+'かえします',
                        (prefix+'返します',),ReadingEvidence(prefix,reading)),())
            # A supported first conversion still closes this alternative path.
            self.assertEqual(self.resolve('本を図書館にかぇします','本を図書館に返します',
                'ほんをとしょかんにかえします',('本を図書館に還します',)),())
    def test_supplied_candidate_uses_other_existing_source_noun_and_case(self):
        prefix='資料を先生に';reading='しりょうをせんせいに'
        with search_fixture(False):
            result=self.resolve(prefix+'かぇします',prefix+'還します',reading+'かえします',
                (prefix+'返します',),ReadingEvidence(prefix,reading))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0][0],prefix+'返します')
        self.assertEqual(result[0][1],'資料')
        self.assertTrue(result[0][2]['shared_roles'])

class SuppliedHomophoneRuntimeTests(unittest.TestCase):
    def test_unavailable_search_keeps_supplied_spelling_and_common_gate(self):
        import app
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Japanese IFELanguage unavailable')
        real_convert=JapaneseIME.convert
        def first(self,reading):
            return '本を図書館に還します' if reading=='ほんをとしょかんにかえします' else real_convert(self,reading)
        state=initial();seen=[];gate=C._check_replacement
        def observed(*args,**kwargs):
            result=gate(*args,**kwargs)
            if '返' in str(args[1]):seen.append((args[0],args[1],result))
            return result
        def correct(source):
            return app.correct_line(source,state.store,dict_index=state.dict_index,
                decisions=state.decisions,context_vec=None,input_method='kana')
        try:
            with search_fixture(False),patch.object(JapaneseIME,'convert',first):
                source='本を図書館にかぇします\tメモ'
                with patch.object(C,'_check_replacement',observed):result=correct(source)
                self.assertEqual(result['corrected'],'本を図書館に返します\tメモ')
                self.assertEqual(result.get('odd_spans'),[])
                self.assertEqual(result.get('analysis_status'),'complete')
                self.assertTrue(any(text==source and accepted[0] is not None
                    for text,edit,accepted in seen))
                written='本を図書館に還します\tメモ'
                self.assertEqual(correct(written)['corrected'],written)
                with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')) as denied:
                    result=correct(source)
                self.assertEqual(result['corrected'],source)
                self.assertTrue(denied.called)
        finally:set_active(None)

if __name__=='__main__':unittest.main()
