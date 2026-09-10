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

"""原文の異様範囲・文脈・読み・打鍵を保った補正。

辞書や誤字の正解表を持たない。既存の異様判定を先に受け取り、
原文座標を動かさず候補を検算する。候補を見つけたことは異様の根拠にしない。
"""
from dataclasses import dataclass, asdict
from functools import lru_cache
import re
import unicodedata


_SEPARATOR = re.compile(r'[\t\r\n。！？!?;；⇒→]|\s{2,}')


@dataclass(frozen=True)
class RepairTarget:
    source: str
    start: int
    end: int
    context_start: int
    context_end: int
    anomalies: tuple
    structural: bool
    following: str
    boundary_kind: str = 'lexical'
    preserved_head: str = ''

    @property
    def text(self):
        return self.source[self.start:self.end]

    @property
    def context(self):
        return self.source[self.context_start:self.context_end]

    def substitute(self, surface):
        return (self.source[self.context_start:self.start] + surface
                + self.source[self.end:self.context_end])


@dataclass(frozen=True)
class Reading:
    text: str
    source: str
    rank: int
    segments: tuple = ()


@dataclass(frozen=True)
class KeyRepair:
    reading: str
    operation: str
    position: int
    pressed: str
    intended: str
    cost: float


def _kana(text):
    return ''.join(chr(ord(c)-0x60) if 'ァ' <= c <= 'ヶ' else c for c in text)


def _is_reading(text):
    return bool(text) and all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in text)


def _case_boundary(t):
    return t[1].startswith(('助詞:格助詞', '助詞:係助詞', '助詞:連体化'))


def _literal_boundary(t):
    return any(c.isascii() and (c.isalnum() or c in '+_') for c in t[0])


def _kana_grammar_boundary(parts, begin, finish):
    """かなの語の断片と、辞書活用で確定できる接続不一致を分ける。

    語の内部の読み探索は既存経路に残す。語をまたぐ活用の不一致は
    漢字表記と同じ原文範囲で検査する。異様判定そのものは共有する。
    """
    import oddness
    for i in range(1, len(parts)):
        a, b = parts[i-1], parts[i]
        if a[3] >= finish or b[4] <= begin:
            continue
        if oddness.polite_aux_mismatch(a, b):
            return True
        if not (oddness.causative_aux_mismatch(a, b)
                or oddness.passive_aux_mismatch(a, b)
                or oddness.auxiliary_te_mismatch(a, b)
                or oddness.orphan_sokuon_mismatch(a, b, parts[i-2] if i>1 else None)):
            continue
        # かなは語中も動詞・助動詞へ割れやすい。接尾の一字を見ただけで
        # 語内探索から奪わず、述語としての明示的な語尾まである範囲を移す。
        if b[0] in ('せる','させる','れる','られる','いる','おる') and b[6]=='基本形':
            return True
        if i+1 < len(parts):
            c=parts[i+1]
            if c[3]!=b[4] or not c[5]:
                continue
            if c[1].startswith('助詞:接続助詞') and c[0] in ('て','で','つつ','ながら'):
                return True
            if c[1].startswith('助動詞'):
                from morphology import dictionary_inflections
                if any(p.startswith('助動詞,') and base in ('ます','た','ない','たい','ぬ','ん','う')
                       for p,form,base,rd in dictionary_inflections(c[0]) or ()):
                    return True
    return False


