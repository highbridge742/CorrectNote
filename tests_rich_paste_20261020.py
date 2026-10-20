# -*- coding: utf-8 -*-
"""Text copied or cut in CorrectNote keeps its bold / italic / underline / strikethrough when it is
pasted back into CorrectNote (2026-10-20 うにさん「太字・斜体・下線・取り消し線を、アプリ内でコピーか
カットしてペーストした場合は、書式も再現する」). The copy also puts CorrectNote's own clipboard form
(the text and where its styles are); a paste uses it only when its text is exactly what is pasted.
The pasted text takes only its own styles (not those around where it goes), line ends and emoji
do not shift them, and Ctrl+Z takes the paste back with its styles. Tk's clipboard and the reading
of the own form are replaced, so the Windows clipboard is not touched."""
import unittest
from unittest.mock import patch
import tkinter as tk

import rich_copy
import text_format

B, I, U, S = (frozenset({k}) for k in ('bold', 'italic', 'underline', 'overstrike'))
NONE = frozenset()


class PayloadTests(unittest.TestCase):
    def test_round_trip_with_line_ends_and_emoji(self):
        runs = [('ab', NONE), ('太😀', B), ('\r\n', NONE), ('xy', I | S), ('z', NONE)]
        data = rich_copy.styles_payload('ab太😀\r\nxyz', runs)
        self.assertTrue(data.endswith(b'\0'))
        got = rich_copy.parse_styles(data)
        self.assertEqual(got['text'], 'ab太😀\nxyz')
        self.assertEqual(got['runs'], [(2, 4, ['bold']), (5, 7, ['italic', 'overstrike'])])

    def test_broken_data_is_ignored(self):
        for data in (b'', b'\xff\xfe', b'{"v":2,"text":"a"}', b'[1,2]', b'{"v":1,"text":"a","runs":[["x"]]}'):
            self.assertIsNone(rich_copy.parse_styles(data), data)
        # spans outside the text are dropped
        self.assertEqual(rich_copy.parse_styles(b'{"v":1,"text":"ab","runs":[[0,5,["bold"]]]}')['runs'], [])


class PasteTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.attributes('-alpha', 0); self.root.geometry('300x200+0+0')
        self.root.tk.eval('rename clipboard rich_paste_saved_clipboard; set ::fake {}; '
                          'proc clipboard {op args} {if {$op eq "get"} {return $::fake}; '
                          'if {$op eq "append"} {append ::fake [lindex $args end]}; '
                          'if {$op eq "clear"} {set ::fake {}}}; '
                          'rename ::tk::GetSelection ::tk::rich_paste_saved_GetSelection; '
                          'proc ::tk::GetSelection {w s} {if {$s eq "CLIPBOARD"} {return $::fake}; '
                          'return [::tk::rich_paste_saved_GetSelection $w $s]}')
        self.text = tk.Text(self.root, undo=True)
        self.text.pack()
        self.text.tag_configure('fmt_bold', underline=0)
        rich_copy.install(self.text)
        self.payload = None
        reader = patch.object(rich_copy, 'read_styles', side_effect=lambda: self.payload)
        reader.start(); self.addCleanup(reader.stop)

    def tearDown(self):
        self.root.tk.eval('rename clipboard {}; rename rich_paste_saved_clipboard clipboard; '
                          'rename ::tk::GetSelection {}; rename ::tk::rich_paste_saved_GetSelection ::tk::GetSelection')
        self.root.destroy()

    def copied(self, text, runs):
        self.root.tk.setvar('::fake', text.replace('\r\n', '\n'))
        self.payload = rich_copy.parse_styles(rich_copy.styles_payload(text, runs))

    def styled(self, tag):
        r = self.text.tag_ranges(tag)
        return [self.text.get(a, z) for a, z in zip(r[0::2], r[1::2])]

    def paste(self, at='end-1c'):
        self.root.update()
        self.text.mark_set('insert', at)
        self.text.event_generate('<<Paste>>'); self.root.update()

    def test_styles_come_back_in_place_with_emoji_and_line_ends(self):
        self.text.insert('1.0', '前😀置き')
        self.copied('普通太字😀\r\n斜め線', [('普通', NONE), ('太字😀', B), ('\r\n', NONE), ('斜め', I), ('線', S)])
        self.paste()
        self.assertEqual(self.text.get('1.0', 'end-1c'), '前😀置き普通太字😀\n斜め線')
        self.assertEqual(self.styled('fmt_bold'), ['太字😀'])
        self.assertEqual(self.styled('fmt_italic'), ['斜め'])
        self.assertEqual(self.styled('fmt_overstrike'), ['線'])

    def test_other_text_on_the_clipboard_is_pasted_plain(self):
        self.copied('太字', [('太字', B)])
        self.root.tk.setvar('::fake', '別の文字')          # another app copied something else
        self.paste()
        self.assertEqual(self.text.get('1.0', 'end-1c'), '別の文字')
        self.assertEqual(self.styled('fmt_bold'), [])

    def test_pasted_text_does_not_take_the_styles_around_it(self):
        self.text.insert('1.0', '太い太い')
        self.text.tag_add('fmt_bold', '1.0', '1.4')
        self.copied('細下', [('細', NONE), ('下', U)])
        self.paste('1.2')
        self.assertEqual(self.text.get('1.0', 'end-1c'), '太い細下太い')
        self.assertEqual(self.styled('fmt_bold'), ['太い', '太い'])
        self.assertEqual(self.styled('fmt_underline'), ['下'])

    def test_replacing_a_selection(self):
        self.text.insert('1.0', 'ここを置き換える')
        self.text.tag_add('sel', '1.2', '1.4'); self.text.mark_set('insert', '1.4')
        self.copied('太字', [('太字', B)])
        self.text.event_generate('<<Paste>>'); self.root.update()
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'ここ太字き換える')
        self.assertEqual(self.styled('fmt_bold'), ['太字'])

    def test_undo_takes_the_paste_back_with_its_styles(self):
        self.text.insert('1.0', '元の文'); self.text.edit_separator()
        self.copied('太字', [('太字', B)])
        self.paste()
        self.assertEqual(self.styled('fmt_bold'), ['太字'])
        self.text.edit_undo()
        self.assertEqual(self.text.get('1.0', 'end-1c'), '元の文')
        self.assertEqual(self.styled('fmt_bold'), [])

    def test_the_formatter_is_told(self):
        calls = []

        class App:
            settings = None
            def _schedule_session_save(self):
                calls.append('save')
        fmt = text_format.install(App(), self.text)
        fmt.listeners.append(lambda: calls.append('mirror'))
        self.copied('太字', [('太字', B)])
        self.paste()
        self.assertIn('mirror', calls)                    # the correction pane shows the styles
        self.assertIn('save', calls)

    def test_copy_puts_the_own_form(self):
        put = []

        class Backend:
            def open(self): return True
            def close(self): pass
            def empty(self): pass
            def register(self, name): return {'HTML Format': 1, 'Rich Text Format': 2, rich_copy.STYLES_FORMAT: 3}[name]
            def put(self, fmt, data): put.append((fmt, data)); return True
        import clipboard_keep
        with patch.object(clipboard_keep, '_backend', return_value=Backend()), \
                patch.object(rich_copy.sys, 'platform', 'win32'):
            self.assertTrue(rich_copy.put('太字\n', [('太字', B), ('\n', NONE)]))
        own = dict(put)[3]
        self.assertEqual(rich_copy.parse_styles(own), {'text': '太字\n', 'runs': [(0, 2, ['bold'])]})


if __name__ == '__main__':
    unittest.main()
