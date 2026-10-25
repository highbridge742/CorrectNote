# -*- coding: utf-8 -*-
"""
**読みの格子**（かな → 表記の最短路・2026-10-25・スレッド「補正の新しい手を検討」）。

Janome は辞書を**表記**で引くので、平仮名だけの所は語が見つからず切れ端に割れる
（などにしたばあい → など|に|し|た|ば|あい）。ここでは同じ IPA 辞書を**読み**で引き、
同じ辞書の**連接の表**（品詞どうしのつながりの費用）で最短路を取る。

材料（新しい同梱は要らない）
----
- 語: `janome.sysdic.entries()` の (表記, 左id, 右id, 費用, 品詞, …, 読み[8])
- 連接: `janome.sysdic.connections`（1316×1316）

読みの表（読み → 表記の並び）は初回に Janome から作り、`cache_path`
（既定はこのファイルの隣の `reading_lattice_table.pickle.gz`・約4MB・作るのに約3秒）に控える。
Janome の版か `TABLE_VERSION` が変われば作り直す。手で作り直すときは `py reading_lattice.py --build`。
控えが書けない所（読み取り専用）でも動く（毎回メモリで作るだけ）。

使い方
------
    import reading_lattice as rl
    r = rl.best('がいこくのりょうり')
    r.words  -> [('外国','がいこく','名詞',()), ('の','の','助詞',()), ('料理','りょうり','名詞',())]
    r.cost   -> 費用（小さいほど自然）
    rl.best(kana, neighbors=fn, max_edit=1)   # 1打の辺つき（fn(ch) -> [(替わりの字, 距離)]）
    rl.margin(kana, neighbors=fn)            # (そのままの費用 - 直しの費用, そのまま, 直し)

- 切り方は強いが表記の選びは弱い（下さい/ください・永い/長い・文書+雨/文章）。
  表記は呼ぶ側の物差しで選び直す前提。`segments()` は読みの切り方だけを返す。
- 打ち違いの辺: 置き換え SUB_BASE+SUB_PER_DIST×距離、余分な1打 EXTRA、隣どうしの入れ替わり SWAP。
  1語に1つまで。打ち落とし（足す辺）は入れていない。隣の字は呼ぶ側が渡す
  （かな入力なら kana_layout.nearby_candidates、ローマ字なら打鍵単位の隣）。
- 費用の数は未調整（雲の試作 2026-10-25: 差3000以上で決めると正しい606行で変える4）。
"""
import gzip
import os
import pickle
import re

TABLE_VERSION = 2   # 2: 表を janome_import と同じ読み方で作る（2026-10-25）
SUB_BASE, SUB_PER_DIST, EXTRA, SWAP = 3000, 1500, 3500, 3500
UNKNOWN_COST = 10000          # 辞書に無い1字
UNKNOWN_ID = 1285             # 名詞,一般 の左右id（未知の1字の置き場）
KATAKANA_PENALTY = 2500       # 平仮名で打った所に片仮名の表記を置く重さ
_KATA = re.compile('[ァ-ヶ]')

_table = None   # 読み -> [(表記, 左id, 右id, 費用, 品詞の大分類)]
_trie = None
_conn = None


def _hira(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in text)


def _janome_version():
    try:
        import janome
        return getattr(janome, '__version__', '') or ''
    except Exception:
        return ''


CACHE_NAME = 'reading_lattice_table.pickle.gz'


def default_cache_path():
    # The app's data folder (app.app_dir(), handed down as CORRECTNOTE_DATA_DIR by app.main so the analysis
    # children see it too): beside the exe, or the package's own folder under MSIX, whose install folder is
    # read-only. A frozen build without it uses the temp folder, never its unpack folder; from source, beside
    # this file (2026-10-25).
    import sys
    folder = os.environ.get('CORRECTNOTE_DATA_DIR')
    if not folder:
        if getattr(sys, 'frozen', False):
            import tempfile
            folder = tempfile.gettempdir()
        else:
            folder = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(folder, CACHE_NAME)


def build_table():
    """読み → [(表記, 左id, 右id, 費用, 品詞)]。janome の辞書モジュールを DictIndex（janome_import.iter_janome_entries）と
    同じ読み方で1組ずつ読み、読み終えたら手放す。`janome.sysdic.entries()` でまとめて読むと、その後に同じプロセスで作る
    DictIndex が空になった（挙動関連担当 2026-10-25・tools_local/lattice_memtest_20261025）。"""
    import importlib, sys
    from janome_import import _find_data, _iter_items, _get_item, _parse_extra, _parse_extra_pos
    table = {}
    for part in range(10):
        names = ('janome.sysdic.entries_compact%d' % part, 'janome.sysdic.entries_extra%d' % part)
        ours = [n for n in names if n not in sys.modules]
        try:
            try:
                compact = importlib.import_module(names[0])
                extra = importlib.import_module(names[1])
            except Exception:
                continue
            cdata = _find_data(compact)
            edata = _find_data(extra)
            if cdata is None or edata is None:
                continue
            for key, comp in _iter_items(cdata):
                ex = _get_item(edata, key)
                if ex is None or not isinstance(comp, (tuple, list)) or len(comp) < 4:
                    continue
                reading = _parse_extra(ex)
                if not reading or reading == '*':
                    continue
                pos = (_parse_extra_pos(ex) or '').split(',')[0]
                table.setdefault(_hira(reading), []).append((comp[0], comp[1], comp[2], comp[3], pos))
        finally:
            for n in ours:
                sys.modules.pop(n, None)
                package = sys.modules.get('janome.sysdic')
                if package is not None:
                    package.__dict__.pop(n.rsplit('.', 1)[1], None)
    return table


