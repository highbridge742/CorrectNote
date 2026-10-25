# -*- coding: utf-8 -*-
"""Where the reading lattice keeps its table, and the analysis child loading it before the first line (2026-10-25).

The table (reading_lattice_table.pickle.gz, about 4MB, about 3.7s to make) goes to the app's data folder, which
app.main hands down as CORRECTNOTE_DATA_DIR (beside the exe, or the package's own folder under MSIX, whose install
folder is read-only); a frozen build without it uses the temp folder; from source, beside the module. The worker's
'warmup' task reads a saved one while no line is waiting and never makes it (making it empties a DictIndex built
later in the same process); a failure there changes nothing.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import reading_lattice


def _child(code):
    import subprocess
    r = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', code], cwd=os.path.dirname(os.path.abspath(__file__)),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=120)
    assert r.returncode == 0, r.stdout
    return r.stdout.strip().splitlines()[-1]


class CachePathTests(unittest.TestCase):
    def test_data_dir_from_the_app(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'CORRECTNOTE_DATA_DIR': d}):
            self.assertEqual(reading_lattice.default_cache_path(), os.path.join(d, reading_lattice.CACHE_NAME))

    def test_frozen_without_it_uses_the_temp_folder(self):
        env = {k: v for k, v in os.environ.items() if k != 'CORRECTNOTE_DATA_DIR'}
        with patch.dict(os.environ, env, clear=True), patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(reading_lattice.default_cache_path(),
                             os.path.join(tempfile.gettempdir(), reading_lattice.CACHE_NAME))

    def test_from_source_beside_the_module(self):
        env = {k: v for k, v in os.environ.items() if k != 'CORRECTNOTE_DATA_DIR'}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(os.path.dirname(reading_lattice.default_cache_path()),
                             os.path.dirname(os.path.abspath(reading_lattice.__file__)))

    def test_a_folder_that_cannot_be_written_still_loads(self):
        # made in a child process: making the table here would leave this process's next DictIndex empty
        code = (
            "import os, tempfile, reading_lattice as rl\n"
            "d = tempfile.mkdtemp(); blocker = os.path.join(d, 'file'); open(blocker, 'w').close()\n"
            "rl.load(cache_path=os.path.join(blocker, rl.CACHE_NAME))\n"
            "print(rl._table is not None, rl.best('がいこくのりょうり').surface)\n")
        self.assertEqual(_child(code), 'True 外国の料理')


class ReadOnlyLoadTests(unittest.TestCase):
    """build=False (the warmup): a saved table is read, a missing one is not made (making it reads
    janome.sysdic.entries(), after which a DictIndex built in the same process comes out empty)."""

    def setUp(self):
        self.saved = reading_lattice._table, reading_lattice._trie, reading_lattice._conn
        reading_lattice._table = None

    def tearDown(self):
        reading_lattice._table, reading_lattice._trie, reading_lattice._conn = self.saved

    def test_no_saved_table_is_not_made(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(reading_lattice, 'build_table', side_effect=AssertionError('built')):
            path = os.path.join(d, reading_lattice.CACHE_NAME)
            reading_lattice.load(cache_path=path, build=False)
            self.assertIsNone(reading_lattice._table)
            self.assertFalse(os.path.exists(path))

    def test_a_saved_table_is_read(self):
        # made (the first line's way) in a child process, then read here without making
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, reading_lattice.CACHE_NAME)
            _child('import reading_lattice as rl\nrl.load(cache_path=%r)\nprint(len(rl._table))' % path)
            with patch.object(reading_lattice, 'build_table', side_effect=AssertionError('built')):
                reading_lattice.load(cache_path=path, build=False)
            self.assertTrue(reading_lattice._table)


class WarmupTests(unittest.TestCase):
    def _warmup(self, load):
        import analysis_worker
        runtime = analysis_worker.Runtime()
        calls = []
        with patch.object(analysis_worker.Runtime, 'prepare_tables', lambda self: None), \
                patch('loanword._english_seed', lambda: None), patch('reading_likelihood._distributions', lambda: None), \
                patch('contextual_repair._native_written_nominal_readings', lambda: None), \
                patch('ngram_yomi._bigram_counts', lambda: None), patch('contextual_repair._seed_context', lambda: None), \
                patch.object(reading_lattice, 'load', lambda *a, **k: (calls.append(k), load())):
            return runtime.execute(dict(kind='warmup')), calls

    def test_warmup_reads_the_saved_lattice_without_making_it(self):
        result, calls = self._warmup(lambda: None)
        self.assertEqual(calls, [dict(build=False)])
        self.assertIn('ready', result)

    def test_a_failed_load_does_not_fail_the_warmup(self):
        def fail():
            raise OSError('no table')
        result, calls = self._warmup(fail)
        self.assertEqual(calls, [dict(build=False)])
        self.assertIn('ready', result)


if __name__ == '__main__':
    unittest.main()
