# -*- coding: utf-8 -*-
"""Exact written lexical evidence; never approximate matches or whole-line immunity."""
import unittest
from unittest.mock import patch
import morphology as M
import general_words as G

class AttestedNounTests(unittest.TestCase):
    def token(self,word,start,known=False,pos='名詞'):
        return M.Token(word,pos,word,word,start,start+len(word),known,'一般','')

    def test_exact_entry_restores_reading_and_positions(self):
        parts=[self.token('爽健美',2),self.token('茶',5,True)]
        result=M._restore_attested_nouns('前の爽健美茶',parts)
        self.assertEqual([(t.surface,t.reading,t.start,t.end,t.pos_sub,t.has_reading) for t in result],
                         [('爽健美茶','そうけんびちゃ',2,6,'固有名詞:一般',True)])
        self.assertEqual(parts[0].surface,'爽健美')
        self.assertFalse(parts[0].has_reading)

    def test_no_substring_gap_or_non_nominal_merge(self):
        for line,parts in (
            ('爽健美茶超',[self.token('爽健美茶超',0)]),
            ('爽健美 茶',[self.token('爽健美',0),self.token('茶',4,True)]),
            ('爽健美茶',[self.token('爽健美',0,pos='動詞'),self.token('茶',3,True)]),
            ('爽鍵美茶',[self.token('爽鍵美',0),self.token('茶',3,True)]),
        ):
            with self.subTest(line=line):
                self.assertEqual(M._restore_attested_nouns(line,parts),parts)

    def test_longest_exact_boundary_and_following_tokens(self):
        end=self.token('がを',7,True,pos='助詞')
        parts=[self.token('アソート',0),self.token('メント',4),end]
        result=M._restore_attested_nouns('アソートメントがを',parts)
        self.assertEqual(result[0].surface,'アソートメント')
        self.assertIs(result[1],end)

    def test_common_and_named_nouns_are_distinct(self):
        self.assertTrue(G.is_general('アソート'))
        self.assertTrue(G.is_general('マイバッグ'))
        self.assertFalse(G.is_general('爽健美茶'))
        self.assertIsNone(G.attested_noun('爽健美'))
        self.assertIsNone(G.attested_noun('爽健美茶','そうけんみちゃ'))
        self.assertIsNotNone(G.attested_noun('爽健美茶','そうけんびちゃ'))

    def test_category_apposition_requires_the_attested_membership(self):
        import oddness
        for label in ('商品','銘柄','飲料'):
            self.assertTrue(G.attested_apposition(label,'爽健美茶'))
            with patch.object(oddness,'_load',return_value={}):
                self.assertTrue(oddness.can_join(label,'名詞:一般',
                                                '爽健美茶','名詞:固有名詞:一般'))
        self.assertFalse(G.attested_apposition('飲料','マイバッグ'))
        self.assertFalse(G.attested_apposition('商品','爽鍵美茶'))
        self.assertFalse(G.attested_apposition('作者','爽健美茶'))
        self.assertFalse(G.attested_apposition('人名','伊右衛門'))

    def test_legacy_splitter_uses_the_same_attested_word_roster(self):
        import corrector
        self.assertTrue(corrector._d42_known_unit('アソート',None))
        self.assertTrue(corrector._d42_known_unit('爽健美茶',None))
        self.assertTrue(corrector._d42_known_unit('クリップボード',None))
        self.assertFalse(corrector._d42_known_unit('爽鍵美茶',None))

    def test_parser_proper_noun_guess_is_not_attestation(self):
        import oddness
        class Index:
            def is_world_reading(self,rd):return False
        self.assertTrue(oddness._proper_noun_is_trusted(
            ('爽健美茶','名詞:固有名詞:一般','そうけんびちゃ',0,4,True),None,Index()))
        self.assertFalse(oddness._proper_noun_is_trusted(
            ('爽鍵美茶','名詞:固有名詞:一般','そうけんびちゃ',0,4,True),None,Index()))

    @unittest.skipUnless(M.HAS_JANOME, "Requires real native tokenization")
    def test_reviewed_unread_katakana_shares_exact_source_metadata(self):
        import reading_segments as R
        source='資料を保存したフォルダ'
        parts=M.tokenize(source);word=next(t for t in parts if t.surface=='フォルダ')
        self.assertEqual((word.reading,word.pos_sub,word.start,word.end,word.has_reading),
                         ('ふぉるだ','一般',7,11,True))
        self.assertEqual(R.native_surface_nominal_heads(source),('フォルダ',))
    def test_reviewed_metadata_does_not_forge_native_rows_or_change_roster(self):
        words=('フォルダ','ステータスバー','クリップボード')
        before={word:M.dictionary_inflections(word) for word in words};roster=G.GENERAL_WORDS
        for word in words:
            parts=M._restore_attested_nouns(word,[self.token(word,0)])
            if not before[word]:
                self.assertEqual((parts[0].reading,parts[0].has_reading),(M.katakana_to_hiragana(word),True))
        self.assertEqual(before,{word:M.dictionary_inflections(word) for word in words})
        self.assertIs(G.GENERAL_WORDS,roster)
    def test_reviewed_noun_still_requires_original_whole_nominal_boundaries(self):
        for source,parts in (
            ('プネラフォルダ',[self.token('プネラフォルダ',0)]),
            ('フォルダプネラ',[self.token('フォルダプネラ',0)]),
            ('フォル ダ',[self.token('フォル',0),self.token('ダ',4)]),
            ('フォルダ',[self.token('フォル',0,pos='動詞'),self.token('ダ',3)]),
        ):
            with self.subTest(source=source):self.assertEqual(M._restore_attested_nouns(source,parts),parts)
    def test_known_native_name_keeps_its_original_reading(self):
        word=self.token('フォルダ',0,known=True);word.reading='native_name';word.pos_sub='固有名詞:一般'
        native=(('名詞,固有名詞,一般,*','*','フォルダ','native_name'),)
        with patch.object(M,'dictionary_inflections',return_value=native):
            result=M._restore_attested_nouns('フォルダ',[word])
        self.assertIs(result[0],word)
        self.assertEqual((word.reading,word.pos_sub),('native_name','固有名詞:一般'))

if __name__=='__main__':unittest.main()
