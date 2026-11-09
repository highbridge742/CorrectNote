# -*- coding: utf-8 -*-
"""The part-of-speech display of a casual adjective form (2026-11-09 うにさん「おもしれえ の品詞が 重い の活用になっているが、
正しくは 面白い の活用」): the units the app builds for the display read おもしれえ as おもしろい (くだけた形), keep the
characters and positions as written, and ordinary lines come out exactly as before. CN_COLLOQUIAL_POS=0 is the old form.
No window; a blank vocabulary in a temporary folder."""
import os
import tempfile
import unittest
from unittest import mock


def _units(text, tokenize):
    import app
    result = dict(original=text, corrected=text, spans=[], details=[])
    return app.build_line_units(result, tokenize)


def _flat(units):
    out = []
    for u in units[1]:
        d = u if isinstance(u, dict) else getattr(u, '__dict__', {})
        out.append({k: d.get(k) for k in ('start', 'end', 'surface', 'base', 'base_form', 'pos', 'tokens') if k in d})
    return out


class ColloquialPos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import corrector
        from vocabulary import open_vocabulary
        cls.store = open_vocabulary(os.path.join(tempfile.mkdtemp(), 'vocabulary.json'))
        cls.fn = staticmethod(corrector.make_tokenizer(cls.store))      # a plain function, not bound to the test

    def tokens(self, text):
        import app
        return list(app.pos_tokenizer(self.fn)(text))

    def test_casual_form_reads_as_the_adjective(self):
        for text in ('おもしれえ', 'これはおもしれえ話だ'):
            toks = self.tokens(text)
            # the tokens are (surface, pos, reading, start, end, sure, inflection)
            got = [(t[0], t[1], t[6] if len(t) > 6 else '', t[3], t[4]) for t in toks]
            hit = [g for g in got if 'おもし' in g[0]]
            self.assertTrue(hit, got)
            self.assertEqual(hit[0][0], 'おもしれえ', got)                          # one word, as written
            self.assertTrue(hit[0][1].startswith('形容詞'), got)                   # an adjective (おもしろい), not 重い
            self.assertEqual(hit[0][2], 'くだけた形', got)
            self.assertEqual(''.join(t[0] for t in toks), text, got)              # the characters as written
            self.assertEqual(text[hit[0][3]:hit[0][4]], hit[0][0], got)            # the positions as written
            # the display units are built from them, with the same text
            shown, units = _units(text, self.fn)
            self.assertEqual(shown, text)
            self.assertTrue(units)

    def test_old_form_and_ordinary_lines_unchanged(self):
        with mock.patch.dict(os.environ, {'CN_COLLOQUIAL_POS': '0'}):
            old = [(t[0], t[1]) for t in self.tokens('おもしれえ')]
        self.assertNotIn('おもしれえ', [w for w, _ in old], old)                    # the old form: おもし｜れ｜え
        for text in ('今日は寒い', '重い荷物', '会議の資料を作る。', 'これは面白い話だ'):
            with mock.patch.dict(os.environ, {'CN_COLLOQUIAL_POS': '0'}):
                old_units = _units(text, self.fn)
                old_toks = list(self.fn(text))
            new_units = _units(text, self.fn)
            new_toks = self.tokens(text)
            self.assertEqual(new_toks, old_toks, text)
            self.assertEqual(repr(new_units), repr(old_units), text)


class ColloquialPosChild(unittest.TestCase):
    """The analysis child builds the display units with the same wrapper (colloquial_pos.pos_tokenizer)."""
    @classmethod
    def setUpClass(cls):
        import analysis_worker as W
        from tests_analysis_async import initial
        a = initial()
        cls.rt = W.Runtime()
        state = W.snapshot(a)
        state['_state_identity'] = W.state_key(a)
        cls.rt.set_state(state)

    def units(self, text):
        result = dict(original=text, corrected=text, spans=[], details=[])
        return self.rt.execute(dict(kind='suspect_units', result=result, attested=[]))

    def test_child_reads_the_casual_form_as_one_adjective(self):
        got = self.units('これはおもしれえ話だ')
        hit = [u for u in got if 'おもし' in u['text']]
        self.assertEqual(len(hit), 1, got)
        self.assertEqual((hit[0]['text'], hit[0]['start'], hit[0]['end']), ('おもしれえ', 3, 8), got)
        self.assertTrue(hit[0]['pos'].startswith('形容詞'), got)
        self.assertEqual(hit[0]['infl'], 'くだけた形', got)
        self.assertEqual(hit[0]['base'], 'おもしろい', got)                    # the description: おもしろい の活用
        with mock.patch.dict(os.environ, {'CN_COLLOQUIAL_POS': '0'}):
            old = self.units('これはおもしれえ話だ')
        self.assertNotIn('おもしろい', [u.get('base') for u in old], old)

    def test_child_ordinary_lines_unchanged(self):
        for text in ('今日は寒い', '重い荷物', '会議の資料を作る。', 'これは面白い話だ'):
            new = self.units(text)
            with mock.patch.dict(os.environ, {'CN_COLLOQUIAL_POS': '0'}):
                old = self.units(text)
            self.assertEqual(new, old, text)

class ColloquialPosExplain(unittest.TestCase):
    """The part-of-speech description (right-click) says おもしれえ is a casual form of おもしろい; other words as before."""
    def lines(self, text, **kw):
        import corrector, explain
        from vocabulary import open_vocabulary
        explain._TOK_CACHE.clear()
        store = open_vocabulary(os.path.join(tempfile.mkdtemp(), 'vocabulary.json'))
        return explain.pos_lines(text, corrector.make_tokenizer(store), store=store, **kw)

    def test_description(self):
        kw = dict(pos_hint='形容詞:自立', infl_hint='くだけた形', atomic_hint=True, known_hint=False,
                  prev_text='は', next_text='話', source_context=None)
        got = self.lines('おもしれえ', **kw)
        self.assertEqual(got, ['イ形容詞・くだけた形／原形 おもしろい'], got)
        with mock.patch.dict(os.environ, {'CN_COLLOQUIAL_POS': '0'}):
            old = self.lines('おもしれえ', **kw)
        self.assertNotEqual(old, got, old)
        for word in ('寒い', '重い', '面白い', '会議'):
            new = self.lines(word)
            with mock.patch.dict(os.environ, {'CN_COLLOQUIAL_POS': '0'}):
                before = self.lines(word)
            self.assertEqual(new, before, word)


if __name__ == '__main__':
    unittest.main()
