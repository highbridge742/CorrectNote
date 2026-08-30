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

from kana_layout import same_key_characters

# **「語＋接尾で組み立てた表記」の専用枠**（項目48-FA・設計15）。
# ふつうの打ち間違い候補（`max_typos`）とは別に数える。
_MAX_BUILT = 2


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


def _attested_unit(surface, reading, store, dict_index=None):
    """
    その表記は「もう出来上がっている」か（項目48-FA・設計15）。

    2通りのどちらかなら出来上がり:

      1. **単位として在る** —— 語彙にある／刈り込んだ索引にある
         （自動補正の門(1)・項目48-CF/CG と同じ判断）。
      2. **そのままの読みが、その表記そのものに組める** ——
         `ぐたいてき` → 具体＋的 → `具体的`（書かれたとおり）。
         `かいはつしゃ` → 開発＋者 → `開発者`。
         これは**生産的な派生語**の形で、語彙にも索引にも入って
         いないのに正しく書けている（第44回 `probe_asis2.py` で
         実測: 開発者・操作性・実行時・具体的・必要性・利用者・
         最大化・最小化・巨大化・関係者・合計数・個別化・
         反対側・作業中・実現性 が、これで守れる）。

    直したい側は通る: `再退化`（どこにも組めない）・`誘い消化`
    （同）・`殺意代価`（同）・`最大家事`（組めるが **`最大化時`**
    であって書かれたとおりではない）。
    """
    if not surface:
        return False
    try:
        if store.lookup(surface) or store.reading_of(surface):
            return True
    except Exception:
        pass
    if dict_index is not None:
        try:
            if dict_index.readings_for_surface(surface):
                return True
        except Exception:
            pass
    # **世の中で1語として在るなら、もう出来上がっている**
    # （項目48-FC・設計16）。同梱の材料だけでは `一時的` `仕様書`
    # `再起動` `効率化` `効率的` `実体化` `説明書` を守れなかった
    # （第45回の実測）。ここが埋める。
    try:
        import seed_japanese as _sj
        if _sj.is_unit(surface):
            return True
    except Exception:
        pass
    if reading:
        try:
            from corrector import compose_suffix_surface
            if compose_suffix_surface(reading, store, dict_index) == surface:
                return True
        except Exception:
            pass
    return False


def _reading_worth_offering(reading, store, dict_index=None):
    """
    その読みは、そのまま「かなの候補」として出す値打ちがあるか
    （項目48-ET・うにさん指示 (g)「不自然な文字列は候補に出さない」）。

    出してよいのは、**同梱の材料のどれかで説明が付く**とき:

        語彙にある ／ 刈り込んだ索引にある ／ 世の中の集合にある

    3つとも無いなら、それは「漢字から推した壊れた読み」であって、
    かなで置いておきたい語ではない（`メモチチョウ`
    `カンイリュウリョク`）。**判定できないときは出す側**に倒す
    （索引が無い環境では今までどおり）。
    """
    if not reading or len(reading) < 2:
        return True
    try:
        if store.lookup(reading) or store.reading_of(reading):
            return True
    except Exception:
        return True
    if dict_index is None:
        return True                  # 見分けられないので今までどおり
    try:
        if dict_index.surfaces_for_reading(reading):
            return True
    except Exception:
        return True
    try:
        if all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in reading) \
                and dict_index.is_world_reading(reading):
            return True
    except Exception:
        return True
    # **語＋機能語で敷き詰まるなら出す**（`さついだいか`＝
    # さつい＋だいか）。うにさんの指示 (g) は「造語めいた複合を
    # **ひらがなに開いて**そこから直す」なので、開いた形そのものは
    # 候補に残す。落としたいのは `メモチチョウ` のように
    # **どうやっても説明が付かない**並びだけ。
    try:
        from corrector import _covered_by_known
        if _covered_by_known(reading, store):
            return True
    except Exception:
        return True                  # 見分けられないなら出す側
    return False