def targets_for_line(line, tokenize, store, dictionary):
    """候補生成前に、異様を含む文節と、その接続を判断する文脈を固定する。"""
    import oddness
    targets = []
    boundaries = [0]
    for m in _SEPARATOR.finditer(line):
        boundaries.extend((m.start(), m.end()))
    boundaries.append(len(line))
    for lo, hi in zip(boundaries[::2], boundaries[1::2]):
        clause = line[lo:hi]
        if not clause:
            continue
        parts = list(tokenize(clause))
        odd = oddness.is_odd_run(clause, tokenize, with_spans=True,
                                store=store, dict_index=dictionary, complete_line=True)
        if not odd:
            continue
        strong = set(tuple(p) for p in oddness.is_odd_run(
            clause, tokenize, with_spans=True, store=store, dict_index=dictionary,
            skip_join=True, complete_line=True))
        for a, b, start, end in odd:
            hit = [i for i, t in enumerate(parts) if t[3] < end and start < t[4]]
            if not hit:
                continue
            first, last = hit[0], hit[-1]
            # 異様な格助詞の連続では、先の助詞は文節境界、後の助詞は
            # 誤って分割された語頭かもしれない。正しい「には」等は odd にない。
            if (first < last and _case_boundary(parts[first])
                    and _case_boundary(parts[first+1])
                    and any(x[2] == parts[first][3] and x[3] == parts[first+1][4]
                            for x in strong)):
                first += 1
            while (first and not _case_boundary(parts[first-1])
                   and not _literal_boundary(parts[first-1])
                   and not parts[first-1][1].startswith(('記号', '助詞:接続助詞'))):
                if parts[first-1][4] != parts[first][3]:
                    break
                first -= 1
            # 接続助詞/格助詞より前の語は途中の文字種境界で切らない。
            while last+1 < len(parts):
                nxt = parts[last+1]
                if (parts[last][4] != nxt[3] or _case_boundary(nxt) or _literal_boundary(nxt)
                        or nxt[1].startswith(('記号', '助詞:接続助詞'))):
                    break
                last += 1
            # 隣の異様な接続を、別の短い対象を作ることで切り捨てない。
            if (first >= 2 and _case_boundary(parts[first-1])
                    and _case_boundary(parts[first-2])
                    and any(x[2] == parts[first-2][3] and x[3] == parts[first-1][4]
                            for x in strong)):
                first -= 1
            begin, finish = parts[first][3], parts[last][4]
            # 読む範囲と検査する範囲を分ける。するの活用は原文のまま検査に残す。
            for i in range(first+1, last+1):
                t = parts[i]
                if (t[0] in ('し', 'する', 'すれ', 'せよ') and t[1].startswith('動詞')
                        and t[3] >= start and (i == last or
                            parts[i+1][1].startswith(('助詞', '助動詞')))):
                    finish = t[3]
                    break
                if (t[1].startswith('助動詞') and
                        (parts[i-1][1].startswith(('動詞', '形容詞'))
                         or t[0] in ('ます', 'まし', 'ませ', 'ましょ', 'です', 'でし', 'でしょ'))):
                    finish = t[3]
                    break
            # 異様の印が接続の両側を含んでも、読む本文は格助詞を越えない。
            for i in range(first+1, last+1):
                if _case_boundary(parts[i]) or parts[i][1].startswith(('記号', '助詞:接続助詞')):
                    finish = min(finish, parts[i][3])
                    break
            if (_case_boundary(parts[first]) and first < last
                    and parts[first+1][5] and parts[first+1][1].startswith('動詞')
                    and parts[first+1][6].startswith('連用') and first+2 < len(parts)
                    and parts[first+2][1].startswith('助動詞')):
                finish = min(finish, parts[first][4])
            # 未知のかな語が格助詞まで一語に飲み込まれても、その後ろの
            # 既知の述語は読み直す本文ではなく検査の文脈に残す。
            for i in range(first, last):
                t, nxt = parts[i], parts[i+1]
                if (not t[5] and _is_reading(t[0]) and len(t[0]) >= 2
                        and t[0][-1] in ('を', 'に', 'へ', 'が')
                        and nxt[5] and (nxt[1].startswith(('動詞', '形容詞')) or
                            (nxt[1].startswith('名詞:サ変接続') and i+2 < len(parts)
                             and parts[i+2][0] in ('し', 'する', 'すれ')
                             and parts[i+2][1].startswith('動詞')))):
                    finish = min(finish, t[4]-1)
            untrimmed_begin = begin
            # 文頭の時点・数量等の副詞的名詞は後続の未知語と一語にしない。
            if (first < last and parts[first][1].startswith('名詞:副詞可能')
                    and parts[first][5]):
                begin = parts[first+1][3]
            # 引用記号自体は候補の綴りに含めず、原文のまま外へ残す。
            while begin < finish and clause[begin] in "`\"'「『（(【[":
                begin += 1
            while begin < finish and clause[finish-1] in "`\"'」』）)】]":
                finish -= 1
            structural = any(x[2] < finish and begin < x[3] for x in strong)
            # 原文で活用接続が異様なら、漢字2字の語も調べる。
            # 読みの長さと漢字の文字数を取り違えて入口を落とさない。
            single_polite=(finish-begin==1 and structural and any(
                parts[i-1][3]==begin and parts[i][3]==finish
                and oddness.polite_aux_mismatch(parts[i-1],parts[i])
                for i in range(1,len(parts))))
            if (not (1 <= finish-begin <= 18) or finish <= start
                    or (finish-begin==1 and not single_polite)
                    or (finish-begin==2 and not structural)):
                continue
            text = clause[begin:finish]
            # 全かなでも、活用の接続が崩れた範囲は同じ検査へ通す。
            # 語の途中で切れたという印だけで従来の語内探索を置き換えない。
            if (not any('一' <= c <= '鿿' or 'ァ' <= c <= 'ヶ' for c in text)
                    and not _kana_grammar_boundary(parts, begin, finish)):
                continue
            # 見慣れない普通名詞の連接だけなら、従来の証拠を持つ経路に委ねる。
            relevant = [t for t in parts if t[3] < finish and begin < t[4]]
            if not structural and all(t[5] and t[1].startswith('名詞') for t in relevant):
                continue
            anomalies = tuple((x, y, lo+s, lo+e) for x, y, s, e in odd
                              if s < finish and begin < e)
            following = clause[finish:]
            target = RepairTarget(line, lo+begin, lo+finish, lo, hi,
                                  anomalies, structural, following)
            if target not in targets:
                targets.append(target)
            # 副詞可能という最上位の解析だけで、語頭を捨てない。
            # 誤変換で副詞的名詞になった場合に備え、元の広い範囲を先に
            # 検査する。成立する候補が無ければ、時点等を文脈に残す範囲へ。
            if untrimmed_begin < begin and finish-untrimmed_begin <= 18:
                full = RepairTarget(line,lo+untrimmed_begin,lo+finish,lo,hi,
                    tuple((x,y,lo+s,lo+e) for x,y,s,e in odd
                          if s<finish and untrimmed_begin<e),
                    structural,following)
                if full not in targets:
                    targets.append(full)
            # 正しい助動詞は検査文脈へ残す。一方、原文で接続できない
            # 助動詞はそれ自身の誤打もあり得るため、語尾まで含む別範囲を
            # 控える。接続全体を先に比較し、語尾の誤打を見落とさない。
            for i in range(1,len(parts)):
                b=parts[i]
                if b[3]!=finish or not oddness.polite_aux_mismatch(parts[i-1],b):
                    continue
                extended=b[4]
                for c in parts[i+1:]:
                    if c[3]!=extended or not c[1].startswith(('助動詞','助詞:接続助詞')):
                        break
                    extended=c[4]
                if extended-begin>18:
                    break
                a=parts[i-1]
                head=(a[0] if a[3]==begin and a[1].startswith('名詞:サ変接続') else '')
                extra=RepairTarget(line,lo+begin,lo+extended,lo,hi,anomalies,
                                   structural,clause[extended:],'auxiliary_connection',head)
                if extra not in targets:
                    targets.append(extra)
                # 助動詞の前が短い名詞へ誤変換されると、直前の「へ/に」も
                # 語中のかなを切り取った境界になり得る。元の助動詞接続が
                # 明らかに崩れた場合だけ、前の名詞一語と境界まで検算する。
                if (a[3]==begin and len(a[0])<=2 and i>=3
                        and _case_boundary(parts[i-2]) and parts[i-2][0] in ('へ','に')
                        and parts[i-3][5] and parts[i-3][1].startswith('名詞')
                        and len(parts[i-3][0])>=2
                        and parts[i-3][4]==parts[i-2][3] and parts[i-2][4]==begin):
                    wide_begin=parts[i-3][3]
                    if extended-wide_begin<=18:
                        wide=RepairTarget(line,lo+wide_begin,lo+extended,lo,hi,anomalies,
                            structural,clause[extended:],'auxiliary_connection')
                        if wide not in targets:
                            targets.append(wide)
                break
            # 補助動詞の直結では、語尾との境界をまたいだ順序違いも
            # あり得る。本文側だけを交換して、接続助詞を取り残さない。
            for i in range(1,len(parts)):
                a,b=parts[i-1],parts[i]
                if not (begin<=a[3]<finish and b[3]<finish):
                    continue
                if not (oddness.causative_aux_mismatch(a,b)
                        or oddness.passive_aux_mismatch(a,b)
                        or oddness.auxiliary_te_mismatch(a,b)
                        or oddness.orphan_sokuon_mismatch(a,b,parts[i-2] if i>1 else None)):
                    continue
                extended=finish
                for t in parts:
                    if t[3]<extended:
                        continue
                    if t[3]!=extended or not t[5] or not t[1].startswith((
                            '助動詞','助詞:接続助詞','動詞:非自立','動詞:接尾')):
                        break
                    extended=t[4]
                if finish<extended and extended-begin<=18:
                    extra=RepairTarget(line,lo+begin,lo+extended,lo,hi,anomalies,
                                       structural,clause[extended:],'auxiliary_connection')
                    if extra not in targets:
                        targets.append(extra)
                break
            # 未然形＋「って」が既に異様なら、引用助詞という誤分割を
            # 固定せず、音便の「っ＋て」まで含む範囲も同じ打鍵で探す。
            for i in range(1,len(parts)):
                a,b=parts[i-1],parts[i]
                if (structural and begin<=a[3]<finish and b[3]==finish
                        and a[4]==b[3] and a[5] and a[1].startswith('動詞')
                        and a[6].startswith(('未然','仮定')) and b[0]=='って'
                        and b[1].startswith('助詞:格助詞') and b[4]-begin<=18):
                    extra=RepairTarget(line,lo+begin,lo+b[4],lo,hi,anomalies,
                        True,clause[b[4]:],'auxiliary_connection')
                    if extra not in targets:targets.append(extra)
                    break
    return sorted(targets, key=lambda t: (t.start, not bool(t.preserved_head),
                                         t.boundary_kind=='lexical', -(t.end-t.start)))


