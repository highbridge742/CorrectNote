# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""直しが入ったのに、直した後の文がまだ不自然に高い費用の行へ紫を足す（2026-11-13・全体評価スレッド）。

なぜ
----
2か所打ち違えた行では、片方だけ直って残りが紫なしで通る行と、別の語が勝って文が崩れたまま紫なしで通る行が
出る（作った例: 「会員と梅木の手続き」が「会員と天気の手続き」）。どちらも直しが入ったので紫が消え、
画面では「直った」ように見える。直した後の文の費用（morphology.path_cost）を見ると、こういう行は正しい文より
はっきり高い所が残る。作った誤字692行の束で、紫なしで誤りが残った60行のうち27行に掛かり、
正しく直った88行では5行に余分な紫が付く（直しはそのまま）。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む。
1. 補正が文を書き換え、紫が1つも付いていない行だけ見る（直しの入らない行は見ない）。
2. 直した後の文の 1字あたりの費用 と、語3つの窓の 1字あたりの費用の最大 を出す。
3. 窓が線（WINDOW）を超えたらその窓に、行だけが線（PER_CHAR）を超えたら直した所に、紫を足す。線は作った正しい文
   190行の上から5%。紫は元の行の位置（直しに掛かる窓は、直す前の字の範囲まで広げる）。文は書き換えない。
IME は使わない（雲と PC で同じ答え）。特定の語や文字列には合わせない。

