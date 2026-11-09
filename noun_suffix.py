# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
漢字の名詞のすぐ後ろに、接尾の語（中・的 など）の読みがかなのまま残った所に、その漢字を置く（補正担当・2026-10-31。
名詞の読みとつなぐと辞書の1語になる字（乗車けん → 乗車券）も同じ形で置く。
うにさん 10-31 03:06Z「かなだけの行も、漢字にするべき部分は漢字に」、未解決の「変換ちゅう」の型）。

IME が名詞までを漢字にし、続く接尾の語をかなのまま確定した跡。かなのままだと解析が ち｜ゅう… と切れて、
その所に紫が付いたり、別の字への打ち違いと見られたりする（作った例: 会議ちゅうです → 会議ちょうです）。

置くのは次が全部そろうときだけ:
  - かなの並びの頭の読みの漢字1字（今までの置き方の候補・一般の文章でよく使う字）を置くと、解析がその字を
    名詞の「接尾」と読み、読みも同じ。
  - 読みは2字以上（1字の読みは助詞・活用の打ち違いと重なる: 雨か・精算き）。
  - その字の後ろ、かなの並びの終わりまでが助詞・助動詞だけで、すぐ後ろは助詞か だ・です（中です・中に・的に・
    中なので。利用てきません の ません は動詞の後ろの形なので置かない）。
  - 行の自然さ（morphology.path_cost）が SUFFIX_GAIN 以上よくなる。かなで書くのが普通の接尾（学生たち・
    来週ごろ・三日ほど）は漢字にすると自然さが下がるので置かない。
  - 置ける字が1つに決まる。
