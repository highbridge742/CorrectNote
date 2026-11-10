# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳（GPL-3.0-or-later・ヘッダは keystroke_doubt.py と同じ）
"""品詞の並びで必ず誤りになる所を紫にする（2026-11-05 かな入力の担当・作った文の誤字の試験の見逃しから）。

文法の閉じた決まりだけを見る（特定の語や文字列には合わせない）:
  (a) 格助詞・係助詞のすぐ後ろの接尾（名詞:接尾 は前に名詞が要る）      書類を｜ら｜提出して
  (b) 文の途中（行頭・句読点・記号の直後でない所）の1字の平仮名の感動詞    毎朝｜う｜少し歩く
  (c) 名詞に付いた です・だ（終止）のすぐ後ろの自立の動詞・形容詞          家族｜です話し｜合った
  (d) 行の中で開きの無い閉じ括弧（行末でなく、後ろに文が続くもの）          見積もりは｜）｜を確認
  (e) 名詞のすぐ後ろの非自立の ん（な・の を挟まない）                       家族｜ん｜で話し合った
  (f) 接続詞のすぐ後ろの格助詞                                               商品が｜又で｜届いて
  (g) 文末の ます のすぐ後ろの は・を・に・の                                 取っておき｜ますは
  (h) 名詞のすぐ後ろの助動詞 う（う は動詞・助動詞の未然形に付く）             予定｜う｜です
  (i) 終助詞 よ・ね・わ・ぞ・ぜ のすぐ後ろの接続助詞 て・で                      通う｜よて｜いです
  (j) 格助詞と自立の動詞の間の、片仮名1字だけの名詞                            ゲームを｜ラ｜する
  (n) 文の終わりの接続詞で、前が 格助詞＋名詞                               連絡を｜四肢｜また（2026-11-07）
  (o) 副助詞のすぐ後ろの ください                                          だって｜ください（2026-11-07）
  (m) 自立の動詞の終止形のすぐ後ろの を                                       フフ行く｜を｜出した（2026-11-07）
  (l) 名詞のすぐ後ろの接続助詞 ので・のに（な・だ を挟まない）                台所｜ので｜金を（2026-11-07）
  (p) 動詞に付く助動詞が名詞・助詞のすぐ後ろ                                 相談｜た・駆使｜ました（2026-11-07）
  (k) かなとして続かない小書き（お｜ゃ）・付く先の無い ゛゜（kana_rules.bad_spots の 続き・濁点）  おゃく様・休たん゛
直し先は決めない（抜く字か打ち違いかは分からない）ので紫だけ。補正が既に直した行・紫のある所は触らない。
説明書の文669と作った正しい文140で当たり0。切り替え CN_POS_SEQ_ODD=0。
"""
import os

_STOP = set('。、，．！？!?　 「」『』（）()…・')
_VAUX = ('た', 'ます', 'まし', 'ませ', 'れる', 'られる', 'せる', 'させる', 'ず', 'ぬ', 'る', 'つ')


def _hira(s):
    return bool(s) and all('ぁ' <= c <= 'ゖ' for c in s)


def _wordish(s):
    """～ ー などの記号だけの「名詞」でない（中身が～ん・も～う は話し言葉の伸ばし）"""
    return any(c not in '～〜ー－-' for c in s)


def _kata(s):
    return bool(s) and all('ァ' <= c <= 'ヺ' or c == 'ー' for c in s)


def _suffix_alone(line, toks, i):
    """(a) の接尾が本当に前の語から離れているか。平仮名・片仮名の接尾は、前後に続く平仮名の並びが3字までの時だけ
    （さかさま・ことがら は平仮名の語の切り違い）。漢字の接尾は、後ろが助詞・助動詞・記号・行末なら1語の名詞の
    使い方（的に・後を）なので除く（例文4万文で31→1、2026-11-07。CN_POS_SEQ_SUFFIX_OLD=1 で前のまま）。"""
    if os.environ.get('CN_POS_SEQ_SUFFIX_OLD') == '1':
        return True
    t = toks[i]
    if _hira(t.surface) or _kata(t.surface):
        a, b = t.start, t.end
        while a > 0 and _hira(line[a - 1]):
            a -= 1
        while b < len(line) and _hira(line[b]):
            b += 1
        return b - a <= 3
    nx = toks[i + 1] if i + 1 < len(toks) else None
    return not (nx is None or nx.pos in ('助詞', '助動詞', '記号'))


