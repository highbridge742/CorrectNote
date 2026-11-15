# -*- coding: utf-8 -*-
"""EXE の隣を「EXE・説明書・data・savedata」にする（2026-11-14 07:04Z うにさん「dataフォルダを作ってそこへコード類を、
savedataフォルダを作ってそこへ保存ファイルとbackupsフォルダを入れて、exe、説明書、フォルダ2個が並ぶ形にして」）。
frozen の EXE（Store 版でない）の時だけ分ける。Store 版と .py で動かす時は今までどおり。CN_DATA_SUBDIRS=0 で前の形。
前の形のファイルは起動の時に移す。新しい側に同じ名前が在れば上書きも削除もしない。作った一時フォルダと作った中身だけを使う。"""
import os
import tempfile
import unittest
from unittest import mock

import app


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


class Switch(unittest.TestCase):
    def test_only_frozen_exe(self):
        self.assertTrue(app.data_subdirs_on({}, frozen=True, package=False))      # EXE
        self.assertFalse(app.data_subdirs_on({}, frozen=True, package=True))      # Store 版（MSIX）は今のまま
        self.assertFalse(app.data_subdirs_on({}, frozen=False, package=False))    # .py で動かす時も今のまま
        self.assertFalse(app.data_subdirs_on({'CN_DATA_SUBDIRS': '0'}, frozen=True, package=False))


class Places(unittest.TestCase):
    def _dirs(self, base, on):
        with mock.patch.object(app, 'app_dir', lambda: base), mock.patch.object(app, 'data_subdirs_on', lambda: on), \
                mock.patch.object(app, 'cache_split_on', lambda: True):
            return app.data_dir(), app.savedata_dir(), app.cache_dir()

    def test_exe_places(self):
        with tempfile.TemporaryDirectory() as base:
            data, save, cache = self._dirs(base, True)
            self.assertEqual(data, os.path.join(base, 'data'))
            self.assertEqual(save, os.path.join(base, 'savedata'))
            self.assertEqual(cache, os.path.join(base, 'data', 'cache'))            # 前の cache\ は data\cache\
            self.assertEqual(sorted(os.listdir(base)), ['data', 'savedata'])

    def test_off_is_the_old_shape(self):
        # CN_DATA_SUBDIRS=0・Store 版・.py の時: 保存ファイルは直下、控えは cache\（Store 版）か直下
        with tempfile.TemporaryDirectory() as base:
            data, save, cache = self._dirs(base, False)
            self.assertEqual((data, save, cache), (base, base, os.path.join(base, 'cache')))
            self.assertFalse(os.path.exists(os.path.join(base, 'data')))
            self.assertFalse(os.path.exists(os.path.join(base, 'savedata')))

    def test_module_files_use_savedata(self):
        # 保存ファイルの置き場は savedata_dir()、控えは cache_dir()（いま .py で動かしているので、どちらも .py の隣のまま）
        here = os.path.dirname(os.path.abspath(app.__file__))
        for name in ('VOCAB_FILE', 'SESSION_FILE', 'SETTINGS_FILE', 'SETUP_FILE', 'DECISIONS_FILE', 'LAST_CHOICE_FILE',
                     'IME_READINGS_FILE', 'RESPELL_STATS_FILE', 'MANUAL_FILE'):
            self.assertEqual(os.path.dirname(getattr(app, name)), here, name)


