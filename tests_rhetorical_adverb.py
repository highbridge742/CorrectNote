# -*- coding: utf-8 -*-
"""A rhetorical adverb cannot be ignored to certify an arbitrary repair."""
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('豈'),'requires native dictionary')
class RhetoricalAdverbTests(unittest.TestCase):
    def test_rhetorical_word_is_not_an_unconditional_adverb(self):
        for face in ('あに','豈'):
            self.assertTrue(S.adverbial_reading_needs_host(face,'あに'))
        self.assertEqual(R._native_adverbial_faces('あに'),())
        self.assertNotIn(2,R.native_adverbial_reading_cuts('あにさてたなにもどします'))
        self.assertFalse(R.native_object_predicate_proof('しょっきをあにさてたなにもどします',5,('食器',)))
        self.assertTrue(R.native_object_predicate_proof('しょっきをあらってたなにもどします',5,('食器',)))

    def test_same_key_shift_restores_a_complete_linked_predicate(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        result=app.correct_line('しょっきをあらつてたなにもどします。',a.store,input_method='kana',
            dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
        self.assertIn(result['corrected'],('しょっきをあらってたなにもどします。','食器を洗ってたなに戻します。'))
        self.assertEqual(result.get('odd_spans'),[])
        # さ→っ requires a different key and Shift; keep this old case unresolved.
        unresolved='しょっきをあらさてたなにもどします。'
        result=app.correct_line(unresolved,a.store,input_method='kana',dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],unresolved)
        self.assertTrue(result.get('odd_spans'))
        for text in ('しょっきをあらってたなにもどします。','さてほんをよみます。',
                     '豈図らんや。','あにはからんや。','「あに」と書きます。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
