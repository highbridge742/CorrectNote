# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
**AI が焼いた、同音異義語の対の表**（設計35・項目48-JJ・2026-08-25）。

うにさんの指定「**見本がなくても補正できないといけません**」（2026-08-25）と
「AI の判断を、表を作るときに使ってよい」（2026-08-24）から。
的リストの1行目の定義がこの表の形そのもの——
「同音異義語：**対の単語に合わせる形**で同じ意味を持つもの」。

共起の学習（context_vec）は、うにさんのメモが誤変換の議論だらけなので
**誤変換の側の共起まで育ってしまう**（48-IQ・思い↔動作）。この表は
**世の中の日本語での結びつき**を AI が直接書いたもので、本人の回数や
履歴を一切見ない（回数を使ってよいのは同音異義語の**二番手**まで・
うにさんの指定 (1)）。

形: (書かれている側の芯, 直す側の芯) → 手がかり。**方向つき**で、
  ・to_cues   直す側の手がかり語。**これが周りに在るときだけ**動く
  ・keep_cues 書かれている側の手がかり語。**1つでも在れば動かない**
  ・tails     許す送り仮名（None=全部同じ活用の型。思い→重い は
              動詞と形容詞なので「い」だけ、のように絞る）

**載せ過ぎだけが危ない**（48-ID）——対も手がかりも、AI が「世の中の
日本語でこの結びつきは揺るがない」と言えるものだけ。曖昧な手がかり
（画面 は 映る/移る の両方に付く）は**どちらの側にも載せない**。

**版つき**（48-IQ・general_words と同じ扱い）。足すときは版を上げ、
出どころを書く。
    版1  2026-08-25  うにさんの的リスト（見本なし）から11対
