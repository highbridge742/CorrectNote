# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact tables (memory usage low) give exactly the ordinary answers."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

import compact_tables as C

HERE = Path(__file__).resolve().parent


class _TableForm:
    """Run a block with CN_COMPACT_TABLES set ('1') or unset (None), then restore
    whatever this process had (another test module may have exported it)."""
    def __init__(self, flag):
        self.flag = flag

    def __enter__(self):
        self.saved = os.environ.get(C.ENV)
        if self.flag is None:
            os.environ.pop(C.ENV, None)
        else:
            os.environ[C.ENV] = self.flag
        return self

    def __exit__(self, *exc):
        if self.saved is None:
            os.environ.pop(C.ENV, None)
        else:
            os.environ[C.ENV] = self.saved
        return False


class CompactShapeTests(unittest.TestCase):
    def test_words_answer_like_a_frozenset(self):
        words = C.CompactWords.of(['b', 'a', '', 'c'])
        self.assertEqual((len(words), sorted(words)), (4, ['', 'a', 'b', 'c']))
        for probe in ('', 'a', 'c', 'd', 'aa', '\n', None, 3):
            self.assertEqual(probe in words, probe in {'', 'a', 'b', 'c'} if isinstance(probe, str) else False)
        self.assertFalse(C.CompactWords.of([]))
        self.assertEqual(len(C.CompactWords.of([''])), 1)

    def test_pairs_and_costs_answer_like_dicts(self):
        table = {'x': [(1, 'a'), (2, 'b')], '': [(3, 'c')], 'y': [], '仮名': [(40, 'かな')]}
        pairs = C.CompactPairs.of(table)
        self.assertEqual(len(pairs), len(table))
        for key, value in table.items():
            self.assertEqual(pairs.get(key), value)
            self.assertIs(type(pairs.get(key)), list)
            self.assertIn(key, pairs)
        self.assertEqual(pairs.get('z', ()), ())
        self.assertIs(type(pairs.get('x')[0]), tuple)
        self.assertEqual(dict(pairs.items()), table)
        costs = C.CompactCosts.of({'b': 5, '': -1, '仮名': 40})
        self.assertEqual((costs.get(''), costs.get('b'), costs.get('仮名'), costs.get('q')), (-1, 5, 40, None))
        with self.assertRaises(KeyError):
            costs['q']

    def test_lists_and_tuples_answer_like_dicts_and_sets(self):
        table = {'あめ': ['雨', '飴'], '': [], 'x': [''], '仮名': ['かな', '仮名', 'カナ']}
        lists = C.CompactLists.of(table)
        self.assertEqual(len(lists), len(table))
        for key, value in table.items():
            self.assertEqual(lists.get(key), value, key)
            self.assertEqual(lists[key], value)
            self.assertIs(type(lists.get(key)), list)
            self.assertIn(key, lists)
        self.assertIsNone(lists.get('ない'))
        self.assertEqual(lists.get('ない', ()), ())
        self.assertNotIn('ない', lists)
        self.assertNotIn(3, lists)
        self.assertEqual(dict(lists.items()), table)
        self.assertEqual(sorted(lists), sorted(table))
        self.assertEqual(sorted(lists.keys()), sorted(table))
        self.assertEqual(sorted(map(tuple, lists.values())), sorted(map(tuple, table.values())))
        self.assertTrue(lists)
        self.assertFalse(C.CompactLists.of({}))
        with self.assertRaises(KeyError):
            lists['ない']
        with self.assertRaises(ValueError):
            C.CompactLists.of({'a': ['b\x01c']})
        with self.assertRaises(ValueError):
            C.CompactLists.of({'a': [1]})
        pairs = {('会', '議'), ('資', '料'), ('', '語')}
        tuples = C.CompactTuples.of(pairs)
        self.assertEqual(len(tuples), 3)
        self.assertEqual(set(tuples), pairs)
        for pair in pairs:
            self.assertIn(pair, tuples)
        for probe in (('会', '議', '室'), ('議', '会'), '会議', ('会',), None, ('会', 1)):
            self.assertNotIn(probe, tuples)
        self.assertFalse(C.CompactTuples.of([]))
        with self.assertRaises(ValueError):
            C.CompactTuples.of([('a', 'b'), ('c',)])

    def test_changed_or_absent_file_declines(self):
        missing = HERE / 'no_such_compact.bin.gz'
        self.assertIsNone(C.load_cost_tables(HERE / 'seed_japanese_cost.txt.gz', missing))


