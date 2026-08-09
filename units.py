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

"""
補正結果の1行を「クリックできる語の単位」に組み立てる。

補正欄では、自動補正が入った語だけでなく **すべての語** を
選び直せるようにしたい。そのためには表示中のテキストを
語の単位に区切り、各語がどこからどこまでかを持っておく必要がある。

区切りは形態素解析に任せるが、janome は誤変換を含む文を
正しく区切れないことがある（「ひらがなを」→ ひ/ら/が/なを）。
そこでユーザーはドラッグで自由な範囲を選んで選び直すことができ、
その記録は **トークンの区切りに関係なく、生テキストへの一致で**
引き当てる。区切りが多少おかしくても、選び直しは機能する。

ここで同時に、ユーザーが過去に選び直した語（choices.py）を反映する。
反映を描画側でやると位置の計算が二重になって崩れやすいので、
「テキストの組み立て」と「位置の確定」を必ずこの1箇所で同時に行う。
（範囲を後追いで調整すると位置がずれる、という失敗が過去にあった。
  SPEC.md「過去の失敗と学び」4 を参照）

各単位の内容:
    start, end   表示テキスト上の位置
    text         実際に表示する文字列（選び直し後の表記）
    base         選び直す前の表記（記憶の引き当てに使う）
    reading      形態素解析が返した読み（無ければ空）
    prev, next   前後の語（文脈つき学習に使う）
    kind         'fixed'  自動補正が入った語
                 'chosen' ユーザーが選び直した語
                 'plain'  そのままの語
    detail       自動補正の内容 (元の語, 補正後, 分類)。無ければ None
"""


def _find_detail(start, end, fixed_spans, details):
    """この範囲に自動補正が掛かっているなら、その内容を返す。"""
    for k, (fs, fe) in enumerate(fixed_spans):
        # 範囲が少しでも重なっていれば、その補正に属するとみなす
        if not (end <= fs or start >= fe):
            if k < len(details):
                return details[k]
            return None
    return None


def _token_before(tokens, pos):
    """位置 pos の直前にある語の表記。無ければ空。"""
    best = ''
    for surface, _p, _r, ts, te in ((t[0], t[1], t[2], t[3], t[4])
                                    for t in tokens):
        if te <= pos:
            best = surface
        else:
            break
    return best

def _token_after(tokens, pos):
    """位置 pos 以降で最初に始まる語の表記。無ければ空。"""
    for t in tokens:
        if t[3] >= pos:
            return t[0]
    return ''


def _find_choice_ranges(text, tokens, choice_store):
    """
    記録されている選び直しを、生テキストへの一致で探す。

    トークンの区切りを条件にしない。janome が「ひらがなを」を
    ひ/ら/が/なを と割っても、「ひらがな」の記録は文字列一致で見つかる。

    重なった候補は長いものを優先する（「ひらがな」と「ひら」が
    両方記録されていたら、長い一致を採る）。

    戻り値: [(start, end, 元の語, 選ばれた表記), ...] 位置順
    """
    if choice_store is None:
        return []
    try:
        originals = choice_store.originals()
    except Exception:
        return []
    if not originals:
        return []

    candidates = []
    for original in originals:
        if not isinstance(original, str) or not original:
            continue
        idx = text.find(original)
        while idx >= 0:
            candidates.append((idx, idx + len(original), original))
            idx = text.find(original, idx + 1)

    # 長い一致を優先して、重ならないように選ぶ
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken = []
    for start, end, original in candidates:
        if any(not (end <= s or start >= e) for s, e, _o, _c in taken):
            continue
        prev = _token_before(tokens, start)
        next_ = _token_after(tokens, end)
        try:
            chosen = choice_store.lookup(original, prev, next_)
        except Exception:
            chosen = None
        if not chosen or chosen == original:
            continue
        if not isinstance(chosen, str):
            # 壊れた記録（過去の不具合で配列が保存されたもの）。
            # ここで弾かないと ''.join() で落ち、起動できなくなる。
            # choices.py 側でも読み込み時に弾いているが、
            # 表示の組み立てはどんな記憶が来ても落ちてはいけないので
            # 二重に守る。
            continue
        taken.append((start, end, original, chosen))

    taken.sort(key=lambda c: c[0])
    return taken


def _units_from_spans(text, spans, details, marked_kind):
    """
    語の区切りが取れないテキストを、補正スパンの内外で単位に分ける。

    スパンの中は marked_kind（'suspect' / 'fixed'）、外は 'plain'。
    色を付けるべき箇所だけに色が付く、最低限の分割。
    """
    marks = sorted((s, e) for s, e in (spans or [])
                   if 0 <= s < e <= len(text))
    units = []
    pos = 0

    def _plain(s, e):
        if s < e:
            units.append({'start': s, 'end': e, 'text': text[s:e],
                          'base': text[s:e], 'reading': '',
                          'prev': '', 'next': '',
                          'kind': 'plain', 'detail': None})

    for s, e in marks:
        if s < pos:
            continue        # 重なりは先のものを優先
        _plain(pos, s)
        units.append({'start': s, 'end': e, 'text': text[s:e],
                      'base': text[s:e], 'reading': '',
                      'prev': '', 'next': '',
                      # detail は元の spans の並びと details の添字が
                      # 対応しているので、並べ替えた marks ではなく
                      # 元の spans で引く
                      'kind': marked_kind,
                      'detail': _find_detail(s, e, spans or [], details)})
        pos = e
    _plain(pos, len(text))
    if not units:
        _plain(0, len(text))
    return units