def spots(line):
    """[(start, end, 理由)]"""
    from morphology import tokenize
    toks = list(tokenize(line))
    out = []
    for i, t in enumerate(toks):
        p = toks[i - 1] if i else None
        head = p is None or p.surface in _STOP or p.pos == '記号'
        if (t.pos == '名詞' and (t.pos_sub or '').startswith('接尾') and p is not None and p.pos == '助詞'
                and p.end == t.start and _suffix_alone(line, toks, i)):
            out.append((t.start, t.end, f'「{p.surface}」のすぐ後ろに接尾の「{t.surface}」は続きません'))
        elif t.pos == '感動詞' and len(t.surface) == 1 and _hira(t.surface) and not head:
            out.append((t.start, t.end, f'文の途中の「{t.surface}」は前後の語とつながりません'))
        elif (p is not None and p.pos == '助動詞' and p.surface in ('です', 'だ') and p.end == t.start
              and not (i >= 2 and toks[i - 2].pos in ('動詞', '形容詞', '助動詞'))
              and t.pos in ('動詞', '形容詞') and (t.pos_sub or '').startswith('自立')
              and not (_hira(t.surface) and t.surface.endswith('っ'))):
            out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「{t.surface}」は続きません'))
    # (n) 行（文）の終わりの接続詞で、前が 格助詞＋名詞（連絡を｜四肢｜また）
    if os.environ.get('CN_POS_SEQ_ENDCONJ') != '0':
        for i, t in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if (t.pos == '接続詞' and (nxt is None or nxt.surface in _STOP) and i >= 2
                    and toks[i - 1].pos == '名詞' and toks[i - 2].pos == '助詞'
                    and (toks[i - 2].pos_sub or '').startswith('格助詞')):
                out.append((toks[i - 1].start, t.end, f'文の終わりの「{t.surface}」は前の語とつながりません'))
    for i, t in enumerate(toks):
        p = toks[i - 1] if i else None
        if p is None or p.end != t.start:
            continue
        if t.surface == 'ん' and t.pos == '名詞' and (t.pos_sub or '').startswith('非自立') and p.pos == '名詞' and _wordish(p.surface):
            out.append((t.start, t.end, f'「{p.surface}」のすぐ後ろに「ん」は続きません'))
        elif (p.pos == '助詞' and (p.pos_sub or '').startswith('終助詞') and p.surface in ('よ', 'ね', 'わ', 'ぞ', 'ぜ')
              and t.pos == '助詞' and t.pos_sub == '接続助詞' and t.surface in ('て', 'で')):
            out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「{t.surface}」は続きません'))
        elif (len(t.surface) == 1 and 'ァ' <= t.surface <= 'ヶ' and t.pos == '名詞' and p.pos == '助詞'
              and (p.pos_sub or '').startswith('格助詞') and i + 1 < len(toks) and toks[i + 1].start == t.end
              and toks[i + 1].pos == '動詞' and (toks[i + 1].pos_sub or '').startswith('自立')):
            out.append((t.start, t.end, f'「{p.surface}」と「{toks[i + 1].surface}」の間の「{t.surface}」は語になりません'))
        elif (t.surface in ('ので', 'のに') and t.pos == '助詞' and t.pos_sub == '接続助詞' and p.pos == '名詞'
              and not (p.pos_sub or '').startswith('非自立') and os.environ.get('CN_POS_SEQ_NODE') != '0'):
            # (l) 名詞のすぐ後ろの接続助詞 ので・のに（な・だ を挟まない: 台所｜ので）
            out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「{t.surface}」は続きません'))
        elif (t.surface == 'を' and t.pos == '助詞' and p.pos == '動詞' and (p.pos_sub or '').startswith('自立')
              and getattr(p, 'infl_form', '') == '基本形' and os.environ.get('CN_POS_SEQ_VO') != '0'
              and not (i + 1 < len(toks) and toks[i + 1].base_form in ('得る', '得'))
              and not _names_command(toks, i)):
            # (m) 自立の動詞の終止形のすぐ後ろの を（の を挟まない: 行く｜を｜出した。〜するを得ない は除く）
            out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「を」は続きません'))
        elif (t.surface in ('ください', '下さい') and t.pos == '動詞' and p.pos == '助詞'
              and (p.pos_sub or '').startswith('副助詞') and p.surface in ('だって', 'でも', 'さえ', 'こそ', 'すら')
              and os.environ.get('CN_POS_SEQ_KUDASAI') != '0'):
            # (o) 副助詞のすぐ後ろの ください（て・を を挟まない: つて｜だって｜ください）
            out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「{t.surface}」は続きません'))
        elif t.surface == 'う' and t.pos == '助動詞' and p.pos == '名詞' and _wordish(p.surface):
            out.append((t.start, t.end, f'「{p.surface}」のすぐ後ろに「う」は続きません'))
        elif (p.pos == '接続詞' and t.pos == '助詞' and (t.pos_sub or '').startswith('格助詞') and t.surface != 'って'
              and not (t.surface in ('という', 'といった', 'とは') and os.environ.get('CN_POS_SEQ_TOIU') != '0')
              and not (len(p.surface) >= 2 and all('一' <= c <= '鿿' for c in p.surface))
              and not _also_common_noun(p.surface)):
            # 一方で（名詞の使い方）・だからって は除く。辞書が一般名詞としても持つ語（ただ＋で: 無料の意味）も除く
            out.append((p.start, t.end, f'接続詞「{p.surface}」のすぐ後ろに「{t.surface}」は続きません'))
        elif (p.pos == '助動詞' and p.surface == 'ます' and t.surface in ('は', 'を', 'に', 'の') and t.pos == '助詞'
              and (i + 1 == len(toks) or toks[i + 1].surface in _STOP)):
            out.append((p.start, t.end, f'「ます」のすぐ後ろに「{t.surface}」は続きません'))
    # (p) 動詞に付く助動詞が名詞・助詞のすぐ後ろ（相談｜た・駆使｜まし・まで｜る）。
    # 正しい文1,004行と例文（Tatoeba）8万文で当たり0〜1・作った誤字の文で約45（2026-11-07）
    if os.environ.get('CN_POS_SEQ_AUX') != '0':
        for i, t in enumerate(toks):
            p = toks[i - 1] if i else None
            if p is None or p.end != t.start or any(a < t.end and p.start < b for a, b, _ in out):
                continue
            ps = p.pos_sub or ''
            if t.pos == '助動詞' and ((t.surface == 'た' and p.pos == '名詞' and not ps.startswith('数'))
                                     or (t.surface in ('ます', 'まし', 'ませ') and p.pos == '名詞')
                                     or (t.surface in _VAUX and p.pos == '助詞' and p.surface not in ('て', 'で', 'だけ', 'って')
                                         and t.surface != 'た' and (t.surface != 'つ' or (ps.startswith('格助詞') and p.surface != 'の'))
                                         and not (t.surface == 'まし' and (i + 1 == len(toks) or toks[i + 1].surface in _STOP)))) \
                    and not (t.surface == 'た' and any('ァ' <= c <= 'ヺ' for c in p.surface)):
                # て・で＋ます（知ってます）、片仮名の入った語＋た（キレた）、あなたがた・よりはまし は除く
                out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「{t.surface}」は続きません'))
    # (q) 行（文）の終わりで、を のすぐ後ろの名詞で終わる（絵を｜民）・(s) 自立の動詞の終止形＋名詞で終わる（持つ｜抵抗）。
    # (r) 助詞のすぐ後ろの ずつ（は｜ずつ｜と: 大きい つ の打ち違い）。例文（Tatoeba）6千文で (q)(r) 0・(s) 2（2026-11-07）
    if os.environ.get('CN_POS_SEQ_END_NOUN') != '0':
        def _end_after(k):
            return k + 1 >= len(toks) or (toks[k + 1].surface in ('。', '！', '？', '!', '?') and k + 2 >= len(toks))
        for i, t in enumerate(toks):
            p = toks[i - 1] if i else None
            if p is None or p.end != t.start or any(a < t.end and p.start < b for a, b, _ in out):
                continue
            ps, ts = p.pos_sub or '', t.pos_sub or ''
            if (t.pos == '名詞' and ts.split(':')[0] in ('一般', 'サ変接続') and _end_after(i)
                    and ((p.surface == 'を' and p.pos == '助詞'
                          # を＋サ変の名詞で終わる（機能を追加・設定を変更）は、する を略したメモ・見出しの正しい形
                          # （2026-11-09 うに 未解決タブの誤判定の行）。CN_POS_SEQ_WO_SAHEN=0 で前のまま
                          and not (ts.startswith('サ変接続') and os.environ.get('CN_POS_SEQ_WO_SAHEN') != '0'))
                         or (p.pos == '動詞' and ps.startswith('自立') and getattr(p, 'infl_form', '') == '基本形'
                             and len(t.surface) >= 2))):
                out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろの「{t.surface}」で文が終わります'))
            elif t.surface == 'ずつ' and t.pos == '助詞' and p.pos == '助詞':
                out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「ずつ」は続きません'))
            elif (os.environ.get('CN_POS_SEQ_NOUN_TE') != '0' and t.pos == '助詞'
                  and ((t.surface == 'て' and p.pos == '名詞'
                        and ps.split(':')[0] not in ('形容動詞語幹', '非自立', '接尾', '代名詞'))
                       or (p.surface in ('が', 'を') and ps.startswith('格助詞') and ts.startswith('格助詞')
                           and t.surface in ('と', 'に', 'で', 'を', 'が')))):
                # (t) 名詞のすぐ後ろの接続助詞 て（待つ｜手｜て・億｜就｜て）・(u) が・を のすぐ後ろの格助詞（手紙が｜と｜説いた）。
                # 例文 Tatoeba 6千文で当たり0（2026-11-07）
                out.append((p.start, t.end, f'「{p.surface}」のすぐ後ろに「{t.surface}」は続きません'))
    try:
        import kana_rules
        for k, why in kana_rules.bad_spots(line):
            if why in ('続き', '濁点') and not any(x <= k < y for x, y, _ in out):
                a0 = k - 1 if why == '続き' and k > 0 else k
                out.append((a0, k + 1, '小書きの字が前の字に続きません' if why == '続き' else '「゛」「゜」の付く字がありません'))
    except Exception:
        pass
    # (d) 開きの無い閉じ括弧（前の行から続く括弧は行末か直後が句読点のことが多いので、前後に文字が続くものだけ）
    pairs = {'）': '（', ')': '(', '」': '「', '』': '『', '】': '【', '］': '［'}
    depth = {}
    for k, c in enumerate(line):
        if c in pairs.values():
            depth[c] = depth.get(c, 0) + 1
        elif c in pairs:
            o = pairs[c]
            if depth.get(o, 0):
                depth[o] -= 1
            elif k > 0 and k + 1 < len(line) and line[k + 1] not in _STOP and line[k - 1] not in _STOP \
                    and not any(a <= k < b for a, b, _ in out):
                out.append((k, k + 1, f'「{c}」の前に「{o}」がありません'))
    return out


