# -*- coding: utf-8 -*-
import unittest
import oddness as O

class ShortcutCaseTests(unittest.TestCase):
    def spans(self,prefix,tail='表示',pos='名詞:サ変接続',reading='で'):
        n=len(prefix)
        return O.shortcut_case_spans(prefix+'出'+tail,[
            ('出','名詞:接尾:一般',reading,n,n+1,True,''),
            (tail,pos,'ひょうじ',n+1,n+1+len(tail),True,'')])

    def test_modifier_and_key_combinations(self):
        for prefix in ('Ctrl+S','Alt+Tab','Ctrl+Shift+F12','Win+R','Command+Space'):
            self.assertEqual(self.spans(prefix),[(len(prefix),len(prefix)+1)])

    def test_nonshortcut_identifiers_are_not_repaired(self):
        for prefix in ('a+b','商品A','MyCtrl+S','Ctrl+UnknownKey','Alt+Tab '):
            self.assertEqual(self.spans(prefix),[])

    def test_no_place_names_or_functional_tails(self):
        self.assertEqual(self.spans('Ctrl+S',pos='名詞:固有名詞:地域:一般'),[])
        self.assertEqual(self.spans('Ctrl+S',tail='の',pos='助詞:連体化'),[])
        self.assertEqual(self.spans('Ctrl+S',reading='しゅつ'),[])

    def test_does_not_split_existing_word(self):
        text='Ctrl+S出力'
        self.assertEqual(O.shortcut_case_spans(text,[('出力','名詞:サ変接続','しゅつりょく',6,8,True,'')]),[])

if __name__=='__main__':unittest.main()