置いた行でほかの補正をし直し、紫が残るなら置かない。特定の語を名指ししない。
"""

SUFFIX_GAIN = 2000     # 置いて path_cost がこれ以上下がるときだけ
MIN_READ = 2           # 接尾の語の読みの長さ（字）。1字の読み（か・き・じ）は助詞や活用の打ち違いと重なる
MAX_READ = 4
COMMON_FACE = 470      # ime_reconvert._rank がこれ以下の字だけ（kana_lattice_place と同じ）


def _hira(ch):
    return 'ぁ' <= ch <= 'ゖ' or ch == 'ー'


def _kanji(ch):
    return '一' <= ch <= '鿿' or ch == '々'


def _to_hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')


def _places(line, store, dict_index):
    """[(開始, 終了, 字)]（line の位置）。"""
    try:
        import last_keystroke as LK
        import ime_reconvert
        from morphology import tokenize, path_cost
    except Exception:
        return []
    out = []
    i = 1
    while i < len(line):
        if not (_hira(line[i]) and _kanji(line[i - 1])):
            i += 1
            continue
        j = i
        while j < len(line) and _hira(line[j]):
            j += 1
        k = i
        while k > 0 and _kanji(line[k - 1]):
            k -= 1
        head = list(tokenize(line[k:i]))
        if not head or head[-1].pos != '名詞' or any(x in (head[-1].pos_sub or '') for x in ('接尾', '数', '非自立', '代名詞')):
            i = j
            continue
        # かなのままで既に名詞と読める所（人ごとに の ごと・先生がた の がた）は、書くつもりのかな
        # ただし、名詞の読みとつなぐと辞書の1語になる字（電話だい → 電話代）だけは見る。CN_SUFFIX_JOINED_NOUN=0 で前のまま
        _at = [t for t in tokenize(line) if t.start == i and t.pos == '名詞' and t.has_reading]
        already = bool(_at)
        # 接尾と読めるかな（人ごと・学生たち）は書くつもりのかな。見ない
        if already and '接尾' in (_at[0].pos_sub or ''):
            i = j
            continue
        if already and __import__('os').environ.get('CN_SUFFIX_JOINED_NOUN') == '0':
            i = j
            continue
        base = path_cost(line)
        head_face = line[k:i]
        head_read = _to_hira(''.join(t.reading or '' for t in head)) if all(t.has_reading for t in head) else ''
        found = set()
        for L in range(MIN_READ, min(MAX_READ, j - i) + 1):
            rd = line[i:i + L]
            try:
                faces = LK._kanji_choices(rd, store, dict_index)
            except Exception:
                faces = []
            cands = [] if already else [(f, False) for f in faces
                                        if len(f) == 1 and _kanji(f) and ime_reconvert._rank(f) <= COMMON_FACE]
            # 名詞の読みとつなぐと辞書の1語（乗車＋けん → じょうしゃけん → 乗車券）になる字。辞書の候補の先頭が
            # 名詞の字そのままに漢字1字を足した形のときだけ
            if head_read:
                try:
                    whole = LK._kanji_choices(head_read + rd, store, dict_index)
                except Exception:
                    whole = []
                if whole and whole[0].startswith(head_face) and len(whole[0]) == len(head_face) + 1 \
                        and _kanji(whole[0][-1]):
                    cands.append((whole[0][-1], True))
            # 置く所のかなが元の解析で助詞・助動詞だけ（先生｜が｜た）なら、文法のかなとして読める。接尾の字（型）は置かない
            # （名詞とつないで辞書の1語になる字は置く）。CN_SUFFIX_GRAMMAR_KANA=0 で前のまま
            if __import__('os').environ.get('CN_SUFFIX_GRAMMAR_KANA') != '0':
                _span = [t for t in tokenize(line) if i <= t.start < i + L]
                if _span and _span[-1].end == i + L and all(t.pos in ('助詞', '助動詞') and t.has_reading for t in _span):
                    cands = [c for c in cands if c[1]]
            for f, joined in cands:
                alt = line[:i] + f + line[i + L:]
                toks = list(tokenize(alt))
                if joined:
                    # 解析が名詞と字を1語（乗車券）か、名詞＋名詞の字と読む
                    at = [t for t in toks if t.start < i + 1 <= t.end and t.end == i + 1]
                    if not at or at[0].pos != '名詞' or at[0].start < k or not at[0].has_reading:
                        continue
                else:
                    at = [t for t in toks if t.start == i]
                    if not at or at[0].surface != f or at[0].pos != '名詞' or '接尾' not in (at[0].pos_sub or '') \
                            or _to_hira(at[0].reading) != rd:
                        continue
                end = j - L + 1
                rest = [t for t in toks if i + 1 <= t.start < end]
                if any(t.pos not in ('助詞', '助動詞') or not t.has_reading for t in rest):
                    continue
                # 名詞のすぐ後ろに来られるのは助詞か断定（だ・です）。ます・ない などは動詞の後ろの形（利用てきません）
                if rest and rest[0].pos == '助動詞' and rest[0].base_form not in ('だ', 'です'):
                    continue
                if rest and rest[-1].end != end:
                    continue
                cost = path_cost(alt)
                if base is None or cost is None or base - cost < SUFFIX_GAIN:
                    continue
                found.add((i, i + L, f, joined))
        # 名詞とつないで辞書の1語になる字が在れば、それを採る（乗車けん の 券。圏・県 の接尾より確か）
        if any(x[3] for x in found):
            found = {x for x in found if x[3]}
        found = {x[:3] for x in found}
        if len(found) == 1:
            out.extend(found)
        i = j
    return out


def repair_line(line, result, run, store, dict_index, decided=()):
    """result: 行のほかの補正の答え。run(text): 置いた行の補正をし直す。置けなければ result のまま。"""
    if not isinstance(result, dict):
        return result
    try:
        places = [p for p in _places(line, store, dict_index)
                  if not any(a < p[1] and p[0] < b for a, b in decided)]
    except Exception:
        return result
    if not places:
        return result
    alt = line
    for s, e, f in sorted(places, reverse=True):
        alt = alt[:s] + f + alt[e:]
    try:
        got = run(alt)
    except Exception:
        return result
    if not isinstance(got, dict) or got.get('odd_spans') or got.get('unsure_spans'):
        return result
    text = got.get('corrected') or alt
    import difflib
    ops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return result
    out = dict(got)
    out.update({'original': line, 'corrected': text, 'changed': True,
                'details': [[line[s:e], f, '名詞の後ろの接尾'] for s, e, f in places] + list(got.get('details') or []),
                'spans': [[o[3], o[4]] for o in ops], 'original_spans': [[o[1], o[2]] for o in ops]})
    return out
