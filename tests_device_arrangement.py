# -*- coding: utf-8 -*-
"""A physical device can be arranged or stored, not borrowed as food or text."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('機械'),'requires native dictionary')
class DeviceArrangementTests(unittest.TestCase):
    def test_actual_device_roles_support_placement_and_storage_only(self):
        for action in ('並べる','整列','整理','運搬','保管','収納'):
            with self.subTest(action=action):self.assertTrue(S.support('機械',action))
        for action in ('読む','食べる'):
            with self.subTest(action=action):self.assertFalse(S.support('機械',action))
        for noun in ('機会','奇怪'):
            self.assertFalse(S.support(noun,'並べる'))

    def test_initial_application_uses_the_same_roles_for_source_and_candidate(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (('んかいをにだいならべます。','機械をにだいならべます。'),
                                 ('きかいをにだいならべます。','きかいをにだいならべます。'),
                                 ('きかいをほかんします。','きかいをほかんします。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
