# -*- coding: utf-8 -*-
"""英語の打ち違いの直し（en_typo.py・2026-10-16）。

うにさんの選択「英語の補正を強化」（2026-10-16）。5字以下の語の打ち違い、
文の中で決まる語（dont・come form・more then）、文末の語、文頭の大文字と
単独の i を直す。直さないもの（技術の語・名前・引用符の中・コード）も
ここで確かめる。例はすべて作った文。
"""
import unittest

import en_space
import en_typo
import loanword
import morphology as M


def apply(line):
    out = line
    for s, e, fix in sorted(en_space.find_missing_spaces(line), reverse=True):
        out = out[:s] + fix + out[e:]
    return out


@unittest.skipUnless(en_typo.available(), 'en_freq.json.gz required')
class EnglishTypoTest(unittest.TestCase):
    def test_short_word_slips(self):
        cases = {
            'I wnat to go home.': 'I want to go home.',
            'Tge meeting is at noon.': 'The meeting is at noon.',
            'We talked abot the plan.': 'We talked about the plan.',
            'She shouls call me back.': 'She should call me back.',
            'I have a meeting tomorrow mornung.':
                'I have a meeting tomorrow morning.',
            'We cna start now.': 'We can start now.',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)

    def test_close_rivals_are_left(self):
        # 2つの語が同じくらい使われる（ius = is / us・hwat = what / heat
        # は後者が少ないので直るが、近いものは直さない）
        for line in ('He showed ius the way.', 'It was a long dya at work.'):
            with self.subTest(line=line):
                fixed = apply(line)
                self.assertNotIn('is the way', fixed)
        self.assertIsNone(en_typo.best_word('ius'))

    def test_split_keeps_typed_letters(self):
        # 分けても読めるなら、字を落とすより分ける（hasa は has a）
        self.assertEqual(apply('He hasa cat and a dog.'), 'He has a cat and a dog.')
        self.assertEqual(apply('Iam here.'), 'I am here.')

    def test_dropped_apostrophe(self):
        cases = {
            'I dont know.': "I don't know.",
            'She doesnt care.': "She doesn't care.",
            'Im going home now.': "I'm going home now.",
            'I think youre right.': "I think you're right.",
            'I cant believe it.': "I can't believe it.",
            'You wont regret it.': "You won't regret it.",
            'Its a nice day.': "It's a nice day.",
            'Lets go to the park.': "Let's go to the park.",
            'Your welcome.': "You're welcome.",
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)
        # 語として在る形は、前後で決まるときだけ
        for line in ('The cat licked its paw.', 'She lets me drive.',
                     'Your bag is here.', 'He has a cant about him.',
                     'I was born im a small town.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_words_settled_by_neighbours(self):
        cases = {
            'I came form Osaka.': 'I came from Osaka.',
            'It is better then I thought.': 'It is better than I thought.',
            'And than we left.': 'And then we left.',
            'I went wit my friend.': 'I went with my friend.',
            'I thing so.': 'I think so.',
            'I wonder wether it will rain.': 'I wonder whether it will rain.',
            'Were are you going?': 'Where are you going?',
            'She turned of the light.': 'She turned off the light.',
            'I am looking fro a pen.': 'I am looking for a pen.',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)
        for line in ('Fill in the form now.', 'The form here is short.',
                     'Back then we were young.', 'She has a quick wit.',
                     'We were here.', 'One of the best.', 'To and fro.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_lone_i_and_sentence_capital(self):
        cases = {
            'i think so too.': 'I think so too.',
            "i'm not sure.": "I'm not sure.",
            'My sister and i went to the market.':
                'My sister and I went to the market.',
            'It rained all day. we stayed inside.':
                'It rained all day. We stayed inside.',
            'Thanks for the gift! it made my day.':
                'Thanks for the gift! It made my day.',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)
        for line in (
                # 式の中の i（変数）
                'Let i be the first index.', 'Take i and j from the list.',
                'Return an integer i such that it fits.',
                # 書き手が文頭を小文字で書いている・略語の点・数の点
                'it rained. we stayed in.', 'I bought eggs, etc. and milk.',
                'Step 1. open the box.', 'Wait... we are late.',
                'We met Mr. smith there.',
                # 文頭に来ても名前かもしれない語
                'It works. name is the file name.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_sentence_final_word(self):
        # 文を終える点の前の語も直す（前は . がくっついた記号とみなされた）
        self.assertEqual(apply('See you tomorow.'), 'See you tomorrow.')
        self.assertEqual(apply('I like it alot.'), 'I like it a lot.')
        # ファイル名や版の点はくっついた記号のまま
        for line in ('Open the file tomrow.txt today.', 'We use ver.2 now.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_left_as_written(self):
        for line in (
                # プログラムの語
                'Push an integer or a bool.', 'Check the sys settings first.',
                'Open the tty device.', 'Pack it with struct first.',
                'Then recurse into the child.', 'Load the util module.',
                # 文の中の大文字は名前
                'We met Marlet at the cafe.', 'I read a book by Kitchem.',
                # 引用符の中は挙げた語
                'The word "teh" is a common slip.',
                'I told him "dont" but he went.',
                # コード
                'x = wnat + 1', 'call foo(abot) now',
                # 重複補正が切ってあれば、2回打った字は直さず、別の語にも直さない
                'Please do not ommit the last line.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)
        # 名前の打ち違いは文の中でも直す
        self.assertEqual(apply('See you on Mondya morning.'),
                         'See you on Monday morning.')

    def test_six_letter_path_defers(self):
        # 6字以上の道（fix_english_word）は、ずっと使われやすい語へ1つの
        # 打ち違いで届くなら珍しい語へ直さない／プログラムの語は直さない
        self.assertIsNone(loanword.fix_english_word('shouls', None))
        self.assertIsNone(loanword.fix_english_word('struct', None))
        self.assertIsNone(loanword.fix_english_word('memoize', None))
        self.assertEqual(loanword.fix_english_word('mornung', None), 'morning')
        # 語尾違いの形しか無いときは直さない（覚える側は今までどおり）
        self.assertIsNone(loanword.fix_english_word('droppes', None))
        self.assertTrue(loanword.fix_english_word('droppes', None, for_learning=True))

    def test_data_file(self):
        freq = en_typo.frequencies()
        self.assertGreater(len(freq), 30000)
        self.assertGreater(en_typo.zipf('the'), en_typo.zipf('form'))
        # よくある誤字は語として載っていない
        for typo in ('teh', 'dont', 'alot', 'thier', 'recieve'):
            with self.subTest(typo=typo):
                self.assertEqual(en_typo.zipf(typo), 0)
        # よく書かれる綴り（略語・名前）は書いたとおり。dont・alot も
        # ここに入るが、別の道（line_fixes・_FORCE_SPLIT）が名指しで直す
        for word in ('tbh', 'xbox', 'dont', 'alot'):
            with self.subTest(word=word):
                self.assertTrue(en_typo.seen(word))
        for typo in ('teh', 'thier', 'recieve', 'wnat'):
            with self.subTest(typo=typo):
                self.assertFalse(en_typo.seen(typo))


@unittest.skipUnless(M.HAS_JANOME and en_typo.available(),
                     'real native dictionary required')
class EnglishTypoPipelineTest(unittest.TestCase):
    """補正の流れ全体（correction_entry.correct_line）で直ること。"""

    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state = initial()

    def setUp(self):
        from last_choice import set_active
        self.addCleanup(set_active, None)

    def run_line(self, line):
        from correction_entry import correct_line
        a = self.state
        return correct_line(line, a.store, context_vocab={}, input_method='kana',
                            dict_index=a.dict_index, decisions=a.decisions,
                            context_vec=a.context_vec)['corrected']

    def test_double_letters_inside_english_words(self):
        # 英語の語は自分で2字続ける（call・need）。継ぎ目の重なりにしない。
        # corrector._check_replacement の門の変更（補正の束 ime31）が要る。
        # それより前の corrector では直らないまま（壊れはしない）。
        import inspect
        import corrector
        excused = 'english_word and start<edge' in inspect.getsource(corrector)
        cases = {
            'She said she would cakl me back after lunch.':
                'She said she would call me back after lunch.',
            'I nede more time.': 'I need more time.',
        }
        for line, want in cases.items():
            with self.subTest(line=line, excused=excused):
                self.assertEqual(self.run_line(line), want if excused else line)

    def test_pipeline(self):
        cases = {
            'I dont know what to do.': "I don't know what to do.",
            'I have a meeting at ten tomorrow mornung.':
                'I have a meeting at ten tomorrow morning.',
            'We met at the station. i think it was noon.':
                'We met at the station. I think it was noon.',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line), want)
        for line in ('The quick brown fox jumps over the lazy dog.',
                     'Please call me when you need help.',
                     'Push an integer or a bool.'):
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line), line)


if __name__ == '__main__':
    unittest.main()
