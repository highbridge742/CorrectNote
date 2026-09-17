# -*- coding: utf-8 -*-
"""A source sequence keeps the same proof inside original clause boundaries."""
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('決する'), 'requires native dictionary')
class SourceSequenceRangeTests(unittest.TestCase):
    def test_adverb_and_native_finite_connector_keep_a_complete_sequence(self):
        for text in ('かいてはけっします', 'まずかんがえてはけっします',
                     'かんがえてはけっしますが', 'まずかんがえてはけっしますが'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_source_sequence(text))
                self.assertTrue(R.intact_native_reading(text))
        for text in ('はけっします', 'まずかくてはけっします',
                     'かんがえてはけっするます', 'かんがえてはけっしますです',
                     'しらゆほかんがえてはけっします', 'ほんをたべてはけっします'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_source_sequence(text))

    def test_original_ranges_stop_at_quotes_punctuation_and_unproved_neighbors(self):
        phrase='かいてはけっします'
        for before,after in (('「','」と書きました。'), ('前の文。','。不明な後続。'),
                             ('説明\t','\tしらゆほます'), ('（','）')):
            text=before+phrase+after
            with self.subTest(text=text):
                self.assertIn((len(before),len(before)+len(phrase)),R.native_context_ranges(text))
                self.assertFalse(any(a<len(before) or b>len(before)+len(phrase)
                                     for a,b in R.native_context_ranges(text)))
        text='かんがえてはけっしますが、しらゆほます。'
        self.assertIn((0,text.index('、')),R.native_context_ranges(text))
        self.assertFalse(any(b>text.index('、') for a,b in R.native_context_ranges(text)))

    def test_application_preserves_wrapped_source_and_still_repairs_typos(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('「かいてはけっします」と書きました。',
                     'まずかんがえてはけっします。',
                     'かんがえてはけっしますが、まだまよいます。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])
        text='かいてはけしなます。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],'かいては消します。')
        self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
