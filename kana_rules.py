# CorrectNote — 誤字補正メモ帳（GPL-3.0-or-later・ヘッダは keystroke_doubt.py と同じ）
"""
読み（ひらがな）の「あり得ない並び」（試作・2026-10-24）。

うにさん 2026-10-24 01:44Z「文頭文末の考え方は使ってなければ使いましょう。『ん』『を』から始まる文はないので、
それが先なら抜くのはその文字です。他にもルールが見つかるはず」。

字の名前を並べた決まりは書かず、同梱の語の表（seed_japanese_cost.txt.gz）から数えて決める。
重みは費用から exp(-費用/40)（よく使う語ほど重い）。1字の語（助詞のかけら）は頭・尾の数に入れない。
  頭に来ない字   2字以上の語の頭に来た割合が 1e-3 未満（数えると ぁぃぅぇぉゃゅょゎ ー ん を っ ぢ が下に固まり、次の ぞ は 2.2e-3）
  尾に来ない字   2字以上の語の尾に来た割合が 1e-4 未満（を・ゎ）
  文の頭        行の頭・句読点や空白の直後。ここに頭に来ない字があればあり得ない（漢字の直後は送り仮名があるので見ない）
  文の終わり     行の終わり・句読点の直前。ここに尾に来ない字があればあり得ない
  続かない2字    語の中で1度も続いたことがなく、後の字が頭に来ない字（語の切れ目を挟んでも続けられない）。
                 ただし後の字がそれだけで1字の語になる字（表に平仮名の1字の語として費用 130 未満で載っている字＝を 69・ん 119。
                 その次は ゎ 140・ょ 147・ぢ 150・っ 312 で、かけらの見出し）は除く
                 （を は助詞としてどの字の後にも来る）
  濁点・半濁点   字に付かずに残った ゛゜（付けられる字なら1字になっているので、残っていればあり得ない）
"""
import gzip, os, collections

_T = None
HEAD_RARE = 1e-3
TAIL_RARE = 1e-4
import math
_STOP = set('。、，．！？!?　 「」『』（）()…・')


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


def _kana(c):
    return 'ぁ' <= c <= 'ゖ' or c in 'ー゛゜'


def _load():
    global _T
    if _T is None:
        import corrector
        path = os.path.join(os.path.dirname(os.path.abspath(corrector.__file__)), 'seed_japanese_cost.txt.gz')
        head, tail, inside, single = collections.Counter(), collections.Counter(), set(), set()
        n = 0.0
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                parts = line.rstrip('\n').split('\t')
                rd = _hira(parts[0].lstrip('*'))
                if not rd or not all(_kana(c) for c in rd): continue
                for i in range(len(rd) - 1): inside.add(rd[i:i + 2])
                if len(rd) < 2:
                    for x in parts[1:]:
                        face, _, c = x.rpartition(':')
                        if face == rd and c.lstrip('-').isdigit() and int(c) < 130: single.add(rd)
                    continue
                try: cost = min(int(x.rsplit(':', 1)[1]) for x in parts[1:])
                except Exception: continue
                w = math.exp(-cost / 40.0)
                n += w; head[rd[0]] += w; tail[rd[-1]] += w
        chars = set(head) | set(tail) | {x for b in inside for x in b}
        no_head = {c for c in chars if head[c] / n < HEAD_RARE and c not in '゛゜'}
        no_tail = {c for c in chars if tail[c] / n < TAIL_RARE and c not in '゛゜'}
        _T = (no_head, no_tail, inside, single)
    return _T


def bad_spots(reading):
    """あり得ない所の一覧 [(位置, 種類)]。かな以外の字は語の切れ目とみる。"""
    no_head, no_tail, inside, single = _load()
    out = []
    s = reading
    for i, c in enumerate(s):
        if not _kana(c): continue
        if c in '゛゜':
            out.append((i, '濁点')); continue
        start = i == 0 or s[i - 1] in _STOP
        end = i + 1 == len(s) or s[i + 1] in _STOP
        if start and c in no_head: out.append((i, '頭'))
        if end and c in no_tail: out.append((i, '尾'))
        if i > 0 and _kana(s[i - 1]) and s[i - 1] not in '゛゜' and c in no_head and c not in single and s[i - 1] + c not in inside:
            out.append((i, '続き'))
    return out


def rules():
    no_head, no_tail, inside, single = _load()
    return ''.join(sorted(no_head)), ''.join(sorted(no_tail)), ''.join(sorted(no_head - single)), len(inside)