def build_candidates(surface, reading, store, find_readings,
                     max_dist=1.6, max_edits=2,
                     max_homophones=8, max_typos=8, dict_index=None,
                     context_vec=None, surrounding_words=None,
                     attested=None):
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
    attested: **メモのどこかに実際に書かれている**表記の一覧
        （{読み: [表記, ...]}）。語彙にも辞書索引にも無い語を
        候補に出すために使う（うにさんの指摘・2026-08-11:
        「『ひらがな』をドラッグしても候補に『平仮名』が無い」）。
        `平仮名` は janome の辞書にあるが**コストが 5614** あり、
        索引の上限 4000 に弾かれて入っていない。それでも
        **本人がメモに書いている語**なら、候補に出すのが筋
        （「メモのどこかに正しく書いてある語」という、このアプリの
        よりどころそのもの）。候補は選び直しの材料でしかなく、
        勝手に置き換わるわけではないので、自動補正より広く取ってよい。

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
        # メモに実際に書かれている表記（語彙・索引に無くてもよい）。
        # 語彙の次・辞書索引より先に置く。本人が書いた語のほうが、
        # 辞書から拾った語より当たりやすいため。
        for cand in (attested or {}).get(reading, ())[:max_homophones]:
            push(cand, reading, 'homophone')
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

        # --- 1.5 平仮名の語を漢字にした形（kind='kanji'・項目48-KC）---
        #
        # うにさんの報告（2026-08-27）:「F2 で、なぜか候補が出ない
        # 単語があります。『わずかな』『なぜか』——平仮名だからの
        # ようですね。この場合は漢字変換候補を並べてください」。
        #
        # `わずかな` は 僅か＋な、`なぜか` は 何故＋か のように
        # **語幹だけが辞書に載る**形が多く、全体の読みの一致（上の
        # 同音）では届かない。頭から長い順に「表記が引ける切り方」を
        # 試し、残りの送り・助詞をそのまま付ける（IME の変換と同じ形）。
        # 表記の出どころは 語彙 → 辞書索引 → **同梱の表**
        # （`table_surfaces_for_reading`。索引は費用4000で刈ってあり
        # `何故`・`平仮名` を持たないが、表はその外側も持つ）。
        #
        # **残せる尾は1字まで**（丸ごと か、頭 len-1 字＋尾1字だけ）。
        # 尾を長く許すと、活用の塊に同音の内容語がはまって雑音になる
        # （`されること → 去れること`・`してください → 仕手ください`・
        # `について → 似ついて`。実測・2026-08-27）。尾1字なら
        # `僅かな`・`何故か`・`確かに` は残り、雑音は全部消える。
        _hira = lambda ch: 'ぁ' <= ch <= 'ゖ' or ch == 'ー'
        _kan = lambda ch: '一' <= ch <= '鿿'
        if surface and all(_hira(ch) for ch in surface) and len(surface) >= 2:
            try:
                from corrector import table_surfaces_for_reading as _tsr
            except Exception:
                _tsr = lambda _r: []
            n_kanji = 0
            for k in range(len(surface), len(surface) - 2, -1):
                if k < 2:
                    break
                if n_kanji >= 4:
                    break
                head, tail = surface[:k], surface[k:]
                convs = []
                for e in store.lookup(head)[:2]:
                    convs.append(e['surface'])
                if dict_index is not None:
                    for s in dict_index.surfaces_for_reading(head)[:3]:
                        if s not in convs:
                            convs.append(s)
                for s in _tsr(head)[:3]:
                    if s not in convs:
                        convs.append(s)
                for s in convs:
                    if n_kanji >= 4:
                        break
                    if s == head or not any(_kan(c) for c in s):
                        continue        # 変換になっていない
                    # 尾が残るのに、変換の頭が**い段のかな**で終わる形は
                    # 活用の途中（連用形）に同音をはめただけ
                    # （`について → 似つい＋て`）。語の変換ではないので捨てる。
                    if tail and s[-1:] in 'いきしちにひみりぎじぢびぴ':
                        continue
                    before = len(out)
                    push(s + tail, surface, 'kanji')
                    if len(out) > before:
                        n_kanji += 1

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

        # --- 2.2 入り込んだ1打を落として、語＋接尾で表記を組む ---
        #
        # うにさんの指示 (g)（2026-08-18）:
        #   「殺意代価という連結した単語が**造語に当たる**。…
        #     **ひらがなに開く**（さついだいか）…そこから
        #     順序入れ替え、隣接キー、脱字、シフトキー抜けを
        #     処理順でチェックする。**通ってきた道**です」
        #
        # 通ってきた道の2つを組み合わせるだけ（項目48-EU・48-EV）:
        #
        #     さついだいか → （`つ` が入り込んだ）→ さいだいか
        #                  → （語＋接尾の合成）→ **最大化**
        #
        # `さいだいか` は**読みとしてはどこにも無い**（派生語なので
        # 当然）。だから上の `find_readings` の道では届かない。
        # **表記を組み立てられるときだけ**候補に出す。
        # **候補に出すだけ**で、自動補正には上げない（(g) どおり。
        # ユーザーが選べば choices が学習する＝(d) の短期参照）。
        try:
            from corrector import (_typo_repairs_intruded, _typo_repairs,
                                   compose_suffix_surface,
                                   typo_repairs_nearby_key,
                                   _charngram_gain)
            # まず**打ち間違いを直さずに**組めるか
            # （`さいだいかじ` → 最大＋化＋時。`最大家事` の的）。
            _s0 = compose_suffix_surface(reading, store, dict_index)
            # ここにも比べる門を掛ける（項目48-EY）。**打ち間違いを
            # 直さずに組めてしまう**ときのほうが危なくて、
            # `一時的 → 位置時的`（-1.55）はこの道から出ていた。
            if _s0:
                _g0 = _charngram_gain(surface, _s0)
                if _g0 is not None and _g0 < 0.0:
                    _s0 = None
            if _s0 and n_typo < max_typos:
                before = len(out)
                push(_s0, reading, 'homophone')
                if len(out) > before:
                    n_typo += 1
            # --- 設計15（項目48-FA・2026-08-18）---
            #
            # 第44回で測った「入口の三重の狭さ」の (b) を、
            # **候補一覧でだけ**広げる（Fable 5 の判断）。
            #
            # 入り込んだ1打を落とすだけでなく、**誤打の種類4種
            # （重複打鍵・脱字・順序違い・濁点）と隣接キーの
            # 打ち間違い**からも表記を組む:
            #
            #     再退化 → さいたいか →（濁点 た→だ）→ さいだいか
            #            → 最大＋化 → **最大化**
            #
            # **自動補正には入れない。** 第44回に実測したとおり、
            # 広げると `投機的 → 同期的`(+2.56)・`符号化 → 複合化`
            # (+2.08) のような**もっともらしい別語への化け**が
            # 起きて、48-EY の比べる門でも止まらない
            # （どれも日本語としてまともな語なので字の並びは
            #   良くなってしまう）。選ぶのがユーザーである
            # 候補一覧なら、広く見せてよい（48-EV と同じ判断）。
            #
            # **枠は別に持つ**（48-EV の学び「既存の答えを押しのけ
            # ない」）。組み立てた表記は**ふつうの打ち間違い候補とは
            # 別の種類**（読みとしてはどこにも無い派生語）なので、
            # `max_typos` を食い合わせず、**専用の枠 2つ**で出す。
            #
            # 食い合わせにすると、`再退化` では上の探索が枠8つを
            # 使い切ってしまい（妻帯・最大・再開・際会…）、
            # **肝心の `最大化` が出ませんでした**（実測）。
            _reps = list(_typo_repairs_intruded(reading))
            # **広げるのは「いま書かれている語が単位として無い」
            # ときだけ**（門(1)「単位として在るなら触らない」の
            # 候補一覧版・項目48-CF/CG と同じ考え）。
            #
            # これが無いと、正しく書けている語に派生形をぶら下げて
            # **候補が荒れました**（実測）:
            #
            #     単語 → 単語化・単語時   補正 → **徒歩性**・**補佐性**
            #
            # `再退化`・`誘い消化`・`殺意代価` はどこにも無いので通る。
            if not _attested_unit(surface, reading, store, dict_index):
                for _extra in (typo_repairs_nearby_key(reading),
                               _typo_repairs(reading)):
                    for _x in _extra:
                        if _x not in _reps:
                            _reps.append(_x)
            _n_built = 0
            for _rep in _reps:
                if _n_built >= _MAX_BUILT:
                    break
                if store.lookup(_rep):
                    continue        # 実績があるなら上の道が出している
                _s = compose_suffix_surface(_rep, store, dict_index)
                if not _s:
                    continue
                # **字の並びが悪くなる方向のものは出さない**
                # （項目48-EY の比べる門を、候補一覧でも使う。
                #   うにさん指示 (g)「不自然な文字列は候補に
                #   出さないように」）。
                #
                # 自動補正は余裕 +1.5 を要るが、**候補は選ぶのが
                # ユーザー**なので「悪くならないこと」だけを見る:
                #
                #     再退化 → 最大化 **+3.20**  誘い消化 → 最小化 **+2.91**
                #     開発者 → **会派者** -1.26  一時的 → **位置時的** -1.55
                #     説明書 → **説明化** -1.62  最大家事 → **最大時化** -2.06
                #
                # これが無いと、うにさんが「違和感」と呼んだ形の
                # 文字列を、こちらから候補に並べてしまいます（実測）。
                _gain = _charngram_gain(surface, _s)
                if _gain is not None and _gain < 0.0:
                    continue
                before = len(out)
                push(_s, _rep, 'typo')
                if len(out) > before:
                    _n_built += 1
        except Exception:
            pass

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
        #
        # **ただし、その読みが壊れているなら出さない**
        # （項目48-ET・うにさん指示 (g)・2026-08-18）:
        #
        #     「**不自然な文字列は候補に出さないように。**」
        #
        # `目もち長` の候補に `メモチチョウ`、`簡易流力` の候補に
        # `カンイリュウリョク` が出ていた（`probe_candidates.py` で
        # 数えた。候補65件のうち5件がこれ）。**どれも「漢字から
        # 推した壊れた読み」をそのままカタカナにしたもの**で、
        # 選びたい人はいない。
        #
        # 見分けは**新しい判断を作らず**、同梱の材料で説明が付くか
        # だけを見る（語彙・索引・世の中の集合）。
        # **説明が付かないときだけ落とす**（48-AR の轍を踏まない：
        # 分からないなら今までどおり出す、ではなく、ここは
        # 「材料のどれにも無い」と**言い切れる**ときだけ落とす）。
        if _reading_worth_offering(reading, store, dict_index):
            push(reading, reading, 'kana')
            push(_to_katakana(reading), reading, 'kana')

    # **同点崩し**（項目48-FD・設計19(ii)）。
    # **並べ替えるだけ。足しも引きもしない。**
    _prefer_known_units(out)

    if context_vec is not None and surrounding_words:
        _reorder_by_context(out, context_vec, surrounding_words)

    return out