class Moving(unittest.TestCase):
    def test_moves_old_shape(self):
        with tempfile.TemporaryDirectory() as base:
            data, save = os.path.join(base, 'data'), os.path.join(base, 'savedata')
            os.makedirs(data); os.makedirs(save)
            for n in ('session.json', 'settings.json', 'vocabulary_personal.json', 'word_book.json', 'session.json.tmp'):
                _write(os.path.join(base, n), n)
            _write(os.path.join(base, 'backups', 'k', 'a.txt'), 'b')
            _write(os.path.join(base, 'cache', 'dict_index.json'), 'c')
            _write(os.path.join(base, 'tools_local', 'scroll_trace', 'x.log'), 't')
            _write(os.path.join(base, 'CorrectNote.exe'), 'exe')
            _write(os.path.join(base, app.MANUAL_FILENAME), 'manual')
            moved = app.move_into_subdirs(base, data, save)
            self.assertEqual(moved, 8)
            self.assertEqual(sorted(os.listdir(base)), sorted(['CorrectNote.exe', app.MANUAL_FILENAME, 'data', 'savedata']))
            self.assertEqual(_read(os.path.join(save, 'session.json')), 'session.json')
            self.assertEqual(_read(os.path.join(save, 'session.json.tmp')), 'session.json.tmp')
            self.assertEqual(_read(os.path.join(save, 'backups', 'k', 'a.txt')), 'b')
            self.assertEqual(_read(os.path.join(data, 'cache', 'dict_index.json')), 'c')
            self.assertEqual(_read(os.path.join(data, 'tools_local', 'scroll_trace', 'x.log')), 't')
            self.assertEqual(app.move_into_subdirs(base, data, save), 0)          # 2回目は何もしない

    def test_never_overwrites(self):
        with tempfile.TemporaryDirectory() as base:
            data, save = os.path.join(base, 'data'), os.path.join(base, 'savedata')
            _write(os.path.join(save, 'session.json'), 'new')
            _write(os.path.join(base, 'session.json'), 'old')
            _write(os.path.join(save, 'backups', 'k', 'a.txt'), 'new')
            _write(os.path.join(base, 'backups', 'k', 'a.txt'), 'old')
            _write(os.path.join(base, 'backups', 'k', 'b.txt'), 'only-old')
            _write(os.path.join(data, 'cache', 'dict_index.json'), 'new')
            _write(os.path.join(base, 'cache', 'dict_index.json'), 'old')
            app.move_into_subdirs(base, data, save)
            # 新しい側は変わらず、古い側も消えずに残る
            self.assertEqual(_read(os.path.join(save, 'session.json')), 'new')
            self.assertEqual(_read(os.path.join(base, 'session.json')), 'old')
            self.assertEqual(_read(os.path.join(save, 'backups', 'k', 'a.txt')), 'new')
            self.assertEqual(_read(os.path.join(base, 'backups', 'k', 'a.txt')), 'old')
            self.assertEqual(_read(os.path.join(save, 'backups', 'k', 'b.txt')), 'only-old')   # 無い物だけ移る
            self.assertEqual(_read(os.path.join(data, 'cache', 'dict_index.json')), 'new')
            self.assertEqual(_read(os.path.join(base, 'cache', 'dict_index.json')), 'old')

    def test_same_folder_does_nothing(self):
        with tempfile.TemporaryDirectory() as base:
            _write(os.path.join(base, 'session.json'), 's')
            self.assertEqual(app.move_into_subdirs(base, base, base), 0)
            self.assertTrue(os.path.exists(os.path.join(base, 'session.json')))

    def test_appdata_fallback_gets_the_same_shape(self):
        # 書けない EXE の隣の代わりの %LOCALAPPDATA%\CorrectNote でも、data・savedata に分かれる
        with tempfile.TemporaryDirectory() as local, tempfile.TemporaryDirectory() as exe:
            fallback = os.path.join(local, 'CorrectNote')
            with mock.patch.object(app, '_EXE_DATA_DIR', {}), mock.patch.object(app, 'folder_writable', lambda f: False), \
                    mock.patch.dict(os.environ, {'LOCALAPPDATA': local}), \
                    mock.patch.object(app, 'running_as_package', lambda: False), \
                    mock.patch.object(app.sys, 'frozen', True, create=True), \
                    mock.patch.object(app.sys, 'executable', os.path.join(exe, 'CorrectNote.exe')):
                os.environ.pop('CN_DATA_SUBDIRS', None)
                os.environ.pop('CN_DATA_FALLBACK', None)
                self.assertEqual(app.savedata_dir(), os.path.join(fallback, 'savedata'))
                self.assertEqual(app.data_dir(), os.path.join(fallback, 'data'))
                self.assertEqual(app.cache_dir(), os.path.join(fallback, 'data', 'cache'))


if __name__ == '__main__':
    unittest.main()
