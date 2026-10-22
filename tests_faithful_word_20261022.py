"""IME がそのまま出す漢字の語は、異様さが語の外にあるとき替えない（2026-10-22・画面の報告から。例文は作った文）"""
import unittest
from unittest import mock
import ime_language, ime_candidates
from tests_analysis_async import initial
from correction_entry import correct_line

CONV = {'さっし': '察し', 'せんぱいのいとをさっしてーんじを': '先輩の糸を察してーん時を'}


class _FakeIME:
    available = True
    error = None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def close(self): pass
    def convert(self, reading): return CONV.get(reading, reading)
    def convert_words(self, reading): return None
    def reverse_words(self, s): return None
    def phonetic(self, s): return None
    def candidates(self, reading): return None


class FaithfulWordTests(unittest.TestCase):
    def run_line(self, line):
        st = initial()
        with mock.patch.object(ime_language, 'JapaneseIME', _FakeIME), \
             mock.patch.object(ime_candidates, 'SearchCandidates', _FakeIME):
            return correct_line(line, st.store, context_vocab={}, input_method='kana', dict_index=st.dict_index,
                                decisions=st.decisions, context_vec=st.context_vec)['corrected']

    def test_faithful_verb_before_odd_tail_is_kept(self):
        # 察し は IME が さっし から出す形。後ろの ーん時 の異様さで 刺し に替えない
        got = self.run_line('先輩の糸を察してーん時を')
        self.assertNotIn('刺し', got)
        self.assertIn('察し', got)



class KanaSuffixTailTests(unittest.TestCase):
    def test_noun_with_kana_suffix_is_seen(self):
        # 漢字の名詞＋かなの接尾（待機＋ちゅう）は書いた複合語。接尾だけを別の接尾に替える戻しの対象を見分ける
        import morphology
        import last_keystroke as L
        line = '待機ちゅう'
        self.assertEqual(L._kana_suffix_tail(list(morphology.tokenize(line)), 0, len(line), line), 'ちゅう')
        self.assertTrue(L._suffix_with_function('ちょう'))
        self.assertFalse(L._suffix_with_function('ゅうき'))


if __name__ == '__main__':
    unittest.main()
