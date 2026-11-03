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
                 occurrence_strokes=(), tab_has_kana=None, previous_line=None, defer_heavy=False):
    """補正エンジンの入口。

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
        result = _correct_line_strokes(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                                       nearby_words, recent,
                                       occurrence_readings, occurrence_calculations, occurrence_strokes)
        # 前の行から続く行頭の付属語（に・が・ので）に掛かった直しや紫だけを、前の行の最後の句とつないだ形で見直す。
        # 行頭に掛からない直し・紫はこの行だけの答えのまま（つなぐと別の所の直しが変わり、正しく直った行が直らなく
        # なった: 挙動関連担当の測り 2026-11-02）
        prefix = _continuation_prefix(previous_line, line)
        head_end = _head_end(line) if prefix else 0
        if prefix and head_end and _touches_head(result, line, head_end):
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
                                              dict_index, nearby_words, recent,
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
    result = _elongation_guard(line, result, store, context_vocab, decisions, input_method, context_vec, dict_index)
    if token is not None and isinstance(result, dict):
        result = dict(result)
        result['used_keys'] = record.answer()
    if deferred and isinstance(result, dict):
        result = dict(result)
        result['deferred_stages'] = sorted(set(deferred))
    return result


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



def _correct_line_strokes(line, store, context_vocab, decisions, input_method, context_vec, dict_index,
                          nearby_words, recent_words, occurrence_readings, occurrence_calculations, occurrence_strokes):
    def plain(text, readings=occurrence_readings, calculations=occurrence_calculations):
        return _correct_line_halfwidth(text, store, context_vocab=context_vocab, decisions=decisions,
                                       input_method=input_method, context_vec=context_vec, dict_index=dict_index,
                                       nearby_words=nearby_words, recent_words=recent_words,
                                       occurrence_readings=readings, occurrence_calculations=calculations)
    def stages(line, plain):
        return _line_stages(line, plain, store, dict_index, decisions, context_vec, input_method, nearby_words)
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
    return _after_stroke_repair(line, result, out, lambda text: stages(text, run))


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
    if slow:
        result = _noun_suffix_mark(line, first, store, dict_index, decisions)
    else:
        result = _noun_suffix(line, first, plain, store, dict_index, decisions)
    result = _learned_gate(line, result, store, decisions, input_method)
    result = _word_pair_mark(line, _lattice_place(line, result, store, dict_index), store, dict_index, decisions)
    result = _renyou_tail_slip(line, result, decisions, input_method)
    result = _degree_adverb(line, result, dict_index, decisions)
    result = _dangling_verb(line, result, decisions)
    result = _impossible_slip(line, result, decisions, input_method)
    result = _kanji_doubt(line, result, store, dict_index, decisions)
    result = _ime_reconvert(line, result, decisions, input_method)
    result = _honorific_stem(line, result, decisions)
    result = _question_ka(line, result, decisions)
    result = _formal_noun_gap(line, result, decisions)
    result = _te_dropped(line, result, decisions)
    result = _pair_choice(line, result, decisions, input_method)
    result = _rival_repair(line, result, decisions, input_method)
    result = _nearby_one_key(line, result, nearby_words, input_method, decisions)
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
        result = _predicate_slip(line, result, plain, store, dict_index, context_vec, decisions, input_method)
        if deferred is not None and result.get('odd_spans') and __import__('os').environ.get('CN_TYPING_RESPELL') != '1':
            # 打鍵中の行の紫の所の読み直し（odd_respell）は、行全体の補正し直しを何度も回すので手が止まってから
            # （挙動関連担当の測り 2026-11-03: 短い行の5字で打鍵中の待ちの約4割）。紫は打鍵中も出たまま
            deferred.append('odd_respell')
        else:
            result = _odd_respell(line, result, plain, store, dict_index, context_vec, decisions, input_method)
    result = _kana_keep(line, result, decisions)
    result = _made_word_check(line, result, decisions, store, dict_index)
    result = _yoon_slip(line, result, decisions, input_method)
    result = _keep_converted(line, result, decisions)
    result = _broken_shape(line, result, decisions, input_method)
    return _drop_mixed_katakana_marks(line, result)


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
        return predicate_slip.repair_line(line, result, run, store, dict_index, context_vec,
                                          corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _odd_respell(line, result, run, store, dict_index, context_vec, decisions, input_method):
    """紫の所の読みに一般の打ち違いの戻しを当て、行がはっきり自然になる形が1つなら直す（odd_respell・2026-11-01）。"""
    try:
        import odd_respell
        return odd_respell.repair_line(line, result, run, store, dict_index, context_vec,
                                       corrector._decided_spans(line, decisions), input_method)
    except Exception:
        return result


def _noun_suffix(line, result, run, store, dict_index, decisions):
    """漢字の名詞のすぐ後ろにかなのまま残った接尾の語（中・的）に漢字を置き、置いた行で補正し直す
    （noun_suffix・2026-10-31）。置けなければ答えはそのまま。"""
    try:
        import noun_suffix
        return noun_suffix.repair_line(line, result, run, store, dict_index, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _lattice_place(line, result, store, dict_index):
    """かなのまま残った文節の頭の並び（かなの文法で説明の付かないもの）の区切りを読みの格子で決めて漢字を置く
    （kana_lattice_place・2026-10-25）。置けなければ答えはそのまま。"""
    try:
        import kana_lattice_place
        return kana_lattice_place.repair_line(line, result, store, dict_index)
    except Exception:
        return result


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


def _nearby_one_key(line, result, nearby_words, input_method, decisions):
    """上下の行に書かれた語と読みが隣のキーの1打だけ違う漢字の語（本字→返事・nearby_one_key・2026-10-30）。"""
    try:
        import nearby_one_key
        return nearby_one_key.repair_line(line, result, nearby_words, input_method, corrector._decided_spans(line, decisions))
    except Exception:
        return result


def _pair_choice(line, result, decisions, input_method='kana'):
    """前後の語との組が例文に無く、同じ読みの別の名詞の組なら在る所（Tatoeba の語の組・pair_choice・2026-10-30）。"""
    try:
        import pair_choice
        return pair_choice.repair_line(line, result, corrector._decided_spans(line, decisions), input_method)
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
