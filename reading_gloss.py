"""漢字の語のすぐ後ろの括弧の中の読みがな（紅葉（もみじ）・緑山駅（みどりやまえき・北山線））を触らない（2026-11-14 補正担当）。

なぜ
----
メモには、漢字の語のすぐ後ろに括弧で読みがなを書き添える書き方がよくある。括弧の中のかなは、書き手が読みとして
わざとかなで書いた所なので、漢字に置いたり（生物（せいぶつ）→ 生物（生物））、1打を戻したり、「品詞として識別できない」
と紫にしたりしない（全体評価の方針 v1 の5）。辞書の読みと合うかは問わない（当て読み・固有名詞がある）。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（答えが出た後に見る）。
1. 行の中で「漢字の字＋開き括弧」の後ろの、かなだけの語句（閉じ括弧・・・、・空白まで）を読みがなと見る。
2. 答えの書き換えのうち、読みがなの中に収まるものは元の字に戻す。
3. 読みがなに掛かる紫・不確かの印を外す。
特定の語や文字列には合わせない。字の種類と括弧の形だけで決める。

2026-11-14 全体評価スレッドの案: 開き括弧＋かな＋閉じ括弧 がそろう読みがなは、括弧ごと抜いた行を補正に通し、
答えに読みがなを元の所へ戻す（後から守るだけだと、読みがなの前後の語が切れて見えて紫・書き換えが残る）。
CN_READING_GLOSS_LIFT=0 で後から守るだけの動き。

切り替え: CN_READING_GLOSS=0 で前のまま。
"""
import difflib
import functools
import os
import unicodedata

_orig = {}


def _on():
    return os.environ.get('CN_READING_GLOSS') != '0'


def _kanji(c):
    return '一' <= c <= '鿿' or c in '々〆ヶ'


def _kana(c):
    return ('ぁ' <= c <= 'ゖ') or ('ァ' <= c <= 'ヺ') or c in 'ーゝゞヽヾ゛゜'


def _open(c):
    return unicodedata.category(c) in ('Ps', 'Pi')


def _stop(c):
    return unicodedata.category(c) in ('Pe', 'Pf') or c in '・、，,／/' or c.isspace()


def glosses(line):
    """読みがなの範囲 [(始め, 終わり)]（元の行の位置）。"""
    out = []
    for i, c in enumerate(line):
        if not _open(c) or i == 0:
            continue
        j = i + 1
        while j < len(line) and not _stop(line[j]):
            j += 1
        if j >= len(line) or j == i + 1:
            continue
        seg = line[i + 1:j]
        if not _kanji(line[i - 1]):
            # かなで書いた語のすぐ後ろに、同じかなを括弧で添えた形（ちず（ちず））も読みがな。括弧の前のかなが
            # 括弧の中とちょうど同じ時だけ（2026-11-15 全体評価、かなで打った正しい文の紫）。CN_READING_GLOSS_SAME=0 で前のまま
            if (os.environ.get('CN_READING_GLOSS_SAME') == '0' or i < len(seg) or line[i - len(seg):i] != seg
                    or not all(_kana(x) for x in seg)):
                continue
        if all(_kana(x) for x in seg) and any(not ('ァ' <= x <= 'ヺ' or x == 'ー') for x in seg) \
                or all(_kana(x) for x in seg) and len(seg) >= 2:
            out.append((i + 1, j))
    return out


def _hit(x, ranges):
    return any(x[0] < e and x[1] > s for s, e in ranges)


def keep(line, result):
    if not _on() or not isinstance(line, str) or not isinstance(result, dict):
        return result
    text = result.get('corrected')
    if not isinstance(text, str):
        return result
    ranges = glosses(line)
    if not ranges:
        return result
    ops = difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes()
    parts, reverted = [], False
    for tag, i1, i2, j1, j2 in ops:
        if tag != 'equal' and any(s <= i1 and i2 <= e and (i1 < i2 or s < i1 < e) for s, e in ranges):
            parts.append(line[i1:i2])
            reverted = True
        else:
            parts.append(text[j1:j2])
    out = dict(result)
    if reverted:
        new = ''.join(parts)
        out['corrected'] = new
        out['changed'] = new != line
        ops2 = difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes()
        out['spans'] = [[j1, j2] for tag, i1, i2, j1, j2 in ops2 if tag != 'equal' and j1 < j2]
        out['original_spans'] = [[i1, i2] for tag, i1, i2, j1, j2 in ops2 if tag != 'equal' and i1 < i2]
        glossed = [line[s:e] for s, e in ranges]
        out['details'] = [d for d in result.get('details') or ()
                          if not (len(d) >= 2 and isinstance(d[0], str) and isinstance(d[1], str) and d[0]
                                  and any(d[0] in g for g in glossed) and d[0] in new)]
    for key in ('odd_spans', 'unsure_spans'):
        if key in result:
            out[key] = [x for x in result.get(key) or () if not (len(x) >= 2 and isinstance(x[0], int) and _hit(x, ranges))]
    if 'odd_reasons' in result:
        out['odd_reasons'] = [x for x in result.get('odd_reasons') or ()
                              if not (len(x) >= 2 and isinstance(x[0], int) and _hit(x, ranges))]
    return out


