# -*- coding: utf-8 -*-
"""Newline searches exclude outer blank lines while normal searches remain literal."""
import unittest
import search as S

class SearchBoundaryTests(unittest.TestCase):
    def test_newline_scope_keeps_inner_blank_lines_and_counts(self):
        text='\n \t\n 先頭😀 \t\n\n末尾 \t\n\t \n\n'
        first=text.index(' 先頭')
        end=text.index('\n',text.index('末尾'))
        self.assertEqual(S.content_line_span(text),(first,end))
        wanted=[(i,i+1) for i in range(first,end) if text[i]=='\n']
        for query,regex in (('\n',False),(r'\n',True),(r'\r?\n',True)):
            pattern=S.build_pattern(query,regex=regex)
            with self.subTest(query=query):
                self.assertEqual(S.find_all(text,pattern),wanted)
                self.assertEqual(S.count_matches(text,pattern),2)
                self.assertEqual(S.find_next(text,pattern,0),wanted[0])
                self.assertEqual(S.find_next(text,pattern,len(text),backwards=True),wanted[-1])
                self.assertEqual(S.find_next(text,pattern,len(text)),wanted[0])
                self.assertIsNone(S.find_next(text,pattern,len(text),wrap=False))
                self.assertEqual(S.replace_all(text,pattern,'|',regex=regex),
                                 ('\n \t\n 先頭😀 \t||末尾 \t\n\t \n\n',2))

    def test_blank_document_or_single_content_line_has_no_newline_match(self):
        for text in ('','\n\n',' \t\n　\n','\n\n内容\n\n','\t\n😀 \t\n  \n'):
            with self.subTest(text=text):
                pattern=S.build_pattern('\n')
                self.assertEqual(S.find_all(text,pattern),[])
                self.assertEqual(S.replace_all(text,pattern,''),(text,0))

    def test_whole_multiline_match_cannot_cross_outer_boundary(self):
        text='\n\n甲\n乙\n\n'
        for query in ('\n甲','乙\n','\n\n'):
            with self.subTest(query=query):
                self.assertEqual(S.find_all(text,S.build_pattern(query)),[])
        self.assertEqual(S.find_all(text,S.build_pattern('甲\n乙')),[(2,5)])
        self.assertEqual(S.replace_all(text,S.build_pattern('甲\n乙'),'丙'),('\n\n丙\n\n',1))

    def test_single_replacement_rejects_manual_selection_of_outer_newline(self):
        text='\n甲\n乙\n'
        pattern=S.build_pattern('\n')
        for span in ((0,1),(4,5)):
            self.assertEqual(S.replace_one(text,pattern,span,'X'),(text,span[1]))
        self.assertEqual(S.replace_one(text,pattern,(2,3),'X'),('\n甲X乙\n',3))

    def test_replace_all_uses_original_scope_even_when_last_content_is_deleted(self):
        text='\nA\nB\n\n'
        pattern=S.build_pattern(r'(?m)^B$|\n',regex=True)
        self.assertEqual(S.replace_all(text,pattern,'',regex=True),('\nA\n\n',2))

    def test_tabs_spaces_and_inserted_newlines_stay_available(self):
        text='\t\nA\n \t\n'
        self.assertEqual(S.find_all(text,S.build_pattern('\t')),[(0,1),(5,6)])
        self.assertEqual(S.replace_all(text,S.build_pattern('A'),'\nX\n'),
                         ('\t\n\nX\n\n \t\n',1))
        self.assertEqual(S.replace_all('\n \n',S.build_pattern(' '),'X'),('\nX\n',1))

    def test_regex_lookaround_backreferences_and_crlf(self):
        text='\r\nA\r\nB\r\n'
        pattern=S.build_pattern(r'(?<=A)(\r?\n)(?=B)',regex=True)
        self.assertEqual(S.find_all(text,pattern),[(3,5)])
        self.assertEqual(S.replace_one(text,pattern,(3,5),r'\1\1',regex=True),
                         ('\r\nA\r\n\r\nB\r\n',7))
        self.assertEqual(S.replace_all(text,pattern,r'\1\1',regex=True),
                         ('\r\nA\r\n\r\nB\r\n',1))
        with self.assertRaises(S.SearchError):
            S.replace_all(text,pattern,r'\2',regex=True)

if __name__=='__main__':unittest.main()

