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

"""
**品詞と活用の文法**（項目48-KS・2026-08-29）。

うにさんの指定（2026-08-29）:

    「文節の末尾が「い」だからイ形容詞、「な」だからナ形容詞、
      ウ段だから動詞。補助動詞には「て」が付く。
      名詞を認識したから、うしろに助詞がくる可能性を予測したり、
      品詞を判定したり、品詞の組み合わせとしての予測など
      動いていますか？無ければ検討してください。
      名詞、代名詞、副詞、連体詞、接続詞、感動詞、助詞は
      文の形が変わりません」

いままで、かな連続の「説明が付くか」（`corrector._kana_run_explained`）
は**語の表と機能語の表を敷き詰めるだけ**で、**活用を知らなかった**。
だから

    入り**ます** ・ 震え**ているように** ・ 早**くなったので**

のような**述語の尻尾**（漢字の語幹に続く活用語尾＋助動詞の連なり）が
「説明できない」になり、**異様の判定に使えなかった**（False の 85% が
正しい日本語・2026-08-28 の実測）。

ここでは、うにさんの挙げた文法をそのまま**閉じた類**として持つ:

    ・活用語尾の段（い段=連用形・あ段=未然形・え段=仮定形/一段語幹・
      ウ段=終止連体形・お段+う=意向形・っ/ん=音便）
    ・助動詞の**接続**（ます は連用形に、ない は未然形に、
      た/て は音便形に付く）
    ・**て + 補助動詞**（ている・ておく・てしまう・てもらう…は、
      て の後ろで動詞がもう一度活用を始める）
    ・イ形容詞の活用（い・く・くて・かった・ければ・さ・そう）
    ・語の表からの活用推定——**表の語が「い」で終わればイ形容詞、
      ウ段で終われば動詞**とみなし、語幹＋活用形も語として認める
      （わるい → わるかった、もどる → もどった）。ただし同梱辞書が
      形容動詞と示す語はイ形容詞にしない（48-VU）。同形のイ形容詞は残す
    ・形の変わらない品詞（名詞・代名詞・副詞・連体詞・接続詞・
      感動詞・助詞）は**表との完全一致**でそのまま置ける

**判定の向き**: この文法は**「説明が付く＝異様ではない」side にだけ**
使う（許す向き。多めに許しても、正しい文を守る側に倒れるだけ）。
説明が付かないことは「異様」の**必要条件**であって、単独の証拠には
しない——`odd_kana_spans` の敷居（長さ・繰り返しの形）と組で使う。

表は増やさない: 語は `oddness` の表（seed_japanese 778,340語）を
借り、機能語は `corrector` の名簿を借りる。**ここに在るのは
「つなぎ方」（文法）だけ**で、同じ意味の名簿を2つ作らない（決まり）。
"""

# 五十音の段（活用語尾に立つもの。ぢ・づ は現代仮名では稀だが含める）
_DAN_I = 'いきぎしじちぢにひびぴみり'      # 連用形（買い・書き・押し）
_DAN_A = 'あかがさざただなはばぱまやらわ'   # 未然形（買わ・書か・押さ）
_DAN_E = 'えけげせぜてでねへべぺめれ'      # 仮定形・一段語幹（書け・見え）
_DAN_U = 'うくぐすずつづぬふぶぷむゆる'    # 終止・連体形（買う・書く）
_DAN_O = 'おこごそぞとどのほぼぽもよろ'    # 意向形（買お+う・書こ+う）

# 五段の行（辞書形の末尾 → 未然/連用/仮定/意向の字と音便の字）。
# 「ウ段だから動詞」——表の語がウ段で終わっていたら、この行で
# 活用した形も同じ語とみなす（もどる → もどり・もどっ・もどれ）。
_GODAN_ROW = {
    'う': ('わ', 'い', 'え', 'お', 'っ'),
    'く': ('か', 'き', 'け', 'こ', 'い'),
    'ぐ': ('が', 'ぎ', 'げ', 'ご', 'い'),
    'す': ('さ', 'し', 'せ', 'そ', ''),
    'ず': ('ざ', 'じ', 'ぜ', 'ぞ', ''),
    'つ': ('た', 'ち', 'て', 'と', 'っ'),
    'づ': ('だ', 'ぢ', 'で', 'ど', 'っ'),
    'ぬ': ('な', 'に', 'ね', 'の', 'ん'),
    'ふ': ('は', 'ひ', 'へ', 'ほ', ''),
    'ぶ': ('ば', 'び', 'べ', 'ぼ', 'ん'),
    'ぷ': ('ぱ', 'ぴ', 'ぺ', 'ぽ', ''),
    'む': ('ま', 'み', 'め', 'も', 'ん'),
    'ゆ': ('', '', '', '', ''),
    'る': ('ら', 'り', 'れ', 'ろ', 'っ'),
}

# 敬称（名前の後ろに付く閉じた類）。`うにさんの` を名前と見るため。
_HONORIFICS = ('さん', 'さま', 'くん', 'ちゃん')

# 助詞は**置ける場所で分ける**（うにさんの「文の間だから助詞」）。
# 格助詞・係助詞は語のあとに付くが、終助詞（ね・よ・わ…）は
# **述語が閉じたあと**にしか立てない。1つの名簿（PARTICLES_1CHAR）で
# どこにでも置くと `わ|くわ|うし|ながら` のような読み方まで通ってしまう
# （実測: `わくわうし` が説明できてしまい、的を取りこぼした）。
_CASE_PARTICLES = frozenset('はがをにでとものへやか')
_FINAL_PARTICLES = frozenset('ねよさなぞぜわかも')

# 名詞の述語（名詞＋だ・です——形の変わらない品詞が述語になる形）
_NOUN_PRED = (
    ('だ', 'END'), ('です', 'END'), ('でした', 'END'), ('だった', 'TA'),
    ('だろう', 'END'), ('でしょう', 'END'), ('なら', 'END'),
    ('な', 'Bf'),                    # ナ形容詞の連体形（きれいな＋名詞）
)

