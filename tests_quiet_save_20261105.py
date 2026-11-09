# -*- coding: utf-8 -*-
"""A file that already holds the same text is not written again (2026-11-05). No window."""
import json
import os
import tempfile
import unittest

import analysis_cache
import file_same
import session


class Same(unittest.TestCase):
    def test_same_text(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.txt')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('語\n次\n')
            self.assertTrue(file_same.same(p, '語\n次\n'))
            self.assertFalse(file_same.same(p, '語\n次'))
            self.assertFalse(file_same.same(p, '語\n他\n'))
            self.assertFalse(file_same.same(os.path.join(d, 'none'), ''))

    def test_session_not_written_again_even_after_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 's.json')
            a = session.SessionStore(p)
            a.tabs = [session.new_tab(text='語\n次')]
            self.assertTrue(a.save())
            os.utime(p, (1000, 1000))
            b = session.SessionStore(p)
            b.tabs = a.tabs; b.active = a.active
            self.assertTrue(b.save())
            self.assertEqual(os.path.getmtime(p), 1000)
            b.tabs = [session.new_tab(text='別')]
            self.assertTrue(b.save())
            self.assertNotEqual(os.path.getmtime(p), 1000)

    def test_analysis_file_not_written_again(self):
        row = dict(original='あ', corrected='あ', changed=False, details=[], spans=[], unsure_spans=[], original_spans=[], odd_spans=[], odd_reasons=[])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'c.json')
            self.assertTrue(analysis_cache.save(p, {'k': 1}, {'あ': [row]}))
            os.utime(p, (1000, 1000))
            self.assertTrue(analysis_cache.save(p, {'k': 1}, {'あ': [row]}))
            self.assertEqual(os.path.getmtime(p), 1000)
            self.assertIn('あ', analysis_cache.load_all(p, {'k': 1})[0])


if __name__ == '__main__':
    unittest.main()