def reading_evidence(target, tokenize, dictionary, limit=32):
    """IME対応→辞書の語/活用→未知部分の一字推測。語の読みを壊さない。"""
    import kanji_guess
    from inflected_lexicon import dictionary_readings
    text = target.text
    out = {}
    def add(reading):
        if _is_reading(reading.text):
            out.setdefault(reading.text, reading)
    for rank, rd in enumerate(kanji_guess.ime_readings_for(text)):
        add(Reading(rd, 'saved_ime_pair', rank))
    beam = [('', 0, ())]
    local_start=target.start-target.context_start
    local_end=target.end-target.context_start
    contextual=[t for t in tokenize(target.context) if local_start<=t[3] and t[4]<=local_end]
    use_context=bool(contextual and contextual[0][3]==local_start
        and contextual[-1][4]==local_end and ''.join(t[0] for t in contextual)==text)
    # 切り出す前に判定できていた活用と読みを、単独解析で名詞へ戻さない。
    # 原文境界とぴったり合う語だけを使い、語の途中の読みを捏造しない。
    parts=([tuple(t[:3])+(t[3]-local_start,t[4]-local_start)+tuple(t[5:]) for t in contextual]
           if use_context else list(tokenize(text)))
    if ''.join(t[0] for t in parts) != text:
        parts = []
    for token_number, t in enumerate(parts):
        options = []
        literal = _kana(t[0])
        if _is_reading(literal):
            options.append((literal, 0, 'literal_kana'))
        elif t[5] and _is_reading(t[2]):
            options.append((t[2], 0, 'analyzed_word'))
        for rd in kanji_guess.ime_readings_for(t[0]):
            if _is_reading(rd):
                options.insert(0, (rd, 0, 'saved_ime_segment'))
        if not _is_reading(literal):
            for rank, rd in enumerate(dictionary_readings(t[0])):
                if _is_reading(rd) and rd not in [r for r, _, _ in options]:
                    options.append((rd, rank+1, 'dictionary_word'))
        # 複合語の後項の連濁は読みの変種。未入力の濁点を補う打鍵とは区別する。
        nominal_use = (t[1].startswith('名詞') or (t[1].startswith('動詞')
                       and t[6].startswith('連用') and target.following[:1] in ('を','が','に','へ','の')))
        if (token_number and nominal_use and '一' <= t[0][0] <= '鿿'
                and parts[token_number-1][1].startswith('名詞')
                and '一' <= parts[token_number-1][0][-1] <= '鿿'):
            voiced = dict(zip('かきくけこさしすせそたちつてとはひふへほ',
                              'がぎぐげござじずぜぞだぢづでどばびぶべぼ'))
            for rd, rank, origin in tuple(options):
                if rd and rd[0] in voiced:
                    options.append((voiced[rd[0]]+rd[1:], rank+1, 'compound_voicing'))
        if not options:
            options = [(r['reading'], r['rank']+2, 'character_guess') for r in
                       kanji_guess.reading_combos_with_evidence(t[0], dictionary, max_combos=limit)]
            # IMEで出来た未知の漢字列には、送り仮名が別の字に化けた訓も
            # 残す。正常な漢字語の読み制限を、この誤変換の逆算へ流用しない。
            raw = [('', 0)]
            for i, char in enumerate(t[0]):
                choices = kanji_guess._trim_okurigana_from_readings(
                    t[0], i, kanji_guess.readings_for_char(char, dictionary), None)
                raw = sorted((prefix+rd, score+j) for prefix, score in raw
                             for j, rd in enumerate(choices))
                raw.sort(key=lambda item: (item[1], item[0]))
                raw = raw[:limit]
            have = {r for r, _, _ in options}
            options.extend((rd, score+4, 'unrecognized_ime_sequence')
                           for rd, score in raw if rd not in have)
        elif len(t[0]) == 1 and '一' <= t[0] <= '鿿' and t[1].startswith('名詞'):
            # 一字名詞になった誤変換には、単独名詞の辞書項以外の訓もあり得る。
            # 多字の既知語や送り仮名を持つ活用形は一字読みへ分解しない。
            existing = {r for r, _, _ in options}
            options.extend((r['reading'], r['rank']+4, 'character_guess') for r in
                           kanji_guess.reading_combos_with_evidence(t[0], dictionary, max_combos=8)
                           if r['reading'] not in existing)
        combined = [(prefix+rd, cost+rank, segments+((t[3], t[4], rd, origin),))
                    for prefix, cost, segments in beam for rd, rank, origin in options]
        # 先着で切らず、各段階で全ての枝を比較してから上限を適用する。
        beam = sorted(combined, key=lambda item: (item[1], item[0]))[:limit]
    for rd, rank, segments in beam if parts else ():
        add(Reading(rd, 'contextual_token_sequence' if use_context else 'token_sequence', rank, segments))
    # 語単位の読みが得られない残りを救う。既知の活用を一字推測へ置き換えない。
    if not out:
        for r in kanji_guess.reading_combos_with_evidence(text, dictionary, max_combos=limit):
            add(Reading(r['reading'], r['source'], r['rank']))
    return list(out.values())[:limit]


def _render(keys):
    out = ''
    for c in keys:
        if c in ('゛', '゜') and out:
            combined = unicodedata.normalize('NFC', out[-1] + ('\u3099' if c == '゛' else '\u309a'))
            if len(combined) == 1:
                out = out[:-1] + combined
                continue
        out += c
    return out


@lru_cache(maxsize=128)
def _key_neighbors(key):
    import kana_layout as k
    return tuple((other, k._base_distance(key, other)) for other in k.KANA_POSITIONS
                 if other != key and 0 < k._base_distance(key, other) <= 1.05)


