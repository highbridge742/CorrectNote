# -*- coding: utf-8 -*-
"""VocabularyStore.save_in_background (2026-10-18): the same file as save(),
written off the UI thread, from the contents at the call, never overwriting a
newer save, and still through a temporary file."""
import os
import tempfile
import unittest

import vocabulary
from vocabulary import VocabularyStore


def store():
    s = VocabularyStore()
    s.add('としょかん', '図書館', 'test')
    s.add('しりょう', '資料', 'test')
    s.add('しりょう', '資料', 'test')        # solid
    return s


class BackgroundSaveTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, 'vocabulary.json')

    def read(self, path=None):
        with open(path or self.path, 'rb') as f:
            return f.read()

    def test_same_bytes_as_save(self):
        s = store()
        s.save(self.path)
        expected = self.read()
        os.remove(self.path)
        s.save_in_background(self.path).join(30)
        self.assertEqual(self.read(), expected)
        self.assertFalse(os.path.exists(self.path + '.tmp'))
        loaded = VocabularyStore(self.path)
        loaded.load()
        self.assertEqual(loaded.to_list(), VocabularyStore.to_list(s))

    def test_written_from_the_contents_at_the_call(self):
        s = store()
        with vocabulary._SAVE_LOCK:          # the writer waits
            thread = s.save_in_background(self.path)
            s.add('かいぎ', '会議', 'test')   # changed after the call
        thread.join(30)
        written = VocabularyStore(self.path)
        written.load()
        self.assertFalse(written.lookup('かいぎ'))
        self.assertTrue(written.lookup('としょかん'))

    def test_an_older_background_save_never_overwrites_a_newer_save(self):
        s = store()
        with vocabulary._SAVE_LOCK:          # the background writer is held back
            thread = s.save_in_background(self.path)
            s.add('かいぎ', '会議', 'test')
            s.save(self.path)                # newer contents (the close path)
        thread.join(30)
        written = VocabularyStore(self.path)
        written.load()
        self.assertTrue(written.lookup('かいぎ'))

    def test_without_a_path_nothing_is_written(self):
        self.assertIsNone(store().save_in_background())


if __name__ == '__main__':
    unittest.main()
