# -*- coding: utf-8 -*-
"""メモリに控えの無いタブへ移る時、ディスクの解析の控えから、そのタブの分だけをほどく（2026-11-22・軽量化）。前は
analysis_cache.lookup が全部のタブの全部の行をほどき直していた（1,500行のタブがあると、小さいタブへ移るだけで約150ms）。
答えは lookup と同じ（照合・ほどき方は lookup そのものを使う）。CN_DISK_CACHE_ONE_TAB=0 で前の形。作った値だけ（一時フォルダ）。"""
import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import analysis_cache as C
import app

FP = {'cache_version': 'test'}


def result(line):
    return {'original': line, 'corrected': line, 'changed': False, 'details': [], 'odd_spans': [], 'spans': []}


def tab_text(i, n=5):
    return '\n'.join('タブ%d の %d 行目' % (i, k) for k in range(n))


class OneTab(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'analysis_cache.json')
        tabs = {tab_text(i, 5 + i * 50): [result(l) for l in tab_text(i, 5 + i * 50).split('\n')] for i in range(4)}
        # 途中まで済んだタブも1つ
        text = tab_text(9)
        partial = {text: [result(l) if k % 2 == 0 else None for k, l in enumerate(text.split('\n'))]}
        self.assertTrue(C.save(self.path, FP, tabs, partial=partial))
        self.texts = list(tabs) + list(partial) + ['無いタブ']
        patcher = mock.patch.object(app, 'ANALYSIS_CACHE_FILE', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fake = NS()

    def one(self, key, fp=FP):
        return app.CorrectNoteApp._disk_cache_lookup_one(self.fake, fp, key)

    def test_same_answer_as_lookup(self):
        for key in self.texts:
            self.assertEqual(self.one(key), C.lookup(self.path, FP, key), key[:10])
        self.assertIsNotNone(self.one(tab_text(2, 105)))
        self.assertIsNone(self.one('無いタブ'))
        self.assertIsNone(self.one(tab_text(1, 55), {'cache_version': 'other'}))     # 指紋が違えば使わない

    def test_reads_the_file_again_when_it_changes(self):
        self.assertIsNotNone(self.one(tab_text(0, 5)))
        C.save(self.path, FP, {tab_text(7): [result(l) for l in tab_text(7).split('\n')]})
        st = os.stat(self.path)
        os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
        self.assertEqual(self.one(tab_text(7)), C.lookup(self.path, FP, tab_text(7)))
        self.assertIsNone(self.one(tab_text(0, 5)))                                  # 書き直された中身を見る

    def test_only_the_tab_is_unpacked(self):
        calls = []
        real = C._read_back
        with mock.patch.object(C, '_read_back', lambda x: calls.append(1) or real(x)):
            self.one(tab_text(0, 5))
        self.assertEqual(len(calls), 5)                                              # 5行のタブの5行だけ

    def test_switch_back(self):
        a = NS(_analysis_partial={}, store=NS(saved_revision=1, revision=lambda: 1),
               _analysis_cache_fingerprint=lambda: FP, _analysis_partial_state=None)
        a._disk_cache_lookup_one = lambda fp, key: self.fail('使わない')
        with mock.patch.dict(os.environ, {'CN_DISK_CACHE_ONE_TAB': '0'}), \
                mock.patch.object(app.analysis_async, 'state_key', lambda x: 'S'):
            self.assertTrue(app.CorrectNoteApp._load_tab_from_disk_cache(a, tab_text(1, 55)))
        self.assertIn(tab_text(1, 55), a._analysis_partial)


if __name__ == '__main__':
    unittest.main()