def key_repairs(reading, before='', after=''):
    """かなを実際の打鍵に開いた一手。濁点も同じ置換/巻き込みの規則で扱う。"""
    import kana_layout as k
    from vocabulary import dup_repair_enabled
    keys = tuple(key for c in reading for key in k.keystrokes(c))
    left_key = k.keystrokes(before[-1])[-1] if before else None
    right_key = k.keystrokes(after[0])[0] if after else None
    out = {reading: KeyRepair(reading, 'same_reading', -1, '', '', 0.0)}
    def add(changed, kind, position, pressed, intended, cost):
        rd = _render(changed)
        if rd == reading or not _is_reading(rd):
            return
        row = KeyRepair(rd, kind, position, pressed, intended, cost)
        old = out.get(rd)
        if old is None or (row.cost, row.operation, row.position) < (old.cost, old.operation, old.position):
            out[rd] = row
    for i, key in enumerate(keys):
        for other, distance in _key_neighbors(key):
            if (key in '゛゜' or other in '゛゜') and not k.mark_slip_enabled():
                continue
            add(keys[:i]+(other,)+keys[i+1:], 'adjacent_substitution', i, key, other, 1.0)
        adjacent = [keys[j] for j in (i-1, i+1) if 0 <= j < len(keys)]
        # 語を切り出しても、直前・直後に実際に打たれたキーを失わない。
        # 範囲外の文字は変更せず、端の1打を巻き込んだ根拠にだけ使う。
        if i==0 and left_key is not None:
            adjacent.append(left_key)
        if i==len(keys)-1 and right_key is not None:
            adjacent.append(right_key)
        if key not in adjacent and any(0 < k._base_distance(key, neighbor) <= 1.05 for neighbor in adjacent):
            add(keys[:i]+keys[i+1:], 'adjacent_intrusion', i, key, '', 1.0)
        if key in adjacent and dup_repair_enabled():
            add(keys[:i]+keys[i+1:], 'duplicate', i, key, '', 1.0)
        if i+1 < len(keys) and key != keys[i+1]:
            add(keys[:i]+(keys[i+1], key)+keys[i+2:], 'transposition', i,
                key+keys[i+1], keys[i+1]+key, 1.0)
        if key in k.SMALL_KANA_PAIR:
            other = k.SMALL_KANA_PAIR[key]
            add(keys[:i]+(other,)+keys[i+1:], 'shift', i, key, other, 0.4)
    return tuple(sorted(out.values(), key=lambda row: (row.cost, row.reading)))


def validate(target, surface, engine, tokenize, store, dictionary, decisions=None,
             expected_reading=None, companions=()):
    """同じ原文範囲への候補。直接再構築・通常置換のいずれからも呼ぶ。"""
    import oddness
    if not surface or surface == target.text:
        return False, 'unchanged'
    # 辞書にある動作名詞は、その直後の誤打だけで接続を戻せる候補を先に
    # 調べる。無ければ語本体を読む別範囲へ進み、そこで全候補を順位付けする。
    if target.preserved_head and not surface.startswith(target.preserved_head):
        return False, 'known_action_changed'
    accepted, reason = engine._check_replacement(target.source,
        (target.start, target.end, surface, 'かな入力'), store, tokenize, dictionary, decisions,
        conv_taken=((target.start, target.end),))
    if accepted is None:
        return False, reason
    if tuple(accepted[:2]) != (target.start, target.end):
        return False, 'changed_source_boundary'
    local_start = target.start-target.context_start
    siblings = [(a-target.context_start, b-target.context_start, text)
                for a, b, text in companions
                if target.context_start <= a <= b <= target.context_end
                and not _overlaps(a, b, target.start, target.end)]
    changed = _apply(target.context, siblings+[(local_start, target.end-target.context_start, surface)])
    local_start += sum(len(text)-(b-a) for a, b, text in siblings if b <= local_start)
    local_end = local_start+len(surface)
    # 表記を差し替えても、隣の助詞・活用との接続を必ず同じ文脈で検査する。
    new_odd = oddness.is_odd_run(changed, tokenize, with_spans=True,
        store=store, dict_index=dictionary, skip_join=True, complete_line=True)
    if any(s < local_end and local_start < e for _, _, s, e in new_odd):
        return False, 'context_still_anomalous'
    parts = list(tokenize(surface))
    if not parts or not all(t[5] for t in parts):
        return False, 'unreadable_candidate'
    lexical_parts = parts
    lexical_tail = parts[-1]
    # 機能語を欠いたまま別の品詞を置かない。格助詞を受ける名詞句と、
    # 接続助詞を受ける連用形を、表記の頻度より先に検査する。
    in_context = list(tokenize(changed))
    inserted = [t for t in in_context if t[3] < local_end and local_start < t[4]]
    if expected_reading is not None:
        if (not inserted or inserted[0][3] != local_start or inserted[-1][4] != local_end
                or ''.join(t[2] for t in inserted) != expected_reading):
            return False, 'reading_changed_in_context'
    if inserted and inserted[0][3] == local_start and inserted[-1][4] == local_end:
        parts = inserted
    following = [t for t in in_context if t[3] >= local_end]
    original_following = [t for t in tokenize(target.context)
                          if t[3] >= target.end-target.context_start]
    polite_surface = next((ts[0][0] for ts in (original_following,following)
        if ts and ts[0][1].startswith('助動詞')
        and ts[0][0] in ('ます','まし','ませ','ましょ')),None)
    # 差し替え後に助動詞が同形の副詞や自立動詞へ再分類されても、
    # 原文で受け取った丁寧語の接続条件を落とさない。
    if polite_surface is not None:
        tail=parts[-1]
        b=(polite_surface,'助動詞',polite_surface,tail[4],tail[4]+len(polite_surface),True,'')
        if (not tail[1].startswith(('動詞','助動詞'))
                or tail[6]!='連用形' or oddness.polite_aux_mismatch(tail,b)):
            return False,'polite_auxiliary_slot'
    # 「てい」は「いる」の途中。語尾を入れ替えた候補が、入力に無い
    # 続きを要求したまま終わるのを採用しない。名詞に再分類されても
    # 単独の候補で得た補助動詞の役割を失わない。
    if (lexical_tail[0]=='い' and lexical_tail[1].startswith('動詞:非自立')
            and len(lexical_parts)>=2
            and lexical_parts[-2][0] in ('て','で')):
        next_part=following[0] if following else None
        continuation=bool(next_part and (
            next_part[1].startswith('助動詞') or
            (next_part[1].startswith('助詞:接続助詞') and next_part[0] in ('て','で','ながら','つつ'))))
        if not continuation:
            return False,'unfinished_aspect_auxiliary'
    source_parts = list(tokenize(target.text))
    # 格助詞を受ける丁寧な述語の修復で、語尾ごと名詞へ置き換えない。
    # 全かなの単語や見出しにはこの条件を課さず、明示的な文の役割を使う。
    before=[t for t in tokenize(target.context) if t[4]<=target.start-target.context_start]
    if (target.boundary_kind=='auxiliary_connection' and before
            and before[-1][4]==target.start-target.context_start
            and before[-1][1].startswith('助詞:格助詞')
            and any(oddness.polite_aux_mismatch(a,b) for a,b in zip(source_parts,source_parts[1:]))
            and not any(t[1].startswith(('動詞','形容詞')) for t in lexical_parts)):
        return False,'predicate_replaced_with_noun'
    original_pairs={(a[0],b[0]) for a,b in zip(source_parts,source_parts[1:])}
    for a,b in zip(lexical_parts,lexical_parts[1:]):
        if ((a[0],b[0]) not in original_pairs and oddness.aspect_auxiliary_needs_te(a,b)):
            return False,'aspect_auxiliary_slot'
        if (a[1].startswith('動詞') and b[0] in ('て','で','た','だ')
                and b[1].startswith(('助詞:接続助詞','助動詞'))
                and (a[0],b[0]) not in original_pairs
                and _modern_te_allowed(a[0],a[2],b[0]) is False):
            return False,'euphonic_auxiliary_slot'
    if (not target.following and source_parts and all(t[1].startswith('名詞') for t in source_parts)
            and not parts[-1][1].startswith('名詞')):
        return False, 'nominal_phrase'
    if following:
        first = following[0]
        # 活用形を短い名詞へ誤分割した文中解析を、成立の証拠にしない。
        # 同じ表記に本物の名詞項がある場合は、その解釈を残す。
        if (_case_boundary(first) and lexical_tail[6].startswith(('未然', '仮定', '命令'))):
            from inflected_lexicon import has_nominal_entry
            if not has_nominal_entry(lexical_tail[0]):
                return False, 'incomplete_inflection_before_nominal_particle'
        if (parts[-1][1].startswith('動詞:接尾') and first[1].startswith('助動詞')
                and first[0] in ('だ', 'で', 'だっ', 'です', 'なら')):
            return False, 'copula_after_verbal_suffix'
        if parts[-1][6].startswith('仮定') and first[0] not in ('ば', 'ど', 'ども'):
            return False, 'conditional_slot'
        if first[1].startswith('助詞:格助詞') and not parts[-1][1].startswith('名詞'):
            return False, 'nominal_slot'
        if first[0] in ('て', 'で') and first[1].startswith('助詞:接続助詞'):
            if not parts[-1][1].startswith(('動詞', '形容詞')) or not parts[-1][6].startswith('連用'):
                return False, 'continuative_slot'
        if first[0] in ('し', 'する', 'すれ', 'せよ') and first[1].startswith('動詞'):
            if not parts[-1][1].startswith('名詞:サ変接続'):
                return False, 'suru_slot'
    return True, 'accepted'


