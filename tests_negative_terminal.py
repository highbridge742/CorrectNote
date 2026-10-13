import unittest
from unittest.mock import patch
import morphology as M,ime_spelling as I

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NegativeTerminalTests(unittest.TestCase):
    def test_native_terminal_senses_and_trailing_space(self):
        for text in ('読まないこと','知らないよう','読まないまま','食べない時','読まないもの ', '読まない事\u3000'):
            self.assertIs(M.native_dependent_noun_ending_possible(text),True,text)
        for text in ('量がまし','資料を確認','読みまし','学生だ','',' '):
            self.assertIs(M.native_dependent_noun_ending_possible(text),False,text)

    def test_changed_range_may_begin_inside_the_terminal_noun(self):
        text='読まないこと';self.assertTrue(I._crosses_negative_attachment(text,5,6))
        text='読まないまま';self.assertTrue(I._crosses_negative_attachment(text,5,6))

    def test_unknown_backend_or_dictionary_failure_preserves_unknown(self):
        with patch.object(M,'HAS_JANOME',False):
            self.assertIsNone(M.native_dependent_noun_ending_possible('量がまし'))
        with patch.object(M._TOKENIZER.sys_dic,'lookup',side_effect=SystemExit(1)):
            self.assertIsNone(M.native_dependent_noun_ending_possible('量がまし'))
        with patch.object(M._TOKENIZER,'user_dic',object()):
            self.assertIsNone(M.native_dependent_noun_ending_possible('量がまし'))

    def test_unknown_grammar_or_spelling_restoration_does_not_get_false(self):
        with patch.object(M._TOKENIZER.sys_dic,'unknowns',{'K':[(1,1,1,'名詞,非自立,一般,*')]}):
            self.assertIsNone(M.native_dependent_noun_ending_possible('ぷねら'))
        for text in ('読みましょぅ','説明しょないこと','ぅ量がまし'):
            self.assertIsNone(M.native_dependent_noun_ending_possible(text))

    def test_missing_terminal_proof_keeps_original_scan(self):
        original=M.tokenize;seen=[]
        def observe(text):seen.append(text);return original(text)
        with patch.object(M,'native_dependent_noun_ending_possible',return_value=None),patch.object(M,'tokenize',side_effect=observe):
            self.assertTrue(I._crosses_negative_attachment('読まないこと',2,6))
        # The unchanged original loop already proves the shorter
        # adjective + dependent noun fragment at its first beginning.
        self.assertEqual(seen[-1],'ないこと')

    def test_impossible_terminal_does_not_retokenize_every_prefix(self):
        text='資料を確認しました。'*48+'量がましています';start=text.rindex('まし');end=start+2
        original=M.tokenize;seen=[]
        def observe(text):seen.append(text);return original(text)
        with patch.object(M,'tokenize',side_effect=observe):
            self.assertFalse(I._crosses_negative_attachment(text,start,end))
        # Original independent-object proofs may still tokenize the source;
        # none should walk each possible beginning of the ending prefix.
        self.assertLess(len(seen),10,len(seen))

if __name__=='__main__':unittest.main()