def lift(line):
    """読みがなを括弧ごと抜いた行と、抜いた所の並び [(抜いた行での位置, 抜いた字)]。抜く物が無ければ (line, [])。
    抜くのは 開き括弧＋かな＋閉じ括弧 がそろう形だけ（中に ・ や添え書きが続く形は抜かず、後から keep で守る）。"""
    cuts, at, parts, removed = [], 0, [], 0
    for s, e in glosses(line):
        if e >= len(line) or unicodedata.category(line[e]) not in ('Pe', 'Pf') or s - 1 < at:
            continue
        parts.append(line[at:s - 1])
        cuts.append((s - 1 - removed, line[s - 1:e + 1]))
        removed += e + 1 - (s - 1)
        at = e + 1
    if not cuts:
        return line, []
    parts.append(line[at:])
    return ''.join(parts), cuts


def _to_text(ops, p):
    """抜いた行の位置 p が、答えの文のどこか（書き換えの中なら、その書き換えの終わり）。"""
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal' and i1 <= p <= i2:
            return j1 + p - i1
        if tag != 'equal' and i1 < p < i2:
            return j2
    return ops[-1][4] if ops else p


def _shift(spans, cuts):
    """位置の並び（抜いた行の位置）を、読みがなを戻した行の位置にする。読みがなをまたぐ範囲は読みがなごと含める。"""
    out = []
    for x in spans or ():
        if not (len(x) >= 2 and isinstance(x[0], int) and isinstance(x[1], int)):
            out.append(x)
            continue
        s = x[0] + sum(len(t) for p, t in cuts if p <= x[0])
        e = x[1] + sum(len(t) for p, t in cuts if p < x[1])
        out.append(type(x)((s, e) + tuple(x[2:])) if isinstance(x, tuple) else [s, e] + list(x[2:]))
    return out


def put_back(line, bare, cuts, result):
    """読みがなを抜いた行の答えに、読みがなを元の所へ戻す。"""
    text = result.get('corrected')
    if not isinstance(text, str):
        return None
    ops = difflib.SequenceMatcher(None, bare, text, autojunk=False).get_opcodes()
    at_text = [(_to_text(ops, p), t) for p, t in cuts]
    parts, at = [], 0
    for q, t in at_text:
        parts.append(text[at:q])
        parts.append(t)
        at = q
    parts.append(text[at:])
    out = dict(result)
    out['corrected'] = ''.join(parts)
    if 'original' in result:
        out['original'] = line      # 答えの元の行は頼まれた行（抜いた短い行のままだとタブを済みにできない）
    out['changed'] = out['corrected'] != line
    for key in ('odd_spans', 'unsure_spans', 'original_spans', 'odd_reasons'):
        if key in result:
            out[key] = _shift(result.get(key), cuts)
    if 'spans' in result:
        out['spans'] = _shift(result.get('spans'), at_text)
    return out


def correct_line(line, *args, **kwargs):
    fn = _orig['correct_line']
    if _on() and isinstance(line, str) and os.environ.get('CN_READING_GLOSS_LIFT') != '0':
        try:
            bare, cuts = lift(line)
        except Exception:
            cuts = []
        if cuts and bare.strip():
            # 読みがなを抜いた行を補正に通す（読みがなは語の途中に入る書き添えで、残したまま読むと 語＋送りがな が
            # 切れて見える: 作った例 雨宿（あまやど）りをする）。位置を返す呼び戻しは位置がずれるので渡さない
            kw = dict(kwargs)
            kw.pop('on_early_odd', None)
            try:
                result = fn(bare, *args, **kw)
                if isinstance(result, dict):
                    back = put_back(line, bare, cuts, result)
                    if back is not None:
                        return back      # 読みがなの中は触っていないので、後からの守りは要らない（またぐ紫を消さない）
                    return fn(line, *args, **kwargs)
                return result
            except Exception:
                pass
    result = fn(line, *args, **kwargs)
    try:
        return keep(line, result)
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
