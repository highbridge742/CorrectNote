# -*- coding: utf-8 -*-
"""解析の控えの指紋（analysis_cache._engine_source_files・2026-11-01）。correction_entry から呼ぶ段を手の一覧に
足し忘れると、その段だけ差し替えても控えの古い答えが残っていた。import をたどって漏れなく拾い、中身で見る。"""
import gzip
import os
import tempfile
import unittest

import analysis_cache as A


def _write(folder, name, text):
    with open(os.path.join(folder, name), 'w', encoding='utf-8') as handle:
        handle.write(text)


class EngineSourcesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.dir = self.folder.name
        _write(self.dir, 'correction_entry.py', 'def run():\n    import new_stage\n    from other_stage import go\n')
        _write(self.dir, 'new_stage.py', 'import deeper, settings\n')
        _write(self.dir, 'other_stage.py', 'X = 1\n')
        _write(self.dir, 'deeper.py', 'Y = 1\n')
        _write(self.dir, 'settings.py', 'import hidden_ui_only\n')
        _write(self.dir, 'hidden_ui_only.py', 'Z = 1\n')

    def tearDown(self):
        self.folder.cleanup()

    def names(self):
        return [row[0] for row in A._engine_source_files(self.dir)]

    def test_stages_reached_through_imports_are_watched(self):
        names = self.names()
        for name in ('correction_entry.py', 'new_stage.py', 'other_stage.py', 'deeper.py'):
            self.assertIn(name, names)
        self.assertNotIn('settings.py', names)              # 画面・保存の側では止める
        self.assertNotIn('hidden_ui_only.py', names)

    def test_a_same_size_change_is_seen(self):
        before = A._engine_source_files(self.dir)
        _write(self.dir, 'deeper.py', 'Y = 2\n')
        self.assertNotEqual(before, A._engine_source_files(self.dir))

    def test_a_gzip_table_is_seen_by_its_contents(self):
        path = os.path.join(self.dir, 'seed_japanese.txt.gz')
        with open(path, 'wb') as handle:
            handle.write(gzip.compress(b'aaaa', mtime=0))
        before = A._engine_source_files(self.dir)
        with open(path, 'wb') as handle:
            handle.write(gzip.compress(b'aaab', mtime=0))
        after = A._engine_source_files(self.dir)
        self.assertIn('seed_japanese.txt.gz', [row[0] for row in after])
        self.assertNotEqual(before, after)

    def test_the_real_folder_has_every_correction_stage(self):
        here = os.path.dirname(os.path.abspath(__file__))
        names = [row[0] for row in A._engine_source_files(here)]
        for stage in ('odd_respell', 'kana_lattice_place', 'question_ka', 'formal_noun_gap', 'kana_keep',
                      'impossible_slip', 'dangling_verb', 'degree_adverb', 'kanji_doubt', 'noun_suffix',
                      'keystroke_doubt', 'shift_slip', 'rival_repair', 'predicate_slip'):
            if os.path.exists(os.path.join(here, stage + '.py')):
                self.assertIn(stage + '.py', names)
        self.assertNotIn('app.py', names)


if __name__ == '__main__':
    unittest.main()
