# -*- coding: utf-8 -*-
"""置き場と削除の記録（2026-11-14）。
  exe_data_dir: EXE の隣に書ければそこ（今までどおり）、書けなければ %LOCALAPPDATA%\\CorrectNote。確かめは1回だけ。
                CN_DATA_FALLBACK=0 で前の形（いつも EXE の隣）
  削除の記録（deletion_log.txt）: 既定はオフ。設定 debug_deletion_log か CN_DELETION_LOG=1 の時だけ見張って書く。
作った値・一時のフォルダだけを使い、個人ファイルは使わない。"""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import app
import settings


class ExeDataDir(unittest.TestCase):
    def setUp(self):
        app._EXE_DATA_DIR.clear()

    def tearDown(self):
        app._EXE_DATA_DIR.clear()

    def test_writable_folder_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(app.folder_writable(d))
            self.assertEqual(app.exe_data_dir(d, environ={}), d)
            self.assertEqual([n for n in os.listdir(d)], [])        # 確かめの一時ファイルは残らない

    def test_unwritable_folder_falls_back_to_local_appdata(self):
        with tempfile.TemporaryDirectory() as exe, tempfile.TemporaryDirectory() as local:
            with mock.patch.object(app, 'folder_writable', lambda folder: False):
                got = app.exe_data_dir(exe, environ={'LOCALAPPDATA': local})
                self.assertEqual(got, os.path.join(local, 'CorrectNote'))
                self.assertTrue(os.path.isdir(got))
            # 1回確かめたら覚えている（書けるようになっても、その回は同じ場所）
            self.assertEqual(app.exe_data_dir(exe, environ={'LOCALAPPDATA': local}), got)

    def test_switch_keeps_the_exe_folder(self):
        with tempfile.TemporaryDirectory() as exe:
            with mock.patch.object(app, 'folder_writable', lambda folder: False):
                self.assertEqual(app.exe_data_dir(exe, environ={'CN_DATA_FALLBACK': '0'}), exe)

    def test_frozen_app_dir_uses_it(self):
        with tempfile.TemporaryDirectory() as exe, tempfile.TemporaryDirectory() as local:
            fake_exe = os.path.join(exe, 'CorrectNote.exe')
            with mock.patch.object(app, 'running_as_package', lambda: False), \
                    mock.patch.object(app.sys, 'frozen', True, create=True), \
                    mock.patch.object(app.sys, 'executable', fake_exe), \
                    mock.patch.object(app, 'folder_writable', lambda folder: False), \
                    mock.patch.dict(os.environ, {'LOCALAPPDATA': local}):
                self.assertEqual(app.app_dir(), os.path.join(local, 'CorrectNote'))


class DeletionLog(unittest.TestCase):
    def fake(self, on):
        values = {'debug_deletion_log': on}
        return SimpleNamespace(settings=SimpleNamespace(get=lambda k: values.get(k)),
                               _sz_snapshot=mock.Mock(return_value=None), _sz_shadow='old')

    def test_off_by_default(self):
        self.assertIs(settings.DEFAULTS['debug_deletion_log'], False)
        a = self.fake(False)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CN_DELETION_LOG', None)
            self.assertFalse(app.CorrectNoteApp._deletion_log_on(a))
            a._deletion_log_on = lambda: app.CorrectNoteApp._deletion_log_on(a)
            app.CorrectNoteApp._sz_check_shrink(a, None)
        a._sz_snapshot.assert_not_called()            # 見張りもしない（書く道に入らない）
        self.assertIsNone(a._sz_shadow)

    def test_setting_or_switch_turns_it_on(self):
        a = self.fake(True)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CN_DELETION_LOG', None)
            self.assertTrue(app.CorrectNoteApp._deletion_log_on(a))
        b = self.fake(False)
        with mock.patch.dict(os.environ, {'CN_DELETION_LOG': '1'}):
            self.assertTrue(app.CorrectNoteApp._deletion_log_on(b))
            b._deletion_log_on = lambda: app.CorrectNoteApp._deletion_log_on(b)
            app.CorrectNoteApp._sz_check_shrink(b, None)
        b._sz_snapshot.assert_called_once()

    def test_setting_is_kept_across_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'settings.json')
            s = settings.Settings(path)
            s.set('debug_deletion_log', True)
            s.save(path)
            again = settings.Settings(path)
            again.load(path)
            self.assertIs(again.get('debug_deletion_log'), True)


