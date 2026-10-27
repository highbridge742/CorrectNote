# -*- coding: utf-8 -*-
"""The 文変換 button (2026-10-26 うにさん「ボタン名を文変換、横幅がないときは文1文字に。再変換の再の次に」).

Its name is 文変換 and it shortens to 文 at the same stage as 再変換 → 再; it comes right after 再変換 by default
and is put right after 再変換 in an order saved before it existed, wherever the user moved 再変換.
"""
import re
import unittest
from pathlib import Path

import toolbar_preferences as tp


class ConvertButtonTests(unittest.TestCase):
    def test_name_and_default_place(self):
        self.assertEqual(tp.LABELS['convert'], '文変換')
        self.assertEqual(tp.label_for('convert'), '文変換')
        self.assertEqual(tp.IDS[tp.IDS.index('reconvert') + 1], 'convert')
        order, hidden = tp.normalized()
        self.assertEqual(order[order.index('reconvert') + 1], 'convert')
        self.assertNotIn('convert', hidden)

    def test_saved_order_gets_it_right_after_reconvert(self):
        saved = [k for k in tp.IDS if k != 'convert']
        # the user moved 再変換 to the far right before 文変換 existed
        saved.remove('reconvert')
        saved.append('reconvert')
        order, hidden = tp.normalized(saved, ['quote'])
        self.assertEqual(order[order.index('reconvert') + 1], 'convert')
        self.assertEqual(hidden, {'quote'})
        # and where 再変換 is gone from the saved order, the usual rule places it
        order, _ = tp.normalized([k for k in tp.IDS if k not in ('convert', 'reconvert')])
        self.assertEqual(order[order.index('reconvert') + 1], 'convert')

    def test_short_name_is_bun_at_the_reconvert_stage(self):
        source = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        stages = dict(re.findall(r"\(self\.(\w+_btn), '[^']*', '[^']*', (\d)\)", source))
        self.assertIn("(self.convert_btn, '文変換', '文', ", source)
        self.assertEqual(stages['convert_btn'], stages['reconvert_btn'])
        self.assertIn("text='文変換', command=self._open_convert_window", source)

    def test_english_names(self):
        import ui_lang_en
        self.assertEqual(ui_lang_en.TABLE['文変換'], 'Sentence convert')
        self.assertLessEqual(len(ui_lang_en.TABLE['文']), 2)


if __name__ == '__main__':
    unittest.main()
