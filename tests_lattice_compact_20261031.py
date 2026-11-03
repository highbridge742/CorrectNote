# -*- coding: utf-8 -*-
"""読みの格子（reading_lattice）の表と木は、compact_tables の形で持つ（2026-10-31・子1つで約290MB少ない）。
答えは同じ: 同じ読みに同じ語が同じ並びで在り、best() の道も費用も同じ。CN_PLAIN_TABLES=1 で dict と木に戻る。"""
import json
import os
import subprocess
import sys
import unittest

import compact_tables

HERE = os.path.dirname(os.path.abspath(__file__))
PICKLE = os.path.join(HERE, 'reading_lattice_table.pickle.gz')


class CompactLatticeShapeTests(unittest.TestCase):
    TABLE = {'か': [('蚊', 10, 11, 500, '名詞'), ('可', 12, 12, -30, '接頭詞')],
             'かな': [('仮名', 1, 2, 3000, '名詞')],
             'がっこう': [('学校', 1315, 1315, 19888, '名詞')]}

    def test_the_same_values_in_the_same_order(self):
        small = compact_tables.CompactLattice.of(self.TABLE)
        for key, value in self.TABLE.items():
            self.assertEqual(list(small[key]), value)
            self.assertEqual(list(small.get(key)), value)
            self.assertIn(key, small)
        self.assertEqual(small.get('ない', ()), ())
        self.assertNotIn('ない', small)
        with self.assertRaises(KeyError):
            small['ない']
        self.assertEqual(sorted(small), sorted(self.TABLE))
        self.assertEqual(len(small), 3)

    def test_the_saved_state_comes_back_the_same(self):
        small = compact_tables.CompactLattice.of(self.TABLE)
        again = compact_tables.CompactLattice.from_state(small.state())
        self.assertEqual({k: again[k] for k in self.TABLE}, {k: small[k] for k in self.TABLE})

    def test_a_value_that_cannot_be_kept_is_refused(self):
        with self.assertRaises(ValueError):
            compact_tables.CompactLattice.of({'か': [('蚊\x00', 1, 1, 1, '名詞')]})


@unittest.skipUnless(os.path.exists(PICKLE), 'reading_lattice_table.pickle.gz が無い')
class LatticeAnswersTests(unittest.TestCase):
    CODE = r'''
import json, sys, tempfile, shutil, os
sys.path.insert(0, sys.argv[1])
import reading_lattice as R
from kana_layout import nearby_candidates
folder = tempfile.mkdtemp(prefix='cn-lattice-')
try:
    shutil.copy2(os.path.join(sys.argv[1], 'reading_lattice_table.pickle.gz'), folder)
    R.load(cache_path=os.path.join(folder, 'reading_lattice_table.pickle.gz'), build=False)
    texts = ['がいこくのりょうり', 'などにしたばあい', 'あさいりぶれんど', 'きょうはいいてんきですね', 'かいぎしつ']
    out = dict(kind=type(R._table).__name__,
               plain=[[R.best(t).cost, R.best(t).words] for t in texts],
               near=[[R.best(t, nearby_candidates, 1).cost, R.best(t, nearby_candidates, 1).words] for t in texts[:3]],
               get=[list(R._table.get(k, ())) for k in ('か', 'かいぎ', 'ない読み')])
    print('LATTICE ' + json.dumps(out, ensure_ascii=False))
finally:
    shutil.rmtree(folder, ignore_errors=True)
'''

    def _run(self, plain):
        env = dict(os.environ)
        env.pop(compact_tables.ENV, None)
        env.pop(compact_tables.PLAIN_TABLES_ENV, None)
        if plain:
            env[compact_tables.PLAIN_TABLES_ENV] = '1'
        run = subprocess.run([sys.executable, '-X', 'utf8', '-c', self.CODE, HERE], cwd=HERE, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=300)
        lines = [l for l in run.stdout.splitlines() if l.startswith('LATTICE ')]
        self.assertTrue(lines, run.stdout[-2000:])
        return json.loads(lines[-1][len('LATTICE '):])

    def test_the_compact_lattice_answers_like_the_dict(self):
        plain, small = self._run(True), self._run(False)
        self.assertEqual(plain['kind'], 'dict')
        self.assertEqual(small['kind'], 'CompactLattice')
        for name in ('plain', 'near', 'get'):
            self.assertEqual(small[name], plain[name], name)


if __name__ == '__main__':
    unittest.main()