切り替え: CN_FIXED_STILL_ODD=0 で前のまま。
"""
import difflib
import functools
import os
import re

PER_CHAR = 1700     # 行の費用÷字数。正しい文190行の上から5%が 1686
WINDOW = 4100       # 語3つの窓の費用÷字数（3字より短い窓は3で割る）。正しい文190行の上から5%が 4072
SPAN = 3            # 窓の語数
_LIGHT = ('する', 'なる', 'ある', 'いる', 'できる', 'おる', 'くる', 'いく')
REASON = '直した後も、この辺りが文として不自然です'

_STRETCH = re.compile('[ぁ-ゖ][ー〜～]')
_orig = {}
STATS = {'lines': 0, 'marked': 0}


def _on():
    return os.environ.get('CN_FIXED_STILL_ODD') != '0'


def _num(name, default):
    try:
        return float(os.environ.get(name, '') or default)
    except ValueError:
        return default


def still_odd(text):
    """直した後の文 → 紫にする窓（始め, 終わり）・'fix'（直した所に付ける）・None。"""
    from morphology import tokenize, path_cost
    if not text or len(text) > 200:
        return None
    toks = [t for t in tokenize(text)]
    if not toks:
        return None
    whole = path_cost(text)
    if whole is None:
        return None
    plain = text
    if _STRETCH.search(text) and os.environ.get('CN_FIXED_STILL_ODD_STRETCH') != '0':
        # 行ぜんたいの費用は、話し言葉の伸ばす音を抜いた形で見る
        plain = re.sub('(?<=[ぁ-ゖ])[ー〜～]+', '', text)
        whole = path_cost(plain) if plain else None
        if whole is None:
            return None
    best, where = 0.0, None
    for i in range(len(toks)):
        a, b = toks[i].start, toks[min(len(toks), i + SPAN) - 1].end
        if any(t.pos == '記号' for t in toks[i:i + SPAN]):
            continue
        if _STRETCH.search(text[a:b]) and os.environ.get('CN_FIXED_STILL_ODD_STRETCH') != '0':
            continue        # ひらがなの後ろの伸ばす音（話し言葉の てねー・たー）を含む窓は、費用が書き方のせいで高い
        c = path_cost(text[a:b])
        if c is None:
            continue
        v = c / max(3, b - a)
        if v > best:
            best, where = v, (a, b)
    if where is None:
        return None
    if best > _num('CN_FIXED_STILL_ODD_WINDOW', WINDOW):
        return where
    if whole / len(plain) > _num('CN_FIXED_STILL_ODD_CHAR', PER_CHAR):
        return 'fix'            # 行ぜんたいが高い: どこかは決められないので、直した所に付ける
    return None


def _has_context(line, text):
    """直した後の文に、直しに掛からない内容語（名詞・動詞・形容詞・副詞）が1つでも在るか。直した語のほかに比べる
    文脈が無い行（直した語だけの行・記号と直した語だけの行）は、費用が高くても文として不自然かを決められない
    （2026-11-13 補正担当、PC の未解決タブの通し: 正しく直った語だけの行5行に紫が残った）。CN_FIXED_STILL_ODD_CONTEXT=0 で前のまま。"""
    if os.environ.get('CN_FIXED_STILL_ODD_CONTEXT') == '0':
        return True
    from morphology import tokenize
    changed = [(j1, j2) for tag, i1, i2, j1, j2 in
               difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if tag != 'equal']
    for t in tokenize(text):
        if t.pos not in ('名詞', '動詞', '形容詞', '副詞'):
            continue
        if t.pos == '動詞' and (getattr(t, 'base_form', '') or t.surface) in _LIGHT:
            continue        # する・なる などは前の語に付く形の動詞で、比べる文脈にならない
        if (getattr(t, 'pos_sub', '') or '').startswith(('接尾', '非自立')):
            continue        # 直した語に付く接尾（化・者）も、比べる文脈にならない（PC の通しで 直した語＋接尾 の行に紫が残った）
        if not any(a < t.end and t.start < max(b, a + 1) for a, b in changed):
            return True
    return False


def _still_odd_fields(line, text):
    """タブで区切った欄（打った行＋タブ＋メモ）は別々の文なので、欄ごとに見る。直しの入った欄だけ・前から。
    窓は行の位置に直して返す（直した所に付ける 'fix' は、その欄の直した所の範囲 ('fix', 始め, 終わり)）。
    2026-11-13 補正担当（PC の未解決タブ: 正しく直った2つ目の欄に、1つ目の欄の残りの紫がずれて付いた）。
    CN_FIXED_STILL_ODD_FIELDS=0 で前のまま。"""
    if os.environ.get('CN_FIXED_STILL_ODD_FIELDS') == '0' or '\t' not in text:
        return still_odd(text)
    changed = [(j1, j2) for tag, i1, i2, j1, j2 in
               difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if tag != 'equal']
    at = 0
    for field in text.split('\t'):
        a, b = at, at + len(field)
        at = b + 1
        if not field.strip() or not any(x < max(y, x + 1) and a <= x < b + 1 for x, y in changed):
            continue
        got = still_odd(field)
        if got is None:
            continue
        if got == 'fix':
            hit = [(x, y) for x, y in changed if a <= x < b + 1]
            return ('fix', hit[0][0], hit[-1][1])
        return (got[0] + a, got[1] + a)
    return None


def to_line(line, text, a, b):
    """直した後の文の範囲 [a, b) を、元の行の範囲にする。直しに掛かる所は直す前の字の範囲まで広げる。"""
    s = e = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes():
        if j2 <= a and not (j1 == j2 == a):
            continue
        if j1 >= b:
            break
        if tag == 'equal':
            lo, hi = i1 + max(a, j1) - j1, i1 + min(b, j2) - j1
        else:
            lo, hi = i1, i2
        s = lo if s is None else min(s, lo)
        e = hi if e is None else max(e, hi)
    if s is None or e is None or e <= s:
        return None
    return s, e


def _near_fix(line, text, where):
    """重い窓が、直した所に掛かるか、語1つを挟まずに隣り合うか。直した所から離れた窓は、直しの良し悪しの手がかりに
    ならない（正しい長い文で、1か所の書き換えから離れた「て＋名詞＋を」の窓に紫が付いた・2026-11-14 作った正しい文624行）。
    リリース検査160行では、この部品が効く行の窓は全部が直した所に掛かっていた。既定は見ない（CN_FIXED_STILL_ODD_NEAR=1 で見る）。"""
    if os.environ.get('CN_FIXED_STILL_ODD_NEAR') != '1':
        # 既定では見ない: PC のリリース検査で、直した所から離れた窓の紫が消え、誤りの残る2行が紫なしになった
        # （2打の打ち違いの行は、1つ直した後も離れた所にもう1つ残る）。正しい文で得た1行より損が大きい
        return True
    from morphology import tokenize
    changed = [(j1, max(j2, j1 + 1)) for tag, i1, i2, j1, j2 in
               difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if tag != 'equal']
    toks = list(tokenize(text))
    idx = [i for i, t in enumerate(toks) if t.start < where[1] and t.end > where[0]]
    if not idx:
        return True
    a = toks[max(0, idx[0] - 1)].start
    b = toks[min(len(toks) - 1, idx[-1] + 1)].end
    return any(x < b and y > a for x, y in changed)


def _only_same_reading(line, text):
    """書き換えが全部、かなを同じ読みの漢字に置いただけ（みずをのむ → みずを飲む）か。読みが変わらないので打ち違いの
    直しではなく、直した後の文の費用（かなのまま残る和語の名詞で高い）は直しの良し悪しの手がかりにならない
    （2026-11-14 補正担当: かなだけの正しい行で、和語の動詞を漢字にした行の かなの名詞 に紫が付いた）。
    既定は見る（前のまま）。CN_FIXED_STILL_ODD_SAME_READING=1 で同じ読みの行を外す（かなの誤字の行の数え直しが済むまで試し）。"""
    if os.environ.get('CN_FIXED_STILL_ODD_SAME_READING') != '1':
        return False
    return same_reading_line(line, text)


def same_reading_line(line, text):
    """書き換えが全部、かなを同じ読みの漢字に置いただけか（切り替えに依らない。correction_entry の守りも使う）"""
    def hira(x):
        return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in x)
    if any('一' <= c <= '鿿' or c == '々' for c in line):
        return False            # 元の行に漢字が在る行は、読みを行ぜんたいで比べられない
    try:
        from morphology import tokenize
        got = ''.join(t.reading if t.reading and t.reading != '*' else t.surface for t in tokenize(text))
    except Exception:
        return False
    return hira(got) == hira(line)


def _kept_kana_cost_only(result, text):
    """高い費用が、和語なのでかなに戻した語（kana_keep: 水 → みず）だけのせいか。戻す前の漢字を当てた文で still_odd が
    何も拾わないときだけ True。かなのまま打った誤字の行（きょうかえし のような打ち違いが残る行）は、漢字を当てても高いので
    紫を残す（2026-11-14 全体評価の指摘: 同じ読みの行を全部外すと、かなの誤字の行の紫が消えた）。"""
    kk = result.get('_kana_kept')
    if not kk:
        return False
    try:
        pre = kk[0]
        mixed = text
        for tag, i1, i2, j1, j2 in sorted(difflib.SequenceMatcher(None, pre, text, autojunk=False).get_opcodes(),
                                          key=lambda o: -o[3]):
            if tag == 'replace' and any('一' <= c <= '鿿' for c in pre[i1:i2]) and all('ぁ' <= c <= 'ゖ' for c in text[j1:j2]):
                mixed = mixed[:j1] + pre[i1:i2] + mixed[j2:]
        return mixed != text and still_odd(mixed) is None
    except Exception:
        return False


def _mark(line, result):
    text = result.get('corrected')
    if not isinstance(text, str) or text == line or result.get('odd_spans'):
        return result
    STATS['lines'] += 1
    if not _has_context(line, text):
        return result
    if _only_same_reading(line, text) and _kept_kana_cost_only(result, text):
        return result
    where = _still_odd_fields(line, text)
    if where is None:
        return result
    if isinstance(where, tuple) and where[0] == 'fix':
        span = to_line(line, text, where[1], max(where[2], where[1] + 1))
    elif where == 'fix':
        ops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
        a, b = ops[0][1], ops[-1][2]
        span = (a, b) if b > a else (max(0, a - 1), min(len(line), a + 1))
    else:
        if not _near_fix(line, text, where):
            return result
        span = to_line(line, text, *where)
    if span is None:
        return result
    out = dict(result)
    out['odd_spans'] = [span]
    out['odd_reasons'] = [(span[0], span[1], REASON)]
    STATS['marked'] += 1
    back = _guess_only_back(line, result, span)
    if back is not None:
        return back
    return out


GUESS_ONLY = ('常用外の字',)


RESPELL = ('紫の所の打ち違い',)


def _kanji_respell_only(det):
    """直しがどれも紫の所の読み直しで、元の所が漢字だけ（人が IME で確定した漢字の語）か。直した後もまだ不自然なら、
    読み直しは文を良くしていないので、元の漢字に戻して紫だけにする（2026-11-15 うにの画面: 漢字3字の語を
    1字だけ別の読みに替え、直した後も不自然の紫が残っていた）。CN_FSO_RESPELL_BACK=0 で前のまま。"""
    if os.environ.get('CN_FSO_RESPELL_BACK') == '0':
        return False
    return all(d[2] in RESPELL and isinstance(d[0], str) and d[0]
               and all('一' <= c <= '鿿' or c in '々〆ヶ' for c in d[0]) for d in det)


def _guess_only_back(line, result, span):
    """直しがどれも推し量りだけの直し（常用外の字を1打違いの身近な語に: 作った例 誤変換の佑 → 多角）で、直した後も
    その辺りが不自然なら、直しは戻して元の行に紫だけ（誤った直しより紫・2026-11-14 未解決タブ）。
    CN_FSO_GUESS_BACK=0 で前のまま"""
    if os.environ.get('CN_FSO_GUESS_BACK') == '0':
        return None
    det = [d for d in result.get('details') or () if isinstance(d, (list, tuple)) and len(d) >= 3]
    if not det:
        return None
    if not all(d[2] in GUESS_ONLY for d in det) and not _kanji_respell_only(det):
        return None
    ops = [o for o in difflib.SequenceMatcher(None, line, result.get('corrected') or line, autojunk=False).get_opcodes()
           if o[0] != 'equal']
    if not ops or not all(span[0] <= o[2] and o[1] <= span[1] for o in ops):      # 重なるか隣り合う
        return None
    out = dict(result)
    marks = [(o[1], max(o[2], o[1] + 1)) for o in ops]
    out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': [],
                'odd_spans': marks,
                'odd_reasons': [(a, b, (f'「{line[a:b]}」は常用漢字の外の字で、打ち違いを戻すとより自然な文になります'
                                        if all(d[2] in GUESS_ONLY for d in det)
                                        else '前後の語とのつながりが辞書で確かめられません'))
                                for a, b in marks]})
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    try:
        return _mark(line, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    # 呼ぶ側（analysis_worker）は inspect.signature で引数を確かめる。包みが元の関数の引数の形を見せるようにする
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
