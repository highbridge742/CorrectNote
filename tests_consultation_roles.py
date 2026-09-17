# -*- coding: utf-8 -*-
"""The topic discussed is distinct from the person consulted."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('相談'),'requires native dictionary')
class ConsultationRoleTests(unittest.TestCase):
    def test_topics_share_meaning_across_native_discussion_actions(self):
        for topic in ('日程','予定','計画','方針','問題'):
            for action in ('相談','協議','議論','検討','審議'):
                with self.subTest(topic=topic,action=action):
                    self.assertTrue(S.support(topic,action))
        proof=S.candidate_evidence('日程','相談','しました',before='旅行の日程を')
        self.assertTrue(proof and proof['shared_roles'])
        self.assertTrue(S.candidate_evidence('先生','相談','します',before='先生に',case='に')['shared_roles'])
        self.assertFalse(S.support('しらゆほ','相談'))

    def test_initial_import_ranks_the_schedule_reading_without_touching_cutting(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        for source,expected in (
                ('旅行の日程をさ宇弾しました。','旅行の日程を相談しました。'),
                ('旅行の日程を相談しました。','旅行の日程を相談しました。'),
                ('布を裁断します。','布を裁断します。'),
                ('書類を裁断します。','書類を裁断します。'),
                ('先生に相談します。','先生に相談します。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=a.context_vec,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
