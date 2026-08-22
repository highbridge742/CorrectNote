# -*- coding: utf-8 -*-
"""
**全文ひらがな化 → 再変換の「測る道具」**（設計17段階A・項目48-FE）。

    py reconvert.py [λを並べる]          例: py reconvert.py 0 200 400 800

**これは道具です。アプリには繋がっていません。**
うにさんの問い (i)「すべて平仮名の文に直して、そこから漢字変換を
組み立てていくとうまくいかないか」を、**測れる形にしただけ**。

やること
--------
1行ずつ、**解析が言い切る読み**を並べて「ひらがなの列」を作り、
そこから**最短路**（Viterbi）で表記を組み直す。

    総コスト = Σ（語コスト） + λ × 語数

λ は「語を1つ増やすことの重さ」。大きくすると**長い語**が
選ばれやすくなる（`殺意`＋`代価` より `最大化` のような形）。
Fable 5 の指示どおり**連接コストの行列は持たない**。λ で代用する。

出すもの
--------
実機メモの全行について

    差 = （元の表記をそのまま読んだときの総コスト）
        − （最良経路の総コスト）

の**分布**。差が大きい行ほど「書かれているものより、もっと安い
読み方がある」＝**疑わしい**。報告するのは:

  - うにさんの「違和感」13件が**上位に来るか**
  - **正しい行が上位に混ざる率**（ここが本命。混ざるなら使えない）
  - λ ごとの表

**ここで止めて判断を仰ぐ**（段階B以降は分布を見てから）。

材料
----
`seed_japanese_cost.txt.gz`（読み → 表記＋語コスト）が在ればそれを
使う。無ければ **janome/IPAdic の語コスト**で代用する（同梱済みで
すぐ動くが、`具体的` `最大化` のような派生語を1語として持たないので
経路が細かく割れる）。**どちらを使ったか必ず出力に書く。**
"""
import gzip
import io
import json
import math
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) or '.')

COST_FILE = 'seed_japanese_cost.txt.gz'
COST_QUANT = 64           # 表の中のコストの刻み（build 側と揃える）
MAX_WORD = 8              # 1語として見る読みの最大長
UNKNOWN_COST = 20000      # どうしても読めない1字ぶんの罰

# うにさんの「文字列として違和感を感じるもの」（メモ 2026-08-18）
ODD = ['殺意代価', '最大家事', '再退化', '歳で以下', '差す代価',
       '誘い消化', '小売り坂', '居で以下', '素帰任', '野外文章',
       '簡易流力', '時ッ層', '目もち長']

# 的とその答え（うにさんのメモの `X ⇒ Y`）
TARGET_PAIRS = [
    ('殺意代価', '最大化'), ('最大家事', '最大化時'), ('再退化', '最大化'),
    ('歳で以下', '最大化'), ('差す代価', '最大化'), ('誘い消化', '最小化'),
    ('小売り坂', '効率化'), ('居で以下', '巨大化'), ('素帰任', '素材'),
    ('野外文章', '長い文章'), ('簡易流力', '簡易入力'),
]


def _kata2hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' and c != 'ー'
                   else c for c in s)


def load_costs():
    """
    読み → [(表記, コスト), ...] の表を用意する。

    戻り値: (表, どこから作ったかの説明)
    """
    here = os.path.dirname(os.path.abspath(__file__)) or '.'
    path = os.path.join(here, COST_FILE)
    if os.path.exists(path):
        table = {}
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for raw in f:
                parts = raw.rstrip('\n').split('\t')
                if len(parts) < 2:
                    continue
                rd = parts[0]
                items = []
                for p in parts[1:]:
                    s, _, c = p.rpartition(':')
                    if not s:
                        continue
                    try:
                        items.append((s, int(c) * COST_QUANT))
                    except Exception:
                        pass
                if items:
                    table[rd] = items
        if table:
            return table, f'{COST_FILE}（SudachiDict 由来・{len(table):,} 通り）'
    # 代用: janome/IPAdic
    from janome_import import iter_janome_entries
    table = {}
    for surface, reading, pos, sub, subsub, cost in \
            iter_janome_entries(min_len=1, max_len=MAX_WORD):
        if not reading or not surface or cost is None:
            continue
        rd = _kata2hira(reading)
        if not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in rd):
            continue
        table.setdefault(rd, []).append((surface, int(cost)))
    for rd in table:
        table[rd] = sorted(set(table[rd]), key=lambda x: x[1])[:8]
    return table, f'janome/IPAdic の語コスト（代用・{len(table):,} 通り）'


def best_path(reading, table, lam):
    """
    読みの列を、総コスト最小で表記に組み直す。

    総コスト = Σ語コスト + λ × 語数
    戻り値: (総コスト, 表記, 語の一覧)
    """
    n = len(reading)
    if n == 0:
        return 0, '', []
    INF = float('inf')
    best = [INF] * (n + 1)
    back = [None] * (n + 1)
    best[0] = 0
    for i in range(n):
        if best[i] == INF:
            continue
        for j in range(i + 1, min(n, i + MAX_WORD) + 1):
            piece = reading[i:j]
            items = table.get(piece)
            if items:
                s, c = items[0]
                cost = best[i] + c + lam
                if cost < best[j]:
                    best[j] = cost
                    back[j] = (i, s)
        # どうしても読めないときの逃げ道（1字ぶん）
        cost = best[i] + UNKNOWN_COST + lam
        if cost < best[i + 1]:
            best[i + 1] = cost
            back[i + 1] = (i, reading[i])
    if best[n] == INF:
        return INF, '', []
    out = []
    k = n
    while k > 0 and back[k] is not None:
        i, s = back[k]
        out.append(s)
        k = i
    out.reverse()
    return best[n], ''.join(out), out


