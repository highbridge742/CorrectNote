# -*- coding: utf-8 -*-
import codecs
import unittest
import file_format as formats


class FileFormatTests(unittest.TestCase):
    def test_roundtrip_all_encodings_boms_and_line_endings(self):
        for encoding in formats.ENCODINGS:
            for text in ('', '本文', '本文\n次の行\n', '本文\r\n次の行\r\n',
                         '\r\r本文\r次の行\r\r', '\r\n\n',
                         '甲\r\n乙\n丙\r丁\n\r\n', '\ufeff本文\n'):
                with self.subTest(encoding=encoding, text=repr(text)):
                    if encoding == 'cp932' and '\ufeff' in text:
                        continue
                    raw = text.encode(encoding)
                    if encoding == 'utf-16-le': raw = codecs.BOM_UTF16_LE + raw
                    if encoding == 'utf-16-be': raw = codecs.BOM_UTF16_BE + raw
                    normal, meta = formats.decode(raw)
                    self.assertNotIn('\r', normal)
                    self.assertEqual(formats.encode(normal, meta), raw)
                    self.assertEqual(formats.encode(normal.rstrip('\n') + '\n' * 24, meta), raw)

    def test_mixed_endings_follow_inserted_deleted_and_edited_lines(self):
        normal, meta = formats.decode('甲\r\n乙\n丙\r丁\n'.encode('utf-8'))
        # The main style is LF, and the final file break remains LF.
        edited = '甲\n追加\n乙改\n丙\n丁'
        updated = formats.rebase(meta, normal, edited)
        self.assertEqual(formats.encode(edited, updated).decode(), '甲\r\n追加\n乙改\n丙\r丁\n')
        deleted = '甲\n丙\n丁'
        updated = formats.rebase(meta, normal, deleted)
        self.assertEqual(formats.encode(deleted, updated).decode(), '甲\r\n丙\r丁\n')
        self.assertEqual(formats.newline_label(meta, normal), '混在（保持）')

    def test_encoding_conversion_is_strict_and_preserves_newlines(self):
        text, meta = formats.decode('資料\r\n次の行\r\n'.encode('cp932'))
        meta['encoding'] = 'utf-8-sig'
        self.assertEqual(formats.encode(text, meta), codecs.BOM_UTF8 + '資料\r\n次の行\r\n'.encode())
        meta['encoding'] = 'cp932'
        with self.assertRaises(UnicodeEncodeError):
            formats.encode('😀資料', meta)
        with self.assertRaises((UnicodeError, ValueError)):
            formats.decode(b'\x81')
        for raw in (b'a\x00b', codecs.BOM_UTF16_LE + b'\x00\x00', codecs.BOM_UTF32_LE + b'a\x00\x00\x00'):
            with self.assertRaises(ValueError):
                formats.decode(raw)

    def test_legacy_and_damaged_metadata_fall_back_without_losing_text(self):
        for metadata in (None, {}, [], dict(encoding=[], newline={}, endings=True, tail=False)):
            self.assertEqual(formats.encode('資料\n次の行', metadata), '資料\r\n次の行'.encode())
        text, meta = formats.decode('甲\n乙\n'.encode())
        self.assertEqual(formats.newline_label(meta, text), 'LF')
        text, meta = formats.decode('甲\r\n乙\r\n'.encode())
        self.assertEqual(formats.newline_label(meta, text), 'CRLF')


if __name__ == '__main__':
    unittest.main()