# 操作の名前（メニューの項目・ボタン）を選ぶ・押す動詞。動詞の終止形＋を の後ろにこれが来る（消すを選ぶ・
# 保存するをクリック）なら、動詞は項目の名前として書かれている
_PICK_VERBS = ('選ぶ', '押す', '選択', 'クリック', 'タップ', '実行', '指定', 'チェック')


def _names_command(toks, i):
    """toks[i] の を の後ろが、項目を選ぶ・押す動詞（選びます・押す・クリックする）なら True（2026-11-09 うに 誤判定:
    右クリックして消すを選びます の 消す を 外科 にしていた）。CN_POS_SEQ_VO_COMMAND=0 で前のまま。"""
    if os.environ.get('CN_POS_SEQ_VO_COMMAND') == '0' or i + 1 >= len(toks):
        return False
    n = toks[i + 1]
    return (n.base_form or n.surface) in _PICK_VERBS or n.surface in _PICK_VERBS


def _in_world_kana_word(line, a, b, dict_index):
    """[a, b) を含むひらがなの連続が、まるごと世の中の語の読み（とんかつ: 解析は とん｜かつ と割る）か。"""
    if dict_index is None or os.environ.get('CN_POS_SEQ_WORLD_KANA') == '0':
        return False
    i, j = a, b
    if not _hira(line[a:b]):
        return False
    while i > 0 and _hira(line[i - 1]):
        i -= 1
    while j < len(line) and _hira(line[j]):
        j += 1
    run = line[i:j]
    try:
        # 連続の頭から、または尾までの、[a, b) を覆う3字以上の語の読み
        for x in range(i, a + 1):
            for y in range(max(b, x + 3), j + 1):
                if (x == i or y == j) and dict_index.is_world_reading(line[x:y]):
                    return True
    except Exception:
        return False
    return False


