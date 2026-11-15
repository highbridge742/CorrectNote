# -*- coding: utf-8 -*-
"""「ひらがなのまま通す語」の窓とつなぎ（2026-11-14 うにさん「特定の単語だけひらがなのままにするリストが要る。きれいは
ひらがなのままでよい。…別ウインドウを出し、個別に自由につけ足しや無効にできるようにする…」）。
窓の操作が kana_keep_list の関数を呼ぶこと・閉じると解析し直すこと・解析の控えの指紋に版が入ること・解析の子（別の読み手）が
読み直すこと・savedata への移し方を確かめる。一時フォルダと作った値だけを使う（個人のファイルは読まない）。"""
import importlib.util
import os
import tempfile
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest import mock

import app
import kana_keep_list
import kana_keep_window


class _Settings(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)

    def set(self, k, v):
        self[k] = v

    def save(self):
        pass


class _Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {'CN_KANA_KEEP_USER_DIR': self.tmp.name})
        self.env.start()
        kana_keep_list.set_user_dir(None)          # 環境変数（解析の子と同じ受け取り方）で置き場を決める

    def tearDown(self):
        self.env.stop()
        kana_keep_list.set_user_dir(None)
        self.tmp.cleanup()


def _default_words():
    import json
    with open(kana_keep_list._default_path(), encoding='utf-8') as f:
        return [w for w in json.load(f).get('words', ()) if isinstance(w, str) and w]


DEFAULT_WORDS = _default_words()
DEFAULT_KEYS = [kana_keep_list._norm(w) for w in DEFAULT_WORDS]   # 比べる形（ひらがな）。窓に出すのは書いた形（カタカナ）


class ListModule(_Folder):
    def test_defaults(self):
        # 初めの語は同梱の一覧のとおり（補正担当が きれい のほかにも足した・2026-11-14 22:26 の kana_keep_default.json）
        self.assertEqual(kana_keep_list.entries(), [{'word': w, 'enabled': True, 'default': True} for w in DEFAULT_WORDS])
        self.assertIn('きれい', DEFAULT_WORDS)
        rules = kana_keep_list.rules()
        self.assertEqual([r['id'] for r in rules], ['wago_kana', 'function_kana', 'verb_kanji'])
        self.assertTrue(all(r['on'] and r['default_on'] for r in rules))
        self.assertEqual(set(rules[0]), {'id', 'label', 'label_en', 'description', 'description_en', 'on',
                                         'default_on', 'members', 'targets'})
        targets = {r['id']: r['targets'] for r in rules}
        self.assertEqual(len(targets['function_kana']), 38)      # _FORMAL_KANA_NOUNS 13 ＋ _KANA_VERBS 25
        self.assertIn('こと', targets['function_kana'])
        self.assertEqual(kana_keep_list.words(), frozenset(DEFAULT_KEYS))
        self.assertFalse(os.path.exists(kana_keep_list._user_path()))   # 何も変えなければ、ユーザーの分は作らない

    def test_operations_write_only_the_difference(self):
        before = kana_keep_list.version()
        kana_keep_list.set_word('きれい', False)                  # 消したら（無効）きれいは漢字になる
        self.assertNotIn('きれい', kana_keep_list.words())
        kana_keep_list.add_word('すてき')
        kana_keep_list.set_rule('verb_kanji', False)
        self.assertEqual(kana_keep_list.words(), frozenset(DEFAULT_KEYS) - {'きれい'} | {'すてき'})
        self.assertFalse(kana_keep_list.rule_on('verb_kanji'))
        self.assertNotEqual(kana_keep_list.version(), before)
        import json
        data = json.load(open(kana_keep_list._user_path(), encoding='utf-8'))
        self.assertEqual(data['words_off'], ['きれい'])
        self.assertEqual(data['words_added'], ['すてき'])
        self.assertEqual(data['rules_off'], ['verb_kanji'])
        kana_keep_list.remove_word('きれい')
        rest = [w for w in DEFAULT_WORDS if w != 'きれい'] + ['すてき']
        self.assertEqual([e['word'] for e in kana_keep_list.entries()], rest)
        kana_keep_list.add_word('ステキ')                          # 片仮名で足しても、ひらがなで持つ
        self.assertEqual([e['word'] for e in kana_keep_list.entries()], rest)
        kana_keep_list.add_word('きれい')                         # 初めの語も足し直せる
        self.assertIn('きれい', kana_keep_list.words())
        kana_keep_list.reset()
        self.assertEqual(kana_keep_list.version(), before)
        self.assertFalse(os.path.exists(kana_keep_list._user_path()))

    def test_set_user_dir_wins_over_the_variable(self):
        with tempfile.TemporaryDirectory() as other:
            kana_keep_list.set_user_dir(other)
            self.assertEqual(os.path.dirname(kana_keep_list._user_path()), other)
            kana_keep_list.set_user_dir(None)
        self.assertEqual(os.path.dirname(kana_keep_list._user_path()), self.tmp.name)

    def test_another_reader_reads_again_after_a_change(self):
        # 解析の子と同じ: 別に読み込んだ部品（別の _state）が、更新時刻の変化で読み直す
        spec = importlib.util.spec_from_file_location('kana_keep_list_child', kana_keep_list.__file__)
        child = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(child)
        self.assertIn('きれい', child.words())
        kana_keep_list.set_word('きれい', False)
        time.sleep(0.01)
        self.assertNotIn('きれい', child.words())
        self.assertEqual(child.version(), kana_keep_list.version())


