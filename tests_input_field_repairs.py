# -*- coding: utf-8 -*-
"""Independent fields retain their source grammar and physically justified edits."""
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
from unittest.mock import patch
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class InputFieldRepairTests(unittest.TestCase):
    def test_native_noun_use_requires_both_dictionary_entries(self):
        from reading_segments import native_deverbal_nominal_faces
        for reading,word in [('さしこみ','差し込み'),('おしこみ','押し込み'),('かきこみ','書き込み')]:
            self.assertIn(word,native_deverbal_nominal_faces(reading))
        for reading in ('ぷねら','たべ','さしこん','しゅうありょう'):
            self.assertFalse(native_deverbal_nominal_faces(reading))

    def test_closed_adnominal_and_comparison_frames_precede_key_search(self):
        import particle_frames as P
        with patch('kana_layout.single_key_drop_adjacency',side_effect=AssertionError('key search before source evidence')):
            self.assertFalse(P.adnominal_topic_frames('きりがないようなも\t'))
            self.assertTrue(P.interrupted_comparison_frames('ほかのぎょうとえおなじ'))
            self.assertTrue(P.interrupted_comparison_frames('ほかのぎょうとえおなじです。'))
        for text in ('きりがないようなも','きりがないようなもの\t','静かなものです。',
                     '「きりがないようなも」と入力します。'):
            self.assertFalse(P.adnominal_topic_frames(text),text)
        for text in ('ほかのぎょうとおなじ','ほかのぎょうとえ、同じ','未知蒟とえおなじ',
                     '「ほかのぎょうとえおなじ」と入力します。'):
            self.assertFalse(P.interrupted_comparison_frames(text),text)

    def test_two_initial_states_repair_each_field_without_an_answer(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        from last_choice import set_active
        for phase in ('seed','fresh'):
            a=initial();a.context_vec=None
            if phase=='fresh':import_from_janome(a.store)
            revision=a.store.revision()
            try:
                pairs=[('にゅうりょくちゃう','入力中'),('もーしろょん','モーション'),
                       ('もーしょろん','モーション'),('つたえふたことで','伝えたことで'),
                       ('ほかのぎょうとえおなじ','他の行と同じ'),
                       ('差し込み゛手、','差し込みで、'),('さしこみ゛て、','差し込みで、'),
                       ('おしこみ゛て、','押し込みで、'),('かきこみ゛て、','書き込みで、'),
                       ('入力茶う\t','入力中\t')]
                for source,expected in pairs:
                    with self.subTest(phase=phase,source=source):
                        result=app.correct_line(source,a.store,dict_index=a.dict_index,decisions=a.decisions,
                                                context_vec=None,input_method='kana')
                        assert_reviewed_source_spelling(self, result['corrected'], expected)
                        self.assertEqual(result.get('odd_spans'),[])
                # A column terminator cannot distinguish 藻/歯 from particles.
                for source in ('このようなも\t','雪のようなは\t','うれしー','だょー','しちゃうょー','入力しちゃう。','ご入力ください。',
                               '誤入力したキー','「もーしろょん」と入力します。','差し込みで、'):
                    with self.subTest(phase=phase,keep=source):
                        assert_reviewed_source_spelling(self, app.correct_line(source,a.store,dict_index=a.dict_index,
                            decisions=a.decisions,context_vec=None,input_method='kana')['corrected'], source)
                # The existing source-only frame check above finds no anomaly.
                # A column terminator cannot choose 藻 vs も or manufacture に.
                self.assertEqual(app.correct_line('きりがないようなも\t',a.store,dict_index=a.dict_index,decisions=a.decisions,context_vec=None,input_method='kana')['corrected'],'きりがないようなも\t')
                # A malformed later field does not freeze the independently proved use sense.
                for source,expected in (('ご連絡した件','ご連絡した件'),
                        ('私用した道具を片付け魔訶。','使用した道具を片付け魔訶。')):
                    with self.subTest(phase=phase,source=source):
                        result=app.correct_line(source,a.store,dict_index=a.dict_index,
                            decisions=a.decisions,context_vec=None,input_method='kana')
                        assert_reviewed_source_spelling(self, result['corrected'], expected)
                        if source=='ご連絡した件':self.assertEqual(result.get('odd_spans'),[])
                for source,expected in (('寒ぃ日です。','寒い日です。'),('大きぃ箱です。','大きい箱です。')):
                    with self.subTest(phase=phase,source=source):
                        result=app.correct_line(source,a.store,dict_index=a.dict_index,
                            decisions=a.decisions,context_vec=None,input_method='kana')
                        assert_reviewed_source_spelling(self, result['corrected'], expected)
                        self.assertEqual(result.get('odd_spans'),[])
                self.assertEqual(a.store.revision(),revision)
            finally:set_active(None)

if __name__=='__main__':unittest.main()