class CacheFolder(unittest.TestCase):
    """作り直せる控えを cache\\ へ（2026-11-14）。EXE・Store 版だけ。.py で動かす時は今までどおり。"""
    CACHES = ('dict_index.json', 'dict_index.json.compact.pickle.2cd1e69c8070.mapped',
              'cn_cost_tables.cache.pickle.e089fde90c35.mapped', 'cn_seed_cost.cache.pickle',
              'janome_entries.pickle.gz', 'reading_lattice_compact.pickle.gz', 'reading_lattice_table.pickle.gz',
              'wlsp_synonyms_compact.pickle.gz', 'context_vec.json', 'analysis_cache.json', 'usage_counts.json')
    PERSONAL = ('session.json', 'settings.json', 'setup.json', 'word_book.json', 'ime_readings.json',
                'deletion_log.txt', 'vocabulary.json', 'respell_rank_stats.json', 'CorrectNote_説明書.html')

    def test_which_files_are_caches(self):
        for name in self.CACHES:
            self.assertTrue(app.is_cache_file(name), name)
        for name in self.PERSONAL:
            self.assertFalse(app.is_cache_file(name), name)

    def test_move_once_keep_personal_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as base:
            target = os.path.join(base, app.CACHE_FOLDER)
            os.makedirs(target)
            for name in self.CACHES + self.PERSONAL:
                with open(os.path.join(base, name), 'w', encoding='utf-8') as f:
                    f.write('old')
            with open(os.path.join(target, 'usage_counts.json'), 'w', encoding='utf-8') as f:
                f.write('new')
            os.makedirs(os.path.join(base, 'backups'))
            moved = app.move_caches_into(base, target)
            self.assertEqual(moved, len(self.CACHES) - 1)
            for name in self.PERSONAL:
                self.assertTrue(os.path.exists(os.path.join(base, name)), name)
            self.assertTrue(os.path.isdir(os.path.join(base, 'backups')))
            self.assertEqual(open(os.path.join(target, 'usage_counts.json'), encoding='utf-8').read(), 'new')
            self.assertTrue(os.path.exists(os.path.join(base, 'usage_counts.json')))   # 先に在った物は上書きも消しもしない
            self.assertEqual(app.move_caches_into(base, target), 0)

    def test_a_file_that_cannot_move_stays_for_next_time(self):
        with tempfile.TemporaryDirectory() as base:
            target = os.path.join(base, app.CACHE_FOLDER)
            os.makedirs(target)
            with open(os.path.join(base, 'dict_index.json'), 'w') as f:
                f.write('x')
            with mock.patch.object(app.os, 'replace', side_effect=PermissionError('in use')):
                self.assertEqual(app.move_caches_into(base, target), 0)
            self.assertTrue(os.path.exists(os.path.join(base, 'dict_index.json')))
            self.assertEqual(app.move_caches_into(base, target), 1)

    def test_split_only_for_exe_or_package_and_switch(self):
        with mock.patch.object(app, 'running_as_package', lambda: False):
            self.assertFalse(app.cache_split_on({}))                 # .py で動かす時
            with mock.patch.object(app.sys, 'frozen', True, create=True):
                self.assertTrue(app.cache_split_on({}))
                self.assertFalse(app.cache_split_on({'CN_CACHE_DIR_SPLIT': '0'}))
        with mock.patch.object(app, 'running_as_package', lambda: True):
            self.assertTrue(app.cache_split_on({}))

    def test_cache_dir_is_under_the_data_folder(self):
        with tempfile.TemporaryDirectory() as base:
            with mock.patch.object(app, 'app_dir', lambda: base), mock.patch.object(app, 'cache_split_on', lambda: True):
                self.assertEqual(app.cache_dir(), os.path.join(base, 'cache'))
                self.assertTrue(os.path.isdir(os.path.join(base, 'cache')))
            with mock.patch.object(app, 'app_dir', lambda: base), mock.patch.object(app, 'cache_split_on', lambda: False):
                self.assertEqual(app.cache_dir(), base)

    def test_table_caches_follow_the_variable(self):
        # reading_lattice・compact_tables・janome_import・synonyms の控えは CORRECTNOTE_DATA_DIR の場所（main が cache_dir にする）
        import reading_lattice, compact_tables, janome_import, synonyms
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'CORRECTNOTE_DATA_DIR': d}):
            self.assertEqual(os.path.dirname(reading_lattice.default_cache_path()), d)
            self.assertEqual(compact_tables._pickle_folder(), d)
            self.assertEqual(os.path.dirname(janome_import._entries_cache_path()), d)
            self.assertEqual(os.path.dirname(synonyms._compact_cache_path()), d)


if __name__ == '__main__':
    unittest.main()
