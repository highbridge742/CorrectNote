"""右クリックの「－ 品詞判定 －」が、英字の語に英語の品詞を言う（2026-10-15）。

うにさん「右クリックの品詞判定に、判定した品詞を表示するようにして
ください」。画面の品詞ごとの色は en_pos で英語の品詞を付けている
（名詞・動詞…）のに、右クリックは「英字（解析は品詞を言えない）」と
しか言わなかった。色と同じ判定（`en_pos.judge`）を、色と同じく行の
前後の語から引いて言う。

ここの例はすべて作った文（ネットの文は使わない）。
"""
import unittest

import corrector
import en_pos
import explain
import pos_font
import units


_LINES = (
    "I don't think it's the state of the power.",
    'In general the history of this state is a simple story.',
    "We’re home at ten o'clock.",
    'これは simple story です。',
    'They state a clear rule.',
)

_RESULT_KEYS = ('spans', 'details', 'original_spans')


def _result(line):
    result = {'original': line, 'corrected': line}
    for key in _RESULT_KEYS:
        result[key] = []
    return result


def _row(label):
    """品詞判定の1行が言う「色の行」（`色は○○の行` があればそれ）。"""
    if label.startswith('英字'):
        return '英字'
    name = label.split('（', 1)[0]
    if '色は' in label:
        return label.split('色は', 1)[1].split('の行', 1)[0]
    return name


class EnglishPosMenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tok = staticmethod(corrector.make_tokenizer(None))

    def _lines_for(self, unit):
        return explain.pos_lines(
            unit['text'], self.tok, pos_hint=unit.get('pos') or '',
            infl_hint=unit.get('infl') or '',
            atomic_hint=bool(unit.get('atomic')),
            known_hint=bool(unit.get('known')),
            prev_text=unit.get('prev') or '', next_text=unit.get('next') or '',
            source_context=unit.get('analysis_context'))

    def _labels(self, line, builder=units.build_suspect_units):
        text, built = builder(_result(line), self.tok)
        self.assertEqual(text, line)
        out = {}
        for unit in built:
            if pos_font._LATIN.fullmatch(unit['text']):
                out.setdefault(unit['text'], []).append(
                    (unit['start'], self._lines_for(unit)))
        return out

    def test_words_say_their_english_part_of_speech(self):
        got = self._labels(_LINES[0])
        self.assertEqual(got['I'][0][1], ['代名詞（英語。色は名詞の行）'])
        self.assertEqual(got['think'][0][1], ['動詞（英語）'])
        self.assertEqual(got['the'][0][1], ['冠詞（英語。色は連体詞の行）'])
        self.assertTrue(got['state'][0][1][0].startswith('名詞（英語'))
        self.assertEqual(got['of'][0][1], ['前置詞（英語。色は助詞の行）'])
        self.assertEqual(got['power'][0][1], ['名詞（英語）'])
        # 短縮形は、つないで引いた形を添える
        self.assertEqual(got['don'][0][1], ["助動詞（英語。don't の一部）"])
        self.assertEqual(got['t'][0][1], ["助動詞（英語。don't の一部）"])
        self.assertEqual(got['s'][0][1], ["助動詞（英語。it's の一部）"])
        curly = self._labels(_LINES[2])
        self.assertEqual(curly['re'][0][1], ['助動詞（英語。We’re の一部）'])
        self.assertTrue(curly['We'][0][1][0].startswith('代名詞'))

    def test_the_menu_says_what_the_colours_show(self):
        """色（`pos_font.spans`）と右クリックの言う行が、どの英単語でも同じ。"""
        for line in _LINES:
            runs = pos_font.spans(line, self.tok(line))
            for builder in (units.build_suspect_units, units.build_line_units):
                for word, seen in self._labels(line, builder).items():
                    for start, lines in seen:
                        kinds = {kind for kind, a, z in runs if a <= start < z}
                        self.assertEqual(len(lines), 1, (line, word))
                        self.assertEqual({_row(lines[0])}, kinds,
                                         (line, word, lines))

    def test_neighbours_decide_like_the_colours(self):
        # 同じ state でも、the の後ろは名詞、They の後ろは動詞
        noun = self._labels(_LINES[1])['state'][0][1][0]
        verb = self._labels(_LINES[4])['state'][0][1][0]
        self.assertTrue(noun.startswith('名詞'), noun)
        self.assertTrue(verb.startswith('動詞'), verb)

    def test_ranges_relabel_only_the_english_lines(self):
        line = _LINES[3]
        built = units.build_suspect_units(_result(line), self.tok)[1]
        start = line.index('simple')
        unit = units.make_range_unit(line, built, start, start + len('simple story'))
        got = self._lines_for(unit)
        self.assertIn('simple ＝ 形容詞（英語）', got)
        self.assertIn('story ＝ 名詞（英語）', got)
        # 日本語を含む範囲は、日本語の行が今までどおり
        mixed = explain.pos_lines('これは simple', self.tok)
        self.assertEqual(mixed[:2], explain._pos_lines('これは simple', self.tok)[:2])
        self.assertEqual(mixed[-1], 'simple ＝ 形容詞（英語）')

    def test_without_line_context_the_word_alone_is_judged(self):
        self.assertEqual(explain.pos_lines('power', self.tok), ['名詞（英語）'])
        self.assertEqual(explain.pos_lines('the state', self.tok)[-1],
                         'state ＝ 名詞（英語。ほかの読み：動詞）')

    def test_unknown_and_dotted_words_stay_english_letters(self):
        self.assertEqual(explain.pos_lines('Zorbleton', self.tok),
                         ['英字（英語の品詞辞書に無い語）'])
        got = explain.pos_lines('see file_name.txt', self.tok)
        self.assertEqual(got[0], 'see ＝ 動詞（英語）')
        self.assertTrue(all('. や _ を含む並び' in x for x in got
                            if x.startswith(('file ', 'name ', 'txt '))), got)

    def test_japanese_words_are_untouched(self):
        line = '今日は本を読みました。'
        for unit in units.build_suspect_units(_result(line), self.tok)[1]:
            self.assertNotIn('analysis_context', unit, unit['text'])
            self.assertEqual(self._lines_for(unit), explain._pos_lines(
                unit['text'], self.tok, pos_hint=unit.get('pos') or '',
                infl_hint=unit.get('infl') or '',
                atomic_hint=bool(unit.get('atomic')),
                known_hint=bool(unit.get('known')),
                prev_text=unit.get('prev') or '',
                next_text=unit.get('next') or ''))

    def test_categories_are_judge_by_row(self):
        for line in _LINES:
            spans = [m.span() for m in pos_font._LATIN.finditer(line)]
            judged = en_pos.judge(line, spans)
            self.assertEqual(en_pos.categories(line, spans),
                             [en_pos.CATEGORY[code] if code else en_pos.UNKNOWN
                              for _codes, code, _whole in judged])


if __name__ == '__main__':
    unittest.main()
