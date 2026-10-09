# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
from text_links import find_links,Link,open_link


class LinkDetectionTests(unittest.TestCase):
    def test_urls_keep_balanced_path_and_trim_prose(self):
        text='案内(https://example.test/a(b))。次は「https://例え.test/資料?q=一」。'
        links=find_links(text)
        self.assertEqual([x.target for x in links],
            ['https://example.test/a(b)','https://例え.test/資料?q=一'])
        self.assertTrue(all(text[x.start:x.end]==x.target and x.kind=='url' for x in links))
        self.assertEqual(find_links('https://[::1]/資料')[0].target,'https://[::1]/資料')

    def test_absolute_paths_quotes_spaces_and_unc(self):
        text='😀 '+r'C:\資料\メモ.txt。 "C:\Program Files\Note\a.txt" '+r'\\server\share\資料.txt'+"\n'C:/Other Folder/test.txt'"
        links=find_links(text)
        self.assertEqual([x.target for x in links],[r'C:\資料\メモ.txt',r'C:\Program Files\Note\a.txt',
            r'\\server\share\資料.txt','C:/Other Folder/test.txt'])
        self.assertTrue(all(text[x.start:x.end]==x.target and x.kind=='path' for x in links))
        self.assertEqual(find_links(r'C:\one.txt D:\two.txt')[1].target,r'D:\two.txt')

    def test_incomplete_ambiguous_and_special_paths_are_not_links(self):
        for text in ('http://','https:///a','www.example.test','../file.txt','C:relative',
                     r'\\server',r'\\?\C:\device',r'\\.\pipe\x','javascript:alert(1)',
                     'https://bad\x00host/x','aC:\\file'):
            with self.subTest(text=text):self.assertEqual(find_links(text),())
        self.assertEqual(find_links('"https://example.test/a b"'),())
        self.assertEqual(find_links('https://example.test/C:/x')[0].kind,'url')

    def test_detection_never_opens_and_explicit_opener_dispatches_once(self):
        with patch('os.startfile',create=True) as files,patch('webbrowser.open',return_value=True) as browser:
            links=find_links('https://example.test/ '+r'C:\a.txt')
            files.assert_not_called();browser.assert_not_called()
            open_link(links[0]);browser.assert_called_once_with('https://example.test/')
            files.assert_not_called()
            open_link(links[1]);files.assert_called_once_with(r'C:\a.txt')


if __name__=='__main__':unittest.main()