def _prefer_known_units(candidates):
    """
    **同じ種類の中で、世の中に1語として在る表記を上へ**
    （項目48-FD・設計19(ii)）。

    `seed_japanese` の**直し先側**（固有名詞を除いた 105,495語）を
    使う。固有名詞を上げないのは、珍しい地名・人名が候補の頭に
    出ると選びにくくなるため（SCOWL の 35/70 と同じ考え）。

    **候補の追加も削除もしない。並び順だけ。** 種類（kind）の
    まとまりも崩さない（同音異義語 → 打ち間違い → かな の大枠は
    設計上の意図なので触らない）。

    **安定な並べ替え**なので、同じ側どうしの順は元のまま。
    このあとの `_reorder_by_context` も安定ソートなので、
    文脈の手がかりがあるときはそちらが勝ち、**同点のときだけ
    ここの結果が残る**（＝「同点崩し」）。

    **表が意見を持てない候補は、1つも動かさない**（`in_scope`）。
    表に入っているのは**漢字だけ 2〜8字**なので、`メモ帳`・
    `ひらがな`・`棚上げ` は「無い」のではなく**範囲の外**。
    最初これを混ぜて、`目もち長` の答えである **`メモ帳` を
    `無料` の下へ落とした**（2026-08-18 に実測して直した）。
    範囲の外のものは**元の位置に釘付け**にし、範囲の中のものだけを
    その空き位置の中で並べ替える。

    表が無ければ何もしない（`available()` が False）。
    """
    if len(candidates) < 2:
        return
    try:
        import seed_japanese as _sj
        if not _sj.available():
            return
    except Exception:
        return
    by_kind = {}
    order = []
    for c in candidates:
        k = c['kind']
        if k not in by_kind:
            by_kind[k] = []
            order.append(k)
        by_kind[k].append(c)
    for k in order:
        group = by_kind[k]
        slots = [i for i, c in enumerate(group)
                 if _sj.in_scope(c['surface'])]
        if len(slots) < 2:
            continue
        picked = [group[i] for i in slots]
        picked.sort(key=lambda c: 0 if _sj.is_common_unit(c['surface'])
                    else 1)
        for i, c in zip(slots, picked):
            group[i] = c
    candidates[:] = [c for k in order for c in by_kind[k]]


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

    # 1.5周目: **読みを、語の境目で切り直す**（項目48-JU・2026-08-26）。
    #
    # 同音異義語の探索は「その読み**全体で1語**」しか見つけられない。
    # だから `にかいせき` から `解析` には届いても、**助詞をまたいだ**
    # `に解析` には**構造上どうやっても届かない**（うにさんの的
    # 「切り替え時二階席が走っていて ⇒ 切り替え時に解析が走っていて」）。
    # 読みの DP（`kana_to_kanji_where_possible`）は同じ読みを
    # 「語彙の語で進める道」に沿って切り直すので、そこに届く。
    #
    # **自動では開かない。** 同じ DP をトークンの並びに当てると、
    # 実機メモ1,342行で**2,431か所**が別の形に書き換わる
    # （元の画像→もとの画像・別の表記→べつの表記。項目48-JU §2）。
    # ここは**候補＝申し出**なので答えは1行も変わらない——
    # 「判断がつかないものは触らない（色を付けて知らせるだけ）」
    # の一つ手前、**選べるようにするだけ**の場所。
    #
    # 名前を `recut` にしたのは、`resplit` が**もう別の意味で使われて
    # いる**ため（設計32・項目48-IW「違和感の範囲を左端から要素で
    # 割り直す」）。同じ言葉に2つの意味を持たせない。
    #
    # 門は3つだけ。**元と違う**こと、**DP が実際に何か変換した**こと
    # （`よはく` のように読みのまま返る＝切り直せていないものは
    #  下の「かな表記」と同じもので、ここに出す意味がない）、
    # そして**漢字かカタカナを含む**こと。
    # この3つで、正しく書けた語はほとんど自分自身に戻る（実測）。
    #
    # **この道にしか置けない。** 単語ひとつの右クリック
    # （`build_candidates`）には区分が1つしか無く、切り直す境目が
    # そもそも存在しない（学び22 の「全部の道に掛ける」は、
    # 掛けられる道が1本しかないときの形）。
    try:
        from halfwidth import kana_to_kanji_where_possible as _recut
    except Exception:
        _recut = None
    if _recut is not None:
        for combo in combos[:4]:
            if not combo or len(combo) < 2:
                continue
            try:
                cut = _recut(combo, store)
            except Exception:
                continue
            if (not cut or cut == combo or cut == surface_all
                    or cut in seen):
                continue
            if not any('一' <= c <= '鿿' or _is_katakana(c)
                       for c in cut):
                continue
            seen.add(cut)
            out.append({'surface': cut, 'reading': combo,
                        'kind': 'recut'})
            if len([c for c in out if c['kind'] == 'recut']) >= 2:
                break

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
        # 区切り直し（recut）は**打ち間違いの推測より上**。
        # 読みを1文字も変えずに境目だけ動かした形なので、
        # 編集距離で当てた候補より証拠が固い（項目48-JU）。
        kind_rank = {'homophone': 0, 'kanji': 1, 'recut': 2,
                     'typo': 3, 'kana': 4}.get(c['kind'], 9)
        keeps_tail = 0 if (o_tail and c['surface'].endswith(o_tail)) else 1
        # スコアは高いほど上に出したいので符号を反転する
        ctx = -ctx_scores.get(c['surface'], 0.0)
        return (kind_rank, keeps_tail, ctx)

    out.sort(key=_rank)
    return out


