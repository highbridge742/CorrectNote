# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""The single correction entry, independent of window and menu imports."""
import difflib
import corrector
from vocabulary import find_known_readings_flex
from analysis_work import current_input

# 子の控えの上限（挙動関連担当の測り 2026-11-02: 1/4 で子のメモリ −20MB・答え同じ）。morphology.py は同梱の名詞索引の
# 固定（public_nominal_cache.CODE_SHA256）に入っているので、ファイルは変えずにここで上書きする
try:
    import morphology as _morphology
    _morphology._TOKENIZATION_CACHE_LIMIT = 512
    _morphology._COST_CACHE_LIMIT = 5000
except Exception:
    pass


class _HalfClearDict(dict):
    """上限に届いた時の clear() で全部でなく古い半分だけ消す控え（重い行で同じ問いを何百回も計算し直していた・
    2026-11-06 挙動関連担当の測り）。答えは変えない。morphology.py は固定なので、控えの入れ物だけ差し替える。"""
    def clear(self):
        n = len(self) // 2
        for k in [k for _, k in zip(range(n), self)]:
            del self[k]


try:
    import os as _os
    if _os.environ.get('CN_COST_CACHE_HALF') != '0' and not isinstance(_morphology._COST_CACHE, _HalfClearDict):
        _morphology._COST_CACHE = _HalfClearDict(_morphology._COST_CACHE)
except Exception:
    pass


_FULLWIDTH_LOWER = {chr(c): chr(c - 0xFEE0) for c in range(ord('ａ'), ord('ｚ') + 1)}
# ローマ字入力で1字だけ残った c を IME が © にすることがある（PC の本物の IME で、c の残る誤字の約半分: の©で・くだ©歳。
# 2026-11-05 ローマ字担当）。日本語の字に接する © だけ、残った英字 c と同じに見る（「© 2026」のような記号の使い方は触らない）
_SYMBOL_LETTER = {} if __import__('os').environ.get('CN_SYMBOL_LETTER') == '0' else {'©': 'c'}   # CN_SYMBOL_LETTER=0 で前のまま


def _halfwidth_letters(line):
    """ローマ字入力で IME が残した全角の小文字（かなの隣のｋ・ｔ）を半角に（字の数は変えない）。
    打ち間違いの印は半角の英字で見ているので、全角のままだと印にも戻しにもならなかった（PC の本物の IME で
    残った英字の6割が全角。2026-10-23・補正C）。かなに接しない全角の英字（全角で書いた語）は触らない。"""
    def hira(ch):
        return 'ぁ' <= ch <= 'ゖ' or ch == 'ー'
    def alnum(ch):
        return 'ａ' <= ch <= 'ｚ' or 'Ａ' <= ch <= 'Ｚ' or '０' <= ch <= '９' or (ch.isascii() and ch.isalnum())
    def japanese(ch):
        return hira(ch) or 'ァ' <= ch <= 'ヺ' or '一' <= ch <= '鿿' or ch == '々'
    out = list(line)
    for i, ch in enumerate(line):
        if ch in _SYMBOL_LETTER:
            if (i > 0 and japanese(line[i - 1])) or (i + 1 < len(line) and japanese(line[i + 1])):
                out[i] = _SYMBOL_LETTER[ch]
            continue
        if ch in _FULLWIDTH_LOWER:
            j, k = i, i
            while j > 0 and alnum(line[j - 1]):
                j -= 1
            while k + 1 < len(line) and alnum(line[k + 1]):
                k += 1
            # 残った英字の印と同じ形（last_keystroke._letter_span: 小文字1〜2字）だけ。全角で書いた語（ｉＰｈｏｎｅ）は触らない
            if (all(c in _FULLWIDTH_LOWER for c in line[j:k + 1]) and k - j < 2
                    and ((j > 0 and hira(line[j - 1])) or (k + 1 < len(line) and hira(line[k + 1])))):
                out[i] = _FULLWIDTH_LOWER[ch]
    return ''.join(out)


def _restore_fullwidth(line, half, result):
    """半角にして補正した結果の、直さなかった所の字を元の行（全角）に戻す。位置は字の数が同じなので変わらない。"""
    import difflib
    done = result.get('corrected', half)
    if done == half:
        out = dict(result)
        out['corrected'] = line
        return out
    chars = list(done)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, half, done, autojunk=False).get_opcodes():
        if tag == 'equal':
            chars[j1:j2] = line[i1:i2]
    out = dict(result)
    out['corrected'] = ''.join(chars)
    return out


def _readable_unsure(line, result, tokenize_fn):
    """入口（corrector）の「直せないので色だけ付ける」かなの窓のうち、文全体の解析でも窓だけでも読め、かなの語と機能語で
    説明が付くもの（本はいくら読んでも の はいくら）の紫を外す。corrector の中ではこの2つの読めるの印が立っても、直しが
    見つからなければ色を付けていた（説明書きは「読める窓は補正もせず、色も付けない」）。例文（Tatoeba）2,515文の
    正しい文で紫の出る行の約6割がこれ（2026-11-07）。corrector は名詞索引の固定のため替えず、ここで外す。
    CN_READABLE_UNSURE=0 で前のまま。"""
    import os
    if os.environ.get('CN_READABLE_UNSURE') == '0' or not isinstance(result, dict):
        return result
    uns = list(result.get('unsure_spans') or ())
    if not uns or (result.get('corrected') or line) != line:
        return result
    try:
        tokens = list(tokenize_fn(line))
    except Exception:
        return result
    keep = []
    for sp in uns:
        a, b = sp[0], sp[1]
        w = line[a:b]
        drop = False
        if w and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in w):
            ak = a > 0 and corrector.is_kanji(line[a - 1])
            bk = b < len(line) and corrector.is_kanji(line[b])
            try:
                known = corrector._tokens_all_known_in_span(tokens, a, b, partial_start=True, partial_end=True,
                                                            after_kanji=ak)
                # 窓を語の切れ目まで広げて読めれば外す案は、例文の正しい文の紫 152→112/1,443 だが誤字の束で紫を
                # 6/331 失った（わすちゃった・そんなにそがなくても）ので入れない（2026-11-07）
                # 漢字のすぐ後ろから始まる窓（送り仮名から: 買｜ってあげ）は after_kanji で説明を見る（2026-11-07）
                if known and corrector._kana_run_explained(
                        w, before_kanji=bk, after_kanji=ak and os.environ.get('CN_READABLE_AFTER') != '0'):
                    drop = corrector._looks_like_valid_japanese(w, tokenize_fn)
                if (not drop and (known or os.environ.get('CN_READABLE_RUN_ANY') != '0')
                        and os.environ.get('CN_READABLE_RUN') != '0'):
                    # 窓を含むひらがなの連続まるごと（好｜きじゃないんだ）を、紫の判定（pos_grammar の活用の文法）が
                    # 前の漢字を語幹に説明できるなら外す。窓が語の途中で切れていて窓だけでは読めない形（2026-11-07）
                    i, j = a, b
                    while i > 0 and 'ぁ' <= line[i - 1] <= 'ゖ':
                        i -= 1
                    while j < len(line) and ('ぁ' <= line[j] <= 'ゖ' or line[j] == 'ー'):
                        j += 1
                    k = i
                    while k > 0 and corrector.is_kanji(line[k - 1]):
                        k -= 1
                    if k == i and os.environ.get('CN_READABLE_RUN_ANY') != '0':
                        # 片仮名の語の後ろ（ランド｜じゃないよ）も語幹と同じに見る（2026-11-07）
                        while k > 0 and ('ァ' <= line[k - 1] <= 'ヺ' or line[k - 1] == 'ー'):
                            k -= 1
                    # 大きい つ＋た・て（入れなかつた）は促音の打ち落としと区別できないので外さない
                    if k < i and j - i >= len(w) and 'つた' not in line[i:j] and 'つて' not in line[i:j]:
                        import pos_grammar
                        drop = bool(pos_grammar.explain_kana_run(
                            line[i:j], after_kanji=True,
                            before_kanji=j < len(line) and corrector.is_kanji(line[j]),
                            kanji_stem=line[k:i]))
            except Exception:
                drop = False
        if not drop:
            keep.append(sp)
    if len(keep) == len(uns):
        return result
    out = dict(result)
    out['unsure_spans'] = keep
    return out


def _explained_kana_revert(line, result):
    """入口（corrector）が、ひらがなの所だけを替えた直しで、替えた所を含むひらがなの連続が元の行のままで活用の文法
    （pos_grammar・前の漢字を語幹に）で説明できるなら、直しを戻して紫にする（まったくだめです→だろです・同じぐらいだ
    →グライダー・ひかえめに→ひかえるに: 例文 Tatoeba の正しい文・2026-11-07）。読める形を別の読める形に替えるのは
    決め手が無い（迷うなら紫）。替えた所がどれも当てはまる時だけ。CN_EXPLAINED_KANA_REVERT=0 で前のまま。"""
    import os
    if os.environ.get('CN_EXPLAINED_KANA_REVERT') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        import pos_grammar
        ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
        spans = []
        for _tag, i1, i2, j1, j2 in ops:
            src = line[i1:i2]
            if not src or not all('ぁ' <= c <= 'ゖ' for c in src):
                return result
            dst = fixed[j1:j2]
            # 小書きの母音を並の字に戻しただけ（でしょぅか→でしょうか: Shift の打ち違い）は、小書きの ぁぃぅぇぉ が
            # その位置に来ること自体が打ち違いの跡なので、戻さない（2026-11-09 公開の検査 tests_gui_operation_followups）。
            # CN_EXPLAINED_SMALL_VOWEL=0 で前のまま
            if (os.environ.get('CN_EXPLAINED_SMALL_VOWEL') != '0' and len(src) == len(dst)
                    and any(c in 'ぁぃぅぇぉ' for c in src)
                    and src.translate(str.maketrans('ぁぃぅぇぉ', 'あいうえお')) == dst):
                return result
            # 平仮名を同じ読みの片仮名にしただけ（びっくり→ビックリ）も見ない
            if dst.translate({c: c - 0x60 for c in range(0x30A1, 0x30F7)}) == src:
                return result
            # かなを同じ読みの漢字に置いただけ（あした→明日）は打ち違いの直しではないので、この段は見ない
            if not dst or not all('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヺ' or c == 'ー' for c in dst):
                return result
            i, j = i1, max(i2, i1)
            while i > 0 and 'ぁ' <= line[i - 1] <= 'ゖ':
                i -= 1
            while j < len(line) and 'ぁ' <= line[j] <= 'ゖ':
                j += 1
            if j - i < 2:
                return result
            k = i
            while k > 0 and corrector.is_kanji(line[k - 1]):
                k -= 1
            try:
                import kana_rules
                if kana_rules.bad_spots(line[i:j]):
                    return result          # 書けない小書き・浮いた濁点のある並び（じてしんゃ）は打ち違いが確か
            except Exception:
                pass
            if not pos_grammar.explain_kana_run(line[i:j], after_kanji=k < i, kanji_stem=line[k:i],
                                                before_kanji=j < len(line) and corrector.is_kanji(line[j])):
                return result
            spans.append((i1, max(i2, i1 + 1)))
    except Exception:
        return result
    out = dict(result)
    out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': []})
    out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(spans))
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, '読める形を別の読める形に替える直しは決め手が無いので、紫だけにしました') for a, b in spans]
    out['_explained_rejected'] = fixed
    return out


def _readable_unsure_last(line, result, store):
    """答えの最後にも _readable_unsure を掛ける（入口が かな→漢字 に直した所に付けた紫が、後の段（かなのまま・和語）で
    直しを戻された後に残る: 私はおじの名を の おじ→叔父→おじ）。CN_READABLE_UNSURE=0 で前のまま。"""
    try:
        fn = getattr(store, '_tokenize_fn', None) or corrector.make_tokenizer(store)
        return _readable_unsure(line, result, fn)
    except Exception:
        return result


_DIGITS = '0123456789０１２３４５６７８９'


_FORMAL_KANA = frozenset(('こと', 'もの', 'ところ', 'ため', 'はず', 'わけ', 'よう', 'つもり'))


_NAME_TAILS = ('さん', 'さま', '様', 'くん', '君', 'ちゃん', '氏', '先生', '殿', '選手', '社長', '部長', '課長')


def _kana_to_name_guard(line, result):
    """かなの並びを漢字にした直しで、行に無かった人名（姓・名）ができ、後ろに敬称も無い形（くたせさぃ → 久田世才）は、
    読みを人名に当てただけで書くつもりの語ではない。戻して紫にする（2026-11-07 うにの未解決タブ、PC の本物の IME の道）。
    CN_KANA_NAME_GUARD=0 で前のまま。"""
    import os
    if os.environ.get('CN_KANA_NAME_GUARD') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        from morphology import tokenize
        kana = lambda w: bool(w) and all('\u3041' <= ch <= '\u3096' or ch in 'ー゛゜' for ch in w)
        toks = list(tokenize(fixed))
        src_names = {t.surface for t in tokenize(line) if '人名' in (t.pos_sub or '')}
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        bad = set()
        for k, (tag, a, b, c, d) in enumerate(ops):
            if tag != 'replace' or not kana(line[a:b]) or not any('一' <= ch <= '鿿' for ch in fixed[c:d]):
                continue
            for t in toks:
                if (t.start < d and c < t.end and '人名' in (t.pos_sub or '') and t.surface not in src_names
                        and not fixed[t.end:].startswith(_NAME_TAILS)):
                    bad.add(k)
        if not bad:
            return result
        new = ''.join(line[a:b] if k in bad else fixed[c:d] for k, (tag, a, b, c, d) in enumerate(ops))
        nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out = dict(result)
        out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                    'original_spans': [[o[1], o[2]] for o in nops],
                    'details': [x for x in (result.get('details') or []) if not (len(x) > 1 and str(x[1]) not in new)]})
        src_odd = [(ops[k][1], ops[k][2]) for k in bad]
        out['odd_spans'] = sorted(set(tuple(o[:2]) for o in (result.get('odd_spans') or ())) | set(src_odd))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (x, y, 'かなを人の名前の漢字に当てただけで、書くつもりの語が決まらないので、紫だけにしました') for x, y in src_odd]
        return out
    except Exception:
        return result


def _noun_formal_guard(line, result):
    """直しで、名詞の直後に の・な を挟まずに形式名詞（こと・もの・はず…）が付く形（平仮名に開いくこと → 飛来こと）が
    新しくできたら、その直しは文として成り立たない。戻して紫にする（2026-11-07 うにの未解決タブを PC の道で回した結果）。
    CN_NOUN_FORMAL_GUARD=0 で前のまま。"""
    import os
    if os.environ.get('CN_NOUN_FORMAL_GUARD') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        from morphology import tokenize
        def bad_at(text):
            toks = list(tokenize(text))
            out = set()
            for x, y in zip(toks, toks[1:]):
                if (x.end == y.start and x.pos == '名詞' and not (x.pos_sub or '').startswith(('非自立', '数', '副詞可能', '代名詞'))
                        and y.pos == '名詞' and (y.pos_sub or '').startswith('非自立') and y.surface in _FORMAL_KANA):
                    out.add(x.end)
            return out
        new_bad = bad_at(fixed)
        if not new_bad:
            return result
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        old_bad = bad_at(line)
        bad = set()
        for k, (tag, a, b, c, d) in enumerate(ops):
            if tag != 'equal' and d in new_bad and b not in old_bad:
                bad.add(k)
        if not bad:
            return result
        new, odd_add = '', []
        for k, (tag, a, b, c, d) in enumerate(ops):
            if k in bad:
                if b > a:
                    odd_add.append((len(new), len(new) + b - a))
                new += line[a:b]
            else:
                new += fixed[c:d]
        nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out = dict(result)
        out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                    'original_spans': [[o[1], o[2]] for o in nops],
                    'details': [x for x in (result.get('details') or []) if not (len(x) > 1 and str(x[1]) not in new)]})
        src_odd = [(ops[k][1], ops[k][2]) for k in bad if ops[k][2] > ops[k][1]]
        out['odd_spans'] = sorted(set(tuple(o[:2]) for o in (result.get('odd_spans') or ())) | set(src_odd))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (x, y, '直すと名詞のすぐ後ろに こと・もの が付いて文にならないので、紫だけにしました') for x, y in src_odd]
        return out
    except Exception:
        return result


def _hira_word_keep(line, result):
    """平仮名で打った語が辞書に平仮名の形で在る（びっくり・どきどき・にこにこ: 和語・擬音語）のに、同じ読みの片仮名へ
    替える直しは戻す（KANA KEEP うに 11-01: 和語はかなのまま、外来語は片仮名に）。固有名詞だけの形（ぱそこん）は戻さない。
    2026-11-07 例文 Tatoeba の正しい文。CN_HIRA_WORD_KEEP=0 で前のまま。"""
    import os
    if os.environ.get('CN_HIRA_WORD_KEEP') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        from morphology import dictionary_base_pos
    except Exception:
        return result
    hira = lambda w: bool(w) and all('\u3041' <= ch <= '\u3096' or ch == 'ー' for ch in w)
    kata = lambda w: ''.join(chr(ord(ch) + 0x60) if '\u3041' <= ch <= '\u3096' else ch for ch in w)
    ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
    if os.environ.get('CN_HIRA_WORD_LONG_JOIN') != '0':
        # ー だけを挟んで分かれた置き換え（ら｜ー｜めん → ラ｜ー｜メン）は1語として見る（ラーめん にしていた）
        merged = []
        for o in ops:
            if (merged and o[0] == 'replace' and len(merged) >= 2 and merged[-1][0] == 'equal'
                    and set(line[merged[-1][1]:merged[-1][2]]) == {'ー'} and merged[-2][0] == 'replace'):
                eq = merged.pop()
                pr = merged.pop()
                merged.append(('replace', pr[1], o[2], pr[3], o[4]))
                continue
            merged.append(o)
        ops = merged
    bad = set()
    for k, (tag, a, b, c, d) in enumerate(ops):
        if tag != 'replace' or b - a < 2 or not hira(line[a:b]) or fixed[c:d] != kata(line[a:b]):
            continue
        pos = dictionary_base_pos(line[a:b]) or ()
        if any(not p.startswith('名詞,固有名詞') for p in pos):
            bad.add(k)
    if not bad:
        return result
    new = ''.join(line[a:b] if k in bad else fixed[c:d] for k, (tag, a, b, c, d) in enumerate(ops))
    nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                'original_spans': [[o[1], o[2]] for o in nops],
                'details': [x for x in (result.get('details') or []) if not (len(x) > 1 and str(x[1]) not in new)]})
    return out


def _digit_dash_keep(line, result):
    """数字と数字の間の長音・ダッシュ（３２０２ー５６２５: 電話番号の区切り）は打ち違いと見ない。その字への直しを戻し、
    その字だけの紫を外す（ー→へ にしていた・2026-11-07 例文 Tatoeba）。CN_DIGIT_DASH=0 で前のまま。"""
    import os
    if os.environ.get('CN_DIGIT_DASH') == '0' or not isinstance(result, dict):
        return result
    pos = [k for k, c in enumerate(line) if c in 'ー－-‐―' and 0 < k < len(line) - 1
           and line[k - 1] in _DIGITS and line[k + 1] in _DIGITS]
    if not pos:
        return result
    out = dict(result)
    fixed = result.get('corrected') or line
    changed = False
    if fixed != line:
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        if any(tag != 'equal' and i2 - i1 == 1 and i1 in pos for tag, i1, i2, j1, j2 in ops):
            parts = [line[i1:i2] if (tag != 'equal' and i2 - i1 == 1 and i1 in pos) else fixed[j1:j2]
                     for tag, i1, i2, j1, j2 in ops]
            new = ''.join(parts)
            nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
            out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                        'original_spans': [[o[1], o[2]] for o in nops],
                        'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and d[0] in 'ー－-‐―')]})
            changed = True
    for key in ('odd_spans', 'unsure_spans'):
        if result.get(key):
            keep = [sp for sp in result[key] if not (sp[1] - sp[0] == 1 and sp[0] in pos)]
            if len(keep) != len(result[key]):
                out[key] = keep
                changed = True
    return out if changed else result


def _aux_verb_keep(line, result):
    """元の行の解析で 自立の動詞＋すぐ後ろの動詞の接尾（られる・れる・せる・させる）と読める所の字を抜く・替える直しを
    戻す（課せられていた→課せれていた・処せられた→処せれた: 例文 Tatoeba の正しい文で見つけた・2026-11-07）。
    戻した所に紫は付けない（元の形は文法で説明が付く）。CN_AUX_VERB_KEEP=0 で前のまま。"""
    import os
    if os.environ.get('CN_AUX_VERB_KEEP') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return result
    aux = [(p.start, t.end) for p, t in zip(toks, toks[1:])
           if t.pos == '動詞' and (t.pos_sub or '').startswith('接尾') and t.base_form in ('られる', 'れる', 'せる', 'させる')
           and p.pos == '動詞' and (p.pos_sub or '').startswith('自立') and p.end == t.start
           # 受け身・使役の接尾は未然形の後だけ（課せ｜られ・読ま｜れ）。連用形の後（こみ｜れ）は文法で説明が付かない
           # （こみれから→これから の直しを戻していた・2026-11-08 手分けB）。CN_AUX_VERB_MIZEN=0 で前のまま
           and ((p.infl_form or '').startswith('未然') or os.environ.get('CN_AUX_VERB_MIZEN') == '0')]
    if not aux:
        return result
    ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    bad = [o for o in ops if o[0] in ('delete', 'replace') and any(a < o[2] and o[1] < b for a, b in aux)
           and all('ぁ' <= c <= 'ゖ' for c in line[o[1]:o[2]])]
    if not bad:
        return result
    # 接尾を戻すなら、同じ 動詞＋接尾 の中の他の直し（手伝わ→手つだわ）も戻す: その所は文法で説明が付いた1つの形
    # （手伝わさせて→手つだわさせて が残っていた・2026-11-09）。CN_AUX_VERB_WHOLE=0 で前のまま
    if os.environ.get('CN_AUX_VERB_WHOLE') != '0':
        units = [(a, b) for a, b in aux if any(a < o[2] and o[1] < b for o in bad)]
        bad = bad + [o for o in ops if o[0] != 'equal' and o not in bad
                     and any(a <= o[1] and o[2] <= b for a, b in units)]
    out = _revert_ops_purple(line, result, ops, bad, '')
    add = {(min(o[1], len(line) - 1), min(max(o[2], o[1] + 1), len(line))) for o in bad}
    out['odd_spans'] = [sp for sp in out.get('odd_spans') or () if tuple(sp[:2]) not in add]
    out['odd_reasons'] = [r for r in out.get('odd_reasons') or () if not (tuple(r[:2]) in add and r[2] == '')]
    return out


_ROMAJI_TRACE = None


def _letters_mean_romaji(line):
    """かな・漢字に挟まれた半角の小文字1〜2字があるか（ローマ字で打った字の残り）。うに 2026-11-10 01:39Z「かな入力時、
    文中に現れたアルファベット1文字が、ローマ字入力によって母音と子音による隣接キーのタイプミスと考えられる場合は、
    補正する」、01:51Z「2字も入れる」（お非ry）。直すかどうかはローマ字の段（隣のキー・巻き込み）が決め、説明が付かなければ直さない。"""
    import os
    import re
    global _ROMAJI_TRACE
    if os.environ.get('CN_LETTER_MEANS_ROMAJI') == '0' or not line:
        return False
    if _ROMAJI_TRACE is None:
        _ROMAJI_TRACE = re.compile(r'[ぁ-ゖ一-鿿々][a-z]{1,2}[ぁ-ゖ一-鿿々]')
    return bool(_ROMAJI_TRACE.search(line))


# 1行の補正の中で、corrector._convert_odd_kana_run（紫のかなの並びを漢字にする）の同じ呼び出しの答えを使い回す。
# 1打戻した行を corrector に通し直す所（last_keystroke._after_mark の retry・紫の読み直しの run）で、似た塊の
# 読みの候補を何千回も同じ形で変換し直していた（2026-11-10 うに「36秒掛かった対応は？」: かな入力の1行が PC で36秒、
# 挙動関連担当の記録で _convert_odd_kana_run 2.6万回）。引数と、行の中で変わらない store・dict_index が同じなら答えも
# 同じなので、答えは変えない。corrector は名詞索引の固定のファイルなので外から包む。CN_ODD_RUN_MEMO=0 で前のまま
import contextvars as _memo_cv
import os
_ODD_RUN_MEMO = _memo_cv.ContextVar('cn_odd_run_memo', default=None)
_ODD_RUN_RAW = getattr(corrector._convert_odd_kana_run, '_cn_raw', corrector._convert_odd_kana_run)


def _odd_run_key(a, k):
    def norm(v):
        if callable(v):
            return ('fn', getattr(v, '__module__', ''), getattr(v, '__qualname__', ''))
        if isinstance(v, (list, set, frozenset)):
            return ('seq', tuple(sorted(map(repr, v))) if isinstance(v, (set, frozenset)) else tuple(map(repr, v)))
        hash(v)
        return v
    store_ = a[1] if len(a) > 1 else k.get('store')
    di = a[2] if len(a) > 2 else k.get('dict_index')
    rest = tuple(norm(v) for v in a[3:])
    kw = tuple(sorted((n, norm(v)) for n, v in k.items() if n not in ('store', 'dict_index')))
    return (a[0] if a else k.get('text'), id(store_), id(di), rest, kw)


REOPEN_VARIANT_CAP = 2000   # 紫の塊の受け皿で、手の変種を変換して試す数の上限（1回の _reopen_odd_chunk ごと）
_REOPEN_COUNT = _memo_cv.ContextVar('cn_reopen_variant_count', default=None)


def _reopen_odd_chunk_capped(*a, **k):
    """corrector._reopen_odd_chunk の受け皿（読み×手の変種を1つずつ変換して最初に通った形を採る）が、語彙の多い PC で
    1つの塊に1万を超える変種を変換して全部通らず、かな入力の1行が36秒だった（2026-11-10 うに「36秒掛かった対応は？」・
    挙動関連担当の記録: 変種の変換 2.6万回・11.6秒、変種ごとの表引き 4.3秒）。変種は読みに近い順・手の費用の安い順に
    並んでいるので、REOPEN_VARIANT_CAP を越えた遠い変種は試さない。CN_REOPEN_VARIANT_CAP=0 で上限なし（前のまま）。"""
    tok = _REOPEN_COUNT.set([0])
    try:
        return _REOPEN_RAW(*a, **k)
    finally:
        _REOPEN_COUNT.reset(tok)


def _variant_capped(k):
    cnt = _REOPEN_COUNT.get()
    if cnt is None or not k.get('short_head') or 'born' not in k:
        return False
    try:
        cap = int(os.environ.get('CN_REOPEN_VARIANT_CAP', REOPEN_VARIANT_CAP))
    except ValueError:
        cap = REOPEN_VARIANT_CAP
    if cap <= 0:
        return False
    cnt[0] += 1
    return cnt[0] > cap


def _convert_odd_kana_run_memo(*a, **k):
    if _variant_capped(k):
        return None
    memo = _ODD_RUN_MEMO.get()
    if memo is None:
        return _ODD_RUN_RAW(*a, **k)
    try:
        key = _odd_run_key(a, k)
    except Exception:
        return _ODD_RUN_RAW(*a, **k)
    if key in memo:
        return memo[key]
    got = _ODD_RUN_RAW(*a, **k)
    if got is None or isinstance(got, (str, tuple)):
        memo[key] = got
    return got


_convert_odd_kana_run_memo._cn_raw = _ODD_RUN_RAW
corrector._convert_odd_kana_run = _convert_odd_kana_run_memo
_REOPEN_RAW = getattr(corrector._reopen_odd_chunk, '_cn_raw', corrector._reopen_odd_chunk)
_reopen_odd_chunk_capped._cn_raw = _REOPEN_RAW
corrector._reopen_odd_chunk = _reopen_odd_chunk_capped


# 同じく1行の中で contextual_repair.lexical_omission_repairs（読みに1打を足して辞書の語になる形を全部作る）の答えを
# 使い回す。1打戻した行を何度も通し直すので、同じ読みで何百回も呼ばれていた（2026-11-10 挙動関連担当の記録:
# 500回・4.8秒）。答えは読み・辞書・引数と ゛゜ の打ち違いの切り替えで決まるので、行の中では変わらない。
# CN_ODD_RUN_MEMO=0 で前のまま
import contextual_repair as _cr_mod
_LOR_RAW = getattr(_cr_mod.lexical_omission_repairs, '_cn_raw', _cr_mod.lexical_omission_repairs)


def _lexical_omission_memo(reading, dictionary, include_shift=False, nominal_compound=False, native_tails=()):
    memo = _ODD_RUN_MEMO.get()
    if memo is None:
        return _LOR_RAW(reading, dictionary, include_shift, nominal_compound, native_tails)
    try:
        import kana_layout as _kl
        key = ('lor', reading, id(dictionary), bool(include_shift), bool(nominal_compound),
               tuple(native_tails or ()), bool(_kl.mark_slip_enabled()))
        hash(key)
    except Exception:
        return _LOR_RAW(reading, dictionary, include_shift, nominal_compound, native_tails)
    if key not in memo:
        memo[key] = _LOR_RAW(reading, dictionary, include_shift, nominal_compound, native_tails)
    return memo[key]


_lexical_omission_memo._cn_raw = _LOR_RAW
_cr_mod.lexical_omission_repairs = _lexical_omission_memo


# 1打戻した行の通し直し（last_keystroke の retry・contextual_repair.SLIP_REVERTED が立つ間）では、corrector の
# 紫の塊の読み直しが語彙の似た読みを2手まで探す（vocabulary.find_known_readings_flex max_edits=2）のを1手までにする。
# 戻した行の上に2打の滑りを重ねない（last_keystroke.retry の注記と同じ考え）。語彙の多い PC では1行の通し直しで
# 塊を何千通りにも読み替えて全部変換し直し、かな入力の1行が36秒だった（2026-11-10 うに「36秒掛かった対応は？」・
# 挙動関連担当の記録 _convert_odd_kana_run 3.6万回）。corrector は固定のファイルなので、corrector が関数の中で
# 読む vocabulary の名前を包む。CN_RETRY_ONE_EDIT=0 で前のまま
import vocabulary as _vocab_mod
_FKR_RAW = getattr(_vocab_mod.find_known_readings_flex, '_cn_raw', _vocab_mod.find_known_readings_flex)


def _fkr_retry_one_edit(typed, store, max_dist=1.6, max_edits=2, beam_width=600, input_method=None):
    if max_edits > 1 and os.environ.get('CN_RETRY_ONE_EDIT') != '0':
        try:
            import contextual_repair as _cr
            if _cr.SLIP_REVERTED.get():
                max_edits = 1
        except Exception:
            pass
    return _FKR_RAW(typed, store, max_dist=max_dist, max_edits=max_edits, beam_width=beam_width,
                    input_method=input_method)


_fkr_retry_one_edit._cn_raw = _FKR_RAW
_vocab_mod.find_known_readings_flex = _fkr_retry_one_edit


def correct_line(line, store, context_vocab=None, decisions=None,
                 input_method='kana', context_vec=None, dict_index=None,
                 nearby_words=(), recent_words=(), occurrence_readings=(), occurrence_calculations=(),
                 occurrence_strokes=(), tab_has_kana=None, previous_line=None, defer_heavy=False, on_early_odd=None):
    """補正エンジンの入口。

    on_early_odd: 呼べるものを渡すと、入口が紫を決めた直後（直しの段に入る前）に on_early_odd(line, odd_spans) を
    1度だけ呼ぶ（途中の紫を早く出すため・挙動関連担当の案 2026-11-06）。odd_spans はその時の紫で、最後の答えの紫とは
    違いうる（後の段が直す・足す）。答えは変えない。None（既定）は今まで通り。

    defer_heavy: True なら打鍵中の行として、重い段（紫の所の2打の戻し odd_respell._two_only）を後回しにする。後回しに
    した時は答えに deferred_stages（段の名前の並び）が付く。呼び手は手が止まった時に defer_heavy=False で解析し直す
    （その答えが本当の答え）。False（既定）は今まで通り。

    previous_line: 1行前の文字列（渡されない・None なら今まで通り）。前の行が文の途中で終わり、この行が助詞・助動詞
    （に・が・ので…）から始まるときは、前の行の最後の句をつないだ形で判定する（前の行から続く文を接続のことばの所で
    改行した書き方・うに 2026-11-02）。答えはこの行の分だけ（前の行は替えない）。

    tab_has_kana: このファイルタブの文字列に平仮名か片仮名が1字以上あるか（tab_context.tab_has_kana で字で数える・
    バイトでは見ない）。False なら半角のまま打った部分の補正（半角→全角）は掛けない（完全に英語の環境での誤検知を防ぐ・
    うに 2026-10-26）。None（渡されない）は今まで通り。

    occurrence_strokes: 確定ごとの打鍵 [(start, end, surface, reading, strokes[, shifts])]（strokes・shifts は
    shift_slip.ShiftStrokeClock.take() の [(キーの字, 押した ms)]・[(シフトの押し ms, 離し ms)]）。中身のないシフトがあれば
    小書き・「を」の抜けを戻す（shift_slip・かな入力だけ）。押した間隔の短い巻き込みの隣の2打があれば、
    どちらかを抜いた形を試す（keystroke_doubt.repair_line・打鍵間隔・2026-10-24）。無ければ今まで通り。

    答えの dict には used_keys（used_keys.py: この行が引いた語彙・選び直しの記憶のキー、最近使った語を読んだか、
    全部をなめたか）が付く。
    """
    # 使った材料のキー（used_keys・裏のタブの解析で関係する行だけやり直す）を記録する。答えは変えない
    import used_keys as _used_keys
    etoken = None
    if callable(on_early_odd):
        try:
            import last_keystroke as _lk_e
            etoken = _lk_e.EARLY_ODD.set((line, on_early_odd, []))
        except Exception:
            etoken = None
    # かな入力の設定でも、かな・漢字の間に半角の英字が1〜2字挟まった行（らいsひゅ・冷蔵kもに）は、ローマ字で打って
    # 変換に残った字の跡（かなのキーでは英字は出ない）なので、その行はローマ字入力として見る（2026-11-10 うに
    # 「ローマ字入力が通らなくなっていました」: IME の自動判定で設定が かな のとき、ローマ字の打ち違いが直らなかった）。
    # CN_LETTER_MEANS_ROMAJI=0 で前のまま
    if input_method == 'kana' and _letters_mean_romaji(line):
        input_method = 'romaji'
    mtoken = _ODD_RUN_MEMO.set({}) if (_ODD_RUN_MEMO.get() is None
                                       and os.environ.get('CN_ODD_RUN_MEMO') != '0') else None
    try:
        return _correct_line_entry(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                                   nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                                   occurrence_strokes, tab_has_kana, previous_line, defer_heavy)
    finally:
        if mtoken is not None:
            _ODD_RUN_MEMO.reset(mtoken)
        if etoken is not None:
            _lk_e.EARLY_ODD.reset(etoken)


def _correct_line_entry(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                        nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                        occurrence_strokes, tab_has_kana, previous_line, defer_heavy):
    import used_keys as _used_keys
    token, record = _used_keys.start()
    deferred, dtoken, ptoken = None, None, None
    if defer_heavy:
        try:
            import odd_respell as _odd
            deferred = []
            dtoken = _odd.DEFER_TWO.set(deferred)
            try:
                import contextual_repair as _cr
                ptoken = (_cr, _cr.DEFER_PAIRS.set(deferred))
            except Exception:
                ptoken = None
        except Exception:
            deferred = None
    try:
      from tab_context import tab_kana as _tab_kana
      with _tab_kana(tab_has_kana):
        recent = _used_keys.RecentWords(recent_words or ())
        nearby = (_used_keys.NearbyWords(_used_keys.raw_tuple(nearby_words))
                  if __import__('os').environ.get('CN_NEARBY_MARK') != '0' else nearby_words)
        result = _correct_line_strokes(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                                       nearby, recent,
                                       occurrence_readings, occurrence_calculations, occurrence_strokes)
        # 前の行から続く行頭の付属語（に・が・ので）に掛かった直しや紫だけを、前の行の最後の句とつないだ形で見直す。
        # 行頭に掛からない直し・紫はこの行だけの答えのまま（つなぐと別の所の直しが変わり、正しく直った行が直らなく
        # なった: 挙動関連担当の測り 2026-11-02）
        prefix = _continuation_prefix(previous_line, line)
        head_end = _head_end(line) if prefix else 0
        if prefix and head_end and _touches_head(result, line, head_end) and not _head_merged_fix(result, line, head_end):
            p = len(prefix)
            # つないだ形は行頭の直し・紫が消えるかを見るだけなので、重い段（紫の所の読み直し・2か所の打ち違い）は打鍵中と
            # 同じに後回しの印だけ付けて飛ばす（前の句込みで探し直して、1行 20秒→120秒: 挙動関連担当の測り 2026-11-03）
            jtok = None
            if __import__('os').environ.get('CN_JOIN_HEAVY') != '1':
                try:
                    import odd_respell as _odd2
                    jtok = _odd2.DEFER_TWO.set([])
                except Exception:
                    jtok = None
            try:
                whole = _correct_line_strokes(prefix + line, store, context_vocab, decisions, input_method, context_vec,
                                              dict_index, nearby, recent,
                                              _shift_items(occurrence_readings, p),
                                              _shift_items(occurrence_calculations, p),
                                              _shift_items(occurrence_strokes, p))
            finally:
                if jtok is not None:
                    _odd2.DEFER_TWO.reset(jtok)
            joined = _strip_prefix(whole, prefix, line)
            if joined is not None and not _touches_head(joined, line, head_end):
                result = _clear_head(result, joined, line, head_end)
    finally:
        _used_keys.stop(token)
        if dtoken is not None:
            import odd_respell as _odd
            _odd.DEFER_TWO.reset(dtoken)
        if ptoken is not None:
            ptoken[0].DEFER_PAIRS.reset(ptoken[1])
    result = _unexplained_change_guard(line, result)
    result = _far_typed_guard(line, result, occurrence_readings)
    result = _given_name_guard(line, result)
    result = _noun_suru(line, result)
    result = _keep_names(line, result)
    result = _elongation_guard(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index)
    result = _double_mark(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes,
                          tab_has_kana, previous_line, defer_heavy)
    result = _lone_mark_go(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                           nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes,
                           tab_has_kana, previous_line, defer_heavy)
    result = _lone_mark_fill(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                             nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes,
                             tab_has_kana, previous_line, defer_heavy)
    result = _small_vowel_slip(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                               nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                               occurrence_strokes, tab_has_kana, previous_line, defer_heavy)
    before_fg = result
    result = _frame_guard(line, result)
    if result is not before_fg and not defer_heavy:
        result = _frame_respell(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index)
    result = _parallel_kin(line, result)
    result = _readable_unsure_last(line, result, store)
    result = _aux_verb_keep(line, result)
    result = _digit_dash_keep(line, result)
    result = _hira_word_keep(line, result)
    result = _noun_formal_guard(line, result)
    result = _kana_to_name_guard(line, result)
    if __import__('os').environ.get('CN_SMALL_VOWEL_SLIP_LAST') != '0':
        # 人名の漢字に当てた直し（くたせさぃ → 久田世才）を上の段が戻した後に、書き方に無い小さい母音が残るなら、
        # ここでもう1度見る（PC の本物の IME の道: 2026-11-08 挙動関連担当の測り）。CN_SMALL_VOWEL_SLIP_LAST=0 で前のまま
        result = _small_vowel_slip(line, result, store, context_vocab, decisions, input_method, context_vec,
                                   dict_index, nearby_words, recent_words, occurrence_readings,
                                   occurrence_calculations, occurrence_strokes, tab_has_kana, previous_line,
                                   defer_heavy)
    result = _merge_odd_spans(result)
    if token is not None and isinstance(result, dict):
        result = dict(result)
        result['used_keys'] = record.answer()
    if deferred and isinstance(result, dict):
        result = dict(result)
        result['deferred_stages'] = sorted(set(deferred))
    return result


def nearby_change_matters(used_keys, old_nearby, new_nearby):
    """上下の行の語が old_nearby から new_nearby に変わった時、その行を解き直す要るか（答えの used_keys から見る・
    挙動関連担当の案 2026-11-06）。分からない時は True（解き直す）。
    - nearby: 上下の行の語の中を読んだ → 語が変わったら解き直す
    - nearby_truth: 有る無しだけ見た → 有る無しが変わったら
    - nearby_probes: 問うた語の有る無しが変わったら
    - nearby_one_key: 増えた・減った漢字の語の読みが、記録した読みと隣のキーの1打だけ違うなら"""
    if not isinstance(used_keys, dict) or 'nearby' not in used_keys:
        return True
    old = tuple(old_nearby or ())
    new = tuple(new_nearby or ())
    if old == new:
        return False
    if used_keys.get('nearby'):
        return True
    t = used_keys.get('nearby_truth')
    if t is not None and bool(new) != bool(old):
        return True
    so, sn = set(old), set(new)
    if any((p in so) != (p in sn) for p in used_keys.get('nearby_probes') or ()):
        return True
    try:
        import nearby_one_key
        return nearby_one_key.change_matters(used_keys.get('nearby_one_key') or (), old, new)
    except Exception:
        return True


_DOUBLE_MARK_BUSY = []


def _double_mark_at(line):
    """濁音・半濁音の字の後ろに、もう1つ ゛゜ が付いた所（が゜・ぱ゛）の ゛゜ の位置。無ければ None。"""
    import unicodedata
    for m in range(1, len(line)):
        if line[m] in '゛゜' and unicodedata.normalize('NFD', line[m - 1])[1:] in ('\u3099', '\u309a'):
            return m
    return None


def _double_mark(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                 nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes,
                 tab_has_kana, previous_line, defer_heavy):
    """濁音・半濁音の字に重ねて打った ゛゜（が゜いこく: ゛ の字にもう1つ ゜）は、付けようのない余分な1打。直しが
    その所に残っている（紫・そのまま）なら、その ゛゜ を抜いた行を補正に通し直し、その所に紫が残らなければそちらに
    する（2026-11-06 うにの画面: か゜ は直るのに が゜ は直らない）。CN_DOUBLE_MARK=0 で前のまま。"""
    import os
    if os.environ.get('CN_DOUBLE_MARK') == '0' or not isinstance(result, dict) or _DOUBLE_MARK_BUSY:
        return result
    m = _double_mark_at(line)
    if m is None:
        return result
    done = result.get('corrected') or line
    if line[m - 1:m + 1] not in done and not any(a <= m < b for a, b in (tuple(x[:2]) for x in result.get('odd_spans') or ())):
        return result
    if m + 1 < len(line) and '一' <= line[m + 1] <= '鿿' and os.environ.get('CN_DOUBLE_MARK_KANJI') != '0':
        # 後ろが漢字（ご゛居ました: ざ の さ が抜けて ゛ だけ残り、IME が 居 にした）は、余分な1打か抜けた字か
        # 決められない。抜いて直さず、その所を紫にする（ご居ました にしない）。CN_DOUBLE_MARK_KANJI=0 で前のまま
        odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
        if any(a <= m < b for a, b in odd):
            return result
        out = dict(result)
        out['odd_spans'] = list(result.get('odd_spans') or ()) + [(m - 1, m + 2)]
        return out
    line2 = line[:m] + line[m + 1:]

    def shift(items):
        out = []
        for x in items or ():
            try:
                a, b = (x.start, x.end) if hasattr(x, 'start') else (x[0], x[1])
            except Exception:
                continue
            if b <= m:
                out.append(x)
            elif a > m:
                out.extend(_shift_items((x,), -1))
        return tuple(out)
    _DOUBLE_MARK_BUSY.append(1)
    try:
        r2 = correct_line(line2, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, shift(occurrence_readings), shift(occurrence_calculations),
                          shift(occurrence_strokes), tab_has_kana, previous_line, defer_heavy)
    except Exception:
        return result
    finally:
        _DOUBLE_MARK_BUSY.pop()
    if not isinstance(r2, dict):
        return result
    if any(a <= m - 1 < b or a <= m < b for a, b in (tuple(x[:2]) for x in r2.get('odd_spans') or ())):
        return result
    fixed = r2.get('corrected') or line2
    out = dict(r2)
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': fixed, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': [[line[m - 1:m + 1], line[m - 1], 'かな入力']] + list(r2.get('details') or []),
                'odd_spans': [(a + (a >= m), b + (b > m)) + tuple(x[2:]) for x in (r2.get('odd_spans') or ())
                              for a, b in [tuple(x[:2])]],
                'odd_reasons': [(a + (a >= m), b + (b > m)) + tuple(x[2:]) for x in (r2.get('odd_reasons') or ())
                                for a, b in [tuple(x[:2])]]})
    out.pop('unsure_spans', None)
    return out


_SMALL_SLIP_BUSY = []


def _small_vowel_slip_at(line):
    """かなの後ろの、日本語の書き方に無い小さい母音（よぅ・さぃ）の位置の並び。かな入力では小さい字は同じキーを
    Shift で打つので、大きい字のつもりの Shift の押し違いの跡。"""
    out = []
    for i in range(1, len(line)):
        ok = _SMALL_VOWEL_OK.get(line[i])
        p = line[i - 1]
        if ok is None or not ('ぁ' <= p <= 'ゖ') or p in ok or p == line[i] or p in _SMALL_VOWEL_OK:
            continue
        out.append(i)
    return out


def _small_vowel_slip(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                      nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes,
                      tab_has_kana, previous_line, defer_heavy):
    """書き方に無い小さい母音（りよぅり・くださぃ）が直しの後も残る（そのまま・紫）なら、その字を大きい字にした行を
    補正に通し直し、その所に紫が残らなければそちらにする（Shift の押し違い: 同じキーの大きい字）。字の数は変わらない。
    CN_SMALL_VOWEL_SLIP=0 で前のまま"""
    import os
    if os.environ.get('CN_SMALL_VOWEL_SLIP') == '0' or not isinstance(result, dict) or _SMALL_SLIP_BUSY:
        return result
    if input_method == 'romaji':
        return result
    ms = _small_vowel_slip_at(line)
    if not ms:
        return result
    done = result.get('corrected') or line
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    ms = [m for m in ms if line[m - 1:m + 1] in done or any(a <= m < b for a, b in odd)]
    if not ms:
        return result
    full = dict(zip('ぁぃぅぇぉ', 'あいうえお'))
    line2 = ''.join(full[c] if i in ms else c for i, c in enumerate(line))
    _SMALL_SLIP_BUSY.append(1)
    try:
        r2 = correct_line(line2, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                          occurrence_strokes, tab_has_kana, previous_line, defer_heavy)
    except Exception:
        return result
    finally:
        _SMALL_SLIP_BUSY.pop()
    if not isinstance(r2, dict):
        return result
    if any(a <= m < b or a <= m - 1 < b for m in ms for a, b in (tuple(x[:2]) for x in r2.get('odd_spans') or ())):
        return result
    fixed = r2.get('corrected') or line2
    if fixed == line2:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(r2)
    out.update({'original': line, 'corrected': fixed, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': [[line[m], full[line[m]], 'かな入力'] for m in ms] + list(r2.get('details') or [])})
    out.pop('unsure_spans', None)
    return out


def _lone_mark_at(line):
    """付けようのない字（に・て・行頭）の後ろに1つだけ在る ゛ で、すぐ後ろが漢字の所の位置。無ければ None。"""
    import unicodedata
    for m in range(len(line) - 1):
        if line[m] != '゛' or not ('一' <= line[m + 1] <= '鿿'):
            continue
        if m == 0 or not ('ぁ' <= line[m - 1] <= 'ゖ' or line[m - 1] in '、。 　'):
            if m != 0:
                continue
        if m > 0 and len(unicodedata.normalize('NFC', line[m - 1] + '\u3099')) == 1:
            continue
        return m
    return None


_FILL_BASES = 'かきくけこさしすせそたちつてとはひふへほ'
LONE_FILL_MARGIN = 4000   # 足す字の候補で、最も低い費用が次の候補よりこれだけ低いときだけ直す（ので 5048・荒れず 2594）


def _lone_mark_fill_at(line):
    """付けようのない字（ま・の・れ・ー・漢字）の後ろの ゛ の位置（濁音の字の後ろ・行頭は除く）。無ければ None。"""
    import unicodedata
    for m in range(1, len(line)):
        if line[m] != '゛':
            continue
        p = line[m - 1]
        if p in '゛゜、。 　' or len(unicodedata.normalize('NFD', p)) > 1:
            continue
        if len(unicodedata.normalize('NFC', p + '\u3099')) == 1:
            continue
        return m
    return None


def _frame_place_ni(n, p):
    """位置・方向の名詞＋に（上に・横に・前に: 分類語彙表の 1.174）は、動詞が選ぶ相手ではなく置き場所を添える
    語なので、名詞＋に＋動詞 の組が例文に無いことは直しの誤りの根拠にならない（上に詰め、）。2026-11-09 手分けA。
    CN_FRAME_PLACE_NI=0 で前のまま"""
    import os
    if os.environ.get('CN_FRAME_PLACE_NI') == '0' or p.surface != 'に':
        return False
    try:
        import semantic_class
        codes = semantic_class.codes(n.surface)
    except Exception:
        return False
    return any(c.startswith('1.174') for c in codes)


def _frame_verb_swap_ok(line, i1, i2, done, n, p, v):
    """直しが動詞の漢字だけを同じ読みの別の動詞に替えた所（メモを描く→書く: かく／かく）で、名詞の意味の分類が新しい
    動詞の仲間ではっきり重いなら、組が例文に無くても戻さない（semantic_fit.verb_swap_supported）。読みは解析の読みの
    ほかに辞書の別の読み（描く=かく）も見る。2026-11-09 手分けA。CN_FRAME_VERB_SWAP=0 で前のまま"""
    import os
    if os.environ.get('CN_FRAME_VERB_SWAP') == '0':
        return False
    try:
        import morphology
        import semantic_fit
        old = [t for t in morphology.tokenize(line) if t.start == v.start and t.pos == '動詞']
        if not old or line[:v.start] != done[:v.start] or line[old[0].end:] != done[v.end:]:
            return False
        o = old[0]
        ob, nb = getattr(o, 'base_form', '') or o.surface, getattr(v, 'base_form', '') or v.surface
        if ob == nb:
            return False

        def readings(base):
            return {row[3] for row in (morphology.dictionary_inflections(base) or ())
                    if row[0].startswith('動詞,') and row[1] == '基本形' and row[2] == base}
        if not (readings(ob) & readings(nb)):
            return False
        return semantic_fit.verb_swap_supported(p.surface, n.surface, ob, nb)
    except Exception:
        return False


def _frame_at(text, pos):
    """pos を含む名詞の 名詞＋助詞＋動詞 が、例文の組（tatoeba_pairs）か語の組の表に在るか。
    True＝在る・False＝無い・None＝その形でない。"""
    try:
        import morphology
        toks = list(morphology.tokenize(text))
    except Exception:
        return None
    for k, t in enumerate(toks):
        if t.start <= pos < t.end:
            if t.pos != '名詞' or k + 2 >= len(toks):
                return None
            p, v = toks[k + 1], toks[k + 2]
            if p.pos != '助詞' or v.pos != '動詞':
                return None
            try:
                import pair_choice
                got = pair_choice._table()
                if got and got[0].get('\t'.join((p.surface, t.surface, v.base_form)), 0) > 0:
                    return True
            except Exception:
                pass
            try:
                import collocation_repair
                if (t.surface, p.surface, v.base_form) in collocation_repair.table()[0]:
                    return True
            except Exception:
                pass
            return False
    return None


def _frame_nouns(particle, verb):
    """(助詞, 動詞の基本形) に付く名詞（例文の組と語の組の表）。"""
    key = (particle, verb)
    got = _FRAME_NOUNS.get(key)
    if got is not None:
        return got
    nouns = set()
    try:
        import pair_choice
        t = pair_choice._table()
        if t:
            idx = _FRAME_NOUNS.get('_idx')
            if idx is None:
                idx = {}
                for k2, n in t[0].items():
                    parts = k2.split('\t')
                    if len(parts) == 3 and n > 0:
                        idx.setdefault((parts[0], parts[2]), set()).add(parts[1])
                _FRAME_NOUNS['_idx'] = idx
            nouns |= idx.get(key, set())
    except Exception:
        pass
    try:
        import collocation_repair
        nouns |= collocation_repair.table()[1].get(key, set())
    except Exception:
        pass
    _FRAME_NOUNS[key] = nouns
    return nouns


_FRAME_NOUNS = {}


def _lone_fill_by_frame(line, done, m, store, context_vocab, decisions, input_method, context_vec, dict_index,
                        nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                        occurrence_strokes, tab_has_kana, previous_line, defer_heavy):
    """゛ を替えた直しの組が無いとき、゛ の前のかなに清音の字を足した読み（ま＋と゛＝まど）の名詞で、同じ 助詞＋動詞 の
    組が在る語に直す。CN_LONE_FILL_FRAME=0 で前のまま"""
    import os
    import unicodedata
    if os.environ.get('CN_LONE_FILL_FRAME') == '0':
        return None
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
           if o[0] != 'equal' and o[1] <= m < o[2]]
    if not ops or _frame_at(done, ops[0][3]) is not False:
        return None
    try:
        import morphology
        toks = list(morphology.tokenize(done))
        k = next(i for i, t in enumerate(toks) if t.start <= ops[0][3] < t.end)
        particle, verb = toks[k + 1].surface, toks[k + 2].base_form
        hira = lambda x: ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in x)
        # ゛ の前の、かなの並び（その語の頭まで: 前が漢字・記号・行頭）
        s0 = m
        while s0 > 0 and ('ぁ' <= hira(line[s0 - 1]) <= 'ゖ'):
            s0 -= 1
        if s0 == m:
            return None
        wants = {}
        for base in _FILL_BASES:
            ch = unicodedata.normalize('NFC', base + '\u3099')
            for st in range(s0, m):
                wants.setdefault(hira(line[st:m]) + ch, st)
        hits = []
        for noun in _frame_nouns(particle, verb):
            nt = list(morphology.tokenize(noun))
            if len(nt) != 1 or not nt[0].has_reading:
                continue
            rd = hira(nt[0].reading)
            if rd in wants:
                hits.append((wants[rd], noun))
    except Exception:
        return None
    if len(hits) != 1:
        return None      # 無い・決めきれない
    st, noun = hits[0]
    line2 = line[:st] + noun + line[m + 1:]
    _DOUBLE_MARK_BUSY.append(1)
    try:
        r2 = correct_line(line2, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                          occurrence_strokes, tab_has_kana, previous_line, defer_heavy)
    except Exception:
        return None
    finally:
        _DOUBLE_MARK_BUSY.pop()
    if not isinstance(r2, dict) or r2.get('odd_spans') or r2.get('unsure_spans'):
        return None
    fixed = r2.get('corrected') or line2
    if noun not in fixed[:st + len(noun) + 1]:
        return None
    out = dict(r2)
    nops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': fixed, 'changed': bool(nops),
                'spans': [[o[3], o[4]] for o in nops], 'original_spans': [[o[1], o[2]] for o in nops],
                'details': [[line[st:m + 1], noun, 'かな入力']] + list(r2.get('details') or [])})
    out.pop('unsure_spans', None)
    return out


FRAME_GUARD_PEERS = 5    # その 助詞＋動詞 に付く名詞が例文・語の組にこれだけ以上あるときだけ「組に無い」を印にする


import contextvars as _cvars
_FRAME_RESPELL = _cvars.ContextVar('cn_frame_respell', default=False)


def _frame_respell(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index):
    """_frame_guard が直しを戻して紫にした所（も水戸 → みと の直しを戻した）を、紫の所の読み直し（odd_respell）で
    もう1度見る。前の段の直しが外れていただけで、別の打ち違いの戻し（もみと → もと）なら直る。
    候補の補正し直しは入口を通す（この段は中では回さない）。CN_FRAME_RESPELL=0 で前のまま"""
    import os
    if (os.environ.get('CN_FRAME_RESPELL') == '0' or _FRAME_RESPELL.get() or input_method != 'kana'
            or not isinstance(result, dict) or not result.get('odd_spans')):
        return result
    tok = _FRAME_RESPELL.set(True)
    try:
        import odd_respell as _orf
        ftok = _orf.FEWEST.set(True)
    except Exception:
        _orf, ftok = None, None
    try:
        def run(text):
            return correct_line(text, store, context_vocab, decisions, input_method, context_vec, dict_index)
        got = _odd_respell(line, result, run, store, dict_index, context_vec, decisions, input_method)
    except Exception:
        return result
    finally:
        _FRAME_RESPELL.reset(tok)
        if ftok is not None:
            _orf.FEWEST.reset(ftok)
    return got if isinstance(got, dict) else result


FRAME_GUARD_BROAD = 200   # 例文でこれだけ以上の名詞を取る動詞は、どんな物でも取る動詞として見る


FRAME_NAME_PERSON = 0.02   # この割合より人を取らない 助詞＋動詞 なら、人の名を目的語に置いた形は誤り
FRAME_NAME_RANK = 470      # 直した名詞がこれより身近（語の使われやすさの順位）なときだけ


def _frame_name_object(line, i1, i2, done, j1, j2, n, p, v):
    """直す前の語が人の名（名字・名前）で、直した名詞と読みが同じ（IME の選び違い: 都築→続き）、かつその 助詞＋動詞 が
    例文で人をほとんど取らない（〜を話す・〜を言う）なら、直した形の組が例文に無くても戻さない（元の形の方がさらに
    おかしい）。2026-11-08 手分けB。CN_FRAME_NAME_OBJECT=0 で前のまま"""
    import os
    if os.environ.get('CN_FRAME_NAME_OBJECT') == '0':
        return False
    try:
        import morphology
        import semantic_fit
        olds = [t for t in morphology.tokenize(line) if t.start < i2 and i1 < t.end]
        if not (n.start <= j1 and j2 <= n.end) or len(olds) != 1:
            return False
        o = olds[0]
        if (o.start, o.end) != (n.start, n.end) or o.pos != '名詞' or not str(o.pos_sub or '').startswith('固有名詞:人名'):
            return False
        hira = lambda r: ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (r or ''))
        if not o.reading or hira(o.reading) != hira(n.reading):
            return False
        if str(n.pos_sub or '').startswith('固有名詞'):
            return False
        # 直した名詞は身近な語で、名の方より使われる語だけ（近藤→混同 は見ない）
        import ime_reconvert
        rk = ime_reconvert._rank(n.surface)
        if rk > FRAME_NAME_RANK or rk > ime_reconvert._rank(o.surface):
            return False
        prof = semantic_fit.profile(p.surface, v.base_form)
        if not prof:
            return False
        tot = sum(prof.values())
        person = sum(c for code, c in prof.items() if code.startswith('1.2'))
        return tot > 0 and person / tot < FRAME_NAME_PERSON
    except Exception:
        return False


def _frame_guard(line, result):
    """直しで出来た 名詞＋を／に＋動詞 の組が、例文（tatoeba_pairs）にも語の組の表にも無いなら、その直しは戻して紫に
    （書類を手する→書類を怒る・見積もりを送りします→遅らします。雲の束で、組に無い直しは 13 か所とも誤り、
    組に在る直しは 13 か所とも正しかった・2026-11-07）。その 助詞＋動詞 の名詞が少ない（表が薄い）ときは見ない。
    CN_FRAME_GUARD=0 で前のまま"""
    import os
    if os.environ.get('CN_FRAME_GUARD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        import morphology
        toks = list(morphology.tokenize(done))
        allops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
        bad = []
        for op in allops:
            tag, i1, i2, j1, j2 = op
            if tag == 'equal':
                continue
            # かなを同じ読みの漢字に置いただけ（しゅくだい→宿題）は直しではないので見ない
            src_k = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in line[i1:i2])
            if src_k and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in src_k):
                try:
                    rd = ''.join(t.reading for t in morphology.tokenize(done[j1:j2]))
                    rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in rd)
                except Exception:
                    rd = None
                if rd == src_k:
                    continue
            hit = False
            for k in range(len(toks) - 2):
                n, p, v = toks[k], toks[k + 1], toks[k + 2]
                if n.pos != '名詞' or p.surface not in ('を', 'に') or p.pos != '助詞' or v.pos != '動詞':
                    continue
                touched = (n.start < max(j2, j1 + 1) and j1 < n.end) or (v.start < max(j2, j1 + 1) and j1 < v.end)
                if not touched:
                    continue
                peers = len(_frame_nouns(p.surface, v.base_form))
                if peers < FRAME_GUARD_PEERS:
                    continue
                # 動詞は元のままで名詞だけを直した所で、その動詞がどんな物でも取る（持つ・見る・する: 例文の名詞が
                # とても多い）なら、組が例文に無いことは誤りの根拠にならない（カーソルを持って行った）。
                # CN_FRAME_GUARD_BROAD=0 で前のまま
                v_touched = v.start < max(j2, j1 + 1) and j1 < v.end
                # 動詞は本人が漢字に変換した語（持って）に限る（かなの せん は する とも読めるだけの切れ端がある）
                if (not v_touched and peers >= FRAME_GUARD_BROAD and any(_is_kanji_char(c) for c in v.surface)
                        and os.environ.get('CN_FRAME_GUARD_BROAD') != '0'):
                    continue
                if _frame_at(done, n.start) is False:
                    if not v_touched and _frame_name_object(line, i1, i2, done, j1, j2, n, p, v):
                        continue
                    if v_touched and _frame_verb_swap_ok(line, i1, i2, done, n, p, v):
                        continue
                    if _frame_place_ni(n, p):
                        continue
                    hit = True
                    break
            if hit:
                bad.append(op)
        if not bad:
            return result
        out = _revert_ops_purple(line, result, allops, bad, '直した形の「名詞＋助詞＋動詞」の組が例文に無いので決められない')
        # 元の行の 名詞＋助詞＋動詞 の組が例文に在る（寿司を食べる）なら、元の形は確かで、戻した所に紫は要らない
        # （寿司を食べてみませんか が紫になっていた・2026-11-09 正しい文の試し）。CN_FRAME_GUARD_ORIG_OK=0 で前のまま
        if os.environ.get('CN_FRAME_GUARD_ORIG_OK') != '0':
            quiet = {(min(o[1], len(line) - 1), min(max(o[2], o[1] + 1), len(line))) for o in bad
                     if _frame_at(line, o[1]) is True}
            if quiet:
                out['odd_spans'] = [sp for sp in out.get('odd_spans') or () if tuple(sp[:2]) not in quiet]
                out['odd_reasons'] = [r for r in out.get('odd_reasons') or ()
                                      if not (tuple(r[:2]) in quiet and r[2].startswith('直した形の「名詞＋助詞＋動詞」'))]
        return out
    except Exception:
        return result


def _lone_mark_fill(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                    nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes,
                    tab_has_kana, previous_line, defer_heavy):
    """かな入力で、付けようのない字の後ろに ゛ だけが残った所（まで の て が抜けた ま゛に・ので の ま゛ の゛・
    れば の れ゛）は、濁音の字の清音の1打が抜けた跡（て・゛ の2打のうち て が抜けた）。か・さ・た・は行の字を
    足した行のうち並びの費用が最も低いものを補正に通し直し、その所に紫が残らなければそちらにする（゛ を消す
    だけの直しは違う）。CN_LONE_MARK_FILL=0 で前のまま"""
    import os
    import unicodedata
    if (os.environ.get('CN_LONE_MARK_FILL') == '0' or not isinstance(result, dict) or _DOUBLE_MARK_BUSY
            or input_method != 'kana'):
        return result
    m = _lone_mark_fill_at(line)
    if m is None:
        return result
    done = result.get('corrected') or line
    odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
    # もう ゛ の所が直って（ご連絡・漢字の語）いて紫も無いなら触らない
    if '゛' not in done and not any(a <= m < b for a, b in odd) and done != line[:m] + line[m + 1:]:
        # ただし ゛ を隣のキーの字に替えた直し（マ゛を開ける → 負けを開ける）の 名詞＋助詞＋動詞 が例文にも語の組の
        # 表にも無く、清音の字を足した形（まど → 窓を開ける）の組なら在るときは、足した形にする（2026-11-07）
        alt = _lone_fill_by_frame(line, done, m, store, context_vocab, decisions, input_method, context_vec,
                                  dict_index, nearby_words, recent_words, occurrence_readings,
                                  occurrence_calculations, occurrence_strokes, tab_has_kana, previous_line,
                                  defer_heavy)
        if alt is not None:
            return alt
        # 理由は残っているのに紫が外れた直し（実゛かく → 実がかく）は、紫を戻す。゛ の前の漢字ごと別の漢字に
        # 替えた直し（回゛の → 火事の: 会議 の ぎ の き が抜けた形）も、その漢字が読みの一部なので決めきれない。紫を付ける
        kanji_swap = ('一' <= line[m - 1] <= '鿿' and line[m - 1] not in done
                      and os.environ.get('CN_LONE_MARK_KANJI_PURPLE') != '0')
        if kanji_swap:
            # 直しは戻し（元の字のまま）、その所を紫にする
            parts = []
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
                parts.append(line[i1:i2] if tag != 'equal' and i1 <= m and m - 1 < i2 else done[j1:j2])
            new = ''.join(parts)
            out = dict(result)
            nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
            out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                        'original_spans': [[o[1], o[2]] for o in nops],
                        'details': [d for d in (result.get('details') or []) if not (d and '゛' in str(d[0]))],
                        'odd_spans': list(result.get('odd_spans') or ()) + [(m - 1, m + 1)]})
            return out
        # ただし ゛ を含む前後ごと別の語に直っている（名ヘラ゛手 → 並べて）なら、理由は古い。紫を戻さない
        mark_only = True
        if os.environ.get('CN_LONE_MARK_STALE') != '0':
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
                if tag != 'equal' and i1 <= m < i2 and i2 - i1 > 1:
                    mark_only = False
        if mark_only and any(len(x) > 1 and x[0] <= m < x[1] for x in (result.get('odd_reasons') or ())):
            out = dict(result)
            out['odd_spans'] = list(result.get('odd_spans') or ()) + [(m - 1, m + 1)]
            return out
        return result
    try:
        import morphology
        cands = []
        for base in _FILL_BASES:
            ch = unicodedata.normalize('NFC', base + '\u3099')
            cand = line[:m] + ch + line[m + 1:]
            c = morphology.path_cost(cand)
            if c is not None:
                cands.append((c, cand, ch))
        cands.sort()
    except Exception:
        return result
    if not cands:
        return result

    def purple():
        # 決めきれない（候補の費用が近い: 荒れず／荒れば）なら、直さずにその所を紫に（迷うなら紫）
        if any(a <= m < b for a, b in odd):
            return result
        out = dict(result)
        out['odd_spans'] = list(result.get('odd_spans') or ()) + [(m - 1, m + 1)]
        return out
    if len(cands) > 1 and cands[1][0] - cands[0][0] < LONE_FILL_MARGIN:
        return purple()
    # ゛ の前の2字の打つ順が入れ替わった形（なへら゛ ← ならべ）と読む方が、字を足す形より行の並びが良い（費用が低い）
    # なら、足す見方は違う。入れ替わりも決めきれない（2026-11-06 うに）ので紫（2026-11-08 補正担当: 本をなへら゛て置く
    # → なへらずて にしていた）。CN_LONE_FILL_SWAP=0 で前のまま
    if m >= 2 and os.environ.get('CN_LONE_FILL_SWAP') != '0':
        xm = unicodedata.normalize('NFC', line[m - 2] + '\u3099')
        if len(xm) == 1 and ('ぁ' <= line[m - 1] <= 'ゖ'):
            try:
                cs = morphology.path_cost(line[:m - 2] + line[m - 1] + xm + line[m + 1:])
            except Exception:
                cs = None
            if cs is not None and cs < cands[0][0]:
                return purple()
    line2, ch = cands[0][1], cands[0][2]
    quick = _quick_mark_insert(line, result, m, ch, ['゛', ch, 'かな入力'])
    if quick is not None:
        return quick
    _DOUBLE_MARK_BUSY.append(1)
    try:
        r2 = correct_line(line2, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                          occurrence_strokes, tab_has_kana, previous_line, defer_heavy)
    except Exception:
        return result
    finally:
        _DOUBLE_MARK_BUSY.pop()
    if not isinstance(r2, dict):
        return result
    if any(a <= m + 1 and m - 1 < b for a, b in (tuple(x[:2]) for x in list(r2.get('odd_spans') or ())
                                                  + list(r2.get('odd_reasons') or ()))):
        return purple()
    fixed = r2.get('corrected') or line2
    out = dict(r2)
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': fixed, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': [['゛', ch, 'かな入力']] + list(r2.get('details') or [])})
    out.pop('unsure_spans', None)
    return out


def _merge_odd_spans(result):
    """紫の範囲のうち、重なるもの・同じもの（[8,14] と [8,10]）を1つにまとめる（段ごとに足した紫が重なって出ていた:
    2026-11-06 挙動関連担当の測り）。範囲だけの紫（2つ組）だけをまとめる。CN_MERGE_ODD=0 で前のまま"""
    import os
    if os.environ.get('CN_MERGE_ODD') == '0' or not isinstance(result, dict):
        return result
    odd = list(result.get('odd_spans') or ())
    if len(odd) < 2 or not all(isinstance(x, (tuple, list)) and len(x) == 2 for x in odd):
        return result
    merged = []
    for a, b in sorted((int(x[0]), int(x[1])) for x in odd):
        if merged and a < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    if merged == [tuple(x) for x in odd]:
        return result
    out = dict(result)
    out['odd_spans'] = merged
    return out


def _quick_mark_insert(line, result, m, ch, det):
    """浮いた ゛ の所 m を ch にするとき、前の段の答えが ゛ を消しただけ・そのままなら、行全体を補正し直さずに
    その答えへ ch を入れる（PC では補正し直し1回に IME を何度も呼び、1行に数十秒かかる: 2026-11-06 挙動関連担当の測り）。
    当てはまらなければ None。CN_LONE_MARK_QUICK=0 で前のまま（いつも補正し直す）"""
    import os
    if os.environ.get('CN_LONE_MARK_QUICK') == '0':
        return None
    done = result.get('corrected') or line
    if done == line:
        new = line[:m] + ch + line[m + 1:]
    elif done == line[:m] + line[m + 1:]:
        new = done[:m] + ch + done[m:]
    else:
        return None
    out = dict(result)
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': new, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': [d for d in (result.get('details') or []) if not (d and d[0] and '゛' in str(d[0]))] + [det],
                'odd_spans': [sp for sp in (result.get('odd_spans') or ()) if not (sp[0] <= m < sp[1])]})
    if 'odd_reasons' in out:
        out['odd_reasons'] = [r for r in (out.get('odd_reasons') or ()) if not (r[0] <= m < r[1])]
    out.pop('unsure_spans', None)
    return out


def _lone_mark_go(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index,
                  nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes,
                  tab_has_kana, previous_line, defer_heavy):
    """かな入力で、漢字の語の前に ゛ だけが残った所（までに**゛**連絡）は、接頭の ご の こ が抜けた跡（こ・゛ の
    2打のうち こ が抜けた）。゛ を ご にした行で ご が接頭詞として名詞に付き、補正を通し直してその所に紫が
    残らなければそちらにする（゛ を消して 連絡 にするのも、隣のキーの へ にするのも違う）。CN_LONE_MARK_GO=0 で前のまま"""
    import os
    if (os.environ.get('CN_LONE_MARK_GO') == '0' or not isinstance(result, dict) or _DOUBLE_MARK_BUSY
            or input_method != 'kana'):
        return result
    m = _lone_mark_at(line)
    if m is None:
        return result
    done0 = result.get('corrected') or line
    if done0 != line and os.environ.get('CN_LONE_MARK_GO_DONE') != '0':
        # 前の段がその ゛ の所をもう直した行（改めてみ゛連絡 → 改めてご連絡: み も打ち違い）は、元の行に ご を入れ直さない
        # （み が残って 改めてみご連絡 になっていた・2026-11-06 かなの試験）
        if any(o[0] != 'equal' and o[1] <= m < max(o[2], o[1] + 1)
               for o in difflib.SequenceMatcher(None, line, done0, autojunk=False).get_opcodes()):
            return result
    line2 = line[:m] + 'ご' + line[m + 1:]
    try:
        import morphology
        toks = list(morphology.tokenize(line2))
    except Exception:
        return result
    at = [i for i, t in enumerate(toks) if t.start == m]
    if not at or toks[at[0]].surface != 'ご' or toks[at[0]].pos != '接頭詞' or at[0] + 1 >= len(toks):
        return result
    nx = toks[at[0] + 1]
    if nx.pos != '名詞' or not all('一' <= c <= '鿿' for c in nx.surface) or len(nx.surface) < 2:
        return result
    # ゛ は後ろの字に付くはずだった ゛ の打つ順の入れ替わり（゛粉炭 = ぶんたん の ゛ が前に出た）でもあり得る。
    # 名詞の読みの1字目に ゛ が付けられる（か・さ・た・は行）なら決められないので紫に。珍しい名詞（旬日）も紫に（batch220）
    import unicodedata as _ud
    try:
        import ime_reconvert as _R
        rd = (getattr(nx, 'reading', '') or '')[:1]
        h = chr(ord(rd) - 0x60) if 'ァ' <= rd <= 'ヶ' else rd
        voiceable = bool(h) and len(_ud.normalize('NFC', h + '\u3099')) == 1
        # ご の こ でなく、別の濁音の字の清音が抜けた形（゛医療 = ざいりょう の さ が抜けた: 材料）もあり得る。
        # 濁音の字＋名詞の読みで身近な語が引けるなら決めきれない。後ろに漢字の名詞が続く（゛遺産会議室）のも紫に（batch221）
        rival = False
        nxt_kanji = at[0] + 2 < len(toks) and toks[at[0] + 2].start == nx.end and toks[at[0] + 2].pos == '名詞' \
            and all('一' <= c <= '鿿' for c in toks[at[0] + 2].surface)
        if not voiceable and os.environ.get('CN_LONE_MARK_GO_RIVAL') != '0':
            try:
                import last_keystroke as _LK
                rd_all = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (getattr(nx, 'reading', '') or ''))
                for v in 'がぎぐげざじずぜぞだぢづでどばびぶべぼ':
                    if any(_R._rank(f) < _R.DOUBT for f in _LK._kanji_choices(v + rd_all, store, dict_index)[:3]):
                        rival = True
                        break
            except Exception:
                rival = True
        if os.environ.get('CN_LONE_MARK_GO_STRICT') != '0' and (voiceable or rival or nxt_kanji
                                                                 or _R._rank(nx.surface) >= _R.DOUBT):
            odd = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
            if any(a <= m < b for a, b in odd):
                return result
            out = dict(result)
            out['odd_spans'] = list(result.get('odd_spans') or ()) + [(m, m + 1 + len(nx.surface))]
            return out
    except Exception:
        return result
    quick = _quick_mark_insert(line, result, m, 'ご', ['゛', 'ご', 'かな入力'])
    if quick is not None:
        return quick
    _DOUBLE_MARK_BUSY.append(1)
    try:
        r2 = correct_line(line2, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations,
                          occurrence_strokes, tab_has_kana, previous_line, defer_heavy)
    except Exception:
        return result
    finally:
        _DOUBLE_MARK_BUSY.pop()
    if not isinstance(r2, dict):
        return result
    if any(a <= m < b or a <= m + 1 < b for a, b in (tuple(x[:2]) for x in r2.get('odd_spans') or ())):
        return result
    fixed = r2.get('corrected') or line2
    if fixed[m:m + 1] != 'ご':
        return result
    out = dict(r2)
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': fixed, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                'original_spans': [[o[1], o[2]] for o in ops],
                'details': [['゛', 'ご', 'かな入力']] + list(r2.get('details') or [])})
    out.pop('unsure_spans', None)
    return out


# ------------------------------------------------------------
# 平仮名の後ろの「ー」（伸ばし: すごーい・みかーん・だれかー）と、その句の終わりの「っ」（どけーっ）は話し言葉の書き方
# （うに 2026-11-03 未解決タブ「誤判定」: 伸ばしの ー を隣のキーの へ に、句末の っ を別のかなに直していた）
# ------------------------------------------------------------
_HIRA_RUN_END = '。、，．,.！？!?…～〜」』）)】 　\t'


def _elongated_runs(line):
    """伸ばしの ー を含む平仮名の並び [(start, end)]。並びは句の終わり（行末・句読点・空白・閉じ括弧）まで続き、
    平仮名の直後の ー の後ろは2字以内（みかーん・すごーい・そーだね）。"""
    import re
    out = []
    for m in re.finditer('[ぁ-ゖー]+', line):
        a, b = m.start(), m.end()
        if b < len(line) and line[b] not in _HIRA_RUN_END:
            continue
        run = line[a:b]
        ok = False
        for i, c in enumerate(run):
            if c == 'ー' and i > 0 and 'ぁ' <= run[i - 1] <= 'ゖ':
                tail = run[i + 1:].lstrip('ー')
                if len(tail) <= 2:
                    ok = True
        if ok:
            out.append((a, b))
    return out


_VOWEL_ROWS = {
    'a': 'あかさたなはまやらわがざだばぱぁゃ', 'i': 'いきしちにひみりぎじぢびぴぃ',
    'u': 'うくすつぬふむゆるぐずづぶぷぅゅ', 'e': 'えけせてねへめれげぜでべぺぇ',
    'o': 'おこそとのほもよろをごぞどぼぽぉょ',
}


def _unelongate(text, vowel):
    """伸ばしの ー を抜く（vowel=False）か前の字の母音のかなにする（お段は う）。並びの終わりの っ も抜く。"""
    out = []
    for i, c in enumerate(text):
        if c == 'ー' and out and 'ぁ' <= out[-1] <= 'ゖ':
            if vowel:
                prev = out[-1]
                for v, row in _VOWEL_ROWS.items():
                    if prev in row:
                        out.append({'a': 'あ', 'i': 'い', 'u': 'う', 'e': 'え', 'o': 'う'}[v])
                        break
            continue
        out.append(c)
    s = ''.join(out)
    while s.endswith('っ') and len(s) > 1:
        s = s[:-1]
    return s


def _loan_fix(corrected, ops, line=None):
    """伸ばしの並びの直しが、ひらがなの外来語を身近な片仮名の語に戻したもの（めなゅー→メニュー）なら、話し言葉の
    伸ばしではない。戻さない（2026-11-06 うにの画面）。CN_ELONGATION_LOAN=0 で前のまま"""
    import os
    if os.environ.get('CN_ELONGATION_LOAN') == '0':
        return False
    try:
        import kana_lattice_place as K
    except Exception:
        return False
    def kata(c):
        return 'ァ' <= c <= 'ヶ' or c == 'ー'
    for o in ops:
        j1, j2 = o[3], o[4]
        if j1 < j2 and line is not None and not all(kata(c) for c in corrected[j1:j2]) \
                and os.environ.get('CN_ELONGATION_LOAN_HEAD') != '0':
            # 前のかなを同じ読みの漢字にした所と一つの直しになった（がくしゅうめにゅー → 学習メニュー）。
            # 漢字の所の読みが元のかなと同じなら、片仮名の所だけを見る（2026-11-09 手分けB）。CN_ELONGATION_LOAN_HEAD=0
            k = j2
            while k > j1 and kata(corrected[k - 1]):
                k -= 1
            head = corrected[j1:k]
            try:
                import morphology
                rd = ''.join(t.reading or '' for t in morphology.tokenize(head))
                rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in rd)
            except Exception:
                rd = None
            if (k < j2 and head and rd and line[o[1]:o[1] + len(rd)] == rd
                    and all('一' <= c <= '鿿' or c == '々' for c in head)):
                j1 = k
        if j1 >= j2 or not all(kata(c) for c in corrected[j1:j2]):
            return False
        while j1 > 0 and kata(corrected[j1 - 1]):
            j1 -= 1
        while j2 < len(corrected) and kata(corrected[j2]):
            j2 += 1
        # 片仮名の並び（デバッグメニュー）の後ろの切れ目から、身近な語（メニュー）になるもの
        if not any(K._kata_common(corrected[x:j2]) for x in range(j1, max(j1, o[3]) + 1) if j2 - x >= 3):
            return False
    return True


def _elongation_guard(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index):
    """伸ばしの ー を含む句末の平仮名の並びに掛かる直しは、話し言葉の書き方を打ち違いと見たものなので戻す。
    その並びの紫は、伸ばしを抜いた形（か母音にした形）が直しも紫も無く通るなら外す（抜いても通らなければ残す）。"""
    import os
    if os.environ.get('CN_ELONGATION_GUARD') == '0' or not isinstance(result, dict) or 'ー' not in line:
        return result
    try:
        runs = _elongated_runs(line)
    except Exception:
        return result
    if not runs:
        return result
    out = result
    corrected = result.get('corrected')
    if corrected and corrected != line:
        import difflib
        ops = [o for o in difflib.SequenceMatcher(None, line, corrected, autojunk=False).get_opcodes() if o[0] != 'equal']
        hit = [o for o in ops if any(o[1] <= b and a <= o[2] for a, b in runs)]
        if hit and len(hit) == len(ops) and _loan_fix(corrected, hit, line):
            hit = []
        if hit and len(hit) == len(ops):
            out = dict(result)
            out.update({'corrected': line, 'changed': False, 'details': [], 'spans': [], 'original_spans': []})
        elif hit:
            return result
    odd = [tuple(o[:2]) for o in (out.get('odd_spans') or ())]
    inside = [o for o in odd if any(a <= o[0] and o[1] <= b for a, b in runs)]
    if not inside:
        return out
    clean = []
    for a, b in runs:
        ok = False
        for vowel in (False, True):
            norm = _unelongate(line[a:b], vowel)
            if not norm or norm == line[a:b]:
                continue
            probe = line[:a] + norm + line[b:]
            try:
                import used_keys as _uk
                got = _correct_line_strokes(probe, store, context_vocab, decisions, input_method, context_vec,
                                            dict_index, (), _uk.RecentWords(()), (), (), ())
            except Exception:
                got = None
            if not isinstance(got, dict):
                continue
            na, nb = a, a + len(norm)
            if (got.get('corrected') or probe)[na:nb] != norm and got.get('corrected') != probe:
                continue
            if got.get('corrected') not in (None, probe):
                import difflib
                if any(o[0] != 'equal' and o[1] <= nb and na <= o[2]
                       for o in difflib.SequenceMatcher(None, probe, got['corrected'], autojunk=False).get_opcodes()):
                    continue
            if any(o[0] < nb and na < o[1] for o in (tuple(x[:2]) for x in (got.get('odd_spans') or ()))):
                continue
            ok = True
            break
        if ok:
            clean.append((a, b))
    if not clean:
        return out
    keep = [o for o in (out.get('odd_spans') or ()) if not any(a <= o[0] and o[1] <= b for a, b in clean)]
    if len(keep) == len(out.get('odd_spans') or ()):
        return out
    out = dict(out)
    out['odd_spans'] = keep
    out['odd_reasons'] = [r for r in (out.get('odd_reasons') or ())
                          if not any(a <= r[0] and r[1] <= b for a, b in clean)]
    return out


def _typed_reading_around(line, i1, i2, occurrence_readings, widest=12):
    """line[i1:i2] を含む一番狭い所 (a, b, [打った読み])。この行の確定の読み（occurrence_readings）を先に、
    無ければ IME の読みの記録（kanji_guess.ime_readings_for）。無ければ None。"""
    best = None
    for occ in occurrence_readings or ():
        try:
            a, b, surface, reading = occ[:4]
        except (TypeError, ValueError):
            continue
        if a <= i1 and i2 <= b and line[a:b] == surface and reading:
            if best is None or b - a < best[1] - best[0]:
                best = (a, b, [reading])
    if best is not None:
        return best
    try:
        import kanji_guess
    except Exception:
        return None
    if kanji_guess._IME_READINGS_PROVIDER is None:
        return None
    for width in range(max(1, i2 - i1), min(len(line), widest) + 1):
        for a in range(max(0, i2 - width), min(i1, len(line) - width) + 1):
            got = kanji_guess.ime_readings_for(line[a:a + width])
            if got:
                return (a, a + width, got)
    return None


FAR_TYPED_KEYS = 3   # どの段も、打った読みからこれ以上離れた直しは出さないつもり（直しは1打か2打の打ち違い）


def _far_typed_guard(line, result, occurrence_readings=()):
    """
    直した所の読みが、そこで打った読み（IME の確定の読み）から3打以上離れ、元の顔より遠くなる直しは、打ち違いでは
    説明が付かないので直さず紫にする（2026-11-02 補正担当。onekey3 の記録ありで、正しく直った行はどれも打った読みから
    1打、別の語に誤って直した行の一部は3打以上: の意月→毎月 のような形）。打った読みが分からない所は今まで通り。
    """
    import os
    if os.environ.get('CN_FAR_TYPED') == '0' or not isinstance(result, dict):
        return result
    corrected = result.get('corrected')
    if not corrected or corrected == line:
        return result
    try:
        import difflib
        import morphology
        import odd_respell
        kt = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
        rd = lambda t: ''.join((x.reading if x.has_reading else x.surface).translate(kt) for x in morphology.tokenize(t))
        ops = difflib.SequenceMatcher(None, line, corrected, autojunk=False).get_opcodes()
        far = []
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal':
                continue
            # 直した所に続く漢字（同じ語の残り: の意｜月 → 毎｜月 の 月）まで広げる（読みが替わるのは語ごと）
            kj = lambda ch: '一' <= ch <= '鿿' or ch == '々'
            w1, w2 = i1, max(i2, i1 + 1) if i1 < len(line) else i2
            while w1 > 0 and kj(line[w1 - 1]) and (j1 - (i1 - w1) - 1) >= 0 and kj(corrected[j1 - (i1 - w1) - 1]):
                w1 -= 1
            while w2 < len(line) and kj(line[w2]) and (j2 + (w2 - max(i2, i1))) < len(corrected) \
                    and kj(corrected[j2 + (w2 - max(i2, i1))]):
                w2 += 1
            got = _typed_reading_around(line, w1, w2, occurrence_readings)
            if got is None:
                continue
            a, b, typed = got
            # 行全体の読みで比べる（切り出した所だけを読むと語の読みがずれる）。打った行の読み＝前後は顔の読み、
            # その所だけ打った読み
            K = odd_respell._keys
            # この直しだけを当てた行で比べる（ほかの所の直しまで数えると、2か所以上を直した行が打った読みから遠く
            # 見えて、行の直しが全部戻っていた: 挙動関連担当の切り分け 2026-11-03）
            only = line[:i1] + corrected[j1:j2] + line[i2:] if os.environ.get('CN_FAR_TYPED_WHOLE') != '1' else corrected
            whole_new, whole_old = K(rd(only)), K(rd(line))
            pre, post = rd(line[:a]), rd(line[b:])
            news = [whole_new]
            typs = list(typed)
            if os.environ.get('CN_FAR_GUARD_ALTS') != '0':
                # 1字の漢字は字の読みも（行 を くだり と読まない）、打った読みは付く先の無い ゛゜ を抜いた形も見る
                # （odd_respell._far_from_typed と同じ見方・2026-11-03 うに 優先の行）
                try:
                    news += [K(x) for x in odd_respell._line_reading_alts(only)]
                    typs += [x for x in (odd_respell._drop_stray_marks(t) for t in typed) if x not in typs]
                except Exception:
                    pass
            dn = min(odd_respell._key_distance(n, K(pre + t + post)) for t in typs for n in news)
            do = min(odd_respell._key_distance(whole_old, K(pre + t + post)) for t in typed)
            if dn >= FAR_TYPED_KEYS and dn > do:
                if os.environ.get('CN_FAR_TYPED_SHIFT') != '0' and os.environ.get('CN_HAND_SHIFT') != '0' \
                        and _shift_wide_explains(line, only):
                    # 手の位置のずれ（片手が揃って隣のキーへ: えりすうと → おりかえし）で説明の付く直しは、打った読みから
                    # 離れていても打ち違いの戻し（2026-11-10 手のずれ・全体評価の束）。CN_FAR_TYPED_SHIFT=0 で前のまま
                    continue
                far.append((i1, max(i2, i1 + 1)))
    except Exception:
        return result
    if not far:
        return result
    out = dict(result)
    out.update({'corrected': line, 'changed': False, 'details': [], 'spans': [], 'original_spans': []})
    odd = [tuple(o[:2]) for o in (result.get('odd_spans') or ())]
    for sp in far:
        sp = (min(sp[0], len(line) - 1), min(sp[1], len(line)))
        if not any(o[0] < sp[1] and sp[0] < o[1] for o in odd):
            odd.append(sp)
    out['odd_spans'] = sorted(odd)
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, f'「{line[a:b]}」の直しは打った読みから遠い') for a, b in far]
    return out


def _given_name_spans(line):
    """名字（janome の 人名:姓）の直後（空白を挟んでもよい）に続く漢字の並び [(start, end)]。名字の後は名前で、
    ふつうの語の読み（佑→たすく）で見て直さない（2026-11-02 うに「直前にあるのが苗字なので、続くものは名前として扱う」）。"""
    import morphology
    toks = list(morphology.tokenize(line))
    out = []
    kj = lambda ch: '一' <= ch <= '鿿' or ch == '々'
    for i, t in enumerate(toks):
        if '人名:姓' not in (t.pos_sub or ''):
            continue
        # 名字は2字以上で、行頭・空白・記号の後に立つもの（漢字の並びの途中の1字を名字に読んだ形: 蘇｜峰子・雅｜太 は除く）
        if len(t.surface) < 2 or (t.start > 0 and not (line[t.start - 1] in ' \u3000' or not line[t.start - 1].isalnum())):
            continue
        k = t.end
        while k < len(line) and line[k] in ' \u3000':
            k += 1
        # 空白を挟むか、続く語が名前（人名:名）のときだけ（加藤木 の 木 は名前ではない）
        nxt = next((u for u in toks[i + 1:] if u.start >= k), None)
        if k == t.end and not (nxt is not None and nxt.start == k and '人名:名' in (nxt.pos_sub or '')):
            continue
        e = k
        while e < len(line) and kj(line[e]):
            e += 1
        if e > k:
            out.append((k, e))
    return out


NOUN_SURU_COMMON = 500   # 直す先のサ変の名詞の身近さの線（ime_reconvert の表の順位）
_SURU_HEADS = ('し', 'する', 'すれ', 'さ', 'せ', 'しよ', 'しろ')


def _noun_suru(line, result):
    """_noun_suru_core の入口。前の段が名詞のすぐ後ろの する の形（して）だけを別の語に替えた行（有線して補正 → 有線と補正:
    紫の所の読み直しが して を と にした）も、元の行で する の付かない名詞＋する を見る。名詞が同じ読みの する の付く
    身近な語に1つに決まれば、前の段の替えを捨ててそちらにする（2026-11-08 うにの未解決タブ・作った例）。
    決まらなければ前の段の答えのまま。CN_NOUN_SURU_OVER_FIX=0 で前のまま。"""
    import os
    if not isinstance(result, dict) or (result.get('corrected') or line) == line \
            or os.environ.get('CN_NOUN_SURU_OVER_FIX') == '0' or os.environ.get('CN_NOUN_SURU') == '0':
        return _noun_suru_core(line, result)
    try:
        from morphology import tokenize
        toks = list(tokenize(line))
    except Exception:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, result.get('corrected') or line, autojunk=False).get_opcodes()
           if o[0] != 'equal']
    for i in range(len(toks) - 1):
        t, q = toks[i], toks[i + 1]
        if not (t.pos == '名詞' and q.pos == '動詞' and q.base_form == 'する' and q.start == t.end):
            continue
        end = q.end
        if i + 2 < len(toks) and toks[i + 2].start == q.end and toks[i + 2].pos in ('助詞', '助動詞'):
            end = toks[i + 2].end
        if not ops or not all(q.start <= o[1] and o[2] <= end for o in ops):
            continue
        base = {'original': line, 'corrected': line, 'changed': False, 'spans': [], 'original_spans': [],
                'details': [], 'odd_spans': [(t.start, end)],
                'odd_reasons': [], 'unsure_spans': []}
        got = _noun_suru_core(line, base)
        if (got.get('corrected') or line) != line:
            out = dict(result)
            for k in ('corrected', 'changed', 'spans', 'original_spans', 'details'):
                out[k] = got.get(k)
            out['odd_spans'] = [x for x in (result.get('odd_spans') or ()) if not (x[0] < end and t.start < x[1])]
            out['odd_reasons'] = [x for x in (result.get('odd_reasons') or ()) if not (x[0] < end and t.start < x[1])]
            out['unsure_spans'] = [x for x in (result.get('unsure_spans') or ()) if not (x[0] < end and t.start < x[1])]
            return out
    return result


def _noun_suru_core(line, result):
    """する の付かない名詞（辞書でサ変接続を持たない名詞）に する が直に付いた所（作業が官僚しました）。同じ読みで
    する の付く名詞が身近なものに1つだけ在れば直し（完了）、在っても1つに決まらない・身近でなければ紫にする。
    読みが同じでサ変の語が無い名詞（仕事する のように辞書で一般名詞の語）は見ない（2026-11-05 挙動関連担当:
    試験の作った例「作業が官僚しました。」が直らず紫も無い。IME が同じ読みの別の語を選んだ形）。
    切り替え CN_NOUN_SURU=0。"""
    import os
    if os.environ.get('CN_NOUN_SURU') == '0' or not isinstance(result, dict) \
            or (result.get('corrected') or line) != line:
        return result
    try:
        from morphology import tokenize, dictionary_inflections, path_cost
        import last_keystroke as _LK
        import ime_reconvert as _R
    except Exception:
        return result
    kanji = lambda w: len(w) >= 2 and all('一' <= c <= '鿿' or c == '々' for c in w)
    jm = _jm_suru()
    # する の付く名詞か: 辞書（IPA）のサ変接続か、JMdict（同梱の jm_pred）で する の付く語（返信: IPA は一般名詞だが返信する）
    sahen = lambda w: w in jm or any(r[0].startswith('名詞,サ変接続') for r in (dictionary_inflections(w) or ()))
    toks = list(tokenize(line))
    odd = list(result.get('odd_spans') or ())
    out = None
    for i in range(len(toks) - 1):
        t, q = toks[i], toks[i + 1]
        if not (t.pos == '名詞' and t.pos_sub == '一般' and kanji(t.surface) and q.start == t.end
                and q.pos == '動詞' and q.base_form == 'する' and q.surface.startswith(_SURU_HEADS)):
            continue
        # 前は文の頭か助詞・記号（複合語の後ろの名詞 〜官僚 は見ない）
        p = toks[i - 1] if i else None
        if p is not None and p.end == t.start and p.pos not in ('助詞', '記号'):
            continue
        if sahen(t.surface) or not t.has_reading:
            continue
        # 前の段が紫を付けた所も、身近な する の付く語が1つに決まるなら直す（紫は外す）。決まらなければ前のまま
        # （2026-11-06 PC: 不測 に紫が付くと 不足 に直らなかった）。CN_NOUN_SURU_OVER_ODD=0 で前のまま
        marked = any(s < t.end and t.start < e for s, e, *_ in odd)
        if marked and os.environ.get('CN_NOUN_SURU_OVER_ODD') == '0':
            continue
        rows = _LK._seed_surfaces(_kata_to_hira(t.reading))
        rivals = [f for f, _c in rows if f != t.surface and kanji(f) and sahen(f)]
        if not rivals:
            continue
        common = [f for f in dict.fromkeys(rivals) if _R._rank(f) <= NOUN_SURU_COMMON]
        a, b = t.start, t.end
        if len(common) == 1:
            fixed = line[:a] + common[0] + line[b:]
            c0, c1 = path_cost(line), path_cost(fixed)
            if c0 is not None and c1 is not None and c1 < c0:
                out = dict(result)
                out.update({'corrected': fixed, 'changed': True, 'spans': [[a, a + len(common[0])]],
                            'original_spans': [[a, b]],
                            'details': list(result.get('details') or ()) + [(t.surface, common[0], '同じ読みの する の付く語')]})
                if marked:
                    out['odd_spans'] = [x for x in odd if not (x[0] < q.end and a < x[1])]
                    out['odd_reasons'] = [x for x in (result.get('odd_reasons') or ()) if not (x[0] < q.end and a < x[1])]
                    if result.get('unsure_spans'):
                        out['unsure_spans'] = [x for x in result['unsure_spans'] if not (x[0] < q.end and a < x[1])]
                return out
        if marked:
            continue
        out = dict(out or result)
        out['odd_spans'] = list(out.get('odd_spans') or ()) + [(a, q.end)]
        out['odd_reasons'] = list(out.get('odd_reasons') or ()) + [
            (a, q.end, f'「{t.surface}」に「する」は付きません（同じ読み: {"・".join(dict.fromkeys(rivals[:3]))}）')]
    return out or result


_JM_SURU = None


def _jm_suru():
    """JMdict（jm_pred.json.gz）で する の付く語（suru）の集まり。読めなければ空。"""
    global _JM_SURU
    if _JM_SURU is None:
        try:
            import gzip, json, os
            with gzip.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jm_pred.json.gz'), 'rt',
                           encoding='utf-8') as f:
                d = json.load(f)
            _JM_SURU = frozenset(w for w, v in d.items() if isinstance(v, dict) and 'suru' in v)
        except Exception:
            _JM_SURU = frozenset()
    return _JM_SURU


def _kata_to_hira(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (text or ''))


def _given_name_guard(line, result):
    """名字の後の名前に掛かった直しは戻し、紫も外す。ほかの所の直しはそのまま。"""
    import os
    if os.environ.get('CN_GIVEN_NAME') == '0' or not isinstance(result, dict):
        return result
    try:
        names = _given_name_spans(line)
    except Exception:
        return result
    if not names:
        return result
    hit = lambda a, b: any(a < e and s < max(b, a + 1) for s, e in names)
    out = dict(result)
    changed = False
    for key in ('odd_spans', 'unsure_spans'):
        spans = result.get(key) or ()
        kept = [sp for sp in spans if not hit(sp[0], sp[1])]
        if len(kept) != len(spans):
            out[key] = kept
            changed = True
    if out.get('odd_reasons'):
        out['odd_reasons'] = [r for r in out['odd_reasons'] if not hit(r[0], r[1])]
    corrected = result.get('corrected') or line
    if corrected != line:
        import difflib
        ops = difflib.SequenceMatcher(None, line, corrected, autojunk=False).get_opcodes()
        if any(tag != 'equal' and hit(i1, i2) for tag, i1, i2, j1, j2 in ops):
            final = ''.join(line[i1:i2] if (tag == 'equal' or hit(i1, i2)) else corrected[j1:j2]
                            for tag, i1, i2, j1, j2 in ops)
            fops = [o for o in difflib.SequenceMatcher(None, line, final, autojunk=False).get_opcodes()
                    if o[0] != 'equal']
            out.update({'corrected': final, 'changed': final != line,
                        'details': [[line[i1:i2], final[j1:j2], '打ち違い'] for tag, i1, i2, j1, j2 in fops],
                        'spans': [[j1, j2] for tag, i1, i2, j1, j2 in fops],
                        'original_spans': [[i1, i2] for tag, i1, i2, j1, j2 in fops]})
            changed = True
    return out if changed else result


def _unexplained_kana_runs(text, changed):
    """直した範囲に掛かるかなの並びのうち、語の表＋機能語＋活用の文法（pos_grammar.explain_kana_run）で説明の付かない
    もの [(start, end)]。並びの前の漢字（送りがなの語幹）・後ろが漢字か・行頭かも渡す。"""
    import re
    import pos_grammar
    out = []
    for m in re.finditer('[ぁ-ゖー]+', text):
        a, b = m.start(), m.end()
        if not any(s <= b and a <= e for s, e in changed):
            continue
        k = a
        while k > 0 and ('一' <= text[k - 1] <= '鿿' or text[k - 1] == '々'):
            k -= 1
        stem = text[k:a]
        before_kanji = b < len(text) and ('一' <= text[b] <= '鿿' or text[b] == '々')
        run = text[a:b]
        # 漢字の前の お・ご は次の語の接頭辞（返事｜お｜願い）。残りだけを見る
        if before_kanji and run[-1:] in ('お', 'ご'):
            run = run[:-1]
            if not run:
                continue
        if not pos_grammar.explain_kana_run(run, after_kanji=bool(stem), kanji_stem=stem,
                                            before_kanji=before_kanji, bare_head=(a == 0)):
            out.append((a, b))
        elif any(c in 'ゃゅょ' and text[a + i - 1] not in _YOON_HEADS for i, c in enumerate(run) if i > 0):
            # 拗音の付けられない字の後ろの ゃゅょ（しましたょ）は、文末の言い回しとしても説明しない
            out.append((a, b))
    return out


_YOON_HEADS = frozenset('きしちにひみりぎじぢびぴてでふゔう')


def _unexplained_change_guard(line, result):
    """
    直した後の行で、直した所に掛かるかなの並びが文法で説明の付かない形（印刷しとて・れて増加）になったら、
    その直しは決め手がないので直さず紫にする（迷うなら紫・2026-11-02 補正担当。onekey3 の記録ありで、別の語に
    誤って直す行の一部がこの形。正しく直った行には出なかった）。直す前の元の行の位置に紫を付ける。
    """
    import os
    if os.environ.get('CN_CHANGE_GUARD') == '0' or not isinstance(result, dict):
        return result
    corrected = result.get('corrected')
    if not corrected or corrected == line:
        return result
    try:
        import difflib
        ops = difflib.SequenceMatcher(None, line, corrected, autojunk=False).get_opcodes()
        changed = [(j1, j2) for tag, i1, i2, j1, j2 in ops if tag != 'equal']
        bad = _unexplained_kana_runs(corrected, changed)
    except Exception:
        return result
    # 説明の付かない並びが、和語なのでかなに戻した語（ひるごはん: kana_keep）に掛かるだけで、戻す前の漢字の行
    # （食堂で昼ご飯を食べた）では説明が付くなら、直しのせいではない（その語がかなの語の表に無いだけ）。CN_CHANGE_GUARD_KEPT=0
    kk = result.get('_kana_kept')
    if bad and kk and os.environ.get('CN_CHANGE_GUARD_KEPT') != '0':
        try:
            pre, kept_pos = kk
            if all(corrected[x:y] and any('ぁ' <= c <= 'ゖ' for c in corrected[x:y]) for x, y in kept_pos):
                ops_p = difflib.SequenceMatcher(None, line, pre, autojunk=False).get_opcodes()
                ch_p = [(j1, j2) for tag, i1, i2, j1, j2 in ops_p if tag != 'equal']
                if (not _unexplained_kana_runs(pre, ch_p)
                        and all(any(x < b and a < y for x, y in kept_pos) for a, b in bad)):
                    return result
        except Exception:
            pass
    # 説明の付かない所が、元から紫の残る所（直していない別の打ち違い）なら、その直しのせいではない
    odd0 = [tuple(o[:2]) for o in (result.get('odd_spans') or ())]
    def _to_line(j):
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and j1 <= j < j2:
                return j - j1 + i1
        return None
    keep = []
    left = []
    for a, b in bad:
        pos = [_to_line(j) for j in range(a, b)]
        if any(i is not None and any(s <= i < e for s, e in odd0) for i in pos):
            continue
        # 直していない（元の行と同じ字の並びで、前後も同じ）かなの並びが、元の行でも説明の付かない形なら、
        # 直しのせいではなく残った別の打ち違い。直しは残して、その並びに紫を付ける（2026-11-03 記録のある行:
        # 残った打ち違いの隣を正しく直したのに、行ごと戻されていた）
        if os.environ.get('CN_CHANGE_GUARD_OLD') != '1' and None not in pos and pos == list(range(pos[0], pos[0] + b - a)):
            a1, b1 = pos[0], pos[0] + b - a
            def _kj(ch):
                return bool(ch) and ('一' <= ch <= '鿿' or ch == '々')
            def _stem(t, k):
                m = k
                while m > 0 and _kj(t[m - 1]):
                    m -= 1
                return t[m:k]
            # 説明の付き方を決める前後（前の漢字の語幹・後ろが漢字か）が元の行と同じとき
            same_ctx = (line[a1:b1] == corrected[a:b] and _stem(line, a1) == _stem(corrected, a)
                        and _kj(line[b1:b1 + 1]) == _kj(corrected[b:b + 1]))
            try:
                old_bad = same_ctx and (a1, b1) in _unexplained_kana_runs(line, [(a1, b1)])
            except Exception:
                old_bad = False
            if old_bad:
                left.append((a1, b1))
                continue
        # 片仮名の語の後ろに続くかな（シャつ を の つ）は、混ぜ書きの名詞の一部。直していないその頭を除いた残り
        # （をください）が説明の付く形なら、直しのせいではない（2026-11-03 tests_mixed_nominal_argument）
        if os.environ.get('CN_CHANGE_GUARD_KATA') != '0' and a > 0 and 'ァ' <= corrected[a - 1] <= 'ヶ':
            first = min([j1 for j1, j2 in changed if a <= j1 < b] or [b])
            ok = False
            for cut in range(1, first - a + 1):
                p0 = _to_line(a)
                if p0 is None or line[p0:p0 + cut] != corrected[a:a + cut]:
                    break
                try:
                    import pos_grammar
                    before_kanji = b < len(corrected) and ('一' <= corrected[b] <= '鿿' or corrected[b] == '々')
                    if pos_grammar.explain_kana_run(corrected[a + cut:b], after_kanji=False, kanji_stem='',
                                                    before_kanji=before_kanji, bare_head=False):
                        ok = True
                        break
                except Exception:
                    break
            if ok:
                continue
        keep.append((a, b))
    bad = keep
    if not bad:
        if left:
            out = dict(result)
            odd = [tuple(o[:2]) for o in (result.get('odd_spans') or ())]
            add = [sp for sp in left if not any(o[0] < sp[1] and sp[0] < o[1] for o in odd)]
            if add:
                out['odd_spans'] = sorted(odd + add)
                out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
                    (a, b, f'「{line[a:b]}」は文の形に説明が付かない') for a, b in add]
            return out
        return result
    spans = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            continue
        if any(j1 <= b and a <= j2 for a, b in bad):
            a0, b0 = i1, max(i2, i1 + 1)
            spans.append((max(0, min(a0, len(line) - 1)), min(len(line), b0)))
    if not spans:
        return result
    out = dict(result)
    out.update({'corrected': line, 'changed': False, 'details': [], 'spans': [], 'original_spans': []})
    odd = [tuple(o[:2]) for o in (result.get('odd_spans') or ())]
    for sp in spans:
        if not any(o[0] < sp[1] and sp[0] < o[1] for o in odd):
            odd.append(sp)
    out['odd_spans'] = sorted(odd)
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
        (a, b, f'「{line[a:b]}」は直すと文の形に説明が付かない') for a, b in spans]
    return out


# ------------------------------------------------------------
# 前の行から続く文（うに 2026-11-02「一行前から続く文を意図的に接続詞で改行する書き方はあるので、接続詞が前行末尾から
# 続いて行頭に来るケースを許容する」）
# ------------------------------------------------------------
_SENTENCE_END = '。．.！？!?」』）)】'
_SMALL_KANA_HEAD = frozenset('ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ')
_CLAUSE_CUT = '。．、，,！？!?\t 　「『（(【'


def _continuation_prefix(previous_line, line):
    """前の行の最後の句（読点・句点・タブ・空白の後ろから行末まで）か ''。前の行が文の終わりの字で終わらず、この行の頭が
    助詞・助動詞（文の頭に立たない語）のときだけ。"""
    if not previous_line or not line:
        return ''
    prev = previous_line.rstrip('\r\n')
    if not prev or prev[-1] in _SENTENCE_END or prev[-1] in _CLAUSE_CUT:
        return ''
    try:
        from morphology import tokenize
        head = next(iter(tokenize(line)), None)
    except Exception:
        return ''
    if head is None or head.start != 0 or head.pos not in ('助詞', '助動詞'):
        return ''
    # 頭の語のすぐ後ろが小書きのかな（に｜ゅ力ミス: にゅ の に を助詞と切った形）なら、頭は付属語ではなく語の切れ端
    # （2026-11-08 手分けA: 前の行とつないだ形で 入力ミス の直しが消え、紫になっていた）。CN_JOIN_SMALL_KANA=0 で前のまま
    if __import__('os').environ.get('CN_JOIN_SMALL_KANA') != '0' and line[head.end:head.end + 1] in _SMALL_KANA_HEAD:
        return ''
    # 頭は平仮名の付属語（片仮名1字を助動詞と見た形は付属語ではない）。行が付属語・感動詞だけ（短いかなの間投詞の行:
    # 解析が頭を助詞と見るだけ）なら前の行に続く文ではない。後ろに内容の語（名詞・動詞・形容詞・副詞）が在ること
    if not all('\u3041' <= ch <= '\u309f' for ch in head.surface):
        return ''
    try:
        rest = [t for t in tokenize(line) if t.start >= head.end]
    except Exception:
        return ''
    if not any(t.pos in ('名詞', '動詞', '形容詞', '副詞', '連体詞') for t in rest):
        return ''
    cut = max(prev.rfind(c) for c in _CLAUSE_CUT)
    tail = prev[cut + 1:]
    if not tail or not any('\u3041' <= ch <= '\u30ff' or '\u4e00' <= ch <= '\u9fff' for ch in tail):
        return ''
    return tail


def _head_end(line):
    try:
        from morphology import tokenize
        head = next(iter(tokenize(line)), None)
    except Exception:
        return 0
    return head.end if head is not None and head.start == 0 else 0


def _changed_ranges(result, line):
    corrected = result.get('corrected') or line
    return [(i1, i2) for tag, i1, i2, _j1, _j2 in
            difflib.SequenceMatcher(None, line, corrected, autojunk=False).get_opcodes() if tag != 'equal']


def _touches_head(result, line, head_end):
    """答えの直し（元の行の位置）か紫が、行頭の語 [0, head_end) に掛かるか。"""
    if not isinstance(result, dict):
        return False
    if any(a < head_end and (b > 0 or a == 0) for a, b in _changed_ranges(result, line)):
        return True
    return any(isinstance(sp, (list, tuple)) and len(sp) >= 2 and sp[0] < head_end
               for k in ('odd_spans', 'unsure_spans') for sp in (result.get(k) or ()))


def _head_merged_fix(result, line, head_end):
    """この行だけの答えが、行頭の付属語と読んだ字を後ろの字ごと1つの直しにした（か｜ーそね → カーソル・が｜いとうあの →
    該当の）なら、行頭は付属語ではなく語の頭。前の行につないで見直さない（2026-11-08 挙動関連担当: 上の行が文の終わりの
    記号で終わらないと、つないだ形が この直しを消していた）。行頭に紫が残る・行頭の字だけの直しは今までどおり見直す。
    CN_JOIN_HEAD_MERGED=0 で前のまま"""
    import os
    if os.environ.get('CN_JOIN_HEAD_MERGED') == '0' or not isinstance(result, dict):
        return False
    if any(isinstance(sp, (list, tuple)) and len(sp) >= 2 and sp[0] < head_end
           for k in ('odd_spans', 'unsure_spans') for sp in (result.get(k) or ())):
        return False
    head = [(a, b) for a, b in _changed_ranges(result, line) if a < head_end and (b > 0 or a == 0)]
    if not head:
        return False
    if all(b > head_end for a, b in head):
        return True
    # 字ごとの差では行頭の字だけの直しに見えても（か→カ・そね→ソル）、直した行の頭の語が行頭の語より長く、
    # 内容の語（名詞・動詞・形容詞）なら、行頭の字を語の頭に組み込んだ直し
    try:
        from morphology import tokenize
        t0 = next(iter(tokenize(result.get('corrected') or line)), None)
    except Exception:
        return False
    return (t0 is not None and t0.start == 0 and t0.end > head_end and t0.pos in ('名詞', '動詞', '形容詞')
            and t0.surface != line[:t0.end])


def _clear_head(result, joined, line, head_end):
    """行頭に掛かる直し・紫を、つないだ形の答え（行頭に何も掛からない）に合わせる。直しが行頭に掛かっていれば、
    つないだ形の答えを使う（行頭の直しを戻した本文は作れない）。紫だけなら、行頭に掛かる紫だけを外す。"""
    if any(a < head_end and (b > 0 or a == 0) for a, b in _changed_ranges(result, line)):
        return joined
    out = dict(result)
    for k in ('odd_spans', 'unsure_spans'):
        if k in out:
            kept = []
            for sp in out.get(k) or ():
                if isinstance(sp, (list, tuple)) and len(sp) >= 2 and sp[0] < head_end:
                    if sp[1] <= head_end:
                        continue          # 行頭の語だけの紫は外す
                    # 行頭から後ろへ続く紫は、つないだ形でもその後ろに紫が在る時だけ、行頭の語を除いた所から残す
                    if not any(isinstance(q, (list, tuple)) and len(q) >= 2 and q[0] < sp[1] and head_end < q[1]
                               for kk in ('odd_spans', 'unsure_spans') for q in (joined.get(kk) or ())):
                        continue
                    sp = type(sp)((head_end,) + tuple(sp[1:])) if isinstance(sp, tuple) else [head_end] + list(sp[1:])
                kept.append(sp)
            out[k] = kept
    if 'odd_reasons' in out:
        out['odd_reasons'] = [r for r in (out.get('odd_reasons') or ())
                              if not (isinstance(r, (list, tuple)) and len(r) >= 2 and r[0] < head_end)]
    return out


def _shift_items(items, d):
    """確定の記録（Occurrence・Calculation・打鍵の組）の位置を d だけずらす。"""
    from dataclasses import is_dataclass, replace
    out = []
    for x in items or ():
        try:
            if is_dataclass(x):
                out.append(replace(x, start=x.start + d, end=x.end + d))
            else:
                out.append((x[0] + d, x[1] + d) + tuple(x[2:]))
        except Exception:
            continue
    return tuple(out)


def _shift_rows(rows, d, lo=0):
    """[(start, end, ...)] か [{start, end}] を d ずらし、lo より前に掛かるものは落とす。"""
    out = []
    for r in rows or ():
        if isinstance(r, dict):
            if not (isinstance(r.get('start'), int) and isinstance(r.get('end'), int)):
                continue
            if r['start'] + d < lo:
                continue
            r = dict(r, start=r['start'] + d, end=r['end'] + d)
            out.append(r)
        elif isinstance(r, (list, tuple)) and len(r) >= 2 and isinstance(r[0], int) and isinstance(r[1], int):
            if r[0] + d < lo:
                continue
            moved = (r[0] + d, r[1] + d) + tuple(r[2:])
            out.append(list(moved) if isinstance(r, list) else moved)
    return out


def _strip_prefix(result, prefix, line):
    """prefix＋line の答えから line の分だけを取り出す。前の行の所に直しや紫が掛かって境目が分からなければ None（この行
    だけで判定し直す）。"""
    if not isinstance(result, dict):
        return None
    p = len(prefix)
    full = prefix + line
    corrected = result.get('corrected') or full
    # 境目（元の行の位置 p）が直した行のどこか。境目をまたぐ直しがあれば分からない
    cpos = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, full, corrected, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= p <= i2:
            cpos = j1 + (p - i1)
            break
        if i1 < p < i2 or (tag != 'equal' and i1 == p == i2):
            return None
    if cpos is None:
        return None
    out = {}
    for k, v in result.items():
        if k == 'diagnosis':
            continue
        if k in ('spans',):
            out[k] = _shift_rows(v, -cpos)
        elif (k.endswith('_spans') or k in ('odd_reasons', 'search_reports')) and isinstance(v, (list, tuple)):
            out[k] = _shift_rows(v, -p)
        else:
            out[k] = v
    text = corrected[cpos:]
    out['original'] = line
    out['corrected'] = text
    out['changed'] = text != line
    # 前の行の所の直し（details）は落とす: この行の元と直しの中に在る組だけ残す
    out['details'] = [d for d in (result.get('details') or ()) if len(d) >= 2 and d[0] in line and d[1] in text]
    cc = result.get('contextual_choices')
    if isinstance(cc, dict):
        out['contextual_choices'] = dict(cc, source=line, candidates=_shift_rows(cc.get('candidates'), -p))
    return out



# 打鍵中の行（軽い答え・defer_heavy）の、行そのものの最初の plain の答えを1つだけ控え、手が止まってからの解き直し
# （defer_heavy=False）の最初の plain に使う（挙動関連担当の測り 2026-11-06: 解き直しの 15〜25% がこの plain）。
# 控えるのは、その plain の間に後回しの印（DEFER_TWO・DEFER_PAIRS）が1つも積まれなかった時だけ（解き直しと同じ道を
# 通った）。引いた語彙・記憶のキー（used_keys）も控えて足すので、答えも used_keys も変わらない。CN_LIGHT_PLAIN_REUSE=0
LIGHT_PLAIN_TTL = 90.0
_LIGHT_PLAIN = [None]


def _light_plain_sig(text, store, context_vocab, decisions, input_method, context_vec, dict_index,
                     nearby_words, recent_words, readings, calculations):
    import os
    if os.environ.get('CN_LIGHT_PLAIN_REUSE') == '0':
        return None
    try:
        import used_keys as _uk
        qtok = _uk._IN_QUERY.set(True)     # 控えの鍵を作るための引きは、行の used_keys に記録しない
    except Exception:
        qtok = None
    try:
        return _light_plain_sig_now(text, store, context_vocab, decisions, input_method, context_vec, dict_index,
                                    nearby_words, recent_words, readings, calculations)
    finally:
        if qtok is not None:
            _uk._IN_QUERY.reset(qtok)


def _light_plain_sig_now(text, store, context_vocab, decisions, input_method, context_vec, dict_index,
                         nearby_words, recent_words, readings, calculations):
    import os
    try:
        from tab_context import _TAB_HAS_KANA
        rev = lambda o: (o.revision() if callable(getattr(o, 'revision', None)) else None) if o is not None else None
        return (text, input_method, repr(readings), repr(calculations), repr(_raw_words(nearby_words)),
                repr(_raw_words(recent_words)),
                id(store), rev(store), id(decisions), rev(decisions), _context_key(context_vocab),
                id(dict_index), id(context_vec), _TAB_HAS_KANA.get(),
                tuple(sorted((k, v) for k, v in os.environ.items() if k.startswith('CN_'))))
    except Exception:
        return None


def _raw_words(x):
    if isinstance(x, tuple):
        return tuple(tuple.__iter__(x))
    return tuple(x or ())


def _context_key(cv):
    """context_vocab の中身の鍵。頼みごとに作り直される Reads（analysis_context）は id が毎回違うので中身で比べる。
    Reads の読みの記録（keys_read・whole・truth）を付けないよう、_values をじかに見る（len も呼ばない）。"""
    if cv is None:
        return None
    vals = getattr(cv, '_values', None)
    if vals is None:
        vals = cv if isinstance(cv, dict) else None
    if vals is None:
        return ('id', id(cv))
    try:
        return repr(sorted(vals.items(), key=lambda kv: repr(kv[0])))
    except Exception:
        return ('id', id(cv))


def _context_marks(cv):
    if cv is None or not hasattr(cv, 'keys_read'):
        return None
    return (set(cv.keys_read), getattr(cv, 'truth', None), getattr(cv, 'whole', False))


def _light_plain_watch(cv=None):
    """軽い答えの plain の前の様子（後回しの印の数・used_keys の記録）。後回しでない時は None。"""
    try:
        import odd_respell as _odd
        two = _odd.DEFER_TWO.get()
        if two is None:
            return None
        try:
            import contextual_repair as _cr
            pairs = _cr.DEFER_PAIRS.get()
        except Exception:
            pairs = None
        import used_keys as _uk
        rec = _uk._ACTIVE.get()
        snap = None if rec is None else (set(rec.vocab), set(rec.choice), rec.recent, rec.whole, rec.loan,
                                         dict(rec.queries), getattr(rec, 'nearby', False),
                                         getattr(rec, 'nearby_truth', None), set(getattr(rec, 'nearby_probes', ())),
                                         set(getattr(rec, 'nearby_one_key', ())))
        return (two, len(two), pairs, len(pairs) if pairs is not None else 0, rec, snap, cv, _context_marks(cv))
    except Exception:
        return None


def _light_plain_keep(sig, watch, got):
    import time, copy
    two, n2, pairs, np_, rec, snap, cv, cm0 = watch
    if len(two) != n2 or (pairs is not None and len(pairs) != np_):
        _LIGHT_PLAIN[0] = None
        return
    diff = None
    if rec is not None and snap is not None:
        v0, c0, r0, w0, l0, q0, n0, nt0, np0, nk0 = snap
        diff = (rec.vocab - v0, rec.choice - c0, rec.recent and not r0, rec.whole and not w0, rec.loan and not l0,
                {k: v for k, v in rec.queries.items() if k not in q0 or q0[k] != v},
                getattr(rec, 'nearby', False) and not n0,
                getattr(rec, 'nearby_truth', None) if nt0 is None else None,
                set(getattr(rec, 'nearby_probes', ())) - np0, set(getattr(rec, 'nearby_one_key', ())) - nk0)
    elif rec is not None:
        return
    cdiff = None
    if cm0 is not None:
        k0, t0, w0 = cm0
        cdiff = (set(cv.keys_read) - k0, cv.truth if cv.truth != t0 else None, bool(cv.whole and not w0))
    _LIGHT_PLAIN[0] = (sig, time.monotonic(), copy.deepcopy(got), diff, cdiff)


def _light_plain_take(sig, cv=None):
    import time, copy
    e = _LIGHT_PLAIN[0]
    if e is None or e[0] != sig or time.monotonic() - e[1] > LIGHT_PLAIN_TTL:
        return None
    _LIGHT_PLAIN[0] = None
    try:
        import used_keys as _uk
        rec = _uk._ACTIVE.get()
        d = e[3]
        if (rec is not None and d is None) or (hasattr(cv, 'keys_read') and e[4] is None):
            return None
        if rec is not None:
            rec.vocab |= d[0]
            rec.choice |= d[1]
            rec.recent = rec.recent or d[2]
            rec.whole = rec.whole or d[3]
            rec.loan = rec.loan or d[4]
            rec.queries.update(d[5])
            if d[6]:
                rec.nearby = True
            if d[7] is not None and getattr(rec, 'nearby_truth', None) is None:
                rec.nearby_truth = d[7]
            if hasattr(rec, 'nearby_probes'):
                rec.nearby_probes |= d[8]
                rec.nearby_one_key |= d[9]
        if hasattr(cv, 'keys_read'):
            c = e[4]
            cv.keys_read |= c[0]
            if c[1] is not None:
                cv.truth = c[1]
            if c[2]:
                cv.whole = True
    except Exception:
        return None
    return copy.deepcopy(e[2])


def _correct_line_strokes(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes):
    memo = {}

    def plain(text, readings=occurrence_readings, calculations=occurrence_calculations):
        # 同じ行の段の中で、同じ形の行の補正し直しは1度だけ（紫の所の読み直しが同じ候補を2度通していた・
        # 2026-11-05 挙動関連担当の測り: 1回1.2〜1.8秒を候補ごとに）。答えは変えない（写しを返す）。
        # 打鍵中の行（後回しの印を付ける）は今までどおり毎回。CN_PLAIN_MEMO=0 で前のまま
        key = None
        if __import__('os').environ.get('CN_PLAIN_MEMO') != '0':
            try:
                import odd_respell as _odd
                typing = _odd.DEFER_TWO.get() is not None
            except Exception:
                typing = True
            if not typing:
                if readings is occurrence_readings and calculations is occurrence_calculations:
                    key = (text, 0)
                elif not readings and not calculations:
                    key = (text, 1)
        if key is not None and key in memo:
            return __import__('copy').deepcopy(memo[key])
        first = text == line and readings is occurrence_readings and calculations is occurrence_calculations
        sig = _light_plain_sig(text, store, context_vocab, decisions, input_method, context_vec, dict_index,
                               nearby_words, recent_words, readings, calculations) if first else None
        if sig is not None and key is not None:
            hit = _light_plain_take(sig, context_vocab)
            if hit is not None:
                memo[key] = __import__('copy').deepcopy(hit)
                return hit
        watch = _light_plain_watch(context_vocab) if (sig is not None and key is None) else None
        got = _correct_line_halfwidth(text, store, context_vocab=context_vocab, decisions=decisions,
                                      input_method=input_method, context_vec=context_vec, dict_index=dict_index,
                                      nearby_words=nearby_words, recent_words=recent_words,
                                      occurrence_readings=readings, occurrence_calculations=calculations)
        if watch is not None and isinstance(got, dict):
            _light_plain_keep(sig, watch, got)
        if key is not None and isinstance(got, dict):
            memo[key] = __import__('copy').deepcopy(got)
        return got
    typed_line = line

    def stages(line, plain):
        # ime_reconvert が打った記録の読みを使えるように、元の行と記録を渡す（段は current_input の外で動くため）
        try:
            import ime_reconvert as _R
            typed_token = _R.TYPED.set((typed_line, occurrence_readings))
        except Exception:
            _R, typed_token = None, None
        # 手分けB の文書の語（タブ全体の語）で絞る道は既定で切る: うにが上下行の参照を切ったため（2026-11-08 13:11Z）。
        # CN_KEYSLIP_DOC_CONTEXT=1 のときだけ前の振る舞い。
        _K, doc_token = None, None
        if __import__('os').environ.get('CN_KEYSLIP_DOC_CONTEXT') == '1':
            try:
                import keyslip_window as _K
                doc_token = _K.DOC_CONTEXT.set(context_vocab)
            except Exception:
                _K, doc_token = None, None
        try:
            return _line_stages(line, plain, store, dict_index, decisions, context_vec, input_method, nearby_words)
        finally:
            if typed_token is not None:
                _R.TYPED.reset(typed_token)
            if doc_token is not None:
                _K.DOC_CONTEXT.reset(doc_token)
    result = stages(line, plain)
    if not occurrence_strokes:
        return result
    try:
        decided = corrector._decided_spans(line, decisions)
        strokes = [o for o in occurrence_strokes
                   if not any(a < o[1] and o[0] < b for a, b in decided)]
        if not strokes:
            return result
        run = lambda text: plain(text, (), ())
        try:
            from ime_language import JapaneseIME
            with JapaneseIME() as ime:
                # 抜いた読みは本物の IME の1つ目の変換で行に戻す（IME が無ければ読みのまま）
                convert = ime.convert if ime.available else None
                out = _stroke_repairs(line, result, strokes, input_method, run, convert)
        except (ImportError, OSError, AttributeError):
            out = _stroke_repairs(line, result, strokes, input_method, run, None)
    except Exception:
        return result
    done = _after_stroke_repair(line, result, out, lambda text: stages(text, run))
    # 打鍵の直しの後の段は直した行を元に見るので、元の行との間で文の形を見直す（散歩はコット→散歩ハット の
    # 助詞の取り込み）。CN_STROKE_GRAMMAR=0 で前のまま
    if (__import__('os').environ.get('CN_STROKE_GRAMMAR') != '0' and isinstance(done, dict) and isinstance(result, dict)
            and done.get('corrected') != result.get('corrected')):
        try:
            done = _fix_breaks_grammar(line, done)
        except Exception:
            pass
    return done


import contextvars as _stage_cv
_STAGE_START = _stage_cv.ContextVar('correction_entry_stage_start')
TYPING_STAGE_BUDGET = 2.0   # 打鍵中の行で、ここまでにこの秒を使っていたら重い2段を後回しにする


def _line_stages(line, plain, store, dict_index, decisions, context_vec, input_method, nearby_words):
    import time as _time
    _st = _STAGE_START.set(_time.monotonic())
    try:
        return _line_stages_now(line, plain, store, dict_index, decisions, context_vec, input_method, nearby_words)
    finally:
        _STAGE_START.reset(_st)


LONG_LINE_RERUN_SEC = 30.0   # 行の1回目の補正にこの秒を超えた行は、行全体を補正し直す段（接尾・述語・紫の読み直し）を回さない


def _noun_ta_guard(line, result, decisions):
    """直しが漢字の用言（背借り）を片仮名の名詞（カリ）にして、すぐ後ろが過去・完了の た（カリた）になった所は、名詞＋た
    で文の形が成り立たない。その直しを戻して元の所を紫にする（2026-11-08 初期状態の語彙で 背借りた → カリた）。
    CN_NOUN_TA_GUARD=0 で見ない。"""
    import os
    import difflib
    if os.environ.get('CN_NOUN_TA_GUARD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        from morphology import tokenize
        toks = list(tokenize(done))
        ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
        decided = corrector._decided_spans(line, decisions)
    except Exception:
        return result
    bad = []
    for tag, i1, i2, j1, j2 in ops:
        if tag != 'replace' or not any('一' <= c <= '鿿' for c in line[i1:i2]):
            continue
        rep = done[j1:j2]
        if not rep or not all('ァ' <= c <= 'ヶ' or c == 'ー' for c in rep):
            continue
        for k, t in enumerate(toks[:-1]):
            if t.start == j1 and t.end == j2 and t.pos == '名詞' and toks[k + 1].pos == '助動詞' \
                    and toks[k + 1].surface == 'た' and toks[k + 1].start == j2:
                if not any(x < i2 and i1 < y for x, y in decided):
                    bad.append((i1, i2, j1, j2))
                break
    if not bad:
        return result
    new = done
    for i1, i2, j1, j2 in sorted(bad, key=lambda x: -x[2]):
        new = new[:j1] + line[i1:i2] + new[j2:]
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    gone = {done[j1:j2] for _i1, _i2, j1, j2 in bad}
    out = dict(result)
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or () if x[1] <= len(new)]
    # 戻した所（new の上の位置）
    for i1, i2, j1, j2 in bad:
        shift = sum((b2 - b1) - (d2 - d1) for b1, b2, d1, d2 in bad if d2 <= j1)
        odd.append((j1 + shift, j1 + shift + (i2 - i1)))
    out.update({'corrected': new, 'changed': new != line,
                'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and d[1] in gone)],
                'odd_spans': sorted(set(odd)),
                'spans': [[o[3], o[4]] for o in ops2], 'original_spans': [[o[1], o[2]] for o in ops2]})
    return out


def _slow_first_pass():
    import os, time as _time
    if os.environ.get('CN_LONG_LINE_RERUN') == '1':
        return False
    return _time.monotonic() - _STAGE_START.get(_time.monotonic()) > LONG_LINE_RERUN_SEC


def _noun_suffix_mark(line, result, store, dict_index, decisions):
    """補正し直しを回さない長い行では、接尾の字を置ける所を紫にする（直しは決めない）。"""
    try:
        import noun_suffix
        decided = corrector._decided_spans(line, decisions)
        places = [p for p in noun_suffix._places(line, store, dict_index)
                  if not any(a < p[1] and p[0] < b for a, b in decided)]
    except Exception:
        return result
    if not places or not isinstance(result, dict) or (result.get('corrected') or line) != line:
        return result
    odd = [tuple(o[:2]) for o in (result.get('odd_spans') or ())]
    reasons = [tuple(r[:3]) for r in (result.get('odd_reasons') or ())]
    for s, e, f in places:
        if not any(x < e and s < y for x, y in odd):
            odd.append((s, e))
            reasons.append((s, e, f'「{line[s:e]}」は「{f}」の書き間違いかもしれません'))
    out = dict(result)
    out['odd_spans'] = sorted(odd)
    out['odd_reasons'] = reasons
    return out


FAR_COMMON = 450   # 消えた語の身近さ（wordfreq の段がこれ以下）
FAR_KNOWN = 600    # 元の所の名詞が語として知られている（wordfreq の段がこれ以下・名詞の外は FAR_COMMON）


def _bracket_particle_ok(line, result):
    """閉じ括弧のすぐ後ろの助詞1つ（「文字の色」に・『題』を）だけに付いた紫を外す。括弧の中を1つの名詞として受ける
    ふつうの形で、かなの並びの説明が付かないのは解析が括弧で切るため（2026-11-08 未解決タブの誤判定: 」にします →
    に市内）。CN_BRACKET_PARTICLE=0 で前のまま。"""
    import os
    if os.environ.get('CN_BRACKET_PARTICLE') == '0' or not isinstance(result, dict):
        return result
    odd = result.get('odd_spans') or []
    if not odd:
        return result
    text = result.get('corrected') or line
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return result
    keep = []
    dropped = []
    for o in odd:
        a, b = o[0], o[1]
        t = next((t for t in toks if t.start == a and t.end == b), None)
        if (t is not None and t.pos == '助詞' and a > 0 and text[a - 1] in '」』）)】'
                and (t.pos_sub or '').startswith(('格助詞', '係助詞', '副助詞'))):
            dropped.append((a, b))
            continue
        keep.append(o)
    if not dropped:
        return result
    out = dict(result)
    out['odd_spans'] = keep
    if out.get('odd_reasons'):
        out['odd_reasons'] = [r for r in out['odd_reasons'] if (r[0], r[1]) not in dropped]
    return out


def _suffix_noun_verb_ok(line, result):
    """語の尾の1字（空き｜箱・洗濯｜物・掃除｜機: 接尾）と、すぐ後ろの動詞の組だけに付いた紫を外す。前の語とつないだ
    名詞（空き箱）が1語として在るなら、名詞＋動詞で助詞を抜いた話し言葉（空き箱あったよ・掃除機かけなきゃ）で、
    打ち違いの印にならない（2026-11-08 補正担当の正しい文の試し）。1字の名詞そのもの（背｜借りた）は前のまま。
    CN_SUFFIX_NOUN_VERB=0 で前のまま。"""
    import os
    if os.environ.get('CN_SUFFIX_NOUN_VERB') == '0' or not isinstance(result, dict):
        return result
    odd = result.get('odd_spans') or []
    if not odd:
        return result
    text = result.get('corrected') or line
    try:
        from morphology import tokenize
        import seed_japanese as S
        toks = list(tokenize(text))
    except Exception:
        return result
    keep, dropped = [], []
    for o in odd:
        a, b = o[0], o[1]
        k = next((i for i, t in enumerate(toks) if t.start == a), None)
        ok = False
        if k is not None and 0 < k and k + 1 < len(toks):
            p, t, v = toks[k - 1], toks[k], toks[k + 1]
            if ((t.pos_sub or '').startswith('接尾') and t.pos == '名詞' and p.end == t.start and t.end == v.start
                    and v.pos == '動詞' and v.end >= b and v.start < b and p.pos == '名詞'):
                try:
                    ok = S.is_unit(p.surface + t.surface) is True
                except Exception:
                    ok = False
        if ok:
            dropped.append((a, b))
        else:
            keep.append(o)
    if not dropped:
        return result
    out = dict(result)
    out['odd_spans'] = keep
    if out.get('odd_reasons'):
        out['odd_reasons'] = [r for r in out['odd_reasons'] if (r[0], r[1]) not in dropped]
    return out


def _kango_suru_ok(line, result):
    """2字以上の漢語の名詞（爆睡・熟読）と、すぐ後ろの する の組に「続けて置けない」として付いた紫を外す。漢語＋する は
    辞書がサ変と書いていなくても作れる形で、打ち違いの印にならない（2026-11-08 補正担当の正しい文の試し: 爆睡してる）。
    名詞は語として知られた語（wordfreq の段 FAR_KNOWN 以下）で、字がどれも音読みのものだけ。CN_KANGO_SURU=0 で前のまま。"""
    import os
    if os.environ.get('CN_KANGO_SURU') == '0' or not isinstance(result, dict):
        return result
    odd = result.get('odd_spans') or []
    reasons = result.get('odd_reasons') or []
    if not odd:
        return result
    text = result.get('corrected') or line
    try:
        from morphology import tokenize
        import kana_keep
        import ime_reconvert as R
        toks = list(tokenize(text))
    except Exception:
        return result
    hira = lambda s: ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')
    keep, dropped = [], []
    for o in odd:
        a, b = o[0], o[1]
        why = [r[2] for r in reasons if len(r) >= 3 and r[0] < b and a < r[1]]
        k = next((i for i, t in enumerate(toks) if t.start == a), None)
        ok = False
        if k is not None and k + 1 < len(toks) and all('続けて置けない' in w for w in why):
            n, v = toks[k], toks[k + 1]
            if (n.pos == '名詞' and len(n.surface) >= 2 and all('一' <= c <= '鿿' for c in n.surface)
                    and n.end == v.start and v.pos == '動詞' and (getattr(v, 'base_form', '') == 'する')
                    and v.end >= b and R._rank(n.surface) <= FAR_KNOWN):
                try:
                    if n.has_reading and n.reading and hira(n.reading) != n.surface:
                        ok = kana_keep.is_kango(n.surface, hira(n.reading))
                    else:
                        # 辞書に読みの無い語（爆睡）は、字がどれも音読みを持つかで見る
                        import kanji_onkun
                        ok = all(any(kanji_onkun.on_or_kun(c, r) == 'on' for r in kanji_onkun.readings_of(c))
                                 for c in n.surface)
                except Exception:
                    ok = False
        if ok:
            dropped.append((a, b))
        else:
            keep.append(o)
    if not dropped:
        return result
    out = dict(result)
    out['odd_spans'] = keep
    out['odd_reasons'] = [r for r in reasons if (r[0], r[1]) not in dropped]
    return out


def _kana_noun_verb_ok(line, result):
    """かなで書いた名詞（ひげ・けが）のすぐ後ろに漢字の動詞が来た形（助詞の省き: ひげ剃った）で、辞書がかなの語を切り損ねて
    「続けて置けない」として付いた紫を外す。かなの並びは左が漢字・片仮名・記号か行頭で切れていて、その読みで IME が
    名詞の字（ヒゲ・怪我）を上位4つに返し、その字が語として知られている（FAR_KNOWN 以下）ときだけ（2026-11-08
    補正担当の正しい文の試し）。CN_KANA_NOUN_VERB=0 で前のまま。"""
    import os
    if os.environ.get('CN_KANA_NOUN_VERB') == '0' or not isinstance(result, dict):
        return result
    odd = result.get('odd_spans') or []
    reasons = result.get('odd_reasons') or []
    if not odd:
        return result
    text = result.get('corrected') or line
    try:
        from morphology import tokenize
        import ime_reconvert as R
        toks = list(tokenize(text))
    except Exception:
        return result
    isk = lambda c: '一' <= c <= '鿿' or c == '々'
    ish = lambda c: 'ぁ' <= c <= 'ゖ'

    def _noun_face(run):
        try:
            for f in R._dict_faces(run, 10)[:4]:
                ft = list(tokenize(f))
                if len(ft) == 1 and ft[0].pos == '名詞' and R._rank(f) <= FAR_KNOWN:
                    return True
        except Exception:
            return False
        return False

    keep, dropped = [], []
    for o in odd:
        a, b = o[0], o[1]
        why = [r[2] for r in reasons if len(r) >= 3 and r[0] < b and a < r[1]]
        ok = False
        if why and all('続けて置けない' in w for w in why):
            v = next((t for t in toks if t.start < b and a < t.end and t.pos == '動詞'
                      and any(isk(c) for c in t.surface) and t.end >= b), None)
            if v is not None:
                e = v.start
                s0 = e
                while s0 > 0 and ish(text[s0 - 1]):
                    s0 -= 1
                run = text[s0:e]
                if len(run) >= 2 and s0 <= a and _noun_face(run):
                    ok = True
        if ok:
            dropped.append((a, b))
        else:
            keep.append(o)
    if not dropped:
        return result
    out = dict(result)
    out['odd_spans'] = keep
    out['odd_reasons'] = [r for r in reasons if (r[0], r[1]) not in dropped]
    return out


def _closed_kana_run_ok(line, result):
    """「品詞として識別できない」だけの紫で、行の解析がその所を閉じた種類の語（助詞・助動詞・形式名詞・代名詞・連体詞・
    2字以上の副詞・する／ある／いる／なる／くる の形）と、所の前から続く漢字の語（知ったかぶり・行か）だけに切るものは
    外す（ことじゃなくて・すんなよ: 話し言葉の正しい形。2026-11-08 補正担当の正しい文の試し）。開いた種類の語（名詞・
    ほかの動詞・形容詞）が1つでも掛かれば紫のまま。CN_CLOSED_KANA_RUN=0 で前のまま。"""
    import os
    if os.environ.get('CN_CLOSED_KANA_RUN') == '0' or not isinstance(result, dict):
        return result
    odd = result.get('odd_spans') or []
    reasons = result.get('odd_reasons') or []
    if not odd:
        return result
    text = result.get('corrected') or line
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return result
    isk = lambda c: '一' <= c <= '鿿' or c == '々'
    light = ('する', 'ある', 'いる', 'なる', 'くる', 'おる', 'やる')

    def closed(t, a):
        sub = t.pos_sub or ''
        if not getattr(t, 'has_reading', True):
            return False
        if t.start < a and any(isk(c) for c in t.surface):
            return True
        if t.pos in ('助詞', '助動詞', '連体詞'):
            return True
        if t.pos == '名詞' and (sub.startswith('非自立') or sub.startswith('代名詞')):
            return True
        if t.pos == '副詞' and len(t.surface) >= 2:
            return True
        return t.pos == '動詞' and (t.base_form or '') in light

    keep, dropped = [], []
    for o in odd:
        a, b = o[0], o[1]
        why = [r[2] for r in reasons if len(r) >= 3 and r[0] < b and a < r[1]]
        over = [t for t in toks if t.start < b and a < t.end]
        if (why and all('品詞として識別できない' in w for w in why) and over
                and all(closed(t, a) for t in over) and any(t.start >= a for t in over)):
            dropped.append((a, b))
        else:
            keep.append(o)
    if not dropped:
        return result
    out = dict(result)
    out['odd_spans'] = keep
    out['odd_reasons'] = [r for r in reasons if (r[0], r[1]) not in dropped]
    return out


def _key_edit_count(a, b):
    """かな入力の打鍵の数え方での違い: 濁点・半濁点は別のキー、隣どうしの入れ替えは1つ（がそく と かぞく は ゛ の
    入れ替えで1つ）。"""
    import unicodedata
    def keys(s):
        return unicodedata.normalize('NFD', s)
    a, b = keys(a), keys(b)
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _unknown_word_guard(line, result, decisions, input_method='kana'):
    """1回目の補正が、元の行の語として知られた2字以上の漢字の名詞（火事）を、語として知られていない漢字の並び
    （化時: 辞書の1語でもなく使われやすさの表にも無い）に替えていたら戻す。打ち違いの直しは知られた語へ向かうもので、
    知られた語を知られていない並びに替える根拠は無い（2026-11-09 補正担当の正しい文の試し: 昨日火事が起こった →
    化時）。行の直しの全部がこの形のときだけ戻し、紫は付けない（元の行は知られた語の正しい形）。CN_UNKNOWN_WORD_GUARD=0
    で見ない。"""
    import os
    if os.environ.get('CN_UNKNOWN_WORD_GUARD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        from morphology import tokenize
        import ime_reconvert as R
        lt = list(tokenize(line))
        dt = list(tokenize(done))
        ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
        decided = corrector._decided_spans(line, decisions)
    except Exception:
        return result
    kan = lambda w: bool(w) and all('一' <= c <= '鿿' or c == '々' for c in w)
    purple = []
    ops_new = [(o[3], o[4]) for o in ops]
    for _tag, i1, i2, j1, j2 in ops:
        old = [t for t in lt if t.start < max(i2, i1 + 1) and i1 < t.end]
        new = [t for t in dt if t.start < max(j2, j1 + 1) and j1 < t.end]
        if not old or not new or any(x < old[-1].end and old[0].start < y for x, y in decided):
            return result
        lost = [t for t in old if t.pos == '名詞' and len(t.surface) >= 2 and kan(t.surface) and t.has_reading
                and R._rank(t.surface) <= FAR_KNOWN]
        nf = done[new[0].start:new[-1].end]
        if not lost or not kan(nf) or R._rank(nf) < 800 or (len(new) == 1 and new[0].has_reading):
            return result
        merged = _split_merge_check(line, done, old, new, nf, input_method)
        if merged == 'keep':
            return result
        if merged == 'purple':
            purple.append((old[0].start, old[-1].end))
    out = dict(result)
    if purple:
        out['odd_spans'] = sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())
                                      if not any(a < x[1] and x[0] < b for a, b in ops_new)) | set(purple))
        out['odd_reasons'] = [(a, b, '割れた語を1打の戻しで1語にまとめる候補が1つに決まりません') for a, b in purple]
    out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': []})
    return out


SPLIT_MERGE_GAIN = 3000     # まとめた行の並びの費用が元の行よりこれだけ下がること
SPLIT_MERGE_MARGIN = 1000   # 二番の候補とこれだけ離れること


def _split_merge_check(line, done, old, new, nf, input_method):
    """入口が、身近な語3つ以上に割れた所（歳｜で｜以下 の形）を知られていない漢字の並び（身近な語の組）にした直しを、
    1打の戻し（split_merge.candidates: かな入力は ゛ を保って隣のキー、ローマ字は字の1打）で説明できるか。
    'keep'＝その直しが候補の一番で、元の行より SPLIT_MERGE_GAIN、二番より SPLIT_MERGE_MARGIN 費用が下がる（戻さない）・
    'purple'＝候補には在るが決まらない（戻して紫）・None＝この形でない（前のまま戻す）。2026-11-09 手分けA。
    CN_SPLIT_MERGE=0 で前のまま"""
    try:
        import split_merge
        import morphology
        if not split_merge.on() or len(old) < 3:
            return None
        if any(t.pos not in ('名詞', '助詞') for t in old):
            return None
        cands = split_merge.candidates(old, input_method)
        if nf not in cands:
            return None
        a, b = old[0].start, old[-1].end
        here = morphology.path_cost(line)
        scored = sorted((morphology.path_cost(line[:a] + f + line[b:]) or 10 ** 9, f) for f in cands)
        best = scored[0]
        second = scored[1][0] if len(scored) > 1 else here
        if (here is not None and best[1] == nf and best[0] <= here - SPLIT_MERGE_GAIN
                and best[0] <= second - SPLIT_MERGE_MARGIN):
            return 'keep'
        return 'purple'
    except Exception:
        return None


def _kana_noun_from_kanji_guard(line, result, decisions):
    """1回目の補正が、元の行で漢字に変換されていた身近な語の所（言う間）を、ひらがなの名詞（いま）に替えていたら戻す。
    元の所が漢字なのは IME が変換した所で、打ち違いを戻した語も IME はふつう漢字で返す（いま → 今）。漢字の所を
    かなの名詞にする直しは打ち違いの直しとしての形にならない（2026-11-09 補正担当の正しい文の試し: あっと言う間 →
    あっといま）。漢字が助詞・助動詞になる直し（李 → の）は名詞でないので見ない。行の直しの全部がこの形のときだけ戻し、
    紫は付けない（元の所は身近な語の正しい形）。CN_KANA_NOUN_GUARD=0 で見ない。"""
    import os
    if os.environ.get('CN_KANA_NOUN_GUARD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        from morphology import tokenize
        import ime_reconvert as R
        lt = list(tokenize(line))
        dt = list(tokenize(done))
        ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
        decided = corrector._decided_spans(line, decisions)
    except Exception:
        return result
    hira = lambda w: bool(w) and all('ぁ' <= c <= 'ゖ' for c in w)
    for _tag, i1, i2, j1, j2 in ops:
        old = [t for t in lt if t.start < max(i2, i1 + 1) and i1 < t.end]
        new = [t for t in dt if t.start < max(j2, j1 + 1) and j1 < t.end]
        if not old or not new or any(x < old[-1].end and old[0].start < y for x, y in decided):
            return result
        # 元の所: 漢字を含む内容語があり、どれも身近（FAR_COMMON 以下か助詞・助動詞）
        content = [t for t in old if t.pos not in ('助詞', '助動詞', '記号')]
        if not any(any('一' <= c <= '鿿' for c in t.surface) for t in content) or not all(
                R._rank(t.surface) <= FAR_COMMON for t in content):
            return result
        # 直した所: ひらがなだけの名詞（非自立・代名詞・数でない2字以上）が新しく入った
        kana_nouns = [t for t in new if t.pos == '名詞' and hira(t.surface) and len(t.surface) >= 2
                      and not any(k in (t.pos_sub or '') for k in ('非自立', '代名詞', '数'))
                      and t.surface not in line[old[0].start:old[-1].end]]
        if not kana_nouns:
            return result
    out = dict(result)
    out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': []})
    return out


def _far_reading_guard(line, result, decisions):
    """1回目の補正が、元の行の身近な語ばかりの所（部屋変な・変だ）を、読みの大きく違う別の語（変化な・キワダ）に
    替えていたら、打ち違いの直しとしての説明が付かないので戻して紫にする（2026-11-08 補正担当: 正しい文で
    この部屋変な臭い → この変化な臭い）。元の所の語がどれも身近（FAR_COMMON 以下か助詞・助動詞）で、
    身近な内容語が1つ以上、表記も読みも直した後に残らず、読みの違いが2字以上かつ元の読みの半分以上のとき。
    CN_FAR_READING_GUARD=0 で見ない。"""
    import os
    import difflib
    if os.environ.get('CN_FAR_READING_GUARD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        from morphology import tokenize
        import ime_reconvert as R
        from odd_respell import _edit_count
        lt = list(tokenize(line))
        dt = list(tokenize(done))
        ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
        decided = corrector._decided_spans(line, decisions)
    except Exception:
        return result
    hira = lambda s: ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')
    func = ('助詞', '助動詞', '記号')
    # 間の同じ所が1字以下の差はまとめて1つの所として見る（部屋変 → 変化 は 部屋 の消しと 化 の足し）
    regs = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            continue
        if regs and i1 - regs[-1][1] <= 1 and j1 - regs[-1][3] <= 1:
            regs[-1] = (regs[-1][0], i2, regs[-1][2], j2)
        else:
            regs.append((i1, i2, j1, j2))
    back = []
    for i1, i2, j1, j2 in regs:
        new = [t for t in dt if t.start < max(j2, j1 + 1) and j1 < t.end]
        if not new:
            continue
        # 前後の同じ字の所まで、元の行も直した行の語の端に揃えて比べる（下さ｜低 → 下さい は 下さ低 と 下さい）
        lo = i1 - (j1 - min(new[0].start, j1))
        hi = i2 + (max(new[-1].end, j2) - j2)
        old = [t for t in lt if t.start < max(hi, lo + 1) and lo < t.end]
        if not old:
            continue
        a, b = old[0].start, old[-1].end
        # 浮いた ゛゜ の残る所（的゜・り゛手）は打ち違いの直しの所で、この守りの見る形ではない
        if any(c in '゛゜' for c in line[a:b]):
            continue
        if any(x < b and a < y for x, y in decided):
            continue
        # 元の所の語はどれも語として知られた語（wordfreq の段 FAR_KNOWN 以下か助詞・助動詞）。身近さ FAR_COMMON は
        # 消えた語の1つに求める（爆睡 → 破壊: 爆睡 は知られた語）
        if not all(t.pos in func or R._rank(t.surface) <= (FAR_KNOWN if t.pos == '名詞' else FAR_COMMON) for t in old):
            continue
        new_face = ''.join(t.surface for t in new)
        new_rd = hira(''.join(t.reading or t.surface for t in new))
        old_rd = hira(''.join(t.reading or t.surface for t in old))
        lost = [t for t in old if t.pos not in func and any('一' <= c <= '鿿' for c in t.surface)
                and t.surface not in new_face and hira(t.reading or '') not in new_rd]
        # 消えた語に2字以上の語があるときだけ（部屋 のような語が丸ごと消える形）。1字の語（低・手）は打ち違いで
        # IME が出した字のことが多い
        # 1字の語でも、前の語に付く接尾（利き｜方）を片仮名の語（ポア）に替える形は同じに見る
        kata_new = bool(new_face) and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in new_face)
        if not lost or not any((len(t.surface) >= 2 or (kata_new and (t.pos_sub or '').startswith('接尾')))
                               and R._rank(t.surface) <= (FAR_KNOWN if t.pos == '名詞' else FAR_COMMON)
                               for t in lost):
            continue
        # 打った記録の読み（家族 を がぞく と打って 即 になった所）が在れば、その読みとの違いで見る
        rds = {old_rd}
        try:
            import kanji_guess
            face = ''.join(t.surface for t in old)
            rds.update(hira(x) for x in kanji_guess.ime_readings_for(face))
            parts = [[hira(t.reading or t.surface)] + [hira(x) for x in kanji_guess.ime_readings_for(t.surface)]
                     for t in old]
            import itertools
            for combo in itertools.islice(itertools.product(*parts), 16):
                rds.add(''.join(combo))
        except Exception:
            pass
        d = min(_key_edit_count(x, new_rd) for x in rds)
        if d < 2 or 2 * d < len(old_rd):
            continue
        back.append((a, b, j1, j2, new[0].start, new[-1].end))
    if not back or len(back) != len(regs):
        return result
    if os.environ.get('CN_FAR_LOG') == '1':
        import sys
        print('FAR_GUARD', line, '|', done, back, file=sys.stderr)
    # 戻すのは、行の直しの全部がこの形のときだけ（他の直しと並ぶ行は見ない）。紫は元の行の位置に
    out = dict(result)
    out['corrected'] = line
    out['changed'] = False
    out['spans'] = []
    out['original_spans'] = []
    out['details'] = []
    odd = []
    for o in (result.get('odd_spans') or []):
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and j1 <= o[0] and o[1] <= j2:
                odd.append([o[0] - j1 + i1, o[1] - j1 + i1])
                break
    for a, b, *_ in back:
        if [a, b] not in odd:
            odd.append([a, b])
    out['odd_spans'] = odd
    return out


def _keep_clean_source(line, result, store, dict_index, decisions=None):
    """入口（corrector の道）の直しで、元の行には異様な並びが1つも無いのに、直した所に異様な並びが立つなら、
    その直しは正しい文を崩した形（クリックして選べる → クリック下よべる）。その直しを元に戻す
    （2026-11-09 うにの誤判定・手分けB。corrector.py は固定なので外で戻す）。CN_KEEP_CLEAN_SOURCE=0 で前のまま。"""
    import os
    if os.environ.get('CN_KEEP_CLEAN_SOURCE') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        import oddness
        fn = getattr(store, '_tokenize_fn', None) or corrector.make_tokenizer(store)
        if oddness.is_odd_run(line, fn, store=store, dict_index=dict_index):
            return result
        got = oddness.is_odd_run(fixed, fn, with_spans=True, store=store, dict_index=dict_index)
        spans = [(x[2], x[3]) for x in got or () if len(x) >= 4]
        if not spans:
            return result
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        bad = {o for o in ops if o[0] != 'equal' and any(a < max(o[4], o[3] + 1) and o[3] < b for a, b in spans)}
        if not bad:
            return result
        new, jmap = '', {}
        for o in ops:
            tag, i1, i2, j1, j2 = o
            if o in bad:
                new += line[i1:i2]
                continue
            for k in range(j2 - j1):
                jmap[j1 + k] = len(new) + k
            new += fixed[j1:j2]
        jmap[len(fixed)] = len(new)
        near = [(o[3], o[4]) for o in bad]

        def moved(sp):
            a, b = sp[0], sp[1]
            if any(x <= b and a <= y for x, y in near) or a not in jmap or b not in jmap:
                return None
            return (jmap[a], jmap[b]) + tuple(sp[2:])
        ops2 = [x for x in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if x[0] != 'equal']
        out = dict(result)
        out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[x[3], x[4]] for x in ops2],
                    'original_spans': [[x[1], x[2]] for x in ops2],
                    'details': [d for d in (result.get('details') or []) if len(d) > 1 and d[1] and d[1] in new]})
        for key in ('odd_spans', 'unsure_spans', 'odd_reasons'):
            if key in result:
                out[key] = [m for m in (moved(sp) for sp in (result.get(key) or ())) if m]
        return out
    except Exception:
        return result


def _line_stages_now(line, plain, store, dict_index, decisions, context_vec, input_method, nearby_words):
    first = plain(line)
    # 文字のまま扱う行（長い1行のデータ・リンクなど）は、入口で飛ばした答えのまま。後ろの段で解析し直さない
    # （約5,700字の行で noun_suffix が50秒を超えた・挙動関連担当 2026-11-03）
    try:
        from literal_lines import literal_only
        if literal_only(line):
            return first
    except Exception:
        pass
    # 1回目の補正だけで長くかかった行（195字の行で約60秒・行全体の補正し直しを重ねて7分で終わらなかった、
    # 挙動関連担当の測り 2026-11-03）は、補正し直しの段を回さない。直せない所は紫のまま
    slow = _slow_first_pass()
    first = _keep_clean_source(line, first, store, dict_index, decisions)
    if slow:
        result = _noun_suffix_mark(line, first, store, dict_index, decisions)
    else:
        result = _noun_suffix(line, first, plain, store, dict_index, decisions)
    result = _noun_ta_guard(line, result, decisions)
    result = _far_reading_guard(line, result, decisions)
    result = _unknown_word_guard(line, result, decisions, input_method)
    result = _kana_noun_from_kanji_guard(line, result, decisions)
    result = _bracket_particle_ok(line, result)
    result = _suffix_noun_verb_ok(line, result)
    result = _kango_suru_ok(line, result)
    result = _kana_noun_verb_ok(line, result)
    result = _closed_kana_run_ok(line, result)
    result = _learned_gate(line, result, store, decisions, input_method)
    result = _long_loan(line, result, decisions, input_method)
    result = _word_pair_mark(line, _lattice_place(line, result, store, dict_index), store, dict_index, decisions)
    result = _renyou_tail_slip(line, result, decisions, input_method)
    result = _degree_adverb(line, result, dict_index, decisions)
    result = _dangling_verb(line, result, decisions)
    result = _impossible_slip(line, result, decisions, input_method)
    result = _kanji_doubt(line, result, store, dict_index, decisions)
    result = _ime_unlikely_join(line, result, decisions)
    result = _ime_reconvert(line, result, decisions, input_method)
    result = _honorific_stem(line, result, decisions)
    result = _question_ka(line, result, decisions)
    result = _formal_noun_gap(line, result, decisions)
    result = _te_dropped(line, result, decisions)
    result = _pair_choice(line, result, decisions, input_method)
    result = _semantic_fit(line, result, decisions, input_method)
    result = _rival_repair(line, result, decisions, input_method)
    result = _nearby_one_key(line, result, nearby_words, input_method, decisions)
    result = _mark_keeps_next(line, result)
    result = _float_mark_choice(line, result)
    result = _mark_swapped_back(line, result)
    result = _swapped_particle_kanji(line, result, decisions, input_method)
    result = _kanji_swap_guard(line, result)
    result = _pos_seq_odd(line, result, dict_index, decisions)
    result = _keyslip_window(line, result, decisions, input_method)
    result = _dakuten_shift(line, result, decisions, input_method)
    result = _head_tie(line, result, store, dict_index, decisions, input_method)
    # 打鍵中の行（defer_heavy）で、ここまでで時間を使った長い行は、重い2段を手が止まってからに回す（答えは変えない:
    # deferred_stages を付け、呼び手が defer_heavy=False で解き直す・挙動関連担当の測り 2026-11-02）
    deferred = None
    try:
        import odd_respell as _odd
        deferred = _odd.DEFER_TWO.get()
    except Exception:
        pass
    import time as _time
    if slow:
        pass
    elif deferred is not None and _time.monotonic() - _STAGE_START.get(_time.monotonic()) > TYPING_STAGE_BUDGET:
        deferred.extend(['predicate_slip', 'odd_respell'])
    else:
        result = _partial_shift(line, result, plain, store, dict_index, context_vec, decisions, input_method)
        result = _predicate_slip(line, result, plain, store, dict_index, context_vec, decisions, input_method)
        if deferred is not None and result.get('odd_spans') and __import__('os').environ.get('CN_TYPING_RESPELL') != '1':
            # 打鍵中の行の紫の所の読み直し（odd_respell）は、行全体の補正し直しを何度も回すので手が止まってから
            # （挙動関連担当の測り 2026-11-03: 短い行の5字で打鍵中の待ちの約4割）。紫は打鍵中も出たまま
            deferred.append('odd_respell')
        else:
            before_odd = result
            result = _odd_respell(line, result, plain, store, dict_index, context_vec, decisions, input_method)
            if result is before_odd:
                if deferred is not None and (result.get('corrected') or line) != line:
                    # 打鍵中の行では、直した行の補正し直し（もう1度の解析）は手が止まってから
                    deferred.append('respell_on_fixed')
                else:
                    result = _respell_on_fixed(line, result, plain, store, dict_index, context_vec, decisions, input_method)
    if not slow and deferred is None:
        result = _line_key_repair(line, result, decisions, input_method, plain)
    elif deferred is not None and input_method == 'romaji' and (result.get('corrected') or line) == line:
        deferred.append('line_key_repair')
    result = _kana_keep(line, result, decisions)
    result = _wago_verb_kanji(line, result)
    result = _made_word_check(line, result, decisions, store, dict_index)
    result = _yoon_slip(line, result, decisions, input_method)
    result = _keep_converted(line, result, decisions)
    result = _broken_shape(line, result, decisions, input_method)
    result = _keep_names(line, result)
    result = _no_rare_kanji_from_kana(line, result)
    result = _keep_common_katakana(line, result)
    result = _keep_lattice_word(line, result, input_method)
    result = _keep_numerals(line, result, input_method)
    result = _numeral_counter(line, result)
    result = _dzi_kana_purple(line, result)
    result = _keep_suru_renyou(line, result)
    result = _swap_rival_kana_fix(line, result)
    result = _swap_rival_letter_drop(line, result, input_method)
    result = _rare_proper_after_wo(line, result)
    result = _lone_kanji_tail(line, result)
    result = _fix_breaks_grammar(line, result)
    result = _fix_lone_kanji_join(line, result, store, dict_index)
    result = _fix_kango_left_kana(line, result, store, dict_index)
    result = _fix_rare_outside_kanji(line, result)
    result = _fix_kanji_by_odd(line, result)
    result = _fix_rare_join_by_key(line, result, decisions, input_method)
    result = _keep_spoken_elongation(line, result)
    result = _keep_sahen_passive(line, result)
    result = _purple_on_fix(line, result)
    return _drop_mixed_katakana_marks(line, result)


def _revert_ops_map(line, result, ops, bad, hit, add_reason=None):
    """ops（line→直した行）のうち bad を元に戻す。紫は hit（直した行の位置）を外し、ほかは戻した行の位置へ写す。
    add_reason があれば、戻した所（元の字）を1つの紫にしてその理由を付ける。"""
    fixed = result.get('corrected') or line
    badset = set(bad)
    new = ''
    jmap = {}
    for o in ops:
        tag, i1, i2, j1, j2 = o
        if tag != 'equal' and o in badset:
            new += line[i1:i2]
            continue
        for k in range(j2 - j1):
            jmap[j1 + k] = len(new) + k
        new += fixed[j1:j2]
    jmap[len(fixed)] = len(new)

    def at(i):
        off = 0
        for o in ops:
            if o[1] >= i:
                break
            if o[0] != 'equal' and o not in badset:
                off += (o[4] - o[3]) - (o[2] - o[1])
        return i + off
    hit = set(hit)
    keep = []
    reasons = []
    import os
    if os.environ.get('CN_ODD_LINE_COORDS') != '0':
        # 紫（odd_spans）は元の行の位置（アプリは元の行に塗る・入口と多くの段がこの位置で書く）。直しを戻しても元の行は
        # 変わらないので、紫は写さずそのまま残し、hit（元の行の位置）だけ外す（2026-11-09 手分けA: 前の行の別の直しで
        # 字数が変わる行で、戻した所の紫が1字ずれていた）。CN_ODD_LINE_COORDS=0 で前のまま
        keep = [(sp[0], sp[1]) for sp in (result.get('odd_spans') or ()) if (sp[0], sp[1]) not in hit]
        reasons = [tuple(r) for r in (result.get('odd_reasons') or []) if (r[0], r[1]) not in hit]
        if add_reason and bad:
            # 戻した直しごと（1字以下の同じ所を挟んで続く直しは1つ）に紫を付ける
            parts = []
            for o in sorted(bad, key=lambda o: o[1]):
                a0, b0 = o[1], min(max(o[2], o[1] + 1), len(line))
                if parts and a0 - parts[-1][1] <= 1:
                    parts[-1] = (parts[-1][0], max(parts[-1][1], b0))
                else:
                    parts.append((a0, b0))
            for a0, b0 in parts:
                keep.append((a0, b0))
                reasons.append((a0, b0, add_reason))
    else:
        for sp in (result.get('odd_spans') or ()):
            a, b = sp[0], sp[1]
            if (a, b) in hit:
                continue
            if a in jmap and b in jmap and jmap[b] > jmap[a]:
                keep.append((jmap[a], jmap[b]))
        for r in (result.get('odd_reasons') or []):
            if (r[0], r[1]) in hit:
                continue
            if r[0] in jmap and r[1] in jmap:
                reasons.append((jmap[r[0]], jmap[r[1]]) + tuple(r[2:]))
        if add_reason and bad:
            a0, b0 = at(min(o[1] for o in bad)), at(max(o[2] for o in bad))
            if b0 <= a0:
                b0 = min(a0 + 1, len(new))
            keep.append((a0, b0))
            reasons.append((a0, b0, add_reason))
    ops2 = [x for x in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if x[0] != 'equal']
    out = dict(result)
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[x[3], x[4]] for x in ops2],
                'original_spans': [[x[1], x[2]] for x in ops2],
                'details': [d for d in (result.get('details') or []) if len(d) > 1 and d[1] and d[1] in new],
                'odd_spans': sorted(set(keep)), 'odd_reasons': reasons})
    return out


def _keep_sahen_passive(line, result):
    """〜する の動詞の未然形 せ ＋ られる（課せられる・罰せられる・発せられる）は正しい受け身。そこを替えた直し
    （課せられた → 変わられた）は戻し、そこの紫も外す（2026-11-09 補正担当の依頼・手分けB）。CN_KEEP_SAHEN_PASSIVE=0"""
    import os
    if os.environ.get('CN_KEEP_SAHEN_PASSIVE') == '0' or not isinstance(result, dict) or 'せられ' not in line:
        return result
    try:
        import morphology
        toks = list(morphology.tokenize(line))
        pairs = []
        for t, u in zip(toks, toks[1:]):
            if (t.pos == '動詞' and t.pos_sub == '自立' and t.infl_form == '未然レル接続' and t.surface.endswith('せ')
                    and (t.base_form or '').endswith('する') and any('一' <= c <= '鿿' for c in t.surface)
                    and u.start == t.end and u.pos == '動詞' and u.base_form == 'られる'):
                pairs.append((t.start, u.end))
        if not pairs:
            return result
        fixed = result.get('corrected') or line
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        bad = [o for o in ops if o[0] != 'equal' and any(o[1] < b and a < max(o[2], o[1] + 1) for a, b in pairs)]
        badset = set(bad)
        # 直した行での対の位置（戻さない直しの分をずらす）
        def jat(i):
            for o in ops:
                if o[1] <= i < o[2] or (o[1] == o[2] == i):
                    return o[3] + (i - o[1] if o[0] == 'equal' else 0)
            return len(fixed)
        jpairs = [(jat(a), jat(b - 1) + 1) for a, b in pairs]
        hit = [tuple(sp[:2]) for sp in (result.get('odd_spans') or ())
               if any(sp[0] < b and a < sp[1] for a, b in (pairs if os.environ.get('CN_ODD_LINE_COORDS') != '0' else jpairs))]
        if not bad and not hit:
            return result
        return _revert_ops_map(line, result, ops, bad, hit)
    except Exception:
        return result


def _purple_on_fix(line, result):
    """直した字の上に紫が残っている直しは、決め手の無い書き換え。直しを戻して元の字のまま紫にする
    （紫の所の打ち違いを直した後、別の段がその直しの上に紫を付けた・2026-11-09 補正担当の方針
    「決め手の無い書き換えは紫を付けるだけ」・手分けB）。CN_PURPLE_ON_FIX=0 で前のまま。"""
    import os
    if os.environ.get('CN_PURPLE_ON_FIX') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    odd = [tuple(sp[:2]) for sp in (result.get('odd_spans') or ())]
    if fixed == line or not odd:
        return result
    try:
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        # 直しの組: 1字以下の同じ所を挟んで続く直しは1つの直し（し|と|ゅうがく → と中学 の し の抜きと ゅうがく の替え）
        groups, cur = [], []
        for o in ops:
            if o[0] == 'equal':
                if o[2] - o[1] > 1 and cur:
                    groups.append(cur)
                    cur = []
                continue
            cur.append(o)
        if cur:
            groups.append(cur)
        # 紫が、直しで新しく置いた字に掛かっている組だけ（字を消しただけの所の境の紫は数えない）
        def on_new(o, a, b):
            if os.environ.get('CN_ODD_LINE_COORDS') != '0':
                # 紫は元の行の位置。直しが新しく字を置いた所の元の行の範囲と比べる（2026-11-09 手分けA）
                return o[4] > o[3] and a < max(o[2], o[1] + 1) and o[1] < b
            return o[4] > o[3] and a < o[4] and o[3] < b
        bad = [o for g in groups if any(on_new(o, a, b) for o in g for a, b in odd) for o in g]
        if not bad:
            return result
        hit = [(a, b) for a, b in odd if any(on_new(o, a, b) for o in bad)]
        return _revert_ops_map(line, result, ops, bad, hit, '直した所に紫が残るので、直し先を決められない')
    except Exception:
        return result


_NUM_CHARS = frozenset('〇一二三四五六七八九十百千万億')
_COUNTERS = frozenset('度階回枚人円年月日時分秒個本冊台件歳割')


def _keep_suru_renyou(line, result):
    """サ変の名詞に付いた する の連用形 し（反映**し**忘れた・確認**し**ながら・連絡**し**た）を、別のかなに替えた直し
    （反映し忘れた → 反映は忘れた）は戻す。名詞＋し＋用言・助動詞・て は正しい続きで、打ち違いの跡ではない
    （2026-11-06 脱字の束6）。CN_KEEP_SURU_RENYOU=0 で前のまま。"""
    import os
    if os.environ.get('CN_KEEP_SURU_RENYOU') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line or 'し' not in line:
        return result
    try:
        import morphology
        toks = list(morphology.tokenize(line))
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        parts, rev = [], []
        for tag, i1, i2, j1, j2 in ops:
            keep = False
            if tag == 'replace' and line[i1:i2] == 'し':
                k = [n for n, t in enumerate(toks) if t.start == i1 and t.end == i2]
                if k and 0 < k[0] < len(toks) - 1:
                    p_, t_, u_ = toks[k[0] - 1], toks[k[0]], toks[k[0] + 1]
                    keep = (t_.base_form == 'する' and p_.end == i1 and u_.start == i2
                            and p_.pos == '名詞' and (p_.pos_sub or '').split(':')[0] == 'サ変接続'
                            and any('一' <= c <= '鿿' for c in p_.surface)
                            and (u_.pos in ('動詞', '助動詞') or (u_.pos == '助詞' and (u_.pos_sub or '').startswith('接続助詞'))))
            if keep:
                parts.append(line[i1:i2])
                rev.append(fixed[j1:j2])
            else:
                parts.append(fixed[j1:j2])
        if not rev:
            return result
        new = ''.join(parts)
    except Exception:
        return result
    out = dict(result)
    nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                'original_spans': [[o[1], o[2]] for o in nops],
                'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and d[0] == 'し' and d[1] in rev)]})
    return out


SWAP_RIVAL_RANK_W = 15   # 入れ替えの形と直した形を比べるときの、内容の語の身近さ（順位）の重み


def _swap_rival_rarer(done, cand, fc, cc):
    """入れ替えの形（いのれました → 祈れました）の内容の語が、直した形（いれました → 入れました）の語よりずっと珍しく、
    行の費用＋重み×順位 で SWAP_RIVAL_MARGIN を超えて悪いなら、張り合う形と見ない（2026-11-09 手分けB）。
    読みの格子で表記にした語の順位で比べる。CN_SWAP_RIVAL_RANK=0 で前のまま"""
    import os
    if os.environ.get('CN_SWAP_RIVAL_RANK') == '0':
        return False
    try:
        import reading_lattice
        import ime_reconvert
    except Exception:
        return False

    def run(text, k):
        # 入れ替えた所を含むひらがなの並びだけを読みの格子にかける（行の漢字の所は格子に通さない）
        hira = lambda c: 'ぁ' <= c <= 'ゖ' or c == 'ー'
        a, b = k, k
        while a > 0 and hira(text[a - 1]):
            a -= 1
        while b < len(text) and hira(text[b]):
            b += 1
        return text[a:b]

    def worst(text):
        if not text:
            return None
        res = reading_lattice.best(text)
        rs = [ime_reconvert._rank(w[0]) for w in (res.words or ())
              if w[2] in ('名詞', '動詞', '形容詞') and w[1] not in ('する', 'ある', 'いる', 'なる')]
        return max(rs) if rs else None
    k = next((i for i, (x, y) in enumerate(zip(done, cand)) if x != y), None)
    if k is None:
        return False
    try:
        rd, rc = worst(run(done, k)), worst(run(cand, k))
    except Exception:
        return False
    if rd is None or rc is None:
        return False
    return cc + SWAP_RIVAL_RANK_W * rc > fc + SWAP_RIVAL_RANK_W * rd + SWAP_RIVAL_MARGIN


def _swap_rival_kana_fix(line, result):
    """行の直しが、かなの並びの中の1か所だけのかな1〜2字の替え・足し（くてばった → くたばった・くばてっ → くばてって）で、
    打った行の近くの隣り合うかな2字を入れ替えただけの形（くてばった → てくばった）が直した行と並ぶ（SWAP_RIVAL_MARGIN
    まで）なら、打鍵の順番違いとも読めるので直しは決め手にならない。直さず紫にする（迷うなら紫・2026-11-06 打鍵順
    入れ替えの束5）。CN_SWAP_RIVAL_FIX=0"""
    import os
    if os.environ.get('CN_SWAP_RIVAL_FIX') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    def hira(c):
        return 'ぁ' <= c <= 'ゖ'
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    if len(ops) != 1:
        return result
    tag, i1, i2, j1, j2 = ops[0]
    if i2 - i1 > 2 or j2 - j1 > 2 or not all(hira(c) for c in line[i1:i2] + done[j1:j2]):
        return result
    try:
        import morphology
        fc = morphology.path_cost(done)
    except Exception:
        return result
    if fc is None:
        return result
    lo, hi = max(0, i1 - 2), min(len(line), i2 + 2)
    for k in range(lo, hi - 1):
        a, b = line[k], line[k + 1]
        if a == b or not (hira(a) and hira(b)):
            continue
        cand = line[:k] + b + a + line[k + 2:]
        if cand == done:
            continue
        try:
            cc = morphology.path_cost(cand)
        except Exception:
            continue
        if cc is not None and cc <= fc + SWAP_RIVAL_MARGIN and not _swap_rival_rarer(done, cand, fc, cc):
            x, y = min(k, i1), max(k + 2, i2)
            out = dict(result)
            out.update({'corrected': line, 'changed': False, 'details': [], 'spans': [], 'original_spans': []})
            odd = [sp for sp in (result.get('odd_spans') or ()) if sp[1] <= x or y <= sp[0]]
            out['odd_spans'] = odd + [(x, y)]
            return out
    return result


def _swap_rival_letter_drop(line, result, input_method):
    """ローマ字の行の直しが、語の直後に残った英字1字を消すだけ（買いg → 買い）で、その語の終わりの打鍵と英字を
    隣どうし入れ替えた読み（kaig → kagi → かぎ）の行が直した行と並ぶ（SWAP_RIVAL_MARGIN まで）なら、打鍵の順番違い
    とも読めるので消すだけの直しは決め手にならない。直さず紫にする（2026-11-06 打鍵順入れ替えの束5）。CN_SWAP_RIVAL_LETTER=0"""
    import os
    import unicodedata
    if input_method != 'romaji' or os.environ.get('CN_SWAP_RIVAL_LETTER') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    if len(ops) != 1 or ops[0][0] != 'delete' or ops[0][2] - ops[0][1] != 1:
        return result
    i = ops[0][1]
    letter = unicodedata.normalize('NFKC', line[i]).lower()
    if not ('a' <= letter <= 'z') or i == 0:
        return result
    try:
        import morphology
        import romaji_swap_repair as RS
        toks = list(morphology.tokenize(line[:i]))
        fc = morphology.path_cost(done)
    except Exception:
        return result
    if not toks or fc is None:
        return result
    kt = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
    last = toks[-1]
    rd = (last.reading if last.has_reading else last.surface).translate(kt)
    if not rd or not all('ぁ' <= c <= 'ゖ' for c in rd) or len(last.surface) > i:
        return result
    start = i - len(last.surface)
    head, tail = rd[:-2], rd[-2:]
    for sp in RS._spellings(tail)[:4]:
        keys = sp + letter
        for k in range(max(0, len(keys) - 3), len(keys) - 1):
            sw = keys[:k] + keys[k + 1] + keys[k] + keys[k + 2:]
            if sw == keys:
                continue
            try:
                kana = RS._to_kana(sw)
            except Exception:
                continue
            if not kana or not all('ぁ' <= c <= 'ゖ' for c in kana):
                continue
            cand = line[:start] + head + kana + line[i + 1:]
            if cand == done or kana == tail:
                continue
            try:
                cc = morphology.path_cost(cand)
            except Exception:
                continue
            if cc is not None and cc <= fc + SWAP_RIVAL_MARGIN:
                out = dict(result)
                out.update({'corrected': line, 'changed': False, 'details': [], 'spans': [], 'original_spans': []})
                odd = [x for x in (result.get('odd_spans') or ()) if x[1] <= start or i + 1 <= x[0]]
                out['odd_spans'] = odd + [(start, i + 1)]
                return out
    return result


PROPER_AFTER_WO_RANK = 600


def _rare_proper_after_wo(line, result):
    """を のすぐ後ろで文が終わる所に、珍しい地名・人名（料理を給田。）が来るのは、打ち違いを IME が固有名詞に
    変換した形のことが多い（を の後ろには述語が来る）。直さず、その語を紫にする（迷うなら紫・2026-11-06 うにの画面）。
    CN_PROPER_AFTER_WO=0"""
    import os
    if os.environ.get('CN_PROPER_AFTER_WO') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done != line:
        return result
    try:
        import morphology
        from ime_reconvert import _freq
        toks = list(morphology.tokenize(line))
        wf = _freq() or {}
    except Exception:
        return result
    add = []
    for n, t in enumerate(toks):
        if n == 0 or t.pos != '名詞' or not str(t.pos_sub or '').startswith('固有名詞'):
            continue
        prev = toks[n - 1]
        if prev.surface != 'を' or prev.pos != '助詞':
            continue
        nxt = toks[n + 1] if n + 1 < len(toks) else None
        if nxt is not None and not (nxt.pos == '記号' and nxt.surface in '。．.！？!?'):
            continue
        r = wf.get(t.surface)
        if r is not None and r < PROPER_AFTER_WO_RANK:
            continue
        add.append((t.start, t.end))
    if not add:
        return result
    odd = list(result.get('odd_spans') or ())
    if any(x[0] < b and a < x[1] for a, b in add for x in odd):
        return result
    out = dict(result)
    out['odd_spans'] = odd + add
    out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(a, b, 'を の後ろで文が終わる所の地名・人名は打ち違いかもしれない') for a, b in add]
    return out


def _lone_kanji_tail(line, result):
    """文の終わりが、助詞のすぐ後ろの1拍の漢字1字の名詞（予定で｜居）で終わる所は、言い終わりのかな（です の す）を
    IME が漢字1字にした打ち違いのことが多い。直さず紫（迷うなら紫・2026-11-06 かなの試験。正しい文2,050行で0件）。
    CN_LONE_KANJI_TAIL=0"""
    import os
    if os.environ.get('CN_LONE_KANJI_TAIL') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    try:
        import morphology
        toks = list(morphology.tokenize(done))
    except Exception:
        return result
    while toks and toks[-1].pos == '記号':
        toks.pop()
    if len(toks) < 2:
        return result
    t, p = toks[-1], toks[-2]
    rd = t.reading or ''
    if not (t.pos == '名詞' and len(t.surface) == 1 and '一' <= t.surface <= '鿿' and p.pos == '助詞'
            and p.end == t.start and len([c for c in rd if c not in 'ャュョァィゥェォゃゅょぁぃぅぇぉ']) == 1):
        return result
    # 直した行の位置を元の行に戻す（その所は前の段が触っていない所だけ）
    m = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
        if tag == 'equal' and i1 <= t.start and t.end <= i2:
            m = (t.start - i1 + j1, t.end - i1 + j1)
    if m is None:
        return result
    odd = list(result.get('odd_spans') or ())
    if any(x[0] < m[1] and m[0] < x[1] for x in odd):
        return result
    out = dict(result)
    out['odd_spans'] = odd + [m]
    out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(m[0], m[1], '文の終わりの漢字1字は打ち違いかもしれない')]
    return out


def _bad_pair(x, y):
    """隣り合う2語が日本語の文の形として続かない組か（直した行にだけ当てる・2026-11-06 うに「自然かどうかは都度判断」）。"""
    xf = x.infl_form or ''
    if (x.pos == '動詞' and xf.startswith('未然') and y.pos == '助動詞' and y.base_form in ('です', 'だ')
            and __import__('os').environ.get('CN_FIX_MIZEN_DESU') != '0'):
        return True          # たた｜です（予定です の打ち違いの戻し）。動詞の未然形のすぐ後ろに です・だ は続かない
    if x.pos == '形容詞' and xf.startswith('基本形') and y.pos == '動詞':
        return True          # 古い｜しい（降るらしい の打ち違いを 古い にした）
    if x.pos == '動詞' and xf.startswith('基本形') and y.pos in ('副詞', '動詞') and y.surface[:1] in 'まし':
        return True          # 呈す｜ますます（提出します）
    if x.pos == '名詞' and y.pos == '助詞' and y.surface in ('ので', 'のに') and (y.pos_sub or '').startswith('接続助詞'):
        return True          # 作業｜ので（作業の手順）
    if x.pos == '助動詞' and xf.startswith('仮定形') and y.pos == '助詞' and y.surface == 'か':
        return True          # 洗った｜ら｜か（洗ってから）
    if (x.pos == '動詞' and xf.startswith('連用形') and x.surface[-1:] in 'てで' and y.pos == '形容詞'
            and y.surface in ('よい', 'いい', '良い')):
        return True          # すて｜よい（捨ててよい の て が無い形・住みよい は て で終わらないので当たらない）
    if (x.pos == '助詞' and ((x.pos_sub or '').startswith('格助詞') or (x.pos_sub or '').startswith('係助詞'))
            and x.surface != 'の' and y.pos == '名詞' and (y.pos_sub or '').startswith('非自立')):
        return True          # が｜ふう らしい（降るらしい）。こと・もの・ふう は前に語が要る（の の後ろ・連体の形は当たらない）
    if x.pos == '助詞' and (x.pos_sub or '').startswith('終助詞') and y.pos == '名詞':
        return True          # 甘い｜さ｜お茶（毎朝お茶）。言い切りの さ・よ・ね のすぐ後ろに名詞は続かない
    if x.pos == '助詞' and x.surface == 'を' and y.pos == '動詞' and y.base_form == 'いる':
        return True          # 靴｜を｜い て（履いて）。を の後ろに いる は来ない
    if x.pos == '動詞' and xf.startswith('基本形') and y.pos == '動詞' and (y.pos_sub or '').startswith('自立'):
        return True          # 降る｜いり（降るらしい）。言い切りの動詞のすぐ後ろに別の動詞は続かない
    if (x.pos == '形容詞' and xf.startswith('基本形') and y.pos == '助詞' and y.surface in ('を', 'が')
            and (y.pos_sub or '').startswith('格助詞')):
        return True          # 著い｜を 共有
    if (x.pos == '助動詞' and x.base_form == 'たい' and xf.startswith('連用') and y.pos == '名詞'
            and not (y.pos_sub or '').startswith(('接尾', '非自立'))):
        return True          # 貸せたく｜もの
    if x.pos == '動詞' and xf.startswith('基本形') and y.pos == '助動詞' and y.base_form in ('き', 'けり'):
        return True          # ある｜き（古い き は連用形に付く）
    if (x.pos == '動詞' and xf == '連用形' and y.pos == '助詞' and y.surface == 'で'
            and (y.pos_sub or '').startswith('接続助詞')):
        return True          # 癒え｜で（接続の で は 読ん・泳い の形にだけ付く）
    if x.pos == '動詞' and y.surface.startswith('ー'):
        return True          # くっつき｜ー（伸ばし ー は外来語の中の字。動詞には続かない）
    if (x.pos == '助詞' and x.surface in ('ので', 'のに') and (x.pos_sub or '').startswith('接続助詞')
            and y.pos == '助詞' and y.surface == 'と'):
        return True          # ので｜と
    if (x.pos == '名詞' and x.surface and '一' <= x.surface[-1] <= '鿿' and y.surface.startswith('っ')
            and y.pos not in ('助詞', '助動詞') and not (y.pos_sub or '').startswith('接尾')
            and not y.surface.startswith('っぽ')):
        return True          # 今週｜っちゅう
    if x.pos == '副詞' and y.pos == '助詞' and y.surface in ('を', 'が'):
        return True          # まだ｜を 開ける（窓を）。副詞のすぐ後ろに を・が は来ない
    if (x.pos == '動詞' and xf.startswith('連用形') and y.pos == '助詞' and y.surface in ('のに', 'ので')
            and (y.pos_sub or '').startswith('接続助詞')):
        return True          # 変え｜のに（帰りに）。連用形に のに・ので は付かない
    if (x.pos == '形容詞' and xf.startswith('ガル接続') and y.pos == '名詞'
            and not (y.pos_sub or '').startswith(('接尾', '非自立')) and not y.surface.startswith('ー')):
        return True          # 新し｜パソコン（新しいパソコン）
    if x.pos == '動詞' and y.pos == '助動詞' and y.surface == 'まい':
        return True          # すすめ｜まい さ（すすめます）。打ち違いの直しで 〜まい（打ち消しの推し量り）は先ず出ない
    if x.pos == '名詞' and (x.pos_sub or '').startswith('サ変接続') and y.pos == '動詞' and y.base_form == 'いる':
        return True          # 食事｜い ました（食事をしました）。する名詞のすぐ後ろに いる は来ない
    if (x.pos == '動詞' and xf.startswith('連用形') and (x.pos_sub or '').startswith('非自立')
            and y.pos == '助動詞' and y.surface == 'です'):
        return True          # 当てて｜い｜です（予定です）。動詞の連用形に です は付かない
    if x.pos == '助詞' and (x.pos_sub or '').startswith('格助詞') and y.pos == '助動詞' and y.surface in ('う', 'た', 'ます'):
        return True          # 牛｜に｜う が（牛乳が）。格助詞のすぐ後ろに う・た・ます は来ない
    if y.pos == '動詞' and (y.infl_form or '').startswith('命令ｙｏ') and y.surface not in ('てよ', 'でよ'):
        return True          # し｜えよ（三時から）。打ち違いの直しで 〜よ の命令の形は先ず出ない
    if y.pos == '助動詞' and y.surface == 'し' and (y.infl_form or '').startswith('体言接続'):
        return True          # 下さ｜し（ください）。古い言い方の し（過去の き）
    if y.pos == '助動詞' and y.surface in ('つる', 'ぬる', 'たる') and (y.infl_form or '').startswith('体言接続'):
        return True          # 出｜つる 森・阿｜たる（古い言い方の つる・ぬる・たる は今の文に出ない。堂々たる は連体詞の1語）
    return False


# 小さい ぁぃぅぇぉ を付けて1拍に読める前の字（ふぁ・てぃ・しぇ・うぃ・とぅ など）。ほかの字の後ろ（えぃ・らぃ）は書かない
_SMALL_VOWEL_OK = {
    'ぁ': set('ふつゔくぐうすずとど'), 'ぃ': set('ふてでうつすずゔくぐとど'), 'ぅ': set('とどふゔく'),
    'ぇ': set('しちじふういつゔきぎにひびぴみりてでくぐすずとど'), 'ぉ': set('ふうつゔとどくぐすず'),
}


def _bad_small_kana(done, line):
    """done の中の、日本語の書き方に無い小さい母音の並び（えぃ月・らぃい）の位置 [(始め, 終わり)]。line に同じ並びが
    在れば除く。CN_FIX_SMALL_KANA=0 で見ない。"""
    import os
    if os.environ.get('CN_FIX_SMALL_KANA') == '0':
        return []
    out = []
    for i in range(1, len(done)):
        c = done[i]
        ok = _SMALL_VOWEL_OK.get(c)
        if ok is None:
            continue
        p = done[i - 1]
        if not ('ぁ' <= p <= 'ゖ') or p in ok or p == c:
            continue
        if done[i - 1:i + 1] in line:
            continue
        out.append((i - 1, i + 1))
    return out


_CLASSICAL_VERB = ('下二', '上二', '四段', 'ラ変', 'ナ変')


def _classical_verbs(done, line):
    """done の中の、古い活用の動詞（助く・捨つ: 下二段・上二段・四段）の位置 [(始め, 終わり)]。line に同じ語が在れば除く。
    CN_FIX_CLASSICAL_VERB=0 で見ない。"""
    import os
    if os.environ.get('CN_FIX_CLASSICAL_VERB') == '0':
        return []
    try:
        import morphology
        T = morphology._TOKENIZER
        if T is None:
            return []
        out, at = [], 0
        for t in T.tokenize(done):
            sf = t.surface
            if (t.part_of_speech.startswith('動詞') and ((t.infl_type or '').startswith(_CLASSICAL_VERB)
                                                        or (t.infl_form or '').startswith('文語')
                                                        or ((t.infl_form or '').startswith('体言接続特殊')
                                                            and any('一' <= ch <= '鿿' for ch in sf))
                                                        or sf[-1:] == 'へ' or 'ゑ' in sf or 'ゐ' in sf)
                    and sf not in line):
                out.append((at, at + len(sf)))
            at += len(sf)
        return out
    except Exception:
        return []


def _is_kanji_char(c):
    return '\u4e00' <= c <= '\u9fff' or c in '々〆'


def _fix_breaks_grammar(line, result):
    """直した行の、直した所の前後に、文の形として続かない2語の組（古い｜しい・呈す｜ますます・作業｜ので・たら｜か）が
    新しくできたなら、その直しは採らない。元の行に戻して紫（迷うなら紫）。元の行に同じ組が在れば直しのせいではないので
    見ない。CN_FIX_GRAMMAR=0"""
    import os
    if os.environ.get('CN_FIX_GRAMMAR') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        import morphology
        tf = list(morphology.tokenize(done))
        to = list(morphology.tokenize(line))
    except Exception:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return result
    old = {(x.surface, y.surface) for x, y in zip(to, to[1:]) if x.end == y.start and _bad_pair(x, y)}
    hits = []
    for x, y in zip(tf, tf[1:]):
        if x.end != y.start or not _bad_pair(x, y) or (x.surface, y.surface) in old:
            continue
        a, b = x.start, y.end
        near = [o for o in ops if o[3] <= b and a <= o[4]]
        if near:
            hits.extend(near)
    if os.environ.get('CN_FIX_TA_TAIL') != '0':
        # 文の終わりが た の付かない 連用タ接続（時間が かたかっ）で終わる形を直しが作った
        def _tail(ts):
            ts = [t for t in ts if t.pos != '記号']
            return ts[-1] if ts else None
        xt, xo = _tail(tf), _tail(to)
        renyou_tail = (xt is not None and xt.pos == '動詞' and (xt.pos_sub or '').startswith('自立')
                       and (xt.infl_form or '') == '連用形' and os.environ.get('CN_FIX_RENYOU_TAIL') != '0')
        # 敬語の五段ラ行の特別な動詞（くださる・なさる・おっしゃる）の い で終わる形は、連用形と読まれても
        # 頼みの言い切り（ください・なさい）。文の終わりに在ってよい。CN_FIX_HONORIFIC_IMPERATIVE=0 で前のまま
        # 行が読点（、，）で終わるなら文は次の行へ続く。連用形＋読点（上に詰め、）は連用中止の形で、文の終わりではない
        # （2026-11-09 手分けA）。CN_FIX_RENYOU_COMMA=0 で前のまま
        if (renyou_tail and done.rstrip()[-1:] in ('、', '，', ',')
                and os.environ.get('CN_FIX_RENYOU_COMMA') != '0'):
            renyou_tail = False
        if (renyou_tail and (xt.base_form or '') in ('くださる', '下さる', 'なさる', '為さる', 'おっしゃる', '仰る', 'いらっしゃる', 'ござる')
                and xt.surface.endswith('い') and os.environ.get('CN_FIX_HONORIFIC_IMPERATIVE') != '0'):
            renyou_tail = False
        # 直しが作った、文の終わりの形容詞の語幹だけの形（かくごっ → かく｜ごつ: ごつい の ガル接続）も続かない。
        # CN_FIX_GARU_TAIL=0 で前のまま
        garu_tail = (xt is not None and xt.pos == '形容詞' and (xt.infl_form or '') == 'ガル接続'
                     and os.environ.get('CN_FIX_GARU_TAIL') != '0')
        if (xt is not None and xt.pos in ('動詞', '形容詞')
                and ((xt.infl_form or '').startswith('連用タ接続') or renyou_tail or garu_tail)
                and (xo is None or xo.surface != xt.surface)):
            hits.extend(o for o in ops if o[3] <= xt.end and xt.start <= o[4])
    for a, b in _classical_verbs(done, line):
        hits.extend(o for o in ops if o[3] < b and a < o[4])
    for a, b in _bad_small_kana(done, line):
        hits.extend(o for o in ops if o[3] <= b and a <= o[4])
    if os.environ.get('CN_FIX_PARTICLE_KATA') != '0':
        # 元の行で助詞だったかなが、片仮名の語の中へ取り込まれた直し（散歩はコット→散歩ハット）
        pt = [(x.start, x.end) for x in to if x.pos == '助詞' and all('ぁ' <= c <= 'ゖ' for c in x.surface)]
        for o in ops:
            rep = done[o[3]:o[4]]
            if rep and all('ァ' <= c <= 'ヶ' or c == 'ー' for c in rep) and any(o[1] <= a and b <= o[2] for a, b in pt):
                # かなで打った外来語を片仮名にしただけ（ちけっと→チケット）は、助詞の取り込みではない
                kata = lambda c: 'ァ' <= c <= 'ヶ'     # 伸ばし ー は前後どちらの字にもなるので見ない（かれー）
                if (all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in line[o[1]:o[2]])
                        and not (o[1] > 0 and kata(line[o[1] - 1])) and not (o[2] < len(line) and kata(line[o[2]]))
                        and os.environ.get('CN_FIX_PARTICLE_KATA_LOAN') != '0'):
                    continue
                # 漢字の語ごと読み直した直し（右田でブル → 右ダブル: 打った読み みぎたでぶる の打ち違いを戻した形）は、
                # 助詞だけを片仮名の語へ取り込んだ形ではない。CN_FIX_PARTICLE_KATA_KANJI=0 で前のまま
                if (any(_is_kanji_char(c) for c in line[o[1]:o[2]])
                        and os.environ.get('CN_FIX_PARTICLE_KATA_KANJI') != '0'):
                    continue
                hits.append(o)
    if not hits:
        return result
    if len(ops) == 1:
        o = ops[0]
        out = dict(result)
        out.update({'corrected': line, 'changed': False, 'details': [], 'spans': [], 'original_spans': []})
        lo, hi = min(o[1], len(line) - 1), max(o[2], o[1] + 1)
        odd = [sp for sp in (result.get('odd_spans') or ()) if sp[1] <= lo or hi <= sp[0]]
        out['odd_spans'] = odd + [(lo, min(hi, len(line)))]
        out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(lo, min(hi, len(line)), '直すと文の形が続かないので、直し先を決められない')]
        return out
    # 直しが2か所以上なら、続かない組に掛かる直しだけ戻す（ほかの直しは残す）
    bad = set(hits)
    parts = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
        if tag == 'equal' or (tag, i1, i2, j1, j2) in bad:
            parts.append(line[i1:i2])
        else:
            parts.append(done[j1:j2])
    new = ''.join(parts)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2],
                'details': [d for d in (result.get('details') or []) if len(d) > 1 and d[1] and d[1] in new]})
    add = sorted({(min(o[1], len(line) - 1), min(max(o[2], o[1] + 1), len(line))) for o in bad})
    odd = [sp for sp in (result.get('odd_spans') or ()) if not any(sp[0] < b and a < sp[1] for a, b in add)]
    out['odd_spans'] = odd + add
    return out


def _ime_one_key_fix(line, i1, i2, rep):
    """line[i1:i2] の IME の逆変換の読みから、同じ長さの隣のキー1打の置き換えで rep の読みになるか。"""
    import os
    if os.environ.get('CN_FIX_LONE_KANJI_IME_SLIP') == '0':
        return False
    try:
        import ime_reconvert
        import kana_lattice_place as KLP
        from contextual_repair import key_repairs
        src = ime_reconvert.ime_reverse_reading(line, i1, i2)
        dst = KLP._reading_of(rep)
    except Exception:
        return False
    if not src or not dst or len(src) != len(dst) or src == dst:
        return False
    try:
        for row in key_repairs(src, line[i1 - 1:i1] if i1 else '', line[i2:i2 + 1]):
            if getattr(row, 'reading', row) == dst and getattr(row, 'operation', '') == 'adjacent_substitution':
                return True
    except Exception:
        return False
    return False


def _same_reading_fix(orig, rep):
    """orig と rep が同じ読みの漢字の語か（同じ読みの表記の選び直し）。"""
    import os
    if os.environ.get('CN_FIX_LONE_KANJI_SAME_READING') == '0' or not orig or orig == rep:
        return False
    try:
        import kana_lattice_place as KLP
        if not all(KLP._kanji(c) for c in orig + rep):
            return False
        a, b = KLP._reading_of(orig), KLP._reading_of(rep)
        return bool(a) and a == b
    except Exception:
        return False


def _fix_lone_kanji_join(line, result, store, dict_index):
    """直して置いた漢字の語（2字以上）のすぐ前か後ろに、直していない漢字1字が付いて1つの漢字の並びになり、
    つないだ形が辞書の語にならない所（誤解｜人 ください・花｜保管 を送った）は、その直しを採らず紫（迷うなら紫）。
    確認｜中・請求｜書 のように辞書の語になる形は残す。CN_FIX_LONE_KANJI=0"""
    import os
    if os.environ.get('CN_FIX_LONE_KANJI') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        import last_keystroke as LK
        import kana_lattice_place as KLP
    except Exception:
        return result
    kj = KLP._kanji

    VO = dict(zip('かきくけこさしすせそたちつてとはひふへほ', 'がぎぐげござじずぜぞだぢづでどばびぶべぼ'))

    def joined_ok(left, right, one):
        """left＋right（one はその片方の漢字1字）が辞書の語か。1字の方は音・訓のどの読みでも（後ろなら濁りも）見る。"""
        try:
            import kanji_onkun
            rs = list(kanji_onkun.readings_of(one) or [])
        except Exception:
            rs = []
        if not rs:
            return True
        if one == right:
            rs = rs + [VO.get(r[:1], r[:1]) + r[1:] for r in rs]
            heads = [KLP._reading_of(left) + r for r in dict.fromkeys(rs)]
        else:
            heads = [r + KLP._reading_of(right) for r in dict.fromkeys(rs)]
        joined = left + right
        try:
            return any(joined in (LK._kanji_choices(h, store, dict_index) or [])[:8] for h in heads)
        except Exception:
            return True

    bad = []
    try:
        import morphology
        one_kanji = {(t.start, t.end) for t in morphology.tokenize(done) if len(t.surface) == 1 and kj(t.surface)}
    except Exception:
        one_kanji = set()
    ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    try:
        noun_tok = {(t.start, t.end): t for t in morphology.tokenize(done)}
    except Exception:
        noun_tok = {}
    for tag, i1, i2, j1, j2 in ops:
        if tag not in ('replace', 'insert'):
            continue
        rep = done[j1:j2]
        if (len(rep) == 1 and kj(rep) and os.environ.get('CN_FIX_LONE_KANJI_ONE') != '0'
                and (j1 == 0 or not kj(done[j1 - 1]))):
            # 直して置いた漢字1字（名詞）のすぐ後ろに、直していない漢字の名詞が続き、つないだ形が辞書の語にならない
            # （g路連絡 → 露｜連絡）
            t1 = noun_tok.get((j1, j2))
            nxt = next((t for (a_, b_), t in noun_tok.items() if a_ == j2), None)
            if (t1 is not None and t1.pos == '名詞' and nxt is not None and nxt.pos == '名詞'
                    and len(nxt.surface) >= 2 and all(kj(c) for c in nxt.surface)
                    and not joined_ok(rep, nxt.surface, rep)):
                bad.append((tag, i1, i2, j1, j2))
            continue
        if len(rep) < 2 or not all(kj(c) for c in rep):
            continue
        # 後ろに 漢字1字（その後ろは漢字でないか、その1字が1語に切れる: 資料｜魚｜共有）
        # その1字が動詞・形容詞の頭（入力｜見て の 見）なら、語に付く1字ではないので見ない（2026-11-08 手分けB）。
        # ただし 身内｜撒いて（ミウ一 → 身内 の誤り）も通すので、既定では使わない（CN_FIX_LONE_KANJI_VERB=1 で使う）
        after = next((t for (a_, b_), t in noun_tok.items() if a_ == j2), None)
        verb_after = (after is not None and after.pos in ('動詞', '形容詞')
                      and (os.environ.get('CN_FIX_LONE_KANJI_VERB') == '1'
                           # 直した所の IME の逆変換の読み（乳リュク を にゅうりゅく）から隣のキー1打の戻しで直した語の
                           # 読み（にゅうりょく）になるなら、直しは打ち違いの戻しとして確か。後ろの1字が動詞の頭なら
                           # 語に付く1字ではない（2026-11-09 手分けA）。CN_FIX_LONE_KANJI_IME_SLIP=0 で前のまま
                           or _ime_one_key_fix(line, i1, i2, rep)
                           # 同じ読みの表記の選び直し（変身 → 返信）は打ち違いの戻しではなく IME の選び違いの直しなので、
                           # 後ろの1字が動詞の頭（願います の 願）なら語に付く1字ではない（2026-11-09 うにの未解決タブ）。
                           # CN_FIX_LONE_KANJI_SAME_READING=0 で前のまま
                           or _same_reading_fix(line[i1:i2], rep)))
        # 後ろの1字が解析で時・状態の接尾（接尾:副詞可能 終了｜時・確認｜中・作業｜後。誤解｜人 の 人 は接尾:一般で見ない）なら、語に付く接尾として形が成り立つ。辞書に1語として
        # 無くても戻さない（囚虜時 → 終了時 を戻していた・2026-11-09 うにの未解決タブ）。CN_FIX_LONE_KANJI_SUFFIX=0
        suffix_after = (after is not None and after.pos == '名詞' and (after.pos_sub or '') == '接尾:副詞可能'
                        and len(after.surface) == 1 and os.environ.get('CN_FIX_LONE_KANJI_SUFFIX') != '0')
        if j2 < len(done) and kj(done[j2]) and not verb_after and not suffix_after and (
                j2 + 1 >= len(done) or not kj(done[j2 + 1]) or (j2, j2 + 1) in one_kanji):
            if not joined_ok(rep, done[j2], done[j2]):
                bad.append((tag, i1, i2, j1, j2))
                continue
        # 前に 漢字1字（その前は漢字でない）。その1字が前のかなと1語（お｜客 の 客: お客）なら、1字の漢字ではない
        # （お客｜様用 を 客様用 と見ない・2026-11-08 手分けA）。CN_FIX_LONE_KANJI_TOKEN=0 で前のまま
        if j1 >= 1 and kj(done[j1 - 1]) and (j1 < 2 or not kj(done[j1 - 2])) and (
                os.environ.get('CN_FIX_LONE_KANJI_TOKEN') == '0' or j1 < 2 or (j1 - 1, j1) in one_kanji):
            if not joined_ok(done[j1 - 1], rep, done[j1 - 1]):
                bad.append((tag, i1, i2, j1, j2))
    if not bad:
        return result
    bad = set(bad)
    parts = []
    for tag, i1, i2, j1, j2 in ops:
        parts.append(line[i1:i2] if tag == 'equal' or (tag, i1, i2, j1, j2) in bad else done[j1:j2])
    new = ''.join(parts)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2],
                'details': [d for d in (result.get('details') or []) if len(d) > 1 and d[1] and d[1] in new]})
    add = sorted({(min(o[1], len(line) - 1), min(max(o[2], o[1] + 1), len(line))) for o in bad})
    odd = [sp for sp in (result.get('odd_spans') or ()) if not any(sp[0] < b and a < sp[1] for a, b in add)]
    out['odd_spans'] = odd + add
    out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(a, b, '直した語に漢字1字が付いて語にならないので、直し先を決められない') for a, b in add]
    return out


def _revert_ops_purple(line, result, ops, bad, reason):
    """ops（line→直した行の difflib の組）のうち bad の直しだけ元に戻し、戻した所を紫にする。"""
    bad = set(bad)
    done = result.get('corrected') or line
    parts = [line[i1:i2] if tag == 'equal' or (tag, i1, i2, j1, j2) in bad else done[j1:j2]
             for tag, i1, i2, j1, j2 in ops]
    new = ''.join(parts)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out = dict(result)
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2],
                'details': [d for d in (result.get('details') or []) if len(d) > 1 and d[1] and d[1] in new]})
    add = sorted({(min(o[1], len(line) - 1), min(max(o[2], o[1] + 1), len(line))) for o in bad})
    odd = [sp for sp in (result.get('odd_spans') or ()) if not any(sp[0] < b and a < sp[1] for a, b in add)]
    out['odd_spans'] = odd + add
    out['odd_reasons'] = list(result.get('odd_reasons') or []) + [(a, b, reason) for a, b in add]
    return out


PARALLEL_KIN_ITEMS = 3   # 並べた語がこれだけ以上の所だけ見る
PARALLEL_KIN_PEERS = 2   # 同じ分類（分類語彙表の分類項目）の仲間がほかにこれだけ以上いる語を「仲間」とする


def _kin_codes(t):
    """語の分類項目（1.5504 など）の組。見出しが漢字でも かなでも引く（表は魚の名を かなで持つ）。"""
    try:
        import semantic_class
    except Exception:
        return frozenset()
    rd = t.reading or ''
    rd = ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in rd)
    got = set(semantic_class.codes(t.surface))
    if rd:
        got |= set(semantic_class.codes(rd))
    return frozenset(c[:6] for c in got)


def _list_items(toks):
    """並立助詞（とか・や など）か読点で区切って並べた名詞の並び。[(始め, 終わり, 分類の組)…] の並びのリスト。"""
    lists, cur, n = [], [], 0
    while n < len(toks):
        t = toks[n]
        if t.pos != '名詞':
            if len(cur) >= PARALLEL_KIN_ITEMS:
                lists.append(cur)
            cur = []
            n += 1
            continue
        m = n
        while m + 1 < len(toks) and toks[m + 1].pos == '名詞' and toks[m + 1].start == toks[m].end:
            m += 1
        codes = frozenset().union(*[_kin_codes(x) for x in toks[n:m + 1]]) if m > n else _kin_codes(t)
        cur.append((t.start, toks[m].end, codes))
        sep = toks[m + 1] if m + 1 < len(toks) else None
        if sep is None or not ((sep.pos == '助詞' and '並立助詞' in str(sep.pos_sub or ''))
                               or (sep.pos == '記号' and sep.surface in '、，,')):
            if len(cur) >= PARALLEL_KIN_ITEMS:
                lists.append(cur)
            cur = []
        n = m + 2 if sep is not None else m + 1
    if len(cur) >= PARALLEL_KIN_ITEMS:
        lists.append(cur)
    return lists


def _parallel_kin(line, result):
    """とか・や・読点で3つ以上並べた名詞のうち、ほかの2つ以上と同じ分類（分類語彙表の分類項目・鯛とか鯖とか鰯とか
    ＝魚）の語は、書いた人が選んだ語。その語を仲間でない語に替える直し（鯖→佐賀）は戻し、その語の紫も外す。
    学んだ語が1打違いに居ても、並べた仲間を崩さない（2026-11-07 うにの画面・学習で補正が崩れない）。CN_PARALLEL_KIN=0"""
    import os
    if os.environ.get('CN_PARALLEL_KIN') == '0' or not isinstance(result, dict):
        return result
    try:
        import morphology
        toks = list(morphology.tokenize(line))
    except Exception:
        return result
    kin = []
    for items in _list_items(toks):
        for k, (a, b, cs) in enumerate(items):
            for c in cs:
                if sum(1 for j, x in enumerate(items) if j != k and c in x[2]) >= PARALLEL_KIN_PEERS:
                    kin.append((a, b, c))
                    break
    if not kin:
        return result
    done = result.get('corrected') or line
    allops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    ops = [o for o in allops if o[0] != 'equal']
    bad = []
    for o in ops:
        hit = [x for x in kin if x[0] < max(o[2], o[1] + 1) and o[1] < x[1]]
        if not hit:
            continue
        a, b, c = hit[0]
        if o[1] < a or o[2] > b:
            continue
        new_word = line[a:o[1]] + done[o[3]:o[4]] + line[o[2]:b]
        try:
            ntoks = list(morphology.tokenize(new_word))
            ncodes = frozenset().union(*[_kin_codes(t) for t in ntoks]) if ntoks else frozenset()
        except Exception:
            continue
        if c not in ncodes:
            bad.append(o)
    out = result
    if bad:
        out = _revert_ops_purple(line, result, allops, bad, '')
        add = {(min(o[1], len(line) - 1), min(max(o[2], o[1] + 1), len(line))) for o in bad}
        out['odd_spans'] = [sp for sp in out.get('odd_spans') or () if tuple(sp[:2]) not in add]
        out['odd_reasons'] = [r for r in out.get('odd_reasons') or () if tuple(r[:2]) not in add]
    done = out.get('corrected') or line
    if done != line and len(done) != len(line):
        return out
    odd = list(out.get('odd_spans') or ())
    keep = [sp for sp in odd if not any(a <= sp[0] and sp[1] <= b for a, b, _ in kin)]
    if len(keep) != len(odd):
        out = dict(out)
        out['odd_spans'] = keep
        out['odd_reasons'] = [r for r in out.get('odd_reasons') or ()
                              if not any(a <= r[0] and r[1] <= b for a, b, _ in kin)]
    return out


KANGO_JOIN_GAP = 120   # 続けた読みの漢語の1番目が2番目より、語の使われやすさの順位でこれだけ前なら決める


def _kango_join(done, toks, k, store, dict_index):
    """かなの漢語 toks[k] のすぐ後ろの漢字（精し の 精）を、かな＋その字の読みで1つの漢語に読めるなら
    (始め, 終わり, 漢語)。候補が1つに決まらない（使われやすさが並ぶ）なら None（紫のまま）。"""
    try:
        import kanji_onkun
        import last_keystroke as LK
        import kana_lattice_place as KLP
        from ime_reconvert import _freq
    except Exception:
        return None
    t = toks[k]
    if k + 1 >= len(toks) or toks[k + 1].start != t.end:
        return None
    u = toks[k + 1]
    run = ''
    for c in u.surface:
        if not KLP._kanji(c):
            break
        run += c
    if len(run) != 1:
        return None
    wf = _freq() or {}
    seen = {}
    for r in dict.fromkeys(kanji_onkun.readings_of(run) or []):
        try:
            for f in (LK._kanji_choices(t.surface + r, store, dict_index) or [])[:6]:
                if f and all(KLP._kanji(c) for c in f) and len(f) == 2 and f not in seen:
                    seen[f] = wf.get(f)
        except Exception:
            continue
    ranked = sorted((v, f) for f, v in seen.items() if v is not None)
    if not ranked:
        return None
    if len(ranked) >= 2 and ranked[1][0] - ranked[0][0] < KANGO_JOIN_GAP:
        return None
    return (t.start, t.end + len(run), ranked[0][1])


def _new_bad_pair(before, after):
    """after に、before に無い文の形の続かない組（_bad_pair）ができたか。"""
    try:
        import morphology
        tb = list(morphology.tokenize(before))
        ta = list(morphology.tokenize(after))
    except Exception:
        return False
    old = {(x.surface, y.surface) for x, y in zip(tb, tb[1:]) if x.end == y.start and _bad_pair(x, y)}
    return any(x.end == y.start and _bad_pair(x, y) and (x.surface, y.surface) not in old for x, y in zip(ta, ta[1:]))


def _unknown_kana_over(done, j1, j2, line):
    """done[j1:j2] に掛かる、辞書に無いかなだけの並び（2字以上・元の行に無い形）があるか（引き続き→ぎきつづき）。"""
    try:
        import morphology
        T = morphology._TOKENIZER
        if T is None:
            return False
        at = 0
        for t in T.tokenize(done):
            sf = t.surface
            a, b = at, at + len(sf)
            at = b
            if b <= j1 or j2 <= a or t.node_type != 'UNKNOWN' or len(sf) < 2:
                continue
            k = ''.join(c for c in sf if 'ぁ' <= c <= 'ゖ')
            if len(k) >= 2 and k not in line:
                return True
        return False
    except Exception:
        return False


def _fix_kango_left_kana(line, result, store, dict_index):
    """漢字で書かれていた所（IME で変換した所）を直して、漢語の名詞をかなのまま置いた所（台風ねっきょうで・
    日程をちょう精して）は、変換した文の中では漢字で書くはずの語がかなで残る不自然な形なので、直しを採らず紫。
    かなの所の直しは、置いたかなの漢語のすぐ隣が漢字の名詞のとき（ちょう｜精・影木｜きょう）だけ。和語（もと・のち）は見ない。CN_FIX_KANGO_KANA=0"""
    import os
    if os.environ.get('CN_FIX_KANGO_KANA') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        import morphology
        import kana_keep
        import last_keystroke as LK
        import kana_lattice_place as KLP
        toks = list(morphology.tokenize(done))
    except Exception:
        return result
    kj = KLP._kanji
    ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    bad = []
    for o in ops:
        tag, i1, i2, j1, j2 = o
        if tag not in ('replace', 'insert') and not (tag == 'delete' and os.environ.get('CN_FIX_KANGO_DELETE') != '0'):
            continue
        was_kanji = any(kj(c) for c in line[i1:i2])
        if was_kanji and os.environ.get('CN_FIX_UNKNOWN_KANA') != '0' and _unknown_kana_over(done, j1, j2, line):
            bad.extend(p for p in ops if p[0] != 'equal' and p[3] <= j2 + 1 and j1 - 1 <= p[4])
            continue
        for k, t in enumerate(toks):
            if t.end <= j1 or j2 <= t.start or t.pos != '名詞' or len(t.surface) < 2:
                continue
            if not all('ぁ' <= c <= 'ゖ' for c in t.surface):
                continue
            # 形式名詞（こと・もの・ところ: 解析の 名詞,非自立）はかなで書くのが普通の語で、漢語の取り残しではない
            # （2026-11-08 手分けA: 伝え二言で → 伝えたことで の こと を 古都 の取り残しと見ていた）。CN_FIX_KANGO_FORMAL=0 で前のまま
            if (t.pos_sub or '').startswith('非自立') and os.environ.get('CN_FIX_KANGO_FORMAL') != '0':
                continue
            if not was_kanji:
                # かなの所の直しは、置いたかなの漢語のすぐ隣が漢字1字の名詞のときだけ（ちょう｜精・影木｜きょう:
                # 1つの漢語の半分だけが漢字になった形）
                nb = [u for u in (toks[k - 1] if k else None, toks[k + 1] if k + 1 < len(toks) else None)
                      if u is not None and (u.end == t.start or u.start == t.end)]
                # する名詞をかなのまま する に続けた形（予約を ぜんく しました）も、漢字の行の中ならかなで残る形
                suru = (os.environ.get('CN_FIX_KANGO_SURU') != '0' and (t.pos_sub or '').startswith('サ変接続')
                        and k + 1 < len(toks) and toks[k + 1].start == t.end and toks[k + 1].pos == '動詞'
                        and toks[k + 1].base_form == 'する' and sum(1 for c in done if kj(c)) >= 2)
                if not suru and not any(u.pos in ('名詞', '形容詞', '接頭詞') and u.surface[-1:] and kj(u.surface[-1] if u.end == t.start else u.surface[0])
                           and len([c for c in u.surface if kj(c)]) >= 1 for u in nb):
                    continue
            try:
                allf = LK._kanji_choices(t.surface, store, dict_index) or []
                faces = allf[:3]
                if os.environ.get('CN_FIX_KANGO_NOUN_FACE') != '0':
                    # 名詞として置いた語なので、送りがなの付く動詞の形（咳き・堰き）を除いた先頭3つも見る（せき→席）
                    faces = faces + [f for f in allf if all(kj(c) for c in f)][:3]
            except Exception:
                faces = []
            if any(kana_keep.is_kango(f, t.surface) for f in faces if f != t.surface):
                if not was_kanji and os.environ.get('CN_FIX_KANGO_JOIN') != '0':
                    joined = _kango_join(done, toks, k, store, dict_index)
                    if joined is not None:
                        a2, b2, face = joined
                        new = done[:a2] + face + done[b2:]
                        if not _new_bad_pair(done, new):
                            out = dict(result)
                            ops2 = [q for q in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if q[0] != 'equal']
                            out.update({'corrected': new, 'changed': True, 'spans': [[q[3], q[4]] for q in ops2],
                                        'original_spans': [[q[1], q[2]] for q in ops2],
                                        'details': [d for d in (result.get('details') or []) if len(d) > 1 and d[1] and d[1] in new]
                                        + [[done[a2:b2], face, 'かな入力']]})
                            return out
                # その語に掛かる直しは全部戻す（1つだけ戻すと ょう精 のような半端な形が残る）
                bad.extend(p for p in ops if p[0] != 'equal' and p[3] <= t.end and t.start <= p[4])
                break
    if not bad:
        return result
    return _revert_ops_purple(line, result, ops, bad, '漢字で書くはずの語がかなで残るので、直し先を決められない')


RARE_OUTSIDE_RANK = 600   # 常用漢字表の外の字の語は、語の使われやすさの順位がこれより後ろ（か載っていない）なら珍しい


def _fix_kanji_by_odd(line, result):
    """かなを漢字1字にした直しが紫の所にすぐ続くなら戻して紫（さんびょう→さん病）。その字の読みは
    紫の語の一部かもしれず、1字だけ漢字にすると半分だけの語になる。CN_FIX_KANJI_BY_ODD=0"""
    import os
    if os.environ.get('CN_FIX_KANJI_BY_ODD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    odd = [tuple(sp[:2]) for sp in (result.get('odd_spans') or ())]
    if done == line or not odd:
        return result
    try:
        import kana_lattice_place as KLP
    except Exception:
        return result
    ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    hira = lambda c: 'ぁ' <= c <= 'ゖ'
    bad = []
    for o in ops:
        tag, i1, i2, j1, j2 = o
        rep = done[j1:j2]
        if tag != 'replace' or len(rep) != 1 or not KLP._kanji(rep) or not all(hira(c) for c in line[i1:i2]):
            continue
        if any(b == j1 and a < b and all(hira(c) for c in done[a:b]) for a, b in odd) or \
                any(a == j2 and a < b and all(hira(c) for c in done[a:b]) for a, b in odd):
            bad.append(o)
    if not bad:
        return result
    return _revert_ops_purple(line, result, ops, bad, '紫の語に続く1字だけを漢字にすると語が半分になるので、直し先を決められない')


def _fix_rare_outside_kanji(line, result):
    """直して置いた語が、常用漢字表の外の字を含み（元の行に無い字）、しかも使われにくい語（爛れ ますか: 多田家ますか
    →いただけますか のつもり）なら、直しを採らず紫。嬉しい・綺麗・嘘 のように よく使う語は残す。CN_FIX_RARE_OUTSIDE=0"""
    import os
    if os.environ.get('CN_FIX_RARE_OUTSIDE') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        import kanji_doubt
        import morphology
        from ime_reconvert import _freq
        if not kanji_doubt.joyo():
            return result
        wf = _freq() or {}
        toks = list(morphology.tokenize(done))
    except Exception:
        return result
    ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    bad = []
    for o in ops:
        if o[0] not in ('replace', 'insert'):
            continue
        for t in toks:
            if t.end <= o[3] or o[4] <= t.start:
                continue
            new_chars = [c for c in t.surface if kanji_doubt.outside(c) and c not in line]
            if not new_chars:
                continue
            ranks = [r for r in (wf.get(t.surface), wf.get(t.base_form)) if r is not None]
            if not ranks or min(ranks) >= RARE_OUTSIDE_RANK:
                bad.extend(p for p in ops if p[0] != 'equal' and p[3] < t.end and t.start < p[4])
                break
    if not bad:
        return result
    return _revert_ops_purple(line, result, ops, bad, '珍しい字の語になるので、直し先を決められない')


def _dzi_kana_purple(line, result):
    """ぢ・づ を ち・つ にしただけで、直した所がかなのまま残る直し（とぢょう→とちょう）は、清音にしても語にならない
    ことが多い（地上 の ち・じ の取り違い）。直しは残して、そのかなの並びを紫にする（迷うなら紫）。CN_DZI_PURPLE=0 で前のまま"""
    import os
    if os.environ.get('CN_DZI_PURPLE') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line or len(done) != len(line):
        return result
    add = []
    for tag, a, b, c, d in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
        if tag != 'replace' or line[a:b] not in ('ぢ', 'づ') or done[c:d] not in ('ち', 'つ'):
            continue
        lo, hi = a, b
        while lo > 0 and 'ぁ' <= line[lo - 1] <= 'ゖ':
            lo -= 1
        while hi < len(line) and 'ぁ' <= line[hi] <= 'ゖ':
            hi += 1
        if hi - lo >= 2 and all('ぁ' <= ch <= 'ゖ' for ch in done[lo:hi]):
            add.append((lo, hi))
    if not add:
        return result
    out = dict(result)
    odd = list(result.get('odd_spans') or ())
    out['odd_spans'] = odd + [sp for sp in add if not any(x[0] <= sp[0] and sp[1] <= x[1] for x in odd)]
    return out


_ONE_KANA_COUNTERS = (('度', 'ど'), ('時', 'じ'), ('個', 'こ'))   # 読みが かな1字の助数詞
_COUNTER_NEXT = ('を', 'が', 'に', 'は', 'で', 'の', 'も', 'か', 'ま', 'ほ', 'く', '、', '。', '前', '後', '半', '以', '目', '近')
COUNTER_MARGIN = 2000


def _numeral_counter(line, result):
    """漢数字の直後の1字が、読みが1字の助数詞（度・時・個）の打ち違いに見える所（三十五**と**を・十二**゛**から・
    もう一**と**）。ど→と のような ゛ の抜け・付け違い、清音の字が抜けて ゛ だけ残った形を、助数詞の候補で
    並びの費用を比べ、1つに決まる（次の候補より COUNTER_MARGIN 以上よい）ときだけ直す。決まらなければ紫。
    数の後ろの と（三と四）を壊さないよう、と・し などのかなは、後ろが助詞・句読点・行末のとき（もう・あと の後ろは
    漢字でも）だけ見る（2026-11-06 漢数字の束）。CN_NUMERAL_COUNTER=0 で前のまま"""
    import os
    import unicodedata
    if os.environ.get('CN_NUMERAL_COUNTER') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if not any(c in _NUM_CHARS for c in done):
        return result
    try:
        import morphology
    except Exception:
        return result
    for k in range(1, len(done)):
        x = done[k]
        if done[k - 1] not in _NUM_CHARS or x in _NUM_CHARS:
            continue
        nxt = done[k + 1:k + 2]
        j = k - 1
        while j > 0 and done[j - 1] in _NUM_CHARS:
            j -= 1
        adv = done[max(0, j - 2):j] in ('もう', 'あと')
        if x == '゛':
            cands = [(f, r) for f, r in _ONE_KANA_COUNTERS if len(unicodedata.normalize('NFD', r)) > 1]
        elif 'ぁ' <= x <= 'ゖ':
            if not (nxt == '' or nxt in _COUNTER_NEXT or (adv and '一' <= nxt <= '鿿' and nxt not in _NUM_CHARS)):
                continue
            if nxt in _NUM_CHARS:
                continue
            cands = [(f, r) for f, r in _ONE_KANA_COUNTERS
                     if x == r or x == unicodedata.normalize('NFD', r)[0]]
        else:
            continue
        if not cands:
            continue
        scored = []
        for f, _r in cands:
            cand_line = done[:k] + f + done[k + 1:]
            # 助数詞のすぐ後ろが用言になる形（二時｜かめ｜て: 確かめて の打ち違い）は数の言い方にならない。採らない
            # （2026-11-06 かなの試験）。CN_COUNTER_VERB_NEXT=0
            if os.environ.get('CN_COUNTER_VERB_NEXT') != '0':
                try:
                    if any(t.start == k + len(f) and t.pos in ('動詞', '形容詞') for t in morphology.tokenize(cand_line)):
                        continue
                except Exception:
                    pass
            c = morphology.path_cost(cand_line)
            if c is not None:
                scored.append((c, f))
        if not scored:
            continue
        scored.sort()
        base = morphology.path_cost(done)
        out = dict(result)
        if (len(scored) == 1 or scored[1][0] - scored[0][0] >= COUNTER_MARGIN) and (base is None or scored[0][0] < base):
            new = done[:k] + scored[0][1] + done[k + 1:]
            ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
            out.update({'corrected': new, 'changed': bool(ops), 'spans': [[o[3], o[4]] for o in ops],
                        'original_spans': [[o[1], o[2]] for o in ops],
                        'details': list(result.get('details') or []) + [[x, scored[0][1], 'かな入力']]})
            if len(new) == len(line):
                out['odd_spans'] = [sp for sp in (result.get('odd_spans') or ()) if not (sp[0] <= k < sp[1])]
        elif len(done) == len(line):
            out['odd_spans'] = list(result.get('odd_spans') or ()) + [(j, k + 1)]
        return out
    return result


def _numerals_in_words(line, i1, i2):
    """line[i1:i2] の漢数字がどれも、隣の漢字1字（数字・助数詞でない）とつないで表の語（二言・一言）になるか。数ではなく
    語の字なので、1字の漢数字を守る決まり（四m → よん）に当たらない（2026-11-08 手分けA: 伝え二言で → 伝えたことで）。
    CN_KEEP_NUMERALS_WORD=0 で前のまま。"""
    import os
    if os.environ.get('CN_KEEP_NUMERALS_WORD') == '0':
        return False
    pos = [p for p in range(i1, i2) if line[p] in _NUM_CHARS]
    if not pos:
        return False
    try:
        import ime_reconvert
        rank = ime_reconvert._rank
    except Exception:
        return False

    def in_word(p):
        for a in (p - 1, p + 1):
            if 0 <= a < len(line) and '一' <= line[a] <= '鿿' and line[a] not in _NUM_CHARS and line[a] not in _COUNTERS:
                pair = line[min(a, p)] + line[max(a, p)]
                if rank(pair) < 800:
                    return True
        return False
    return all(in_word(p) for p in pos)


def _keep_numerals(line, result, input_method=None):
    """漢数字の並び（三十五度・二十・二階）の中の字や、その並びにじかに接する字を抜いたり替えたりする直し
    （差十五度 → 十五度・三十g度 → 三十旅）は戻して紫にする。数は打ち違いの戻しで読みを合わせても、元の数に戻る
    とは言い切れない（2026-11-06 脱字の束6: 漢数字が崩れる型）。CN_KEEP_NUMERALS=0 で前のまま。"""
    import os
    if os.environ.get('CN_KEEP_NUMERALS') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line or not any(c in _NUM_CHARS for c in line + fixed):
        return result
    try:
        # 数として読む漢数字だけ守る: 2字以上続く並び（三十五・十二）か、助数詞が直に付く1字（二階・五度）。
        # 1字だけの漢数字（二も・三区建て: 荷物・組み立て の変換違い）は語の一部の読み違いなので直してよい（batch215）
        num = set()
        k = 0
        while k < len(line):
            if line[k] in _NUM_CHARS:
                e = k
                while e < len(line) and line[e] in _NUM_CHARS:
                    e += 1
                if e - k >= 2 or (e < len(line) and line[e] in _COUNTERS) or os.environ.get('CN_KEEP_NUMERALS_ALL') == '1':
                    num.update(range(k, e))
                k = e
            else:
                k += 1
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        parts, rev, marks = [], [], []
        for tag, i1, i2, j1, j2 in ops:
            src = line[i1:i2]
            touch = tag in ('replace', 'delete') and (
                # かなを漢数字1字に替えて、後ろにかなが続く直し（ちょっと → 四っと）は紫にとどめる（batch218）
                (tag == 'replace' and fixed[j1:j2] and all(c in _NUM_CHARS for c in fixed[j1:j2])
                 and all('ぁ' <= c <= 'ゖ' for c in src) and j2 < len(fixed) and 'ぁ' <= fixed[j2] <= 'ゖ'
                 and os.environ.get('CN_KEEP_KANA_NOT_NUMERAL') != '0')
                or any(p in num for p in range(i1, i2))
                # 1字の漢数字でも、かなだけに替える（四m → よん）、前の英字だけを消して数を残す（ｋ六建て → 六建て）直しは
                # 語の読み違いを直したことにならない。紫にとどめる（batch220）
                or (os.environ.get('CN_KEEP_NUMERALS_SINGLE') != '0' and not _numerals_in_words(line, i1, i2) and (
                    (any(c in _NUM_CHARS for c in src) and fixed[j1:j2]
                     and not any('一' <= c <= '鿿' for c in fixed[j1:j2]))
                    or (tag == 'delete' and i2 < len(line) and line[i2] in _NUM_CHARS
                        and all(c.isascii() or 'Ａ' <= c <= 'ｚ' for c in src))))
                or (i2 in num and src[-1:] not in '、。 　')
                or (i1 - 1 in num and any(c in _COUNTERS for c in src)))
            if touch and tag == 'replace':
                # 数の字が、かな入力の打ち違いで IME が数に変えた字（貸す九人: 打った かすくにん → 確認）なら守らない
                # （keyslip_window.numeral_slip・2026-11-08 手分けB。CN_NUMERAL_SLIP=0 で前のまま）
                try:
                    import keyslip_window as _K
                    if input_method == 'kana' and _K.numeral_slip(line, i1, i2, fixed[j1:j2]):
                        touch = False
                except Exception:
                    pass
            if touch:
                parts.append(src)
                rev.append(fixed[j1:j2])
                marks.append((i1, i2))
            else:
                parts.append(fixed[j1:j2])
        if not rev:
            return result
        new = ''.join(parts)
    except Exception:
        return result
    out = dict(result)
    nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                'original_spans': [[o[1], o[2]] for o in nops],
                'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and d[1] in rev)],
                'odd_spans': sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(marks))})
    return out


KEEP_LATTICE_RANK = 450   # 一般の文の表でこれ以内の漢字の語の読み（がいこく＝外国）は、ローマ字の1打違いで替えない


def _keep_lattice_word(line, result, input_method):
    """ローマ字入力で、平仮名の並びの中の、身近な漢字の語の読み（3字以上: がいこく＝外国）を、別のかなに替えた直し
    （がいこく → がいこう）は戻す。読みの格子で身近な語に読める並びは、打ったとおりの正しい読み（2026-11-06 補正担当:
    正しいかなの行 がいこくのりょうり が崩れた）。CN_KEEP_LATTICE_WORD=0 で前のまま。"""
    import os, re
    if (os.environ.get('CN_KEEP_LATTICE_WORD') == '0' or input_method != 'romaji' or not isinstance(result, dict)):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        import reading_lattice
        import ime_reconvert
        runs = [(m.start(), m.end()) for m in re.finditer('[ぁ-ゖー]+', line)]
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        parts, rev = [], []
        cache = {}
        for tag, i1, i2, j1, j2 in ops:
            src, dst = line[i1:i2], fixed[j1:j2]
            keep = False
            if (tag == 'replace' and re.fullmatch('[ぁ-ゖー]+', src) and re.fullmatch('[ぁ-ゖー]+', dst)):
                run = next(((a, b) for a, b in runs if a <= i1 and i2 <= b), None)
                if run is not None:
                    if run not in cache:
                        res = reading_lattice.best(line[run[0]:run[1]])
                        cache[run] = res.words if res and res.surface else ()
                    pos = run[0]
                    for w in cache[run]:
                        a, b = pos, pos + len(w[1])
                        pos = b
                        if (a <= i1 and i2 <= b and len(w[1]) >= 3 and w[2] in ('名詞', '動詞', '形容詞')
                                and any('一' <= c <= '鿿' for c in w[0])
                                and ime_reconvert._rank(w[0]) <= KEEP_LATTICE_RANK):
                            keep = True
            if keep:
                parts.append(src)
                rev.append((src, dst))
            else:
                parts.append(dst)
        if not rev:
            return result
        new = ''.join(parts)
    except Exception:
        return result
    out = dict(result)
    nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                'original_spans': [[o[1], o[2]] for o in nops],
                'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and tuple(d[:2]) in rev)]})
    return out


KEEP_KATA_RANK = 520   # 一般の文の表でこれ以内の片仮名の語（データ 393・サーバー 470・ミーティング 520）


def _keep_common_katakana(line, result):
    """元の行に在る身近な片仮名の語（3字以上・一般の文の表で KEEP_KATA_RANK 以内）の中だけを書き換えた直し
    （データ → デコーダ）は戻す。身近な片仮名の語は打った読みのとおりに IME が出した語で、その中の字を足したり
    替えたりすると別の語になるだけ（2026-11-06 脱字のスレッドの束5）。CN_KEEP_COMMON_KATA=0 で前のまま。"""
    import os
    if os.environ.get('CN_KEEP_COMMON_KATA') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line or not any('ァ' <= c <= 'ヺ' for c in line):
        return result
    try:
        import ime_reconvert
        from morphology import tokenize
        keep = [(t.start, t.end) for t in tokenize(line)
                if len(t.surface) >= 3 and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in t.surface)
                and ime_reconvert._rank(t.surface) <= KEEP_KATA_RANK]
        if not keep:
            return result
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        parts, back, rev = [], False, []
        for tag, i1, i2, j1, j2 in ops:
            inside = tag != 'equal' and any(a <= i1 and i2 <= b and (i1 > a or i2 < b or tag != 'insert')
                                            and not (tag == 'insert' and (i1 == a or i1 == b)) for a, b in keep)
            if inside:
                parts.append(line[i1:i2])
                back = True
                rev.append((line[i1:i2], fixed[j1:j2]))
            else:
                parts.append(fixed[j1:j2])
        if not back:
            return result
        new = ''.join(parts)
    except Exception:
        return result
    out = dict(result)
    nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    keep_d = [d for d in (result.get('details') or [])
              if not (len(d) > 1 and any((d[1] and d[1] in dst) or (not d[1] and d[0] and d[0] in src) for src, dst in rev))]
    out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                'original_spans': [[o[1], o[2]] for o in nops], 'details': keep_d})
    return out


def _no_rare_kanji_from_kana(line, result):
    """ひらがなで書いた語を、読みを替えずに常用漢字表の外の字を含む表記にした所（きれい → 綺麗）は、ひらがなに戻す。
    打ち違いの直しではなく書き方の好みで、表の外の字はふつう かな で書く（2026-11-06 変換ミスの担当: 正しい文
    庭の花がきれいに咲きました を崩した）。読みの変わる直しは触らない。CN_NO_RARE_KANJI=0 で前のまま。"""
    import os
    if os.environ.get('CN_NO_RARE_KANJI') == '0' or not isinstance(result, dict):
        return result
    fixed = result.get('corrected') or line
    if fixed == line:
        return result
    try:
        import kanji_doubt
        import kana_keep
        if not kanji_doubt.joyo():
            return result
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        parts, back = [], []
        for tag, i1, i2, j1, j2 in ops:
            src, dst = line[i1:i2], fixed[j1:j2]
            if (tag == 'replace' and src and all('ぁ' <= c <= 'ゖ' for c in src)
                    and kanji_doubt.outside(dst) and kana_keep._reading(dst) == src):
                parts.append(src)
                back.append(dst)
            else:
                parts.append(dst)
        if not back:
            return result
        new = ''.join(parts)
    except Exception:
        return result
    out = dict(result)
    nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                'original_spans': [[o[1], o[2]] for o in nops],
                'details': [d for d in (result.get('details') or []) if not (len(d) > 1 and d[1] in back)]})
    return out


_HONORIFICS = ('さん', 'さま', 'くん', 'ちゃん', '様', '氏', '殿', '君', '先生')
_AFTER_HONORIFIC = frozenset('はがをにでとものへやかよねっ、。，．,.!?！？ 　\t)）」』】]〕>＞:：')
_PARTICLE_CHARS = frozenset('はがをにでとものへや')


def _name_char(ch):
    return ('ぁ' <= ch <= 'ゖ' or 'ァ' <= ch <= 'ヺ' or ch in 'ー々ヶ' or '一' <= ch <= '鿿'
            or ch.isascii() and ch.isalnum() or 'Ａ' <= ch <= 'ｚ' or '０' <= ch <= '９')


_KATA_TITLES = ('ミスター', 'ミセス', 'ミズ', 'ドクター', 'プロフェッサー', 'マダム', 'ミス')
_TITLES = ('mrs', 'mr', 'ms', 'mx', 'miss', 'dr', 'prof', 'sir', 'madam', 'mme', 'mlle', 'messrs')


def _title_name_spans(line):
    """英語の敬称（Mr.・Mrs.・Ms.・Dr.・Prof. など、全角も）の後ろの名前 [(開始, 終わり)]。
    敬称の後ろの1語と、続けて大文字で始まる語（Mr. John Smith）を名前と見る（2026-11-05 うに
    「海外のMr.Dc.も必要では」）。"""
    import unicodedata
    norm = ''.join(c if len(c) == 1 else ch
                   for ch in line for c in [unicodedata.normalize('NFKC', ch)])
    low = norm.lower()
    n = len(norm)
    out = []
    # 平仮名は助詞（Prof.佐藤の）なので名前に入れない
    word = lambda c: not ('ぁ' <= c <= 'ゖ') and (c.isalpha() or c.isdigit() or c in "-'’" or _name_char(c))
    for t in _TITLES:
        k = low.find(t)
        while k != -1:
            e = k + len(t)
            if (k == 0 or not norm[k - 1].isalpha()) and e < n and norm[e] in '. ':
                a = e + 1 if norm[e] == '.' else e
                while a < n and norm[a] == ' ':
                    a += 1
                b = a
                while b < n and b - a < 30 and word(norm[b]):
                    b += 1
                # 続けて大文字で始まる語（姓）も名前に入れる
                while b < n and norm[b] == ' ' and b + 1 < n and norm[b + 1].isupper():
                    c = b + 1
                    while c < n and c - a < 40 and word(norm[c]):
                        c += 1
                    b = c
                if b > a and (norm[e] == '.' or norm[a:a + 1].isupper()):
                    out.append((a, b))
            k = low.find(t, k + 1)
    # 片仮名の敬称（ミスター田中・ドクター・スミス）。ミス は「入力ミス」と紛れるので ・ か空白が続く時だけ
    kata = lambda c: 'ァ' <= c <= 'ヺ' or c == 'ー'
    for t in _KATA_TITLES:
        k = norm.find(t)
        while k != -1:
            e = k + len(t)
            if (k == 0 or not (kata(norm[k - 1]) or '一' <= norm[k - 1] <= '鿿')) and e < n \
                    and not (t == 'ミス' and norm[e] not in '・ ') and norm[e] != 'ー':
                a = e
                while a < n and norm[a] in '・ ':
                    a += 1
                b = a
                while b < n and b - a < 30 and (word(norm[b]) or (norm[b] == '・' and b + 1 < n and word(norm[b + 1]))):
                    b += 1
                if b > a:
                    out.append((a, b))
            k = norm.find(t, k + 1)
    return out


def _capital_pair_spans(line):
    """頭文字が大文字の英語の語が2つ以上続く所（John Smith・Mary Ann Lee）を姓名と見る [(開始, 終わり)]。
    英語の文の頭の語（文頭・. ! ? の後）から始まる並びは、文頭の大文字と紛れるので2語目から数える
    （2026-11-05 うに「アルファベットだと姓名でそれぞれ頭文字が大文字になる」）。"""
    import re
    import unicodedata
    norm = ''.join(c if len(c) == 1 else ch
                   for ch in line for c in [unicodedata.normalize('NFKC', ch)])
    out = []
    for m in re.finditer(r"[A-Z][a-z][A-Za-z'’-]*(?: [A-Z][a-z][A-Za-z'’-]*)+", norm):
        a, b = m.start(), m.end()
        if a > 0 and (norm[a - 1].isalnum() or norm[a - 1] in "'’-"):
            continue
        before = norm[:a].rstrip(' ')
        if not before or before[-1] in '.!?。！？':
            # 文頭の大文字は名前と限らない: 2語目からが2語以上の時だけ
            sp = norm.find(' ', a)
            if norm[sp + 1:b].count(' ') < 1:
                continue
            a = sp + 1
        out.append((a, b))
    return out


def _name_spans(line):
    """人の名前と見る所 [(開始, 終わり)]: 敬称（さん・様・先生 など）のすぐ前の語と、@・＠ の後ろの語。
    名前は辞書に無い字の並びが普通なので、打ち違いとして直したり紫にしたりしない（2026-11-05 うに
    「さん付けの前の名前が補正されている」「名前の前に引用（>・＞）が来る文」「@ の後ろに名前」）。"""
    out = []
    n = len(line)
    for hon in _HONORIFICS:
        k = line.find(hon)
        while k != -1:
            e = k + len(hon)
            nxt = line[e:e + 1]
            ok_after = (not nxt or nxt in _AFTER_HONORIFIC or not ('ぁ' <= nxt <= 'ゖ')
                        or line[e:e + 2] in ('から', 'まで', 'より', 'たち', 'だけ', 'です', 'でし', 'だっ', 'じゃ'))
            # ちゃんと・くんれん・さんぽ のような語の頭は敬称ではない
            if hon in ('ちゃん', 'くん') and nxt in ('と', 'れ', 'す', 'ぽ'):
                ok_after = False
            if ok_after and k > 0:
                a = k
                while a > 0 and k - a < 10 and _name_char(line[a - 1]):
                    ch = line[a - 1]
                    # かなの名前の左の助詞（明日は｜ゆかり）は名前に入れない: 助詞の左が漢字・片仮名なら止める
                    if ch in _PARTICLE_CHARS and a - 1 > 0 and not ('ぁ' <= line[a - 2] <= 'ゖ'):
                        break
                    a -= 1
                if a < k:
                    out.append((a, k))
            k = line.find(hon, k + 1)
    out.extend(_title_name_spans(line))
    out.extend(_capital_pair_spans(line))
    for i, ch in enumerate(line):
        if ch in '@＠':
            # 英字・数字・記号に続く半角の @ は名前の印ではない（d).et@ss@gjr はかな配列のまま打った 書類が届きます の
            # 打鍵。@ は ゛ のキー・2026-11-07 tests_jis_autofix_gui）。行頭・空白・かな漢字の後の @ だけ。CN_AT_AFTER_ASCII=0
            if (ch == '@' and i > 0 and line[i - 1].isascii() and not line[i - 1].isspace()
                    and __import__('os').environ.get('CN_AT_AFTER_ASCII') != '0'):
                continue
            e = i + 1
            while e < n and e - i <= 30 and (_name_char(line[e]) or line[e] in '_-.') \
                    and not any(line.startswith(h, e) for h in _HONORIFICS):
                e += 1
            if e > i + 1:
                out.append((i + 1, e))
    return sorted(set(out))


def _keep_names(line, result):
    """名前と見る所に掛かる直しは元の字に戻し、その所の紫は外す。切り替え CN_KEEP_NAMES=0。"""
    import os
    if os.environ.get('CN_KEEP_NAMES') == '0' or not isinstance(result, dict):
        return result
    names = _name_spans(line)
    if not names:
        return result
    hit = lambda a, b: any(x < max(b, a + 1) and a < y for x, y in names)
    fixed = result.get('corrected') or line
    out = dict(result)
    changed = False
    if fixed != line:
        ops = difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes()
        if any(tag != 'equal' and hit(i1, i2) for tag, i1, i2, j1, j2 in ops):
            parts = [line[i1:i2] if (tag != 'equal' and hit(i1, i2)) else fixed[j1:j2]
                     for tag, i1, i2, j1, j2 in ops]
            new = ''.join(parts)
            nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
            kept = {fixed[j1:j2] for tag, i1, i2, j1, j2 in ops if tag != 'equal' and hit(i1, i2)}
            out.update({'corrected': new, 'changed': bool(nops),
                        'spans': [[o[3], o[4]] for o in nops], 'original_spans': [[o[1], o[2]] for o in nops],
                        'details': [d for d in (result.get('details') or [])
                                    if not (len(d) > 1 and isinstance(d[1], str) and any(k and k in d[1] for k in kept))]})
            changed = True
    for key in ('odd_spans', 'unsure_spans', 'face_doubt_spans'):
        if result.get(key):
            keep = [sp for sp in result[key] if not (names and any(x <= sp[0] and sp[1] <= y for x, y in names))]
            if len(keep) != len(result[key]):
                out[key] = keep
                changed = True
    if result.get('odd_reasons'):
        keep = [r for r in result['odd_reasons'] if not any(x <= r[0] and r[1] <= y for x, y in names)]
        if len(keep) != len(result['odd_reasons']):
            out['odd_reasons'] = keep
            changed = True
    if changed and os.environ.get('CN_KEEP_NAMES_BAD_KANA') != '0':
        # 名前の所でも、かなとして読めない並び（おゃ: 前の字に付かない小書き・付く先の無い ゛゜）は紫を残す。直しは
        # しない（2026-11-06 かな入力のスレッド: おゃく様 が 奥様 に直った後、名前の守りで紫まで消えていた）
        try:
            import kana_rules
            add = []
            for x, y in names:
                for k, kind in kana_rules.bad_spots(line[x:y]):
                    if kind in ('続き', '濁点'):
                        add.append((x + max(0, k - 1), x + k + 1))
            if add:
                cur = [tuple(sp[:2]) for sp in (out.get('odd_spans') or ())]
                out['odd_spans'] = sorted(set(cur) | set(add))
        except Exception:
            pass
    return out if changed else result


def _drop_mixed_katakana_marks(line, result):
    """混ぜ書きの片仮名の名詞（スくりーん・シャつ）の中だけに付いた紫は外す（書いたままの語・2026-11-03
    tests_mixed_nominal_argument。PC では段の後ろの方で ー に紫が付いていた）。名詞を超える紫は残す。"""
    import os
    if os.environ.get('CN_MIXED_KATA_MARKS') == '0' or not isinstance(result, dict) or not result.get('odd_spans'):
        return result
    try:
        import broken_shape as _bs
        mixed = _bs.mixed_katakana_spans(line)
    except Exception:
        return result
    if not mixed:
        return result
    inside = lambda o: any(s <= o[0] and o[1] <= e for s, e in mixed)
    odd = [o for o in result['odd_spans'] if not inside(o)]
    if len(odd) == len(result['odd_spans']):
        return result
    out = dict(result)
    out['odd_spans'] = odd
    out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ()) if not inside(r)]
    return out


def _after_stroke_repair(line, base, out, again):
    """
    打鍵の記録の戻し（巻き込み・中身のないシフト）が行を直したら、直した行をもう一度ほかの段に通す。戻しの答えは
    その文節だけで、同じ行の別の打ち違い（前半と後半に1つずつ）が直らず紫も消えていた（紹介例スレッドの2か所の組:
    176組で文全体が直ったのは1組・2026-11-02）。2度目の答えは、戻した所に掛からない直しと紫だけ採る。
    """
    import os, difflib
    if (os.environ.get('CN_STROKE_AGAIN') == '0' or not isinstance(out, dict) or out is base
            or not out.get('changed')):
        return out
    got = out.get('corrected') or line
    if got == line:
        return out
    ops = difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes()
    reg_g = [(j1, j2) for tag, i1, i2, j1, j2 in ops if tag != 'equal']
    reg_l = [(i1, i2) for tag, i1, i2, j1, j2 in ops if tag != 'equal']
    def to_line(a, b):
        for tag, i1, i2, j1, j2 in ops:
            if tag == 'equal' and j1 <= a and b <= j2:
                return (a - j1 + i1, b - j1 + i1)
        return None
    near = lambda a, b, regs: any(s - 1 < b and a < e + 1 for s, e in regs)
    # 元の行の紫のうち、戻した所の外のもの（読みの記録ありで見た紫）
    odd = [tuple(o[:2]) for o in (base.get('odd_spans') or ()) if not near(o[0], o[1], reg_l)]
    reasons = [tuple(r[:3]) for r in (base.get('odd_reasons') or ()) if not near(r[0], r[1], reg_l)]
    # 打鍵の間隔で1字減らしたが、減らした形にも紫が残る文節（keystroke_doubt の fix_odd）は紫を付け直す
    for a_, b_ in out.get('_stroke_odd') or ():
        if not any(x[0] < b_ and a_ < x[1] for x in odd):
            odd.append((a_, b_))
            reasons.append((a_, b_, '打鍵の間隔で1字減らした後も残る打ち違い'))
    try:
        second = again(got)
    except Exception:
        second = None
    final = got
    if isinstance(second, dict):
        sec = second.get('corrected') or got
        sops = difflib.SequenceMatcher(None, got, sec, autojunk=False).get_opcodes()
        if sec != got and not any(near(j1, max(j2, j1 + 1), reg_g) for tag, j1, j2, k1, k2 in sops if tag != 'equal'):
            final = sec
        if final == got:
            for o in second.get('odd_spans') or ():
                if near(o[0], o[1], reg_g):
                    continue
                m = to_line(o[0], o[1])
                if m and not any(x[0] < m[1] and m[0] < x[1] for x in odd):
                    odd.append(m)
                    reasons.append((m[0], m[1], '打鍵の記録で直した後も残る打ち違い'))
        else:
            # 2度目で直した所の紫は落とす（直した行の上の紫は、元の行の位置に写せる所だけ）
            fops = difflib.SequenceMatcher(None, line, final, autojunk=False).get_opcodes()
            fixed_l = [(i1, i2) for tag, i1, i2, j1, j2 in fops if tag != 'equal']
            odd = [o for o in odd if not near(o[0], o[1], fixed_l)]
            reasons = [r for r in reasons if not near(r[0], r[1], fixed_l)]
    # 直した後の行にまだ残る英字（かな・漢字の間のローマ字の打ち残し: のｋで・ｗ電気）は紫。巻き込みの戻しは1つの
    # 文節しか見ないので、別の所の英字が印なしで残っていた（紹介例スレッドの2か所の組）
    try:
        fops2 = difflib.SequenceMatcher(None, line, final, autojunk=False).get_opcodes()
        jp = lambda ch: ('ぁ' <= ch <= 'ヶ' or '一' <= ch <= '鿿' or ch in 'ー々')
        latin = lambda ch: ch.isascii() and ch.isalpha() or 'ａ' <= ch <= 'ｚ' or 'Ａ' <= ch <= 'Ｚ'
        for j, ch in enumerate(final):
            if not latin(ch) or not (any(jp(c) for c in final[max(0, j - 1):j]) or any(jp(c) for c in final[j + 1:j + 2])):
                continue
            m = None
            for tag, i1, i2, j1, j2 in fops2:
                if tag == 'equal' and j1 <= j < j2:
                    m = (j - j1 + i1, j - j1 + i1 + 1)
            if m and not any(x[0] < m[1] and m[0] < x[1] for x in odd):
                odd.append(m)
                reasons.append((m[0], m[1], f'「{line[m[0]:m[1]]}」はかなの中に残った英字です'))
    except Exception:
        pass
    if final == got and odd == [] and not (base.get('odd_spans')):
        return out
    res = dict(out)
    res.pop('_stroke_odd', None)
    if final != got:
        fops = difflib.SequenceMatcher(None, line, final, autojunk=False).get_opcodes()
        det = []
        for tag, i1, i2, j1, j2 in fops:
            if tag == 'equal':
                continue
            why = '打鍵の間隔' if near(i1, max(i2, i1 + 1), reg_l) else '打ち違い'
            det.append([line[i1:i2], final[j1:j2], why])
        res.update({'corrected': final, 'changed': True, 'details': det,
                    'spans': [[j1, j2] for tag, i1, i2, j1, j2 in fops if tag != 'equal'],
                    'original_spans': [[i1, i2] for tag, i1, i2, j1, j2 in fops if tag != 'equal']})
    res['odd_spans'] = sorted(odd)
    res['odd_reasons'] = reasons
    return res


def _made_word_check(line, result, decisions, store=None, dict_index=None):
    """前の段がかなを漢字の語に直してできた形が通らない所（知覚・認識の動きの名詞＋での）は、直しを採らず紫
    （made_word_check・2026-11-01）。"""
    try:
        import made_word_check
        return made_word_check.repair_line(line, result, corrector._decided_spans(line, decisions), store, dict_index)
    except Exception:
        return result


def _wago_verb_kanji(line, result):
    """かなだけの行の和語の動詞を漢字に置く（wago_verb・うに 2026-11-09 06:30Z カード「動詞は漢字」）。
    切り替え CN_WAGO_VERB_KANJI=0。"""
    try:
        import wago_verb
        return wago_verb.repair_line(line, result)
    except Exception:
        return result


def _kana_keep(line, result, decisions):
    """かなで書いた和語（おもちゃ・ちいさい・むすめ）を、読みをそのまま漢字に変えただけの所は元のかなに戻す。
    漢語（でんわ・しょくじ）は漢字のまま（kana_keep・2026-11-01）。"""
    try:
        import kana_keep
        return kana_keep.repair_line(line, result, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _predicate_slip(line, result, run, store, dict_index, context_vec, decisions, input_method):
    """述語の打ち違いが IME で辞書の語の並び（去り＋かかる・意味の無い名詞の並び＋する）に変換された所を、1語の述語に戻す
    （predicate_slip・2026-11-01）。決め手が無ければ紫。"""
    try:
        import predicate_slip
        out = predicate_slip.repair_line(line, result, run, store, dict_index, context_vec,
                                         corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result
    return _slip_reading_shrink_guard(result, out)


def _slip_reading_shrink_guard(result, out):
    """述語の戻しで、替えた所の読みが2字以上縮む（泣きはじめた→始めた: なきはじめ→はじめ）なら採らない。打ち違いの
    戻しは読みを1打ぶんしか変えない（2026-11-07 例文 Tatoeba の正しい文）。CN_SLIP_SHRINK_GUARD=0 で前のまま。"""
    import os
    if os.environ.get('CN_SLIP_SHRINK_GUARD') == '0' or not isinstance(out, dict) or out is result:
        return out
    before = (result.get('corrected') if isinstance(result, dict) else None) or ''
    after = out.get('corrected') or ''
    if not before or before == after:
        return out
    try:
        from morphology import tokenize
        kt = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
        def rd(t):
            return ''.join((x.reading if getattr(x, 'has_reading', True) and x.reading else x.surface).translate(kt)
                           for x in tokenize(t))
        # 語の切れ端の読みは当てにならない（始 を はじめ と読む）ので、行まるごとの読みの長さで比べる
        if len(rd(before)) - len(rd(after)) >= 2:
            return result
    except Exception:
        return out
    return out


ODD_RESPELL_SEC = 8.0   # 紫の所の読み直し1回に使う秒の上限。超えたらその行は読み直さない（前の答えのまま）


class _RespellTimeout(BaseException):
    """odd_respell の中の except Exception で飲まれないよう BaseException から。"""


def _deadline_run(run, sec=None):
    """run（行の補正し直し）を、始めてから sec 秒を過ぎたら _RespellTimeout を投げる形に包む。
    長い行（1行に何文も続く）で紫の所の読み直しが何十秒も終わらなかった（2026-11-05 挙動関連担当の測り）ので、
    途中まで見た候補で決めず、その行は読み直さない。切り替え CN_ODD_RESPELL_SEC（0 で上限なし）。"""
    import os
    import time as _time
    try:
        sec = float(os.environ.get('CN_ODD_RESPELL_SEC', sec if sec is not None else ODD_RESPELL_SEC))
    except ValueError:
        sec = ODD_RESPELL_SEC
    if sec <= 0:
        return run
    end = _time.monotonic() + sec

    def wrapped(*a, **k):
        if _time.monotonic() > end:
            raise _RespellTimeout()
        return run(*a, **k)
    return wrapped


RESPELL_COMMON = 450   # 紫の所の読み直しで消してよくない身近な語（wordfreq の段がこれ以下）


def _rarer_word_respell(line, result, out):
    """紫の所の読み直しが、元の行の身近な2字以上の名詞（ご覧）を、それより身近でない語（五輪）に替えるなら採らない。
    打ち違いの直しは、IME が出した珍しい字を身近な語に戻すもので、身近な語を珍しい語へ替える根拠は無い（2026-11-08
    補正担当の正しい文の試し: 字をご覧 → 字を五輪）。CN_RESPELL_RARER=0 で前のまま。"""
    import os
    if os.environ.get('CN_RESPELL_RARER') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        from morphology import tokenize
        import ime_reconvert as R
        bt, ft = list(tokenize(before)), list(tokenize(fixed))
        ops = difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes()
    except Exception:
        return False
    kan = lambda w: any('一' <= c <= '鿿' for c in w)
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            continue
        old = [t for t in bt if t.start < max(i2, i1 + 1) and i1 < t.end]
        new = [t for t in ft if t.start < max(j2, j1 + 1) and j1 < t.end]
        new_face = fixed[new[0].start:new[-1].end] if new else ''
        for t in old:
            if (len(t.surface) >= 2 and kan(t.surface) and t.has_reading and t.surface not in new_face
                    and t.pos == '名詞'
                    and R._rank(t.surface) <= RESPELL_COMMON):
                cont = [u for u in new if kan(u.surface) and u.pos not in ('助詞', '助動詞', '記号')]
                if cont and min(R._rank(u.surface) for u in cont) >= R._rank(t.surface):
                    return True
    return False


def _verb_copula_count(text):
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return 0
    n = 0
    for a, b in zip(toks, toks[1:]):
        if (a.pos in ('動詞', '形容詞') and (getattr(a, 'infl_form', '') or '') == '基本形' and b.start == a.end
                and b.pos == '助動詞' and b.surface in ('で', 'だ')):
            n += 1
    return n


def _verb_copula_made(line, result, out):
    """紫の所の読み直しが、動詞・形容詞の言い切りのすぐ後ろに断定の で・だ を置く形（肥沃である → 開くである）を
    新しく作るなら真（文法で続かない）。CN_RESPELL_VERB_COPULA=0 で前のまま（いつも偽）。2026-11-09 補正担当の
    正しい文の試し。"""
    import os
    if os.environ.get('CN_RESPELL_VERB_COPULA') == '0' or not isinstance(out, dict) or out is result:
        return False
    new = out.get('corrected') or line
    old = (result.get('corrected') if isinstance(result, dict) else None) or line
    if new == old:
        return False
    return _verb_copula_count(new) > _verb_copula_count(old)


def _odd_respell(line, result, run, store, dict_index, context_vec, decisions, input_method):
    """紫の所の読みに一般の打ち違いの戻しを当て、行がはっきり自然になる形が1つなら直す（odd_respell・2026-11-01）。"""
    try:
        import odd_respell
        out = odd_respell.repair_line(line, result, _deadline_run(run), store, dict_index, context_vec,
                                      corrector._decided_spans(line, decisions), input_method)
    except (Exception, _RespellTimeout):
        return result
    if _impossible_after_fix(line, result, out) or _far_kana_respell(line, result, out, input_method) \
            or _dropped_vowel_letter(line, result, out, input_method):
        return result
    out = _keep_kanji_face(line, result, _respell_ime_face(line, result, out))
    if _verb_copula_made(line, result, out):
        return result
    # 入口の直しを「読める形を別の読める形に替える」として戻した行（賢くはない → 賢くしない を戻して紫）を、紫の所の
    # 読み直しで同じ直しに戻さない（2026-11-08 補正担当の正しい文の試し）。CN_RESPELL_KEEP_EXPLAINED=0 で前のまま
    if _rarer_word_respell(line, result, out):
        return result
    # 入口の直しを戻した行（賢くはない → 賢くしない を戻して紫）を、紫の所の読み直しが同じ直しに戻すのは止めない:
    # 打ち違いの行（つもりでか → です）では正しく直る。CN_RESPELL_KEEP_EXPLAINED=1 で止める（試し）
    rej = result.get('_explained_rejected') if isinstance(result, dict) else None
    if (rej and isinstance(out, dict) and out.get('corrected') == rej
            and __import__('os').environ.get('CN_RESPELL_KEEP_EXPLAINED') == '1'):
        return result
    if _between_lone_kanji(line, result, out) or _particle_after_verb_noun(line, result, out) \
            or _drops_common_kanji(line, result, out) or _verb_stem_reread(line, result, out) \
            or _same_reading_rival_noun(line, result, out) or _particle_split_respell(line, result, out) \
                or _unrelated_kana_respell(line, result, out) or _respell_real_kana_word(line, result, out, store, dict_index):
        return result
    if _swap_rival_respell(line, result, out):
        # 入れ替えの形が読み直しよりはっきり軽ければ、読み直し（手を洗ったらか: 文にならない）ではなく入れ替えで直す
        # （うに 11-06 12:51Z「手を洗ったらか とは、文になっていない」）。並ぶだけなら紫のまま。CN_RESPELL_SWAP_TAKE=0
        return _swap_take(line, result, out)
    got = _particle_for_letter(line, result, out)
    if got is out:
        got = _letter_vowel_choice(line, result, out, store, dict_index)
    if got is out:
        got = _letter_vowel_rival(line, result, out, store, dict_index)
    return got


LETTER_VOWEL_MARGIN = 1000


def _ends_in_particle(text):
    """行が（句読点・空白を除いて）格助詞・係助詞・接続助詞で終わるか（担当で・資料を）。終助詞（よ・ね・か）は除く。"""
    try:
        import morphology
        t = text.rstrip(' 　\t。、．，.!?！？')
        toks = list(morphology.tokenize(t))
        if not toks:
            return False
        x = toks[-1]
        return x.pos == '助詞' and not (x.pos_sub or '').startswith(('終助詞', '副助詞／並立助詞／終助詞'))
    except Exception:
        return False


def _letter_vowel_rival(line, result, out, store, dict_index):
    """紫の所の読み直しが、ローマ字の子音の英字1字（n を除く）の残る所を別の語に読み替えた直し（ｋ利他 → 降りた・
    ｋん額 → 音楽）なら、その英字に母音を足して前後の漢字の語と読み直した形（借りた・金額）と行の費用で比べる。
    読み直しが LETTER_VOWEL_MARGIN 以上軽ければそのまま、母音を足した形が1つだけ同じだけ軽ければそれに、
    並べば紫のまま。CN_LETTER_VOWEL_RIVAL=0 で前のまま。"""
    import os
    # 既定は切（行の費用が 出場者・死刑 のような別の語を軽く見て、正しい 電車 の直しを替えた。CN_LETTER_VOWEL_RIVAL=1 で入）
    if os.environ.get('CN_LETTER_VOWEL_RIVAL') != '1' or not isinstance(out, dict) or out is result:
        return out
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return out
    try:
        import unicodedata
        from morphology import path_cost
        nf = lambda ch: unicodedata.normalize('NFKC', ch)
        ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
        if not ops:
            return out
        lo, hi = min(o[1] for o in ops), max(o[2] for o in ops)
        letters = [i for i in range(len(before)) if nf(before[i]).isascii() and nf(before[i]).isalpha()]
        inside = [i for i in letters if lo <= i < hi]
        if len(inside) != 1 or len(letters) != 1:
            return out
        i = inside[0]
        c = nf(before[i]).lower()
        if c in 'aiueon':
            return out
        base = before[:i] + before[i + 1:]
        cands = [x for x in _letter_vowel_reread(base, i, c, store, dict_index) if x[1] != fixed]
        if not cands:
            return out
        cands = sorted({t: (ct, t, k) for ct, t, k in sorted(cands, reverse=True)}.values())
        c_out = path_cost(fixed)
        if c_out is None:
            return out
        best_c, best_t, _k = cands[0]
        if c_out <= best_c - LETTER_VOWEL_MARGIN:
            return out
        if best_c <= c_out - LETTER_VOWEL_MARGIN and (len(cands) == 1 or cands[1][0] - best_c >= LETTER_VOWEL_MARGIN):
            face = best_t
        else:
            return result
    except Exception:
        return out
    new = dict(out)
    o2 = [o for o in difflib.SequenceMatcher(None, line, face, autojunk=False).get_opcodes() if o[0] != 'equal']
    new.update({'corrected': face, 'changed': bool(o2), 'spans': [[o[3], o[4]] for o in o2],
                'original_spans': [[o[1], o[2]] for o in o2],
                'details': [[line[o[1]:o[2]], face[o[3]:o[4]], '紫の所の打ち違い'] for o in o2]})
    return new


def _letter_vowel_reread(fixed, j, cons, store, dict_index):
    """英字を抜いた行 fixed の j に、子音＋母音のかなを足して、すぐ後ろか前の漢字の語と1つの読みにして漢字に戻した形
    [(費用, 行, かな)]（変身をｗ擦れ → わ＋すれ → 忘れ・変えrます → かえ＋り → 帰り・ｋん額 → き＋んがく → 金額）。
    読みの漢字の候補の1番目だけを使う。"""
    out = []
    try:
        import morphology
        import last_keystroke as LK
        from morphology import path_cost
        toks = list(morphology.tokenize(fixed))
    except Exception:
        return out
    hira = lambda r: ''.join(chr(ord(ch) - 0x60) if 'ァ' <= ch <= 'ヶ' else ch for ch in (r or ''))
    kj = lambda w: any('一' <= ch <= '鿿' for ch in w)
    right = []
    for t in toks:
        if t.start < j:
            continue
        right.append(t)
        if kj(t.surface) or len(right) >= 2:
            break
    left = [t for t in toks if t.end == j]
    for v in 'aiueo':
        k = LK._romaji_to_kana(cons + v)
        if not k:
            continue
        sides = []
        if right and right[0].start == j and kj(right[-1].surface) and all(t.has_reading for t in right):
            sides.append((j, right[-1].end, k + ''.join(hira(t.reading) for t in right), 'R'))
        if left and kj(left[0].surface) and left[0].has_reading:
            sides.append((left[0].start, j, hira(left[0].reading) + k, 'L'))
        for a, b, rd, side in sides:
            f = None
            # 読み全体で候補が無ければ、後ろの1〜2字を送りがな・助動詞として残して見る（かりた → 借り＋た）
            for n in (0, 1, 2):
                if n >= len(rd) - 1:
                    break
                head, tail = (rd, '') if n == 0 else (rd[:-n], rd[-n:])
                try:
                    faces = LK._kanji_choices(head, store, dict_index) or []
                except Exception:
                    faces = []
                if faces and kj(faces[0]):
                    f = faces[0] + tail
                    break
            if f is None:
                continue
            t2 = fixed[:a] + f + fixed[b:]
            ct = path_cost(t2)
            if ct is not None:
                out.append((ct, t2, k))
    return out


def _letter_vowel_choice(line, result, out, store=None, dict_index=None):
    """紫の所の読み直しが、ローマ字の子音の英字1字（n を除く）を抜いただけの直しなら、その子音に母音を足した5通り
    （b → ば・び・ぶ・べ・ぼ）と行の費用で比べる。母音だけが抜けた脱字（順bが → 順番が ではなく 順が にしていた）の
    跡のことが多い（2026-11-06 脱字のスレッド: 抜くだけの直しが16件とも誤り）。抜いた形が LETTER_VOWEL_MARGIN 以上
    軽ければ抜いたまま、母音を足した形が同じだけ軽ければそれに、どちらとも決まらなければ紫のまま。
    CN_LETTER_VOWEL=0 で前のまま。"""
    import os
    if os.environ.get('CN_LETTER_VOWEL') == '0' or not isinstance(out, dict) or out is result:
        return out
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return out
    try:
        import last_keystroke as LK
        from morphology import path_cost
        ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
        if len(ops) != 1 or ops[0][0] != 'delete' or ops[0][2] - ops[0][1] != 1:
            return out
        i, j = ops[0][1], ops[0][3]
        import unicodedata
        nf = lambda ch: unicodedata.normalize('NFKC', ch)    # 全角の英字（ｋ）も同じに見る
        c = nf(before[i])
        if not (c.isascii() and c.isalpha()) or c.lower() in 'aiueon':
            return out
        if (i > 0 and nf(before[i - 1]).isascii() and nf(before[i - 1]).isalpha()) or \
                (i + 1 < len(before) and nf(before[i + 1]).isascii() and nf(before[i + 1]).isalpha()):
            return out
        if _letter_near_strokes(before, i, same_only=True):
            # 前後の打鍵と同じキー（ご連絡hしました の h ＝ し の h）は巻き込みの余分な1打。抜いたまま
            return out
        c_del = path_cost(fixed)
        if c_del is None:
            return out
        cands = []
        for v in 'aiueo':
            k = LK._romaji_to_kana(c.lower() + v)
            if not k:
                continue
            t = fixed[:j] + k + fixed[j:]
            ct = path_cost(t)
            if ct is not None:
                cands.append((ct, t, k))
        if store is not None and os.environ.get('CN_LETTER_VOWEL_REREAD') != '0':
            cands += _letter_vowel_reread(fixed, j, c.lower(), store, dict_index)
        if not cands:
            return out
        cands = sorted({t: (ct, t, k) for ct, t, k in sorted(cands, reverse=True)}.values())
        best_c, best_t, best_k = cands[0]
        if os.environ.get('CN_LETTER_VOWEL_TAIL') != '0' and _ends_in_particle(fixed) and not _ends_in_particle(before):
            # 抜いた形が文の終わりを助詞で切る（担当でs → 担当で）なら、抜いた形は採らない（費用は文の切れを数えない）
            c_del = float('inf')
        if c_del <= best_c - LETTER_VOWEL_MARGIN:
            return out
        if best_c <= c_del - LETTER_VOWEL_MARGIN and (len(cands) == 1 or cands[1][0] - best_c >= LETTER_VOWEL_MARGIN):
            face = best_t
        else:
            return result
    except Exception:
        return out
    new = dict(out)
    o2 = [o for o in difflib.SequenceMatcher(None, line, face, autojunk=False).get_opcodes() if o[0] != 'equal']
    new.update({'corrected': face, 'changed': bool(o2), 'spans': [[o[3], o[4]] for o in o2],
                'original_spans': [[o[1], o[2]] for o in o2]})
    det = [list(d) for d in (out.get('details') or [])]
    if det:
        det[-1] = [before[i], best_k, det[-1][2] if len(det[-1]) > 2 else '紫の所の打ち違い']
    new['details'] = det
    return new


def _same_reading_rival_noun(line, result, out):
    """紫の所の読み直しが、漢字の語（不測）を別の読みの漢字の語（付属）に替える形で、元の語と同じ読みの身近な語（不足:
    一般の文の表で 470 以内）が在るか。同じ読みの身近な語が在る所は IME の選び違いのほうが多く、読みを替える戻しは
    決め手にならない。採らずに紫のまま（後の段が同じ読みの語を選べる・2026-11-06 変換ミスの担当: 不測 → 付属）。
    CN_RESPELL_SAME_RIVAL=0 で前のまま。"""
    import os
    if os.environ.get('CN_RESPELL_SAME_RIVAL') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        import ime_reconvert
        import reading_lattice
        from morphology import tokenize
        reading_lattice.load()
        kanji = lambda t: bool(t) and all('一' <= c <= '鿿' or c == '々' for c in t)
        hira = lambda r: ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in r)
        toks = list(tokenize(before))
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes():
            if tag != 'replace' or not kanji(fixed[j1:j2]):
                continue
            t = next((t for t in toks if t.start <= i1 and i2 <= t.end), None)
            if t is None or not kanji(t.surface) or len(t.surface) < 2 or not t.has_reading:
                continue
            r = hira(t.reading)
            u = next((u for u in tokenize(fixed) if u.start <= j1 < u.end), None)
            if u is None or (u.has_reading and hira(u.reading) == r):
                continue                     # 同じ読みの語への替え（選び違いの直し）はそのまま
            for surf, _l, _r, _c, pos in reading_lattice._table.get(r, ()):
                if surf != t.surface and kanji(surf) and ime_reconvert._rank(surf) <= 470 \
                        and ime_reconvert._rank(surf) < ime_reconvert._rank(t.surface):
                    return True
    except Exception:
        return False
    return False


# 入れ替えの形が読み直しよりこれだけ重くても並ぶと見る（行の重さの差がこの程度では決め手にならない: 受け取ったらか 20138 と
# 受け取ってから 20920）
SWAP_RIVAL_MARGIN = 1000


def _swap_rival_respell(line, result, out):
    """紫の所の読み直し（てらか → たらか）より、紫の所で隣り合うかな2字を入れ替えただけの形（てから）のほうが行として
    軽いか。打鍵の順番違いでも読めるので、読み直しは決め手にならず紫のまま（2026-11-06 打鍵順入れ替えの束5）。
    CN_RESPELL_SWAP_RIVAL=0"""
    import os
    if os.environ.get('CN_RESPELL_SWAP_RIVAL') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before or len(before) != len(line):
        return False
    try:
        import morphology
        fc = morphology.path_cost(fixed)
    except Exception:
        return False
    if fc is None:
        return False
    def hira(c):
        return 'ぁ' <= c <= 'ゖ'
    seen = set()
    hit = False
    _SWAP_BEST.v = None
    for sp in (result.get('odd_spans') or ()):
        # 紫の1字の前後2字まで（紫が入れ替えの片方だけに付く: て｜らか）
        x, y = max(0, sp[0] - 2), min(len(before), sp[1] + 2)
        for k in range(x, y - 1):
            a, b = before[k], before[k + 1]
            if a == b or not (hira(a) and hira(b)) or k in seen:
                continue
            seen.add(k)
            cand = before[:k] + b + a + before[k + 2:]
            if cand == fixed:
                continue
            try:
                cc = morphology.path_cost(cand)
            except Exception:
                continue
            if cc is not None and cc <= fc + SWAP_RIVAL_MARGIN:
                best = getattr(_SWAP_BEST, 'v', None)
                if best is None or cc < best[0]:
                    _SWAP_BEST.v = (cc, fc, cand, k)
                hit = True
    return hit


import threading as _threading
_SWAP_BEST = _threading.local()


def _swap_take(line, result, out):
    import os
    best = getattr(_SWAP_BEST, 'v', None)
    _SWAP_BEST.v = None
    if best is None or os.environ.get('CN_RESPELL_SWAP_TAKE') == '0':
        return result
    cc, fc, cand, k = best
    before = result.get('corrected') or line
    try:
        import morphology
        bc = morphology.path_cost(before)
    except Exception:
        return result
    # 読み直しよりはっきり軽く（SWAP_TAKE_GAIN）、打ったままの行よりも軽いときだけ
    if bc is None or not (cc + SWAP_TAKE_GAIN <= fc and cc < bc):
        return result
    # 入れ替えた2字が、入れ替えた行で助詞・助動詞の語（て｜から の から）の中に収まるときだけ。内容の語に入る形
    # （いつて → いてつ: 凍てつき）は行の重さが軽くても自然な文とは限らない（いってきます が正しい）
    try:
        toks = list(morphology.tokenize(cand))
    except Exception:
        return result
    if not any(t.start <= k and k + 2 <= t.end and t.pos in ('助詞', '助動詞') for t in toks):
        return result
    new = dict(result)
    ops = [o for o in difflib.SequenceMatcher(None, line, cand, autojunk=False).get_opcodes() if o[0] != 'equal']
    new.update({'corrected': cand, 'changed': True,
                'details': list(result.get('details') or []) + [[before[k:k + 2], cand[k:k + 2], '紫の所の打ち違い']],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    new['odd_spans'] = [sp for sp in (result.get('odd_spans') or ()) if sp[1] <= k - 2 or k + 4 <= sp[0]]
    return new


SWAP_TAKE_GAIN = 300


REAL_KANA_WORD_RANK = 500   # かなで打った語が、この順位より前のよく使う漢字の語に読めるなら、打ったとおりの語と見る


def _respell_real_kana_word(line, result, out, store, dict_index):
    """紫の所の読み直しが、かなで打った2字以上の所（かいぎ）を、読みの違う漢字の語（介護 かいご）に替える直しで、
    打ったかなのままでもよく使う漢字の語（会議）に読めるなら、打ち違いの証しにならない。採らずに紫のまま。
    CN_RESPELL_REAL_KANA=0"""
    import os
    if os.environ.get('CN_RESPELL_REAL_KANA') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        import last_keystroke as LK
        import kana_lattice_place as KLP
        from ime_reconvert import _freq
        wf = _freq() or {}
        ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] == 'replace']
    except Exception:
        return False
    for tag, i1, i2, j1, j2 in ops:
        a, b = before[i1:i2], fixed[j1:j2]
        if len(a) < 2 or not all('ぁ' <= c <= 'ゖ' for c in a) or not any(KLP._kanji(c) for c in b):
            continue
        if len(b) < 2 or not all(KLP._kanji(c) for c in b):
            continue
        rb = KLP._reading_of(b)
        # 打ったかなと同じ長さで1字だけ違う読みの語（かいぎ → 介護 かいご）だけを見る
        if (not rb or rb == a or len(rb) != len(a) or not all('ぁ' <= c <= 'ゖ' for c in rb)
                or sum(x != y for x, y in zip(rb, a)) != 1):
            continue
        try:
            faces = (LK._kanji_choices(a, store, dict_index) or [])[:2]
        except Exception:
            faces = []
        for f in faces:
            r = wf.get(f)
            if f != b and r is not None and r < REAL_KANA_WORD_RANK and any(KLP._kanji(c) for c in f):
                return True
    return False


def _unrelated_kana_respell(line, result, out):
    """紫の所の読み直しが、かな1字を別のかな1字に替えるだけで、その2字がキーの隣（かな・ローマ字どちらかの配列）でも
    濁点・小書きの違いでもない（新部て → 新部へ・てらか → たらか）か。打ち違いで起こらない替え方なので決め手にならない。
    採らずに紫のまま（2026-11-06 打鍵順入れ替えの束5 ほか: このかな1字の替えは誤り20件・正しい1件）。CN_RESPELL_UNRELATED_KANA=0"""
    import os, unicodedata
    if os.environ.get('CN_RESPELL_UNRELATED_KANA') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    def hira(c):
        return 'ぁ' <= c <= 'ゖ'
    small = {'っ': 'つ', 'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ', 'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お'}
    def related(a, b):
        if len(b) != 1:
            return False
        if unicodedata.normalize('NFD', a)[0] == unicodedata.normalize('NFD', b)[0] or small.get(a, a) == small.get(b, b):
            return True
        try:
            from kana_layout import nearby_candidates
            for im in ('kana', 'romaji'):
                if any(x == b for x, _d in nearby_candidates(a, max_dist=1.0, include_phonetic=False, input_method=im)):
                    return True
        except Exception:
            return True
        return False
    try:
        ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    except Exception:
        return False
    if not ops:
        return False
    for tag, i1, i2, j1, j2 in ops:
        a, b = before[i1:i2], fixed[j1:j2]
        if not (tag == 'replace' and len(a) == 1 and hira(a) and b and len(b) <= 2 and all(hira(c) for c in b)):
            return False
        if related(a, b):
            return False
    return True


def _particle_split_respell(line, result, out):
    """紫の所の読み直しが、助詞のすぐ後ろの漢字の語を、助詞（は・も・が など）から始まる形に替える
    （久しぶりに｜実科 → 久しぶりに｜は結果: に を には に割って別の語を作る）か。助詞の後ろに助詞を足す読みは
    打った読みのとおりではなく、決め手にならない。採らずに紫のまま（2026-11-06 変換ミスの担当）。CN_RESPELL_PARTICLE_SPLIT=0"""
    import os
    if os.environ.get('CN_RESPELL_PARTICLE_SPLIT') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        from morphology import tokenize
        toks = list(tokenize(before))
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes():
            if tag not in ('replace', 'insert') or not fixed[j1:j2] or fixed[j1] not in 'はもがをにでと':
                continue
            prev = next((t for t in toks if t.end == i1), None)
            if prev is not None and prev.pos == '助詞' and any('一' <= c <= '鿿' for c in before[i1:i2] + fixed[j1:j2]):
                # 直した形で、前の助詞と読み直した字が1つの語になる（も｜水戸 → もと: 巻き込みの み を抜いた）なら、
                # 助詞を割って足した形ではない。CN_RESPELL_PARTICLE_JOIN=0 で前のまま
                if os.environ.get('CN_RESPELL_PARTICLE_JOIN') != '0' and any(
                        t.start <= prev.start and t.end > j1 and t.pos != '助詞' for t in tokenize(fixed)):
                    continue
                return True
    except Exception:
        return False
    return False


def _verb_stem_reread(line, result, out):
    """紫の所の読み直しが、辞書の動詞として読める語（飼って・診に）の漢字だけを別の読みの漢字に替える（飼って → 打って）か、
    動詞の連用形と次の助詞の間にかなを足す（診に → 診るに）形か。動詞の形が整っている所は、打った読みのとおりの語を
    IME が別の漢字にした選び違いのほうが多く、読みを替える戻しは決め手にならない。採らずに紫のまま（2026-11-06
    変換ミスの担当: 同音異義の束）。CN_RESPELL_VERB_STEM=0 で前のまま。"""
    import os
    if os.environ.get('CN_RESPELL_VERB_STEM') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        from morphology import tokenize
        toks = list(tokenize(before))
        kanji = lambda t: bool(t) and all('一' <= c <= '鿿' or c == '々' for c in t)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes():
            if tag == 'replace' and kanji(before[i1:i2]) and kanji(fixed[j1:j2]):
                t = next((t for t in toks if t.start <= i1 and i2 <= t.end), None)
                if (t is not None and t.pos == '動詞' and t.has_reading and t.end > i2
                        and 'ぁ' <= before[i2] <= 'ゖ'):
                    return True
            if tag == 'insert' and all('ぁ' <= c <= 'ゖ' for c in fixed[j1:j2]):
                t = next((t for t in toks if t.end == i1), None)
                n = next((t for t in toks if t.start == i1), None)
                if (t is not None and n is not None and t.pos == '動詞' and t.has_reading
                        and n.pos == '助詞'):
                    return True
    except Exception:
        return False
    return False


def _drops_common_kanji(line, result, out):
    """紫の所の読み直しが、身近な漢字の語（何・今・人: 一般の文の表で 450 以内）を丸ごと ひらがな2字以内（助詞など）に
    替えた形か（お昼何食べる → お昼に食べる）。身近な漢字の語は IME が打った読みのとおりに出した語で、打ち違いの跡では
    ない。採らずに紫のまま（2026-11-06 変換ミスの担当: 正しい文を崩した）。CN_RESPELL_KEEP_COMMON=0 で前のまま。"""
    import os
    if os.environ.get('CN_RESPELL_KEEP_COMMON') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        import ime_reconvert
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes():
            if tag != 'replace':
                continue
            src, dst = before[i1:i2], fixed[j1:j2]
            if (src and all('一' <= c <= '鿿' or c == '々' for c in src) and ime_reconvert._rank(src) <= 450
                    and 0 < len(dst) <= 2 and all('ぁ' <= c <= 'ゖ' for c in dst)):
                return True
    except Exception:
        return False
    return False


def _particle_after_verb_noun(line, result, out):
    """紫の所の読み直しが、動詞の基本形と名詞の間の1字を助詞（格助詞・接続助詞）にした形か（するら予定 →
    するに予定・するが予定）。動詞の基本形はそのまま名詞を修飾するので、間の1字は抜く（巻き込み）のが自然で、
    助詞に替える形は採らない（紫のまま）。2026-11-06 巻き込みのスレッドの束3。CN_RESPELL_VERB_NOUN=0 で前のまま。"""
    import os
    if os.environ.get('CN_RESPELL_VERB_NOUN') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        from morphology import tokenize
        ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
        if len(ops) != 1 or ops[0][4] - ops[0][3] != 1:
            return False
        j = ops[0][3]
        toks = list(tokenize(fixed))
        k = next((n for n, t in enumerate(toks) if t.start == j and t.end == j + 1), None)
        if k is None or k == 0 or k + 1 >= len(toks):
            return False
        p, t, n = toks[k - 1], toks[k], toks[k + 1]
        return (t.pos == '助詞' and t.pos_sub.split(':')[0] in ('格助詞', '接続助詞')
                and p.pos == '動詞' and p.infl_form == '基本形' and p.end == j
                and n.pos == '名詞' and n.start == j + 1)
    except Exception:
        return False


_LETTER_PARTICLE = {'g': ('が',), 'n': ('に', 'の'), 'ん': ('に', 'の'), 'w': ('を',), 'd': ('で',), 't': ('と',),
                    'm': ('も',), 'h': ('は', 'へ'), 'k': ('か',), 'y': ('や',)}


def _particle_for_letter(line, result, out):
    """紫の所の読み直しが、名詞の後ろに1字だけ残った子音の英字か ん を抜いただけで、名詞のすぐ後ろに用言か名詞が
    来る形（時計g止まって → 時計止まって・冷蔵庫ん牛乳 → 冷蔵庫牛乳）なら、抜く前にその子音に母音を足した助詞
    （g→が・n/ん→に）と比べる。母音だけ抜けた脱字の跡で、抜くと助詞が消えて文の組み立てが崩れる。助詞の形が
    抜いた形より並びの費用で軽ければその助詞に、助詞の候補が並べば紫のまま（2026-11-06 脱字のスレッドの 1）。
    CN_LETTER_PARTICLE=0 で前のまま。"""
    import os
    if os.environ.get('CN_LETTER_PARTICLE') == '0' or not isinstance(out, dict) or out is result:
        return out
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return out
    try:
        from morphology import tokenize, path_cost
        ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
        if len(ops) != 1 or ops[0][0] != 'delete' or ops[0][2] - ops[0][1] != 1:
            return out
        i = ops[0][1]
        ch = before[i].lower()
        if ch not in _LETTER_PARTICLE or (i + 1 < len(before) and before[i + 1].isascii() and before[i + 1].isalpha()):
            return out
        if ch != 'ん' and os.environ.get('CN_DROPPED_VOWEL_ROLL') != '0' and _letter_near_strokes(before, i, same_only=True):
            # 前後の打鍵と同じか隣のキーの英字は巻き込みの余分な1打（ご連絡hしました の h）。抜くだけでよい
            return out
        j = ops[0][3]
        toks = list(tokenize(fixed))
        left = next((t for t in toks if t.end == j), None)
        right = next((t for t in toks if t.start == j), None)
        if left is None or right is None or left.pos != '名詞' or right.pos not in ('名詞', '動詞', '形容詞'):
            return out
        c_del = path_cost(fixed)
        cands = []
        for pt in _LETTER_PARTICLE[ch]:
            t = fixed[:j] + pt + fixed[j:]
            c = path_cost(t)
            if c is not None:
                cands.append((c, t, pt))
        if not cands or c_del is None:
            return out
        cands.sort()
        if len(cands) > 1 and cands[1][0] - cands[0][0] < 1000:
            return result
        if cands[0][0] >= c_del:
            return out
        face, pt = cands[0][1], cands[0][2]
    except Exception:
        return out
    new = dict(out)
    o2 = [o for o in difflib.SequenceMatcher(None, line, face, autojunk=False).get_opcodes() if o[0] != 'equal']
    new.update({'corrected': face, 'changed': bool(o2), 'spans': [[o[3], o[4]] for o in o2],
                'original_spans': [[o[1], o[2]] for o in o2]})
    det = [list(d) for d in (out.get('details') or [])]
    if det:
        det[-1] = [before[i], pt, det[-1][2] if len(det[-1]) > 2 else '紫の所の打ち違い']
    new['details'] = det
    return new


def _between_lone_kanji(line, result, out):
    """紫の所の読み直しが、1字の漢字の名詞2つに挟まれたかなだけを替えた形か（四て尾 → 四へ尾）。IME が崩した漢字を
    残したままの直しで、行は直っていない。紫のまま（2026-11-06 挙動関連担当のアプリの道の試し・脱字のスレッドの 2）。
    CN_RESPELL_LONE_KANJI=0 で前のまま。"""
    import os
    if os.environ.get('CN_RESPELL_LONE_KANJI') == '0' or not isinstance(out, dict) or out is result:
        return False
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return False
    try:
        from morphology import tokenize
        ops = [o for o in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
        if not ops:
            return False
        lo, hi = ops[0][3], ops[-1][4]
        toks = list(tokenize(fixed))

        def lone(t):
            return t is not None and t.pos == '名詞' and len(t.surface) == 1 and '一' <= t.surface <= '鿿'
        left = next((t for t in toks if t.end == lo), None)
        right = next((t for t in toks if t.start == hi), None)
        inner = [t for t in toks if lo <= t.start and t.end <= hi]
        return lone(left) and lone(right) and bool(inner) and all(all('ぁ' <= c <= 'ゖ' for c in t.surface) for t in inner)
    except Exception:
        return False


RESPELL_KANA_FAR = 3   # かな入力で、読み直しが読みをこの打鍵数以上替える直しは採らない


def _dropped_vowel_letter(line, result, out, input_method):
    """ローマ字入力で1字だけ残った子音の英字（遅れmス・申し訳ありませんg少し）が、前後に打ったキーのどれとも隣でないか。
    隣でない英字は巻き込み（会議hな の h は な の n の隣）ではなく、母音を打ち落として子音だけ残った脱字の跡なので、
    紫の所の読み直しで抜いたり別の語に置き換えたりせず、紫のまま（2026-11-06 ローマ字の試しのスレッド: 脱字の誤り30件の
    うち19件がこの形・脱字は優先が低い）。CN_RESPELL_DROPPED_VOWEL=0 で前のまま。"""
    import os, re
    if input_method != 'romaji' or os.environ.get('CN_RESPELL_DROPPED_VOWEL') == '0' or not isinstance(out, dict):
        return False
    before = (result or {}).get('corrected') or line
    after = out.get('corrected') or line
    if after == before:
        return False
    try:
        import difflib
        import keyboard_layout
        import last_keystroke as LK
        pos = keyboard_layout.letter_positions()
        ops = [o for o in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes() if o[0] != 'equal']
        if not ops:
            return False
        lo, hi = ops[0][1], ops[-1][2]

        def romaji(ch):
            if 'ァ' <= ch <= 'ヶ':
                ch = chr(ord(ch) - 0x60)
            if 'ぁ' <= ch <= 'ゖ':
                try:
                    return LK._kana_run_to_romaji(ch) or ''
                except Exception:
                    return ''
            return ''

        def romaji_wide(ch):
            if '一' <= ch <= '鿿':
                try:
                    import kana_keep
                    rd = kana_keep._reading(ch)
                    return (LK._kana_run_to_romaji(rd) or '') if rd else ''
                except Exception:
                    return ''
            return romaji(ch)

        def near(a, b):
            if a == b:
                return True
            pa, pb = pos.get(a), pos.get(b)
            return bool(pa and pb) and abs(pa[0] - pb[0]) <= 1 and abs(pa[1] - pb[1]) <= 1

        if os.environ.get('CN_RESPELL_DROPPED_DIGRAPH') != '0':
            # 母音の抜けた2字の子音（しまshた の sh・ch・ts・ky…）も、ローマ字の1かなの頭だけが残った脱字の跡
            for m in re.finditer(r'(?<![A-Za-z])(?:sh|ch|ts|[kgsztdnhbpmr]y)(?![A-Za-z])', before):
                if lo - 1 <= m.start() <= hi and not _letter_swap_resolves(before, m.start(), m.end()):
                    # 直しが打鍵の数を増やさない（非ry → 昼: hiry → hiru の y は u の隣のキーの打ち違い）なら、母音を
                    # 打ち落とした跡ではなく隣のキーの1打（うに 2026-11-10 01:39Z「母音と子音による隣接キーのタイプミス」）。
                    # CN_DROPPED_DIGRAPH_SAME_KEYS=0 で前のまま
                    if (os.environ.get('CN_DROPPED_DIGRAPH_SAME_KEYS') != '0'
                            and m.group()[-1] == 'y'
                            and not _vowel_added(before, after, m.start(), m.group())):
                        continue
                    return True
        for m in re.finditer(r'(?<![A-Za-z])[b-df-hj-mp-tv-z](?![A-Za-z])', before):
            i = m.start()
            if not (lo - 1 <= i <= hi):
                continue
            c = m.group().lower()
            sides = []
            if i > 0:
                r = romaji(before[i - 1])
                if r:
                    sides.append(r[-1])
            if i + 1 < len(before):
                r = romaji(before[i + 1])
                if r:
                    sides.append(r[0])
            if os.environ.get('CN_DROPPED_VOWEL_ROLL') != '0':
                # 前後の字の打鍵（漢字は読みのローマ字）を2打ずつ見て、同じキーか隣のキーなら巻き込みの余分な1打
                # （ご連絡hしました の h は し=shi の h と同じキー）。巻き込みは抜く直しだけ通し、母音を足して
                # かなにする直し（ご連絡へしました）は採らない（2026-11-06 ローマ字の試しのスレッド）
                wide = []
                def hep(r):
                    for a_, b_ in (('si', 'shi'), ('ti', 'chi'), ('tu', 'tsu'), ('hu', 'fu'), ('zi', 'ji'),
                                   ('sy', 'sh'), ('ty', 'ch'), ('zy', 'j')):
                        r = r.replace(a_, b_)
                    return r
                if i > 0:
                    r = romaji_wide(before[i - 1])
                    wide.extend(r[-2:])
                    wide.extend(hep(r)[-2:])
                if i + 1 < len(before):
                    r = romaji_wide(before[i + 1])
                    wide.extend(r[:2])
                    wide.extend(hep(r)[:2])
                if any(near(c, x) for x in wide):
                    if _vowel_added(before, after, i, c):
                        return True
                    continue
            if sides and not any(near(c, x) for x in sides) and not _letter_swap_resolves(before, i, i + 1):
                return True
        return False
    except Exception:
        return False


PARTIAL_SHIFT_MARGIN = 2500   # 揃えて戻した行が、1打だけ直した行よりこれだけ自然（並びの費用）なら置き換える


def _partial_shift(line, result, run, store, dict_index, context_vec, decisions, input_method):
    """かな入力の1打の置き換えの直しが、手の位置のずれ（続く2〜4打が揃って隣のキー）の1打だけを戻した途中までの直し
    なら、揃えて戻した形に置き換える（2026-11-06 隣キーの巻き込みのサンプル文: すことすわった → すこしすわった、正しくは
    少し変わった）。直した字の前か後ろの字も同じ向きの隣のキーで、その字を含む平仮名の所を odd_respell._choose_shifted
    （GAIN・MARGIN・紫が残らない）で読み直し、1打の直しの行より PARTIAL_SHIFT_MARGIN 以上自然なときだけ採る。
    決まらなければ1打の直しのまま。CN_PARTIAL_SHIFT=0（または CN_HAND_SHIFT=0）で切れる。"""
    import os
    if input_method != 'kana' or os.environ.get('CN_HAND_SHIFT') == '0' or os.environ.get('CN_PARTIAL_SHIFT') == '0' or not isinstance(result, dict):
        return result
    if os.environ.get('CN_PARTIAL_SHIFT_ROLL') != '0' and (
            any(len(d) > 2 and '打鍵の間隔' in str(d[2]) for d in (result.get('details') or ()))
            or any(len(r) > 2 and '打鍵の間隔' in str(r[2]) for r in (result.get('odd_reasons') or ()))):
        # 打鍵の記録で巻き込みの印が付いた行は、手の位置のずれとして読み直さない（それなりら → それなのに・
        # 2026-11-06 巻き込みのスレッドの束2）。CN_PARTIAL_SHIFT_ROLL=0 で前のまま
        return result
    done = result.get('corrected') or line
    if done == line or len(line) != len(done):
        return result
    diff = [i for i, (x, y) in enumerate(zip(line, done)) if x != y]
    if len(diff) != 1:
        return result
    p = diff[0]
    try:
        import odd_respell as _o, hand_shift as _hs, morphology
        at, pos = _hs._kana_table()
        x, y = _hs._SMALL.get(line[p], line[p]), _hs._SMALL.get(done[p], done[p])
        if x not in pos or y not in pos or pos[x][0] != pos[y][0] or abs(pos[x][1] - pos[y][1]) != 1:
            return result
        d = pos[y][1] - pos[x][1]
        ok = False
        for j in (p - 1, p + 1):
            if 0 <= j < len(line):
                z = _hs._SMALL.get(line[j], line[j])
                if z in pos and at.get((pos[z][0], pos[z][1] + d)) and _hs._left_hand(pos[z]) == _hs._left_hand(pos[x]):
                    ok = True
        if not ok:
            return result
        a, b = p, p + 1
        while a > 0 and _o._is_hira(line[a - 1]) and p - a < 4:
            a -= 1
        while b < len(line) and _o._is_hira(line[b]) and b - p < 5:
            b += 1
        fixed = _o._choose_shifted(line, a, b, [line[a:b]], run, store, dict_index, context_vec)
        if not fixed or fixed == done:
            return result
        c_new, c_done = morphology.path_cost(fixed), morphology.path_cost(done)
        if c_new is None or c_done is None or c_new > c_done - PARTIAL_SHIFT_MARGIN:
            return result
        if any(x0 < b and a < y0 for x0, y0 in corrector._decided_spans(line, decisions)):
            return result
    except Exception:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, fixed, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return result
    out = dict(result)
    out.update({'corrected': fixed, 'changed': True,
                'details': [[line[ops[0][1]:ops[-1][2]], fixed[ops[0][3]:ops[-1][4]], '手の位置のずれ']],
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops],
                'odd_spans': [], 'unsure_spans': [], 'odd_reasons': []})
    return out


def _letter_near_strokes(text, i, same_only=False):
    """text[i] の英字が、前後の字の打鍵（漢字は1字の読み・し=shi も si も）の2打ずつと同じキーか隣のキーか。"""
    try:
        import kana_keep
        import keyboard_layout
        import last_keystroke as LK
        pos = keyboard_layout.letter_positions()

        def rom(ch):
            if 'ァ' <= ch <= 'ヶ':
                ch = chr(ord(ch) - 0x60)
            if '一' <= ch <= '鿿':
                ch = kana_keep._reading(ch) or ''
            if not ch or not all('ぁ' <= x <= 'ゖ' for x in ch):
                return ['']
            r = LK._kana_run_to_romaji(ch) or ''
            h = r
            for a_, b_ in (('si', 'shi'), ('ti', 'chi'), ('tu', 'tsu'), ('hu', 'fu'), ('zi', 'ji'),
                           ('sy', 'sh'), ('ty', 'ch'), ('zy', 'j')):
                h = h.replace(a_, b_)
            return [r, h]
        keys = []
        if i > 0:
            for r in rom(text[i - 1]):
                keys.extend(r[-2:])
        if i + 1 < len(text):
            for r in rom(text[i + 1]):
                keys.extend(r[:2])
        c = text[i].lower()
        pc = pos.get(c)
        for k in keys:
            if k == c:
                return True
            pk = pos.get(k)
            if not same_only and pc and pk and abs(pc[0] - pk[0]) <= 1 and abs(pc[1] - pk[1]) <= 1:
                return True
    except Exception:
        return False
    return False


def _vowel_added(before, after, i, c):
    """before[i] の英字の所の直しが、打鍵の数を増やしているか（h → へ: 1打 → 2打。母音を足した直し）。
    亜m → ま のような入れ替えは打鍵の数が同じなので当たらない。漢字は1字ずつの読みで数える。"""
    import os
    try:
        import kana_keep
        import last_keystroke as LK

        def n_keys(t):
            k = 0
            for ch in t:
                if ch.isascii() and ch.isalpha():
                    k += 1
                    continue
                if 'ァ' <= ch <= 'ヶ':
                    ch = chr(ord(ch) - 0x60)
                if '一' <= ch <= '鿿':
                    # 漢字は読みのうち一番短い打ち方で数える（庫 は くら でなく こ: 冷蔵kも → 冷蔵庫 は打鍵を増やしていない。
                    # 2026-11-10 うに「ローマ字入力が通らなくなっていました」）。CN_VOWEL_ADDED_SHORT=0 で前のまま
                    rds = [kana_keep._reading(ch) or '']
                    if os.environ.get('CN_VOWEL_ADDED_SHORT') != '0':
                        try:
                            import odd_respell as _OR
                            rds += list(_OR._one_kanji_readings(ch) or ())
                        except Exception:
                            pass
                    rds = [r for r in rds if r and all('ぁ' <= x <= 'ゖ' for x in r)]
                    if rds:
                        k += min(len(LK._kana_run_to_romaji(r) or '') for r in rds)
                    continue
                if ch and all('ぁ' <= x <= 'ゖ' for x in ch):
                    k += len(LK._kana_run_to_romaji(ch) or '')
            return k
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
            if tag != 'equal' and i1 <= i < max(i2, i1 + 1):
                return n_keys(after[j1:j2]) > n_keys(before[i1:i2])
    except Exception:
        return False
    return False


def _letter_swap_resolves(text, i, j):
    """残った英字 text[i:j] を前後の字の読みのローマ字とつなぎ、隣り合う2打を1回入れ替えると英字が全部かなになるか
    （修正し亜mした: a・m → ma で しました。遅れmス はどう入れ替えても残る）。なるなら打鍵の順番違いで、母音の抜けた
    脱字ではない（2026-11-06 ローマ字の試しのスレッド: 止めた65件のうち38件が入れ替え・隣キーの正しい直し）。
    CN_DROPPED_VOWEL_SWAP=0 で見ない。"""
    import os
    if os.environ.get('CN_DROPPED_VOWEL_SWAP') == '0':
        return False
    try:
        import kana_keep
        import last_keystroke as LK

        def rom(ch):
            if not ch:
                return ''
            if 'ァ' <= ch <= 'ヶ':
                ch = chr(ord(ch) - 0x60)
            if not ('ぁ' <= ch <= 'ゖ'):
                if '一' <= ch <= '鿿':
                    ch = kana_keep._reading(ch)
                else:
                    return ''
            try:
                return LK._kana_run_to_romaji(ch) or ''
            except Exception:
                return ''
        left = rom(text[i - 1]) if i > 0 else ''
        right = rom(text[j]) if j < len(text) else ''
        w = left + text[i:j].lower() + right
        a = len(left)
        for k in range(max(0, a - 2), min(len(w) - 1, j - i + a + 1)):
            t = w[:k] + w[k + 1] + w[k] + w[k + 2:]
            if t != w and t[-1] in 'aiueon' and LK._romaji_to_kana(t) is not None:
                return True
        if j - i == 1:
            # 母音のキーの隣を打った打ち違い（犬の → 犬んp: o の隣の p）も、母音に戻すと英字が消えるなら脱字ではない
            import keyboard_layout
            pos = keyboard_layout.letter_positions()
            pc = pos.get(text[i].lower())
            for v in 'aiueo':
                pv = pos.get(v)
                if pc and pv and abs(pc[0] - pv[0]) <= 1 and abs(pc[1] - pv[1]) <= 1:
                    t = w[:a] + v + w[a + 1:]
                    if LK._romaji_to_kana(t) is not None:
                        return True
    except Exception:
        return False
    return False


def _shift_wide_explains(before, after):
    """before → after の替わった所（前後の同じ字を外した所）を、その所を打った読みの記録（無ければ平仮名の字のまま）から
    手の位置のずれの戻し（hand_shift.kana_repairs、hand_shift_wide を含む）で作れるか。CN_FAR_SHIFT_WIDE=0 で見ない。"""
    try:
        import odd_respell as _o, hand_shift
        from kanji_guess import ime_readings_for
    except Exception:
        return False
    p = 0
    while p < min(len(before), len(after)) and before[p] == after[p]:
        p += 1
    q = 0
    while q < min(len(before), len(after)) - p and before[-1 - q] == after[-1 - q]:
        q += 1
    md, mf = before[p:len(before) - q], after[p:len(after) - q]
    if not md or not mf:
        return False
    tr = [_o._hira(x) for x in (ime_readings_for(md) or ())]
    if not tr and all(_o._is_hira(c) or c in '゛゜' for c in md):
        tr = [md]
    fr = [mf] if all(_o._is_hira(c) for c in mf) else (_o._line_reading_alts(mf) or [])
    for t in tr:
        if not t or len(t) > 12:
            continue
        got = set(hand_shift.kana_repairs(t, limit=2000))
        if any(f in got for f in fr):
            return True
    return False


def _far_kana_respell(line, result, out, input_method):
    """かな入力の紫の所の読み直しが、行の読みを3打以上替える直しか（読むう→消す: よむう→けす は3打。1つの所の
    打ち違いの戻しではなく別の語への置き換え）。採らずに紫のまま（2026-11-05 挙動関連担当の PC の測り: 生成ファイルの
    揃った起動で 本を読むう が 本を消す に直っていた）。ローマ字入力は打鍵の数え方が違うので見ない。CN_RESPELL_KANA_FAR=0。"""
    import os
    if input_method != 'kana' or os.environ.get('CN_RESPELL_KANA_FAR') == '0' or not isinstance(out, dict):
        return False
    before = (result or {}).get('corrected') or line
    after = out.get('corrected') or line
    if after == before:
        return False
    try:
        import odd_respell as _o
        rb, ra = _o._line_reading(before), _o._line_reading(after)
        if not rb or not ra:
            return False
        if _o._key_distance(_o._keys(rb), _o._keys(ra)) < RESPELL_KANA_FAR:
            return False
        if os.environ.get('CN_HAND_SHIFT') != '0':
            # 手の位置のずれ1つ（続く2〜4打が揃って同じ向きに1列: おらよ → おせわ）で説明できる直しは、別の語への
            # 置き換えではなく1つの所の打ち違いの戻し（hand_shift・2026-11-06）
            import hand_shift
            if hand_shift.kana_explains(rb, ra):
                return False
            if os.environ.get('CN_FAR_SHIFT_WIDE') != '0' and _shift_wide_explains(before, after):
                # 手の位置のずれ（人さし指の境目越し・間に他の手の打鍵を挟む: hand_shift_wide）で替わった所だけが説明できる
                # 直し（襟数と → 折り返し: えりすうと → おりかえし）も、1つの所の打ち違いの戻し（2026-11-10 全体評価の束）
                return False
        return True
    except Exception:
        return False


def _impossible_after_fix(line, result, out):
    """読み直しの直しが、いまの日本語で起こらない品詞のつながり（して＋くらい）を替わった所に作るか。作るなら採らない
    （紫のまま。2026-11-05 挙動関連担当の作った例: してくらさい が してくらいさ に直っていた）。CN_RESPELL_POS_CHECK=0。"""
    import os
    if os.environ.get('CN_RESPELL_POS_CHECK') == '0' or not isinstance(out, dict):
        return False
    before = (result or {}).get('corrected') or line
    after = out.get('corrected') or line
    if after == before:
        return False
    try:
        from pos_grammar import _impossible_connection_spans
        ops = [o for o in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes() if o[0] != 'equal']
        if not ops:
            return False
        lo, hi = ops[0][3], ops[-1][4]
        old_spans = set(_impossible_connection_spans(before))
        return any(a < hi + 1 and lo - 1 < b and (a, b) not in old_spans
                   for a, b in _impossible_connection_spans(after))
    except Exception:
        return False


def _carry_odd(line, got, result, base):
    """直した行 got を補正し直して付いた紫（base の odd_spans・got の位置）を、元の行 line の位置に写して result に足す。
    1行に打ち違いが2つあり、1つ目を直した後に2つ目の紫が付くのに、2つ目の読み直しが採れないと紫まで消えていた
    （2026-11-06 ローマ字の束4: 予約をhへのうしました）。直した所に掛かる紫は足さない。CN_CARRY_ODD=0 で前のまま。"""
    import os
    if os.environ.get('CN_CARRY_ODD') == '0' or not isinstance(result, dict):
        return result
    spans = [tuple(x[:2]) for x in (base.get('odd_spans') or ())]
    if not spans:
        return result
    try:
        ops = difflib.SequenceMatcher(None, got, line, autojunk=False).get_opcodes()
        changed = [(o[1], o[2]) for o in ops if o[0] != 'equal']
        add = []
        for a, b in spans:
            if any(x < b + 1 and a - 1 < y for x, y in changed):
                continue
            for tag, i1, i2, j1, j2 in ops:
                if tag == 'equal' and i1 <= a and b <= i2:
                    add.append((a - i1 + j1, b - i1 + j1))
                    break
        old = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
        add = [sp for sp in add if sp not in old]
        if not add:
            return result
    except Exception:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(set(old) | set(add))
    return out


def _respell_on_fixed(line, result, run, store, dict_index, context_vec, decisions, input_method):
    """前の段が行の一部を直したあとに残った紫を、直した行の上でもう一度読み直す（2026-11-04 うにの画面:
    打ち違いを1つ直すと、残りの所の紫が消えるか1字だけに縮み、紫の所の読み直しが届かなかった）。直した行を補正し直し、
    その紫で odd_respell を回す。前の直しに掛かる直しは採らない。切り替え CN_RESPELL_ON_FIXED=0。"""
    import os
    if os.environ.get('CN_RESPELL_ON_FIXED') == '0' or not isinstance(result, dict):
        return result
    got = result.get('corrected') or line
    if got == line or len(got) > 200:
        return result
    try:
        base = run(got)
    except Exception:
        return result
    if not isinstance(base, dict) or (base.get('corrected') or got) != got or not base.get('odd_spans'):
        return result
    # 前の段が文法で説明が付くとして外した紫の所（kana_lattice_place の _purple_cleared）は付け直さない。CN_RESPELL_KEEP_CLEARED=0
    cl = result.get('_purple_cleared')
    if cl and os.environ.get('CN_RESPELL_KEEP_CLEARED') != '0':
        left = [o for o in base.get('odd_spans') or () if not any(x <= o[0] and o[1] <= y for x, y in cl)]
        if not left:
            return result
    result = _carry_odd(line, got, result, base)
    try:
        import odd_respell
        second = odd_respell.repair_line(got, base, _deadline_run(run), store, dict_index, context_vec, (), input_method)
    except (Exception, _RespellTimeout):
        return result
    if not isinstance(second, dict) or second is base:
        return result
    second = _keep_kanji_face(got, base, _respell_ime_face(got, base, second))
    fin = second.get('corrected') or got
    if fin == got:
        return result
    # 2度目の直しは、替わった所が身近な語だけになり、行がはっきり自然になるときだけ（紫を消して 宝庫億書 のような
    # 珍しい語の並びにしない・2026-11-04 Store の測り）
    try:
        import ime_reconvert as _R
        from morphology import tokenize as _tok, path_cost as _pc
        o2 = [o for o in difflib.SequenceMatcher(None, got, fin, autojunk=False).get_opcodes() if o[0] != 'equal']
        k1, k2 = o2[0][3], o2[-1][4]
        nt = list(_tok(fin))
        if any(_R._token_rarity(t, nt) > _R.DOUBT_MARK for t in nt if t.start < k2 and k1 < t.end):
            return result
        # 替わった所の漢字の並び（億書）が、1つの語としても無いなら採らない
        import re as _re
        import kana_keep as _kk
        import last_keystroke as _LK
        for m in _re.finditer('[一-鿿々]{2,}', fin[k1:k2]):
            w = m.group()
            if _R._rank(w) >= 800 and not _R._known_compound(w) \
                    and w not in (_LK._kanji_choices(_kk._reading(w), store, dict_index) or ()):
                return result
        c0, c1 = _pc(got), _pc(fin)
        if c0 is None or c1 is None or c1 >= c0:
            return result
    except Exception:
        return result
    # 前の直しを元に戻す形（直した所が元の行の字のまま残る）は採らない。前の直しの上で読み直すのはよい（ぼ→お の上で 教え）
    ops1 = [o for o in difflib.SequenceMatcher(None, line, got, autojunk=False).get_opcodes() if o[0] != 'equal']
    keep = [o for o in difflib.SequenceMatcher(None, line, fin, autojunk=False).get_opcodes() if o[0] == 'equal']
    if any(any(k[1] <= o1[1] and o1[2] <= k[2] for k in keep) for o1 in ops1 if o1[2] > o1[1]):
        return result
    dec = corrector._decided_spans(line, decisions)
    ops = [o for o in difflib.SequenceMatcher(None, line, fin, autojunk=False).get_opcodes() if o[0] != 'equal']
    if any(x < o[2] and o[1] < y for o in ops for x, y in (dec or ())):
        return result
    near = [(o[1], o[2]) for o in ops]
    out = dict(result)
    out.update({'corrected': fin, 'changed': True,
                'details': list(result.get('details') or []) + list((second.get('details') or [])[-1:]),
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    for key in ('odd_spans', 'unsure_spans'):
        out[key] = [sp for sp in (result.get(key) or ()) if not any(x < sp[1] and sp[0] < y for x, y in near)]
    if 'odd_reasons' in result:
        out['odd_reasons'] = [r for r in (result.get('odd_reasons') or ()) if not any(x < r[1] and r[0] < y for x, y in near)]
    return out


def _respell_ime_face(line, result, out):
    """読み直した所の表記を IME の最初の変換にする（下し亜→下さい ではなく ください・2026-11-04 うにの画面）。
    IME の無い環境では out のまま。切り替え CN_RESPELL_IME_FACE=0。"""
    import os
    if not isinstance(out, dict) or out is result or os.environ.get('CN_RESPELL_IME_FACE') == '0':
        return out
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return out
    try:
        import ime_reconvert
        face = ime_reconvert.ime_face(before, fixed)
    except Exception:
        return out
    if not face or face == fixed:
        return out
    if os.environ.get('CN_RESPELL_IME_RARE_FACE') != '0':
        # IME の表記が、読み直しで選んだ漢字の語より珍しい別の漢字の語（来週 → 来襲）なら、その所は替えない。読みは同じで、
        # IME の変換の順は学習（試験の確定）で変わる（2026-11-10 1.18.2 ローマ字の画面・挙動関連担当の覗き:
        # この PC の IME は らいしゅう を 来襲 と変換）。ほかの所の替え（下さい → ください）はそのまま
        parts = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, fixed, face, autojunk=False).get_opcodes():
            if tag != 'equal' and _ime_face_rarer(fixed, fixed[:i1] + face[j1:j2] + fixed[i2:]):
                parts.append(fixed[i1:i2])
            else:
                parts.append(face[j1:j2])
        face = ''.join(parts)
        if face == fixed:
            return out
    new = dict(out)
    ops = [o for o in difflib.SequenceMatcher(None, line, face, autojunk=False).get_opcodes() if o[0] != 'equal']
    new['corrected'] = face
    new['changed'] = bool(ops)
    new['spans'] = [[o[3], o[4]] for o in ops]
    new['original_spans'] = [[o[1], o[2]] for o in ops]
    det = [list(d) for d in (out.get('details') or [])]
    old = [o for o in difflib.SequenceMatcher(None, fixed, face, autojunk=False).get_opcodes() if o[0] != 'equal']
    for d in det:
        if len(d) >= 2 and isinstance(d[1], str):
            for o in old:
                piece = fixed[o[1]:o[2]]
                if piece and piece in d[1]:
                    d[1] = d[1].replace(piece, face[o[3]:o[4]], 1)
    new['details'] = det
    return new


def _ime_face_rarer(fixed, face):
    """face の替わった所の漢字の語が一般の文章で珍しく（odd_respell.COMMON_NEW より後ろ）、fixed の同じ所の漢字の語の
    ほうが身近か。"""
    try:
        import odd_respell as _OR
        import ime_reconvert as R
        from morphology import tokenize
    except Exception:
        return False
    ops = [o for o in difflib.SequenceMatcher(None, fixed, face, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return False

    def rank(text, a, b):
        rs = [R._rank(t.surface) for t in tokenize(text)
              if t.start < max(b, a + 1) and a < t.end and any('一' <= c <= '鿿' for c in t.surface)]
        return max(rs) if rs else None
    rf = rank(face, ops[0][3], ops[-1][4])
    rx = rank(fixed, ops[0][1], ops[-1][2])
    return rf is not None and rx is not None and rf > _OR.COMMON_NEW and rx < rf


def _keep_kanji_face(line, result, out):
    """紫の所の読み直しが、元の行にあった漢字の語を、同じ読みの別の漢字に替えていたら元の顔に戻す（ご返信ｊを →
    ご変身を ではなく ご返信を・2026-11-06 ローマ字の試しのスレッド）。打ち違いは読みに出るので、読みの変わらない
    漢字の置き換えは直しではない。替わった所ごとに、前と後の漢字の並びが同じ数で、組ごとに読みが同じなら前の顔に。
    戻した行が前と同じになれば直しを採らない。CN_RESPELL_KEEP_FACE=0 で前のまま。"""
    import os, re
    if not isinstance(out, dict) or out is result or os.environ.get('CN_RESPELL_KEEP_FACE') == '0':
        return out
    before = (result.get('corrected') if isinstance(result, dict) else None) or line
    fixed = out.get('corrected') or line
    if fixed == before:
        return out
    try:
        import kana_keep
        pieces = []
        last = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, before, fixed, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            while i1 > 0 and j1 > 0 and re.match('[一-鿿々]', before[i1 - 1]) and before[i1 - 1] == fixed[j1 - 1]:
                i1 -= 1
                j1 -= 1
            while i2 < len(before) and j2 < len(fixed) and re.match('[一-鿿々]', before[i2]) and before[i2] == fixed[j2]:
                i2 += 1
                j2 += 1
            if j1 < last:
                return out
            ka = list(re.finditer('[一-鿿々]+', before[i1:i2]))
            kb = list(re.finditer('[一-鿿々]+', fixed[j1:j2]))
            seg = fixed[j1:j2]
            if ka and len(ka) == len(kb):
                for ma, mb in reversed(list(zip(ka, kb))):
                    if ma.group() != mb.group() and kana_keep._reading(ma.group()) \
                            and kana_keep._reading(ma.group()) == kana_keep._reading(mb.group()):
                        seg = seg[:mb.start()] + ma.group() + seg[mb.end():]
            elif ka and kb and os.environ.get('CN_RESPELL_KEEP_FACE_ANY') != '0':
                # 前の漢字の並びの数が違う（返信ｗ素 → 変身を）ときは、後の漢字の並びごとに、同じ読みの前の並びを探す
                ra = [(m.group(), kana_keep._reading(m.group())) for m in ka]
                for mb in reversed(kb):
                    rb = kana_keep._reading(mb.group())
                    hit = [f for f, r in ra if r and r == rb and f != mb.group()]
                    if len(hit) == 1:
                        seg = seg[:mb.start()] + hit[0] + seg[mb.end():]
            pieces.append(fixed[last:j1] + seg)
            last = j2
        face = ''.join(pieces) + fixed[last:]
    except Exception:
        return out
    if face == fixed:
        return out
    if face == before:
        return result
    new = dict(out)
    ops = [o for o in difflib.SequenceMatcher(None, line, face, autojunk=False).get_opcodes() if o[0] != 'equal']
    new['corrected'] = face
    new['changed'] = bool(ops)
    new['spans'] = [[o[3], o[4]] for o in ops]
    new['original_spans'] = [[o[1], o[2]] for o in ops]
    det = [list(d) for d in (out.get('details') or [])]
    for o in [o for o in difflib.SequenceMatcher(None, fixed, face, autojunk=False).get_opcodes() if o[0] != 'equal']:
        piece = fixed[o[1]:o[2]]
        for d in det:
            if len(d) >= 2 and isinstance(d[1], str) and piece and piece in d[1]:
                d[1] = d[1].replace(piece, face[o[3]:o[4]], 1)
                break
    new['details'] = det
    return new


def _noun_suffix(line, result, run, store, dict_index, decisions):
    """漢字の名詞のすぐ後ろにかなのまま残った接尾の語（中・的）に漢字を置き、置いた行で補正し直す
    （noun_suffix・2026-10-31）。置けなければ答えはそのまま。"""
    try:
        import noun_suffix
        out = noun_suffix.repair_line(line, result, run, store, dict_index, corrector._decided_spans(line, decisions))
    except Exception:
        return result
    # 置いた所が元の行で機能語だけの並び（いい子｜だから→子宝）なら置く前に戻す（2026-11-07）
    return _lattice_function_guard(line, result, out)


def _lattice_place(line, result, store, dict_index):
    """かなのまま残った文節の頭の並び（かなの文法で説明の付かないもの）の区切りを読みの格子で決めて漢字を置く
    （kana_lattice_place・2026-10-25）。置けなければ答えはそのまま。"""
    try:
        import kana_lattice_place
        out = kana_lattice_place.repair_line(line, result, store, dict_index)
    except Exception:
        return result
    return _lattice_function_guard(line, result, out)


_FUNCTION_POS = ('助詞', '助動詞', '副詞', '接続詞', '連体詞', '感動詞')


def _lattice_function_guard(line, before, after):
    """格子で置いた所が、元の行の解析で語の切れ目に揃った機能語・副詞だけの並び（勝つ｜かどうか｜は）なら、置く前の
    答えに戻す（かどうか→華道家・どうしよう→銅使用: 例文 Tatoeba の正しい文で見つけた・2026-11-07）。
    置いた所がどれも当てはまる時だけ戻す。CN_LATTICE_FUNC_GUARD=0 で前のまま。"""
    import os
    if (os.environ.get('CN_LATTICE_FUNC_GUARD') == '0' or after is before or not isinstance(after, dict)
            or not isinstance(before, dict)):
        return after
    new, old = after.get('corrected') or line, before.get('corrected') or line
    if new == old:
        return after
    try:
        from morphology import tokenize
        toks = list(tokenize(old))
    except Exception:
        return after
    ops = [o for o in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return after
    for _tag, i1, i2, _j1, _j2 in ops:
        src = old[i1:i2]
        if not src or not all('ぁ' <= c <= 'ゖ' for c in src):
            return after
        inside = [t for t in toks if t.end > i1 and t.start < i2]
        # 置いた所の端が、元の解析で読みのある かなの動詞（どう｜やっ｜て の やっ）の途中を切るなら、その動詞を割った
        # 置き方（どうや → 同夜）。前が機能語・副詞だけなら戻す（2026-11-08 補正担当の正しい文の試し）。
        # CN_LATTICE_SPLIT_VERB=0 で前のまま
        if (os.environ.get('CN_LATTICE_SPLIT_VERB') != '0' and inside and inside[-1].end > i2
                and inside[-1].pos == '動詞' and inside[-1].has_reading
                and all('ぁ' <= c <= 'ゖ' for c in inside[-1].surface)
                and all(t.pos in _FUNCTION_POS or _formal_noun_token(t) for t in inside[:-1])
                and inside[0].start == i1):
            continue
        if (not inside or inside[0].start != i1 or inside[-1].end != i2
                or not all(t.pos in _FUNCTION_POS or _formal_noun_token(t) for t in inside)):
            return after
        # 副詞と解析した語のすぐ後ろが を・が なら副詞ではない（いと｜を: 副詞は を・が を取らない）。名詞として置いた所は残す
        # （2026-11-08 手分けA）。CN_LATTICE_FUNC_GUARD_CASE=0 で前のまま
        if os.environ.get('CN_LATTICE_FUNC_GUARD_CASE') != '0' and inside[-1].pos == '副詞':
            nxt = next((t for t in toks if t.start == i2), None)
            if nxt is not None and nxt.pos == '助詞' and nxt.surface in ('を', 'が'):
                return after
    return before


_FORMAL_KANA_NOUNS = ('とこ', 'ところ', 'もん', 'もの', 'こと', 'わけ', 'はず', 'ため', 'せい', 'うち', 'まま', 'ほう', 'つもり')


def _formal_noun_token(t):
    """かなで書いた形式名詞（行く｜とこ・休みの｜せい｜か: 解析の 名詞,非自立 か、話し言葉の とこ・もん）。
    格子で漢字に置くと別の語になる（とこ→床・せいか→成果・2026-11-07 例文 Tatoeba）。CN_LATTICE_FORMAL_NOUN=0 で見ない。"""
    import os
    if os.environ.get('CN_LATTICE_FORMAL_NOUN') == '0' or t.pos != '名詞':
        return False
    return ((t.pos_sub or '').startswith('非自立') and all('ぁ' <= c <= 'ゖ' for c in t.surface)) or t.surface in _FORMAL_KANA_NOUNS


def _word_pair_mark(line, result, store, dict_index, decisions):
    """隣り合う語の組（名詞＋接尾・名詞＋格助詞＋かなの動詞）をつないだ読みが辞書の1語になる所
    （word_pair_mark・2026-10-25）。候補1つなら置いて紫、複数なら紫。"""
    try:
        import word_pair_mark
        return word_pair_mark.repair_line(line, result, store, dict_index, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _impossible_slip(line, result, decisions, input_method):
    """いまの文では起こらない品詞のつながりの所のかな1字を、近いキーに替えて行が一番自然になる形が1つに決まれば置く
    （impossible_slip・2026-10-30）。並べば紫のまま。"""
    try:
        import impossible_slip
        return impossible_slip.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _kanji_doubt(line, result, store, dict_index, decisions):
    """常用漢字表の外の字を含む語を疑い、一般のミスタイプを当てて行がより自然になれば紫か直す（kanji_doubt・2026-10-26）。"""
    try:
        import kanji_doubt
        return kanji_doubt.repair_line(line, result, store, dict_index, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _ime_unlikely_join(line, result, decisions):
    """漢字の語が続いて1語として無い所（纏｜外）で、中の1字が どの読みでも IME の上の方に出ない（本人の学習も無い）字なら、
    その字は打った読みの字ではないと見て、同じ読み（別の読み・語幹）で IME の先頭に出る身近な1字に替え、1語として在る形
    （的外れ）になるものが1つだけなら直す（ime_order・うに 2026-11-08 13:19Z/13:20Z）。届かなければ何もしない（紫は後ろの段）。
    切り替え CN_IME_ORDER=0。"""
    import os
    if os.environ.get('CN_IME_ORDER') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if not any('\u4e00' <= c <= '\u9fff' for c in done):
        return result
    try:
        import ime_order as _O
        import seed_japanese as _S
        import ime_reconvert as _R
        from morphology import tokenize
        toks = tokenize(done)
    except Exception:
        return result
    changed = [(o[3], o[4]) for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
               if o[0] != 'equal']
    try:
        decided = list(corrector._decided_spans(line, decisions))
    except Exception:
        decided = []
    odd_now = [tuple(x[:2]) for x in list(result.get('odd_spans') or ())]
    fixes = []
    i = 0
    while i < len(toks):
        j = i
        while (j < len(toks) and toks[j].surface and all(_O._kanji(c) for c in toks[j].surface)
               and (j == i or toks[j - 1].end == toks[j].start)):
            j += 1
        # 最後の語は 漢字＋かな（外れ）でもよい: 漢字の所までを並びにし、かなは後ろ（tail）として見る
        if (j > i and j < len(toks) and toks[j].start == toks[j - 1].end and toks[j].surface
                and _O._kanji(toks[j].surface[0])):
            k = 0
            while k < len(toks[j].surface) and _O._kanji(toks[j].surface[k]):
                k += 1
            last = (toks[j].start, toks[j].start + k, toks[j].surface[:k])
        else:
            last = None
        # 替えてよいのは1字の語そのもの（漢字＋かなの語の一部は替えない: 始め・買い）で、珍しい字（段 600 以上）・
        # 数・接尾（一膳・二日制）でないもの
        run = [(t.start, t.end, t.surface,
                len(t.surface) == 1 and not (t.pos_sub or '').startswith(('数', '接尾'))
                and not (n > i and toks[n - 1].pos_sub == '数') and _R._rank(t.surface) >= 600)
               for n, t in enumerate(toks[i:j], start=i)] + ([last + (False,)] if last else [])
        if len(run) >= 2:
            a, b = run[0][0], run[-1][1]
            face = done[a:b]
            try:
                rare = 2 <= b - a <= 3 and _S.is_unit(face) is not True and _R._rank(face) >= 800
            except Exception:
                rare = False
            if rare and not any(x < b and a < y for x, y in changed):
                tail = ''
                for c in done[b:b + 2]:
                    if 'ぁ' <= c <= 'ゖ':
                        tail += c
                    else:
                        break
                parts = [t[2] for t in run]
                cands = []
                for k, t in enumerate(run):
                    if t[3] and _O.unlikely_char(t[2]):
                        for f, _r in _O.respell_faces(parts, k, tail):
                            if f not in cands:
                                cands.append(f)
                if len(cands) == 1:
                    fixes.append((a, b, cands[0]))
        i = max(j + (1 if last else 0), i + 1)
    if not fixes:
        return result
    new = done
    details = []
    for a, b, f in sorted(fixes, reverse=True):
        org = None
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, done, line, autojunk=False).get_opcodes():
            if tag == 'equal' and i1 <= a and b <= i2:
                org = (a - i1 + j1, b - i1 + j1)
        if org is None or any(x < org[1] and org[0] < y for x, y in decided):
            continue
        details.append([done[a:b], f, 'IME で出にくい字'])
        new = new[:a] + f + new[b:]
    if new == done:
        return result
    out = dict(result)
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + details,
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    if odd_now:
        out['odd_spans'] = [s for s in odd_now if not any(s[0] < o[2] and o[1] < s[1] for o in ops)]
    return out


def _fix_rare_join_by_key(line, result, decisions, input_method):
    """紫の付いた漢字の並び（1語として無い・珍しい）だけで、中の1字が どの読みでも IME の上に出ない字なら、並びを
    字の読み（語幹を含む）と他の字の IME が先頭に返す読みで読み、かなキーの1打を戻して身近な語に届く表記が1つだけなら
    直す（纏外 → まとがい → まちがい 間違い・うに 2026-11-08 13:38Z「紫が付いたところだけその処理を」）。
    読みそのものが語なら（てんと テント）IME はその語を返すのでその読みは見ない。かな入力だけ。切り替え CN_RARE_JOIN_KEY=0。"""
    import os
    if (os.environ.get('CN_RARE_JOIN_KEY') == '0' or os.environ.get('CN_IME_ORDER') == '0'
            or input_method != 'kana' or not isinstance(result, dict)):
        return result
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or ()]
    if not odd:
        return result
    done = result.get('corrected') or line
    try:
        import ime_order as _O
        import seed_japanese as _S
        import ime_reconvert as _R
        from morphology import tokenize
    except Exception:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
    if ops:
        # 紫は元の行の位置。直しの入った行では位置が合わないので見ない
        return result
    try:
        decided = list(corrector._decided_spans(line, decisions))
    except Exception:
        decided = []
    toks = tokenize(line)
    fixes = []
    for a, b in odd:
        if any(x < b and a < y for x, y in decided):
            continue
        run = [t for t in toks if a <= t.start and t.end <= b]
        if (len(run) < 2 or run[0].start != a or run[-1].end != b
                or not all(t.surface and all(_O._kanji(c) for c in t.surface) for t in run)
                or any(p.end != q.start for p, q in zip(run, run[1:]))):
            continue
        face = line[a:b]
        try:
            if not (2 <= b - a <= 3 and _S.is_unit(face) is not True and _R._rank(face) >= 800):
                continue
        except Exception:
            continue
        # 並びの後ろが活用の続き（挫｜いて）なら、並びは用言の語幹で、名詞の打ち違いではない
        nxt = next((t for t in toks if t.start == b), None)
        if nxt is not None and nxt.pos not in ('助詞', '助動詞', '記号'):
            continue
        flags = [len(t.surface) == 1 and not (t.pos_sub or '').startswith(('数', '接尾'))
                 and _R._rank(t.surface) >= 600 and _O.unlikely_char(t.surface) for t in run]
        if not any(flags):
            continue
        cands = _O.key_respell([t.surface for t in run], flags, line[a - 1:a] if a else '', line[b:b + 1])
        if len(cands) == 1:
            fixes.append((a, b, cands[0]))
    if not fixes:
        return result
    new = line
    details = []
    for a, b, f in sorted(fixes, reverse=True):
        details.append([line[a:b], f, '紫の所の打ち違い（IME で出にくい字）'])
        new = new[:a] + f + new[b:]
    out = dict(result)
    ops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'original': line, 'corrected': new, 'changed': True,
                'details': list(result.get('details') or []) + details,
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    fixed = [(a, b) for a, b, _f in fixes]
    out['odd_spans'] = [s for s in (result.get('odd_spans') or ()) if tuple(s[:2]) not in fixed]
    if result.get('odd_reasons'):
        out['odd_reasons'] = [r for r in result['odd_reasons'] if tuple(r[:2]) not in fixed]
    return out


_SMALL_VOWEL = {'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お'}
_END_MARKS = set('。、！？!?…ー〜～」』）)　 ')


def _spoken_elongation_positions(line):
    """話し言葉の伸ばし（〜でぇ・〜よぉ・すごぉい）の小書き母音の位置: 前のひらがなと同じ母音で、行末・記号・
    もう1つの小書き母音の前にあるもの。"""
    try:
        from corrector import _VOWEL_OF
    except Exception:
        return []
    out = []
    for i, c in enumerate(line):
        v = _SMALL_VOWEL.get(c)
        if not v or i == 0:
            continue
        if _VOWEL_OF.get(line[i - 1]) != v:
            continue
        nxt = line[i + 1:i + 2]
        if nxt == '' or nxt in _END_MARKS or nxt in _SMALL_VOWEL:
            out.append(i)
    # ひらがなの後ろの伸ばしの ー（もくもくしゅー・すごーい）も話し言葉の伸ばし
    if __import__('os').environ.get('CN_KEEP_HIRA_LONG') != '0':
        for i, c in enumerate(line):
            if c == 'ー' and i > 0 and 'ぁ' <= line[i - 1] <= 'ゖ':
                out.append(i)
    return sorted(set(out))


def _kata_to_hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _keep_spoken_elongation(line, result):
    """話し言葉の伸ばしの小書き母音（突つかないでぇ）は打ち違いとみない: その字だけの直し（でぇ→でえ・です）を戻し、
    その字に掛かる紫を外す（うに 10-24「小書き母音は語の頭だけ、くださぃ・かわいぃ は話し言葉として残す」の続き、
    2026-11-08 未解決タブの誤判定）。切り替え CN_KEEP_ELONGATION=0。"""
    import os
    if os.environ.get('CN_KEEP_ELONGATION') == '0' or not isinstance(result, dict):
        return result
    pos = _spoken_elongation_positions(line)
    if not pos:
        return result
    done = result.get('corrected') or line
    out = dict(result)
    changed = False
    if done != line:
        ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
        keep = []
        for o in ops:
            tag, i1, i2, j1, j2 = o
            if any(i1 <= p < max(i2, i1 + 1) for p in pos) and i2 - i1 <= 2 and j2 - j1 <= 2:
                changed = True
                continue
            # ー の前の字を替えた直し（しゅ｜ー → ショ｜ー）: 字を片仮名にしただけ（こーひー → コーヒー）でなく、
            # かなそのものを替えたなら戻す
            if (any(i2 == p and line[p] == 'ー' for p in pos) and i2 - i1 <= 2
                    and _kata_to_hira(done[j1:j2]) != line[i1:i2]):
                changed = True
                continue
            keep.append(o)
        if changed:
            new = []
            last = 0
            for tag, i1, i2, j1, j2 in keep:
                new.append(line[last:i1])
                new.append(done[j1:j2])
                last = i2
            new.append(line[last:])
            new = ''.join(new)
            ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
            out.update({'corrected': new, 'changed': new != line,
                        'spans': [[o[3], o[4]] for o in ops2], 'original_spans': [[o[1], o[2]] for o in ops2]})
            # 戻した直しの理由は外す（直した先の字が行に残らないもの）
            out['details'] = [d for d in (result.get('details') or [])
                              if not (isinstance(d, (list, tuple)) and len(d) > 1 and str(d[1]) not in new)]
    odd = list(result.get('odd_spans') or ())
    small = [p for p in pos if line[p] != 'ー']
    kept = [sp for sp in odd if not any(sp[0] <= p < sp[1] for p in small)
            and not (sp[1] - sp[0] <= 2 and any(sp[0] <= p + 1 and p - 1 < sp[1] for p in pos))]
    if len(kept) != len(odd):
        out['odd_spans'] = kept
        if result.get('odd_reasons'):
            out['odd_reasons'] = [r for r in result['odd_reasons']
                                  if any(tuple(r[:2]) == tuple(k[:2]) for k in kept)]
        changed = True
    return out if changed else result


def _nearby_one_key(line, result, nearby_words, input_method, decisions):
    """上下の行に書かれた語と読みが隣のキーの1打だけ違う漢字の語（本字→返事・nearby_one_key・2026-10-30）。"""
    try:
        import nearby_one_key
        return nearby_one_key.repair_line(line, result, nearby_words, input_method, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _mark_keeps_next(line, result):
    """付く先の無い ゛゜ を後ろの字に付けた直し（時間゛かかった → 時間がかった）は、後ろの字を1つ使ってしまう。
    ゛゜ の前の字（が の か）を打ち落とした形も同じ1打の誤りなので、゛゜ だけを後ろの字の濁音・半濁音に替え、
    後ろの字は残した形（時間がかかった）とも比べ、自然さ（morphology.path_cost）の良い方にする。
    特定の語には合わせない（2026-11-05 かな入力の担当）。切り替え CN_MARK_KEEPS_NEXT=0。"""
    import os
    if os.environ.get('CN_MARK_KEEPS_NEXT') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line or ('゛' not in line and '゜' not in line):
        return result
    try:
        import difflib, unicodedata
        from morphology import path_cost
        ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
        if len(ops) != 1 or ops[0][0] != 'replace':
            return result
        _, a, b, c, d = ops[0]
        src, new = line[a:b], done[c:d]
        if len(src) != 2 or len(new) != 1 or src[0] not in '゛゜':
            return result
        voiced = unicodedata.normalize('NFC', src[1] + ('\u3099' if src[0] == '゛' else '\u309a'))
        if len(voiced) != 1 or voiced != new:
            return result
        alt = line[:a] + voiced + line[a + 1:]
        c0, c1 = path_cost(done), path_cost(alt)
        if c0 is None or c1 is None or c1 >= c0:
            return result
        out = dict(result)
        out.update({'corrected': alt, 'changed': True, 'spans': [[a, a + 1]], 'original_spans': [[a, a + 1]],
                    'details': [list(x) for x in (result.get('details') or ()) if list(x)[:2] != [src, new]]
                    + [[src[0], voiced, 'かな入力']]})
        return out
    except Exception:
        return result


SWAP_READING_MARGIN = 3000


def _swap_reading_worse(line, m, mark):
    """line[m] の ゛゜ を次の字に付けた形（さしこみ゛て → さしこみで）と、前の2字の打つ順の入れ替わりと見た形
    （→ さしみごて）を行の並びの費用で比べ、入れ替わりの形がはっきり悪い（SWAP_READING_MARGIN 以上高い）なら真。
    そのときは入れ替わりの見方を取らず、次の字に付けた直しを残す（2026-11-08 うにの未解決タブ・作った例）。
    CN_SWAP_READING_CHECK=0 で前のまま（いつも偽）。"""
    import os
    import unicodedata
    if os.environ.get('CN_SWAP_READING_CHECK') == '0' or m + 1 >= len(line) or m < 2:
        return False
    nxt = unicodedata.normalize('NFC', line[m + 1] + mark)
    if len(nxt) != 1:
        return False
    x, y = line[m - 2], line[m - 1]
    fwd = line[:m] + nxt + line[m + 2:]
    swp = line[:m - 2] + y + unicodedata.normalize('NFC', x + mark) + line[m + 1:]
    try:
        from morphology import path_cost
        cf, cs = path_cost(fwd), path_cost(swp)
    except Exception:
        return False
    return cf is not None and cs is not None and cs - cf >= SWAP_READING_MARGIN


def _mark_swapped_back(line, result):
    """゛゜ が付けられない字の後ろに浮き、その1つ前の字には付けられる形（なへら゛ ← ならべ）は、゛゜ の付く字と次の字の
    打つ順が入れ替わった跡でもある。その ゛゜ を後ろの字に付けた直し（へら゛て → へらで）は、入れ替わりの見方と
    決められないので直さず紫にする（2026-11-06 うにの画面: 並べて の順番違い）。CN_MARK_SWAPPED_BACK=0 で前のまま。"""
    import os
    if os.environ.get('CN_MARK_SWAPPED_BACK') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line or ('゛' not in line and '゜' not in line):
        return result
    try:
        import unicodedata
        ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
        hits = []
        for _t, a, b, _c, _d in ops:
            for m in range(max(2, a), min(len(line), b + 1)):
                if line[m] not in '゛゜' or not (a <= m < b):
                    continue
                mark = '\u3099' if line[m] == '゛' else '\u309a'
                y, x = line[m - 1], line[m - 2]
                if (len(unicodedata.normalize('NFC', y + mark)) != 1
                        and len(unicodedata.normalize('NFC', x + mark)) == 1
                        and ('ぁ' <= y <= 'ゖ' or 'ァ' <= y <= 'ヺ')):
                    if _swap_reading_worse(line, m, mark):
                        continue
                    hits.append((m - 2, m + 1))
        if not hits:
            return result
        # その ゛゜ の所の直しだけ戻す（ほかの所の直しは残す）
        parts, rev = [], []
        for tag, a, b, c, d in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes():
            if tag != 'equal' and any(h[0] <= a and b <= h[1] + 1 and a < h[1] for h in hits):
                parts.append(line[a:b])
                rev.append(done[c:d])
            elif (tag == 'replace' and any(a == h[1] - 1 for h in hits) and b - a > 2 and d - c > 1
                  and line[a] in '゛゜' and unicodedata.normalize('NFD', done[c])[1:] in ('\u3099', '\u309a')):
                # ゛゜＋次の字 を濁音1字にした所が、ほかの直しと1つにまとまった（゛手おく → で置く）: 頭の1字だけ戻す
                parts.append(line[a:a + 2] + done[c + 1:d])
                rev.append(done[c:c + 1])
            else:
                parts.append(done[c:d])
        if not rev:
            return result
        new = ''.join(parts)
    except Exception:
        return result
    out = dict(result)
    nops = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(nops), 'spans': [[o[3], o[4]] for o in nops],
                'original_spans': [[o[1], o[2]] for o in nops],
                'details': [x for x in (result.get('details') or ()) if not (len(x) > 1 and x[1] in rev)],
                'odd_spans': sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | set(hits))})
    return out


FLOAT_MARK_MARGIN = 1000


def _float_mark_choice(line, result):
    """付けられない字（ー・ん・あ行・け゜ など）の後ろに浮いた ゛゜ を、消すか前の字に付けるかだけの直し（タクシー゛以降 →
    タクシー以降・ありません゛本日 → ありませが本日）は、゛゜ の付く字（か〜ほ行）を打ち落とした跡のことが多い。その所に
    濁音・半濁音の1字を足した形（ありませんが本日）と比べ、一番の形が今の直しより FLOAT_MARK_MARGIN 以上自然で、
    二番より同じだけ自然ならそれにし、決まらなければ直さず紫にする（2026-11-06 脱字のスレッド）。CN_FLOAT_MARK=0。"""
    import os
    if os.environ.get('CN_FLOAT_MARK') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line or ('゛' not in line and '゜' not in line):
        return result
    try:
        import unicodedata
        from morphology import path_cost
        ops = [o for o in difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes() if o[0] != 'equal']
        if len(ops) != 1:
            return result
        _, a, b, c, d = ops[0]
        m = next((k for k in range(max(0, a - 1), min(len(line), b + 1)) if line[k] in '゛゜'), None)
        if m is None or m == 0 or not (a <= m < b or m == b):
            return result
        prev = line[m - 1]
        mark = '\u3099' if line[m] == '゛' else '\u309a'
        if len(unicodedata.normalize('NFC', prev + mark)) == 1:
            return result            # 前の字に付けられる ゛゜ は別の段（_mark_keeps_next）
        # 直しが ゛゜ を消すか前の字を替えただけ（新しい字を足していない）こと
        if len(done) > len(line) - 1 and done[c:d] not in ('', ):
            if not (b - a == 2 and d - c == 1):
                return result
        bases = 'かきくけこさしすせそたちつてとはひふへほ' if line[m] == '゛' else 'はひふへほ'
        cands = []
        for ch in bases:
            v = unicodedata.normalize('NFC', ch + mark)
            t = line[:m] + v + line[m + 1:]
            ct = path_cost(t)
            if ct is not None:
                cands.append((ct, t, v))
        c_done = path_cost(done)
        if not cands or c_done is None:
            return result
        cands.sort()
        best = cands[0]
        if best[0] <= c_done - FLOAT_MARK_MARGIN and (len(cands) == 1 or cands[1][0] - best[0] >= FLOAT_MARK_MARGIN):
            face = best[1]
            out = dict(result)
            o2 = [o for o in difflib.SequenceMatcher(None, line, face, autojunk=False).get_opcodes() if o[0] != 'equal']
            out.update({'corrected': face, 'changed': True, 'spans': [[o[3], o[4]] for o in o2],
                        'original_spans': [[o[1], o[2]] for o in o2],
                        'details': [[line[m], best[2], '浮いた濁点']]})
            return out
        if c_done <= best[0] - FLOAT_MARK_MARGIN:
            return result
        out = dict(result)
        out.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': [],
                    'odd_spans': sorted(set(tuple(x[:2]) for x in (result.get('odd_spans') or ())) | {(m - 1, m + 1)})})
        return out
    except Exception:
        return result


SWAP_PARTICLE_GAIN = 4000   # 助詞に戻した行が、これだけ自然（path_cost が軽い）になること
_SWAP_PARTICLES = ('の', 'に', 'を', 'が', 'は', 'で', 'と', 'へ', 'も')


def _swapped_particle_kanji(line, result, decisions, input_method):
    """ローマ字入力で助詞の2打を入れ替えた形（の を on・に を in と打つ）を IME が1字の漢字（音・院）にした所を、助詞に
    戻す（2026-11-06 ローマ字の試しのスレッド: 製品音説明会・こない音で・部長院報告。正しい文で 音→の は 2,450 以下しか
    軽くならない: 大きな音で・隣の部屋の音が）。1字の漢字の名詞の読み（打った読みがあればそれ）を1回の入れ替えで戻すと
    助詞だけになり、行が SWAP_PARTICLE_GAIN 以上軽くなるとき。候補が1つなら直し、並べば紫。CN_SWAP_PARTICLE=0 で前のまま。"""
    import os
    if input_method != 'romaji' or os.environ.get('CN_SWAP_PARTICLE') == '0' or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line:
        return result
    try:
        from morphology import tokenize, path_cost, katakana_to_hiragana
        import romaji_swap_repair as R
        import kanji_guess
        toks = list(tokenize(line))
        base = path_cost(line)
        if base is None:
            return result
        decided = corrector._decided_spans(line, decisions)
        taken = [tuple(x[:2]) for x in (result.get('odd_spans') or ())]
        fixes, marks = [], []
        for i, t in enumerate(toks):
            if not (0 < i < len(toks) - 1) or len(t.surface) != 1 or not ('一' <= t.surface <= '鿿') or t.pos != '名詞':
                continue
            p, n = toks[i - 1], toks[i + 1]
            if p.pos not in ('名詞', '動詞', '形容詞', '助動詞') or n.pos not in ('名詞', '動詞', '形容詞', '接頭詞'):
                continue
            if any(a < t.end and t.start < b for a, b in decided):
                continue
            rds = set(kanji_guess.ime_readings_for(t.surface) or ())
            if not rds and t.reading:
                rds = {katakana_to_hiragana(t.reading)}
            cands = []
            for rd in rds:
                for k in R.swap_readings(rd):
                    if k in _SWAP_PARTICLES:
                        cost = path_cost(line[:t.start] + k + line[t.end:])
                        if cost is not None and base - cost >= SWAP_PARTICLE_GAIN:
                            cands.append((cost, k))
            cands = sorted(set(cands))
            if not cands:
                continue
            if len({k for _c, k in cands}) == 1:
                fixes.append((t.start, t.end, cands[0][1]))
            else:
                marks.append((t.start, t.end))
        if not fixes and not marks:
            return result
        out = dict(result)
        if marks:
            out['odd_spans'] = sorted(set(taken) | set(marks))
        if fixes:
            new = line
            for a, b, k in sorted(fixes, reverse=True):
                new = new[:a] + k + new[b:]
            out.update({'corrected': new, 'changed': True,
                        'details': list(result.get('details') or []) + [[line[a:b], k, '助詞の入れ替え'] for a, b, k in fixes],
                        'spans': [[a, a + len(k)] for a, b, k in fixes], 'original_spans': [[a, b] for a, b, k in fixes]})
        return out
    except Exception:
        return result


KANJI_SWAP_RARER_GAP = 120


def _kanji_swap_guard(line, result):
    """直しが送り仮名などの前後を残したまま漢字だけを別の漢字に替え、語の読みが2字以上変わる形（行く→開く: いく→ひらく）は、
    打った読みから1打の誤りでは届かない読み替えなので入れない。直す前の語が身近な語（珍しさ600以下）なら元の字に戻し、
    そこを紫にする。読みの並べ替え（どとい→とどい）や1字の差（いしゅつ→ていしゅつ）は1打の誤りで届くので触らない。
    特定の語には合わせない（2026-11-06 かな入力の担当）。切り替え CN_KANJI_SWAP_GUARD=0。"""
    import os
    if os.environ.get('CN_KANJI_SWAP_GUARD') == '0' or not isinstance(result, dict):
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        import difflib
        from morphology import tokenize
        import ime_reconvert as _R
        kanji = lambda w: bool(w) and all('一' <= c <= '鿿' or c == '々' for c in w)
        hira = lambda s: ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)

        def lev(a, b):
            # かな入力の打鍵で数える: ゛゜ は別のキー（はしせめる → はじめる は せ を ゛ にした1打・2026-11-08）。
            # CN_KANJI_SWAP_KEYS=0 で前の字の数え方
            if os.environ.get('CN_KANJI_SWAP_KEYS') != '0':
                return _key_edit_count(a, b)
            d = list(range(len(b) + 1))
            for i, x in enumerate(a, 1):
                p, d[0] = d[0], i
                for j, y in enumerate(b, 1):
                    p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (x != y))
            return d[-1]
        tl, td = list(tokenize(line)), list(tokenize(done))
        ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
        bad = set()
        for k, (tag, a, b, c, d) in enumerate(ops):
            # 長さの同じ置き換えだけ（戻しても他の紫・直しの位置がずれない）
            wide = shrink = False
            if (tag == 'replace' and b - a > d - c and kanji(line[a:b]) and kanji(done[c:d])
                    and os.environ.get('CN_KANJI_SWAP_SHRINK', '1') != '0'
                    and not any(o[1] > c for o in (result.get('odd_spans') or ()))
                    and not any(o2[0] != 'equal' for o2 in ops[k + 1:])):
                # 漢字の並び（語を2つ以上つないだ所）を、字の少ない別の漢字の語へまとめる直し（例: 甲乙丙→丁戊 のような形）は、
                # 打った読みから2字以上離れるなら1打の誤りでは届かない。元の語がどれも辞書の語なら戻して紫に（2026-11-07）
                shrink = True
            elif tag != 'replace' or b - a != d - c or not (kanji(line[a:b]) and kanji(done[c:d])):
                # 漢字だけの語（IME で変換した所）を、漢字＋送り仮名の別の語へ替える直し（多田家→叩き）も同じに見る。
                # 後ろに紫が無いときだけ（戻すと位置がずれる）。CN_KANJI_SWAP_WIDE=0 で前のまま
                kana_tail = lambda w: bool(w) and '一' <= w[0] <= '鿿' and all(
                    '一' <= x <= '鿿' or '\u3041' <= x <= '\u3096' for x in w)
                if (tag != 'replace' or os.environ.get('CN_KANJI_SWAP_WIDE') == '0' or b - a < 2
                        or not kanji(line[a:b]) or not kana_tail(done[c:d]) or kanji(done[c:d])
                        or any(o[1] > c for o in (result.get('odd_spans') or ()))
                        or any(o2[0] != 'equal' for o2 in ops[k + 1:])):
                    continue
                wide = True
            of = [t for t in tl if t.start < b and a < t.end]
            od = [t for t in td if t.start < d and c < t.end]
            if not of or not od or not all(t.has_reading for t in of + od):
                continue
            A, B, C, D = of[0].start, of[-1].end, od[0].start, od[-1].end
            if line[A:a] != done[C:c] or line[b:B] != done[d:D]:
                continue
            r1 = hira(''.join(t.reading for t in of))
            r2 = hira(''.join(t.reading for t in od))
            if sorted(r1) == sorted(r2):
                continue
            # 1字の漢字の語は、解析の読み（端 を はした）のほかに字の音訓（はし）でも読んで、近い方で見る
            # （打った記録の無い行: 端攻める は はしせめる と打った読みから 始める へ1打）。CN_KANJI_SWAP_ONKUN=0 で前のまま
            if os.environ.get('CN_KANJI_SWAP_ONKUN') != '0' and any(len(t.surface) == 1 for t in of):
                try:
                    import itertools
                    import ime_order
                    opts = [list(dict.fromkeys([hira(t.reading)] + (ime_order.readings_of(t.surface)
                                                                   if len(t.surface) == 1 and kanji(t.surface) else [])))
                            for t in of]
                    alts = [''.join(x) for x in itertools.islice(itertools.product(*opts), 32)]
                    r1 = min(alts, key=lambda x: (lev(x, r2), x != r1))
                except Exception:
                    pass
            # 用言は、解析の読み（描く=えがく・放す=ほかす）のほかに、その表記の持つ別の読み（かく・はなす）でも読んで
            # 近い方で見る（打った記録の無い行: 文章を描く は かく と打って IME が選び違えた所・2026-11-09 手分けA）。
            # CN_KANJI_SWAP_ALL_READINGS=0 で前のまま
            if os.environ.get('CN_KANJI_SWAP_ALL_READINGS') != '0' and lev(r1, r2) >= 2 \
                    and any(t.pos in ('動詞', '形容詞') for t in of + od):
                try:
                    import itertools
                    from morphology import dictionary_inflections

                    def _all_readings(toks):
                        opts = []
                        for t in toks:
                            rs = [hira(t.reading)]
                            if t.pos in ('動詞', '形容詞'):
                                for row in dictionary_inflections(getattr(t, 'base_form', '') or t.surface) or ():
                                    if row[0].startswith(t.pos + ',') and row[1] == (getattr(t, 'infl_form', '') or '') \
                                            and row[2] == t.surface and row[3] not in rs:
                                        rs.append(row[3])
                            opts.append(rs)
                        return [''.join(x) for x in itertools.islice(itertools.product(*opts), 32)]
                    # 同じ読みになる組（かく／かく）が在る時だけ、その読みで見る（いく→あく のような1字違いへは広げない:
                    # 行く→開く を通していた）
                    same = [(x, y) for x in _all_readings(of) for y in _all_readings(od) if x == y]
                    if same:
                        r1, r2 = same[0]
                except Exception:
                    pass
            if shrink:
                if lev(r1, r2) < 2 or len(of) < 2 or len(od) >= len(of):
                    continue
                bad.add(k)
                continue
            if lev(r1, r2) < 2 and wide:
                continue
            if lev(r1, r2) < 2:
                # 1字の読みの差でも、1字の漢字の語を1字の別の漢字の語へ替え、ずっと珍しい語になる直し（本→頬:
                # ほん→ほお）は、身近な語を珍しい語へ替えるだけの根拠が無い。戻して紫に。CN_KANJI_SWAP_RARER=0 で前のまま
                if (os.environ.get('CN_KANJI_SWAP_RARER') == '0' or len(of) != 1 or len(od) != 1
                        or len(of[0].surface) != 1 or len(od[0].surface) != 1):
                    continue
                if not (_R._token_rarity(of[0], tl) <= 400
                        and _R._token_rarity(od[0], td) - _R._token_rarity(of[0], tl) >= KANJI_SWAP_RARER_GAP):
                    continue
            if max(_R._token_rarity(t, tl) for t in of) > 600:
                continue
            bad.add(k)
        if not bad:
            return result
        new, odd_add = '', []
        for k, (tag, a, b, c, d) in enumerate(ops):
            if k in bad:
                odd_add.append((len(new), len(new) + b - a))
                new += line[a:b]
            else:
                new += done[c:d]
        out = dict(result)
        rest = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
        out['corrected'] = new
        out['changed'] = new != line
        out['spans'] = [[c, d] for _, a, b, c, d in rest]
        out['original_spans'] = [[a, b] for _, a, b, c, d in rest]
        out['details'] = [x for x in (result.get('details') or ()) if len(list(x)) < 2 or str(list(x)[1]) in new]
        out['odd_spans'] = sorted(set(tuple(o[:2]) for o in (result.get('odd_spans') or ())) | set(odd_add))
        out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
            (x, y, '漢字だけを読みの違う別の漢字に替える直しは入れていません') for x, y in odd_add]
        return out
    except Exception:
        return result


def _long_loan(line, result, decisions, input_method='kana'):
    """ひらがなの ー を含む外来語（めにゅー・めにょー → メニュー）を片仮名に（keyslip_window.long_loan_line・
    2026-11-09 手分けB）。格子で漢字を置く段の前に置き、前のかな（がくしゅう）は後ろの段が漢字にする。
    CN_KEYSLIP_LONG_LOAN=0 で前のまま。"""
    try:
        import keyslip_window
        return keyslip_window.long_loan_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _keyslip_window(line, result, decisions, input_method='kana'):
    """かな入力の1キーの打ち違い・巻き込みで崩れた語の並び（変度→返事・これカニら→これから）を打鍵の単位で戻す
    （keyslip_window・2026-11-08 手分けB）。CN_KEYSLIP_WINDOW=0 で前のまま。"""
    try:
        import keyslip_window
        out = keyslip_window.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result
    return out


def _head_tie(line, result, store, dict_index, decisions, input_method='kana'):
    """既知の頭＋紫の2字の漢語（一括＋流力）を、48-RK と同じ門で同点の候補を全部比べ、1つだけ通れば直す
    （head_tie・2026-11-09 手分けB）。CN_HEAD_TIE=0 で前のまま。"""
    if input_method != 'kana' or not result.get('odd_spans'):
        return result
    try:
        import head_tie
        return head_tie.repair_line(line, result, store, dict_index, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _dakuten_shift(line, result, decisions, input_method='kana'):
    """かな入力で ゛゜ を隣の字に付けた所（ばしめる → はじめる）を戻す（dakuten_shift・2026-11-08 補正担当）。
    CN_DAKUTEN_SHIFT=0 で前のまま。"""
    try:
        import dakuten_shift
        return dakuten_shift.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _pos_seq_odd(line, result, dict_index=None, decisions=None):
    """品詞の並びで必ず誤りになる所（格助詞の直後の接尾・文の途中の1字の感動詞・です の直後の動詞）を紫に（pos_seq_odd）。"""
    try:
        import pos_seq_odd
        return pos_seq_odd.mark_line(line, result, dict_index, decisions)
    except Exception:
        return result


def _pair_choice(line, result, decisions, input_method='kana'):
    """前後の語との組が例文に無く、同じ読みの別の名詞の組なら在る所（Tatoeba の語の組・pair_choice・2026-10-30）。"""
    try:
        import pair_choice
        return pair_choice.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _semantic_fit(line, result, decisions, input_method='kana'):
    """名詞と述語の意味の分類が噛み合わない所で、同じ読み・1打違いの読みの名詞から分類が合うものを選ぶ（semantic_fit・2026-11-07）。"""
    try:
        import semantic_fit
        return semantic_fit.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _learned_gate(line, result, store, decisions, input_method='kana'):
    """覚えた語がかなの欄の紫を消した所で、隣の名詞との組が辞書にも無く、1打違いのよく使う読みがあれば、かなに戻して紫に（learned_gate・2026-11-01）。"""
    try:
        import learned_gate
        return learned_gate.repair_line(line, result, store, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _rival_repair(line, result, decisions, input_method='kana'):
    """前の段が1打の戻しで替えた語を、打った読みのほかの1打の戻しと例文の組で比べ直す（rival_repair・2026-11-01）。"""
    try:
        import rival_repair
        return rival_repair.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _honorific_stem(line, result, decisions):
    """謙譲の お＋動詞の連用形＋する に同じ読みの普通名詞が入った所（お持ちします の 持ち の所に同じ読みの名詞が入った形・honorific_stem・2026-10-30）。"""
    try:
        import honorific_stem
        return honorific_stem.repair_line(line, result, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _question_ka(line, result, decisions):
    """疑問の語で始まる文の終わりの か が接尾の漢字（化）に変換された所を か に戻す（question_ka・2026-11-01）。"""
    try:
        import question_ka
        return question_ka.repair_line(line, result, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _yoon_slip(line, result, decisions, input_method='kana'):
    """付けられない字の後ろの ゃゅょ を、前の字を替えずに片付けた直しは採らず紫（yoon_slip・2026-11-01 B）。"""
    try:
        import yoon_slip
        return yoon_slip.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _keep_converted(line, result, decisions):
    """打ち違いの直しのついでに、打ち違いの無い語を読みの同じ別の表記に替えた所を戻す（keep_converted・2026-11-01）。"""
    try:
        import keep_converted
        return keep_converted.repair_line(line, result, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _broken_shape(line, result, decisions, input_method='kana'):
    """文の形として成り立たない並び（1打違いが別の字に変換されて残った所）に紫を付ける。かな入力で隣のキーの1字の足しと見える漢字1字は除いて直す（broken_shape・2026-11-01）。"""
    try:
        import broken_shape
        return broken_shape.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _te_dropped(line, result, decisions):
    """動詞の連用形＋補助の動詞（しまう・いる・おく など）の間の て の脱字を戻す（te_dropped・2026-11-01）。"""
    try:
        import te_dropped
        return te_dropped.repair_line(line, result, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _formal_noun_gap(line, result, decisions):
    """形式名詞（こと・もの）のすぐ後ろに名詞が来て用言に続く所に紫（formal_noun_gap・2026-11-01）。"""
    try:
        import formal_noun_gap
        return formal_noun_gap.repair_line(line, result, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _line_key_repair(line, result, decisions, input_method, run=None):
    """どの段も直さなかったローマ字の行を、打った読みの1打の戻しを IME で変換し直して直す（2026-11-04）。"""
    try:
        import ime_reconvert
        return ime_reconvert.line_key_repair(line, result, input_method, corrector._decided_spans(line, decisions),
                                             run)
    except Exception:
        return result


def _ime_reconvert(line, result, decisions, input_method):
    """世の中でめったに使わない漢字の語を、PC の IME で同じ読み・1打違いの読みから変換し直して疑う（ime_reconvert・2026-10-30）。"""
    try:
        import ime_reconvert
        return ime_reconvert.repair_line(line, result, input_method, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _dangling_verb(line, result, decisions):
    """後ろに て・た の続かない音便形の動詞（くだい）に抜けた1字を足す（dangling_verb・2026-10-26）。
    行の費用で1つに決まれば置く、並べば紫。"""
    try:
        import dangling_verb
        return dangling_verb.repair_line(line, result, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _degree_adverb(line, result, dict_index, decisions):
    """程度の副詞が受ける述語の無い名詞にかかる所（とても思い→とても重い・degree_adverb・2026-10-26）。
    同じ読みの形容詞が1つに決まれば置く、決まらなければ紫。"""
    try:
        import degree_adverb
        return degree_adverb.repair_line(line, result, dict_index, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _renyou_tail_slip(line, result, decisions, input_method):
    """動詞の連用形＋説明の付かない短い尾（つくり｜のす）の尾の1字を隣のキーに替えると助動詞の尾になる所
    （renyou_tail_slip・2026-10-25）。候補1つなら置く。かな入力だけ。"""
    if input_method != 'kana':
        return result
    try:
        import renyou_tail_slip
        return renyou_tail_slip.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _stroke_repairs(line, result, strokes, input_method, run, convert):
    """中身のないシフト（shift_slip・かな入力）を先に、直らなければ押した間隔の短い2打（keystroke_doubt）を見る。"""
    import keystroke_doubt
    try:
        import shift_slip
        out = shift_slip.repair_line(line, result, strokes, input_method, run, convert)
        if out is not result:
            return out
    except Exception:
        pass
    return keystroke_doubt.repair_line(line, result, strokes, input_method, run, convert)


def _correct_line_halfwidth(line, store, context_vocab=None, decisions=None,
                            input_method='kana', context_vec=None, dict_index=None,
                            nearby_words=(), recent_words=(), occurrence_readings=(), occurrence_calculations=()):
    """ローマ字入力の全角の英字を半角に見てから _correct_line へ。"""
    if input_method == 'romaji' and any(ch in _FULLWIDTH_LOWER or ch in _SYMBOL_LETTER for ch in line):
        half = _halfwidth_letters(line)
        if half != line:
            result = _correct_line(half, store, context_vocab=context_vocab, decisions=decisions,
                                   input_method=input_method, context_vec=context_vec, dict_index=dict_index,
                                   nearby_words=nearby_words, recent_words=recent_words,
                                   occurrence_readings=occurrence_readings,
                                   occurrence_calculations=occurrence_calculations)
            done = result.get('corrected', half)
            try:
                from last_keystroke import _only_drops_keys
                drops = done != half and _only_drops_keys(half, done)
            except Exception:
                drops = False
            if drops:
                # 全角で残った英字は、IME が子音の続き（tm・kr）を音にできずに残したもの。打鍵の順の入れ替わりの跡が
                # 多く、英字を抜くだけの戻しは別の語を作る（食うｔを→食うを・さｋらが→さかが。PC の本物の IME の顔で、
                # 全角の行の抜くだけの直しは10件とも誤り）。直さず、残った英字に紫（迷うなら紫）
                spans = [(i, i + 1) for i, ch in enumerate(line)
                         if (ch in _FULLWIDTH_LOWER or ch in _SYMBOL_LETTER) and half[i] != ch]
                return {**result, 'corrected': line, 'changed': False, 'details': [], 'spans': [],
                        'original_spans': [], 'unsure_spans': [], 'odd_spans': spans,
                        'odd_reasons': [(a, b, f'「{line[a:b]}」はかなの中に残った英字です') for a, b in spans]}
            return _restore_fullwidth(line, half, result)
    return _correct_line(line, store, context_vocab=context_vocab, decisions=decisions,
                         input_method=input_method, context_vec=context_vec, dict_index=dict_index,
                         nearby_words=nearby_words, recent_words=recent_words,
                         occurrence_readings=occurrence_readings, occurrence_calculations=occurrence_calculations)


def _correct_line(line, store, context_vocab=None, decisions=None,
                  input_method='kana', context_vec=None, dict_index=None,
                  nearby_words=(), recent_words=(), occurrence_readings=(), occurrence_calculations=()):
    """
    補正エンジンの入口。

    補正の判断は corrector.py に集約されている。
    （以前は補正経路が複数並列に存在し、片方に安全策を入れても
      別の経路が同じ誤りを通してしまう構造だったため、
      正しい日本語を壊す誤補正が頻発した。単一経路に作り直した。）

    decisions には、ユーザーが補正結果をクリックして示した
    「この補正は不要」という判断が入る。

    context_vec には、語の共起から作った軽量な文脈ベクトル
    （context_vec.ContextVectorStore）を渡せる。同じ読みに
    複数の有力な表記がある場合に、周辺の語と意味的に馴染む方を
    選ぶ追加の手がかりとして使う（無くても動く）。

    dict_index には janome 辞書の読み索引を渡せる。
    「素帰任」のような、語として成立しない漢字列を読みに戻して
    推測する際に、漢字1文字の読みを引くのに使う（無くても
    自前の単漢字読み表で動く）。
    """
    from literal_lines import literal_only,result as literal_result
    if literal_only(line):return literal_result(line)
    # トークナイザは毎回作り直さずに使い回す（行ごとに作ると遅い）
    fn = getattr(store, '_tokenize_fn', None)
    if fn is None:
        fn = corrector.make_tokenizer(store)
        store._tokenize_fn = fn
    with current_input(line,occurrence_readings):
        from ime_session import resource_scope
        from ime_colloquial import source_tokenizer
        with resource_scope():
            tokenize_fn = source_tokenizer(line, fn)
            result = corrector.correct_line(
                line, store, tokenize_fn, find_known_readings_flex,
                context_vocab=context_vocab, decisions=decisions,
                input_method=input_method, context_vec=context_vec,
                dict_index=dict_index, nearby_words=nearby_words,
                recent_words=recent_words)
            result = _readable_unsure(line, result, tokenize_fn)
            result = _explained_kana_revert(line, result)
    # 1行に誤字が2つ以上あると、1つ目を直した行で初めて2つ目の印が立つ（作った例: 2つ目の語の打ち違いが1つ目の直しの後に見える行）。
    # 直した行をもう1度だけ通し、1つ目の直しと重ならない直しだけを元の行の位置に戻して足す
    if result.get('changed') and result.get('corrected') and result['corrected'] != line:
        with current_input(result['corrected'],()):
            from ime_session import resource_scope
            from ime_colloquial import source_tokenizer
            import last_keystroke as _lk
            # 最後の打鍵の読み直しは、直した行にまだ印（紫・異様）が残るときだけ
            # もう1度通す。印の無い行は入口だけ（読み直しは1行に1度）
            # 漢字をかなに開いただけの直し（撮った→とった）が混じる行も、もう1度通す
            _opened = any(isinstance(d, (list, tuple)) and len(d) >= 2 and d[0] and d[1]
                          and any('一' <= c <= '鿿' for c in d[0])
                          and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in d[1])
                          for d in result.get('details') or ())
            _still_odd = bool(result.get('odd_spans') or result.get('unsure_spans') or _opened)
            _lk_token = _lk._ACTIVE.set(not _still_odd)
            try:
                with resource_scope():
                    again = corrector.correct_line(
                        result['corrected'], store, source_tokenizer(result['corrected'], fn),
                        find_known_readings_flex,
                        context_vocab=context_vocab, decisions=decisions,
                        input_method=input_method, context_vec=context_vec,
                        dict_index=dict_index, nearby_words=nearby_words,
                        recent_words=recent_words)
            finally:
                _lk._ACTIVE.reset(_lk_token)
        result = _merge_second_pass(line, result, again)
    # 打ち間違えた読みがそのまま辞書の語になる形（本字を書いて→返事を書いて）を語の組で見る
    from collocation_repair import apply as _collocation_apply
    result = _collocation_apply(line, result, input_method, decisions)
    # 1打の打ち違いを IME が漢字の語にした跡（新しい阿久津を買った・撮った地）に紫だけを足す（答えは変えない）
    from last_keystroke import mark_stray_kanji as _mark_stray_kanji
    with current_input(line, occurrence_readings):
        result = _mark_stray_kanji(line, result, store, dict_index, input_method, decisions)
    # 音と活用の決まりでありえないかなの並び（進まなぃ・なっだ・残つて・しているる）にも紫だけ
    from last_keystroke import mark_impossible_kana as _mark_impossible_kana
    result = _mark_impossible_kana(line, result, input_method, decisions)
    # 直せずに残った行で、動詞の連用形に語にならない名詞が続く所（寝クス・出かけ牟田）と
    # かなの間のカタカナ1字（降るラ沿い）に紫だけを足す
    if result.get('corrected', line) == line:
        import oddness as _odd
        _extra = [sp for sp in _odd.renyou_stray_noun_spans(line, fn) + _odd.stray_katakana_letter_spans(line)
                  if not any(a < sp[1] and sp[0] < b for a, b in result.get('odd_spans') or ())
                  # 本人が「直さない」と決めた文字列（protect・reject）には足さない
                  and not any(a < sp[1] and sp[0] < b for a, b in corrector._decided_spans(line, decisions))]
        if _extra:
            result = dict(result)
            result['odd_spans'] = sorted(list(result.get('odd_spans') or ()) + _extra, key=lambda sp: tuple(sp[:2]))
            result['odd_reasons'] = list(result.get('odd_reasons') or ()) + [
                (a, b, f'「{line[a:b]}」は動詞の後ろに語にならない名詞が続いています' if b - a > 1 else f'「{line[a:b]}」はかなの間に紛れたカタカナ1字です') for a, b in _extra]
    # ローマ字の隣り合う2打の入れ替わり（さあから→あさから）を紫の範囲の中で戻す（ローマ字入力だけ）
    from romaji_swap_repair import apply as _romaji_swap_apply
    result = _romaji_swap_apply(line, result, input_method, store, dict_index, decisions)
    result = _mark_impossible_connections(line, result)
    result = _keep_function_kana(line, result)
    if input_method == 'romaji':
        result = _mark_leftover_letters(line, result)
    if occurrence_calculations:
        from quote_calculator import apply_to_result
        result = apply_to_result(result, occurrence_calculations, decisions, fn, dict_index)
    return result


def _function_kana(token):
    """かなで書くのが自然な働きの語か: 形式名詞（名詞・非自立）・補助の動詞（動詞・非自立）・接続詞。"""
    return ((token.pos == '名詞' and token.pos_sub.startswith('非自立'))
            or (token.pos == '動詞' and token.pos_sub.startswith('非自立'))
            or token.pos == '接続詞')


def _keep_function_kana(line, result):
    """
    かなで書いた形式名詞・補助の動詞・接続詞を、**同じ読みのまま漢字に替えるだけ**の直しを戻す（2026-10-24・うにさん
    「ところで が漢字になったが平仮名のままが自然」）。打ち違いの直し（読みが変わる）はそのまま。語は名指ししない
    （品詞の細分類で決める）。戻した所は直しから外す。
    """
    import os
    if os.environ.get('CN_FUNCTION_KANA') == '0' or not result:
        return result
    done = result.get('corrected') or line
    if done == line:
        return result
    try:
        import difflib
        from morphology import tokenize
        toks = tokenize(line)
    except Exception:
        return result
    hira = str.maketrans({chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)})
    def kana(ch): return '\u3041' <= ch <= '\u309f' or ch == 'ー'
    def reading(text):
        try:
            return ''.join((t.reading if t.has_reading else t.surface).translate(hira) for t in tokenize(text))
        except Exception:
            return None
    def can_read(text, target):
        """text の語のどれかの読み（辞書にある読みも）を並べて target になりうるか（処 → ところ）。"""
        try:
            from morphology import dictionary_inflections
            heads = {''}
            for t in tokenize(text):
                rds = {(t.reading if t.has_reading else t.surface).translate(hira)}
                if any('\u4e00' <= c <= '\u9fff' for c in t.surface):
                    rds |= {rd.translate(hira) for _p, _f, _b, rd in (dictionary_inflections(t.surface) or ()) if rd}
                heads = {h + r for h in heads for r in rds if target.startswith(h + r)}
                if not heads or len(heads) > 64: return False
            return target in heads
        except Exception:
            return False
    ops = difflib.SequenceMatcher(None, line, done, autojunk=False).get_opcodes()
    out, changed = [], False
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            out.append(done[j1:j2]); continue
        keep = True
        hit = [t for t in toks if t.start < max(i2, i1 + 1) and i1 < t.end]
        # かなで書いた1語の一部だけを、同じ読みの漢字に替える直し（くだい→く台）も戻す（語を割る）
        split = False
        if (len(hit) == 1 and all(kana(c) for c in hit[0].surface)
                and (i1 > hit[0].start or i2 < hit[0].end)):
            # 直した後、その語の所が2語以上に割れる（く＋台）ときだけ。送り仮名の付いた語（たべ→食べ）は1語のまま
            a, b = hit[0].start, hit[0].end
            na, nb = j1 - (i1 - a), j2 + (b - i2)
            try:
                parts = [t for t in tokenize(done) if t.start < nb and na < t.end]
            except Exception:
                parts = []
            split = len(parts) > 1
        # 直した所の語がすべて働きの語のときだけ（の｜き｜かい のように解析が割っただけの語＝機械 は戻さない）
        if split or (hit and all(_function_kana(t) and all(kana(c) for c in t.surface) for t in hit)):
            a, b = min(t.start for t in hit), max(t.end for t in hit)
            # 前後の同じ所まで広げて、語の単位で読みを比べる
            if a >= i1 - 8 and b <= i2 + 8 and line[a:i1] == done[j1 - (i1 - a):j1] and line[i2:b] == done[j2:j2 + (b - i2)]:
                old_seg, new_seg = line[a:b], done[j1 - (i1 - a):j2 + (b - i2)]
                ro, rn = reading(old_seg), reading(new_seg)
                if ro and (ro == rn or can_read(new_seg, ro)) and any('\u4e00' <= c <= '\u9fff' for c in done[j1:j2]):
                    keep = False
        if keep and j2 > j1:
            # 直した所に、後ろに語を要する語（連体詞・接頭詞: 我が）が来て、その後ろに語が無い（行末・記号）なら戻す
            # （呼ぶ側→呼ぶ我が。どの道の直しでも、文として成り立たない形は採らない。2026-10-24・うにさんの誤判定）
            try:
                new_toks = list(tokenize(done))
            except Exception:
                new_toks = []
            for k, t in enumerate(new_toks):
                if t.start < j2 and j1 < t.end and t.pos in ('連体詞', '接頭詞'):
                    nxt = new_toks[k + 1] if k + 1 < len(new_toks) else None
                    if nxt is None or nxt.pos == '記号':
                        keep = False
                        break
        if keep:
            out.append(done[j1:j2])
        else:
            out.append(line[i1:i2]); changed = True
    if not changed:
        return result
    text = ''.join(out)
    out_result = dict(result)
    out_result['corrected'] = text
    if text == line:
        out_result.update(changed=False, details=[], spans=[], original_spans=[])
        return out_result
    spans, original_spans = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes():
        if tag != 'equal':
            spans.append([j1, j2]); original_spans.append([i1, i2])
    out_result['spans'], out_result['original_spans'] = spans, original_spans
    out_result['details'] = [d for d in (result.get('details') or ())
                             if not (isinstance(d, (list, tuple)) and len(d) >= 2 and d[1] and d[1] not in text)]
    return out_result


def _mark_impossible_connections(line, result):
    """
    **いまの日本語では起こらない品詞のつながり**に紫を足す（2026-10-23・補正C）。
    印だけ。補正の本体（最後の打鍵の読み直しは紫を入口にする）の外で足す——
    中で足すと、紫を消すためだけの直し（週につに→週にもつに）が通った（実測）。
    直した範囲と重なる所には付けない。判定は pos_grammar の1本。
    """
    import os
    if os.environ.get('CN_POS_ODD') == '0' or not result:
        return result
    try:
        from pos_grammar import _impossible_connection_spans
        spans = _impossible_connection_spans(line)
    except Exception:
        return result
    done = [tuple(sp[:2]) for sp in (result.get('original_spans') or ())]
    odd = list(result.get('odd_spans') or ())
    added = False
    # 混ぜ書きの片仮名の名詞（スくりーん）の中の切れ目は品詞のつながりではない（2026-11-03）
    if os.environ.get('CN_POS_ODD_MIXED') != '0':
        try:
            import broken_shape as _bs
            mixed = _bs.mixed_katakana_spans(line)
        except Exception:
            mixed = []
        spans = [(a, b) for a, b in spans if not any(s <= a and b <= e for s, e in mixed)]
    for a, b in spans:
        # 直した範囲と重なる所・その2字の内には付けない（直しの跡の語の切れ目は当てにならない: 風がつょい→風がつよい）
        if any(a < e + 2 and s - 2 < b for s, e in done) or any(tuple(o[:2]) == (a, b) for o in odd):
            continue
        # 元からの紫の中に入る所は足さない（スくりーん の ー: 外の紫で足りる・2026-11-03 tests_mixed_nominal_argument）
        if os.environ.get('CN_POS_ODD_NESTED') != '1' and any(o[0] <= a and b <= o[1] for o in odd):
            continue
        odd.append((a, b))
        added = True
    corrected = result.get('corrected') or line
    if corrected != line:
        # 直した行の上でも見る。元の行では直しの跡（作った例: 余った゛）の隣で語の切れ目が当てにならず見送った所
        # （名詞＋に＋打ち違えた動詞）も、直した行では本当の続き。直した所に重なる所・すぐ隣は見ない。
        # 位置は元の行に写す（2026-10-30・補正担当）
        try:
            fixed_spans = _impossible_connection_spans(corrected)
            if os.environ.get('CN_POS_ODD_MIXED') != '0':
                import broken_shape as _bs
                mixed2 = _bs.mixed_katakana_spans(corrected)
                fixed_spans = [(a, b) for a, b in fixed_spans if not any(s <= a and b <= e for s, e in mixed2)]
        except Exception:
            fixed_spans = []
        import difflib
        ops = difflib.SequenceMatcher(None, line, corrected, autojunk=False).get_opcodes()
        changed = [(j1, j2) for tag, i1, i2, j1, j2 in ops if tag != 'equal']
        for a, b in fixed_spans:
            if any(a < e + 1 and s - 1 < b for s, e in changed):
                continue
            org = None
            for tag, i1, i2, j1, j2 in ops:
                if tag == 'equal' and j1 <= a and b <= j2:
                    org = (a - j1 + i1, b - j1 + i1)
            if org is None or any(o[0] < org[1] and org[0] < o[1] for o in odd):
                continue
            odd.append(org)
            added = True
    if not added:
        return result
    out = dict(result)
    out['odd_spans'] = odd
    return out


def _mark_leftover_letters(line, result):
    """
    ローマ字で、かなの中に残った小文字の英字（最後の打鍵の読み直しが「打ち違いの確かな印」として見る所）を、
    直さなかったときに紫にする（2026-10-23・補正C）。読み直しは、英字を抜く戻しと英字を残して読む戻しが
    並ぶと決めない（かzこうで・やsみます）。迷うなら直さず紫。直した行には付けない。
    """
    if not result or result.get('corrected', line) != line:
        return result
    try:
        from last_keystroke import _letter_span
        if _letter_span(line) is None:
            return _mark_stray_latin(line, result)
    except Exception:
        return result
    k = [i for i, ch in enumerate(line) if ch.isascii() and ch.isalpha()]
    a, b = k[0], k[-1] + 1
    odd = list(result.get('odd_spans') or ())
    if any(s < b and a < e for s, e, *_ in odd):
        return result
    out = dict(result)
    out['odd_spans'] = odd + [(a, b)]
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + [(a, b, f'「{line[a:b]}」はかなの中に残った英字です')]
    return out


def _latin(ch):
    return ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('ａ' <= ch <= 'ｚ') or ('Ａ' <= ch <= 'Ｚ')


def _japanese(ch):
    return 'ぁ' <= ch <= 'ゖ' or 'ァ' <= ch <= 'ヶ' or '一' <= ch <= '鿿' or ch in 'ー々'


def _mark_stray_latin(line, result):
    """ローマ字入力で、日本語の字に挟まれたか行頭・行末で日本語の字に付いた1〜2字の小文字の英字（全角の英字も）が
    残った所を紫にする（ｑ明日は・ｈｙエアが。かなの中の英字は _letter_span の受け持ち・2026-11-04 Store 登録スレッドの測り）。
    英語の語（3字以上・大文字を含む・英数字の続き）は見ない。"""
    import os
    if os.environ.get('CN_STRAY_LATIN') == '0':
        return result
    odd = list(result.get('odd_spans') or ())
    reasons = list(result.get('odd_reasons') or ())
    added = False
    i = 0
    while i < len(line):
        if not _latin(line[i]):
            i += 1
            continue
        j = i
        while j < len(line) and _latin(line[j]):
            j += 1
        run = line[i:j]
        before = line[i - 1] if i else ''
        after = line[j] if j < len(line) else ''
        lower = all(c.islower() for c in run)
        if (j - i <= 2 and lower and (_japanese(before) or _japanese(after))
                and not (before and (before.isalnum() and not _japanese(before)))
                and not (after and (after.isalnum() and not _japanese(after)))
                and not any(o[0] < j and i < o[1] for o in odd)):
            odd.append((i, j))
            reasons.append((i, j, f'「{run}」は日本語の中に残った英字です'))
            added = True
        i = j
    if not added:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(tuple(o[:2]) for o in odd)
    out['odd_reasons'] = reasons
    return out


def _merge_second_pass(line, first, second):
    """2回目の直し（1回目の直した行の上）を、1回目と重ならないものだけ元の行の位置に写して足す。"""
    if not second.get('changed') or second.get('corrected') == first.get('corrected'):
        return first
    # 段によって位置が tuple と list の両方で来る（並べると比べられず落ちた・2026-11-02）。tuple にそろえる
    pairs = sorted((tuple(x[:2]), tuple(y[:2])) for x, y in zip(first.get('spans') or (), first.get('original_spans') or ()))
    if len(pairs) != len(first.get('details') or ()):
        return first

    def to_original(a, b):
        delta = 0
        for (s, e), (os_, oe) in pairs:
            if a < e and s < b or (s == e and a <= s <= b and a < b):
                return None
            if e <= a:
                delta += (oe - os_) - (e - s)
        return a + delta, b + delta

    rows = list(zip(second.get('details') or (), second.get('spans') or (), second.get('original_spans') or ()))
    if not rows or len(rows) != len(second.get('details') or ()):
        return first
    mapped = []
    for detail, span, orig in rows:
        o = to_original(*orig)
        if o is None:
            return first
        mapped.append((detail, span, o))

    def shift(a, b):
        # 1回目の直した行の位置を、2回目の直しの後の行の位置へ
        delta = 0
        for _, (s2, e2), (s1, e1) in rows:
            if e1 <= a:
                delta += (e2 - s2) - (e1 - s1)
        return a + delta, b + delta

    merged = dict(first)
    merged['corrected'] = second['corrected']
    items = [(o, sh, d) for d, (sh, o) in ((d, (shift(*sp), o)) for (d, sp, o) in
             zip(first.get('details') or (), first.get('spans') or (), first.get('original_spans') or ()))]
    items += [(o, sp, d) for d, sp, o in mapped]
    items.sort(key=lambda x: tuple(x[0][:2]))
    merged['details'] = [d for _, _, d in items]
    merged['spans'] = [sp for _, sp, _ in items]
    merged['original_spans'] = [o for o, _, _ in items]
    moved = [o for _, _, o in mapped]

    def back(spans):
        out = []
        for sp in spans or ():
            o = to_original(*tuple(sp[:2]))
            if o is not None:
                out.append(o)
        return out
    for key in ('odd_spans', 'unsure_spans'):
        kept = [sp for sp in (first.get(key) or ()) if not any(sp[0] < b and a < sp[1] for a, b in moved)]
        merged[key] = kept + [o for o in back(second.get(key)) if o not in kept]
    return merged


# 補正の各段が使われたか・効果があったかを数える（数だけ。答えは変えない。2026-10-24・usage_counts）
try:
    import usage_counts as _usage_counts
    _usage_counts.install()
except Exception:
    pass

# 使った材料のキーを記録する入口（used_keys・答えは変えない）
try:
    import used_keys as _used_keys_mod
    _used_keys_mod.install()
except Exception:
    pass


# 同じ1行の中で、同じ「2か所打ち違いの組」の探索をやり直さない（2026-11-10 全体評価 A2・pair_search_memo.py。速さだけで
# 答えは変えない）。CN_PAIR_SEARCH_MEMO=0 で前のまま
try:
    import pair_search_memo as _pair_search_memo
    _pair_search_memo.install()
except Exception:
    pass


# ホームポジションのずれ（片手が横に1キーずれて同じ向きに続けて打ち違う）の候補を広げる（2026-11-10 全体評価・
# hand_shift_wide.py、うに 08:09Z「ホームポジションのずれによる連続ミス」）。CN_HAND_SHIFT_WIDE=0 で前のまま
try:
    import hand_shift_wide as _hand_shift_wide
    _hand_shift_wide.install()
except Exception:
    pass


# ホームポジションのずれ（片手が横に1キーずれて同じ向きに続けて打ち違う）を keyslip_window の1キーの戻しの候補にも足す
# （2026-11-10 全体評価・hand_shift_window.py、うに 08:09Z）。CN_HAND_SHIFT_WINDOW=0 で前のまま
try:
    import hand_shift_window as _hand_shift_window
    _hand_shift_window.install()
except Exception:
    pass


# 読み直しの候補を、補正に通す前に行の並びの費用で絞る（どうせ採られない候補を先に落とす・答えは同じ。2026-11-10 全体評価・
# pass_screen.py）。CN_PASS_SCREEN=0 で前のまま
try:
    import pass_screen as _pass_screen
    _pass_screen.install()
except Exception:
    pass