@lru_cache(maxsize=1)
def _seed_context():
    # 同梱の一般的な話題の関係だけを読む。使用回数も履歴も作らない。
    from context_vec import ContextVectorStore
    context = ContextVectorStore()
    context.ensure_seeded()
    return context


def _surfaces(reading, store, dictionary, compose=False):
    # 本人語彙には同梱の初期語彙も含まれる。索引から落ちた普通の語を
    # 捨てない一方、使用回数や最終使用時刻は順位に使わない。
    return list(dict.fromkeys(
        list(dictionary.surfaces_for_reading(reading, limit=12, band=True))
        + [entry['surface'] for entry in store.lookup(reading) if entry.get('surface')]
        + list(dictionary.inflected_surfaces_for_reading(reading))
        + (_composed_surfaces(reading,store,dictionary) if compose else [])))



@lru_cache(maxsize=4096)
def _grammatical_suffix(suffix, state):
    from pos_grammar import explain_kana_run
    return explain_kana_run(suffix,no_words=True,initial_state=state,before_kanji=False)


def _allows_grammatical_tail(forms, tail, head_reading=None, head_surface=None):
    """辞書の活用形と既存の文法による接続。生成と順位で共有する。"""
    from morphology import dictionary_inflections
    from pos_grammar import continuation_state
    for pos,form,base,rd in forms:
        if head_reading is not None and rd!=head_reading:
            continue
        if pos.startswith('動詞,'):
            state=continuation_state(form)
            if state is None and form=='連用タ接続' and head_surface:
                # 読み末尾「い」だけでは書いて/泳いでを区別できない。
                # 生成後の検算と同じ辞書活用の根拠で、音便の接続を渡す。
                if _modern_te_allowed(head_surface,rd,'て') is True:state='TSU'
                elif _modern_te_allowed(head_surface,rd,'で') is True:state='N'
            if state and _grammatical_suffix(tail,state):
                return True
        elif pos.startswith('名詞,サ変接続,'):
            for n in range(1,min(3,len(tail))+1):
                for tp,tf,tb,tr in dictionary_inflections(tail[:n]) or ():
                    state=continuation_state(tf)
                    if (tp.startswith('動詞,') and tb=='する' and tr==tail[:n]
                            and state and _grammatical_suffix(tail[n:],state)):
                        return True
    return False


@lru_cache(maxsize=8192)
def _modern_te_allowed(surface, reading, particle):
    """生成する現代語のて/た接続。辞書の活用型と音便を共有して検算する。

    文語等は未判定。同じ表記の別の読みを接続の証拠に混ぜない。
    原文の文語を異様と決める規則ではない。設計/反証: GPT-6, 2026-09-11。
    """
    from morphology import dictionary_paradigms
    known=False
    for pos,kind,form,base,rd in dictionary_paradigms(surface) or ():
        if not pos.startswith('動詞,') or rd!=reading:
            continue
        if kind.startswith('五段'):
            known=True
            voiced=kind.startswith(('五段・ガ行','五段・ナ行','五段・バ行','五段・マ行'))
            if ((particle in ('で','だ'))!=voiced):
                continue
            if form=='連用タ接続' or (kind=='五段・サ行' and form=='連用形'):
                return True
        elif kind.startswith(('一段','カ変','サ変')):
            known=True
            # サ変の「し」は未然と連用が同形で、辞書の一部に片方だけある。
            continuative=(form=='連用形' or (kind.startswith('サ変')
                          and base.endswith('する') and surface==base[:-2]+'し'))
            if continuative and particle in ('て','た'):
                return True
        else:
            return None
    return False if known else None