def _build_table_entries():
    """元の作り方（janome.sysdic.entries()）。同じ表になるかの確かめ用。補正では使わない。"""
    import janome.sysdic as sysdic
    table = {}
    for v in sysdic.entries().values():
        reading = v[8] if len(v) > 8 else '*'
        if not reading or reading == '*':
            continue
        table.setdefault(_hira(reading), []).append((v[0], v[1], v[2], v[3], v[4].split(',')[0]))
    return table


def load(cache_path=None, rebuild=False, build=True):
    """読みの表と連接を用意する（2回目からは何もしない）。build=False なら控えから読むだけで、
    控えが無い・合わないときは作らずに戻る（解析の子の warmup 用。作るときの janome.sysdic.entries() の
    あとに同じプロセスで作る DictIndex が空になるため・2026-10-25）。"""
    global _table, _trie, _conn
    if _table is not None and not rebuild:
        return
    import janome.sysdic as sysdic
    path = cache_path or default_cache_path()
    stamp = (TABLE_VERSION, _janome_version())
    table = None
    if not rebuild:
        try:
            with gzip.open(path, 'rb') as f:
                got_stamp, got = pickle.load(f)
            if got_stamp == stamp:
                table = got
        except Exception:
            table = None
    if table is None:
        if not build:
            return
        table = build_table()
        try:
            tmp = path + '.tmp'
            with gzip.open(tmp, 'wb', compresslevel=6) as f:
                pickle.dump((stamp, table), f, protocol=4)
            os.replace(tmp, path)
        except Exception:
            pass
    trie = {}
    for k in table:
        node = trie
        for ch in k:
            node = node.setdefault(ch, {})
        node['$'] = k
    _table, _trie, _conn = table, trie, sysdic.connections


class Result(object):
    __slots__ = ('words', 'cost')

    def __init__(self, words, cost):
        self.words, self.cost = words, cost

    @property
    def surface(self):
        return ''.join(w[0] for w in self.words)

    @property
    def edits(self):
        return [e for w in self.words for e in w[3]]

    def __repr__(self):
        return 'Result(%s, %d, %s)' % ('/'.join(w[0] for w in self.words), self.cost, self.edits)


def _words_from(t, i, neighbors, max_edit):
    out = []

    def walk(node, j, ec, ne, ops):
        if '$' in node:
            out.append((j, node['$'], ec, tuple(ops)))
        if j >= len(t):
            return
        ch = t[j]
        if ch in node:
            walk(node[ch], j + 1, ec, ne, ops)
        if ne < max_edit:
            if neighbors is not None:
                for c, d in neighbors(ch):
                    if c != ch and c in node:
                        walk(node[c], j + 1, ec + SUB_BASE + int(SUB_PER_DIST * d), ne + 1,
                             ops + [('sub', j, ch, c)])
            walk(node, j + 1, ec + EXTRA, ne + 1, ops + [('extra', j, ch, '')])
            if j + 1 < len(t) and t[j + 1] in node and ch in node[t[j + 1]]:
                walk(node[t[j + 1]][ch], j + 2, ec + SWAP, ne + 1, ops + [('swap', j, ch + t[j + 1], t[j + 1] + ch)])

    walk(_trie, i, 0, 0, [])
    return out


def best(kana, neighbors=None, max_edit=0, word_cost=None):
    """かなの並びの最短路。word_cost(表記, 読み, 費用) -> 費用 で呼ぶ側が費用を足し引きできる
    （本人の確かな語を少し安くする等。上限は呼ぶ側で）。"""
    load()
    t = kana
    n = len(t)
    if n == 0:
        return Result([], 0)
    best_at = [dict() for _ in range(n + 1)]
    best_at[0] = {0: (0, [])}
    C = _conn
    for i in range(n):
        here = best_at[i]
        if not here:
            continue
        items = list(here.items())
        for j, key, ec, ops in _words_from(t, i, neighbors, max_edit):
            plain = not _KATA.search(key)
            for surf, l, r, cost, pos in _table[key]:
                if plain and _KATA.search(surf) and 'ー' not in key:
                    cost += KATAKANA_PENALTY
                if word_cost is not None:
                    cost = word_cost(surf, key, cost)
                pc, pp = min(((c + C[pr][l], p) for pr, (c, p) in items), key=lambda x: x[0])
                tot = pc + cost + ec
                if r not in best_at[j] or tot < best_at[j][r][0]:
                    best_at[j][r] = (tot, pp + [(surf, key, pos, ops)])
        pc, pp = min(((c + C[pr][UNKNOWN_ID], p) for pr, (c, p) in items), key=lambda x: x[0])
        tot = pc + UNKNOWN_COST
        if tot < best_at[i + 1].get(UNKNOWN_ID, (float('inf'),))[0]:
            best_at[i + 1][UNKNOWN_ID] = (tot, pp + [(t[i], t[i], '未知', ())])
    cost, path = min(((c + C[r][0], p) for r, (c, p) in best_at[n].items()), key=lambda x: x[0])
    return Result(path, cost)


def segments(kana):
    """読みの切り方だけ（[(読み, 品詞の大分類)]）。"""
    return [(w[1], w[2]) for w in best(kana).words]


def margin(kana, neighbors=None, max_edit=1, word_cost=None):
    """(そのままの費用 − 直しの費用, そのまま, 直し)。差が大きいほど直しが確か。"""
    plain = best(kana, None, 0, word_cost)
    fixed = best(kana, neighbors, max_edit, word_cost)
    return plain.cost - fixed.cost, plain, fixed


if __name__ == '__main__':
    import sys
    args = sys.argv[1:]
    if args[:1] == ['--build']:
        load(rebuild=True)
        p = default_cache_path()
        print(p, os.path.getsize(p) if os.path.exists(p) else 'not written')
        args = args[1:]
    for a in args:
        print(a, best(a))