# 助詞の追加ぶん（`corrector.PARTICLES_MULTI` に無い閉じた類）
_EXTRA_PARTICLES = frozenset((
    'ばかり', 'ぐらい', 'くらい', 'なんて', 'なんか', 'ずつ', 'すら',
    'やら', 'かな', 'っけ', 'とか', 'って', 'のみ',
    # **念押しの終助詞**（項目48-OU・2026-09-03。`だからってば`・
    # `私ったら`）。閉じた類
    'ってば', 'ったら',
))

# 機能語の追加ぶん（corrector の名簿に無い閉じた類。**ここに足しても
# 補正の答えは変わらない**——この文法は印の判定にしか使わないため）
_EXTRA_FUNCS = frozenset((
    'どちら', 'こちら', 'そちら', 'あちら',      # 指示語の漏れ
    'してる', 'してた', 'してて',                # ている の縮み（話し言葉）
    # かなで書く副詞（**副詞＋名詞** は普通の並びなので、語×語の
    # 「直接つなげない」の外に出す。まず会議から・ほぼ全部）
    'まず', 'ほぼ', 'ごく', 'おそらく', 'ようやく', 'いったん',
    'たしかに', 'まさに', 'もともと',
))

# **1字の語幹を許す基本動詞**（なる・ある・いる・おる・でる・みる・ねる）。
# 語幹1字の活用推定を全部許すと `ひ|ら|ん`（干る の未然＋ん）のような
# 読み方で的を取りこぼすので、**閉じた白名簿**にする。
_BASIC_STEMS_1 = frozenset('なあいおでみね')

# 一段活用でありうる語幹の末尾（い段・え段——見る・食べる）。
# ウ段など他の段で終わる語幹の「る」は五段（ゆする・かえる…は
# 語幹末で分かれる。`ゆす|る` を一段と見て `ゆすかりた` を
# 「語幹＋借りた」と読んでしまった・実測）。
_ICHIDAN_TAIL = frozenset(_DAN_I + _DAN_E)

_TABLES = None


def _load_tables():
    """機能語の名簿は `corrector` から借りる（1回だけ・循環なし）。"""
    global _TABLES
    if _TABLES is not None:
        return _TABLES
    import corrector as C
    try:
        import oddness as O
        words = O._load() or frozenset()
    except Exception:
        words = frozenset()
    funcs = (set(C.PARTICLES_MULTI) | set(C.AUXILIARY_TAILS)
             | set(C.DEMONSTRATIVES) | set(C.FUNCTION_NOUNS)
             | set(C.BASIC_VERB_FORMS) | set(C.CONNECTIVES)
             | set(_EXTRA_PARTICLES) | set(_EXTRA_FUNCS)
             | {'よい', 'いい', 'ない'})
    funcs = {x for x in funcs if len(x) >= 2}
    global _VFUNCS, _ATAILS, _FNOUNS
    _VFUNCS = frozenset(x for x in C.BASIC_VERB_FORMS if len(x) >= 2)
    _ATAILS = frozenset(x for x in C.AUXILIARY_TAILS if len(x) >= 2)
    _FNOUNS = frozenset(x for x in C.FUNCTION_NOUNS if len(x) >= 2)
    _TABLES = (words, funcs, _CASE_PARTICLES)
    return _TABLES


# --- 活用のオートマトン ---------------------------------------------
#
# 状態:
#   Bf   語の頭に立てる位置（文節の頭・機能語のあと）
#   Bw   語を置いた直後（**語と語は直接つなげない**・項目48-IS の決まり
#        のまま。ただし活用する語＝動詞・形容詞は 副詞＋動詞 のように
#        直接続くので、活用の入口だけは許す）
#   S    漢字の語幹の直後（活用語尾がここから始まる）
#   R    連用形のあと（ます・た・て・たい が付ける）
#   MZ   未然形のあと（ない・ぬ・ん・ず・れる・せる）
#   E    仮定形・一段語幹のあと（る・れば・ば・ない・られる・ます…）
#   TSU  促音便（っ）のあと（た・て・たら・たり）
#   N    撥音便（ん）のあと（だ・で）
#   TE   て形のあと（**補助動詞がもう一度活用を始める**・GEN を通す）
#   TA   た形のあと（ら・り・そのまま終わり）
#   IST  イ形容詞の語幹のあと（い・く・くて・かった・ければ・さ・そう）
#   SOU  そう（様態）のあと（だ・です・に・な）
#   END  述語が閉じた（助詞・終助詞・です が付ける）
#   K    **1字の格助詞の直後**（項目48-RZ・2026-09-06）。END と同じ
#        ものが付けるが、次の文節の頭に**もう1つ格助詞**は置けない
#        （`もみ|と|に|もどります`——と の直後の に）。`Bk` へ ε
#   Bk   格助詞の直後の文節の頭。Bf と同じだが、が・を・に・へ・で
#        （1字の格助詞）は置けない。は・も（係助詞）・の・と（へと・
#        引用の と）は置ける
#
# 受け入れ: 連続の終わりに Bf/Bw/END/TA/TE/R/E/K/Bk で立っていること。
# （MZ・TSU・N・IST・S の途中では終われない——「〜かっ」は語ではない）