@lru_cache(maxsize=8192)
def _productive_predicate(surface, head):
    """候補を作る語尾は、保護用の緩い説明だけで正当化しない。"""
    from morphology import tokenize
    parts=list(tokenize(surface))
    if (not parts or not all(t.has_reading for t in parts)
            or parts[0].surface!=head):
        return False
    import oddness
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    if any(oddness.aspect_auxiliary_needs_te(a,b) for a,b in zip(legacy,legacy[1:])):
        return False
    for a,b in zip(parts,parts[1:]):
        if (a.pos=='動詞' and b.surface in ('て','で','た','だ')
                and (b.pos=='助動詞' or (b.pos=='助詞' and b.pos_sub.startswith('接続助詞')))
                and _modern_te_allowed(a.surface,a.reading,b.surface) is False):
            return False
    for i,t in enumerate(parts[1:],1):
        if t.pos=='助動詞' or (t.pos=='助詞' and t.pos_sub.startswith('接続助詞')):
            continue
        if t.pos=='動詞' and t.pos_sub.startswith(('非自立','接尾')):
            continue
        if (i==1 and parts[0].pos=='名詞' and parts[0].pos_sub.startswith('サ変接続')
                and t.pos=='動詞' and t.base_form=='する'):
            continue
        return False
    return True


def _composed_surfaces(reading,store,dictionary):
    """原文の異様な接続を含む範囲で、語と文法的な語尾を組み合わせる。"""
    from morphology import dictionary_inflections
    out=[]
    for cut in range(2,len(reading)):
        head,tail=reading[:cut],reading[cut:]
        if len(tail)>10:
            continue
        for surface in _surfaces(head,store,dictionary):
            if (_allows_grammatical_tail(dictionary_inflections(surface) or (),tail,head,surface)
                    and _productive_predicate(surface+tail,surface)):
                out.append(surface+tail)
    return list(dict.fromkeys(out))


@lru_cache(maxsize=8192)
def _surface_score_head(surface):
    """文法的な語尾を足した表記を、語本体と同じ一般性で比べる。

    『並べました』全体が単語費用表に無いことを、『並べ』という語が
    珍しいことにしない。語尾は候補全体の読み・接続で別に評価される。
    """
    from morphology import dictionary_inflections
    for cut in range(len(surface)-1,0,-1):
        head,tail=surface[:cut],surface[cut:]
        if not _is_reading(tail) or len(tail)>10:
            continue
        if (_allows_grammatical_tail(dictionary_inflections(head) or (),tail,head_surface=head)
                and _productive_predicate(surface,head)):
            return head
    return surface


def context_material(target, tokenize):
    """対象に近い内容語から渡す。得点関数の距離減衰と順序を一致させる。"""
    start = target.start-target.context_start
    end = target.end-target.context_start
    parts = [t for t in tokenize(target.context)
             if (t[4] <= start or t[3] >= end)
             and t[1].startswith(('名詞', '動詞', '形容詞')) and len(t[0]) > 1]
    parts.sort(key=lambda t: (start-t[4] if t[4] <= start else t[3]-end, t[3]))
    return tuple(t[0] for t in parts)


def _complete_verbs_before_bad_polite(target, tokenize):
    """終止形に丁寧語が直結した場合、語の原形を活用修復の根拠として残す。"""
    if target.boundary_kind!='auxiliary_connection':
        return frozenset()
    from morphology import dictionary_inflections
    import oddness
    parts=list(tokenize(target.text))
    bases=set()
    for a,b in zip(parts,parts[1:]):
        if (a[5] and a[1].startswith('動詞:自立') and a[6]=='基本形'
                and oddness.polite_aux_mismatch(a,b)):
            for pos,form,base,rd in dictionary_inflections(a[0]) or ():
                if pos.startswith('動詞,') and form=='基本形' and rd==a[2]:
                    # かな表記の原形は同じ読みの漢字活用でも保持できる。
                    # 漢字で書かれた原形は、その語の表記を保つ根拠にする。
                    bases.add(('reading',rd) if _is_reading(a[0]) else ('surface',base))
    return frozenset(bases)


def _candidate_verb_bases(surface, tokenize):
    from morphology import dictionary_inflections
    from inflected_lexicon import dictionary_readings
    bases=set()
    for t in tokenize(surface):
        if not t[5] or not t[1].startswith('動詞'):
            continue
        for pos,form,base,rd in dictionary_inflections(t[0]) or ():
            # 「読め」の命令形と「読める」の連用形は表記が同じ。
            # 候補の解析と違う活用の原形まで保存したことにしない。
            if not pos.startswith('動詞,') or form!=t[6] or rd!=t[2]:
                continue
            bases.add(('surface',base))
            for base_reading in dictionary_readings(base):
                bases.add(('reading',base_reading))
    return frozenset(bases)


def _terminal_auxiliary_fragment(surface, following, tokenize):
    """語尾がまだ続く形は、同じ打鍵で得た完成語より後で比較する。"""
    parts=list(tokenize(surface))
    if (len(parts)<3 or not parts[-1][1].startswith('動詞:非自立')
            or parts[-1][6]!='連用形' or parts[-2][0] not in ('て','で')):
        return False
    after=list(tokenize(following)) if following else []
    if after and (after[0][1].startswith('助動詞')
                  or after[0][1].startswith('助詞:接続助詞')
                  or after[0][0] in ('、',',')):
        return False
    return True