class CompactRealDataTests(unittest.TestCase):
    """Every key of the real tables, against the ordinary loaders."""
    def test_seed_words_are_the_same_words(self):
        from word_table import _read
        path = str(HERE / 'seed_japanese.txt.gz')
        with _TableForm(None):
            wide, narrow = _read(path)
        compact = C.words_from_seed(path)
        self.assertIsNotNone(compact)
        self.assertIs(compact[0], compact[1])
        self.assertIs(wide, narrow)
        self.assertEqual(len(compact[0]), len(wide))
        self.assertEqual(set(compact[0]), set(wide))

    def test_bundled_cost_file_equals_the_ordinary_tables(self):
        import corrector
        saved = (corrector._TABLE_READINGS, corrector._TABLE_COST, corrector._TABLE_SURFACES)
        try:
            corrector._TABLE_READINGS = corrector._TABLE_COST = corrector._TABLE_SURFACES = None
            with _TableForm(None):
                corrector._table_readings_for_surface('')
            ordinary = (corrector._TABLE_READINGS, corrector._TABLE_COST, corrector._TABLE_SURFACES)
        finally:
            corrector._TABLE_READINGS, corrector._TABLE_COST, corrector._TABLE_SURFACES = saved
        self.assertIs(type(ordinary[0]), dict)
        compact = C.load_cost_tables(HERE / 'seed_japanese_cost.txt.gz', HERE / C.FILE_NAME)
        self.assertIsNotNone(compact, 'bundled compact file or its pinned SHA-256 differs')
        for original, small in zip(ordinary, compact):
            self.assertEqual(len(small), len(original))
            for key, value in original.items():
                got = small.get(key)
                self.assertEqual(got, value, key)
                self.assertIs(type(got), type(value))

    def test_dict_index_cache_loads_compact_with_the_same_answers(self):
        import os
        from dict_index import DictIndex
        path = str(HERE / 'dict_index.json')
        if not os.path.exists(path):
            self.skipTest('dict_index.json is not in this folder')
        with _TableForm(None):
            ordinary = DictIndex(path)
            self.assertTrue(ordinary._load_cache())
        self.assertIs(type(ordinary._by_reading), dict)
        with _TableForm('1'):
            compact = DictIndex(path)
            self.assertTrue(compact._load_cache())
        self.assertIs(type(compact._by_reading), C.CompactLists)
        self.assertIs(type(compact._world), C.CompactWords)
        for name in ('_by_reading', '_by_surface', '_inflected'):
            small, original = getattr(compact, name), getattr(ordinary, name)
            self.assertEqual(len(small), len(original), name)
            for key, value in original.items():
                self.assertEqual(small.get(key), list(value), (name, key))
        self.assertEqual(len(compact._world), len(ordinary._world))
        self.assertEqual(set(compact._world), set(ordinary._world))
        self.assertEqual(len(compact._band), len(ordinary._band))
        for key, value in ordinary._band.items():
            self.assertEqual(set(compact._band.get(key)), set(value), key)
        for reading in ('ひらがな', 'かんむり', 'じ', 'ない'):
            self.assertEqual(compact.surfaces_for_reading(reading), ordinary.surfaces_for_reading(reading))
            self.assertEqual(compact.surfaces_for_reading(reading, band=False),
                             ordinary.surfaces_for_reading(reading, band=False))
            self.assertEqual(compact.inflected_surfaces_for_reading(reading),
                             ordinary.inflected_surfaces_for_reading(reading))
            self.assertEqual(compact.is_world_reading(reading), ordinary.is_world_reading(reading))
        for surface in ('時', '層', '平仮名', 'ない'):
            self.assertEqual(compact.readings_for_surface(surface), ordinary.readings_for_surface(surface))
        self.assertEqual(compact.resource_status, ordinary.resource_status)
        self.assertEqual({k: set(v) for k, v in compact._band.items()},
                         {k: set(v) for k, v in ordinary._band.items()})

    def test_compound_tables_load_compact_with_the_same_answers(self):
        import os
        from word_table import read_compound_tables
        path = str(HERE / 'seed_japanese.txt.gz')
        with _TableForm(None):
            ordinary = read_compound_tables(path)
        self.assertIsNotNone(ordinary, 'bundled compound tables differ from their pinned SHA-256')
        self.assertIs(type(ordinary[2]), set)
        with _TableForm('1'):
            compact = read_compound_tables(path)
        self.assertIs(type(compact[2]), C.CompactTuples)
        for small, original in zip(compact[:2], ordinary[:2]):
            self.assertEqual(len(small), len(original))
            for key, value in original.items():
                self.assertEqual(small.get(key, 0), value, key)
            self.assertEqual(small.get('ない', 0), 0)
        self.assertEqual(len(compact[2]), len(ordinary[2]))
        self.assertEqual(set(compact[2]), ordinary[2])
        for pair in list(ordinary[2])[:2000]:
            self.assertIn(pair, compact[2])
        self.assertNotIn(('会', '議', '室'), compact[2])

    def test_english_lexicon_compact_answers_like_the_frozenset(self):
        import os
        import subprocess
        code = ('import loanword,compact_tables as C;s=loanword._english_seed_all();'
                'import seed_english;print(type(s).__name__,len(s),"neighbours" in s,"zzzz" in s,'
                'len(getattr(seed_english,"EXTRA_WORDS",())))')
        out = {}
        for flag in ('1', None):
            env = dict(os.environ)
            env.pop(C.ENV, None)
            if flag:
                env[C.ENV] = flag
            run = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], cwd=str(HERE), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=300)
            out[flag] = run.stdout.strip().splitlines()[-1].split()
        self.assertEqual(out[None][0], 'frozenset')
        self.assertEqual(out['1'][0], 'CompactWords')
        self.assertEqual(out['1'][1:4], out[None][1:4])
        self.assertEqual(out['1'][2:4], ['True', 'False'])
        self.assertEqual(out['1'][4], '0')          # the read table is released in low
        self.assertNotEqual(out[None][4], '0')

    def test_worker_environment_switches_the_engine_tables(self):
        # The flag is read in the process that loads the tables (the worker).
        code = ('import corrector,compact_tables as C;corrector._table_readings_for_surface("");'
                'import word_table;w,_=word_table.read_word_sets("seed_japanese.txt.gz");'
                'print(type(corrector._TABLE_READINGS).__name__,type(w).__name__)')
        for flag, expected in (('1', 'CompactPairs CompactWords'), (None, 'dict frozenset')):
            env = dict(os.environ)
            env.pop(C.ENV, None)
            if flag:
                env[C.ENV] = flag
            out = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], cwd=str(HERE), env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8',
                                 timeout=300)
            self.assertEqual(out.stdout.strip().splitlines()[-1], expected, out.stdout)


if __name__ == '__main__':
    unittest.main()
