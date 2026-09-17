# -*- coding: utf-8 -*-
"""Source focus links and actual auxiliary identity share native evidence."""
import unittest
from dataclasses import replace
import morphology as M
import reading_segments as R
import contextual_repair as C

@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class FocusedSequenceTests(unittest.TestCase):
    def test_completed_focus_links_and_independent_clauses(self):
        for text in ('かいては','よんでは','かいても','ほんをよんでは'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_reading_link(text))
        for text in ('かくては','よみでは','しらゆほては','ては','かいてはは'):
            with self.subTest(text=text):self.assertFalse(R.completed_native_reading_link(text))
        for text in ('かいてはけします','よんでもかきます','てがみをかいてはけします'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_reading_sequence(text))
        for text in ('かいてはしらゆほます','かくてはけします','よみではかきます',
                     'かいてはけしますです','かいてはけしま'):
            with self.subTest(text=text):self.assertFalse(R.completed_native_reading_sequence(text))

    def test_actual_auxiliary_does_not_borrow_homographic_verb(self):
        import oddness
        def legacy(t):
            return (t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                    t.reading,t.start,t.end,t.has_reading,t.infl_form)
        parts=M.tokenize('かいて吐けなします')
        self.assertTrue(oddness.polite_aux_mismatch(legacy(parts[-2]),legacy(parts[-1])))
        self.assertFalse(C._productive_predicate('吐けなします','吐け',before='かいて'))
        for text in ('読み続けます','寝させます','読まれます','読みます','なくします'):
            with self.subTest(text=text):
                head=M.tokenize(text)[0]
                self.assertTrue(C._productive_predicate(text,head.surface))

    def test_verb_type_auxiliary_keeps_its_native_continuative_form(self):
        import oddness
        def legacy(t):
            return (t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                    t.reading,t.start,t.end,t.has_reading,t.infl_form)
        for text in ('ございません','ございませんでした','であります','ではありません'):
            parts=M.tokenize(text)
            for left,right in zip(parts,parts[1:]):
                with self.subTest(text=text,left=left.surface):
                    self.assertFalse(oddness.polite_aux_mismatch(legacy(left),legacy(right)))
        # A different verb sharing the spelling must still not license these.
        for text in ('かいて吐けなします','ござるます','書きまします','書きでします'):
            parts=M.tokenize(text)
            with self.subTest(text=text):
                self.assertTrue(any(oddness.polite_aux_mismatch(legacy(a),legacy(b))
                                    for a,b in zip(parts,parts[1:])))

    def test_source_keeps_focus_and_rejects_ungrammatical_generated_spelling(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('かいてはけします。','よんでもかきます。','かいてはみます。',
                     'よんでもらいます。','ございません。','ございませんでした。',
                     'であります。','ではありません。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],text);self.assertEqual(r['odd_spans'],[])
        # Existing incomplete lexical coverage may still mark 手筈; the
        # connective rule must not alter that whole lexical spelling.
        text='てはずをかくにんします。'
        r=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(r['corrected'],text)
        text='かいてはけしなます。'
        r=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        # AHR supplies the original focus edge; AHH's incomplete hold is superseded.
        self.assertEqual(r['corrected'],'かいては消します。')
        self.assertEqual(r['odd_spans'],[])


    def test_native_focus_edges_require_actual_euphony(self):
        for text,edge in (('かいてはけしなます',4),('読んでも書きなます',4),
                           ('書いては消しなます',4)):
            with self.subTest(text=text):self.assertIn(edge,C._native_focused_te_edges(text))
        for text in ('読むてもかきます','よみではかきます','泳いてはけします','ぬぉてはけします'):
            with self.subTest(text=text):self.assertEqual(C._native_focused_te_edges(text),())

    def test_swallowed_focus_keeps_original_anomaly_and_wide_interpretation(self):
        text='かいてはけしなます'
        target=C.RepairTarget(text,3,7,0,len(text),(('しな','ます',5,9),),True,text[7:])
        targets=C._native_focused_prefix_targets([target])
        self.assertIn(target,targets)
        narrow=next(t for t in targets if t.start==4)
        self.assertEqual(narrow.text,'けしな')
        self.assertEqual(narrow.anomalies,target.anomalies)
        self.assertEqual(narrow.context,target.context)
        self.assertEqual(C._native_focused_prefix_targets(targets),targets)
        for blocked in (replace(target,anomalies=(('は','け',3,5),)),
                        replace(target,preserved_head='はけ'),replace(target,spelling=('source-fact',)),
                        replace(target,boundary_kind='kana_request')):
            with self.subTest(target=blocked):
                self.assertEqual(C._native_focused_prefix_targets([blocked]),[blocked])

    def test_complete_words_after_connective_keep_their_original_text(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('書いてはけを洗います。','読んでものを考えます。',
                     'よんでものをかんがえます。','はしってはころびます。',
                     '食べても空腹です。','あそんでもねむくありません。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])

if __name__=='__main__':unittest.main()

