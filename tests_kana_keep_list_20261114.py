# -*- coding: utf-8 -*-
"""ひらがなのまま通す語の一覧（kana_keep_list・2026-11-14）の試験。文は作った例。"""
import os
import shutil
import tempfile
import unittest

import kana_keep_list as L


class _UserDir:
    def __enter__(self):
        self.d = tempfile.mkdtemp()
        self.old = os.environ.get('CN_KANA_KEEP_USER_DIR')
        os.environ['CN_KANA_KEEP_USER_DIR'] = self.d
        L.set_user_dir(None)
        L.load(force=True)
        return self.d

    def __exit__(self, *a):
        if self.old is None:
            os.environ.pop('CN_KANA_KEEP_USER_DIR', None)
        else:
            os.environ['CN_KANA_KEEP_USER_DIR'] = self.old
        shutil.rmtree(self.d, ignore_errors=True)
        L.load(force=True)


def _res(line, corrected):
    return {'corrected': corrected, 'changed': corrected != line, 'details': [['x', corrected, 'かな入力']]}


class KanaKeepList(unittest.TestCase):
    def test_default_has_kirei(self):
        with _UserDir():
            self.assertIn('きれい', L.words())
            self.assertEqual([r['id'] for r in L.rules()], ['wago_kana', 'function_kana', 'verb_kanji'])

    def test_keep_reverts_kanji(self):
        with _UserDir():
            got = L.keep('きれいに撮れてる', _res('きれいに撮れてる', '綺麗に撮れてる'))
            self.assertEqual(got['corrected'], 'きれいに撮れてる')
            self.assertFalse(got['changed'])

    def test_rewrite_purple_dropped_when_line_restored(self):
        import fixed_still_odd as F
        with _UserDir():
            r = _res('星がきれいで空を見た', '星が綺麗で空を見た')
            r['odd_spans'] = [(6, 9)]
            r['odd_reasons'] = [(6, 9, F.REASON)]
            got = L.keep('星がきれいで空を見た', r)
            self.assertEqual(got['corrected'], '星がきれいで空を見た')
            self.assertFalse(got['odd_spans'])

    def test_user_typed_kanji_not_turned_to_kana(self):
        # うに 11-14 13:21Z「漢字にしたものをひらがなに補正する必要はない」: 書き手が漢字で打った語はそのまま
        with _UserDir():
            for w in ('うどん', 'いちばん', 'おしえる'):
                self.assertIn(w, L.words())
            line = '一番小さい子に教える'
            got = L.keep(line, _res(line, '一番小さい子に教える'))
            self.assertEqual(got['corrected'], line)
            got = L.keep('一番の友だちに教えるよ', _res('一番の友だちに教えるよ', '一番の友達に教えるよ'))
            # ともだち が一覧に在る（2026-11-15 うにの追加）ので、直しの 友達 は書き手の打った形 友だち へ戻す（かなにはしない）
            self.assertEqual(got['corrected'], '一番の友だちに教えるよ')
            got = L.keep('みちをおしえる', _res('みちをおしえる', 'みちを教える'))
            self.assertEqual(got['corrected'], 'みちをおしえる')

    def test_weak_purple_on_list_word_dropped(self):
        with _UserDir():
            line = 'みちをおしえる。'
            r = {'corrected': line, 'changed': False, 'details': [], 'odd_spans': [(3, 5)],
                 'odd_reasons': [(3, 5, '直した形の「名詞＋助詞＋動詞」の組が例文に無いので決められない')]}
            self.assertFalse(L.drop_weak(line, r)['odd_spans'])
            r2 = dict(r, odd_reasons=[(3, 5, '「おし」は、かな入力で隣のキーを打ったか、一緒に押したかもしれません')])
            self.assertTrue(L.drop_weak(line, r2)['odd_spans'])

    def test_disable_and_remove(self):
        with _UserDir():
            L.set_word('きれい', False)
            self.assertNotIn('きれい', L.words())
            self.assertEqual(L.keep('きれいに撮れてる', _res('きれいに撮れてる', '綺麗に撮れてる'))['corrected'], '綺麗に撮れてる')
            L.set_word('きれい', True)
            L.remove_word('きれい')
            self.assertNotIn('きれい', [e['word'] for e in L.entries()])
            L.reset()
            self.assertIn('きれい', L.words())

    def test_added_word(self):
        with _UserDir():
            v0 = L.version()
            L.add_word('しりょう')
            self.assertNotEqual(L.version(), v0)
            e = [x for x in L.entries() if x['word'] == 'しりょう'][0]
            self.assertFalse(e['default'])
            self.assertEqual(L.keep('しりょうをおくる', _res('しりょうをおくる', '資料をおくる'))['corrected'], 'しりょうをおくる')

    def test_user_kanji_untouched(self):
        with _UserDir():
            line = '綺麗なほしを見た'
            got = L.keep(line, _res(line, '綺麗な星を見た'))
            self.assertEqual(got['corrected'], '綺麗な星を見た')

    def test_rule_members(self):
        with _UserDir():
            self.assertTrue(L.rule_on('aux_verb'))
            L.set_rule('function_kana', False)
            self.assertFalse(L.rule_on('aux_verb'))
            self.assertFalse(L.rule_on('function_word'))
            self.assertTrue(L.rule_on('wago_noun'))
            L.set_rule('function_kana', True)
            self.assertTrue(L.rule_on('aux_verb'))

    def test_switch_off(self):
        with _UserDir():
            old = os.environ.get('CN_KANA_KEEP_LIST')
            os.environ['CN_KANA_KEEP_LIST'] = '0'
            try:
                r = _res('きれいに撮れてる', '綺麗に撮れてる')
                self.assertIs(L.keep('きれいに撮れてる', r), r)
            finally:
                if old is None:
                    os.environ.pop('CN_KANA_KEEP_LIST', None)
                else:
                    os.environ['CN_KANA_KEEP_LIST'] = old

    def test_phrase_and_typed_kanji(self):
        with _UserDir():
            got = L.keep('あめかもしれない', _res('あめかもしれない', '雨かも知れない'))
            self.assertEqual(got['corrected'], '雨かもしれない')
            got = L.keep('ともだちとあそぶ', _res('ともだちとあそぶ', '友達と遊ぶ'))
            self.assertEqual(got['corrected'], 'ともだちと遊ぶ')

    def test_typed_word_other_reading(self):
        with _UserDir():
            got = L.keep('いわしとさんまをやく', _res('いわしとさんまをやく', 'いわしと三間を焼く'))
            self.assertEqual(got['corrected'], 'いわしとさんまを焼く')
            self.assertIn('さんま', L.words())


if __name__ == '__main__':
    unittest.main()
