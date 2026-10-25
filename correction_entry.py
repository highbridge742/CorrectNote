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
import corrector
from vocabulary import find_known_readings_flex
from analysis_work import current_input


_FULLWIDTH_LOWER = {chr(c): chr(c - 0xFEE0) for c in range(ord('ａ'), ord('ｚ') + 1)}


def _halfwidth_letters(line):
    """ローマ字入力で IME が残した全角の小文字（かなの隣のｋ・ｔ）を半角に（字の数は変えない）。
    打ち間違いの印は半角の英字で見ているので、全角のままだと印にも戻しにもならなかった（PC の本物の IME で
    残った英字の6割が全角。2026-10-23・補正C）。かなに接しない全角の英字（全角で書いた語）は触らない。"""
    def hira(ch):
        return 'ぁ' <= ch <= 'ゖ' or ch == 'ー'
    def alnum(ch):
        return 'ａ' <= ch <= 'ｚ' or 'Ａ' <= ch <= 'Ｚ' or '０' <= ch <= '９' or (ch.isascii() and ch.isalnum())
    out = list(line)
    for i, ch in enumerate(line):
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


def correct_line(line, store, context_vocab=None, decisions=None,
                 input_method='kana', context_vec=None, dict_index=None,
                 nearby_words=(), recent_words=(), occurrence_readings=(), occurrence_calculations=(),
                 occurrence_strokes=()):
    """補正エンジンの入口。

    occurrence_strokes: 確定ごとの打鍵 [(start, end, surface, reading, strokes[, shifts])]（strokes・shifts は
    shift_slip.ShiftStrokeClock.take() の [(キーの字, 押した ms)]・[(シフトの押し ms, 離し ms)]）。中身のないシフトがあれば
    小書き・「を」の抜けを戻す（shift_slip・かな入力だけ）。押した間隔の短い巻き込みの隣の2打があれば、
    どちらかを抜いた形を試す（keystroke_doubt.repair_line・打鍵間隔・2026-10-24）。無ければ今まで通り。

    答えの dict には used_keys（used_keys.py: この行が引いた語彙・選び直しの記憶のキー、最近使った語を読んだか、
    全部をなめたか）が付く。
    """
    # 使った材料のキー（used_keys・裏のタブの解析で関係する行だけやり直す）を記録する。答えは変えない
    import used_keys as _used_keys
    token, record = _used_keys.start()
    try:
        result = _correct_line_strokes(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                                       nearby_words, _used_keys.RecentWords(recent_words or ()),
                                       occurrence_readings, occurrence_calculations, occurrence_strokes)
    finally:
        _used_keys.stop(token)
    if token is not None and isinstance(result, dict):
        result = dict(result)
        result['used_keys'] = record.answer()
    return result


def _correct_line_strokes(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes):
    def plain(text, readings=occurrence_readings, calculations=occurrence_calculations):
        return _correct_line_halfwidth(text, store, context_vocab=context_vocab, decisions=decisions,
                                       input_method=input_method, context_vec=context_vec, dict_index=dict_index,
                                       nearby_words=nearby_words, recent_words=recent_words,
                                       occurrence_readings=readings, occurrence_calculations=calculations)
    result = plain(line)
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
                return _stroke_repairs(line, result, strokes, input_method, run, convert)
        except (ImportError, OSError, AttributeError):
            return _stroke_repairs(line, result, strokes, input_method, run, None)
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
    if input_method == 'romaji' and any(ch in _FULLWIDTH_LOWER for ch in line):
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
                spans = [(i, i + 1) for i, ch in enumerate(line) if ch in _FULLWIDTH_LOWER and half[i] != ch]
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
    # 1行に誤字が2つ以上あると、1つ目を直した行で初めて2つ目の印が立つ（これから課題に鳥巣かかる）。
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
            result['odd_spans'] = sorted(list(result.get('odd_spans') or ()) + _extra)
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
    if not spans:
        return result
    done = [tuple(sp[:2]) for sp in (result.get('original_spans') or ())]
    odd = list(result.get('odd_spans') or ())
    added = False
    for a, b in spans:
        # 直した範囲と重なる所・その2字の内には付けない（直しの跡の語の切れ目は当てにならない: 風がつょい→風がつよい）
        if any(a < e + 2 and s - 2 < b for s, e in done) or any(tuple(o[:2]) == (a, b) for o in odd):
            continue
        odd.append((a, b))
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
            return result
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


def _merge_second_pass(line, first, second):
    """2回目の直し（1回目の直した行の上）を、1回目と重ならないものだけ元の行の位置に写して足す。"""
    if not second.get('changed') or second.get('corrected') == first.get('corrected'):
        return first
    pairs = sorted(zip(first.get('spans') or (), first.get('original_spans') or ()))
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
    items.sort(key=lambda x: x[0])
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
