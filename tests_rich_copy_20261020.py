# -*- coding: utf-8 -*-
"""Copying keeps bold, italic, underline and strikethrough (2026-10-19 うにさん「書式もコピー
できますか」). A styled selection goes on the clipboard as the same plain text as before plus
"HTML Format" (Excel, browsers) and "Rich Text Format" (Word, and the RichEdit inside Notepad,
which reads only the RTF). A selection without styles is copied as text only. The clipboard
tests put back what was on the clipboard before them."""
import re
import sys
import unittest
import tkinter as tk

import rich_copy

B, I, U, S = (frozenset({k}) for k in ('bold', 'italic', 'underline', 'overstrike'))
NONE = frozenset()


class BuildTests(unittest.TestCase):
    def test_html_lines_and_escapes(self):
        runs = [('a<&>', NONE), ('太字', B), ('\n', NONE), ('斜', I), ('下', U), ('消', S)]
        self.assertEqual(rich_copy.html_fragment(runs),
                         'a&lt;&amp;&gt;<b>太字</b><br><i>斜</i><u>下</u><s>消</s>')

    def test_html_tabs_become_a_table(self):
        runs = [('a', B), ('\tb\n', NONE), ('c\t', I)]
        self.assertEqual(rich_copy.html_fragment(runs),
                         '<table><tr><td><b>a</b></td><td>b</td></tr>'
                         '<tr><td><i>c</i></td><td></td></tr></table>')

    def test_html_nests_several_styles(self):
        self.assertEqual(rich_copy.html_fragment([('x', B | I | U | S)]), '<s><u><i><b>x</b></i></u></s>')

    def test_cf_html_offsets_are_utf8_bytes(self):
        fragment = '<b>太字😀</b>'
        data = rich_copy.cf_html(fragment)
        head = data.decode('utf-8')
        offset = {k: int(v) for k, v in re.findall(r'(\w+HTML|\w+Fragment):(\d+)', head)}
        self.assertEqual(data[offset['StartFragment']:offset['EndFragment']].decode('utf-8'), fragment)
        self.assertTrue(data[offset['StartHTML']:].startswith(b'<html>'))
        self.assertEqual(offset['EndHTML'], len(data))

    def test_rtf_styles_escapes_and_surrogates(self):
        doc = rich_copy.rtf([('a{\\}', NONE), ('太😀', B), ('\n\t', S), ('u', U)])
        self.assertTrue(doc.startswith('{\\rtf1\\ansi\\uc1 ') and doc.endswith('}'))
        self.assertNotIn('fonttbl', doc)        # the font of where it is pasted
        self.assertIn('{a\\{\\\\\\}}', doc)
        self.assertIn('{\\b \\u22826?\\u-10179?\\u-8704?\\b0}', doc)
        self.assertIn('{\\strike \\par\n\\tab \\strike0}', doc)
        self.assertIn('{\\ul u\\ulnone}', doc)
        doc.encode('ascii')

    def test_plain_text_uses_crlf(self):
        self.assertEqual(rich_copy.plain_text('a\nb\r\nc'), 'a\r\nb\r\nc')


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.text = tk.Text(self.root)
        self.text.insert('1.0', 'ab太字😀\nxy\tz')
        self.text.tag_add('fmt_bold', '1.2', '1.end')
        self.text.tag_add('fmt_overstrike', '2.0', '2.2')

    def tearDown(self):
        self.root.destroy()

    def test_runs_follow_the_style_tags(self):
        self.assertEqual(rich_copy.styled_runs(self.text, '1.0', 'end-1c'),
                         [('ab', NONE), ('太字😀', B), ('\n', NONE), ('xy', S), ('\tz', NONE)])
        # Starting inside a styled range keeps that style
        self.assertEqual(rich_copy.styled_runs(self.text, '1.3', '1.end'), [('字😀', B)])
        self.assertFalse(rich_copy.has_styles(rich_copy.styled_runs(self.text, '2.2', '2.end')))

    def test_install_wraps_tk_copy(self):
        self.assertTrue(rich_copy.install(self.text))
        self.assertTrue(rich_copy.install(self.text))      # twice is the same
        tags = self.text.bindtags()
        at = tags.index('Text')
        self.assertEqual(tags[at - 1:at + 2], (rich_copy.BEFORE_TAG, 'Text', rich_copy.AFTER_TAG))
        self.assertEqual(len(tags), 6)          # the widget, the 3 above, ".", "all"


