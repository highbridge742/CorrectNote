# -*- coding: utf-8 -*-
"""活用した語の再変換に、同じ読みの書き分けを出す（synonyms.same_reading_forms・candidates._inflected_homophones・
2026-11-02 うにさん「送り仮名を合わせる」）。

語彙も辞書も基本形で持つので、活用した形の読み全体では同音の語を引けず、同音の段が空だった（読みの違う類語だけが
出ていた）。基本形の読みで書き分けを引いて元の形に合わせ、全体の読みが同じもの（漢字だけが替わる）だけを出す。"""
import unittest

import candidates as C
import morphology
import synonyms as S


@unittest.skipUnless(morphology.HAS_JANOME, 'janome')
class SameReadingFormsTests(unittest.TestCase):
    def test_spellings_take_the_form_of_the_word(self):
        spell = {'とる': ['取る', '撮る', '捕る'], 'あつい': ['暑い', '熱い', '厚い'], 'うつす': ['写す', '移す']}.get
        got = lambda text: S.same_reading_forms(text, lambda r: spell(r, []))
        self.assertEqual(got('取った'), ['撮った', '捕った'])
        self.assertEqual(got('暑かった'), ['熱かった', '厚かった'])
        self.assertEqual(got('写している'), ['移している'])

    def test_a_different_reading_is_not_a_same_reading_form(self):
        # 同じ漢字でも読みの違う語（送り仮名が変わる）は、ここには出さない
        self.assertEqual(S.same_reading_forms('取った', lambda r: ['取る', '取れる']), [])
        self.assertEqual(S.same_reading_forms('写している', lambda r: ['写る']), [])

    def test_only_verbs_and_adjectives(self):
        for text in ('会議', '静かだ', ''):
            self.assertEqual(S.same_reading_forms(text, lambda r: ['買う']), [])

    def test_the_base_reading_comes_from_the_word_itself(self):
        # 基本形だけを解析し直すと別の読みになる語があるので、その語の読みと送り仮名から作る
        token = S._head('取った')[1]
        self.assertEqual(S._base_reading(token), 'とる')

    def test_they_come_first_as_same_reading_candidates(self):
        class Store:
            def lookup(self, reading): return [dict(surface='撮る')] if reading == 'とる' else []
            def has_reading(self, reading): return False
            def reading_of(self, surface): return ''
        got = C.build_candidates('取った', 'とった', Store(), lambda *a, **k: [])
        self.assertEqual((got[0]['surface'], got[0]['kind'], got[0]['reading']), ('撮った', 'homophone', 'とった'))
        self.assertEqual(C._inflected_homophones('取った', Store(), None, {'とる': ['録る']})[:1], ['撮った'])


if __name__ == '__main__':
    unittest.main()
