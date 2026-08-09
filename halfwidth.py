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
半角入力モードで打ってしまった文字列を、かなに戻す。

かな入力の人が日本語入力をオフのまま打つと、
キーに割り当てられたかなではなく半角文字がそのまま入る。
  「もじにゅうりょく」と打ったつもりが → 「md@i(4l)h」

このモジュールは、その半角文字列を
JISかな配列の対応に従ってかなに戻す。

戻したものが意味の通るかなになっていれば、
それは半角モードのまま打ってしまった誤りだと判断できる。
"""

# ============================================================
# JISかな配列: 半角文字 -> かな
# ============================================================
# kana_layout.py の KANA_POSITIONS と同じ配列を、
# 半角文字側から引けるようにしたもの。
#
#  数字段: 1  2  3  4  5  6  7  8  9  0  -  ^  \
#          ぬ ふ あ う え お や ゆ よ わ ほ へ ろ
#  上段:   Q  W  E  R  T  Y  U  I  O  P  @  [
#          た て い す か ん な に ら せ ゛ ゜
#  中段:   A  S  D  F  G  H  J  K  L  ;  :  ]
#          ち と し は き く ま の り れ け む
#  下段:   Z  X  C  V  B  N  M  ,  .  /  _
#          つ さ そ ひ こ み も ね る め ろ

HALFWIDTH_TO_KANA = {
    # --- 数字段 ---
    '1': 'ぬ', '2': 'ふ', '3': 'あ', '4': 'う', '5': 'え',
    '6': 'お', '7': 'や', '8': 'ゆ', '9': 'よ', '0': 'わ',
    '-': 'ほ', '^': 'へ', '\\': 'ろ',
    # --- 上段 ---
    'q': 'た', 'w': 'て', 'e': 'い', 'r': 'す', 't': 'か',
    'y': 'ん', 'u': 'な', 'i': 'に', 'o': 'ら', 'p': 'せ',
    '@': '゛', '[': '゜',
    # --- 中段 ---
    'a': 'ち', 's': 'と', 'd': 'し', 'f': 'は', 'g': 'き',
    'h': 'く', 'j': 'ま', 'k': 'の', 'l': 'り', ';': 'れ',
    ':': 'け', ']': 'む',
    # --- 下段 ---
    'z': 'つ', 'x': 'さ', 'c': 'そ', 'v': 'ひ', 'b': 'こ',
    'n': 'み', 'm': 'も', ',': 'ね', '.': 'る', '/': 'め',
    '_': 'ろ',
}

# Shift を押しながら打ったときの対応（小書きかな・記号）。
# 半角では Shift + キー で別の文字が入る。
SHIFT_TO_KANA = {
    '#': 'ぁ', '$': 'ぅ', '%': 'ぇ', '&': 'ぉ',
    "'": 'ゃ', '(': 'ゅ', ')': 'ょ',
    'E': 'ぃ', 'Z': 'っ',
    '"': 'ふ',      # Shift+2
    '!': 'ぬ',      # Shift+1
    '=': 'ほ', '~': 'へ',
    '<': '、', '>': '。', '?': 'め',
    '*': 'や',      # Shift+7 相当（環境により異なる）
    '{': 'む', '}': 'ー',
    '|': 'ー',
    '+': 'れ',
}


def halfwidth_to_kana(text):
    """
    半角文字列を、JISかな配列の対応でかなに変換する。

    変換できない文字（かなに割り当てのない記号や全角文字）は
    そのまま残す。呼び出し側で「どれくらい変換できたか」を見て
    半角入力かどうかを判断する。

    戻り値: (変換後の文字列, 変換できた文字数, 対象だった文字数)
    """
    if not text:
        return '', 0, 0

    out = []
    converted = 0
    target = 0

    for ch in text:
        # 空白・改行はそのまま
        if ch in ' \t\n':
            out.append(ch)
            continue
        target += 1
        kana = SHIFT_TO_KANA.get(ch)
        if kana is None:
            kana = HALFWIDTH_TO_KANA.get(ch.lower() if ch.isalpha() else ch)
        if kana is None:
            out.append(ch)
            continue
        out.append(kana)
        converted += 1

    return ''.join(out), converted, target


def looks_like_halfwidth_input(text, min_len=4):
    """
    この文字列は「半角モードのまま打ってしまったかな」に見えるか。

    ここでは形だけを見る（長さ・文字種）。
    「変換できるかどうか」では判断できない点に注意。
    ラテン文字はどんな並びでもかなに変換できてしまうため、
    「Python」も「hello」も変換自体は成功してしまう。

    本当に半角入力の誤りかどうかは、
    変換した結果が意味の通る語になっているかで決まる。
    その判定は語彙を参照する必要があるので correct_halfwidth() で行う。
    """
    if not text or len(text) < min_len:
        return False

    # 日本語を含む場合は、半角モードの打ち間違いではなく
    # 意図した半角混じりの文章とみなす
    for ch in text:
        if '\u3041' <= ch <= '\u30f6' or '\u4e00' <= ch <= '\u9fff':
            return False

    # 大文字が混じる場合は意図した英単語の可能性がある。
    # ただし、かな入力では小書きかな（っ ゃ ゅ ょ）を打つのに
    # Shift を使うため、その分の大文字は正当なものとして数えない。
    # 「くりっくでもどす」を打つと Z（＝っ）が何度も現れる。
    SHIFT_KANA_KEYS = set('ZEAIUO')
    upper_others = sum(1 for ch in text
                       if ch.isupper() and ch not in SHIFT_KANA_KEYS)
    if upper_others >= 2:
        return False

    # 「大文字1字＋小文字2字以上」の並びを含むのは、意図して打った
    # 英単語（Shift, Ctrl, Python 等）。大文字が1つしか無いため
    # 上の条件では止まらず、「Shift+=」がかなに化けて
    # 「特にはかれほ」になる誤爆が実機で起きた。
    # 先頭だけを見ると「(Shift」のように記号を伴った途端に
    # 見逃す（実機で発生）ので、文字列のどこにあっても止める。
    # かな入力の小書き（Shift+キー）で大文字が入る場合、直後も
    # Shift由来の大文字か記号になるのが普通で、小文字が2つ
    # 続くことはまず無い。
    # 小書きかな用の Shift キー（Z E A I U O）は例外
    # （「くりっく」の っ は Z として入るため）。
    for i in range(len(text) - 2):
        if (text[i].isupper() and text[i] not in SHIFT_KANA_KEYS
                and text[i + 1].islower() and text[i + 2].islower()):
            return False

    # コードの断片は変換しない。
    # 技術メモには `_looks_like_valid_japanese` や
    # `kana_layout.nearby_candidates()` のような識別子が現れる。
    # 語彙が育つと makes_sense_as_japanese が「かなに戻すと
    # 説明できてしまう」ようになり（何にでも一致する短い語が
    # 増えるため。学び12と同根）、識別子が丸ごとかなに化ける
    # 誤爆が実機で起きた。意味の判定に頼る前に、形で止める:
    #   - バッククォートを含む（Markdown のコード引用）
    #   - 英字が「_」「.」で繋がれている（snake_case / メソッド呼び出し）。
    #     ただし「@」（かな入力の濁点キー）を含む場合は除く。
    #     かなを半角のまま打った列には濁点の @ がほぼ必ず混ざる一方、
    #     コードの識別子に @ が入ることはまず無いので、これで
    #     「hd(4r.bsw@」（かな打ち）と「kana_layout.nearby」（コード）
    #     を見分けられる。
    if '`' in text:
        return False
    # 引用符で始まって英字が続くのは文字列リテラル（'corrected' 等）。
    # かな入力で「ゃ」（'）を語頭に打つことは無いので安全に断れる。
    if len(text) >= 2 and text[0] in '\'"' and text[1].isalpha():
        return False
    if '@' not in text:
        for i in range(1, len(text) - 1):
            if text[i] in '_.' and text[i - 1].isalpha() \
                    and text[i + 1].isalpha():
                return False

    # 小文字の英字だけでできた文字列（ctypes, hover 等）も変換しない。
    # かなを半角のまま打つと、母音（あうえお＝数字段）や濁点（@）
    # などの記号・数字がほぼ必ず混ざるため、英字だけの並びが
    # かな入力の誤りであることはまず無い。ローマ字のべた打ち
    # （tanjonoturagari）は correct_romaji 側が引き受けるので、
    # ここで断っても取りこぼしにはならない。
    if text.isalpha():
        return False

    # 英文の断片（response, / bytes). / innuendo; / sex-related）。
    # 前後の句読点・括弧を剥がした中身が英字（とハイフン）だけなら、
    # 意図した英語とみなす。かなを半角のまま打った列には、母音の
    # 数字や濁点の @ などがほぼ必ず**中に**混ざるため、
    # 「英字だけ＋末尾の句読点」がかな入力の誤りであることはまず無い
    # （実機で英文のメモが丸ごとかなに化けた: response,→す意図せらみ
    # トイ根 等）。
    core_en = text.strip('.,;:!?()[]"\'')
    if core_en and all(ch.isalpha() or ch == '-' for ch in core_en):
        return False

    _, n_conv, n_target = halfwidth_to_kana(text)
    if n_target == 0:
        return False

    # 数式・記号の並び（「/*-0.3」「1+2*3」など）は、
    # かなを半角のまま打った誤りではなく、意図して打った式である。
    # かな配列では数字キーにもかなが割り当たっているため
    # （0→わ、3→あ、-→ほ、.→る）、そのまま変換をかけると
    # 意味の無いかな列に化けてしまう
    # （実機で「/*-0.3」が「/*+03」になると報告された）。
    #
    # 数字と演算記号だけでできている文字列は、日本語の入力ミス
    # ではあり得ないので、はっきり対象から外す。
    if all(ch.isdigit() or ch in '+-*/=.,()%^ ' for ch in text):
        return False

    # ほぼ全ての文字がかなキーに対応していること
    return (n_conv / n_target) >= 0.9


# かな配列で日本語を打つときに使う記号キー。
# 濁点・半濁点・小書きかな・長音などがここに含まれるため、
# 日本語を半角で打つとこれらがほぼ必ず混じる。
SYMBOL_KEYS = set('@[]:;,./\\^-()#$%&\'"!<>?_{}|+=*~')


def correct_halfwidth(text, store, find_readings, max_dist=1.6):
    """
    半角モードのまま打ってしまった文字列を、かなに戻して補正する。

    変換しただけでは「Python」のような意図した英単語まで
    かなに変えてしまうので、変換後の文字列が
    語彙にある語として意味を成すことを確認してから採用する。

    戻り値: 補正後のかな文字列。半角入力でないと判断したら None。
    """
    if not looks_like_halfwidth_input(text):
        return None

    # 数字と数の区切り記号だけの並びは、数値・電話番号・版数
    # （03-6230-9666・3.0・12/25）。かな配列でも打ててしまう形
    # （0=わ・.=る 等）だが、数字だけの並びが「半角のまま打った
    # 日本語」であることはまず無い。方針「数字・記号・英字を含む
    # 範囲は触らない」の数字版の関門（実機で電話番号が
    # 「けわあほオフ…」に化けた・2026-08-09）。
    if all(ch in '0123456789.,-:/()%+ ' for ch in text):
        return None

    kana, _, _ = halfwidth_to_kana(text)
    try:
        from morphology import normalize_marks
        kana = normalize_marks(kana)
    except Exception:
        pass

    if not kana:
        return None

    # --- 採用の判断 ---
    # かな配列で日本語を打つと、濁点「@」小書き「(」長音「\\」など
    # 記号キーがほぼ必ず混じる。これは「日本語を半角で打った」ことを
    # 示す手がかりになる。
    #
    # ただし記号の有無だけでは判断できない。
    # コードやURL（foo.bar()、http://... など）も記号を多く含むためで、
    # これらをかなに変換してしまうと大きな害になる。
    #
    # そこで記号は補助的な材料とし、
    # 「かなに戻したものが日本語として読めるか」を主な根拠にする。
    # 記号が混じっている場合は、日本語である可能性が高い分、
    # やや緩めのしきい値で判定する。
    has_symbol = any(ch in SYMBOL_KEYS for ch in text)
    min_ratio = 0.4 if has_symbol else 0.6

    if makes_sense_as_japanese(kana, store, min_ratio=min_ratio):
        # 半角モードでは日本語入力（IME）を一度も経由していないため、
        # 「ひらがなのまま入力した」という意図を読み取れない。
        # そこで語彙にある表記が分かる範囲で漢字・カタカナに変換する
        # （もじにゅうりょく → 文字入力）。
        return kana_to_kanji_where_possible(kana, store)

    # --- 訂正を伴う場合 ---
    # 半角モードでも隣のキーを押し間違えるので、
    # かなに戻した後の誤字も直せるようにする
    # （md[ki)4l)h → もじのにょうりょく → もじにゅうりょく）。
    # ただし英単語が偶然かなの語に化ける危険があるため、
    # 訂正後も「日本語として意味が通る」ことを必ず確かめる。
    #
    # 4〜5文字の短い語（「ふれろむ」→「ふれーむ」等、外来語の
    # 長音を隣接キーと打ち間違えたような場合）は、6文字未満だと
    # 一律に対象外にしていたため訂正の機会が無かった
    # （実機で「半角入力の再変換候補にカタカナの補正が入らない。
    #   2;\\] ⇒ フレーム」と報告された）。
    # 短い語では誤爆のリスクが上がる分、訂正数を1箇所までに絞り、
    # 一致の質もより厳しく見ることでバランスを取る。
    if len(kana) < 4:
        return None
    short = len(kana) < 6
    max_e = 1 if short else 3
    found = find_readings(kana, store, max_dist=max_dist, max_edits=max_e)
    for cand_reading, cost, edits in found:
        # 訂正が多すぎるものは、たまたま似た語に届いただけなので除く
        if edits > 0 and cost / edits > 1.35:
            continue
        if short and edits > 1:
            continue
        # 長さが大きく変わるものも、別の語に化けている可能性が高い
        if abs(len(cand_reading) - len(kana)) > 1:
            continue
        if makes_sense_as_japanese(cand_reading, store):
            return kana_to_kanji_where_possible(cand_reading, store)

    return None


# ============================================================
# ローマ字入力への対応
# ============================================================
# ローマ字入力の人が半角モードのまま打つと、
# ローマ字がそのまま残る（「mojinonyuuryoku」など）。
# これをかなに直して補正できるようにする。

# ローマ字 -> かな。長いものから照合する必要があるため、
# 変換時に長さ順で試す。
ROMAJI_TO_KANA = {
    # --- 3文字（拗音） ---
    'kya': 'きゃ', 'kyu': 'きゅ', 'kyo': 'きょ',
    'sha': 'しゃ', 'shu': 'しゅ', 'sho': 'しょ',
    'sya': 'しゃ', 'syu': 'しゅ', 'syo': 'しょ',
    'cha': 'ちゃ', 'chu': 'ちゅ', 'cho': 'ちょ',
    'tya': 'ちゃ', 'tyu': 'ちゅ', 'tyo': 'ちょ',
    'nya': 'にゃ', 'nyu': 'にゅ', 'nyo': 'にょ',
    'hya': 'ひゃ', 'hyu': 'ひゅ', 'hyo': 'ひょ',
    'mya': 'みゃ', 'myu': 'みゅ', 'myo': 'みょ',
    'rya': 'りゃ', 'ryu': 'りゅ', 'ryo': 'りょ',
    'gya': 'ぎゃ', 'gyu': 'ぎゅ', 'gyo': 'ぎょ',
    'jya': 'じゃ', 'jyu': 'じゅ', 'jyo': 'じょ',
    'zya': 'じゃ', 'zyu': 'じゅ', 'zyo': 'じょ',
    'bya': 'びゃ', 'byu': 'びゅ', 'byo': 'びょ',
    'pya': 'ぴゃ', 'pyu': 'ぴゅ', 'pyo': 'ぴょ',
    'dya': 'ぢゃ', 'dyu': 'ぢゅ', 'dyo': 'ぢょ',
    'tsu': 'つ', 'chi': 'ち', 'shi': 'し',
    # --- 2文字 ---
    'ka': 'か', 'ki': 'き', 'ku': 'く', 'ke': 'け', 'ko': 'こ',
    'sa': 'さ', 'si': 'し', 'su': 'す', 'se': 'せ', 'so': 'そ',
    'ta': 'た', 'ti': 'ち', 'tu': 'つ', 'te': 'て', 'to': 'と',
    'na': 'な', 'ni': 'に', 'nu': 'ぬ', 'ne': 'ね', 'no': 'の',
    'ha': 'は', 'hi': 'ひ', 'hu': 'ふ', 'fu': 'ふ', 'he': 'へ', 'ho': 'ほ',
    'ma': 'ま', 'mi': 'み', 'mu': 'む', 'me': 'め', 'mo': 'も',
    'ya': 'や', 'yu': 'ゆ', 'yo': 'よ',
    'ra': 'ら', 'ri': 'り', 'ru': 'る', 're': 'れ', 'ro': 'ろ',
    'wa': 'わ', 'wo': 'を', 'nn': 'ん',
    'ga': 'が', 'gi': 'ぎ', 'gu': 'ぐ', 'ge': 'げ', 'go': 'ご',
    'za': 'ざ', 'zi': 'じ', 'ji': 'じ', 'zu': 'ず', 'ze': 'ぜ', 'zo': 'ぞ',
    'da': 'だ', 'di': 'ぢ', 'du': 'づ', 'de': 'で', 'do': 'ど',
    'ba': 'ば', 'bi': 'び', 'bu': 'ぶ', 'be': 'べ', 'bo': 'ぼ',
    'pa': 'ぱ', 'pi': 'ぴ', 'pu': 'ぷ', 'pe': 'ぺ', 'po': 'ぽ',
    'la': 'ぁ', 'li': 'ぃ', 'lu': 'ぅ', 'le': 'ぇ', 'lo': 'ぉ',
    'xa': 'ぁ', 'xi': 'ぃ', 'xu': 'ぅ', 'xe': 'ぇ', 'xo': 'ぉ',
    # --- 1文字（母音・ん） ---
    'a': 'あ', 'i': 'い', 'u': 'う', 'e': 'え', 'o': 'お',
    'n': 'ん', '-': 'ー',
}

_ROMAJI_KEYS = sorted(ROMAJI_TO_KANA, key=len, reverse=True)


def romaji_to_kana(text):
    """
    ローマ字をかなに変換する。

    「っ」（促音）は子音の重なりで表されるので、
    同じ子音が続いたら「っ」に置き換える。
      「gakkou」→「がっこう」

    戻り値: (変換後の文字列, 変換できた文字数, 対象だった文字数)
    """
    if not text:
        return '', 0, 0

    s = text.lower()
    out = []
    i = 0
    n = len(s)
    converted = 0
    target = 0

    while i < n:
        ch = s[i]
        if ch in ' \t\n':
            out.append(ch)
            i += 1
            continue
        target += 1

        # 促音: 同じ子音が2つ続く（ただし n は「ん」なので除く）
        if (i + 1 < n and ch == s[i + 1] and ch.isalpha()
                and ch not in 'aiueon'):
            out.append('っ')
            converted += 1
            i += 1
            continue

        # 長いローマ字から順に照合する
        matched = False
        for key in _ROMAJI_KEYS:
            if s.startswith(key, i):
                out.append(ROMAJI_TO_KANA[key])
                converted += 1
                # 2文字目以降も「対象だった文字」として数える
                target += len(key) - 1
                i += len(key)
                matched = True
                break
        if matched:
            continue

        out.append(ch)
        i += 1

    return ''.join(out), converted, target


def correct_romaji(text, store, find_readings, max_dist=1.6, min_len=4):
    """
    ローマ字のまま打ってしまった文字列を、かなに戻して補正する。

    半角かな入力の場合と同じく、変換しただけでは
    英単語まで変換してしまうので、
    変換結果が語彙にある語として意味を成すことを確認してから採用する。

    戻り値: 補正後のかな文字列。ローマ字入力でないと判断したら None。
    """
    if not text or len(text) < min_len:
        return None
    # 日本語を含むなら、意図した半角混じりの文章
    for ch in text:
        if '\u3041' <= ch <= '\u30f6' or '\u4e00' <= ch <= '\u9fff':
            return None
    # 大文字が多いものは意図した英単語・略語
    if sum(1 for ch in text if ch.isupper()) >= 2:
        return None
    # 「大文字1字＋小文字の続き」も意図した英単語（Amazon・Python）。
    # かな配列の判定（looks_like_halfwidth_input）と同じ理屈。
    # ローマ字のべた打ちは Shift を使う理由が無いので、頭が大文字の
    # 列を対象から外しても取りこぼしにはならない
    # （実機で Amazon が アマゾン に化けた・2026-08-09）。
    if len(text) >= 3 and text[0].isupper() and text[1:].islower():
        return None
    # ローマ字は英字だけで構成される
    if not all(ch.isalpha() or ch == '-' for ch in text):
        return None

    kana, n_conv, n_target = romaji_to_kana(text)
    if n_target == 0 or not kana:
        return None
    # ほとんどがかなに変換できていること
    if not all('\u3041' <= c <= '\u3096' or c == 'ー' for c in kana):
        return None

    # 短い英単語はローマ字としても読めてしまう（more→もれ→漏れ、
    # sake→さけ 等）。かなに戻して4文字未満にしかならない列は、
    # 偶然の一致とみなして触らない（実機で英文の more が 漏れ に
    # 化けた）。かな入力の取りこぼしにはならない: べた打ちの報告例は
    # いずれも語＋助詞の長い列（tanjonoturagari 等）。
    if len(kana) < 4:
        return None
    entries = [e for e in store.lookup(kana) if e['count'] >= 2]
    if entries or makes_sense_as_japanese(kana, store):
        return kana_to_kanji_where_possible(kana, store)

    # 訂正を伴う場合は、英単語が偶然かなの語に化けないよう厳しくする
    if len(kana) < 6:
        return None
    found = find_readings(kana, store, max_dist=max_dist, max_edits=3)
    for cand_reading, cost, edits in found:
        if edits > 0 and cost / edits > 1.35:
            continue
        if abs(len(cand_reading) - len(kana)) > 1:
            continue
        if makes_sense_as_japanese(cand_reading, store):
            return kana_to_kanji_where_possible(cand_reading, store)

    return None


# ============================================================
# かな -> 半角（逆引き）
# ============================================================
# ローマ字入力のつもりでかな入力モードのまま打つと、
# ローマ字の各キーに割り当てられたかなが入ってしまう。
#   「mojinonyuuryoku」と打ったつもりが
#   → 「もらまにみらみんななすんらのな」
# キー配列を逆に引いて半角に戻し、ローマ字として読み直す。

KANA_TO_HALFWIDTH = {}
for _half, _kana in HALFWIDTH_TO_KANA.items():
    # 同じかなに複数のキーが対応する場合は先に出たほうを使う
    KANA_TO_HALFWIDTH.setdefault(_kana, _half)


def kana_to_halfwidth(text):
    """
    かな列を、JISかな配列の対応で半角文字に戻す。

    戻り値: (変換後の文字列, 変換できた文字数, 対象だった文字数)
    """
    if not text:
        return '', 0, 0
    out = []
    converted = 0
    target = 0
    for ch in text:
        if ch in ' \t\n':
            out.append(ch)
            continue
        target += 1
        half = KANA_TO_HALFWIDTH.get(ch)
        if half is None:
            out.append(ch)
            continue
        out.append(half)
        converted += 1
    return ''.join(out), converted, target


def correct_kana_typed_as_romaji(text, store, find_readings, max_dist=1.6,
                                 min_len=6):
    """
    ローマ字入力のつもりで、かな入力モードのまま打ってしまった文字列を直す。

    かなをキー配列で半角に戻し、それをローマ字として読み直す。
      「もらまにみらみんななすんらのな」
        → 半角に戻す → 「mojinonyuuryoku」
        → ローマ字として読む → 「もじにゅうりょく」

    普通のかな文を壊さないよう、
    「半角に戻したものがローマ字として読め、
      その結果が語彙にある語になる」ことを確認してから採用する。

    戻り値: 補正後のかな文字列。該当しなければ None。
    """
    if not text or len(text) < min_len:
        return None
    # ひらがなだけで構成されていること
    if not all('\u3041' <= c <= '\u3096' for c in text):
        return None

    half, n_conv, n_target = kana_to_halfwidth(text)
    if n_target == 0 or n_conv < n_target:
        return None      # 全ての文字がキーに対応していること

    # 半角に戻したものをローマ字として読む
    kana, r_conv, r_target = romaji_to_kana(half)
    if not kana or r_target == 0:
        return None
    # ローマ字として完全に読めること（読めない文字が残るなら別物）
    if not all('\u3041' <= c <= '\u3096' or c == 'ー' for c in kana):
        return None
    # 元の文字列と同じなら意味がない
    if kana == text:
        return None

    # 読み直した結果が、語彙にある語であること
    if [e for e in store.lookup(kana) if e['count'] >= 2] \
            or makes_sense_as_japanese(kana, store):
        return kana_to_kanji_where_possible(kana, store)

    found = find_readings(kana, store, max_dist=max_dist, max_edits=2)
    for cand_reading, cost, edits in found:
        if edits > 0 and cost / edits > 1.35:
            continue
        if abs(len(cand_reading) - len(kana)) > 1:
            continue
        if makes_sense_as_japanese(cand_reading, store):
            return kana_to_kanji_where_possible(cand_reading, store)

    return None


# ============================================================
# 全角で入ってしまった半角文字
# ============================================================

def zenkaku_to_hankaku(text):
    """
    全角の英数字・記号を半角に直す。

    かな入力モードで日本語変換がオンのまま打つと、
    半角文字が全角になって入ることがある。
      「md@i(4l)h」と打ったつもりが「ｍｄ＠い（４ｌ）ｈ」
    """
    out = []
    for ch in text:
        code = ord(ch)
        # 全角英数字・記号（！から～まで）
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif ch == '\u3000':      # 全角スペース
            out.append(' ')
        else:
            out.append(ch)
    return ''.join(out)


def has_zenkaku_ascii(text):
    """全角の英数字・記号を含むか。"""
    return any(0xFF01 <= ord(ch) <= 0xFF5E for ch in text)


# かな -> ローマ字（1文字かなの逆引き）
# 全角化された入力の中に、ローマ字として確定されたかなが
# 混ざることがあるため、それを半角に戻すのに使う。
KANA_TO_ROMAJI = {}
for _r, _k in sorted(ROMAJI_TO_KANA.items(), key=lambda x: len(x[0])):
    KANA_TO_ROMAJI.setdefault(_k, _r)


def normalize_zenkaku_input(text):
    """
    全角で入ってしまった入力を、半角の並びに戻す。

    かな入力モードで日本語変換をオンのまま打つと、
    打鍵が全角文字やかなとして確定されてしまう。
      「md@i(4l)h」と打ったつもりが「ｍｄ＠い（４ｌ）ｈ」

    全角の英数字・記号は半角に直し、
    かなとして確定してしまった文字はローマ字読みで半角に戻す
    （「い」→「i」）。

    戻り値: 半角に戻した文字列
    """
    text = zenkaku_to_hankaku(text)
    out = []
    for ch in text:
        if '\u3041' <= ch <= '\u3096':
            out.append(KANA_TO_ROMAJI.get(ch, ch))
        else:
            out.append(ch)
    return ''.join(out)


def correct_zenkaku_input(text, store, find_readings, max_dist=1.6):
    """
    全角で入ってしまった入力を、半角に戻してから補正する。

    戻り値: 補正後のかな文字列。該当しなければ None。
    """
    if not has_zenkaku_ascii(text):
        return None
    half = normalize_zenkaku_input(text)
    if not half or half == text:
        return None
    # 半角に戻せたら、通常の半角入力として補正する
    fixed = correct_halfwidth(half, store, find_readings, max_dist)
    if fixed:
        return fixed
    return correct_romaji(half, store, find_readings, max_dist)


# ============================================================
# 変換結果が「日本語として意味を成すか」の判定
# ============================================================

def _explained_ratio(kana, store, min_word_len=2, max_word_len=12):
    """
    かな列のうち、既知の語と機能語で説明できる割合を返す。

    半角モードで打った文字列は1つの語とは限らず、
    「たんごのつながり」のように複数の語と助詞からなる文になる。
    さらに、実際の文には辞書に無い語も混ざる。

    そこで「全体を隙間なく説明できるか」ではなく
    「どれだけ説明できたか」を割合で返し、
    呼び出し側でしきい値を決められるようにする。

    動的計画法で、各位置までに説明できた文字数の最大を求める。

    戻り値: (説明できた割合, 説明に使えた内容語の最大長)
    """
    n = len(kana)
    if n == 0:
        return 0.0, 0

    # 助詞・助動詞として単独で現れてよい語
    FILLERS = {
        'の', 'を', 'が', 'は', 'に', 'で', 'と', 'も', 'へ', 'や', 'か',
        'ば', 'て', 'た', 'だ', 'な', 'ね', 'よ', 'さ', 'し', 'ら', 'る',
        'から', 'まで', 'より', 'など', 'ので', 'のに', 'けど', 'ても',
        'ます', 'ました', 'ません', 'です', 'でした', 'ない', 'なく',
        'れる', 'られる', 'せる', 'させる', 'たい', 'そう', 'よう',
        'する', 'される', 'された', 'されない', 'しな', 'すること',
        'いる', 'ある', 'なる', 'こと', 'もの', 'ため', 'この', 'その',
        'では', 'には', 'とは', 'かも', 'なら', 'ながら', 'ければ',
    }

    # covered[i] = 位置 i までで説明できた文字数の最大
    covered = [0] * (n + 1)
    best_content = 0

    for i in range(n):
        # 説明できない文字として1つ進む（覆えた文字は増えない）
        if covered[i] > covered[i + 1]:
            covered[i + 1] = covered[i]
        # 機能語で進む
        for w in FILLERS:
            if kana.startswith(w, i):
                j2 = i + len(w)
                if covered[i] + len(w) > covered[j2]:
                    covered[j2] = covered[i] + len(w)
        # 語彙にある語で進む
        upper = min(max_word_len, n - i)
        for length in range(min_word_len, upper + 1):
            sub = kana[i:i + length]
            if [e for e in store.lookup(sub) if e['count'] >= 2]:
                j2 = i + length
                if covered[i] + length > covered[j2]:
                    covered[j2] = covered[i] + length
                if length > best_content:
                    best_content = length

    return covered[n] / n, best_content


def makes_sense_as_japanese(kana, store, min_ratio=0.6, min_content_len=3):
    """
    このかな列は、日本語として意味を成すか。

    判断の材料は2つ:
      - 既知の語と機能語で、どれだけ説明できたか（割合）
      - その中に、十分な長さの内容語が含まれているか

    全体を完全に説明できることは求めない。
    実際の文には辞書に無い語が必ず混ざるためで、
    そこまで求めると「はんかくのままにゅうりょく」のような
    正しい文まで弾いてしまう。

    一方で、英単語をかな配列で読んだ偶然の並び
    （hello → くいりりら）は、ほとんど説明できないので
    割合で区別できる。
    """
    if not kana:
        return False
    ratio, content_len = _explained_ratio(kana, store)
    if ratio < min_ratio:
        return False
    # 機能語だけで埋まった場合を除くため、
    # 実質的な語が含まれていることを求める
    return content_len >= min_content_len


def kana_to_kanji_where_possible(kana, store, min_word_len=2,
                                 max_word_len=12):
    """
    かな列を、語彙にある表記に置き換えられる範囲だけ置き換える。

    半角モードのまま打った文字列は、IMEによる変換を
    一度も経由していない。そのため「ひらがなのまま入力した」という
    意図を読み取ることができず、通常の誤字補正のように
    「ひらがなのまま返す」方針を適用する根拠が無い。
    そこで半角入力から復元した文字列だけは、
    語彙にある表記が分かる範囲で漢字・カタカナに変換する。

    語彙に無い部分（助詞や未登録語）はひらがなのまま残す。
    「たんごのつながり」→「単語のつながり」
    「もじにゅうりょく」→「文字入力」

    戻り値: 変換後の文字列
    """
    n = len(kana)
    if n == 0:
        return kana

    FILLERS = {
        'の', 'を', 'が', 'は', 'に', 'で', 'と', 'も', 'へ', 'や', 'か',
        'ば', 'て', 'た', 'だ', 'な', 'ね', 'よ', 'さ', 'し', 'ら', 'る',
        'から', 'まで', 'より', 'など', 'ので', 'のに', 'けど', 'ても',
        'ます', 'ました', 'ません', 'です', 'でした', 'ない', 'なく',
        'れる', 'られる', 'せる', 'させる', 'たい', 'そう', 'よう',
        'する', 'される', 'された', 'されない', 'しな', 'すること',
        'いる', 'ある', 'なる', 'こと', 'もの', 'ため', 'この', 'その',
        'では', 'には', 'とは', 'かも', 'なら', 'ながら', 'ければ',
    }

    # dp[i] = (位置iまでに覆えた文字数, 1つ前の位置, 使った表記 or None)
    # None は「1文字そのまま」を意味する。
    NEG = -1
    best_covered = [NEG] * (n + 1)
    back = [None] * (n + 1)
    best_covered[0] = 0

    for i in range(n):
        if best_covered[i] == NEG:
            continue
        # 説明できない1文字として進む（表記変換なし）
        cand = best_covered[i]
        if cand > best_covered[i + 1]:
            best_covered[i + 1] = cand
            back[i + 1] = (i, kana[i], None)

        # 機能語で進む（表記変換なし、ひらがなのまま）
        for w in FILLERS:
            if kana.startswith(w, i):
                j = i + len(w)
                cand = best_covered[i] + len(w)
                if cand > best_covered[j]:
                    best_covered[j] = cand
                    back[j] = (i, w, None)

        # 語彙にある語で進む（表記があれば変換する）
        upper = min(max_word_len, n - i)
        for length in range(min_word_len, upper + 1):
            sub = kana[i:i + length]
            entries = [e for e in store.lookup(sub) if e['count'] >= 2]
            if not entries:
                continue
            # 表記が1文字だけの候補は避ける。
            # 「した」→「下」のように、活用形の一部が
            # たまたま無関係な単漢字の読みと一致することがあり、
            # 半角入力の変換は文脈を見て判断できないため、
            # 誤って別の意味の語に化けるリスクが高い。
            # 2文字以上の候補があればそちらを使い、
            # 無ければひらがなのまま（変換しない）を選ぶ。
            multi_char = [e for e in entries if len(e['surface']) >= 2]
            surface = multi_char[0]['surface'] if multi_char else None
            j = i + length
            cand = best_covered[i] + length
            if cand > best_covered[j]:
                best_covered[j] = cand
                back[j] = (i, sub, surface)

    # 経路をたどって組み立てる
    out = []
    pos = n
    pieces = []
    while pos > 0 and back[pos] is not None:
        prev, original, surface = back[pos]
        pieces.append(surface if surface else original)
        pos = prev
    pieces.reverse()
    return ''.join(pieces)
