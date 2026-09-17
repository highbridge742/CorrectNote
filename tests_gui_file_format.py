# -*- coding: utf-8 -*-
"""File IO uses only this fixture's newly-created directory and synthetic text."""
import codecs
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
import app
from session import SessionStore, new_tab


class FileFormatApplicationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='correctnote-file-format-')
        self.directory = Path(self.folder.name).resolve()
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root, undo=True)
        a.session = SessionStore()
        a.session.tabs = [new_tab()]
        a.editor_source_text = lambda: a.editor.get('1.0', 'end-1c')
        a._dirty = False; a.current_file = None; a.bookmarks = set()
        a._learned_lines = set(); a._pick_mode = None
        a._autofix_reset = Mock(); a._clear_f2_target = Mock()
        a._reset_typed_marks = Mock(); a._refresh_title = Mock()
        a._save_session = a._capture_session
        a._schedule_session_save = Mock()
        a.status = tk.Label(self.root)
        a._encoding_var = tk.StringVar(master=self.root, value='utf-8')

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root')
        self.folder.cleanup()

    def open_bytes(self, raw, name='memo.txt'):
        path = self.directory / name
        path.write_bytes(raw)
        text, error, metadata = self.a._read_text_file(str(path), with_format=True)
        self.assertIsNone(error)
        self.a._place_in_new_tab(str(path), text, metadata)
        self.a._capture_session()
        return path

    def test_load_save_session_restore_and_second_save_preserve_bytes(self):
        bodies = [('utf-8', b'', '甲\n乙\n\n'),
                  ('utf-8', codecs.BOM_UTF8, '甲\r\n乙\n丙\r\n'),
                  ('cp932', b'', '資料\r\n保存\r\n'),
                  ('utf-16-le', codecs.BOM_UTF16_LE, '😀資料\r\n次\r\n'),
                  ('utf-16-be', codecs.BOM_UTF16_BE, '資料\r次\r')]
        for i, (encoding, bom, body) in enumerate(bodies):
            with self.subTest(encoding=encoding, body=repr(body)):
                raw = bom + body.encode(encoding)
                path = self.open_bytes(raw, str(i)+'.txt')
                self.assertTrue(self.a._write_to_file(str(path)))
                self.assertEqual(path.read_bytes(), raw)
                state_path = str(self.directory / 'synthetic-session.json')
                self.a.session.save(state_path)
                loaded = SessionStore()
                self.assertTrue(loaded.load(state_path))
                self.a.session = loaded
                # Rebuild the editor using the saved source and normal padding.
                self.a.editor.delete('1.0', 'end')
                self.a.editor.insert('1.0', loaded.current()['text'])
                self.a._pad_blank_lines()
                self.assertTrue(self.a._write_to_file(str(path)))
                self.assertEqual(path.read_bytes(), raw)

    def test_encoding_choice_marks_only_current_tab_and_survives_capture(self):
        first = self.open_bytes('資料\r\n次\r\n'.encode('cp932'), 'first.txt')
        origin = self.a.session.current()
        second = self.open_bytes('別の資料\n'.encode(), 'second.txt')
        current = self.a.session.current()
        self.a._choose_file_encoding('utf-8-sig')
        self.assertEqual(origin['file_format']['encoding'], 'cp932')
        self.assertEqual(current['file_format']['encoding'], 'utf-8-sig')
        self.assertTrue(self.a._dirty)
        self.a._capture_session()
        self.assertIs(self.a.session.current(), current)
        self.assertEqual(current['file_format']['encoding'], 'utf-8-sig')
        self.assertTrue(self.a._write_to_file(str(second)))
        self.assertEqual(second.read_bytes(), codecs.BOM_UTF8 + '別の資料\n'.encode())
        self.assertEqual(first.read_bytes(), '資料\r\n次\r\n'.encode('cp932'))

    def test_unrepresentable_text_and_io_failure_never_overwrite_original(self):
        original = '資料\r\n'.encode('cp932')
        path = self.open_bytes(original)
        self.a.editor.insert('1.0', '😀')
        self.a._dirty = True
        self.assertFalse(self.a._write_to_file(str(path)))
        self.assertIsInstance(self.a._save_failed_error, UnicodeEncodeError)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(self.a._dirty)
        with patch.object(app.messagebox, 'showerror') as error:
            self.a._choose_file_encoding('cp932')
            error.assert_called_once()
        self.a._choose_file_encoding('utf-8')
        with patch('os.replace', side_effect=OSError('synthetic IO failure')):
            self.assertFalse(self.a._write_to_file(str(path)))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual([p.name for p in self.directory.iterdir()], ['memo.txt'])
        self.assertTrue(self.a._write_to_file(str(path)))
        self.assertEqual(path.read_bytes(), '😀資料\r\n'.encode())

    def test_open_binary_or_invalid_encoding_keeps_existing_document(self):
        self.a.editor.insert('1.0', '既存の本文')
        for raw in (b'\x00\x01\x02', b'\x81'):
            path = self.directory / 'invalid.txt'; path.write_bytes(raw)
            text, error, metadata = self.a._read_text_file(str(path), with_format=True)
            self.assertIsNone(text); self.assertTrue(error); self.assertIsNone(metadata)
        self.assertEqual(self.a.editor_source_text(), '既存の本文')

    def test_legacy_unsaved_tab_recovers_format_without_replacing_its_text(self):
        original = self.directory / 'legacy.txt'
        original.write_bytes('保存済みの資料\r\n'.encode('cp932'))
        state = self.directory / 'legacy-session.json'
        state.write_text(json.dumps(dict(version=1, active=0, tabs=[dict(
            text='保存前の書きかけ', path=str(original), saved=False)])), encoding='utf-8')
        loaded = SessionStore()
        self.assertTrue(loaded.load(str(state)))
        tab = loaded.current()
        self.assertEqual(tab['text'], '保存前の書きかけ')
        self.assertFalse(tab['saved'])
        self.assertEqual(tab['file_format']['encoding'], 'cp932')
        self.assertEqual(tab['file_format']['tail'], 'w')
        self.assertEqual(original.read_bytes(), '保存済みの資料\r\n'.encode('cp932'))

    def test_old_session_gets_defaults_and_malformed_format_is_ignored(self):
        path = self.directory / 'old-session.json'
        path.write_text(json.dumps(dict(version=1, active=0,
            tabs=[dict(text='既存の本文', file_format=dict(encoding=[], newline=4))])), encoding='utf-8')
        loaded = SessionStore()
        self.assertTrue(loaded.load(str(path)))
        self.assertEqual(loaded.current()['text'], '既存の本文')
        self.assertEqual(loaded.current()['file_format']['encoding'], 'utf-8')


if __name__ == '__main__':
    unittest.main()