def written_cost(words, table, lam):
    """
    **書かれているとおりに読んだときの総コスト**。

    解析が切った語をそのまま使う。表に無い語は罰を付ける
    （＝「その表記でその読みは、世の中では見かけない」）。
    """
    total = 0
    for surface, rd in words:
        items = table.get(rd)
        c = None
        if items:
            for s, cc in items:
                if s == surface:
                    c = cc
                    break
            if c is None:
                # 同じ読みの別表記はある＝表記のほうが珍しい
                c = items[0][1] + 4000
        if c is None:
            c = UNKNOWN_COST
        total += c + lam
    return total


def main():
    lams = [int(x) for x in sys.argv[1:]] or [0, 200, 400, 800, 1600]
    import corrector as C
    from vocabulary import VocabularyStore
    store = VocabularyStore(path='vocabulary.json')
    tok = C.make_tokenizer(store)
    table, where = load_costs()
    print(f'語コストの材料: **{where}**\n')

    here = os.path.dirname(os.path.abspath(__file__)) or '.'
    with open(os.path.join(here, 'session.json'), encoding='utf-8') as f:
        sess = json.load(f)

    # 1行ずつ「解析が言い切る読み」を作る（項目48-DE）
    rows = []
    for tab in sess.get('tabs', []):
        for line in (tab.get('text') or '').splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                toks = tok(s)
            except Exception:
                continue
            if not toks or not all(t[5] for t in toks):
                continue        # 読みを言い切れない行は測らない
            words = [(t[0], _kata2hira(t[2])) for t in toks]
            rd = ''.join(w[1] for w in words)
            if not rd or not all('ぁ' <= c <= 'ゖ' or c == 'ー'
                                 for c in rd):
                continue
            rows.append((s, rd, words))
    print(f'読みを言い切れた行 **{len(rows)}**（メモ全体から）\n')

    for lam in lams:
        diffs = []
        for s, rd, words in rows:
            w = written_cost(words, table, lam)
            b, surf, _ = best_path(rd, table, lam)
            if b == float('inf'):
                continue
            diffs.append((w - b, s, surf))
        diffs.sort(key=lambda x: -x[0])
        n = len(diffs)
        hit = [i for i, (d, s, _) in enumerate(diffs)
               if any(o in s for o in ODD)]
        top = diffs[:30]
        n_odd_top = sum(1 for d, s, _ in top if any(o in s for o in ODD))
        print(f'=== λ = {lam} ===')
        print(f'  測れた行 {n} / 差の中央値 '
              f'{diffs[n // 2][0] if n else 0} / 最大 '
              f'{diffs[0][0] if n else 0}')
        print(f'  **うにさんの的を含む行**: {len(hit)} 行、'
              f'順位 {[i + 1 for i in hit[:10]]}')
        print(f'  上位30に的が {n_odd_top} 行 → '
              f'**正しい行が上位に混ざる率 '
              f'{(30 - n_odd_top) * 100.0 / 30:.0f}%**')
        for d, s, surf in top[:6]:
            mark = ' ★的' if any(o in s for o in ODD) else ''
            print(f'    差{d:7d}{mark}  {s[:38]}')
            print(f'              → {surf[:38]}')
        print()

    # --- **いちばん大事な確かめ**（項目48-FE）---
    #
    # メモの中の的の行は `X ⇒ Y` という**見本の行**なので、
    # 分布だけ見ると測り方の都合が混じる。的を**ふつうの文**に
    # 置いて、最良経路が答えに届くかを1件ずつ見る。
    print('=== 的を、ふつうの文に置いて測る（λ = '
          f'{lams[len(lams) // 2]}）===')
    print('**読みを直さずに変換し直すだけで、答えに届くか**\n')
    lam = lams[len(lams) // 2]
    n_reach = 0
    for w, want in TARGET_PAIRS:
        line = f'{w}という並びです。'
        try:
            toks = tok(line)
        except Exception:
            toks = []
        if not toks or not all(t[5] for t in toks):
            print(f'  {w:8s} 読みを言い切れない')
            continue
        words = [(t[0], _kata2hira(t[2])) for t in toks]
        rd = ''.join(x[1] for x in words)
        wc = written_cost(words, table, lam)
        b, surf, _ = best_path(rd, table, lam)
        got = surf.replace('という並びです。', '')
        ok = (got == want)
        n_reach += 1 if ok else 0
        print(f'  {w:8s} 読み {rd[:14]:14s} 差 {wc - b:7d}  '
              f'→ {got:12s} {"○" if ok else "**×**"}（答え {want}）')
    print(f'\n  **答えに届いた {n_reach}/{len(TARGET_PAIRS)}**')
    print('  ※ 届かないのは、**読みそのものが壊れている**ため。')
    print('    最短路は「渡された読みを別の表記に読み直す」だけで、')
    print('    **読みを直しはしない**（`さいたいか` から `最大化`')
    print('    ＝`さいだいか` へは、原理的に行けない）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
