# -*- coding: utf-8 -*-
"""品詞の書式の初期値の版4（2026-11-01 うにさん「フォントサイズのデフォルトを11に変更。助詞と前置詞を別々の項目に
分け、助詞を0.9倍に変更。前置詞は1.0倍。その他英字を1.1倍に変更。色を藍・とても明るい」「冠詞のデフォルトを0.9倍」）。

古い設定ファイルは、初期値のままだった所だけ新しい初期値へ移す。選び直した値は残す。英語の前置詞は前置詞の行。"""
import json
import os
import tempfile
import unittest

import pos_font as P
import settings as S


def load(data):
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'settings.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False)
        return S.Settings(path)


V3_DEFAULTS = {'名詞': 1.1, '名詞（サ変）': 1.0, '数詞': 1.2, '英字': 1.0, '動詞': 1.1, '形容詞': 1.1, '形容動詞': 1.0,
               '副詞': 1.1, '連体詞': 1.0, '接続詞': 1.0, '感動詞': 1.0, '助詞': 1.0, '助動詞': 1.1, '接頭詞': 1.0,
               '記号': 1.0, 'フィラー': 1.4, 'その他': 1.0, '冠詞': 1.0, '代名詞': 1.2}


class PosDefaults4Tests(unittest.TestCase):
    def test_new_defaults(self):
        values = S.Settings()
        multipliers = P.normalize_multipliers(values.get('pos_font_multipliers'))
        self.assertEqual((multipliers['助詞'], multipliers['前置詞'], multipliers['英字'], multipliers['冠詞']),
                         (0.8, 0.9, 1.0, 0.8))
        self.assertEqual(values.get('editor_font_size'), 12)
        self.assertEqual(P.PALETTE_NAMES[P.normalize_colors({})['英字']], '藍・とても明るい')
        self.assertEqual(P.POS_DIALOG_ROWS[[k for k, _l in P.POS_DIALOG_ROWS].index('助詞') + 2], ('前置詞', '前置詞'))

    def test_old_defaults_move_and_chosen_values_stay(self):
        old = dict(pos_font_defaults='3', editor_font_size=10, pos_font_multipliers=dict(V3_DEFAULTS),
                   pos_font_colors={'英字': P.palette_color('グレー', '明るい')},
                   pos_font_colors_light={'英字': P.palette_color('グレー', 'やや濃い')})
        moved = load(old)
        multipliers = P.normalize_multipliers(moved.get('pos_font_multipliers'))
        self.assertEqual((multipliers['助詞'], multipliers['前置詞'], multipliers['英字'], multipliers['冠詞']),
                         (0.8, 0.9, 1.0, 0.8))
        self.assertEqual(moved.get('editor_font_size'), 12)
        self.assertEqual(P.normalize_colors(moved.get('pos_font_colors'))['英字'], P.palette_color('藍', 'とても明るい'))
        self.assertEqual(P.normalize_colors(moved.get('pos_font_colors_light'), False)['英字'],
                         P.palette_color('藍', 'やや濃い'))
        self.assertEqual(moved.get('pos_font_defaults'), '6')
        chosen = dict(V3_DEFAULTS, 助詞=0.8, 英字=1.3, 冠詞=1.2)
        kept = load(dict(old, editor_font_size=14, pos_font_multipliers=chosen,
                         pos_font_colors={'英字': P.palette_color('赤', '中間'), '助詞': P.palette_color('青', '中間')}))
        multipliers = P.normalize_multipliers(kept.get('pos_font_multipliers'))
        self.assertEqual((multipliers['助詞'], multipliers['前置詞'], multipliers['英字'], multipliers['冠詞']),
                         (0.8, 0.8, 1.3, 1.2))     # 前置詞は今まで塗っていた助詞の値を引き継ぐ
        self.assertEqual(kept.get('editor_font_size'), 14)
        colors = P.normalize_colors(kept.get('pos_font_colors'))
        self.assertEqual((colors['英字'], colors['前置詞']), (P.palette_color('赤', '中間'), P.palette_color('青', '中間')))

    def test_compound_particles_take_their_own_row_at_1_0(self):
        # 2026-11-01 うにさん「「によって」「として」…まで小さくなると読みにくくもなる」: 連語の助詞は別の項目
        self.assertEqual(P.major_pos('助詞:格助詞:連語'), '助詞（複合）')
        self.assertEqual(P.major_pos('助詞:並立助詞'), '助詞')        # たり は短い助詞のまま
        self.assertEqual(P.major_pos('助詞:格助詞:一般'), '助詞')
        self.assertEqual(P.POS_FONT_DEFAULTS['助詞（複合）'], 0.9)
        keys = [k for k, _l in P.POS_DIALOG_ROWS]
        self.assertEqual(keys[keys.index('助詞') + 1], '助詞（複合）')
        self.assertEqual(P.normalize_colors({})['助詞（複合）'], P.normalize_colors({})['助詞'])
        v4 = load(dict(pos_font_defaults='4', pos_font_multipliers=dict(V3_DEFAULTS, 助詞=0.9),
                       pos_font_colors={'助詞': P.palette_color('青', '中間')}))
        self.assertEqual(P.normalize_multipliers(v4.get('pos_font_multipliers'))['助詞（複合）'], 0.9)
        self.assertEqual(P.normalize_colors(v4.get('pos_font_colors'))['助詞（複合）'], P.palette_color('青', '中間'))
        self.assertEqual(v4.get('pos_font_defaults'), '6')

    def test_tari_takes_the_style_of_the_predicate_before_it(self):
        # 2026-11-01 うにさん「なかったり」: janome は たり を並立助詞とも助動詞とも付ける。前の語の書式で揃える
        def kinds(text, tokens):
            return [(text[a:z], m) for m, a, z in P.spans(text, tokens)]
        text = '高かったり安かったり'
        tokens = (('高かっ', '形容詞:自立', '', 0, 3), ('たり', '助詞:並立助詞', '', 3, 5),
                  ('安かっ', '形容詞:自立', '', 5, 8), ('たり', '助動詞', '', 8, 10))
        self.assertEqual(kinds(text, tokens), [('高かっ', '形容詞'), ('たり', '形容詞'), ('安かっ', '形容詞'), ('たり', '形容詞')])
        text = '見たり'
        self.assertEqual(kinds(text, (('見', '動詞:自立', '', 0, 1), ('たり', '助詞:並立助詞', '', 1, 3))),
                         [('見', '動詞'), ('たり', '動詞')])
        text = 'りんごやみかん'                 # ほかの並立助詞は助詞のまま
        self.assertEqual(kinds(text, (('りんご', '名詞:一般', '', 0, 3), ('や', '助詞:並立助詞', '', 3, 4),
                                      ('みかん', '名詞:一般', '', 4, 7)))[1], ('や', '助詞'))

    def test_a_particle_that_is_also_a_conjunction_is_drawn_as_one(self):
        # 2026-11-01 うにさん「および」: janome は前の語によって および を接続助詞と付ける
        import morphology
        if not morphology.HAS_JANOME:
            self.skipTest('janome')
        text = '色および形'
        tokens = (('色', '名詞:接尾:一般', '', 0, 1), ('および', '助詞:接続助詞', '', 1, 4), ('形', '名詞:一般', '', 4, 5))
        self.assertIn(('接続詞', 1, 4), P.spans(text, tokens))
        text = 'りんごがある'                   # 1字の助詞（が）は触らない
        self.assertIn(('助詞', 3, 4), P.spans(text, (('りんご', '名詞:一般', '', 0, 3), ('が', '助詞:格助詞:一般', '', 3, 4),
                                                      ('ある', '動詞:自立', '', 4, 6))))

    def test_ascii_marks_tagged_as_nouns_are_marks(self):
        # 2026-11-01 うにさん「英語の記号に見える部分が名詞判定」: janome は <= (*) -> && - , を 名詞・サ変接続 と付ける
        text = "a '<=' b (*) c->d"
        tokens = (("'<='", '名詞:サ変接続', '', 2, 6), ('(*)', '名詞:サ変接続', '', 9, 12), ('->', '名詞:サ変接続', '', 14, 16))
        self.assertEqual([m for m, a, z in P.spans(text, tokens)], ['記号', '記号', '記号'])
        # 絵の記号（★♪）も名詞と付いたら記号。品詞の分からない字（その他）はそのまま
        self.assertEqual(P.spans('★♪', (('★♪', '名詞:サ変接続', '', 0, 2),)), (('記号', 0, 2),))
        self.assertEqual(P.spans('😀', (('😀', '未知品詞', '', 0, 1),)), (('その他', 0, 1),))
        # 数の字だけ（① ½ ²）は数詞
        self.assertEqual(P.spans('①½', (('①½', '名詞:サ変接続', '', 0, 2),)), (('数詞', 0, 2),))

    def test_an_english_preposition_takes_its_own_row(self):
        import en_pos
        self.assertEqual(en_pos.CATEGORY['P'], '前置詞')


if __name__ == '__main__':
    unittest.main()