class Fingerprint(_Folder):
    def test_version_is_in_the_fingerprint(self):
        import analysis_cache
        fp = analysis_cache.build_fingerprint(os.path.dirname(app.__file__), 'x', 'kana', ())
        self.assertEqual(fp['kana_keep'], kana_keep_list.version())
        kana_keep_list.add_word('すてき')
        fp2 = analysis_cache.build_fingerprint(os.path.dirname(app.__file__), 'x', 'kana', ())
        self.assertNotEqual(fp['kana_keep'], fp2['kana_keep'])


class Window(_Folder):
    def setUp(self):
        super().setUp()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = SimpleNamespace(root=self.root, settings=_Settings(), kana_keep_changed=mock.Mock(),
                                   _place_dialog=lambda w, a, b: None)
        self.w = kana_keep_window.KanaKeepWindow(self.app)
        self.w.open()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        super().tearDown()

    def test_operations_call_the_list_functions(self):
        with mock.patch.object(kana_keep_list, 'set_word') as sw, mock.patch.object(kana_keep_list, 'set_rule') as sr:
            self.w.set_word('きれい', False)
            self.w.set_rule('verb_kanji', False)
        sw.assert_called_once_with('きれい', False)
        sr.assert_called_once_with('verb_kanji', False)
        with mock.patch.object(kana_keep_list, 'add_word') as aw:
            self.w.entry.insert(0, 'すてき')
            self.assertTrue(self.w.add())
        aw.assert_called_once_with('すてき')
        with mock.patch.object(kana_keep_list, 'remove_word') as rw:
            self.w.remove('きれい')
        rw.assert_called_once_with('きれい')
        with mock.patch.object(kana_keep_list, 'reset') as rs:
            self.assertFalse(self.w.reset(ask=lambda: False))    # 確かめで「いいえ」なら戻さない
            rs.assert_not_called()
            self.assertTrue(self.w.reset(ask=lambda: True))
            rs.assert_called_once_with()

    def test_rows_and_targets(self):
        self.assertEqual(set(self.w.rule_vars), {'wago_kana', 'function_kana', 'verb_kanji'})
        self.assertEqual(set(self.w.word_vars), set(DEFAULT_WORDS))
        self.assertTrue(self.w.toggle_targets('function_kana'))     # 開くと対象の語が見える
        self.assertIn('こと', self.w.target_labels['function_kana'].cget('text'))
        self.assertFalse(self.w.toggle_targets('function_kana'))    # もう一度で畳む

    def test_close_reanalyses_only_when_changed(self):
        self.w.apply()
        self.app.kana_keep_changed.assert_not_called()
        self.w.set_word('きれい', False)
        self.w.close()
        self.app.kana_keep_changed.assert_called_once_with()
        self.assertTrue(self.app.settings.get(kana_keep_window.POS_KEY, '').startswith('+'))   # 位置を覚える

    def test_apply_button(self):
        self.w.add('すてき')
        self.assertTrue(self.w.apply())
        self.app.kana_keep_changed.assert_called_once_with()


class AppSide(unittest.TestCase):
    def test_changed_reanalyses_everything(self):
        fake = mock.Mock(_analysis_state_revision=3)
        app.CorrectNoteApp.kana_keep_changed(fake)
        self.assertEqual(fake._analysis_state_revision, 4)
        fake._reanalyze_all.assert_called_once_with()

    def test_user_list_moves_to_savedata(self):
        self.assertIn('kana_keep_user.json', app.SAVEDATA_NAMES)
        with tempfile.TemporaryDirectory() as base:
            data, save = os.path.join(base, 'data'), os.path.join(base, 'savedata')
            os.makedirs(data); os.makedirs(save)
            open(os.path.join(base, 'kana_keep_user.json'), 'w').close()
            app.move_into_subdirs(base, data, save)
            self.assertTrue(os.path.exists(os.path.join(save, 'kana_keep_user.json')))


if __name__ == '__main__':
    unittest.main()