_PIECES = {
    'R': (
        ('ます', 'END'), ('ました', 'TA'), ('まして', 'TE'),
        ('ません', 'END'), ('ませんでした', 'END'), ('ましょう', 'END'),
        ('ますまい', 'END'), ('まい', 'END'),
        ('た', 'TA'), ('て', 'TE'), ('た', 'IST'),      # たい はイ形容詞
        ('そう', 'SOU'), ('ながら', 'END'), ('つつ', 'END'),
        ('なさい', 'END'), ('なさいます', 'END'), ('なさら', 'MZ'),
        ('なさっ', 'TSU'), ('なさる', 'END'),
        ('やす', 'IST'), ('にく', 'IST'), ('づら', 'IST'), ('がた', 'IST'),
        ('うる', 'END'), ('え', 'E'),    # 得る（可能）: 取り得る・あり得ない（48-SX）
        ('ちゃう', 'END'), ('ちゃっ', 'TSU'), ('ちゃい', 'R'),
        ('じゃう', 'END'), ('じゃっ', 'TSU'),
        # **ら抜き**（項目48-OU・2026-09-03）。一段の語幹末（E）にも
        # 同じ表が足されるので、`食べ＋れ＋る`・`見＋れ＋ます`・
        # `決め＋れ＋ない` が説明できる。**五段は可能動詞（書ける）が
        # 既に E で立つ**ので、ここは触らなくても届く
        ('れ', 'E'),
    ),
    'MZ': (
        ('な', 'IST'), ('ぬ', 'END'), ('ん', 'END'), ('ず', 'END'),
        ('ずに', 'END'), ('れ', 'E'), ('せ', 'E'), ('んとす', 'END'),
        ('され', 'E'), ('さ', 'E'),        # 使役・使役受身（待た**され**ます）
    ),
    'E': (
        ('る', 'END'), ('れば', 'END'), ('ば', 'END'), ('ろ', 'END'),
        ('よ', 'END'), ('よう', 'END'), ('られ', 'E'), ('させ', 'E'),
        ('な', 'IST'), ('ず', 'END'), ('ずに', 'END'), ('まい', 'END'),
        ('ん', 'END'), ('んとす', 'END'),
    ),
    'TSU': (
        ('た', 'TA'), ('たら', 'END'), ('たり', 'END'), ('て', 'TE'),
        # **ておく → とく**（項目48-OU・2026-09-03。話し言葉として
        # 決まった縮約。`やっとく`・`書いとく`）。`と` は て＋お の
        # 融合で、そのあとは おく（か行五段）の活用がそのまま続く
        ('とく', 'END'), ('とけ', 'E'), ('とか', 'MZ'), ('とき', 'R'),
        ('とい', 'TSU'), ('とこう', 'END'),
    ),
    'N': (
        ('だ', 'TA'), ('で', 'TE'),
        # **でおく → どく**（撥音便の側。`読んどく`）
        ('どく', 'END'), ('どけ', 'E'), ('どか', 'MZ'), ('どき', 'R'),
        ('どい', 'TSU'), ('どこう', 'END'),
    ),
    # **て形のあとの補助動詞**（項目48-OU）。`_gen_steps` が活用の
    # 入口（る・た・て・ん…）を出すので、ここに足すのは
    # **そこで作れない形**だけ:
    #   い抜き（ている → てる）の ます・ません・ない・なかった
    #   ていく → てく の きます・こう
    'TE': (
        ('ます', 'END'), ('ました', 'TA'), ('ません', 'END'),
        ('ませんでした', 'END'), ('ない', 'IST'), ('なかった', 'TA'),
        ('なけれ', 'E'), ('きます', 'END'), ('こう', 'END'),
        # **ているの → てんの**（項目48-PS・2026-09-03）。
        # `し**てんの**`・`やっ**てんの**`・`食べ**てんの**` は正しい口語。
        # これが無いと `してんの` が説明できず、芯の再構築が
        # **`進展の`** にしていた（初期で実測）。
        ('んの', 'END'), ('んのか', 'END'), ('んだ', 'END'),
        ('んです', 'END'), ('んですか', 'END'),
    ),
    'TA': (
        ('ら', 'END'), ('り', 'END'),
    ),
    'IST': (
        ('い', 'END'), ('く', 'Bf'), ('くて', 'TE'), ('かった', 'TA'),
        ('かったら', 'END'), ('ければ', 'END'), ('かろう', 'END'),
        ('さ', 'Bw'), ('そう', 'SOU'), ('すぎ', 'E'),
    ),
    'SOU': (
        ('だ', 'END'), ('です', 'END'), ('でした', 'END'),
        ('に', 'Bf'), ('な', 'Bf'),
    ),
    'END': (
        ('し', 'END'), ('です', 'END'), ('でしょう', 'END'),
        ('だろう', 'END'), ('まい', 'END'), ('らし', 'IST'),
        ('みたい', 'END'), ('って', 'END'),
    ),
}

# 48-WK: て/でしまうの縮約は、しまうと同じワ行五段の活用を保つ。
# 無声の音便には「ちゃ」、有声の音便には「じゃ」を接続する。
# 連用形・一段語幹の既存の縮約にも否定・仮定・意向を補う。
def _shimau_contraction_pieces(prefix):
    return ((prefix + 'う', 'END'), (prefix + 'っ', 'TSU'),
            (prefix + 'い', 'R'), (prefix + 'わ', 'MZ'),
            (prefix + 'え', 'E'), (prefix + 'おう', 'END'))


_PIECES['TSU'] += _shimau_contraction_pieces('ちゃ')
_PIECES['N'] += _shimau_contraction_pieces('じゃ')
_PIECES['R'] = tuple(dict.fromkeys(
    _PIECES['R'] + _shimau_contraction_pieces('ちゃ')
    + _shimau_contraction_pieces('じゃ')))

# ます・た・て … は連用形にも一段語幹にも付く
_PIECES['E'] = _PIECES['E'] + _PIECES['R']
# 解析済みの未然形は、接続先が限定される（するの せ・さ・しよ）。
_PIECES['MN'] = tuple(p for p in _PIECES['MZ'] if p[0] in ('ぬ', 'ん', 'ず', 'ずに'))
_PIECES['MR'] = (('れ', 'E'), ('せ', 'E'))
_PIECES['MO'] = (('う', 'END'),)
_PIECES['COND'] = (('ば', 'END'),)


def continuation_state(form):
    """解析された動詞の活用形を、続きの接続状態にする。未対応はNone。"""
    if form and form.startswith('命令'):
        return 'END'
    return {'連用形':'R', '未然形':'MZ', '未然ヌ接続':'MN',
            '未然レル接続':'MR', '未然ウ接続':'MO', '仮定形':'COND',
            '基本形':'END'}.get(form)


# 終助詞は述語のあとにだけ（買った**ね** ○ ／ 語の途中には置かない）
_PIECES['END'] = _PIECES['END'] + tuple(
    (c, 'END') for c in sorted(_FINAL_PARTICLES)) + _NOUN_PRED

