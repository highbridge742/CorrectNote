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
カタカナ語と英単語の誤字補正（2026-08-10・うにさんの指定）。

これまで **カタカナ語は原則として補正対象外** だった。固有名詞・
俗語・専門語が多く、辞書に無い語を「知らない＝誤字」と扱うと
正しく書いたものを壊すため。英単語に至っては経路そのものが無かった。

うにさんの指定で方針が変わった:

    プセネタリウム（隣接キー）／プネラタリウム（順序）／
    プネタリウム（脱字）／ププラネタリウム（重複）／
    プラニネタリウム（余分な文字）／ぷらねたりうむ（ひらがな）
    …をすべて「プラネタリウム」に直す。これらは一例なので、
    **共通的に判定する**こと。

共通の性質は「長い外来語は、字面がとても特徴的」であること。
7〜8文字の並びのうち1文字違うだけの別語は、まず存在しない。
そこで、かな連続の補正で使っている**キー配置の距離**という
細かい模型はここでは使わず、**素直な編集距離**（挿入・削除・
置換・隣り合う2文字の入れ替え＝ダメラウ）で測る。

    - キー配置の距離は「押し間違えとは考えにくい」組み合わせを
      弾くための仕組み。短いかな語では必要だが、長い外来語では
      かえって取りこぼす（せ→ら は配列上ずっと遠い）。
    - 代わりに**長さで守る**。5文字未満は見ない。直すのは
      **1文字ぶんの違いまで**（allowed_edits の説明を参照）。
    - **迷ったら直さない**。同じ距離の候補が2つ以上あれば手を引く。
    - **形態素解析がすべて既知の語として読めた並びは触らない**
      （ショートカットキー＝ショートカット＋キー のような複合語を
      勝手に縮めないため。corrector.py 側の関門）。

「プラネ１リウム」「プラネタリウ［」のような、かなですらない
文字が紛れた形も、素直な編集距離なら**置換1回**として自然に
拾える（キーの位置に読み替える必要が無い）。

英単語も考え方は同じ。覚えるのは `learn_english_words` で、
ユーザーが正しく書いた語をそのまま拾う。

**2026-08-11 に方針が変わった**（うにさんの指定・項目48-AW）:

    変えた前  外部の辞書もモデルも持ち込まない
    変えた後  **単語リストは持ち込む。学習済みモデルと通信は
              持ち込まない**

初期状態で測ったら、**カタカナ語と英単語の補正が一度も効かない**
ことが分かった（直し先を「メモのどこかに正しく書いてある語」だけに
していたため）。`プセネタリウム` も `Plaqnetarium` も直らない。
単語リストは中身が読めて検証できるので、「安全性がコードで
確かめられる」という軸とは矛盾しない。**通信と学習済みモデルは
引き続き持ち込まない**（動かせない軸）。

    seed_katakana.py  IPAdic 由来 9,094語。**役目ごとに分けて使う**:
                      全語        正しく書けている語（48-BE）
                      4文字以上   直し先になれる語 7,521（48-BF）
                      かな一意    ひらがなから寄せてよい語 7,403
                                  （48-BH。かたつむり・さくら・
                                    ぼたん のような語を除いたもの）
                      ふつうに使う 5文字以下をひらがなから寄せて
                                  よい語 2,381（48-BI）
    seed_english.py   SCOWL 由来。6文字以上・米英の両方
                      **直し先** 57,568語（size 35・ふつうに使う語）
                      **触らない** 107,218語（size 60。広いほうが
                                  正しく書けている語を守る・48-BK）

種を足すと土台が2つ増える（**どちらも片方だけでは足りない**）:

  1. **辞書に載っている語は正しく書けている。触らない**
     （項目48-BA / 48-BE）。辞書が「その人が書いた語」だけだった
     頃は `own >= 2` が兼ねていた門で、種を足した瞬間に前提が
     崩れる（committee→committed と壊れた）。
     **守る側の一覧は、直し先の門を通す前の全語**を使うこと。
  2. **種の語へ直すなら、その1手が打ち間違いとして説明が付くこと**
     （項目48-BD）。うにさんの分け方（重複・隣接キー・脱字・
     順序・余分）に当てはまらない1手は、**距離が1でも
     打ち間違いではない**:

         アンコモン → アンチモン  （こ と ち はキーが遠い）
         リダイレクト → ダイレクト（リ は ダ の隣ではない）