def resolve(target, engine, tokenize, store, dictionary, decisions=None, legacy_surface=None):
    """同じ文脈で成立した全候補を比較し、最優先の一つと診断を返す。"""
    from ngram_yomi import continuation_cost
    from reading_likelihood import edit_cost, adjacent_readings, evidence
    collect_reading_diagnostic = (engine.TRACE is not None
        or getattr(engine._trace, '_diagnostic_observer', None) is not None)
    from morphology import path_cost
    from semantic_roles import object_before, candidate_evidence as role_evidence
    readings = reading_evidence(target, tokenize, dictionary)
    diagnostic = dict(start=target.start, end=target.end, text=target.text,
                      boundary_kind=target.boundary_kind, preserved_head=target.preserved_head,
                      context_start=target.context_start, context_end=target.context_end,
                      anomalies=target.anomalies, structural=target.structural,
                      readings=[asdict(r) for r in readings], candidates=[], rejected={})
    if engine._chunk_is_intact(target.text, tokenize, repair_context=target):
        diagnostic['status'] = 'intact'
        return None, diagnostic
    surrounding_readings = (
        adjacent_readings(target.context, list(tokenize(target.context)),
            target.start-target.context_start, target.end-target.context_start))
    if collect_reading_diagnostic:
        diagnostic['reading_likelihood'] = [dict(row,
            source_start=row['source_start']+target.context_start,
            source_end=row['source_end']+target.context_start)
            for row in evidence(target.context, list(tokenize(target.context)),
                                dictionary_alternatives=False)]
    candidates = {}
    complete_verbs = _complete_verbs_before_bad_polite(target,tokenize)
    # 他の列や正解の見本を材料にしない。この対象を除いた同じ文の内容語。
    material = context_material(target, tokenize)
    object_word=object_before(target.context,target.start-target.context_start,tokenize)
    semantic = _seed_context()
    preceding = [t for t in tokenize(target.context)
                 if t[4] <= target.start-target.context_start]
    has_argument = bool(preceding and preceding[-1][1].startswith('助詞:格助詞'))
    known_verbs = [t[0] for t in tokenize(target.text)
                   if (has_argument or (target.boundary_kind=='auxiliary_connection'
                       and any('一'<=c<='鿿' for c in t[0])))
                   and t[5] and t[1].startswith('動詞') and len(t[0]) > 1]
    legacy_parts = list(tokenize(legacy_surface)) if legacy_surface else []
    legacy_reading = (''.join(t[2] for t in legacy_parts)
                      if legacy_parts and all(t[5] for t in legacy_parts) else None)
    for reading in readings:
        for repair in key_repairs(reading.text,*surrounding_readings):
            surfaces = _surfaces(repair.reading, store, dictionary,
                    compose=target.boundary_kind=='auxiliary_connection')
            if repair.reading.endswith('し') and target.following.startswith(('て', 'た', 'ま', 'な')):
                # 「名詞＋し」が別の名詞の一部へ誤分割されても、入力された
                # しを残してサ変活用の境界を戻す。追加打鍵は仮定しない。
                surfaces.extend(sf+'し' for sf in _surfaces(repair.reading[:-1], store, dictionary)
                    if any(t[1].startswith('名詞:サ変接続') for t in list(tokenize(sf))[-1:]))
            # 既存経路の先頭候補も、同じ読みに同じ一手で届くなら同列で比較。
            # 新設の経路であること自体を、優先する理由にしない。
            if legacy_reading == repair.reading:
                surfaces.append(legacy_surface)
            for surface in dict.fromkeys(surfaces):
                valid, reason = validate(target, surface, engine, tokenize, store, dictionary, decisions, repair.reading)
                if not valid:
                    diagnostic['rejected'][reason] = diagnostic['rejected'].get(reason, 0)+1
                    continue
                # IME情報を先にし、物理操作、元の文字種、文脈、一般性を比較。
                # 漢語の一般性は既存表を、目的語と動作の意味的な役割は版付きの
                # 一般語分類を使う。未知の意味を不適合と決めない。
                score_head = (_surface_score_head(surface)
                    if target.boundary_kind=='auxiliary_connection' else surface)
                cost = engine._table_cost(score_head)
                continuation = continuation_cost(repair.reading)
                context_cost = path_cost(target.substitute(surface))
                local_prediction = (edit_cost(reading.text, repair.reading, *surrounding_readings)
                                    if collect_reading_diagnostic else None)
                argument_evidence=role_evidence(object_word,surface,target.following) if object_word else None
                argument_fit=bool(argument_evidence and argument_evidence['shared_roles'])
                rank = (0 if reading.source == 'saved_ime_pair' else 1,
                        int(repair.cost>1), -int(argument_fit), repair.cost,
                        sum(segment[3] in ('character_guess', 'unrecognized_ime_sequence')
                            for segment in reading.segments),
                        len(complete_verbs - _candidate_verb_bases(surface,tokenize))
                            if complete_verbs else 0,
                        int(any('ァ' <= c <= 'ヶ' for c in target.text)
                            and not any('ァ' <= c <= 'ヶ' for c in surface)),
                        int(engine._is_whole_proper_noun(surface, tokenize)),
                        -semantic.context_score(score_head, material),
                        sum(word not in surface for word in known_verbs),
                        int(_terminal_auxiliary_fragment(surface,target.following,tokenize))
                            if target.boundary_kind=='auxiliary_connection' else 0,
                        (continuation if continuation is not None else 100000)
                            if target.boundary_kind=='auxiliary_connection' else 0,
                        engine._kango_tier_of(score_head),
                        cost if cost is not None else 100000,
                        continuation if continuation is not None else 100000,
                        context_cost if context_cost is not None else 100000, reading.rank, surface)
                row = dict(surface=surface, rank=rank, score_head=score_head, local_prediction=local_prediction,
                           object_word=object_word, argument_fit=argument_fit, argument_evidence=argument_evidence,
                           reading=asdict(reading), repair=asdict(repair),
                           also_from_legacy=surface == legacy_surface)
                if surface not in candidates or rank < candidates[surface]['rank']:
                    candidates[surface] = row
    ordered = sorted(candidates.values(), key=lambda row: row['rank'])
    diagnostic['candidates'] = ordered
    diagnostic['status'] = 'selected' if ordered else 'no_candidate'
    return (ordered[0]['surface'] if ordered else None), diagnostic


def _overlaps(a, b, start, end):
    return start <= a <= end if a == b else a < end and start < b


def _repair_coverage(target):
    """同じ異様な接続の両側は、独立した二つの編集として合成しない。"""
    return (min([target.start]+[s for _,_,s,e in target.anomalies]),
            max([target.end]+[e for _,_,s,e in target.anomalies]))


def _retain_independent_changes(old_changes, selected, targets):
    coverages=[_repair_coverage(t) for t in targets
               if any((t.start,t.end)==(a,b) for a,b,_ in selected)]
    return [change for change in old_changes if not any(
        _overlaps(change[0],change[1],a,b) for a,b in coverages)]


def _apply(source, changes):
    out = []; cursor = 0
    for a, b, surface in sorted(changes):
        if a < cursor:
            raise ValueError('overlapping source edits')
        out.extend((source[cursor:a], surface)); cursor = b
    out.append(source[cursor:])
    return ''.join(out)


def _validate_joint_choices(selected, retained, targets, diagnostics, engine,
                            tokenize, store, dictionary, decisions):
    """長さの異なる複数補正を合成した状態でも、同じ候補を再検査する。"""
    choices = {(d['start'], d['end']): d for d in diagnostics if d.get('candidates')}
    rejected = {}
    # 不成立になった候補へ戻らないため、候補数の合計以内に必ず終わる。
    budget = sum(len(d['candidates']) for d in choices.values())+len(selected)
    for _ in range(budget):
        changed = False
        for a, b, surface in tuple(selected):
            target = next(t for t in targets if (t.start, t.end) == (a, b))
            diagnostic = choices[a, b]
            row = next(c for c in diagnostic['candidates'] if c['surface'] == surface)
            companions = retained+[c for c in selected if c[:2] != (a, b)]
            valid, reason = validate(target, surface, engine, tokenize, store, dictionary,
                                     decisions, row['repair']['reading'], companions)
            if valid:
                continue
            changed = True
            excluded = rejected.setdefault((a, b), set())
            excluded.add(surface)
            diagnostic.setdefault('joint_rejected', []).append(dict(surface=surface, reason=reason))
            selected.remove((a, b, surface))
            for candidate in diagnostic['candidates']:
                sf = candidate['surface']
                if sf in excluded:
                    continue
                valid, _ = validate(target, sf, engine, tokenize, store, dictionary,
                                    decisions, candidate['repair']['reading'], companions)
                if valid:
                    selected.append((a, b, sf))
                    diagnostic['status'] = 'selected_after_joint_validation'
                    break
                excluded.add(sf)
            else:
                diagnostic['status'] = 'no_joint_candidate'
        if not changed:
            break
    return selected


