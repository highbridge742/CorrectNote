# -*- coding: utf-8 -*-
"""文変換の逆向きで使う日本語の述語の活用（2026-10-26）。"""

_GODAN = {  # 終わりの字 → (あ段, い段, え段, て形)
    'う': ('わ', 'い', 'え', 'って'), 'く': ('か', 'き', 'け', 'いて'), 'ぐ': ('が', 'ぎ', 'げ', 'いで'),
    'す': ('さ', 'し', 'せ', 'して'), 'つ': ('た', 'ち', 'て', 'って'), 'ぬ': ('な', 'に', 'ね', 'んで'),
    'ぶ': ('ば', 'び', 'べ', 'んで'), 'む': ('ま', 'み', 'め', 'んで'), 'る': ('ら', 'り', 'れ', 'って'),
}


class Verb:
    def __init__(self, word, conj, kind):
        self.word, self.conj, self.kind = word, conj, kind

    def stems(self):
        """(否定の語幹, 連用形, て形, 可能の形, 受け身の形)"""
        w, c = self.word, self.conj
        if self.kind == 'suru' or c == 'suru':
            base = w[:-2] if w.endswith('する') else w
            return base + 'し', base + 'し', base + 'して', base + 'できる', base + 'される'
        if c == 'kuru' or w in ('来る', 'くる'):
            h = '来' if w.startswith('来') else ''
            return (h or 'こ'), (h or 'き'), (h or 'き') + 'て', (h or 'こ') + 'られる', (h or 'こ') + 'られる'
        if c == 'ichidan':
            s = w[:-2] + 'じ' if w.endswith('ずる') else w[:-1]
            return s, s, s + 'て', s + 'られる', s + 'られる'
        last = w[-1]
        a, i, e, te = _GODAN.get(last, ('ら', 'り', 'れ', 'って'))
        s = w[:-1]
        if c == 'iku':
            te = 'って'
        if c == 'aru':
            i = 'い'
        return s + a, s + i, s + te, s + e + 'る', s + a + 'れる'

    def form(self, past=False, neg=False, prog=False, want=False, can=False, passive=False):
        if self.kind in ('adj', 'na'):
            return _adj_form(self.word, self.kind, past, neg)
        nai, ren, te, pot, pas = self.stems()
        if passive:
            return Verb(pas, 'ichidan', 'v').form(past=past, neg=neg, prog=prog)
        if can:
            return Verb(pot, 'ichidan', 'v').form(past=past, neg=neg)
        if want:
            return _adj_form(ren + 'たい', 'adj', past, neg)
        if prog:
            return Verb(te + 'いる', 'ichidan', 'v').form(past=past, neg=neg)
        if neg:
            return nai + ('なかった' if past else 'ない')
        if past:
            return te[:-1] + ('だ' if te.endswith('で') else 'た')
        return self.word if self.kind != 'suru' else (self.word if self.word.endswith('する') else self.word + 'する')


def _adj_form(word, kind, past, neg):
    if kind == 'adj':
        s = word[:-1]
        if neg:
            return s + ('くなかった' if past else 'くない')
        return s + ('かった' if past else 'い')
    if neg:
        return word + ('ではなかった' if past else 'ではない')
    return word + ('だった' if past else 'だ')