"""

import re

# ------------------------------------------------------------
# 文字種の判定
# ------------------------------------------------------------

# 「ー」（長音）と小書きのカタカナも1文字として数える
_KATAKANA_RE = re.compile('[ァ-ヶー]')

# カタカナの並びに紛れうる「かなではない文字」。
# かな入力で隣のキーを押してしまうと、数字や括弧が入る
# （プラネ１リウム・プラネタリウ［）。全角・半角の両方を見る。
_STRAY_RE = re.compile('[!-~！-～]')


def is_katakana_char(ch):
    return bool(_KATAKANA_RE.match(ch))


def katakana_to_hiragana(text):
    out = []
    for ch in text:
        if 'ァ' <= ch <= 'ヶ':
            out.append(chr(ord(ch) - 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def hiragana_to_katakana(text):
    out = []
    for ch in text:
        if 'ぁ' <= ch <= 'ゖ':
            out.append(chr(ord(ch) + 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def is_all_katakana(text):
    """すべてカタカナ（長音・中黒を含む）か。"""
    if not text:
        return False
    return all(is_katakana_char(c) or c == '・' for c in text)


# ------------------------------------------------------------
# 編集距離（ダメラウ・レーベンシュタイン）
# ------------------------------------------------------------

def edit_distance(a, b, limit=None):
    """
    a を b にするのに必要な操作の回数。

    挿入・削除・置換に加えて、**隣り合う2文字の入れ替え**も
    1回として数える（プネラタリウム＝ら と ね の入れ替え）。

    limit を渡すと、その回数を超えた時点で打ち切って limit + 1 を
    返す（4516 語との総当たりを速くするため）。
    """
    n, m = len(a), len(b)
    if limit is not None and abs(n - m) > limit:
        return limit + 1
    if not n:
        return m
    if not m:
        return n
    prev2 = None
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            v = min(prev[j] + 1,          # 削除
                    cur[j - 1] + 1,       # 挿入
                    prev[j - 1] + cost)   # 置換
            if (i > 1 and j > 1 and prev2 is not None
                    and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                v = min(v, prev2[j - 2] + 1)   # 入れ替え
            cur[j] = v
        if limit is not None and min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[m]


def single_edit(a, b):
    """
    距離1の2つの並びが、**どの種類の打ち間違いか**を返す。

    戻り値: (種類, 元の文字, 直し先の文字, a の中の位置)
        '置換'  a の1文字が b の1文字に化けた
        '余分'  a に1文字余分に入った
        '脱字'  a から1文字落ちた
        '入替'  隣り合う2文字の順番が入れ替わった
        ''      距離が1ではない（同じ・2手以上）
    """
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return ('', '', '', -1)
    i = 0
    while i < la and i < lb and a[i] == b[i]:
        i += 1
    j = 0
    while j < la - i and j < lb - i and a[la - 1 - j] == b[lb - 1 - j]:
        j += 1
    ra, rb = la - i - j, lb - i - j
    if ra == 1 and rb == 1:
        return ('置換', a[i], b[i], i)
    if ra == 1 and rb == 0:
        return ('余分', a[i], '', i)
    if ra == 0 and rb == 1:
        return ('脱字', '', b[i], i)
    if ra == 2 and rb == 2 and a[i] == b[i + 1] and a[i + 1] == b[i]:
        return ('入替', a[i:i + 2], b[i:i + 2], i)
    return ('', '', '', -1)


def within_one_edit(a, b):
    """
    **距離が1以内か「だけ」を、表を作らずに見る**（項目48-BC）。

    `edit_distance` は行列を作るので、1語あたり数千件の相手と
    比べると効いてくる。距離1かどうかは、
    **前から同じところ・後ろから同じところを飛ばして、
    残りが両側とも1文字以下か**で決まる（入れ替えだけ2文字残る）。
    数え上げが要らないぶん桁で速い。

    `allowed_edits()` は常に1を返すので、これで取りこぼしは無い。
    **本当の距離が要る場所では今までどおり `edit_distance` を使う**
    （ここは総当たりを間引く前段の関門）。
    """
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    i = 0
    while i < la and i < lb and a[i] == b[i]:
        i += 1
    if i == la and i == lb:
        return True
    j = 0
    while j < la - i and j < lb - i and a[la - 1 - j] == b[lb - 1 - j]:
        j += 1
    ra, rb = la - i - j, lb - i - j
    if ra <= 1 and rb <= 1:
        return True                     # 置換・挿入・削除
    return (ra == 2 and rb == 2
            and a[i] == b[i + 1] and a[i + 1] == b[i])   # 入れ替え


# 英字の並びの前後にくっついていたら、識別子・版番号・URL・パスと
# みなして「英単語」として扱わない記号。
#
# `:` を足したのは 2026-08-10。実機のメモに `P:lanetarium`
# （`:` を打ち間違えて混ぜた試験用の行）があり、そこから
# `lanetarium` を英単語として**覚えてしまっていた**。
# うにさんの配列表のとおり `:` はかなの「け」のキーでもあるので、
# 英字にくっついた `:` は打ち間違いか識別子（C:\ や key:value）で
# あって、語の区切りではない。
_GLUED_SYMBOLS = '._-@/:'


# 英語の語形変化の語尾。単数複数・時制の違いを「打ち間違い」と
# 取り違えないためだけに持つ、ごく短い表。
# **これは英単語の辞書ではない**（外部の辞書は持ち込まない方針）。
# 語尾を落とした形が一致するかを見るだけで、意味は一切見ない。
_INFLECTIONS = ('s', 'es', 'd', 'ed', 'ing', 'n', 'en', 'r', 'er')


def _stems(word):
    """語尾を落とした形の候補（元の形そのものを含む）。"""
    out = {word}
    for suf in _INFLECTIONS:
        if len(word) > len(suf) + 2 and word.endswith(suf):
            out.add(word[:-len(suf)])
    # ies → y（studies / study）
    if len(word) > 4 and word.endswith('ies'):
        out.add(word[:-3] + 'y')
    return out


def _same_word_family(a, b):
    """
    2つの英単語は、語尾が違うだけの**同じ語**か。

    `change` と `changed`、`window` と `windows`、
    `receives` と `received` のような組。打ち間違いではないので、
    片方をもう片方に直してはいけない（検証レポート 2-A / 2-F）。

    英単語の辞書を持たない以上、どちらの形が正しいかを判断する
    材料は無い。**判断が付かないものは直さない**（設計原則3）。
    """
    if a == b:
        return True
    return bool(_stems(a) & _stems(b))


def allowed_edits(length):
    """
    何回まで直してよいか。**常に1回**。

    最初は「8文字以上なら2回」にしていたが、実機のメモで総点検
    （sweep）したところ、2回を許すと正しく書けている語が次々に
    壊れた（2026-08-10）:

        タッチスクリーン → バックスクリーン
        チェックボックス → ブラックボックス
        アンインストール → インストール
        タブショートカット → ショートカット

    外来語は「同じ長さで2文字だけ違う別語」がいくらでもある。
    1回に絞れば、うにさんが挙げた例（隣接キー・順序の入れ替え・
    脱字・重複・余分な1文字）はすべて1回で説明が付くので、
    取りこぼしも起きない。
    """
    return 1


MIN_LENGTH = 5


# ------------------------------------------------------------
# 最初から持っている単語リスト（種）
# ------------------------------------------------------------
#
# **入れ物を分ける**（2026-08-12・項目48-BA）。
#
# 第34回では種の語を `_katakana_vocabulary` / `_english_vocabulary` に
# 混ぜたら tests_mock が3件落ちた。落ちた中身がそのまま理由になる:
#
#     使っていない語の並びは複合語とみなさない → True になった
#     多いほうの形だけを覚える → 英語の語彙に種の56,000語が全部出た
#
# **「直し先になれる語」と「その人が実際に使っている語」は別物**。
# 前者は種を含めてよいが、後者は覚えた語だけでなければならない。
# 混ぜると、「使っている語か？」を尋ねている関門が全部素通りになる。
#
#   _katakana_vocabulary / _english_vocabulary … 覚えた語だけ
#   _katakana_seed       / _english_seed       … 種だけ
#   _katakana_targets    / _english_targets    … 直し先（種＋覚えた語）
#
# 直し先では**覚えた語が種を上書きする**（本人の書き方が優先）。

# 種のカタカナ語を直し先にしてよい最短の長さ（項目48-BB / 48-BF）。
#
# **4文字**。`fix_katakana_word` は5文字以上の並びしか見ないので、
# 4文字の語には「1文字余分に打った」でしか届かない＝ここが底。
# 3文字以下を入れても、届く道が無いので意味が無い。
#
# 第35回の前半は**6文字**にしていた。種9,081語を調べた実測で、
# 「1文字違いの別語が存在しにくい」という、この経路が寄りかかって
# いる性質（`allowed_edits` の理屈）が成り立つのが6文字から
# だったため:
#
#     長さ 3  距離1の隣人がいる語 97.7% ／ 4  77.2% ／ 5  43.2%
#     長さ 6  22.8% ／ 7  12.1% ← ここで寝る ／ 8以上 約10%
#
# **うにさんの指摘で作り直した**:「**カタカナ6文字以上は少ない
# です**」。実際、ふつうに使う40語（ドラッグ・カーソル・ファイル・
# クリック…）のうち6文字以上は**1語だけ**だった。
# **長さで守るのをやめ、「打ち間違いとして説明が付くか」で守る**
# ことにした（`typo_explains_seed_word`）。そちらは長さに
# 関係なく効くので、短い語も同じ強さで守れる。
SEED_KATAKANA_MIN_LENGTH = 4

_seed_katakana_cache = None
_seed_katakana_all_cache = None
_seed_katakana_kana_only_cache = None
_seed_katakana_common_cache = None
_seed_english_cache = None
_seed_english_all_cache = None


def typo_explains_seed_word(typed, reading):
    """
    **種の語へ直すとき、その1手が「打ち間違い」として説明が付くか**
    （項目48-BD・うにさんの指摘「カタカナ6文字以上は少ないです」から）。

    長さだけで守ろうとすると、**ふつうの外来語がほとんど直せない**
    （種9,081語のうち6文字以上は3,303語しかない）。そこで
    **打ち間違いの種類で切る**。うにさんが挙げた5種類のうち、

        余分な1文字・脱字・重複・順序の入れ替え
            → **形そのものが証拠**。ふつうに書いた語がたまたま
              この形になることは考えにくい。そのまま通す。
        隣接キーの押し間違い（＝1文字の置換）
            → **これだけが当てずっぽうになりうる**。
              `アンコモン` と `アンチモン` は こ→ち の置換で
              距離1だが、**こ と ち はキーが遠い**（99.0）。
              押し間違いとしては説明が付かない。

    実測（うにさんのプラネタリウム16例）:

        余分 12例 / 脱字 1例 / 入替 1例 / 置換 1例
        置換の1例（プセネタリウム）は **せ→ら でキー距離 1.0**

    つまり**この関門はうにさんの例を1つも落とさず、
    `アンコモン → アンチモン` だけを止める**。
    かなですらない1文字（プラネ１リウム の `１`）は、
    紛れ込んだ印そのものなので通す。

    **余分な1文字**も同じ考えで見る。うにさんの分け方では、
    余分な1文字は「**重複打鍵**」か「**隣接キーが入り込んだ**」の
    どちらかなので、

        余分な文字が、隣の文字と同じ      → 重複打鍵
        余分な文字が、隣の文字とキーが近い → 隣接キーが入り込んだ
        余分な文字が、かなですらない       → 紛れ込んだ印

    のどれかであることを求める。うにさんの12例はすべて通る。
    止まるのは、**ふつうの日本語の作り方**でできている語:

        リダイレクト → ダイレクト   （リ は ダ の隣ではない）
        イレギュラー → レギュラー   （イ は レ の隣ではない）

    どちらも辞書に無い（IPAdic に入っていない）ので、
    「辞書にある語は触らない」では守れなかったもの。

    **覚えた語（その人が実際に書いた語）には掛けない。**
    掛けるのは種の語＝「本人が書いたわけではない直し先」だけ。
    """
    from kana_layout import kana_key_distance, FAR

    def is_kana(ch):
        return bool(ch) and ('ぁ' <= ch <= 'ゖ' or ch == 'ー')

    kind, ca, cb, at = single_edit(typed, reading)
    if kind == '置換':
        if not is_kana(ca):
            return True                 # かなですらない1文字が紛れた
        return kana_key_distance(ca, cb) < FAR
    if kind == '余分':
        if not is_kana(ca):
            return True                 # 紛れ込んだ印（プラネタリウ５ム）
        for k in (at - 1, at + 1):
            if not (0 <= k < len(typed)):
                continue
            near = typed[k]
            if near == ca:
                return True             # 重複打鍵
            if is_kana(near) and kana_key_distance(ca, near) < FAR:
                return True             # 隣接キーが入り込んだ
        return False
    return True                         # 脱字・入替は形そのものが証拠


def _katakana_seed_all():
    """
    **辞書に載っているカタカナ語のぜんぶ**。戻り値: {読み: 表記}

    こちらは「**正しく書けている語の一覧**」として使う。
    直し先の一覧（`_katakana_seed`）とは**役目が違う**ので、
    長さの門も隣人の門も掛けない（項目48-BE）。

    英語側の土台「辞書に載っている語は正しく書けている。触らない」
    と同じものを、カタカナ側にも置いた。**片方にしか無かった**の
    が第35回前半の穴で、`リダイレクト → ダイレクト`
    `イレギュラー → レギュラー` はそこから出ていた
    （長い語が「直し先」の門で落とされると、**守る側からも
    消えていた**）。
    """
    global _seed_katakana_all_cache
    if _seed_katakana_all_cache is not None:
        return _seed_katakana_all_cache
    out = {}
    try:
        import seed_katakana
        for w in seed_katakana.KATAKANA_WORDS:
            out.setdefault(katakana_to_hiragana(w), w)
    except Exception:
        out = {}
    _seed_katakana_all_cache = out
    return out


def _katakana_seed_kana_only():
    """
    **ひらがなから寄せてよい**カタカナ語。戻り値: {読み: 表記}

    「その読みは**カタカナでしか書かれない**」語だけ
    （項目48-BH）。`katakana_for_hiragana` の受け持ちで、
    ひらがなで書かれた外来語をカタカナに直すときに使う。

    覚えた語だけを相手にしていた頃は、語彙ストアを見れば分かった
    （`_has_non_katakana_surface`）。**種を持つとその前提が崩れる**:

        かたつむり → カタツムリ   （蝸牛 とも書く）
        さくら   → サクラ       （桜）
        ぼたん   → ボタン       （牡丹）
        ひまわり → ヒマワリ     （向日葵）

    そこで**辞書を作る側で**調べてある（`seed_katakana_build.py`
    が IPAdic 392,016項目を全部見て、非カタカナの表記がある読みを
    `AMBIGUOUS_WORDS` に入れる）。9,094語のうち **7,403語**が
    「カタカナでしか書かれない」語。
    """
    global _seed_katakana_kana_only_cache
    if _seed_katakana_kana_only_cache is not None:
        return _seed_katakana_kana_only_cache
    out = {}
    try:
        import seed_katakana
        ambiguous = frozenset(getattr(seed_katakana, 'AMBIGUOUS_WORDS', ()))
        for w in seed_katakana.KATAKANA_WORDS:
            if w in ambiguous:
                continue
            out.setdefault(katakana_to_hiragana(w), w)
    except Exception:
        out = {}
    _seed_katakana_kana_only_cache = out
    return out


# 種からひらがな→カタカナに寄せてよい、読みの長さの下限（項目48-BI）。
SEED_KANA_MIN_LENGTH = 6


def _seed_kana_allowed(reading, surface):
    """
    **種の語へ、ひらがなから寄せてよいか**（項目48-BI）。

    実機のメモで1件だけ、こうなった:

        しゅぷーる → シュプール      （tab0 493行）

    前後は `ぎょえん` `うにゅーん` `ふぇぇん` という**その場で作った
    声**で、外来語のつもりではない。読みは1文字も変わらないので
    「壊した」とまでは言いにくいが、書いたものを勝手に変えている。

    **短い語には、もう1つ理由を求める。**

      6文字以上          … 字面が特徴的（この経路の元々の理屈）
      5文字以下でも通す  … `familiarity` が**ふつうに使う語**と
                           言っている（ずれ 0）とき

    実測: すくろーる(5)・どらっぐ(4)・くりっく(4) は ずれ 0、
    しゅぷーる(5) は 48。プラネタリウム(47) と アンチモン(49) を
    分けられなかった表（項目48-AF）だが、**短い語に限って
    「よく使うか」を尋ねる**ぶんには、はっきり割れる。

    **線引きは `seed_katakana.COMMON_WORDS` に焼き込んである。**
    `familiarity.json` そのものを読みに行かないのは、あれが
    exe に同梱されていないから（build.yml は保護対象で触れない）。
    読めない環境では**黙って効かなくなる**（項目48-AF の教訓）。
    種の一覧は .py なので PyInstaller が必ず持っていく。
    """
    if len(reading) >= SEED_KANA_MIN_LENGTH:
        return True
    return surface in _katakana_seed_common()


def _katakana_seed_common():
    """**ふつうに使う**カタカナ語の集合（項目48-BI）。"""
    global _seed_katakana_common_cache
    if _seed_katakana_common_cache is not None:
        return _seed_katakana_common_cache
    try:
        import seed_katakana
        out = frozenset(getattr(seed_katakana, 'COMMON_WORDS', ()))
    except Exception:
        out = frozenset()
    _seed_katakana_common_cache = out
    return out


def _katakana_seed():
    """
    **直し先になれる**カタカナ語。戻り値: {読み: 表記}

    2つの門を通ったものだけ（項目48-BB / 48-BD）。
    「正しく書けている語か」を尋ねるときは
    `_katakana_seed_all` のほう。
    """
    global _seed_katakana_cache
    if _seed_katakana_cache is not None:
        return _seed_katakana_cache
    out = {}
    try:
        import seed_katakana
        for w in seed_katakana.KATAKANA_WORDS:
            if len(w) >= SEED_KATAKANA_MIN_LENGTH:
                out.setdefault(katakana_to_hiragana(w), w)
    except Exception:
        out = {}
    _seed_katakana_cache = out
    return out


def _distance1_index(vocab):
    """
    **距離1の相手だけを素早く集めるための索引**（項目48-BC）。

    種を足すと直し先が56,000語になる。総当たりのままだと
    **1語直すのに0.23秒**かかり、977行のタブが分単位になる
    （実測）。学び21「遅さは測ってから直す」。

    束ね方は (先頭の文字, 長さ)。距離1では、
    **先頭が変わらないなら長さは ±1 まで**しか動かないので、
    3つの束を見れば足りる。先頭が変わる形は下の
    `_distance1_candidates` で名指しに拾う。

    戻り値: {(先頭の文字, 長さ): [語, ...]}, [先頭に出る文字]
    """
    idx = {}
    for w in vocab:
        if not w:
            continue
        idx.setdefault((w[0], len(w)), []).append(w)
    heads = sorted({k[0] for k in idx})
    return idx, heads


def _distance1_candidates(key, vocab, index):
    """
    `key` から距離1以内にありうる語だけを返す（取りこぼし無し）。

    先頭の文字が変わらないなら (1)。変わるなら、その1回の編集は
    必ず先頭に掛かっているので、形は次の4つしかない:

      (2) 先頭の置き換え      c + key[1:]
      (3) 先頭に1文字余分     c + key
      (4) 先頭の1文字が脱字   key[1:]
      (5) 先頭2文字の入れ替え key[1] + key[0] + key[2:]

    (2)(3)(4) は表を直に引けばよく、索引を持たなくてよい
    （その方が控えの大きさを増やさずに済む）。
    (5) は束 (key[1], 長さ) に入っている。
    """
    idx, heads = index
    L = len(key)
    out = set()
    for n in (L - 1, L, L + 1):
        out.update(idx.get((key[0], n), ()))
    if L >= 2:
        out.update(idx.get((key[1], L), ()))
        out.update(idx.get((key[1], L - 1), ()))
        rest = key[1:]
        for c in heads:
            if c + rest in vocab:
                out.add(c + rest)
            if c + key in vocab:
                out.add(c + key)
    out.discard(key)
    return out


def _store_revision(store):
    """
    語彙が変わった回数（項目48-BT）＋**最後の選択の枠が変わった回数**
    （項目48-QQ）。

    **控えの見分けに件数を使わない。** 語が増えなくても
    直し先の中身は変わる。`revision()` を持たないストア
    （試験用の作り物など）では -1 を返す＝**毎回作り直す**
    （遅いだけで、間違わない側）。

    ### なぜ枠の版も要るか（項目48-QQ）

    この下の表（`_katakana_vocabulary`・`_english_vocabulary`）は
    `store.lookup()` の並びの先頭を採り、その並びは
    **`last_choice` の枠で入れ替わる**。語彙が1つも動かなくても
    本人が選び直せば答えが変わるので、**語彙の版だけでは足りない**
    （`cachecheck.py` 第2節）。**ここ1か所に足す**——控えは
    いくつもあるが見分けは全部この関数を通る（学び22）。
    """
    try:
        rev = store.revision()
    except Exception:
        return -1
    try:
        import last_choice as _lc
        return (rev, _lc.frame_revision())
    except Exception:
        return (rev, 0)


def _indexed(store, attr, vocab):
    """索引をストアに控える（**直し先が変わったら**作り直す）。"""
    stamp = (_store_revision(store), len(vocab))
    cached = getattr(store, attr, None)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    index = _distance1_index(vocab)
    try:
        setattr(store, attr, (stamp, index))
    except Exception:
        pass
    return index


def _merged_cache(store, attr, seed, learned):
    """
    種と覚えた語を重ねた表を、ストアに控える。

    **控えないと、1語直すたびに56,000件の辞書を作り直す**ことに
    なる（英語の種はそれだけある）。

    作り直しの見分けは `store.revision()`（項目48-BT）。
    **覚えた語の件数では足りない**——件数が変わらないまま
    中身が入れ替わる（`バイオリン` → `ヴァイオリン`）ことがあり、
    そのとき控えは古い表を返し続けていた。
    """
    if not seed:
        return learned
    stamp = (_store_revision(store), len(seed))
    cached = getattr(store, attr, None)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    out = dict(seed)
    out.update(learned)
    try:
        setattr(store, attr, (stamp, out))
    except Exception:
        pass
    return out


def _katakana_targets(store):
    """
    カタカナの直し先。種に、覚えた語を**上書き**で重ねる。

    本人が書いた表記のほうが強い（同じ読みなら覚えたほうを採る）。
    """
    return _merged_cache(store, '_katakana_target_cache',
                         _katakana_seed(), _katakana_vocabulary(store))


# ------------------------------------------------------------
# カタカナ語
# ------------------------------------------------------------

def _katakana_vocabulary(store, min_count=2):
    """
    語彙のうち「表記がすべてカタカナ」の語。

    戻り値: {読み: 表記}。同じ読みに複数あれば、
    **`store.lookup()` の並びで最初に来るカタカナ表記**。
    結果はストアに控える（**語彙か枠が変わったら**作り直す）。

    見分けは `_store_revision()`（項目48-BT・48-QQ）。

    ### ★★ 「回数の多いほう」をやめた理由（項目48-QQ・2026-09-05）

    回数の記録を廃したので（48-QG）、ここの `count` は
    **メモリ上の写し（solid なら 2・そうでなければ 1）**しかない。
    そのまま最大を採ると、同じ読みに solid なカタカナ表記が2つある
    とき **`to_list()` に先に出たほう**が勝ち、
    `lookup()` の並び（`_rank_key` ＋ **最後の選択の枠**）を
    **迂回してしまう**（学び22）。実測でも `cachecheck.py` が
    「本人が選び直しても表が入れ替わらない」で落ちていた
    ——`ばいおりん` を `ヴァイオリン` に選び直しても、この表は
    `バイオリン` を返していた。

    **`lookup()[0]` をそのまま採ってはいけない**——先頭がカタカナ
    以外の表記の読み（`こうえん → 公園`）が表から丸ごと落ちる。
    **並びの順に見て、最初に条件を満たすものを採る。**
    （種を入れたストアで測って、初期状態の答えは差0・落ちた読み0）
    """
    rev = _store_revision(store)
    cached = getattr(store, '_katakana_vocab_cache', None)
    if cached is not None and cached[0] == (rev, min_count):
        return cached[1]

    out = {}
    try:
        readings = list(store._by_reading)
    except Exception:
        try:
            readings = sorted({(e.get('reading') or '')
                               for e in store.to_list()} - {''})
        except Exception:
            readings = []
    for reading in readings:
        if not reading:
            continue
        try:
            entries = store.lookup(reading)
        except Exception:
            continue
        for e in entries:
            if (e.get('count', 0) or 0) < min_count:
                continue
            surface = e.get('surface') or ''
            if not is_all_katakana(surface):
                continue
            out[reading] = surface
            break
    try:
        store._katakana_vocab_cache = ((rev, min_count), out)
    except Exception:
        pass
    return out


def _has_non_katakana_surface(store, reading):
    """その読みに、カタカナ以外の表記も登録されているか。"""
    try:
        for e in store.lookup(reading):
            if not is_all_katakana(e.get('surface') or ''):
                return True
    except Exception:
        return True     # 分からないときは「ある」側に倒して触らない
    return False


def fix_katakana_word(word, store, known_word=False,
                      min_length=MIN_LENGTH):
    """
    カタカナの並び1つを、語彙にある外来語へ直す。

    word: 元のテキストのままの並び（カタカナ以外が紛れていてもよい）
    known_word: 形態素解析がこの並びを「辞書にある1語」として
        読めたか。読めたなら正しい語なので触らない。

    戻り値: 直した表記（カタカナ）。直さないなら None。
    """
    if known_word or not word:
        return None
    typed = katakana_to_hiragana(word)
    # **短い並び（3〜4字）は脱字だけ疑う**（項目48-IT・うにさんの
    # 「パコン・パソン・パソコ・キボード・キーード・キーボー は異様」）。
    # 短い語は同じ長さの別語がいくらでもあるので置換は見ない。
    # 1字落ちて本来より1字短い形だけを、表の語に戻す。
    short = False
    if len(typed) < min_length:
        if len(typed) < 3:
            return None
        short = True
        # 短い並びがそれ自体で表の語（ローマ・パコン）なら、本人の語。
        # `ローマ字入力` の `ローマ` が `ローマン` に伸びた（tests_mock）。
        try:
            import oddness as _odd
            _words = _odd._load()
            if _words and word in _words:
                return None
        except Exception:
            pass

    # 直し先は「種＋覚えた語」。**覚えた語だけを尋ねている関門
    # （is_known_compound など）とは入れ物を分ける**（項目48-BA）。
    vocab = _katakana_targets(store)
    if not vocab:
        return None

    # 読みがそのまま語彙にあるなら、それは正しく書けている。
    # （表記の違い＝ひらがなで書いた場合の直しは、
    #   katakana_for_hiragana の受け持ち。）
    if typed in vocab:
        surface = vocab[typed]
        return surface if surface != word else None

    # **辞書に載っている語は、正しく書けている。触らない**
    # （項目48-BE）。英語側と同じ土台をカタカナ側にも置いた。
    # ここは**門を通す前の全語**を見る。直し先の門で落とした語まで
    # 守られなくなると、`リダイレクト → ダイレクト`
    # `イレギュラー → レギュラー` のように**長いほうが壊れる**。
    if typed in _katakana_seed_all():
        surface = _katakana_seed_all()[typed]
        return surface if surface != word else None

    budget = allowed_edits(len(typed))
    best = None          # (距離, 読み)
    second = None
    ties = []            # best と同じ距離で並んだ読み（best を含む）
    _no_bar = typed.replace('ー', '')
    index = _indexed(store, '_katakana_index_cache', vocab)
    for reading in _distance1_candidates(typed, vocab, index):
        if abs(len(reading) - len(typed)) > budget:
            continue
        if short and len(reading) != len(typed) + 1:
            continue
        # 総当たりの前に、表を作らない関門で間引く（項目48-BC）
        if not within_one_edit(typed, reading):
            continue
        # **打ち間違いとして説明が付かない相手は、そもそも候補に
        # しない**（項目48-BD）。
        #
        # 学び38・項目48-AN は「歯止めは候補を絞る前ではなく、
        # 決まってから掛ける」と言っているが、**あれは「好み」で
        # 間引くな**という話（回数の多いほうを先に残すと、
        # 同点＝触らない が「決まった」に化ける）。
        # こちらは**そもそも届くかどうか**の判定なので、
        # 距離の関門や「ーの有無だけの違い」と同じ側にある。
        # 実測でも、後ろに置いても前に置いても**4つの材料と
        # 全6タブの結果は1文字も変わらず**、前に置いたときだけ
        # `クリッック → クリック` `ファイイル → ファイル` が
        # 増えた（届かない相手が同点の相手になっていた）。
        if (reading in _katakana_seed()
                and reading not in _katakana_vocabulary(store)
                and not typo_explains_seed_word(typed, reading)):
            continue
        # 長音「ー」の有無だけが違う相手は、誤字ではなく**表記のゆれ**。
        # どちらも正しい書き方なので直さない
        # （ダイアログ／ダイアローグ、コンピュータ／コンピューター。
        #   実機のメモで「ダイアログ」が「ダイアローグ」に
        #   書き換えられた・2026-08-10）。
        # かな連続の探索にも同じ考えの関門がある
        # （find_similar_readings の「ーの位置は動かさない」）。
        # 伸ばし棒だけの違いは揺れ（コンピュータ／コンピューター）なので
        # 直さない。ただし**短い並びの ー の脱字**（キボード → キーボード）
        # は揺れではなく落としたもの（項目48-IT・うにさんの指定）。
        if reading.replace('ー', '') == _no_bar \
                and not (short and len(reading) == len(typed) + 1):
            continue
        d = edit_distance(typed, reading, limit=budget)
        if d > budget:
            continue
        if best is None or d < best[0]:
            second = best
            best = (d, reading)
            ties = [reading]
        elif d == best[0]:
            ties.append(reading)
            if second is None or d < second[0]:
                second = (d, reading)
        elif second is None or d < second[0]:
            second = (d, reading)
    if best is None:
        return None
    # 同じ距離で並んだら、**拮抗を決める**（項目48-IU・うにさんの
    # 「拮抗したら何もしないは逆効果。異様であれば最有力の候補に補正する」）。
    # 決め手は 48-IS と同じ順: 使用実績（回数）→ 一般的さ（同梱の表の
    # 費用）。それでも並ぶなら手を引く（`キーード`: キーボード 回数3・
    # 費用13 ／ キーワード 回数1・費用62 → キーボード）。
    if second is not None and second[0] == best[0]:
        chosen = _break_tie(ties, vocab, store, typed)
        if chosen is None:
            return None
        best = (best[0], chosen)
    surface = vocab[best[1]]
    return surface if surface != word else None


def _break_tie(readings, vocab, store, typed=''):
    """
    同じ距離で並んだ読みから1つ選ぶ（項目48-IU）。

    決め手の順:

        ① **連打の畳み**（打った並びの中の同じ字の連続を1つ減らすと
           その読みになる）——★★ **これは置換より確からしい**
        ② 立っている語か（`count >= 2` ＝ solid）
        ③ 同梱の表で一般的なほう（費用が小さい）
        どちらでも並ぶなら None（触らない）

    ### ★ ① を足した理由（項目48-QG'・2026-09-05）

    回数の記録をやめたら、**②の目盛りが 2段しか残らなくなった**。
    育った語彙で同梱の見本が2つ落ちた（`seedcheck` 40 → 38）:

        クリッック → **クリニック**（正しくは クリック）
        ファイイル → **ファイナル**（正しくは ファイル）

    どちらも「回数 1331 対 4」「924 対 36」で②が裁いていたもの。
    ③に落ちると**カタカナでは表の費用が当てにならない**——
    実測で `クリック 35 / クリニック 33`・`ファイル 33 / ファイナル 8`。
    費用は (読み, 表記) ではなく**表記だけ**の値なので、別の読みでの
    安さが混ざる（`撃つ 0`・`コウチョウ 50` と同じ罠）。

    そこで**打鍵の形**で裁く。`クリッック` は `ッ` が2つ、
    `ファイイル` は `イ` が2つ——**同じ字の連続を1つ減らすと相手に
    なる**。SPEC の4つの型のうち「重複」そのもので、置換1回より
    ずっとありふれた誤り。**数字ではなく打鍵の形なので、
    ★★「論理的に正しいもの」の側**（回数が無くても言える）。

    判定は `corrector._is_repeat_collapse` を借りる——**同じ判定を
    2か所に書かない**（48-GN）。
    """
    def _repeat(reading):
        if not typed or reading == typed:
            return False
        try:
            from corrector import _is_repeat_collapse
            return bool(_is_repeat_collapse(typed, reading))
        except Exception:
            return False

    def _count(reading):
        try:
            return max((int(e.get('count', 0)) for e in store.lookup(reading)),
                       default=0)
        except Exception:
            return 0

    def _cost(reading):
        try:
            from corrector import _table_cost
            c = _table_cost(vocab[reading])
        except Exception:
            c = None
        return c if c is not None else 10 ** 9

    def _key(r):
        return (0 if _repeat(r) else 1, -_count(r), _cost(r))

    ranked = sorted(readings, key=_key)
    if len(ranked) < 2:
        return ranked[0] if ranked else None
    a, b = ranked[0], ranked[1]
    if _key(a) == _key(b):
        return None
    return a


def dictionary_single_word(word, tokenize_fn):
    """
    そのカタカナの並びが、辞書の**1語**として読めるか（項目48-IT）。

    `dictionary_explains` は `ディスレイ` を `ディス`＋`レイ` と2語に
    割っても「説明が付く」と言う。うにさんの指定「ディスレイ・ディスプレ
    は異様」。**1語で読めるなら本人の語**（コールバック・キログラム）、
    2語以上に割れてしか読めないなら、1手で表の語に届くほうを採る。
    """
    if not word or tokenize_fn is None:
        return False
    try:
        toks = [t for t in tokenize_fn(word)]
    except Exception:
        return False
    if len(toks) == 1 and toks[0][0] == word and toks[0][5]:
        return True
    try:
        toks = [t for t in tokenize_fn('1' + word) if t[3] >= 1]
    except Exception:
        return False
    return len(toks) == 1 and toks[0][0] == word and bool(toks[0][5])


def is_known_compound(parts, store):
    """
    複数の**ユーザーが実際に使っている外来語**がつながった形か。

    「ショートカットキー」＝ショートカット＋キー、
    「タッチスクリーン」＝タッチ＋スクリーン のような複合語を、
    1文字違いの別語に縮めてしまわないための関門
    （実機のメモで縮められた・2026-08-10）。

    ここでは「語彙ストアに使用実績がある語」だけを数える。
    janome の辞書まで根拠にするかどうかは、この関門ではなく
    `dictionary_explains` の側で見る（下の注意書きを参照）。
    """
    if len(parts) < 2:
        return False
    vocab = _katakana_vocabulary(store)
    for p in parts:
        if not is_all_katakana(p):
            return False
        if katakana_to_hiragana(p) not in vocab:
            return False
    return True


def dictionary_explains(word, tokenize_fn):
    """
    そのカタカナの並びは、**形態素解析の辞書だけで説明が付く**か。

    付くなら、利用者が実在する語を書いたということなので触らない
    （検証レポート 2-C。`コールバック`→`オールバック`、
    `キログラム`→`プログラム`、`ハーモニカ`→`ハーモニー`）。

    `is_known_compound` が利用者の語彙しか信じないのに対し、
    こちらは**辞書**を信じる。両方要る:
      - 利用者の語彙にしか無い語がある（社内用語・作品名）
      - 辞書にしか無い語がある（コールバック・キログラム）

    見方を2段にしてある。

      1. その並び単体を解析して、**全部が辞書にある語**になるか。
         1語でも複合でもよい（コールバック＝コール＋バック）。
      2. 駄目なら、**前に数字を置いてから**もう一度解析する。
         IPAdic は単位を「名詞,接尾,助数詞」で持っており、
         **数字の後ろにしか出てこない**。そのため `キログラム` は
         単体だと未知語に落ちるが、`1キログラム` なら辞書の語になる
         （実機で `キログラム`→`プログラム` が出たのがこれ）。

    **承知の上の取りこぼし**: この関門を通すと、辞書の語2つに割れる
    打ち間違い（`プラモタリウム` ＝ プラモ＋タリウム）は直せなくなる。
    以前はそれを嫌って辞書を根拠にしていなかったが、実機のメモと
    SPEC.md 全体で測ったところ、**割れて困るのは正しい語のほう**
    だった（コールバック・ハーモニカ・バックアップ）。
    うにさんが挙げたプラネタリウムの誤字31例は、どれも辞書で説明が
    付かないので影響を受けない。取りこぼしは我慢できても、
    正しい文が壊れるのは我慢できない、という軸で選んでいる。

    tokenize_fn: corrector が使っているものと同じ字句解析の関数。
        戻り値は (表記, 品詞, 読み, 開始, 終了, 辞書にあるか) の並び。
    """
    if not word or tokenize_fn is None:
        return False

    def _all_known(tokens, text, offset=0):
        toks = [t for t in tokens if t[3] >= offset]
        if not toks:
            return False
        if ''.join(t[0] for t in toks) != text:
            return False
        return all(t[5] for t in toks)

    try:
        if _all_known(tokenize_fn(word), word):
            return True
    except Exception:
        return False

    # 単位（助数詞）は数字の後ろにしか出てこない。
    try:
        toks = tokenize_fn('1' + word)
    except Exception:
        return False
    rest = [t for t in toks if t[3] >= 1]
    return (len(rest) == 1 and rest[0][0] == word and bool(rest[0][5]))


def katakana_for_hiragana(reading, store, min_length=MIN_LENGTH):
    """
    ひらがなで書かれた外来語を、カタカナの表記に直す。

    「ぷらねたりうむ」→「プラネタリウム」。うにさんの指定
    （カタカナが適した単語はカタカナに補正する）。

    「ひらがなで打たれたものはひらがなのまま」という原則の例外なので、
    根拠が揃ったときだけ行う:
      - 5文字以上（短い語は、たまたま同じ読みの和語がある）。
        min_length で緩められる。**別の関門で既に根拠が揃っている
        場合だけ**（濁点のキーの打ち間違いから完全一致で辿り着いた
        「どらっぐ」など）4文字まで下げてよい。
      - その読みの表記が**カタカナのものしか無い**
        （漢字やひらがなの表記もあるなら、外来語だと言い切れない）
      - 使用回数が2回以上（辞書から取り込んだだけの語に寄せない）

    戻り値: カタカナの表記。直さないなら None。
    """
    if not reading or len(reading) < min_length:
        return None
    if not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in reading):
        return None
    # **その人が書いた語のほうが強い。** 覚えていればそれを使う。
    surface = _katakana_vocabulary(store).get(reading)
    if not surface:
        # 覚えていなくても、**辞書が「カタカナでしか書かない語」と
        # 言っている**なら寄せてよい（項目48-BH）。
        # `AMBIGUOUS_WORDS`（かたつむり・さくら・ぼたん…）は
        # ここに来ない。
        seeded = _katakana_seed_kana_only().get(reading)
        if seeded and _seed_kana_allowed(reading, seeded):
            surface = seeded
    if not surface:
        return None
    # その人の語彙に漢字・ひらがなの表記があるなら、外来語だと
    # 言い切れない（種より、その人の書き方を優先する）。
    if _has_non_katakana_surface(store, reading):
        return None
    return surface


def is_stray(ch):
    """カタカナの並びに紛れうる「かなではない1文字」か。"""
    return bool(ch) and bool(_STRAY_RE.match(ch))


def find_katakana_runs(line, min_katakana=4):
    """
    カタカナの並びを取り出す。

    紛れてよいのは **カタカナに前後を挟まれた1文字だけ**
    （プラネ１リウム の「１」）。末尾にくっついた文字は含めない。

    以前は末尾の1文字も含めていたが、実機のメモで総点検したところ、
    日本語の文に普通に出てくる区切り文字を巻き込んで消していた
    （2026-08-10）:

        （東京上野キャンパス） → 閉じ括弧が消える
        ファイル/編集         → スラッシュが消える
        文脈ベクトル=0.02s    → 等号が消える
        カタカナ+漢字         → プラスが消える

    「プラネタリウ［」のように**末尾に紛れた形**は、
    呼び出し側が「その1文字を除いた部分が既に正しい語かどうか」を
    確かめたうえで、改めて1文字足して試す（corrector.py）。
    キャンパス は正しい語なので触られず、プラネタリウ は
    正しい語ではないので直る、という切り分けになる。

    戻り値: [(開始, 終了, 並び), ...]
    """
    runs = []
    n = len(line)
    i = 0
    while i < n:
        if not is_katakana_char(line[i]):
            i += 1
            continue
        j = i
        strays = 0
        while j < n:
            ch = line[j]
            if is_katakana_char(ch):
                j += 1
                continue
            # 紛れた1文字は、**次の文字もカタカナ**のときだけ認める
            if (strays == 0 and is_stray(ch)
                    and j + 1 < n and is_katakana_char(line[j + 1])):
                strays += 1
                j += 1
                continue
            break
        run = line[i:j]
        if sum(1 for c in run if is_katakana_char(c)) >= min_katakana:
            runs.append((i, j, run))
        i = max(j, i + 1)
    return runs


def is_known_katakana(word, store):
    """その並びが、そのまま語彙にある外来語か（＝正しく書けている）。"""
    if not word:
        return False
    return katakana_to_hiragana(word) in _katakana_vocabulary(store)


# ------------------------------------------------------------
# 英単語
# ------------------------------------------------------------

# 英単語として覚える・直す対象。数字混じり（Python3・v1）は
# 対象にしない（版番号や識別子は誤字ではないため）。
_ENGLISH_RE = re.compile(r'[A-Za-z]+')

# 英単語であることを示す読みの前置き。
# 語彙ストアは「読み→表記」の入れ物なので、英単語も同じ形で
# 入れる。かなの読みと混ざらないよう、前置きを付けて区別する。
ENGLISH_PREFIX = 'en:'

# 英単語を覚える・直すときの最短の長さ。
# 短い語は「1文字違いの別の語」が多すぎる（form/from・there/three）。
# うにさんの例（Planetarium 系）は10文字以上なので、
# 安全側に倒して6文字からにする。
MIN_ENGLISH_LENGTH = 6


def english_reading(word):
    """英単語を語彙ストアに入れるときの読み（小文字に揃える）。"""
    return ENGLISH_PREFIX + word.lower()


_EN_VOWELS = frozenset('aeiouy')


def looks_like_english(word):
    """
    英語の綴りとして無理がないか。

    **英単語の辞書は持たない**方針なので、綴りの決まりだけで見る。
    False を返すのは「まず英語には現れない形」だけで、判断が付かない
    ものは True に倒す。

    この判定は **「他の語を直す側になれるか」にしか使わない**。
    直される側には使わないので、誤って False にしても
    「直せない語が増える」だけで、書いた文字が壊れることはない
    （`sqlite` のような、英語の綴りから外れた正しい語を
    　巻き添えにしないための線引き）。

    これが要るのは、メモの中で**誤字のほうが多い**とき。
    回数だけで代表形を決めると、誤字が唯一の正解になり、
    正しく書いたほうが誤字へ直されてしまう（実機の語彙に
    `Plaqnetarium` が129回で入り、`Planetarium` と打つと
    `Plaqnetarium` に直されていた・2026-08-10）。
    日本語側の「異様さ」で守るのと同じ考え方を、英字に当てる。
    """
    w = (word or '').lower()
    if not w or not w.isalpha():
        return False
    if not any(ch in _EN_VOWELS for ch in w):
        return False                    # 母音が1つも無い
    # q の後は u（英語の綴りの決まり）
    for i, ch in enumerate(w):
        if ch == 'q' and (i + 1 >= len(w) or w[i + 1] != 'u'):
            return False
    # 同じ字が3つ以上続く
    run = 1
    for a, b in zip(w, w[1:]):
        run = run + 1 if a == b else 1
        if run >= 3:
            return False
    # 母音を挟まずに子音が6つ以上続く
    run = 0
    for ch in w:
        if ch in _EN_VOWELS:
            run = 0
        else:
            run += 1
            if run >= 6:
                return False
    return True


def learn_english_words(text, store, category='英語'):
    """
    文章に出てくる英単語を覚える。

    **英単語の辞書は持っていない**ので、直す相手は「ユーザーが
    正しく書いた語」だけになる。外部の辞書やモデルを持ち込まない
    という方針のため、ここは避けられない。裏を返せば、一度でも
    正しく書いた語はそれ以降ずっと直せるようになる。

    覚えるのは5文字以上の英字だけの並び。数字や記号が混ざったもの
    （Python3・v1.0・md5）は、誤字ではなく識別子のことが多いので
    覚えない。

    **既に覚えている語は数え直さない。** ここは打鍵が落ち着くたびに
    メモ全文で呼ばれるので、呼ばれるたびに `store.add` していると
    **使用回数が際限なく増える**（実機・2026-08-11。1回の呼び出しで
    メモ中の英単語すべてが +1 され、2回打鍵を止めただけで
    どの誤字も `own >= 2`＝「何度も書いている語＝正しい」に化けて、
    英単語の補正が丸ごと効かなくなっていた）。
    日本語側で「同じ行を二度学習しない」ようにしたのと同じ理屈
    （項目46・学び2）。
    ついでに、戻り値が**新しく覚えた語の数**になるので、
    呼び出し側が毎回 `store.save()`（2.3MB の書き出し・77ms）を
    走らせずに済む。

    戻り値: **新しく**覚えた語の数
    """
    if not text:
        return 0
    try:
        known = set(_english_vocabulary(store))
    except Exception:
        known = set()
    added = 0
    for m in _ENGLISH_RE.finditer(text):
        word = m.group(0)
        if len(word) < MIN_ENGLISH_LENGTH:
            continue
        if word.lower() in known:
            continue        # 既に覚えている。数え直さない
        # 前後に数字や記号がくっついている（Python3・utf8）なら
        # 識別子とみなして覚えない
        s, e = m.start(), m.end()
        if s > 0 and (text[s - 1].isdigit() or text[s - 1] in _GLUED_SYMBOLS):
            continue
        if e < len(text) and (text[e].isdigit() or text[e] in _GLUED_SYMBOLS):
            continue
        # **打ち間違いを覚えない。**
        # 覚えてしまうと「知っている語＝正しい」と見なして
        # 二度と直せなくなる（実機で Pplanetarium が覚えられ、
        # Planetarium に直らなくなった・2026-08-10）。
        # 既に知っている語の1文字違いなら、それは誤字なので覚えない。
        # 日本語側の「誤変換語を覚えない」（学び2）と同じ考え方。
        try:
            if fix_english_word(word, store):
                continue
        except Exception:
            pass
        try:
            store.add(english_reading(word), word, category)
            known.add(word.lower())
            added += 1
        except Exception:
            pass
    return added


def relearn_english_from_texts(texts, store):
    """
    メモ全文から英単語を覚え直す（起動時に一度）。

    **多く書かれている形から先に覚える。** 少ないほうは
    「多いほうの打ち間違い」として自動的に弾かれる
    （learn_english_words の中の関門）。順番に頼らない形にして
    おかないと、誤字がメモの先に出てきた場合に誤字のほうを
    覚えてしまう。

    ただし**回数だけでは決めない**。メモの中に誤字のほうが多く
    残っていると、多数決では誤字が唯一の正解になり、正しく書いた
    ほうが誤字へ直されてしまう（実機で `Plaqnetarium` 16回 /
    `Planetarium` 2回・2026-08-10）。`looks_like_english` を
    通らない綴りは他の語を直す側になれないので、この場合は
    **両方とも覚える**（正しいほうが弾かれない）。

    覚え直す前に、**覚えている英単語をいったん全部捨てる**。
    ここが自己修復になっている: 以前の版は誤字も覚えてしまって
    いたので、そのまま残すと「知っている語＝正しい」と見なされて
    永遠に直らない（実機で Pplanetarium が直らなかった・
    2026-08-10）。使用回数の少ないものだけを捨てる形も試したが、
    誤字が2回以上覚えられていると残ってしまい、直らないままだった。

    全部捨ててよいのは、**英単語の記録がメモから作り直せる**から。
    かなの語彙と違って、外から取り込んだ辞書も、長い時間をかけて
    育てた実績も持っていない（持ちようがない）。捨てて拾い直す
    ほうが、汚れが残るより確実。

    戻り値: 覚えた語の数
    """
    from collections import Counter
    counts = Counter()
    for text in texts:
        if not text:
            continue
        for m in _ENGLISH_RE.finditer(text):
            word = m.group(0)
            if len(word) < MIN_ENGLISH_LENGTH:
                continue
            s, e = m.start(), m.end()
            if s > 0 and (text[s - 1].isdigit() or text[s - 1] in _GLUED_SYMBOLS):
                continue
            if e < len(text) and (text[e].isdigit() or text[e] in _GLUED_SYMBOLS):
                continue
            counts[word] += 1

    # 覚えている英単語をいったん全部捨てる（上の説明を参照）
    try:
        stale = [e for e in store.to_list()
                 if (e.get('reading') or '').startswith(ENGLISH_PREFIX)]
        for e in stale:
            store.remove(e['reading'], e['surface'])
    except Exception:
        pass
    try:
        store._english_vocab_cache = None
    except Exception:
        pass

    # **誤字は正しい綴りの周りに集まる。**
    # 覚える順を回数だけで決めると、誤字を並べた行があるメモでは
    # 誤字が先に入り、後から来た正しい綴りが「その誤字の打ち間違い」
    # として捨てられる（実機・2026-08-11。`Planetarium` が1回、
    # 試験用に並べた誤字が7種類あり、`lanetarium` が先に覚えられて
    # `Planetarium` が覚えられなくなった。以後 `Panetarium` は
    # `lanetarium` へ直され、他の誤字は「知っている語」になって
    # 直らなくなった）。
    #
    # そこで**1文字違いの仲間がいくつあるか**を先に見る。
    # 誤字は正しい綴りから1文字違いだが、誤字どうしは2文字以上
    # 離れることが多いので、**仲間がいちばん多いものが正しい綴り**。
    # 実測（実機のメモ）:
    #   Planetarium 仲間5 / lanetarium 仲間3 / Panetarium 仲間3
    #   Pklanetarium 仲間2 / Pllanetarium 仲間2 / Planetariumm 仲間1
    # 誤字が並んでいないメモでは仲間が全部0になり、これまでどおり
    # 回数の順になる（ふるまいは変わらない）。
    words = list(counts)
    neighbours = {w: 0 for w in words}
    for i, a in enumerate(words):
        for b in words[i + 1:]:
            if abs(len(a) - len(b)) > 1:
                continue
            if edit_distance(a.lower(), b.lower(), limit=1) <= 1:
                neighbours[a] += 1
                neighbours[b] += 1

    added = 0
    for word, n in sorted(counts.items(),
                          key=lambda kv: (-neighbours[kv[0]], -kv[1], kv[0])):
        # **何度も書いている語は、種が「直せる」と言っても覚える**
        # （2026-08-12・項目48-BK）。種を持つ前は、覚える側の
        # 関門（直せる語＝誤字なので覚えない）で足りていた。
        # 種を持つと、**辞書に無いだけの正しい語**（`callout`
        # `tkinter` のような新しめの語・道具の名前）が
        # 「直せる語」に見えるので、**永久に覚えられなくなる**。
        # 覚えられなければ `own >= 2` の門も一生効かない。
        # **1文字違いの仲間がいない**ことも求める。誤字は正しい
        # 綴りの周りに集まるので、仲間が0なら「誤字の群れ」の
        # 一部ではない。うにさんのメモは誤字を何度も並べて書いて
        # あるので、回数だけで許すと `lanetarium` `panetarium` を
        # 覚えてしまい、二度と直せなくなる（実測でテストが3件落ちた）。
        if not (n >= 2 and neighbours.get(word, 0) == 0
                and looks_like_english(word.lower())):
            try:
                if fix_english_word(word, store):
                    continue
            except Exception:
                pass
        try:
            # **メモに出てきた回数をそのまま使用回数にする。**
            # 1回だけ足すと、どの語も回数1になり
            # 「何度も書いている語＝正しい」（own >= 2）の判定が
            # 死ぬ。以前はそれでも動いているように見えたが、
            # `learn_english_words` が呼ばれるたびに回数を
            # 水増ししていたからで、そちらを直したらここが要る
            # （実機・2026-08-11）。
            for _ in range(max(1, n)):
                store.add(english_reading(word), word, '英語')
            store._english_vocab_cache = None
            added += 1
        except Exception:
            pass
    return added


def _english_vocabulary(store, min_count=1):
    """
    覚えている英単語。戻り値: {小文字の語: 表記}

    同じ語を大文字小文字ちがいで覚えていたら、
    **`store.lookup()` の並びで最初に来るほう**を採る
    （Planetarium と planetarium が両方あるとき）。

    見分けは `_store_revision()`（項目48-BT・48-QQ）。
    「回数の多いほう」をやめた理由は `_katakana_vocabulary` の
    説明を参照（回数は廃した・並びを迂回してはいけない）。
    """
    rev = _store_revision(store)
    cached = getattr(store, '_english_vocab_cache', None)
    if cached is not None and cached[0] == (rev, min_count):
        return cached[1]

    out = {}
    try:
        readings = [r for r in store._by_reading
                    if r.startswith(ENGLISH_PREFIX)]
    except Exception:
        try:
            readings = sorted({(e.get('reading') or '')
                               for e in store.to_list()
                               if (e.get('reading') or '').startswith(
                                   ENGLISH_PREFIX)})
        except Exception:
            readings = []
    for reading in readings:
        try:
            entries = store.lookup(reading)
        except Exception:
            continue
        for e in entries:
            if (e.get('count', 0) or 0) < min_count:
                continue
            out[reading[len(ENGLISH_PREFIX):]] = e.get('surface') or ''
            break
    try:
        store._english_vocab_cache = ((rev, min_count), out)
    except Exception:
        pass
    return out


_QWERTY_ROWS = ('qwertyuiop', 'asdfghjkl', 'zxcvbnm')
_QWERTY_POS = {ch: (r, c)
               for r, row in enumerate(_QWERTY_ROWS)
               for c, ch in enumerate(row)}
_EN_VOWEL_SET = frozenset('aeiou')


def _qwerty_near(a, b):
    """QWERTY 配列で隣り合うキーか（corrector._qwerty_adjacent と同じ形）。"""
    pa, pb = _QWERTY_POS.get(a), _QWERTY_POS.get(b)
    if pa is None or pb is None or a == b:
        return False
    return abs(pa[0] - pb[0]) <= 1 and abs(pa[1] - pb[1]) <= 1


def typo_explains_seed_english(typed, known):
    """
    **種の英単語へ直すとき、その1手が説明が付くか**（項目48-BJ）。

    カタカナ側（`typo_explains_seed_word`）と同じ考えだが、
    **英語には「打ち間違い」ではない誤りが混じる**ところが違う。

        seperate / definately / accomodate / occured

    これらは指が滑ったのではなく、**綴りを覚え違えている**。
    キーの隣接だけで裁くと、いちばん直したい形が落ちる。
    そこで置換のときだけ「**母音どうしの取り違え**」も通す
    （英語の綴り間違いは母音に集中する）。

    | 1手 | 通す条件 |
    |---|---|
    | 脱字・入替 | 形そのものが証拠。無条件 |
    | 置換 | キーが隣同士、**または母音どうし** |
    | 余分な1文字 | 隣と同じ（重複打鍵）か、隣とキーが近い |

    実測（材料 702語の英字の並び）で止まったもの:

        iconic  → ironic    c と r は隣ではない
        lineno  → linens    o と s は隣ではない（識別子）
        rcWork  → rework    c と e は隣ではない
        callouts → callous  余分な t は u とも s とも隣ではない
        neighbours → neighbors  余分な u は o とも r とも隣ではない
        fimports → imports  余分な f は i の隣ではない
        pchanged → changed  余分な p は c の隣ではない

    **うにさんの Planetarium 12例は全部通る**（重複・隣接キー・
    脱字・入替のどれかで説明が付く）。
    """
    kind, ca, cb, at = single_edit(typed, known)
    if kind == '置換':
        if _qwerty_near(ca, cb):
            return True
        return ca in _EN_VOWEL_SET and cb in _EN_VOWEL_SET
    if kind == '余分':
        for k in (at - 1, at + 1):
            if not (0 <= k < len(typed)):
                continue
            if typed[k] == ca or _qwerty_near(ca, typed[k]):
                return True
        return False
    return True                         # 脱字・入替は形そのものが証拠


def _english_seed():
    """
    **直し先になれる**英単語。戻り値: {小文字の語: 表記}

    ふつうに使う語だけ（SCOWL size 35）。珍しい語まで直し先に
    すると `tkinter → tinter` `UniDic → Unific` と引っぱられる
    （項目48-BK）。
    """
    global _seed_english_cache
    if _seed_english_cache is not None:
        return _seed_english_cache
    out = {}
    try:
        import seed_english
        for w in seed_english.ENGLISH_WORDS:
            out[w] = w
    except Exception:
        out = {}
    _seed_english_cache = out
    return out


def _english_seed_all():
    """
    **辞書に載っている英単語のぜんぶ**（触らない語の一覧）。

    直し先より**広い**（SCOWL size 60・米英の両方）。
    ここが狭いと、`footer → rooter` `iconic → ironic`
    `neighbours → neighbors` と**正しく書けている語を壊す**
    （項目48-BK）。カタカナ側の `_katakana_seed_all` と同じ役目。
    """
    global _seed_english_all_cache
    if _seed_english_all_cache is not None:
        return _seed_english_all_cache
    out = set(_english_seed())
    try:
        import seed_english
        out |= set(getattr(seed_english, 'EXTRA_WORDS', ()))
    except Exception:
        pass
    _seed_english_all_cache = frozenset(out)
    return _seed_english_all_cache


def _english_targets(store):
    """英単語の直し先。種に、覚えた語を**上書き**で重ねる。"""
    return _merged_cache(store, '_english_target_cache',
                         _english_seed(), _english_vocabulary(store))


def _english_count(store, key):
    """その英単語を何回書いたか（覚えていなければ 0）。"""
    try:
        return max((e.get('count', 0)
                    for e in store.lookup(ENGLISH_PREFIX + key)),
                   default=0)
    except Exception:
        return 0


def fix_english_word(word, store):
    """
    英単語1つを、覚えている語へ直す。

    カタカナ語と同じ考え方（素直な編集距離・長さで守る・
    迷ったら直さない）。大文字小文字の違いは誤字と見なさない
    （小文字に揃えてから比べ、直すときは覚えている表記を使う）。

    戻り値: 直した表記。直さないなら None。
    """
    if not word or len(word) < MIN_ENGLISH_LENGTH:
        return None
    if not word.isalpha():
        return None
    vocab = _english_targets(store)
    if not vocab:
        return None
    key = word.lower()
    # **辞書に載っている語は、正しく書けている。触らない**
    # （項目48-BA。**単語リストを持つようにした以上、これが土台**）。
    #
    # 種を足す前は「覚えた語＝その人が書いた語」だけが相手だった
    # ので、この門は `own >= 2` が兼ねていた。**種を足した瞬間に
    # その前提が崩れる**: 一度も書いていない正しい語が、距離1の
    # 隣の語へ直されてしまう（実測で committee→committed、
    # possible→possibly と壊れた）。
    #
    # **効かせるのは「種の辞書」に載っている語だけ**。覚えた語まで
    # 同じ扱いにすると、`Plaqnetarium` を20回書いたメモで
    # 「覚えている＝正しい」になって直せなくなる（実機で起きた形。
    # 覚えた語の側の門は `own >= 2 かつ 英語らしい綴り` のままで、
    # **英語らしくない綴りは何度書いても正しいと認めない**）。
    if key in _english_seed_all():
        return None
    # **小文字のあとに大文字が来る語（CamelCase）は、識別子か
    # 固有名詞**（項目48-BK）。`UniDic` `AttributeError`
    # `RegisterHotKey` `DwmSetWindowAttribute`。英語の単語に
    # この形は出てこない。**書いた人の意図**がはっきりしている。
    #
    # 「小文字のあと」を条件にするのが要点。`PPlanetarium`
    # （うにさんの見本。同じキーを2度打った形）は大文字が続いて
    # いるだけなので、**ここで止めてはいけない**。
    if any(word[i].isupper() and word[i - 1].islower()
           for i in range(1, len(word))):
        return None
    own = _english_count(store, key)
    if own >= 2 and looks_like_english(key):
        return None         # 何度も書いている語＝正しい

    # **同じ文字の2連続を1つに畳む**（うにさんの指定・項目48-AX）。
    #
    # うにさん:「同一キーの2連続というのは、実際ほぼないタイプミス
    # のはずです。とはいえ隣接キーミスとも考えにくい。やはり2連続を
    # 1回にまとめる補正でよいでしょう」
    #
    # **これは別種の打ち間違い**（キーが2回入った）なので、
    # 一般の編集距離より先に、名指しで解く。距離に任せると
    # 複数形と同点になって手を引いてしまう:
    #
    #     planetariumm → planetarium（mm を畳む・距離1）
    #                  → planetariums（m→s・距離1） ← 同点で止まる
    #
    # ここへ来ている時点で `key` は辞書にない（上の門を抜けている）
    # ので、letter・mall・occurred のような二重字の正しい語は
    # 畳まれない。畳んだ先が1つに決まるときだけ採る。
    _folded = {key[:i] + key[i + 1:]
               for i in range(1, len(key))
               if key[i] == key[i - 1]}
    _hit = sorted(w for w in _folded
                  if w in vocab and not _same_word_family(key, w))
    if len(_hit) == 1:
        return _match_case(vocab[_hit[0]], word)
    # **回数だけでは「正しい」と認めない。**
    # 誤字を含む例をメモに並べていると、その誤字の回数が正しい形を
    # 上回る。実機では `Plaqnetarium` が65回・`Planetarium` が9回で、
    # 誤字のほうが「何度も書いている語」として素通りしていた
    # （メモに「以下は Planetarium に自動補正します」と書いてあるのに
    # 　直らない・2026-08-10）。英語の綴りとして無理がある形は、
    # 何度書かれていてもこの近道を通さない。
    # 一度しか見ていない語は、**もっとよく書いている1文字違いの語**が
    # あれば、そちらの打ち間違いとみなす。誤字を先に覚えてしまった
    # ときの逃げ道（覚える側でも弾いているが、順番によっては
    # 誤字のほうが先に入りうる）。
    _override = own == 1

    budget = allowed_edits(len(key))
    best = None
    second = None
    index = _indexed(store, '_english_index_cache', vocab)
    learned = _english_vocabulary(store)
    for known in _distance1_candidates(key, vocab, index):
        if known == key:
            continue
        if abs(len(known) - len(key)) > budget:
            continue
        # 総当たりの前に、表を作らない関門で間引く（項目48-BC）
        if not within_one_edit(key, known):
            continue
        # **打ち間違い／綴り間違いとして説明が付かない相手は、
        # そもそも候補にしない**（項目48-BJ）。カタカナ側と同じ
        # 置き方（届かない相手は同点の相手にもならない・学び47）。
        if (known in _english_seed() and known not in learned
                and not typo_explains_seed_english(key, known)):
            continue
        if not looks_like_english(known):
            # **英語らしくない綴りは、他の語を直す側になれない。**
            # 回数だけで代表形を決めると、メモに誤字のほうが多いとき
            # 誤字が唯一の正解になり、正しく書いた語がそちらへ
            # 直されてしまう（Planetarium → Plaqnetarium・2026-08-10）。
            # 直される側には使わない判定なので、ここで落としても
            # 「直せない語が増える」だけで、書いた文字は壊れない。
            continue
        # **回数の歯止め（_override）は、ここでは掛けない**
        # （2026-08-11・項目48-AN）。近さで並べ終わってから、
        # 勝った語にだけ掛ける。**候補を先に間引くと、
        # 「どちらとも決められない」が「決まった」に化ける。**
        #   Panetarium → lanetarium(3回・距離1)
        #                planetarium(2回・距離1)
        # 正しくは同点＝触らない。ところが回数で先に間引くと
        # planetarium が消え、誤字のほうが唯一の答えとして残っていた。
        # 検証レポート 2-A は「own == 0 にも回数の歯止めを」と言うが、
        # **それはできない**。実測すると、うにさんの語彙でも
        # テストの材料でも `planetarium` は1回しか記録されない
        # （`relearn_english_from_texts` は同じ綴りを数え上げない）。
        # 置き換え先に2回以上を求めると、うにさん指定の
        # `Palnetarium → Planetarium` が通らなくなる。
        # 代わりに、実際に出ていた誤爆の形（語尾違い）を下で断つ。
        if _same_word_family(key, known):
            # 語尾だけが違う形は、打ち間違いではなく**別の形**
            # （検証レポート 2-A / 2-F）。
            #   change → changed / window → Windows /
            #   detail → details / button → buttons /
            #   callouts → callout / languages → Language /
            #   receives → received
            # 英単語の辞書は持たない方針なので、単数複数や時制を
            # 正しく判断する材料は無い。**判断が付かないものは
            # 直さない**（設計原則3）。
            continue
        d = edit_distance(key, known, limit=budget)
        if d > budget:
            continue
        if best is None or d < best[0]:
            second = best
            best = (d, known)
        elif second is None or d < second[0]:
            second = (d, known)
    if best is None:
        return None
    if second is not None and second[0] == best[0]:
        return None
    if _override and _english_count(store, best[1]) < 2:
        # 一度しか書いていない語を上書きしてよいのは、
        # **二度以上書いている語**だけ（歯止めは勝った語に掛ける）。
        #
        # ★★ もとは `< 3`（「よく書いている語」）だった。回数の記録を
        # やめた（項目48-QG）ので `_english_count` は 1 か 2 しか返さず、
        # `< 3` は**恒買＝この近道が丸ごと死ぬ**。意図（一度きりの語で
        # 上書きさせない）をそのまま残すには `< 2`＝**立っている語か**
        # に読み替えるのが素直。`_override` の側も `own == 1`＝
        # **立っていない**という同じ2値なので、対になっている。
        return None
    # **頭だけ大文字の語は、1文字の置き換えだけの直しをしない**
    # （2026-08-16・実機で `Claude → Clause` と壊した）。
    # 頭だけ大文字で辞書に無い語は固有名詞であることが多く、
    # 隣接キーの置き換え1つで辞書の語に届いてしまう
    # （d と s は隣）。うにさんの見本にある大文字語の誤字は
    # すべて **重複・脱落・挿入・記号**（Pllanetarium・
    # Panetarium・Pklanetarium・P:lanetarium）で、置き換えは
    # 1つも無い。形で分けられるので、置き換えだけの直しを
    # 固有名詞の側に倒す（`Planetarjum` のような置き換え誤字は
    # 直らなくなるが、書いた固有名詞を壊すよりよい）。
    _target = best[1]
    if (word[:1].isupper() and word[1:].islower()
            and len(key) == len(_target)
            and sum(1 for a, b in zip(key, _target) if a != b) == 1):
        return None
    return _match_case(vocab[best[1]], word)


def _match_case(surface, word):
    """
    **書いた人の大文字小文字に合わせる**（項目48-BA）。

    種の単語リスト（SCOWL）は全部小文字なので、そのまま返すと
    `Plaqnetarium` が `planetarium` に化けて、**誤字は直るのに
    大文字が壊れる**。覚えた語の表記が優先で、種から来たときだけ
    元の形をなぞる。
    """
    if surface.islower() and not word.islower():
        if word.isupper():
            surface = surface.upper()
        elif word[:1].isupper():
            surface = surface[:1].upper() + surface[1:]
    return surface if surface != word else None


# **かなのキーを打ってしまって、英字の並びに紛れた記号**
# （項目48-EB・2026-08-16）。うにさんの見本:
#
#     P:lanetarium ／ Pl:anetarium  → Planetarium
#
# ここに挙げるのは、うにさん自身が対応表に書いた
# **かなのキーの記号**（`: ⇒ け` `; ⇒ れ` `@ ⇒ ゛` `[ ⇒ ゜`
# `] ⇒ む` `^ ⇒ へ` `\ ⇒ ー/ろ` `, ⇒ ね`）だけ。
#
# **`. - _ /` は入れない。** これらは識別子・URL・パスの区切りで、
# 入れると `looks_like` を `lookalike` に直してしまう
# （実機メモ tab0 244行で実測）。`_GLUED_SYMBOLS` が
# 「くっついていたら英単語として扱わない」ために持っている記号と、
# ここは**役割が逆**なので、表を分けてある。
_MISKEY_SYMBOLS = ':;@[]^\\,'

_GLUED_ENGLISH_RE = re.compile(
    r'([A-Za-z]+)([' + re.escape(':;@[]^\\,') + r'])([A-Za-z]+)')


def known_english_spelling(word, store):
    """
    その綴りを**正しい英単語として知っている**なら、覚えている表記を返す。

    `fix_english_word` は「正しく書けている語」に None を返すので、
    「正しいと知っているか」を聞くにはこちらを使う。
    """
    if not word or not word.isalpha():
        return None
    if len(word) < MIN_ENGLISH_LENGTH:
        return None
    key = word.lower()
    if key not in _english_seed_all() and _english_count(store, key) < 2:
        return None
    known = _english_targets(store).get(key) or word
    # **大文字小文字の違いは誤字ではない**（`fix_english_word` と
    # 同じ扱い）。綴りが同じで大小だけ違うなら、**書いた人の形**を
    # 残す。種の表は小文字なので、ここを入れないと
    # `P:lanetarium` が `planetarium` になって頭文字が落ちる。
    if known.lower() == word.lower():
        return word
    return known


_ACRONYM_RE = None

# 略語の種（項目48-LW・AI の判断で書き下した閉じた名簿・2026-08-30）。
# 英語の学びは6字からなので、よく使う短い略語の**正しい綴り**を
# ここで持つ（直し先にも「触らない側」にも使う）。増やすのは測ってから。
_ACRONYM_SEED = ('URL', 'IME', 'API', 'PDF', 'CSV', 'PNG', 'JSON',
                 'HTML', 'CPU', 'EXE')


def find_miskeyed_acronym(line, store):
    """
    **大文字だけの略語の打ち違い**（項目48-LW・2026-08-30 21回目）。

        YRLは → URLは   （Y と U は QWERTY の隣）

    英語の道の下限（MIN_ENGLISH_LENGTH=6）には届かない短い略語を、
    狭い門で直す:
      - **大文字3〜5字だけ**の並びで、前後に英数字が続かない
      - そのままでは知らない綴り（種にも本人の控えにも無い）
      - **1字だけ隣のキー（QWERTY）に替える**と、本人が書いてきた
        既知の略語（英語の控えに実績2以上・大文字表記）になる
      - 直し先が**ただ1つ**（2つ以上は紛れ＝触らない）

    戻り値: [(開始, 終了, 直した表記), ...]
    """
    global _ACRONYM_RE
    if _ACRONYM_RE is None:
        import re as _re
        _ACRONYM_RE = _re.compile(r'[A-Z]{3,5}')
    out = []
    vocab = _english_targets(store)
    if not vocab:
        return out
    seeds = _english_seed_all()
    for m in _ACRONYM_RE.finditer(line):
        s, e = m.start(), m.end()
        # 境目は**半角の英数字**だけを見る（`は` も isalnum() が真に
        # なるので、Unicode で見ると YRLは が弾かれる・実測）
        if s > 0 and line[s - 1].isascii() and line[s - 1].isalnum():
            continue
        if e < len(line) and line[e].isascii() and line[e].isalnum():
            continue
        word = m.group(0)
        key = word.lower()
        if word in _ACRONYM_SEED or key in seeds \
                or _english_count(store, key) >= 1:
            continue        # 知っている綴りは正しい。触らない
        hits = set()
        for i, ch in enumerate(key):
            for alt in _QWERTY_POS:
                if not _qwerty_near(ch, alt):
                    continue
                cand = key[:i] + alt + key[i + 1:]
                if cand == key:
                    continue
                # 直し先: 略語の種、または本人の控えの大文字の略語
                # （実績2以上）
                if cand.upper() in _ACRONYM_SEED:
                    hits.add(cand.upper())
                    continue
                if cand in vocab and _english_count(store, cand) >= 2:
                    surface = vocab[cand]
                    if surface == surface.upper():
                        hits.add(surface)
        if len(hits) == 1:
            out.append((s, e, next(iter(hits))))
    return out


def find_miskeyed_english(line, store):
    """
    英字の並びに**かなのキーの記号**が紛れた形を見つけて直す。

        P:lanetarium → Planetarium   （`:` を抜くと知っている語）

    記号を抜いた綴りが**正しい英単語として知られている**か、
    `fix_english_word` で直せるときだけ返す。
    `C:\\Users` `key:value` は抜いても語にならないので通らない。

    戻り値: [(開始, 終了, 直した表記), ...]
    """
    out = []
    for m in _GLUED_ENGLISH_RE.finditer(line):
        left, _sym, right = m.groups()
        merged = left + right
        if len(merged) < MIN_ENGLISH_LENGTH:
            continue
        fixed = known_english_spelling(merged, store)
        if not fixed:
            fixed = fix_english_word(merged, store)
        if fixed:
            out.append((m.start(), m.end(), fixed))
    return out


def katakana_for_hiragana_typo(reading, store, min_length=MIN_LENGTH):
    """
    ひらがなで書いた外来語の**打ち間違い**を、カタカナの表記へ直す。

        かーそね → カーソル   （る と ね は かな入力で隣のキー）

    `katakana_for_hiragana`（そのまま変換する道）と**同じ門**を通す。
    とくに大事なのが `_has_non_katakana_surface`:

    **書かれているかなが、語彙で漢字やひらがなの表記を持っているなら、
    それは正しく書けている語**なので触らない。この門が無いと、
    同じ行にカタカナ語があるだけで正しい語が壊れる（2026-08-16 に
    実測。語彙から作った「危ない組」で、4文字まで下げたときの
    誤検知31件が**すべてこの形**だった）:

        かめい（仮名 564回）→ カメラ    ／ きろく（記録 114回）→ キック
        はんたい（反対 17回）→ ハンター ／ しょもつ（書物 25回）→ ショーツ

    門を揃えると、長さの下限は**危険を測る代理でしかなくなる**。
    """
    if not reading or len(reading) < min_length:
        return None
    if not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in reading):
        return None
    # **そのままで正しく書けている語なら触らない。**
    # `katakana_for_hiragana` が持っている門を、こちらにも置く。
    if _has_non_katakana_surface(store, reading):
        return None
    fixed = fix_katakana_word(hiragana_to_katakana(reading), store,
                              min_length=min_length)
    if not fixed:
        return None
    # **語の頭は動かさない**（2026-08-16 に踏んだ）。
    #
    #     ドラッグとどらっぐ → ドラッグ**ドラッグ**
    #
    # かなの連続 `とどらっぐ` の頭の `と`（助詞）を1文字消して
    # `ドラッグ` に当てていた。**助詞を食う**形（項目48-DJ と同じ）。
    #
    # 頭の1文字が保たれることだけを求める。`かーそね → カーソル` は
    # か→カ で保たれるので通り、`とどらっぐ → ドラッグ` は と→ド で
    # 変わるので落ちる。
    if hiragana_to_katakana(reading)[0] != fixed[0]:
        return None
    # **語の尻も食わない**（項目48-LP・2026-08-30 に踏んだ）。
    #
    #     すくろーるご → スクロール    （末尾の ご ＝ 語/後 の読み）
    #     たぶい       → タブ          （末尾の い ＝ 移動 の頭）
    #
    # 末尾の1字を**削って**当てる形は、48-LC で禁じた「縁の削除は
    # 語の切り詰め」と同じ手——消した字が次の語（接尾・送り仮名）
    # だったとき、その語ごと失われる。
    #
    # 削ってよい尻は、**日本語の語の頭に立てない字**（ん・ー・小書き）
    # だけ。それらは次の語の頭ではありえないので、余分な打鍵と
    # 言い切れる（`かーそるん → カーソル` は今までどおり直る）。
    # `かーそね → カーソル` は ね→ル の**置換**で長さが保たれるので
    # この門は関係なく通る。
    if reading[-1] not in 'んーゃゅょぁぃぅぇぉっ' \
            and hiragana_to_katakana(reading[:-1]) == fixed:
        return None
    return fixed


def find_english_runs(line, min_len=MIN_ENGLISH_LENGTH):
    """
    英字だけの並びを取り出す。

    前後に数字や記号（. _ - @ /）がくっついているものは、
    識別子・版番号・URL とみなして対象にしない。

    戻り値: [(開始, 終了, 並び), ...]
    """
    runs = []
    for m in _ENGLISH_RE.finditer(line):
        word = m.group(0)
        if len(word) < min_len:
            continue
        s, e = m.start(), m.end()
        if s > 0 and (line[s - 1].isdigit() or line[s - 1] in _GLUED_SYMBOLS):
            continue
        if e < len(line) and (line[e].isdigit() or line[e] in _GLUED_SYMBOLS):
            continue
        runs.append((s, e, word))
    return runs
