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
語を選び直すための候補づくり。

補正エンジンが自動で直すのは「明確に誤りだと言える」ものだけで、
判断がつかないものはあえて直さない（SPEC.md の設計方針）。
そのぶん取りこぼしが出るので、ユーザーが自分で選び直せる道を用意する。

IMEの変換候補と同じ感覚で使えるよう、候補は次の順に並べる。

  1. 同音異義語   読みが同じ別の表記（公園 / 講演 / 後援）
                  自動補正が最も苦手とする領域なので最優先で出す
  2. 打ち間違い   隣接キー・脱字・押しすぎ・順序間違いで
                  届く範囲にある語（vocabulary の探索を流用）
  3. かな表記     ひらがな・カタカナそのもの

補正エンジンとは独立しており、ここでは「直すべきか」を一切判断しない。
選ぶのはユーザーなので、可能性を広く並べることだけを仕事にする。
"""


def _is_hiragana(ch):
    return '\u3041' <= ch <= '\u3096'


def _is_katakana(ch):
    return '\u30a1' <= ch <= '\u30f6'


def _to_katakana(kana):
    """ひらがなをカタカナに直す。"""
    out = []
    for ch in kana:
        if _is_hiragana(ch):
            out.append(chr(ord(ch) + 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def _to_hiragana(kana):
    out = []
    for ch in kana:
        if _is_katakana(ch):
            out.append(chr(ord(ch) - 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def resolve_reading(surface, reading, store):
    """
    語の読みを決める。

    形態素解析が読みを返さない語（未知語・誤字）も多いので、
    表記からの逆引きと、かなそのものを順に試す。
    """
    if reading and all(_is_hiragana(c) or c == 'ー' for c in reading):
        return reading
    if reading:
        # janome はカタカナで読みを返すことがある
        hira = _to_hiragana(reading)
        if all(_is_hiragana(c) or c == 'ー' for c in hira):
            return hira
    found = store.reading_of(surface)
    if found:
        return found
    if all(_is_hiragana(c) or c == 'ー' for c in surface):
        return surface
    if all(_is_katakana(c) or c == 'ー' for c in surface):
        return _to_hiragana(surface)
    return None


def _split_stem_tail(word):
    """語を「漢字・カタカナの部分」と「後ろのひらがな」に分ける。"""
    i = len(word)
    while i > 0 and _is_hiragana(word[i - 1]):
        i -= 1
    return word[:i], word[i:]


# 活用すると同じ語幹の読みになってしまう不規則動詞。
# 「来る」「着る」はどちらも連用形・て形が「き」になるため、
# 「きている」「きた」のような活用済みの形は、辞書にも語彙にも
# 単独の語としては載っておらず、通常の同音探索では見つからない。
# （「来る」はイレギュラーな活用のため、辞書の見出し語の読み
#   「くる」から機械的に導くこともできない）
_IRREGULAR_STEM_KANJI = {
    'き': ['来', '着'],
}

# 活用・助動詞の続きとして良く現れる語尾。長いものから順に試す。
_VERB_TAIL_SUFFIXES = [
    'ていない', 'ています', 'ていた', 'ていて', 'ている',
    'てきた', 'てきて', 'てくる',
    'ってきた', 'ってきて', 'ってくる',
    'てしまった', 'てしまう',
    'てくれた', 'てくれる',
    'た', 'て',
]


def verb_stem_candidates(reading):
    """
    活用形の語幹に含まれる、不規則動詞の同音を展開する。

    「もどってきている」のような、頭に別の語が付いた複合表現でも、
    語尾を剥がした残りが「き」で終わっていれば
    （＝「来る」「着る」の活用形が埋め込まれていれば）そこだけを
    漢字候補に差し替える。頭の部分（もどって、等）はそのまま残す。

    戻り値: 漢字を当てた候補の文字列のリスト。
    """
    out = []
    for suf in _VERB_TAIL_SUFFIXES:
        if not reading.endswith(suf):
            continue
        head = reading[:-len(suf)] if suf else reading
        if head.endswith('き'):
            prefix = head[:-1]
            for kanji in _IRREGULAR_STEM_KANJI['き']:
                out.append(prefix + kanji + suf)
    return out


def align_okurigana(original, candidate):
    """
    候補の送り仮名を、元の語の形に合わせる。

    活用する語を差し替えるとき、辞書から出てくるのは原形が多い。
      売っ（た） を 打つ に差し替えると「打つた」になってしまう。
    元の語の送り仮名「っ」を残して「打っ」にすれば「打った」になる。

    漢字部分だけを入れ替え、ひらがな部分は元のものを使う。
    どちらかに漢字部分が無い場合は、判断できないので候補のまま返す。
    """
    o_stem, o_tail = _split_stem_tail(original)
    c_stem, c_tail = _split_stem_tail(candidate)
    if not o_stem or not c_stem:
        return candidate
    if o_tail == c_tail:
        return candidate
    # 送り仮名の長さが大きく違う場合は別の語の可能性が高いので触らない
    if abs(len(o_tail) - len(c_tail)) > 1:
        return candidate
    return c_stem + o_tail


def build_candidates(surface, reading, store, find_readings,
                     max_dist=1.6, max_edits=2,
                     max_homophones=8, max_typos=8, dict_index=None,
                     context_vec=None, surrounding_words=None):
    """
    ある語について、選び直せる候補を作る。

    surface: いま表示されている表記
    reading: 形態素解析が返した読み（無ければ空でよい）
    dict_index: janome 辞書の読み索引（dict_index.DictIndex）。
        個人語彙に無い語（平仮名 等）も候補に出すために使う。
        None でも動く（候補が個人語彙の範囲に狭まるだけ）。
    context_vec: 語の共起から作った軽量な文脈ベクトル
        （context_vec.ContextVectorStore）。渡すと、同じ種類
        （kind）の中での並び順に、周辺の語との意味的な近さを
        軽く反映する。候補そのものの取捨選択（何を候補に含めるか）
        には使わない。あくまで「たくさん出た候補のうち、
        文脈に合いそうなものを上に寄せる」順位付けの材料。
        None なら、これまでどおりの順（探索で見つかった順）。
    surrounding_words: 対象語の前後の内容語（近い順）。
        context_vec と併せて渡す。

    戻り値: [{'surface', 'reading', 'kind'}, ...]
        kind は 'homophone'（同音異義語）/ 'typo'（打ち間違い）/
                'kana'（かな表記）
        いま表示中の表記は含めない。
    """
    reading = resolve_reading(surface, reading, store)
    out = []
    seen = {surface}

    def push(cand_surface, cand_reading, kind):
        if not cand_surface or cand_surface in seen:
            return
        seen.add(cand_surface)
        out.append({'surface': cand_surface,
                    'reading': cand_reading,
                    'kind': kind})

    if reading:
        # --- 1. 同音異義語（読みが完全に同じ別の表記） ---
        # 自動補正では文脈が無いと選べないため触れない領域。
        # ここが選び直しの主目的なので最優先で並べる。
        # 個人語彙を先に（本人がよく使う表記が上に来る）、
        # その後に janome 辞書全体から補う。
        for entry in store.lookup(reading)[:max_homophones]:
            push(entry['surface'], reading, 'homophone')
        if dict_index is not None:
            for s in dict_index.surfaces_for_reading(reading):
                if len([c for c in out if c['kind'] == 'homophone']) \
                        >= max_homophones:
                    break
                push(s, reading, 'homophone')

        # 活用形に埋め込まれた不規則動詞の同音（来ている／着ている 等）。
        # 辞書にも語彙にも活用済みの複合形は載っていないため、
        # 通常の同音探索・辞書索引のどちらでも見つからない。
        for cand in verb_stem_candidates(reading):
            push(cand, reading, 'homophone')

        # --- 2. 打ち間違いで届く範囲の語 ---
        # 隣接キー・脱字・押しすぎ・順序間違いをまとめて扱う探索を流用する。
        try:
            found = find_readings(reading, store, max_dist=max_dist,
                                  max_edits=max_edits)
        except Exception:
            found = []
        n_typo = 0
        for cand_reading, _cost, edits in found:
            if n_typo >= max_typos:
                break
            if edits == 0 or cand_reading == reading:
                continue
            surfaces = [e['surface'] for e in store.lookup(cand_reading)[:2]]
            if not surfaces and dict_index is not None:
                surfaces = dict_index.surfaces_for_reading(cand_reading)[:1]
            for s in surfaces:
                if n_typo >= max_typos:
                    break
                before = len(out)
                push(s, cand_reading, 'typo')
                if len(out) > before:
                    n_typo += 1

        # --- 2.5 配列上で遠い取り違え ---
        # 従来の探索（find_readings）は隣接キーの押し間違いしか
        # 扱えないため、「乱後（らんご）」「やん後（やんご）」の
        # ように配列上で遠い取り違えを含む語では候補が1つも出ない
        # （実機で「何かしらの候補は出すべき。元の文字列が意味を
        #   なさないので」と指摘された）。
        # 自動補正の再構築と同じ探索（find_similar_readings）を
        # 候補づくりにも使う。ここは選ぶのがユーザーなので、
        # 自動補正のような厳しい関門は掛けず、届く範囲を広く見せる。
        if n_typo < max_typos:
            try:
                from vocabulary import find_similar_readings
                far = find_similar_readings(reading, store, max_cost=4.0)
            except Exception:
                far = []
            for cand_reading, _cost, edits in far:
                if n_typo >= max_typos:
                    break
                if edits == 0 or cand_reading == reading:
                    continue
                surfaces = [e['surface']
                            for e in store.lookup(cand_reading)[:2]]
                if not surfaces and dict_index is not None:
                    surfaces = dict_index.surfaces_for_reading(
                        cand_reading)[:1]
                for s in surfaces:
                    if n_typo >= max_typos:
                        break
                    before = len(out)
                    push(s, cand_reading, 'typo')
                    if len(out) > before:
                        n_typo += 1

        # --- 3. かなそのもの ---
        # 「漢字にせずひらがなで置いておきたい」場合があるため。
        push(reading, reading, 'kana')
        push(_to_katakana(reading), reading, 'kana')

    if context_vec is not None and surrounding_words:
        _reorder_by_context(out, context_vec, surrounding_words)

    return out


def _reorder_by_context(candidates, context_vec, surrounding_words):
    """
    候補リストを、種類（kind）ごとのまとまりを保ったまま、
    その中だけを文脈スコアの高い順に並べ替える。
    さらに、明らかに文脈に合わない「打ち間違い」候補は取り除く。

    種類をまたいで並べ替えない理由: 同音異義語を最優先に、
    次に打ち間違いという順序そのものは、自動補正が最も苦手とする
    領域を優先して見せるという設計上の意図があり（SPEC.md参照）、
    文脈スコアの強弱でその大枠を崩したくない。

    取り除く対象を「打ち間違い」だけに限る理由:
      同音異義語は「読みが同じ別の表記」であり、書き手が本当に
      意図した語である可能性が常にある。文脈スコアが低いという
      だけで消すと、選び直したい語が一覧から無くなってしまう。
      一方「打ち間違い」は、こちらが推測で広げた候補にすぎない。
      「『単語として成立』の候補に『単行』『飛び』が出る」
      「『分からない文章』が『悪からない花粉症』になる」
      という実機からの指摘のとおり、ここが雑音の主な出どころなので、
      文脈から見て明らかに遠いものは見せないほうがよい。
    """
    scores = context_vec.rank_candidates(
        [c['surface'] for c in candidates], surrounding_words)
    if not scores or not any(v > 0 for v in scores.values()):
        return    # 手がかりが無ければ、元の順のまま何もしない

    # 打ち間違い候補のうち、文脈と全く結び付かないものを落とす。
    # ただし全滅させない: 周辺語と結び付く候補が1つも無い場合は
    # 判断材料が乏しいということなので、何も落とさない
    # （「判断がつかないものは触らない」という方針を、
    #   候補の取捨にも当てはめる）。
    typo_scores = [scores.get(c['surface'], 0.0)
                  for c in candidates if c['kind'] == 'typo']
    if typo_scores and any(s > 0 for s in typo_scores):
        kept = []
        for c in candidates:
            if c['kind'] == 'typo' and scores.get(c['surface'], 0.0) <= 0.0:
                continue    # 文脈と全く結び付かない打ち間違い候補
            kept.append(c)
        # 打ち間違いが全部消えてしまう場合だけは、元に戻す
        # （候補が同音とかなだけになると、選択肢が減りすぎる）
        if any(c['kind'] == 'typo' for c in kept):
            candidates[:] = kept

    by_kind = {}
    order = []
    for c in candidates:
        k = c['kind']
        if k not in by_kind:
            by_kind[k] = []
            order.append(k)
        by_kind[k].append(c)

    for k in order:
        # 安定ソート。同スコアなら元の順を保つ。
        by_kind[k].sort(key=lambda c: -scores.get(c['surface'], 0.0))

    candidates[:] = [c for k in order for c in by_kind[k]]




def build_range_candidates(segments, store, find_readings,
                           max_dist=1.6, max_edits=2,
                           max_variants=8, dict_index=None, **kwargs):
    """
    ドラッグ範囲の候補を、読みの組み合わせを試しながら作る。

    誤変換された範囲では、漢字が意図と別の読みで確定している。
      「時ッ層」= 時(とき) ッ(っ) 層(そう) だが、意図は じ・っ・そう
    そこで区分ごとに「確定した読み」に加えて
    「その表記が持ちうる別の読み」（辞書の逆引き）を候補にし、
    組み合わせた読みそれぞれで同音異義語を探す。
    じっそう が組み合わせに現れれば「実装」に届く。

    segments: [(表記, 読み or ''), ...]  units.make_range_unit が作る
    戻り値: build_candidates と同じ形式
    """
    if not segments:
        return []

    # 区分ごとの読みの選択肢を集める
    options = []
    for text, reading in segments:
        opts = []
        if reading:
            opts.append(reading)
        if dict_index is not None:
            for r in dict_index.readings_for_surface(text):
                if r not in opts:
                    opts.append(r)
        if not opts:
            # 読みがまったく分からない区分があれば、組み合わせは作れない
            opts = [None]
        options.append(opts[:4])

    # 読みの組み合わせを作る（先頭＝確定した読みの組が最優先）
    combos = ['']
    for opts in options:
        new = []
        for prefix in combos:
            for o in opts:
                if o is None:
                    continue
                if len(new) >= max_variants:
                    break
                new.append(prefix + o)
            if len(new) >= max_variants:
                break
        combos = new
        if not combos:
            break

    surface_all = ''.join(t for t, _r in segments)
    out = []
    seen = {surface_all}

    def take(sub, allow_kinds):
        for c in sub:
            if c['kind'] not in allow_kinds or c['surface'] in seen:
                continue
            seen.add(c['surface'])
            out.append(c)

    # 1周目: 全ての読みの組み合わせから同音異義語だけを集める。
    # 「じっそう」の組み合わせに「実装」があれば、ここで同音として並ぶ。
    for combo in combos:
        take(build_candidates(surface_all, combo, store, find_readings,
                              max_dist=max_dist, max_edits=0,
                              dict_index=dict_index, **kwargs),
             ('homophone',))

    # 2周目: 確定した読み（先頭の組み合わせ）だけ、
    # 重い打ち間違い探索とかな表記も掛ける。
    if combos:
        take(build_candidates(surface_all, combos[0], store, find_readings,
                              max_dist=max_dist, max_edits=max_edits,
                              dict_index=dict_index, **kwargs),
             ('typo', 'kana'))

    # 3周目: 前の部分だけを置き換え、後ろはそのまま残す。
    #
    # 活用する語は「売っ＋た」のように語幹と語尾に分かれる。
    # 「売った」全体では辞書に無いので同音異義語が見つからないが、
    # 語幹「売っ（うっ）」なら「打っ」に届く。
    # 後ろの「た」を保ったまま差し替えることで「打った」が作れる。
    # （語尾だけ変えた「打つ」を出しても解決しないため）
    if len(segments) >= 2:
        for k in range(len(segments) - 1, 0, -1):
            head_text = ''.join(t for t, _r in segments[:k])
            tail_text = ''.join(t for t, _r in segments[k:])
            head_readings = []
            hr = ''.join(r for _t, r in segments[:k])
            if all(r for _t, r in segments[:k]):
                head_readings.append(hr)
            if dict_index is not None and k == 1:
                for r in dict_index.readings_for_surface(head_text):
                    if r not in head_readings:
                        head_readings.append(r)
            for hread in head_readings[:3]:
                sub = build_candidates(head_text, hread, store, find_readings,
                                       max_dist=max_dist,
                                       max_edits=max_edits,
                                       dict_index=dict_index, **kwargs)
                for c in sub:
                    if c['kind'] not in ('homophone', 'typo'):
                        continue
                    # 原形で出てきた候補を、元の活用形に合わせる
                    # （売っ+た に対し 打つ ではなく 打っ にする）
                    aligned = align_okurigana(head_text, c['surface'])
                    whole = aligned + tail_text
                    if whole in seen:
                        continue
                    seen.add(whole)
                    out.append({'surface': whole,
                                'reading': (c.get('reading') or '') ,
                                'kind': c['kind']})

    # 最後に種類で並べ直す（同音 → 打ち間違い → かな）。
    # 語尾を保った差し替え（打った）は後から作られるが、
    # 同音なら打ち間違いの推測より上に出したい。
    #
    # 同じ種類の中では、元の語の送り仮名を保っているものを先に出す。
    # 「売った」に対しては「打った」が正解で、
    # 語尾を落とした「打つ」は選んでも解決しないため。
    #
    # そこまでが同じなら、最後に文脈スコア（周辺の語との意味的な
    # 近さ）の高い順にする。ドラッグ範囲の候補は組み合わせを
    # 試すぶん数が増えやすく、そのままでは文脈に合わないものが
    # 上位に並びやすいため（実機からの指摘）。
    # 種類と送り仮名の優先はこれまでどおり保つので、
    # 文脈スコアで大枠の並びが崩れることはない。
    _o_stem, o_tail = _split_stem_tail(surface_all)

    context_vec = kwargs.get('context_vec')
    surrounding_words = kwargs.get('surrounding_words')
    ctx_scores = {}
    if context_vec is not None and surrounding_words:
        try:
            ctx_scores = context_vec.rank_candidates(
                [c['surface'] for c in out], surrounding_words)
        except Exception:
            ctx_scores = {}

    def _rank(c):
        kind_rank = {'homophone': 0, 'typo': 1, 'kana': 2}.get(c['kind'], 9)
        keeps_tail = 0 if (o_tail and c['surface'].endswith(o_tail)) else 1
        # スコアは高いほど上に出したいので符号を反転する
        ctx = -ctx_scores.get(c['surface'], 0.0)
        return (kind_rank, keeps_tail, ctx)

    out.sort(key=_rank)
    return out


KIND_LABELS = {
    'homophone': '同音',
    'typo': '打ち間違い',
    'kana': 'かな',
}