# ★★ **格助詞の連続は説明が付かない**（項目48-RZ・2026-09-06・
# うにさんの指定「`もみとにもどります`、紫がないですね。`もみとの` が
# 変なのは AI なら分かります。`もみ` を名詞と捉えていますが、`とに` には
# 続かないでしょう」）。
#
# いままで1字の格助詞は END へ行き、END → ε → Bf → 1字の格助詞 と
# **際限なく並べられた**（もみ＋と＋に＋もどります が「説明が付く」）。
# 日本語で格助詞が2つ続くのは **へと**（駅へと向かう）と、**引用の と**
# （君にと思って）・**並立の と**（父と母とに——前にも と が要る）だけ。
# だから、1字の格助詞（が・を・に・へ・と・で・は・も）の直後は `K` に
# 置き、そこから始まる文節の頭（`Bk`）には **が・を・に・へ・で** を
# 置かない。`の`（との・への・での）・`は`・`も`（にも・とは）・`と`
# （へと・引用）は今までどおり。`_CASE_PARTICLES` の や・か・の は
# 格助詞ではなく（並立・疑問・連体）、`K` を作らない。
#
# **並立の と（AとBとに）は 48-RZ で立つ**（前の と を数えていない）。
# 実機メモ・正しい日本語1,500文で測って受け止める（項目48-RZ の実測）。
_K_INDUCING = frozenset('がをにへとではも')
_BLOCKED_AFTER_CASE = frozenset('がをにへで')
_PIECES['K'] = _PIECES['END']

# 状態からの ε 遷移（字を消費しない）
_EPS = {
    'R': ('Bw',),          # 連用中止・名詞化（読み、書き）
    'E': ('Bw',),          # 一段の連用形（見に行く の 見）
    'TE': ('Bf',),         # て＋補助動詞は語の表からも引ける（ておきます）
    'TA': ('END',),
    'SOU': ('END',),
    'END': ('Bf',),        # 連体形＋形式名詞（するもの・るとき）
    'K': ('Bk',),          # 格助詞の直後の文節（もう1つ格助詞は置けない・48-RZ）
    'Ev': ('Bn',),         # 終止の直後（stems_only だけが作る状態・48-TH''''）
}

_ACCEPT = frozenset(('Bf', 'Bw', 'END', 'TA', 'TE', 'R', 'E', 'K', 'Bk', 'Ev'))

# ★ **stems_only では、用言の END を「終止」と「接続」に分ける**（項目48-TH''''・
# 2026-09-06）。今までの END は 終止（やめ**る**・やめ**た**・ひど**い**・し**ます**）
# も 接続（やめ**たら**・やめ**れば**・ひどく**て**・やめる**し**）も同じ状態で、
# END → ε → Bf から**もう1つ用言を始められた**（おく＋ゆく・ほう＋れんぞう・
# てた＋とおす・ねらう＋いち）。日本語で終止形の直後に用言は立たない（連体形＋
# 名詞は名詞が要る——stems_only は名詞を引かない）。
#   Ev  用言が終止・連体・命令で終わった（る・う・た・ます・ぬ・ん・い・だ…）
#   Bn  Ev の直後の文節の頭——助詞・機能語・名詞の述語だけ（用言の語幹を始めない・
#       名詞を引かない）。機能語の表の動詞形（おく・いく・くる・する…＝
#       `BASIC_VERB_FORMS`）も終止形なら Ev へ落とす
# 接続の語尾（`_CONJ_PIECES`）は今までどおり END → Bf で次の用言に続く
# （やめたら行く・食べて寝る・やめるし行く）。stems_only 以外は何も変えない。
_PIECES['Ev'] = _PIECES['END']
_CONJ_PIECES = frozenset(('ながら', 'つつ', 'れば', 'ば', 'ず', 'ずに', 'たら', 'たり',
                          'かったら', 'ければ', 'し', 'って', 'く', 'くて', 'まして'))
_VERB_STATES = frozenset(('R', 'E', 'MZ', 'TSU', 'N', 'TE', 'IST', 'SOU', 'TA', 'S', 'Ev'))
_VFUNCS = frozenset()          # 機能語の表の動詞形（おく・いく・する…）
_ATAILS = frozenset()          # 助動詞の尾（ます・てた・ない…）——用言のあとにだけ
_FNOUNS = frozenset()          # 形式名詞（ほう・こと・とき…）——直後に用言は立たない


def _stems_target(st, piece, st2):
    """stems_only: 用言の状態から END に落ちる語尾のうち、接続でないものは Ev へ。"""
    if st2 == 'END' and st in _VERB_STATES and piece not in _CONJ_PIECES:
        return 'Ev'
    return st2


def _gen_steps(run, i):
    """漢字の語幹の直後（S）と て形のあと（TE）で始まる活用語尾。"""
    c = run[i]
    out = []
    if c in _DAN_I:
        out.append((i + 1, 'R'))
    if c in _DAN_A:
        out.append((i + 1, 'MZ'))
    if c in _DAN_E:
        out.append((i + 1, 'E'))
    if c in _DAN_U:
        out.append((i + 1, 'END'))
    if c == 'っ':
        out.append((i + 1, 'TSU'))
    if c == 'ん':
        out.append((i + 1, 'N'))
    if c in _DAN_O and i + 1 < len(run) and run[i + 1] == 'う':
        out.append((i + 2, 'END'))
    return out


def _possible_i_adjective(word):
    # 48-VU: 形容動詞の基本形を、末尾が「い」というだけでイ形容詞にしない。
    # 同形のイ形容詞が辞書にあれば許す。その他の語の推定は従来どおり。
    from morphology import dictionary_base_pos
    kinds = dictionary_base_pos(word)
    return (not kinds or any(p.split(',')[0] == '形容詞' for p in kinds)
            or not any(p.startswith('名詞,形容動詞語幹,') for p in kinds))


def _looks_verb(word, words):
    """
    その表記は**用言（動詞）の形**か（項目48-MR・2026-08-31）。

    表に品詞は無いので、**活用の形**で見る:

        一段   `入れ` → `入れる` が表に在る
        五段   `書き` → い段を言い切りへ戻した `書く` が表に在る

    `全て` はどちらでもない（`全てる` も `全つ` も無い）ので、
    用言ではない。**閉じた活用の表だけで決まる**——語を並べた表を
    足すわけではない。
    """
    if not word:
        return False
    if word + 'る' in words:
        return True                      # 一段（入れ→入れる・見→見る）
    tail = word[-1]
    for u, row in _GODAN_ROW.items():
        if row[1] and row[1] == tail and word[:-1] + u in words:
            return True                  # 五段の連用形（書き→書く）
    return False