# **候補の見出しは、ここが最初の行**（項目48-JU・2026-08-26）。
#
# 並び順と見出しの文字はここだけに書く。`app.py` の3つのメニュー
# （補正欄・メモ欄・簡易入力）は**この表を回す**。前は3か所に
# 同じ組を書き写していて、種類を1つ足したら**3か所とも直さないと
# 黙って落ちる**形だった（学び22「片方だけに置くと迂回される」）。
#
# 順は**証拠の固い順**。同音（読みが同じ1語）→ 区切り直し（読みは
# そのままで境目だけ動かした）→ 打ち間違い（編集距離の推測）→ かな。
MENU_KINDS = (
    ('samekey', '同じキーの文字'),
    ('symbol', '記号の言い換え'),
    ('homophone', '同音の語'),
    ('kanji', '漢字にする'),
    ('recut', '区切り直し'),
    ('typo', '打ち間違いの可能性'),
    ('kana', 'かな表記'),
)

KIND_LABELS = dict(MENU_KINDS)


# ============================================================
# 記号の言い換え（F2 から選ぶ）
# ============================================================
# 「〜」は範囲を表す記号だが、文章では「から」と書きたいことが多い。
# 打ち直すより選べたほうが速い、といううにさんの指定（2026-08-10）。
#
# 記号は読みを持たないので、読みを起点にした候補づくり
# （build_candidates）には一切かからない。ここで表として持つ。
# 増やすときはこの表に足すだけでよい。
SYMBOL_WORDS = {
    '〜': ['から'],
    '～': ['から'],
    '~': ['から'],
}