def _trace_diagnostic(engine, stage, diagnostic):
    # 通常の画面解析で、全候補の巨大な診断文字列を作らない。
    if engine.TRACE is not None or getattr(engine._trace, '_diagnostic_observer', None):
        engine._trace(stage, repr(diagnostic))


def _legacy_resolves_anomaly(target, changes, engine, tokenize, store, dictionary, decisions):
    """語本体を保ったまま、同じ原文の異様が隣の修正で解消したか。

    異様の範囲は語尾の接続まで含むが、読む範囲は語本体だけの場合がある。
    その語尾が既に直っていれば、元から正しい語まで重ねて変えない。
    既存出力を無条件には信用せず、広い元の範囲を同じ検算に通す。
    """
    if not target.anomalies or any(_overlaps(a,b,target.start,target.end) for a,b,_ in changes):
        return False
    start=min([target.start]+[a for _,_,a,b in target.anomalies])
    end=max([target.end]+[b for _,_,a,b in target.anomalies])
    relevant=[c for c in changes if _overlaps(c[0],c[1],start,end)]
    if not relevant or not all(start<=a<=b<=end for a,b,_ in relevant):
        return False
    wide=RepairTarget(target.source,start,end,target.context_start,target.context_end,
                      target.anomalies,target.structural,target.source[end:target.context_end])
    surface=_apply(wide.text,[(a-start,b-start,text) for a,b,text in relevant])
    valid,_=validate(wide,surface,engine,tokenize,store,dictionary,decisions)
    return valid


def with_contextual_repair(fn):
    """通常の置換/途中の再構築/再解析を、最後に同じ原文範囲で検算する。

    既存処理の内部は段階的に移行する。新しく確定した候補はこの返却点で
    合成し、文脈を捨てた別の再解析へ再投入しない。
    """
    from functools import wraps
    import os
    import sys
    @wraps(fn)
    def wrapped(line, *args, **kwargs):
        engine = sys.modules[fn.__module__]
        def argument(name, position, default=None):
            return kwargs.get(name, args[position] if len(args) > position else default)
        store = argument('store', 0)
        tokenize = argument('tokenize_fn', 1)
        dictionary = argument('dict_index', 8)
        method = argument('input_method', 6, 'kana')
        decisions = argument('decisions', 5)
        if (method != 'kana' or dictionary is None or tokenize is None or store is None
                or len(engine._CORRECTION_PATH.get()) != 1
                or os.environ.get('CN_CONTEXTUAL_REPAIR') == '0'):
            return fn(line, *args, **kwargs)
        targets = targets_for_line(line, tokenize, store, dictionary)
        if not targets:
            return fn(line, *args, **kwargs)
        legacy = fn(line, *args, **kwargs)
        old = legacy.get('corrected', line)
        old_changes = [(a, b, old[c:d]) for a, b, c, d in engine._diff_spans(line, old)]
        selected = []; diagnostics = []
        for target in targets:
            if any(_overlaps(target.start, target.end, a, b) for a, b, _ in selected):
                continue
            if _legacy_resolves_anomaly(target,old_changes,engine,tokenize,store,dictionary,decisions):
                diagnostic=dict(start=target.start,end=target.end,text=target.text,
                                status='resolved_by_existing_change')
                diagnostics.append(diagnostic)
                _trace_diagnostic(engine,'文脈補正',diagnostic)
                continue
            changes = [change for change in old_changes if _overlaps(
                change[0], change[1], target.start, target.end)]
            legacy_surface = None
            if changes and all(target.start <= a <= b <= target.end for a,b,_ in changes):
                legacy_surface = _apply(target.text, [(a-target.start,b-target.start,text)
                                                      for a,b,text in changes])
            surface, diagnostic = resolve(target, engine, tokenize, store, dictionary, decisions, legacy_surface)
            diagnostics.append(diagnostic)
            _trace_diagnostic(engine, '文脈補正', diagnostic)
            if surface is not None:
                selected.append((target.start, target.end, surface))
        # 語本体を直す新候補へ、同じ接続の語尾を直す旧候補を重ねない。
        # どちらも単独では成立しても、合成すると別の文になるため。
        retained = _retain_independent_changes(old_changes, selected, targets)
        # 新しい候補がない場合も、古い経路が部分だけを直して不整合を残すのを防ぐ。
        for target in targets:
            if any(_overlaps(target.start, target.end, a, b) for a, b, _ in selected):
                continue
            overlapping = [change for change in retained if _overlaps(
                change[0], change[1], target.start, target.end)]
            if not overlapping:
                continue
            if all(target.start <= a <= b <= target.end for a, b, _ in overlapping):
                surface = _apply(target.text, [(a-target.start, b-target.start, text)
                                               for a, b, text in overlapping])
                valid, reason = validate(target, surface, engine, tokenize, store, dictionary, decisions)
            else:
                # 既存経路がより広い範囲を直す場合はこの狭い対象から判断しない。
                continue
            if not valid:
                retained = [change for change in retained if change not in overlapping]
                engine._trace('文脈最終検査', f'{target.text!r} → {surface!r} を除外: {reason}')
                diagnostics.append(dict(start=target.start, end=target.end,
                                        status='legacy_rejected', surface=surface, reason=reason))
        selected = _validate_joint_choices(selected, retained, targets, diagnostics, engine,
                                            tokenize, store, dictionary, decisions)
        corrected = _apply(line, retained+selected)
        final_choices = {(a,b):surface for a,b,surface in selected}
        for diagnostic in diagnostics:
            diagnostic['selected'] = final_choices.get((diagnostic['start'],diagnostic['end']))
            _trace_diagnostic(engine, '文脈補正確定', diagnostic)
        result = dict(legacy)
        if engine.TRACE is not None:
            result['contextual_diagnostics'] = diagnostics
        if corrected == old:
            return result
        original_spans = []; spans = []; details = []
        for a, b, c, d in engine._diff_spans(line, corrected):
            original_spans.append((a, b)); spans.append((c, d))
            details.append((line[a:b], corrected[c:d], 'かな入力'))
        reasons = []
        odd = engine._odd_spans_for_line(line, tokenize, original_spans,
                                         store, dictionary, reasons_out=reasons)
        unsure = [span for span in result.get('unsure_spans', []) if not any(
                  _overlaps(span[0], span[1], a, b) for a, b in original_spans)]
        result.update(original=line, corrected=corrected, changed=corrected != line,
                      details=details, original_spans=original_spans, spans=spans,
                      odd_spans=odd, odd_reasons=reasons, unsure_spans=unsure)
        result.pop('diagnosis', None)
        return result
    return wrapped