def _left_alone(line, decisions):
    """紫を立てない所: 記述の対象（「〜」と入力します 等・literal_examples）と、うにさんが「もう直さない」と決めた文字列
    （decisions.left_alone_texts・決めた側が上）。"""
    out = []
    try:
        import literal_examples
        out += list(literal_examples.protected_ranges(line))
    except Exception:
        pass
    try:
        for w in (decisions.left_alone_texts() if decisions is not None else ()):
            if not w:
                continue
            k = line.find(w)
            while k >= 0:
                out.append((k, k + len(w)))
                k = line.find(w, k + 1)
    except Exception:
        pass
    return out


def mark_line(line, result, dict_index=None, decisions=None):
    if os.environ.get('CN_POS_SEQ_ODD') == '0' or not isinstance(result, dict):
        return result
    if (result.get('corrected') or line) != line:
        return result
    try:
        found = spots(line)
    except Exception:
        return result
    # かなの語の読みの中に立った印は外す（このお店でとんかつを: とん｜かつ＋を・2026-11-07 例文 Tatoeba）
    found = [f for f in found if not _in_world_kana_word(line, f[0], f[1], dict_index)]
    keep = _left_alone(line, decisions)
    found = [f for f in found if not any(x < f[1] and f[0] < y for x, y in keep)]
    taken = [tuple(x[:2]) for x in list(result.get('odd_spans') or ()) + list(result.get('unsure_spans') or ())]
    add = [(a, b, why) for a, b, why in found if not any(x < b and a < y for x, y in taken)]
    if not add:
        return result
    out = dict(result)
    out['odd_spans'] = sorted(set(taken) | {(a, b) for a, b, _ in add}) if not result.get('unsure_spans') else \
        list(result.get('odd_spans') or ()) + [(a, b) for a, b, _ in add]
    out['odd_reasons'] = list(result.get('odd_reasons') or ()) + add
    return out


def _also_common_noun(surface):
    """辞書がこの表記を一般名詞としても持つか（ただ: 接続詞・副詞・名詞）。CN_POS_SEQ_CONJ_NOUN=0 で前のまま（偽）。
    2026-11-09 補正担当の正しい文の試し（ただで差し上げます）。"""
    if os.environ.get('CN_POS_SEQ_CONJ_NOUN') == '0':
        return False
    try:
        from morphology import dictionary_inflections
        return any(r[0].startswith('名詞,一般') for r in (dictionary_inflections(surface) or ()))
    except Exception:
        return False