"""

VERSION = 7
# 版7（2026-09-14・GPT-6 Astra）: 既存の漢字1字の動詞手がかりを、実辞書の送り仮名付き活用でも照合。
# 版6（2026-09-14・GPT-6 Astra）: 既存の語尾制約が認める原文は他の同音経路でも保持。
# 版5（2026-09-14・GPT-6 Astra）: 共通の元の主語・目的語の意味が成立すれば保持。対は増やさない。
# 版4（2026-09-14・GPT-6 Astra）: 既存対を実際の活用・格・節の範囲で判断。
# 視覚→四角は直後の「で＋囲む/囲う」に限定。別節/連体修飾の手がかりは混ぜない。
# 版3（2026-08-30・Fable）: うにさんの一覧「視覚で囲って ⇒ 四角で囲って」
# から 視覚→四角 を足した（手がかり: 囲・枠・矩形…。視覚的 は後ろの門）。
# 版2（2026-08-25・同日）: うにさんの×つきの的から**逆向きの対**を足した
# （書→描・話→離・重→思）。「書かれている側の手がかりが在る」ときは
# **KEEP（この表記で正しいと確認）**を返し、他の同音の道も止める
# （`傷が治りました` が方針2の毒された共起で `直り` に化けるのを塞ぐ）。

# **この表記で正しいと確認した**（呼び出し側は他の同音の道も止めること）
KEEP = 'KEEP'

# (書かれている芯, 直す芯, 許す送り仮名, 直す側の手がかり,
#  書かれている側の手がかり, **後ろに来てはいけない形**,
#  **後ろに来てよい形**（None=制約なし。'' は行末））。
# 後ろの門は構造の門——`思い` は動詞なので「ます」が続けるが、
# 直す先の `重い` は形容詞で「ます」に接続できない（`と思います` を
# `と重います` にした実測の化けを塞ぐ）。逆向きの `重い → 思い` は
# **後ろに名詞が続かないとき**（行末・助詞）だけ（`私の重い鞄` は正しい）。
PAIRS = (
    ('治', '直', None,
     ('半角', '誤字', '補正', '誤変換', '不具合', 'バグ', '文字', '表示',
      '動作', 'アプリ'),
     ('風邪', '病気', '怪我', '傷', '体調', '病'),
     (), None),
    ('思', '重', ('い',),
     ('動作', '処理', '起動', '速度', '読み込み', 'アプリ', 'タブ', '解析',
      '荷物'),
     ('気持ち', '心', '昔', '考え', '相手'),
     ('ます', 'まし', 'のほか', 'やり', 'つき', '込'), None),
    ('重', '思', ('い',),
     ('私', '僕', 'あなた', '彼', '彼女'),
     ('動作', '処理', '起動', '速度', '読み込み', 'アプリ', 'タブ', '解析',
      '荷物', '体', '責任', '負担', '鞄', '箱', '腰', '税'),
     (),
     # 後ろに名詞が続くなら正しい形容詞（私の重い鞄）。行末・記号・
     # 助詞のときだけ「私の思い」の型
     ('', '。', '、', '　', ' ', 'は', 'が', 'を', 'に', 'も', 'で', 'です',
      'だ', 'と'),
     # 直前が「の」のときだけ（私**の**重い）。「私が重い」（体重の話）は
     # 正しい形容詞なので触らない
     ('の',)),
    ('売', '打', ('っ', 'ち', 'つ'),
     ('文字', 'キー', 'かな', 'ローマ字', '入力', 'タイプ', 'キーボード'),
     ('店', '商品', '品物', '金', '円', '価格'),
     (), None),
    ('描', '書', None,
     ('文章', 'メモ', '文字', '説明', '日記'),
     ('絵', 'イラスト', '図', '線', 'キャラ', '顔', '漫画'),
     (), None),
    ('書', '描', None,
     ('絵', '顔', 'イラスト', '図', '漫画', '風景', 'キャラ', '線'),
     ('文章', 'メモ', '文字', '説明', '日記', '記事', '名前', '住所',
      'コード', '字'),
     (), None,
     # 直前が「を」のときだけ（絵**を**書く）。「絵について書く」は正しい
     ('を',)),
    ('映', '移', None,
     ('チャット', 'タブ', '次', '別', '先', '話題'),
     ('鏡', 'テレビ', 'カメラ', '写真', '光', '目'),
     (), None),
    ('組', '汲', None,
     ('意図', '気持ち', '事情', '意向'),
     ('チーム', 'プログラム', '番組', '腕', '足'),
     (), None),
    ('離', '話', ('す', 'し', 'せ', 'さ', 'そ'),
     ('続き', '話題', '内容', '相手'),
     ('手', '指', '距離', '目', '体'),
     (), None),
    ('放', '話', ('す', 'し', 'せ', 'さ', 'そ'),
     ('続き', '話題', '内容', '相手'),
     ('手', '鳥', '魚', '犬', '猫'),
     (), None),
    ('話', '離', ('す', 'し', 'せ', 'さ', 'そ'),
     ('手', '指'),
     ('続き', '話題', '内容', '相手', '声', '電話', '日本語', '英語'),
     (), None,
     # 直前が「を」のときだけ（手**を**話す）。「ハンドルについて
     # 話しました」を 離し に変えた（fpcheck の誤検知1件・実測）——
     # 手がかり語だけでは助詞が見えない
     ('を',)),
    ('官僚', '完了', ('',),
     ('実行', '処理', '操作', '保存', '補正', '変換', '解析'),
     ('政治', '省庁', '国家', '政府'),
     (), None),
    ('開業', '改行', ('',),
     ('行', '削除', '挿入', '空白', '文末', '段落'),
     ('医院', '店', '営業', '駅'),
     (), None),
    ('糸', '意図', ('',),
     ('察し', '汲', '伝わ', '理解', '読み取'),
     ('針', '縫', '布', '裁縫', '毛'),
     (), None),
    ('爪', '詰め', ('',),
     ('上', '下', '左', '右', '横', '端', '奥', '隅'),
     ('切', '伸', '猫', '犬', '指', '手', '足', '磨', '割', 'ネイル'),
     (),
     # 読点・行末のときだけ（`上に詰め、`＝連用中止の形。
     # `上に爪を立てる` は後ろが を なので触らない）
     ('', '、', '。', '　', ' '),
     # 直前が「に」のときだけ（上**に**爪、）
     ('に',)),
    # 版3: 視覚 → 四角（うにさんの一覧「視覚で囲って ⇒ 四角で囲って」）。
    # 囲う・枠 が近くに在るのは図形の話で、そこに立つ しかく は
    # 世の中の日本語では 四角。**視覚的** は後ろの門（的）で守る。
    ('視覚', '四角', ('',),
     ('囲っ', '囲む', '囲い', '囲ん', '囲う', '囲え', '枠',
      '矩形', '図形', '正方形', '長方形'),
     ('聴覚', '触覚', '感覚', '認知', '効果', '情報'),
     ('的',), ('で',), None, ('囲む','囲う')),
)


# 対の表に「書かれている側」として載っている**1字の芯**（糸 など）。
# 1字の語はふだん評価の土俵に上がらない（find_editable_spans の
# len<2 の門——1字は読みが短く、読みの探索では何にでも一致して
# 誤爆するため）。だが**この表の証拠は読みの探索ではなく手がかり語**
# なので、表に載っている字だけは土俵に上げてよい（項目48-JK）。
SINGLE_LEFT = frozenset(p[0] for p in PAIRS if len(p[0]) == 1)


def _split(surface):
    """先頭の漢字の連なり（芯）と、続く送り仮名に割る。"""
    i = 0
    while i < len(surface) and '一' <= surface[i] <= '鿿':
        i += 1
    return surface[:i], surface[i:]


def _hits(cues, material):
    """手がかり語が周りの語に在るか（語そのもの・2字以上は頭一致も）。"""
    for w in material:
        for c in cues:
            if w == c or (len(c) >= 2 and w.startswith(c)):
                return True
        # 48-ACU / GPT-6 Astra / 2026-09-14: exact native inflections
        # share the existing lemma cue. Never derive a cue from a substring
        # or a kana homophone; the written verb must exist in the dictionary.
        if any('一'<=char<='鿿' for char in w):
            from morphology import dictionary_inflections
            for pos,form,base,reading in dictionary_inflections(w) or ():
                if not pos.startswith('動詞,'):
                    continue
                if base in cues:
                    return True
                # An existing one-kanji cue denotes the written verb stem.
                # Require a complete native form, not a prefix of a noun
                # (切手) or a compound with a different predicate.
                stem,tail=_split(base)
                if (len(stem)==1 and stem in cues and tail
                        and all('ぁ'<=c<='ゖ' for c in tail)):
                    return True
    return False


def local_material(surface, material, before='', after='', source=''):
    """Use the actual clause when the caller supplies an exact source boundary.

    2026-09-14 / GPT-6 Astra: a distant text-writing cue cannot change a
    drawing predicate in another clause. A comma after an object alone
    does not end its dependency; require a native predicate/connective.
    """
    if source != before+surface+after:
        return tuple(material)
    from morphology import tokenize
    parts=tokenize(source);start=len(before);end=start+len(surface)
    boundaries=[0,len(source)]
    for i,t in enumerate(parts):
        if t.surface in ('。','！','？','!','?',';','；','\n','\r\n'):
            boundaries.append(t.end)
        elif (i and t.pos=='助詞' and t.pos_sub.startswith('接続助詞')
              and t.has_reading and parts[i-1].has_reading
              and parts[i-1].pos in ('動詞','形容詞','助動詞')):
            # A written comma is optional between connected predicates.
            boundaries.append(t.end)
        elif t.surface in ('、',',','，') and i:
            prev=parts[i-1]
            connective=prev.pos=='助詞' and prev.pos_sub.startswith('接続助詞')
            finite=prev.pos in ('動詞','形容詞','助動詞') and prev.infl_form in ('基本形','連用形')
            after_te=prev.surface=='から' and i>1 and parts[i-2].surface in ('て','で')
            if prev.has_reading and (connective or finite or after_te):boundaries.append(t.end)
    lo=max(b for b in boundaries if b<=start)
    hi=min(b for b in boundaries if b>=end)
    local=[t for t in parts if lo<=t.start and t.end<=hi]
    if any(t.pos=='動詞' and t.start<end and start<t.end for t in local):
        # The head of an explicit object belongs to this verb. A verb
        # inside its relative modifier has a different object (文字を読む猫).
        from semantic_roles import object_before
        legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                 t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in local]
        obj=object_before(source,start,lambda _:legacy)
        if obj:
            index=next(i for i in range(len(local)-1,-1,-1)
                       if source[local[i].start:local[i].start+len(obj)]==obj
                       and local[i].start+len(obj)<=start)
            while index and local[index-1].end==local[index].start:
                prev=local[index-1]
                if not (prev.has_reading and (prev.pos in ('名詞','連体詞')
                        or prev.pos=='助詞' and prev.pos_sub=='連体化')):break
                index-=1
            local=local[index:]
    return tuple(t.surface for t in local if (t.end<=start or t.start>=end)
                 and t.has_reading and t.pos in ('名詞','動詞','形容詞'))


def find_fix(surface, material, after='', prev='', source=''):
    """
    見本（並記）が無くても、**対の単語**だけで直せるか。

    戻り値:
      直し先の文字列   直す側の手がかりが周りに在り、書かれている側の
                       手がかりが1つも無い
      KEEP             書かれている側の手がかりが在る＝**この表記で
                       正しいと確認**（呼び出し側は他の同音の道も止める。
                       `傷が治りました` を方針2の毒された共起から守る）
      None             意見なし
    after: この語のすぐ後ろに続く文字。prev: すぐ前の1文字。
    どちらも**構造の門**（手がかり語には助詞が見えない——
    `ハンドルについて話しました` を 離し に変えた実測から）。
    """
    if not surface:
        return None
    material=tuple(material or ())
    stem, tail = _split(surface)
    if not stem or len(tail) > 3:
        return None
    for p in PAIRS:
        x, y, tails, to_cues, keep_cues, deny_after = p[:6]
        only_after = p[6] if len(p) > 6 else None
        prev_ok = p[7] if len(p) > 7 else None
        following_action = p[8] if len(p) > 8 else None
        if stem != x:
            continue
        if tails is not None and tail not in tails:
            continue
        from semantic_roles import original_argument_evidence
        if original_argument_evidence(surface,prev,after,source):
            return KEEP
        # 48-ACU: a shape/enclosure cue must belong to this instrumental
        # phrase. A distant frame cannot change a visual-perception phrase;
        # a noun compound such as visual experiment has no such case/verb.
        if following_action is not None:
            from morphology import tokenize
            parts=[t for t in tokenize(surface+after) if t.start>=len(surface)]
            if (len(parts)<2 or parts[0].surface!='で' or parts[0].pos!='助詞'
                    or parts[0].pos_sub!='格助詞:一般' or parts[0].start!=len(surface)
                    or parts[1].start!=parts[0].end or parts[1].pos!='動詞'
                    or not parts[1].has_reading or parts[1].base_form not in following_action):
                continue
            # The exact following action is native evidence even before the
            # initial dictionary import populates the surrounding-word index.
            material=material+(parts[1].surface,parts[1].base_form)
        if _hits(keep_cues, material):
            return KEEP
        if after and any(after.startswith(d) for d in deny_after):
            # This existing native construction excludes the proposed sense.
            # Preserve that result across other homophone paths as well.
            return KEEP
        if only_after is not None:
            ok = (not after and '' in only_after) \
                or any(o and after.startswith(o) for o in only_after)
            if not ok:
                continue
        if prev_ok is not None:
            # A comma after an explicit case leaves that dependency intact.
            boundary=prev.rstrip('、,， \t')
            if not boundary or boundary[-1] not in prev_ok:
                continue
        if _hits(to_cues, material):
            return y + tail
    return None
