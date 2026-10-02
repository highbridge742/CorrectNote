# -*- coding: utf-8 -*-
import unittest


from morphology import HAS_JANOME

@unittest.skipUnless(HAS_JANOME, "Requires real Janome; run with the native integration suite")
class MarkClusterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state=initial()

    def test_lexical_repair_consumes_its_voiced_host_marks(self):
        import app
        s=self.state
        for source,expected in [('荷物をはコンテ゜゛から休みます。','荷物を運んでから休みます。'),
                                ('荷物をはこんて゜゛から休みます。','荷物を運んでから休みます。'),
                                ('荷物を運んで゜゛から休みます。','荷物を運んでから休みます。'),
                                ('運んで゛゜から置く','運んでから置く'),
                                ('濁点は゛゜です','濁点は゛゜です'),
                                ('「か゛゜めん」という文字列','「か゛゜めん」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))


    def test_native_adjective_and_polite_tail_share_completion(self):
        import app
        from contextual_repair import _allows_grammatical_tail
        from morphology import dictionary_inflections
        s=self.state
        for source,expected in [('すごい゛゜ですね','すごいですね'),
                                ('高い゛゜です','高いです'),
                                ('高い゛゜にする','高い゛゜にする'),
                                ('「高い゛゜」という文字列','「高い゛゜」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertEqual('complete',r.get('analysis_status'))
        forms=dictionary_inflections('高い')
        self.assertTrue(_allows_grammatical_tail(forms,'ですね','たかい','高い'))
        self.assertFalse(_allows_grammatical_tail(forms,'にする','たかい','高い'))
        self.assertFalse(_allows_grammatical_tail(forms,'ます','たかい','高い'))


    def test_cluster_voicing_respects_native_predicate_inflection(self):
        import app
        from contextual_repair import _allows_grammatical_tail
        from morphology import dictionary_inflections
        s=self.state
        for source,expected in [('高かった゛゜です','高かったです'),
                                ('箱に入れて゜゛から閉じる','箱に入れてから閉じる'),
                                ('寒かった゜゛ですね','寒かったですね'),
                                ('赤かった゛゜ので驚いた','赤かったので驚いた'),
                                ('開けて゛゜ください','開けてください'),
                                ('泳いて゛゜から休む','泳いでから休む'),
                                ('よんて゛゜から戻る','読んでから戻る'),
                                ('「入れて゜゛」という文字列','「入れて゜゛」という文字列'),
                                ('う゛う゛と唸る','う゛う゛と唸る'),
                                ('高かったです','高かったです')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))
        forms=dictionary_inflections('高かっ')
        self.assertTrue(_allows_grammatical_tail(forms,'たです','たかかっ','高かっ'))
        self.assertFalse(_allows_grammatical_tail(forms,'だです','たかかっ','高かっ'))
        self.assertFalse(_allows_grammatical_tail(forms,'たます','たかかっ','高かっ'))

    def test_native_past_seam_resolves_its_original_neighbor(self):
        import app
        s=self.state
        for source,expected in [('待った゛゜ら呼んで','待ったら呼んで'),
                                ('食べた゛゜あとに休む','食べたあとに休む'),
                                ('書いた゛゜本を開く','書いた本を開く'),
                                ('食べた゛゜ものを片付ける','食べたものを片付ける'),
                                ('待った゛゜','待った'),
                                ('泳いて゛゜から休む','泳いでから休む'),
                                ('「食べた゛゜あと」という文字列','「食べた゛゜あと」という文字列'),
                                ('待ったら呼んで','待ったら呼んで')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_lagged_voicing_consumes_equivalent_mark_glyphs(self):
        import app
        s=self.state
        for source,expected in [('硬い゛゜に取り掛かる','課題に取り掛かる'),
                                ('硬いﾞﾟに取り掛かる','課題に取り掛かる'),
                                ('硬い゙゚に取り掛かる','課題に取り掛かる'),
                                ('かたい゛゜に取り掛かる','課題に取り掛かる'),
                                ('硬い゛゜に取り掛かる	硬い石を拾う','課題に取り掛かる	硬い石を拾う'),
                                ('「硬い゛゜」という文字列','「硬い゛゜」という文字列'),
                                ('硬い石を拾う','硬い石を拾う'),
                                ('課題に取り掛かる','課題に取り掛かる')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))