def is_functional_noun(token):
    """解析上の形式名詞と、文法の機能語の境界が一致するか。"""
    return (len(token) > 1 and (token[1] or '').startswith('名詞:非自立')
            and token[0] in _load_tables()[1])


def explain_kana_run(run, after_kanji=False, before_kanji=None,
                     kanji_stem='', is_word=None, bare_head=False,
                     no_words=False, stems_only=False, initial_state=None):
    """
    **かな連続が、語の表＋機能語＋活用の文法で説明できるか。**

    after_kanji:  直前が漢字（活用語尾・送り仮名がここから始まり得る）
    before_kanji: 直後が漢字（末尾の お/ご は次の語の接頭辞であり得る）。
                  **None は「分からない」**（今までどおり接頭辞であり得る
                  と読む）。**False（直後が漢字ではない）のときだけ**、
                  末尾の お/ご を接頭辞とは読まない（項目48-TJ・
                  2026-09-06。`よれごを確認` の `よれご` が
                  よれ＋ご で説明されて、`よごれ` に直せなくなっていた。
                  ご の次は を なので接頭辞ではあり得ない）
    kanji_stem:   直前の漢字の連続（`思` ＋ `いがけず` のように、
                  漢字＋かなでひとつの表の語になる形を引くため）
    is_word:      語かどうかを判定する関数（None なら表だけ）。
                  辞書の索引・本人の語彙を足すのに使う（きちんと・
                  ぴたり は表に無いが辞書には在る普通の語）
    stems_only:   **語の表を、動詞・形容詞の活用の根拠にだけ使う**読み
                  （項目48-TH・2026-09-06）。名詞の部品としては使わない。
                  `やめたら`（やめる＋たら）・`ひどくて`（ひどい＋くて）は
                  True、`きゅうずいを`（きゅう＋ずい＋を）は False。
                  **用言1つ＋活用語尾・機能語**の形だけ（48-TH'''）——裸の
                  連用形から次の語へ進まない（`かぎかえを`＝嗅ぎ＋替え＋を は
                  False）・用言の直後に用言を始めない
    no_words:     **語の表を使わない**読み（項目48-SQ・2026-09-06）。
                  機能語・活用・名前＋敬称だけで説明が付くか——
                  `しやすさ`（し＋やす＋さ）・`たかちゃん` は True、
                  `きゅうずいを`（きゅう＋ずい＋を＝語＋語）は False。
                  「内容語が1つも無い連続」には語彙で直すものが無い、
                  という判定に使う
    bare_head:    **連続が行の頭に立っている**（前に何も無い。項目48-RZ・
                  2026-09-06）。係助詞・格助詞は前の句が要るので、
                  **本当の行頭に裸の1字助詞は立てない**（48-KX の
                  かな版）。`もみとにもどります` は も＋みと＋に で
                  説明が付いていた——行頭の も を助詞に読んでいたから。
                  行頭でなければ（前が漢字・読点・括弧）今までどおり

    initial_state: 直前の活用状態が確定した場合の入口（R=連用形など）。
                   Noneなら従来どおり文節の頭から読む。

    戻り値: True（説明が付く＝異様とは言えない）／False（付かない）。
    **False は異様の必要条件であって、単独の証拠にしない。**
    """
    # 呼び手が直前の活用形を確定できるときだけ、その接続状態を使う。
    if initial_state is not None and initial_state not in _PIECES and initial_state != 'Bw':
        raise ValueError('unsupported grammatical state: ' + str(initial_state))
    if not run:
        return initial_state is None or initial_state in _ACCEPT
    # 48-XR: 表示用の解析と同じ根拠で、口語の助動詞表記を読む。
    # ここでは文字を書き換えず、後続の接続も通常の文法で検証する。
    if 'ぅ' in run:
        from morphology import colloquial_auxiliary_normal_form
        run = colloquial_auxiliary_normal_form(run)
    _tbl_words, funcs, p1 = _load_tables()
    if not _tbl_words:
        return True                      # 表が無ければ意見なし
    if is_word is None:
        words = _tbl_words
    else:
        class _W(object):
            def __contains__(self, frag):
                return frag in _tbl_words or bool(is_word(frag))
        words = _W()
    nouns = words               # 名詞の部品として引く表（48-TH）
    if no_words or stems_only:
        class _NoWords(object):
            def __contains__(self, frag):
                return False
        nouns = _NoWords()
        if no_words:
            words = nouns
    if initial_state is None and (run in nouns or run in funcs):
        return True
    n = len(run)
    # 末尾の お/ご は、次の語の接頭辞（お待ちください・「なんだお前」の
    # 切れ端）。直後が漢字でなくても、行やかぎ括弧の切れ目で同じ形が
    # できる（実測: `なんだお` に印が立ち、48-GL の「出しすぎ」になった）
    ends = {n}
    if n >= 3 and run[-1] in 'おご' and before_kanji is not False:
        ends.add(n - 1)                  # 次が漢字でないと分かれば読まない（48-TJ）

    seen = set()
    stack = [(0, initial_state or 'Bf')]
    if after_kanji:
        stack.append((0, 'S'))
        # 漢字の連続＋かなの頭が、表の語（思いがけず・引き継ぎ）。
        # **用言でなければ、その先は「文節の頭」として扱う**
        # （`Bf`・項目48-MR・2026-08-31）。「語と語を直接つなげない」の
        # 決まりは `たん|あご` `すき|にん` のような**かなだけの並び**を
        # 止めるためのもので、ここは**漢字が語の切れ目を保証している**:
        #
        #     全**て**ひらがなであり → 全て（漢字＋送り仮名）で1語が
        #                             閉じたあとの `ひらがな` は新しい語
        #
        # `Bw` のままだと `全て` のあとに語が置けず、うにさんの画面の
        # 誤検知（`てひらがなであり` に紫）になっていた。
        #
        # **用言（動詞）の形のときは `Bw` のまま**——連用形の直後は
        # 複合動詞の場所で、そこに語を置けるようにすると
        # `入れ|ちいさい`（`入れていない` の壊れた形）まで説明が
        # 付いてしまい、**本物の異様を取りこぼす**（実測。この形は
        # 下のイ形容詞の枝でも同じ理由で断っている）。
        # 48-VY: 形容動詞語幹＋「さ」は名詞。未然形の「さ」と区別する。
        # 漢字に続く送り仮名も含め、辞書の基本形・全品詞で裏付ける。
        # 普通名詞に「さ」を付ける推定や、語ごとの例外表は作らない。
        if kanji_stem:
            from morphology import dictionary_base_pos
            for k in range(min(12, n)):
                if run[k] != 'さ':
                    continue
                base = kanji_stem + run[:k]
                if any(p.startswith('名詞,形容動詞語幹,')
                       for p in (dictionary_base_pos(base) or ())):
                    stack.append((k + 1, 'Bw'))
        if kanji_stem:
            for k in range(1, min(6, n) + 1):
                w0 = kanji_stem + run[:k]
                if w0 not in words:
                    continue
                stack.append((k, 'Bw' if _looks_verb(w0, words) else 'Bf'))
            # 漢字の語幹の動詞・形容詞（動く・早い）を活用させた形
            for k in range(0, min(4, n)):
                stem = kanji_stem + run[:k]
                if (stem + 'い' in words and k < n
                        and _possible_i_adjective(stem + 'い')):
                    stack.append((k, 'IST'))
                for u, row in _GODAN_ROW.items():
                    if stem + u not in words or k >= n:
                        continue
                    a, i_, e, o, onb = row
                    c = run[k]
                    if c == u:
                        stack.append((k + 1, 'Ev' if stems_only else 'END'))
                    if c == a:
                        stack.append((k + 1, 'MZ'))
                    if c == i_:
                        stack.append((k + 1, 'R'))
                    if c == e:
                        stack.append((k + 1, 'E'))
                    if onb and c == onb:
                        stack.append((k + 1, 'TSU' if onb != 'ん' else 'N'))
                    if c == o and k + 1 < n and run[k + 1] == 'う':
                        stack.append((k + 2, 'Ev' if stems_only else 'END'))
                    if u == 'る' and (not ('ぁ' <= stem[-1] <= 'ゖ')
                                      or stem[-1] in _ICHIDAN_TAIL):
                        stack.append((k, 'E'))       # 一段（見る・出る）
    while stack:
        i, st = stack.pop()
        if (i, st) in seen:
            continue
        seen.add((i, st))
        if i in ends and st in _ACCEPT:
            return True
        if i >= n:
            continue
        c = run[i]
        # ー は前の音の伸び（状態を変えずに読み飛ばす）
        if c == 'ー':
            stack.append((i + 1, st))
            continue
        # ε 遷移
        for st2 in _EPS.get(st, ()):
            if initial_state is not None and st in ('R', 'E') and st2 == 'Bw':
                continue  # 接続の検証では、途中の活用を名詞化して逃がさない
            # **stems_only では、裸の連用形・一段の語幹（R・E）から次の語へ
            # 進まない**（項目48-TH'''・2026-09-06）。連用形＋を（替えを）・
            # 連用形＋動詞（嗅ぎ替え）は文法としては立つが、この読みは
            # 「用言1つ＋活用語尾・機能語」で説明が付くかを聞いている。
            # 進ませると `かぎかえを`（嗅ぎ＋替え＋を）・`したれやなぎ`
            # （し＋垂れ＋や＋薙ぎ）まで「読める」になり、readcheck の直りを
            # 初期 −18／育ち −42 失った（f6）。用言は語尾（た・て・たら・
            # ます・る・ない…）を取ってから次へ
            if stems_only and st in ('R', 'E'):
                continue
            if stems_only and st2 == 'END' and st in ('TA', 'SOU'):
                st2 = 'Ev'                # た・そうだ は終止（48-TH''''）
            stack.append((i, st2))
        if st in ('S', 'TE'):
            for _nx in _gen_steps(run, i):
                if stems_only and _nx[1] == 'END':
                    _nx = (_nx[0], 'Ev')
                stack.append(_nx)
            if st == 'TE':
                # **て形のあとの補助動詞**（項目48-OU）。`_gen_steps`
                # だけでは い抜きの `てます`・`てない` が作れない
                for piece, st2 in _PIECES.get('TE', ()):
                    if run.startswith(piece, i):
                        stack.append((i + len(piece), st2))
            continue
        if st in _PIECES:
            for piece, st2 in _PIECES[st]:
                if run.startswith(piece, i):
                    if stems_only:
                        st2 = _stems_target(st, piece, st2)
                    stack.append((i + len(piece), st2))
            continue
        if st in ('Bf', 'Bw', 'Bk', 'Bn'):
            # 1字の格助詞（形の変わらない品詞は、表との一致で置ける。
            # 終助詞は END からだけ——「文の間だから助詞」の場所の決まり）
            # **格助詞の直後（Bk）には、もう1つ格助詞を置かない**（48-RZ）。
            # **本当の行頭に裸の1字助詞は立てない**（同・bare_head）
            if c in p1 and not (st == 'Bk' and c in _BLOCKED_AFTER_CASE) \
                    and not (bare_head and i == 0 and not after_kanji
                             and c != 'と'):   # 行頭の と は引用・続き（とのことですが）
                stack.append((i + 1, 'K' if c in _K_INDUCING else 'END'))
            # 名詞の述語（名詞＋だ・です・なら）
            for piece, st2 in _NOUN_PRED:
                if run.startswith(piece, i):
                    stack.append((i + len(piece), st2))
            # 機能語（2字以上）
            for ln in range(2, min(12, n - i) + 1):
                if run[i:i + ln] in funcs:
                    _f = run[i:i + ln]
                    # 助動詞の尾（てた・ます・ない…）は用言のあとにだけ——
                    # 文節の頭には立てない（`てた＋とおす`。漢字の直後の
                    # 連続の頭は 送り仮名＋尾 なので除く。48-TH''''）
                    if ((stems_only or initial_state is not None)
                            and _f in _ATAILS and (st in ('Bf', 'Bk', 'Bn')
                                                   or (initial_state == 'Bw' and st == 'Bw'))
                            and not (after_kanji and i == 0)):
                        continue
                    stack.append((i + ln, 'Ev' if (
                        stems_only and (_f in _FNOUNS or (
                            _f in _VFUNCS and _f != 'あり'
                            and not _f.endswith(('て', 'で', 'ば', 'く')))))
                        else 'END'))
            # 語（**語と語は直接つなげない**——Bw からは置けない）
            if st in ('Bf', 'Bk'):
                for ln in range(2, min(12, n - i) + 1):
                    if run[i:i + ln] in nouns:
                        stack.append((i + ln, 'Bw'))
                # 名前＋敬称（うにさん・たろうくん）
                # 名前は**2字以上**（項目48-SQ・2026-09-06。1字＋敬称〔`せくん`〕は
                # 名前の形ではなく、打ち間違い `くせん → せくん` を説明していた）
                for k in range(2, min(4, n - i)):
                    for h in _HONORIFICS:
                        if run.startswith(h, i + k):
                            stack.append((i + k + len(h), 'Bw'))
            # 活用する語の推定: 表の語が「い」で終わればイ形容詞、
            # ウ段で終われば動詞（Bw からも置ける——副詞＋動詞の形）。
            # **動詞の語幹は2字以上**（1字の語幹を許すと `ひ|ら|ん` =
            # 干る の未然＋ん のような読み方で、的を取りこぼした・実測）。
            # イ形容詞は `よい`（語幹1字）が普通の語なので1字を許す。
            if stems_only and st in ('Bw', 'Bn'):
                continue                  # 用言の直後に用言を始めない（48-TH'''／48-TH''''）
            for ln in range(1, min(11, n - i) + 1):
                stem = run[i:i + ln]
                j = i + ln
                # イ形容詞は文節の頭から（動詞の語幹の直後には立たない
                # ——`入れ|ちいさい` を許すと的を取りこぼす・実測）
                # **stems_only では、活用形が2つ表に在る語だけを用言と読む**
                # （項目48-TH''・2026-09-06）。表に品詞は無いので、い で
                # 終わる語（こてい＝固定）や う で終わる語（きゅう＝級）が
                # 全部「用言」に見えて、打ち間違いまで説明していた。
                # 形容詞は 語幹＋い と 語幹＋く、五段は 終止形 と 連用形
                # （い段）、一段は 語幹＋る と 語幹 の両方
                # **1字の形容詞語幹は閉じた組**（よい・ない・こい・すい。48-TH''''）——
                # が＋い／が＋く（害・学）のような名詞の偶然が語幹に見えていた
                if (st in ('Bf', 'Bk') and j < n and (stem + 'い') in words
                        and _possible_i_adjective(stem + 'い')
                        and (not stems_only or ((stem + 'く') in words
                                                and (ln >= 2 or stem in 'よなこす')))):
                    stack.append((j, 'IST'))
                if j >= n:
                    continue
                # **1字の語幹は、音便（っ・ん）の形のときだけ**
                # （項目48-OU・2026-09-03）。1字の語幹を全部許すと
                # `ひ|ら|ん`（干る の未然＋ん）のような読み方で的を
                # 取りこぼす（元からの用心）。**音便は語幹と活用語尾が
                # 融合した形**なので、そこだけは他の読み方に化けない:
                #
                #     やってる ＝ **や**（やる）＋っ＋て＋る
                #     しってる ＝ **し**（知る）／まってて ＝ **ま**（待つ）
                #     よんどく ＝ **よ**（読む）＋ん＋どく
                #
                # 白名簿（`_BASIC_STEMS_1`）は今までどおり全部の活用を許す。
                #
                # **サ変の連用形 `し`**（項目48-PS・2026-09-03）。
                # `する` は**1字の語幹を持つ唯一の動詞**で、
                # `して`・`した`・`します`・`し**てんの**` はどれも
                # 正しい形。白名簿に足すと五段の推定まで開いてしまう
                # （`しる`＝知る の活用が全部立つ）ので、**ここだけ**の
                # 閉じた枝にする。これが無いと `してんの` が説明できず、
                # 芯の再構築が **`進展の`** にしていた（初期で実測）。
                if stem == 'し':
                    stack.append((j, 'R'))
                _onbin_only = (ln < 2 and stem not in _BASIC_STEMS_1)
                if _onbin_only and run[j] not in 'っん':
                    continue
                c2 = run[j]
                for u, row in _GODAN_ROW.items():
                    if (stem + u) not in words:
                        continue
                    a, i_, e, o, onb = row
                    if stems_only and u != 'る' and (stem + i_) not in words:
                        continue                  # 連用形が無い＝用言ではない
                    if _onbin_only:
                        if onb and c2 == onb:
                            stack.append((j + 1,
                                          'TSU' if onb != 'ん' else 'N'))
                        continue
                    if c2 == u:
                        stack.append((j + 1, 'Ev' if stems_only else 'END'))
                    if c2 == a:
                        stack.append((j + 1, 'MZ'))
                    if c2 == i_:
                        stack.append((j + 1, 'R'))
                    if c2 == e:
                        stack.append((j + 1, 'E'))
                    if onb and c2 == onb:
                        stack.append((j + 1, 'TSU' if onb != 'ん' else 'N'))
                    if c2 == o and j + 1 < n and run[j + 1] == 'う':
                        stack.append((j + 2, 'Ev' if stems_only else 'END'))
                    if u == 'る' and stem[-1] in _ICHIDAN_TAIL:
                        stack.append((j, 'E'))
    return False