@unittest.skipUnless(sys.platform == 'win32', 'Windows clipboard')
class ClipboardTests(unittest.TestCase):
    def setUp(self):
        import clipboard_keep
        self.ck = clipboard_keep
        self.b = clipboard_keep._backend()
        if not self.b.open():
            self.skipTest('clipboard busy')
        try:
            formats = self.b.formats()
            complete = len(formats) == self.b.u.CountClipboardFormats()
            self.saved = [(f, self.b.take(f)) for f in formats if clipboard_keep._keepable(f)]
            # A format that could not be read (an owner that did not render it in time) would
            # be lost when putting the rest back: then the test does not run
            complete = complete and all(d is not None for f, d in self.saved)
        finally:
            self.b.close()
        if not complete:
            self.skipTest('could not read the whole clipboard to put it back')
        self.html = self.b.register('HTML Format')
        self.rtf = self.b.register('Rich Text Format')
        self.root = tk.Tk(); self.root.attributes('-alpha', 0); self.root.geometry('200x100+0+0')
        self.text = tk.Text(self.root); self.text.pack(); self.root.update()
        self.text.insert('1.0', 'ab太字😀\nxy\tz')
        self.text.tag_add('fmt_bold', '1.2', '1.end')
        self.text.tag_add('fmt_italic', '2.0', '2.2')
        rich_copy.install(self.text)

    def tearDown(self):
        self.root.destroy()
        import time
        for _ in range(40):                     # another program may hold it for a moment
            if self.b.open():
                break
            time.sleep(0.05)
        else:
            self.fail('could not open the clipboard to put it back')
        try:
            self.b.empty()
            for f, d in self.saved:
                self.b.put(f, d)
        finally:
            self.b.close()

    def clipboard(self):
        import time
        for _ in range(40):
            if self.b.open():
                break
            time.sleep(0.05)
        else:
            self.fail('clipboard busy')
        try:
            return {f: self.b.take(f) for f in self.b.formats()}
        finally:
            self.b.close()

    def select(self, a, z):
        self.text.tag_remove('sel', '1.0', 'end')
        self.text.tag_add('sel', a, z)

    def test_copy_puts_three_forms(self):
        self.select('1.0', 'end-1c')
        self.text.event_generate('<<Copy>>'); self.root.update()
        got = self.clipboard()
        self.assertEqual(got[13].decode('utf-16-le'), 'ab太字😀\r\nxy\tz\0')
        self.assertIn(b'<b>' + '太字😀'.encode('utf-8') + b'</b>', got[self.html])
        self.assertIn(b'<i>xy</i>', got[self.html])
        self.assertIn(b'{\\b \\u22826?', got[self.rtf])
        self.assertEqual(self.root.clipboard_get(), 'ab太字😀\nxy\tz')    # pasting back is unchanged

    def test_plain_selection_is_text_only(self):
        self.select('2.2', '2.end')
        self.text.event_generate('<<Copy>>'); self.root.update()
        got = self.clipboard()
        self.assertNotIn(self.html, got)
        self.assertNotIn(self.rtf, got)
        self.assertEqual(self.root.clipboard_get(), '\tz')

    def test_cut_keeps_the_styles(self):
        self.select('1.0', '1.end')
        self.text.event_generate('<<Cut>>'); self.root.update()
        got = self.clipboard()
        self.assertIn(self.rtf, got)
        self.assertEqual(got[13].decode('utf-16-le'), 'ab太字😀\0')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '\nxy\tz')

    def test_reading_right_after_a_change_sees_every_format(self):
        # Opened without a window, the clipboard was taken away mid-read just after a change
        # (1418), and the save before a test (or before lending it) kept only part of it
        self.assertTrue(rich_copy.put('ab', [('ab', B)]))
        expected = self.b.u.CountClipboardFormats()
        self.assertGreaterEqual(expected, 3)
        got = self.clipboard()
        self.assertEqual(len(got), expected)
        self.assertTrue(all(data is not None for data in got.values()))

    def test_a_faked_tk_clipboard_never_reaches_windows(self):
        # As tests_gui_cut_tabs / tests_gui_encoded_paste do: Tk's copy stays in the interpreter
        before = self.clipboard()
        self.root.tk.eval('rename clipboard rich_copy_saved_clipboard; '
                          'proc clipboard {op args} {if {$op eq "get"} {return $::fake}; '
                          'if {$op eq "append"} {append ::fake [lindex $args end]}; '
                          'if {$op eq "clear"} {set ::fake {}}}')
        try:
            self.select('1.0', 'end-1c')
            self.text.event_generate('<<Copy>>'); self.root.update()
            self.assertEqual(self.root.tk.getvar('fake'), 'ab太字😀\nxy\tz')
            self.assertEqual(self.clipboard(), before)
        finally:
            self.root.tk.eval('rename clipboard {}; rename rich_copy_saved_clipboard clipboard')

    def test_copy_function_for_the_menu(self):
        self.select('1.0', '1.4')
        self.assertEqual(rich_copy.copy(self.text), 'ab太字')
        self.assertIn(self.html, self.clipboard())
        self.select('2.2', '2.end')
        self.assertIsNone(rich_copy.copy(self.text))      # the caller copies the text as before


if __name__ == '__main__':
    unittest.main()
