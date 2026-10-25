"""英文の半角スペースの入れ忘れ（項目48-ES・2026-10-14）。"""
import unittest

import en_space


def apply(line):
    out = line
    for s, e, fix in sorted(en_space.find_missing_spaces(line), reverse=True):
        out = out[:s] + fix + out[e:]
    return out


class MissingSpaceTest(unittest.TestCase):
    def test_splits_missing_space(self):
        cases = {
            'Thisis a pen.': 'This is a pen.',
            'Iam a student.': 'I am a student.',
            'I wantto go home.': 'I want to go home.',
            'Look atthe sky.': 'Look at the sky.',
            'What isthis?': 'What is this?',
            'Let us meetat the station.': 'Let us meet at the station.',
            'Welcometo Japan.': 'Welcome to Japan.',
            'Do yougo to school?': 'Do you go to school?',
            'Letme know when you arrive.': 'Let me know when you arrive.',
            'Attachedis the file you asked for.':
                'Attached is the file you asked for.',
            'It was quitea long day.': 'It was quite a long day.',
            'He hasa cat and a dog.': 'He has a cat and a dog.',
            'Ireally like it.': 'I really like it.',
            'everytime I see it.': 'every time I see it.',
            'They like eachother very much.': 'They like each other very much.',
            'Takeit easy, please.': 'Take it easy, please.',
            'Tellus more about it.': 'Tell us more about it.',
            'comeon, we are late.': 'come on, we are late.',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)

    def test_frequent_pairs_beat_dictionary(self):
        # 辞書に語として載っていても、よくある入れ忘れは直す（Hunspell の REP）
        cases = {
            'Thankyou for your help.': 'Thank you for your help.',
            '今日はThankyouと言った': '今日はThank youと言った',
            'noone came to the party.': 'no one came to the party.',
            'ofcourse it is fine.': 'of course it is fine.',
            'infact we did it.': 'in fact we did it.',
        }
        for line, want in cases.items():
            with self.subTest(line=line):
                self.assertEqual(apply(line), want)
        # コードの行では直さない
        self.assertEqual(apply('    atleast = len(args) - defcount'),
                         '    atleast = len(args) - defcount')

    def test_order_fix_comes_first(self):
        # 入れ替えで届く語があれば、スペースは考えない
        self.assertEqual(apply('teh cat is cute.'), 'the cat is cute.')
        self.assertEqual(apply('thier house is big.'), 'their house is big.')
        # 大文字の頭は動かさない（Iam を aim にしない）
        self.assertEqual(apply('Iam here.'), 'I am here.')
        # 入れ替えの先が機能語でないときは直さない（acre→care・bets→best）
        for line in ('the acre is wide.', 'he bets on it.', 'tsar and odor'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_valid_english_untouched(self):
        for line in ('the quick brown fox', 'I like GitHub and iPhone.',
                     'facebook and youtube are popular.',
                     'I use playstation every day.',
                     'The username is wrong.', 'It is a nice setup.',
                     'Kubernetes is hard.', "I'm going home.",
                     'This license is quite different.',
                     'suitable for input to text formatters',
                     # 5字以下の語（固有名詞と短い語の名簿・seed_english_names）
                     'We ate meat and goat.', 'The acre has an odor.',
                     'To and fro.', 'Tis the season.', 'It sat atop the hill.',
                     'a meme and a dodo', 'The onus is on us.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_dropped_apostrophe_is_not_split(self):
        # アポストロフィを落とした短縮形は割らない。2026-10-16 からは
        # en_typo が ' を戻す（うにさんの選択「英語の補正を強化」）
        self.assertEqual(apply('arent you coming'), "aren't you coming")
        self.assertEqual(apply('they werent here'), "they weren't here")

    def test_proper_nouns_untouched(self):
        for line in ('Justin went home.', 'I met Justin yesterday.',
                     'Norway is cold.', 'Toby and Avery came.',
                     'Hasan said hi.', 'Iran and Ivan.', 'Paris is beautiful.',
                     'Curtis is here.', 'Allison is late.',
                     'Herman Melville wrote it.', 'Socrates said so.',
                     'Mayfield is a town.', 'Willis is tall.',
                     'Haddad came.', 'Grayson and Easton met Menon.',
                     'Markus and Maximus came.',
                     # 文の途中の大文字は固有名詞（Passat・Costas）
                     'I drive a Passat today.', 'We met Costas there.',
                     # 文頭でも、頭が文を始める語でなければ割らない
                     'Passat is a car.', 'Loomis is here.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_word_order_gate(self):
        # 機能語どうしでも、英語の語順として並ばない組は割らない
        for line in ('Isis and Ion were gods.', 'hehe and toto are here.',
                     'Toby is my dog.', 'Indo is short for it.',
                     'doin and goin are slang.', 'Theon is here.',
                     'Justus came late.', 'lookin good today',
                     # 冠詞の門（a very・an on・a ran）
                     'Avery and Anton are here.', 'Aran is an island.',
                     'It isan pen.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)
        # I の頭は、I の後ろに来る語のときだけ
        self.assertEqual(apply('Iwant a cup of tea.'), 'I want a cup of tea.')
        self.assertEqual(apply('Iran is a country.'), 'Iran is a country.')

    def test_code_and_names_untouched(self):
        for line in ('if isinstance(x, int):', 'self.lineno = lineno',
                     'the lineno of the frame', 'call onerror when it fails',
                     'see the infile and outfile', 'bytestring is a type',
                     'use `thisline` here', 'Pythonで書いたcodeをtest',
                     'for aname, value in attrs.items():',
                     'def isId(self, aname):', '    "atime": float,',
                     'return map(str.strip, alist)',
                     'hasattr(fileobj, "readinto")',
                     'timeit is a module', 'the mixin class', 'see the readme',
                     'I use aws and goto.'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_romaji_untouched(self):
        for line in ('shoruiga', 'anata to watashi', 'kore wa pen desu',
                     'locale.atof のatofは', '日本語のdesuは'):
            with self.subTest(line=line):
                self.assertEqual(apply(line), line)

    def test_lone_function_words_in_japanese(self):
        # 日本語の中の1語でも、機能語だけに分かれるなら直す
        self.assertEqual(apply('今日はThisisです'), '今日はThis isです')
        self.assertEqual(apply('英語でItwasと書く'), '英語でIt wasと書く')

    def test_learning_gate(self):
        self.assertTrue(en_space.would_split('Thisis'))
        self.assertTrue(en_space.would_split('thankyou'))
        self.assertFalse(en_space.would_split('planetarium'))
        self.assertFalse(en_space.would_split('GitHub'))
        self.assertFalse(en_space.would_split('Justin'))
        self.assertFalse(en_space.would_split('meat'))


if __name__ == '__main__':
    unittest.main()
