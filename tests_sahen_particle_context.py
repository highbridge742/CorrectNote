# -*- coding: utf-8 -*-
"""A noun/suru proof may not silently discard a coordinating particle."""
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('保存'),'requires native dictionary')
class SahenParticleContextTests(unittest.TestCase):
    def test_native_focus_and_result_particles_still_connect(self):
        for text in ('ほぞんはします','ほぞんもします','ほぞんこそします',
                     'ほぞんさえします','ほぞんにします','ほぞんとします'):
            with self.subTest(text=text):self.assertTrue(R.completed_sahen_reading(text))

    def test_actual_coordination_or_question_does_not_borrow_another_pos(self):
        for text in ('ほぞんやします','かくにんやします','ほぞんかします','にゅうりょくかします'):
            with self.subTest(text=text):self.assertFalse(R.completed_sahen_reading(text))
        self.assertFalse(R.completed_native_reading_sequence('しゃしんをえらんでほぞんやします'))
        self.assertTrue(R.completed_native_reading_sequence('しゃしんをえらんでほぞんします'))

    def test_corrected_sequence_drops_the_adjacent_intrusion_instead(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        result=app.correct_line('しゃしんをえらんでほぞんゃします。',a.store,input_method='kana',
            dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],'しゃしんをえらんでほぞんします。')
        self.assertEqual(result.get('odd_spans'),[])
        for text in ('保存や検索をします。','入力もします。','保存にします。',
                     '「保存やします」と書かれています。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