def build_suspect_units(result, tokenize_fn, choice_store=None):
    """
    自動では直さず、疑わしい箇所に色をつけるだけの表示のための組み立て。

    build_line_units は「補正後のテキスト」を起点にするが、
    こちらは「入力そのまま（result['original']）」を起点にする。
    統合レイアウト（メモ欄と補正結果欄を1つにする）や、
    簡易入力ウィンドウのように、自動置換をせずユーザーの入力を
    そのまま保ちたい場面で使う。

    表記は変わらないので、ここでの「選び直し」は
    テキストを差し替えるのではなく、呼び出し側が
    カーソル位置への差し込みなど、別の形で反映する。

    戻り値: (表示するテキスト＝result['original'], [単位, ...])
        単位の kind は 'suspect'（疑わしい）/ 'chosen'（選び直し済み)/
        'plain'。'fixed' は使わない（自動では直さないため）。
    """
    text = result.get('original', '')
    if not text:
        return text, []

    suspect_spans = result.get('original_spans', []) or []
    details = result.get('details', []) or []

    try:
        tokens = tokenize_fn(text)
    except Exception:
        tokens = []

    if not tokens or ''.join(t[0] for t in tokens) != text:
        # 語の区切りが信用できない（形態素解析が空白などを落とし、
        # 連結が元テキストと一致しない）。以前はここで行全体を
        # 1つの単位にし、補正が1箇所でもあると **行全体に色が
        # 付いて** いた（実機で「文頭にスペースがあると行全体が
        # 補正の色になる」と報告された）。区切りが分からなくても
        # 補正の位置（original_spans）は分かっているので、
        # スパンの内外で分割して、色は該当箇所だけに付ける。
        return text, _units_from_spans(text, suspect_spans, details,
                                       'suspect')

    units = []
    for i, tok in enumerate(tokens):
        surface, _pos_tag, reading, src_start, src_end = (
            tok[0], tok[1], tok[2], tok[3], tok[4])
        prev_word = tokens[i - 1][0] if i > 0 else ''
        next_word = tokens[i + 1][0] if i + 1 < len(tokens) else ''

        detail = _find_detail(src_start, src_end, suspect_spans, details)

        chosen = None
        if choice_store is not None:
            try:
                chosen = choice_store.lookup(surface, prev_word, next_word)
            except Exception:
                chosen = None

        kind = 'plain'
        if chosen and chosen != surface:
            kind = 'chosen_hint'   # 過去に選んだ実績があるという印だけ
        elif detail is not None:
            kind = 'suspect'

        units.append({
            'start': src_start,
            'end': src_end,
            'text': surface,
            'base': surface,
            'reading': reading or '',
            'prev': prev_word,
            'next': next_word,
            'kind': kind,
            'detail': detail,
            'chosen_hint': chosen,
        })

    return text, units