def _is_hira(c):
    return 'ぁ' <= c <= 'ゖ' or c == 'ー'


def _is_kanji(c):
    return '一' <= c <= '鿿'


def _is_kata(c):
    return 'ァ' <= c <= 'ヶ'


def _exclamation_shape(run):
    """
    **擬音・かけ声・伸ばしの形**か（印を立てない側の門）。

    実機メモにはセリフ・鳴き声の材料がある（うほうほ・ふぎゃー・
    月夜さまーっ・ふぇぇん）。どれも語の表では説明が付かないが、
    **形そのものが「声」**であって誤字ではない。閉じた形で除く:

      ・2字2回（うほうほ・わうわう——ABAB は補正の道が別に持つ）
      ・末尾が促音・長音（かくごっ・ふぎゃー——叫び・伸ばし）
      ・小書きの母音を含む短いもの（くぅーん・ふぇぇん）
      ・短くて長音を含む（どりーん・すりーぷ）
    """
    if len(run) == 4 and run[:2] == run[2:]:
        return True
    if run[-1] in 'っー':
        return True
    if run.endswith('ーん'):
        return True                      # どりーん・つんぼよーん
    if len(run) <= 5 and any(c in 'ぁぃぅぇぉ' for c in run):
        return True
    if len(run) <= 4 and 'ー' in run:
        return True
    return False