# 同一キーの文字も候補に出す記号（うにさんの指定・2026-08-11・C-4）。
#
# 「（は、ゆを候補に出したり、！は、ぬや１を候補に出したり、
#   同一キーにある文字を候補に出す」。
# 実際の並びは kana_layout.same_key_characters が作る。
#
# **F2 で止まる記号は、ここに入れたものだけ。**
# 表に載っている記号を全部 F2 の通り道にすると、`、` と `。` で
# 毎回止まることになる。うにさんは前に「句点で終えると遡れません」
# と言っていて、句読点で足を取られるのを嫌っている（項目41）。
# なので**句読点は通り道から外し**、ドラッグや右クリックで
# 直に選んだときだけ候補を出す（下の symbol_candidates は
# この集合を見ない）。
#
# 増やすときはここに足す。減らしたくなったら消すだけでよい。
F2_SYMBOL_STOPS = frozenset(
    '！？（）｛｝「」［］＜＞＝＋＊＃＄％＆＠｜＿'
    '!?(){}[]<>=+*#$%&@|_'
    '〜～~'
)


def symbol_candidates(text):
    """
    記号に対する候補。2種類ある。

    1. 言い換え（〜 → から）。SYMBOL_WORDS の表。
    2. **同一キーにある文字**（（ → ゆ / ！ → ぬ・１）。
       かな入力とローマ字入力、Shift の有無を取り違えると、
       同じキーの上で文字が入れ替わる。打ち直すより選べたほうが
       速い、といううにさんの指定（2026-08-11・C-4）。

    text: 選ばれている文字列（記号1文字を想定）
    戻り値: build_candidates と同じ形の候補の並び
    """
    if not text or len(text) != 1:
        return []
    out = []
    for w in SYMBOL_WORDS.get(text) or ():
        out.append({'surface': w, 'reading': None, 'kind': 'symbol'})
    if _takes_same_key(text):
        for w in same_key_characters(text):
            out.append({'surface': w, 'reading': None, 'kind': 'samekey'})
    return out


# 同一キーの候補を出さない文字。
# `゛゜` は「単体で書くことはないのでスルーします」（うにさん・
# 2026-08-11）。
_NO_SAME_KEY = frozenset('゛゜')


def _takes_same_key(ch):
    """
    同一キーの候補を出してよい文字か。**記号だけ**。

    かな・英字・数字にまで出すと、ふつうの語の候補一覧の先頭に
    「ゆ の候補は ゅ・8・( です」のような役に立たない並びが
    割り込む。`isalnum()` はかな・漢字・全角数字も True になるので、
    これ1つで「記号かどうか」を切り分けられる
    （`ー` は Lm 扱いで True。長音は語の一部なので、これで正しい）。
    """
    return bool(ch) and not ch.isalnum() and ch not in _NO_SAME_KEY


def is_symbol_word(text):
    """
    F2 が止まってよい記号か。

    **候補が出せるかどうかとは別**。句読点は候補を出せるが、
    F2 の通り道からは外してある（F2_SYMBOL_STOPS の説明を参照）。
    """
    if not text:
        return False
    return text in SYMBOL_WORDS or text in F2_SYMBOL_STOPS