def build_line_units(result, tokenize_fn, choice_store=None):
    """
    1行分の補正結果を、語の単位に組み立てる。

    result: corrector.correct_line() の戻り値
    tokenize_fn: 行を語に区切る関数
    choice_store: choices.ChoiceStore（ユーザーの選び直しの記憶）

    戻り値: (表示するテキスト, [単位, ...])
    """
    text = result.get('corrected', '')
    if not text:
        return text, []

    fixed_spans = result.get('spans', []) or []
    details = result.get('details', []) or []

    try:
        tokens = tokenize_fn(text)
    except Exception:
        tokens = []

    # 語の連結が元のテキストと一致しない場合は、区切りを信用しない。
    # 行全体を1トークンにすると、補正が1箇所でもあるだけで
    # 行全体が「補正あり」の色になる（実機で報告された）。
    # 補正の位置（spans）は分かっているので、その内外で区切った
    # 単位を代わりに使う。
    if not tokens or ''.join(t[0] for t in tokens) != text:
        pieces = _units_from_spans(text, fixed_spans, details, 'fixed')
        tokens = [(u['text'], '不明', u['reading'], u['start'], u['end'],
                   False) for u in pieces]

    # ユーザーの選び直しを、生テキストへの一致で先に確定する
    choice_ranges = _find_choice_ranges(text, tokens, choice_store)

    units = []
    out = []
    out_pos = 0      # 表示テキスト上の位置
    src_pos = 0      # 元テキスト上の位置
    ci = 0           # choice_ranges の添字
    ti = 0           # tokens の添字

    def emit(shown, base, reading, kind, detail, prev, next_):
        nonlocal out_pos
        units.append({
            'start': out_pos,
            'end': out_pos + len(shown),
            'text': shown,
            'base': base,
            'reading': reading,
            'prev': prev,
            'next': next_,
            'kind': kind,
            'detail': detail,
        })
        out.append(shown)
        out_pos += len(shown)

    n = len(text)
    while src_pos < n:
        # 選び直しの範囲がこの位置から始まるなら、1つの単位として出す
        if ci < len(choice_ranges) and choice_ranges[ci][0] == src_pos:
            s, e, original, chosen = choice_ranges[ci]
            ci += 1
            emit(chosen, original, '', 'chosen',
                 _find_detail(s, e, fixed_spans, details),
                 _token_before(tokens, s), _token_after(tokens, e))
            src_pos = e
            continue

        # 次の選び直し範囲の手前までが、通常の語の領域
        limit = choice_ranges[ci][0] if ci < len(choice_ranges) else n

        # 現在位置を含む語まで進める
        while ti < len(tokens) and tokens[ti][4] <= src_pos:
            ti += 1
        if ti >= len(tokens):
            # 保険: 語で覆えない残り
            frag = text[src_pos:limit]
            emit(frag, frag, '', 'plain',
                 _find_detail(src_pos, limit, fixed_spans, details),
                 _token_before(tokens, src_pos), _token_after(tokens, limit))
            src_pos = limit
            continue

        surface, _pos_tag, reading, ts, te = (tokens[ti][0], tokens[ti][1],
                                              tokens[ti][2], tokens[ti][3],
                                              tokens[ti][4])
        frag_start = max(ts, src_pos)
        frag_end = min(te, limit)
        frag = text[frag_start:frag_end]

        if frag == surface:
            # 語がそのまま収まる（通常の場合）
            prev_w = tokens[ti - 1][0] if ti > 0 else ''
            next_w = tokens[ti + 1][0] if ti + 1 < len(tokens) else ''
            frag_reading = reading or ''
        else:
            # 選び直しの範囲が語の途中を切った。残りの断片を出す。
            # 断片の読みは分からないので、かなの場合だけ自身を読みとする。
            prev_w = _token_before(tokens, frag_start)
            next_w = _token_after(tokens, frag_end)
            frag_reading = frag if all(
                '\u3041' <= c <= '\u3096' or c == 'ー' for c in frag) else ''

        detail = _find_detail(frag_start, frag_end, fixed_spans, details)
        emit(frag, frag, frag_reading,
             'fixed' if detail is not None else 'plain',
             detail, prev_w, next_w)
        src_pos = frag_end

    return ''.join(out), units


def make_range_unit(line_text, units, start, end):
    """
    ドラッグで選ばれた範囲 [start, end) を、選び直しの単位に仕立てる。

    janome の区切りが実態と合わないとき（ひ/ら/が/なを 等）のために、
    ユーザーが自分で範囲を決められるようにする。
    前後の語は、範囲の外側にある既存の単位から取る。

    範囲の読みは、覆っている単位の読みを繋いで作る。
    「タン具」なら たん＋ぐ＝たんぐ。これが無いと漢字・カタカナ
    混じりの範囲は読みが引けず、候補が一切出せない。
    さらに「時ッ層」のような誤変換では、漢字が別の読みで
    確定していることがある（時=とき だが意図は じ）ため、
    区分ごとの表記と読みを segments として持たせ、
    候補づくり側で読みの組み合わせを試せるようにする。

    戻り値: 単位（build_line_units と同じ形式＋segments）。
            範囲が不正なら None。
    """
    if not (0 <= start < end <= len(line_text)):
        return None
    sel = line_text[start:end]
    if not sel.strip():
        return None

    prev = ''
    next_ = ''
    for u in units:
        if u['end'] <= start:
            prev = u['text']
        if u['start'] >= end and not next_:
            next_ = u['text']

    def _kana_only(s):
        return all('\u3041' <= c <= '\u3096' or c == 'ー' for c in s)

    # 範囲が覆っている単位を、断片も含めて区分に分ける
    segments = []      # [(表記, 読み or ''), ...]
    for u in units:
        s = max(u['start'], start)
        e = min(u['end'], end)
        if s >= e:
            continue
        frag = line_text[s:e]
        if frag == u['text']:
            reading = u['reading'] or (frag if _kana_only(frag) else '')
        else:
            # 単位の途中で切れた断片。かなならそのまま読みにできる
            reading = frag if _kana_only(frag) else ''
        segments.append((frag, reading))

    if not segments:
        segments = [(sel, sel if _kana_only(sel) else '')]

    # 全区分の読みが揃っていれば、繋いだものを範囲全体の読みとする
    if all(r for _t, r in segments):
        reading = ''.join(r for _t, r in segments)
    elif _kana_only(sel):
        reading = sel
    else:
        reading = ''

    return {
        'start': start, 'end': end,
        'text': sel, 'base': sel,
        'reading': reading,
        'prev': prev, 'next': next_,
        'kind': 'range', 'detail': None,
        'segments': segments,
    }


def unit_at(units, col):
    """表示テキスト上の位置 col にある語を返す。無ければ None。"""
    for u in units:
        if u['start'] <= col < u['end']:
            return u
    return None