def odd_kana_spans(line, dict_index=None, store=None):
    """
    **行の中の、説明の付かない ひらがな連続**（項目48-KS の①-a）。

    紫の印にするための位置 [(始まり, 終わり), ...] を返す。
    敷居（**紫は答えを変えないが、出しすぎは害**・48-GL）:

      ・4字未満は見ない（短い断片は文脈が足りない）
      ・末尾2字が同じ字・擬音やかけ声の形は見ない（じゅるる・ふぎゃー）
      ・連続まるごとが**世の中の語の読み**なら黙る（にゅうりょく——
        かなで書いただけの正しい語。dict_index が居るときだけ引ける）
      ・語は 表＋辞書の索引＋本人の語彙 から引く（きちんと・ぴたり は
        表に無いが辞書に在る。本人が学習させた語も語彙で守られる）
      ・語の表・機能語・活用の文法のどれでも説明が付かないものだけ
    """
    if not line:
        return []
    out0 = []
    if dict_index is not None and store is not None and 'ー' in line:
        from reading_segments import odd_partial_loanwords
        from corrector import make_tokenizer
        out0.extend((a,b) for a,b,_h,_t,_s in
                    odd_partial_loanwords(line,dict_index,store,make_tokenizer(store)))
    # 48-WM: 小書き母音は口語の語尾・文字の言及にも現れるため、
    # 前接文字だけでは異様と断定しない。拗音の構造判定は分けて残す。
    # 促音っは送り仮名にも使うので従来どおり対象外。
    for p, c in enumerate(line):
        if c not in 'ゃゅょ':
            continue
        prev = line[p - 1] if p > 0 else ''
        if not prev or _is_hira(prev) or prev == 'ー' \
                or prev in '「『（(［[｛{【〔・　 \t':
            continue
        out0.append((p - 1, p + 1))

    def _is_word(frag):
        if len(frag) < 2:
            return False
        if dict_index is not None:
            try:
                if dict_index.readings_for_surface(frag):
                    return True
            except Exception:
                pass
        if store is not None:
            try:
                if store.reading_of(frag):
                    return True
            except Exception:
                pass
        return False

    out = out0
    n = len(line)
    i = 0
    while i < n:
        if not _is_hira(line[i]):
            i += 1
            continue
        j = i
        while j < n and _is_hira(line[j]):
            j += 1
        run = line[i:j]
        i0, i = i, j
        if len(run) < 4:
            continue
        if run[-1] == run[-2]:
            continue                     # じゅるる・じゅるるー
        if _exclamation_shape(run):
            continue
        prev = line[i0 - 1] if i0 > 0 else ''
        nxt = line[j] if j < n else ''
        # カタカナの直後も語幹の続き（カシコ**し**・ググ**った**・
        # サボ**り**——カタカナ語も活用するし、カタカナ＋かなで
        # 1語の表記もある）
        after = bool(prev) and (_is_kanji(prev) or _is_kata(prev)
                                or prev.isdigit() or '０' <= prev <= '９')
        before = bool(nxt) and _is_kanji(nxt)
        stem = ''
        if after and (_is_kanji(prev) or _is_kata(prev)):
            k = i0
            same = _is_kanji if _is_kanji(prev) else _is_kata
            while k > 0 and same(line[k - 1]):
                k -= 1
            stem = line[k:i0]
        # **本当の行頭**（前に空白しか無い）に立つ連続だけ、裸の1字助詞を
        # 頭に置かない（項目48-RZ。読点・括弧のあとは前の句を受ける形）
        _bare = (not after) and not line[:i0].strip(' \t\u3000')
        try:
            ok = explain_kana_run(run, after_kanji=after,
                                  before_kanji=before, kanji_stem=stem,
                                  is_word=_is_word, bare_head=_bare)
        except Exception:
            ok = True
        if not ok and dict_index is not None:
            # かなで書いただけの、世の中に在る語（にゅうりょく）
            try:
                if dict_index.is_world_reading(run):
                    ok = True
            except Exception:
                pass
        # 前の名詞と読点が、かな単独の解析で失われた並列を説明する。
        # 補正側の共通入口と同じ判定を使い、印だけを後から隠さない。
        if not ok and len(run)>=4 and run[-2]=='と':
            try:
                from corrector import _comma_nominal_context, make_tokenizer
                if _comma_nominal_context(line,i0,run,make_tokenizer(store)):
                    ok=True
            except Exception:
                pass
        if not ok and not after:
            from reading_segments import short_nominal_reading
            if short_nominal_reading(run):
                ok = True
        if not ok:
            out.append((i0, j))
    return out


def world_covered(text, dict_index):
    """
    **世の中の読み（2字以上・刈り込む前）と機能語で、すき間なく
    敷き詰められるか**（項目48-KV の確かめ・④の物差し）。

    `にゅうりょくみす` ＝ にゅうりょく（入力）＋みす（ミス）→ True。
    `にゆうりよくみす`（大書き）→ どこも読みにならない → False。
    dict_index が無ければ False（意見なし＝手は動かない）。
    """
    if not text or dict_index is None:
        return False
    _w, funcs, p1 = _load_tables()
    n = len(text)
    ok = [False] * (n + 1)
    ok[0] = True
    for i in range(n):
        if not ok[i]:
            continue
        if text[i] in p1:
            ok[i + 1] = True
        for ln in range(2, min(10, n - i) + 1):
            frag = text[i:i + ln]
            if frag in funcs:
                ok[i + ln] = True
                continue
            try:
                if dict_index.is_world_reading(frag):
                    ok[i + ln] = True
            except Exception:
                pass
    return ok[n]


if __name__ == '__main__':
    print(__doc__)
