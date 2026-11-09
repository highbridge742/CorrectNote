"""ime_order: IME の上に出ない字を、別の読みで出る身近な字に替える（2026-11-08 うに 13:19Z/13:20Z）。例は作り例。"""
import unittest

import correction_entry as CE
import ime_order as O


class ImeOrderTest(unittest.TestCase):
    def test_unlikely_char(self):
        self.assertTrue(O.unlikely_char('纏'))
        for c in '的天点外店':
            self.assertFalse(O.unlikely_char(c), c)

    def test_stem_reading(self):
        self.assertIn('まと', O.readings_of('纏'))

    def test_respell_join(self):
        line = 'それは纏外れな質問だ。'
        r = CE._ime_unlikely_join(line, {'corrected': line}, {})
        self.assertEqual(r['corrected'], 'それは的外れな質問だ。')

    def test_no_word_no_change(self):
        line = '纏外の話をした。'
        r = CE._ime_unlikely_join(line, {'corrected': line}, {})
        self.assertEqual(r.get('corrected'), line)

    def test_correct_lines_untouched(self):
        for line in ('今始めたところです。', '一膳しかない。', '週休２日制にする。', '本読んで。', '車貸して。'):
            r = CE._ime_unlikely_join(line, {'corrected': line}, {})
            self.assertEqual(r.get('corrected'), line, line)

    def test_purple_key_respell(self):
        line = 'それは纏外です。'
        r = CE._fix_rare_join_by_key(line, {'corrected': line, 'odd_spans': [[3, 5]]}, {}, 'kana')
        self.assertEqual(r['corrected'], 'それは間違いです。')
        self.assertEqual(r['odd_spans'], [])

    def test_no_purple_no_key_respell(self):
        line = 'それは纏外です。'
        r = CE._fix_rare_join_by_key(line, {'corrected': line, 'odd_spans': []}, {}, 'kana')
        self.assertEqual(r['corrected'], line)

    def test_romaji_not_used(self):
        line = 'それは纏外です。'
        r = CE._fix_rare_join_by_key(line, {'corrected': line, 'odd_spans': [[3, 5]]}, {}, 'romaji')
        self.assertEqual(r['corrected'], line)


if __name__ == '__main__':
    unittest.main()
