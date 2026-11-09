"""IME の候補の順で、その漢字が「その読みで打って出た字」かを判定する（2026-11-08 うに 13:19Z・13:20Z）。

うに: 「IME に てん の候補を出しても 纏 が出るのはかなり優先度が低い。その見方から、これは てん と打って出た文字ではない
と考えるべき」「別の漢字の時でも、IME 優先度が高いか低いか、またはユーザーの IME 学習で優先度が高くなっていて出ることが
あるかを判定してください」。

- 候補の順: 辞書の表記を janome の費用の安い順に並べたもの（ime_reconvert._dict_faces）を IME の順の代わりに使う。
  雲には本物の IME が無いので、PC でも雲でも同じ答えになる材料だけで決める。
- 学習: 本人がその表記をその読みで確定した記録（kanji_guess.ime_readings_for）が在れば、IME が学習して上に出している
  と見て「その読みで出た字」とする。
- 出やすい読み: 表記がその読みの候補の上から IME_TOP 番以内で、しかも語として珍しくない（ime_reconvert._rank が
  RARE_WORD 未満）。珍しい語の読み（纏 = まとい）は、IME の先頭でも人がふだん打つ読みではない。

字に出やすい読みが1つも無ければ、その字は打った読みの字ではない（打ち違い・別の読みの字の選び違い）と見る。
切り替え CN_IME_ORDER=0 で使わない。
"""
import os
from functools import lru_cache

IME_TOP = 3        # 候補の上からこれ以内なら、その読みで出る字
RARE_WORD = 600    # wordfreq の段がこれ以上の語の読みは、ふだん打つ読みに数えない
COMMON_ONE = 470   # 置き換える1字の身近さ（段がこれ以下）
NEW_WORD = 600     # 置き換えてできる語の身近さ（段がこれ未満）


def on():
    return os.environ.get('CN_IME_ORDER') != '0'


def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s or '')


def _kanji(c):
    return '一' <= c <= '鿿' or c in '々〆'


def readings_of(ch):
    """字の読み（音訓の表の読みと、訓読みの語幹: まとい → まと）。"""
    try:
        import kanji_onkun
        rs = list(kanji_onkun.readings_of(ch))
    except Exception:
        rs = []
    out = []
    for r in rs:
        r = _hira(r).replace('-', '').replace('.', '')
        if r and r not in out:
            out.append(r)
    for r in list(out):
        # 送り仮名を付けて使う字は、語幹だけの読みで変換に出る（纏う・纏める の まと）
        if len(r) >= 3 and r[-1] in 'いうくすつぬふむゆるえけせてねへめれ':
            stem = r[:-1]
            if stem not in out:
                out.append(stem)
    return out


def learned(face, reading=None):
    """本人がこの表記を（この読みで）確定した記録が在るか: IME の学習で上に出ている。"""
    try:
        import kanji_guess
        got = [_hira(r) for r in kanji_guess.ime_readings_for(face)]
    except Exception:
        return False
    if reading is None:
        return bool(got)
    return any(r == reading for r in got)


@lru_cache(maxsize=4096)
def _top(reading):
    try:
        import ime_reconvert as R
        faces = R._dict_faces(reading, 40)
    except Exception:
        return ()
    # 漢字だけの表記を、世の中の使われやすさの順に（IME の候補の順はおおむね使われやすさの順）。
    # 片仮名・送り仮名付きは別の字の比べに入れない
    kan = [f for f in faces if all(_kanji(c) for c in f)]
    return tuple(sorted(kan, key=lambda f: (_rank(f), kan.index(f))))


def _rank(face):
    try:
        import ime_reconvert as R
        return R._rank(face)
    except Exception:
        return 800


def ime_plausible(face, reading):
    """この表記がこの読みで打って出る字か（IME の上の方・珍しくない語・または学習）。"""
    if learned(face, reading):
        return True
    faces = _top(reading)
    if face not in faces[:IME_TOP]:
        return False
    return _rank(face) < RARE_WORD


def unlikely_char(ch):
    """この1字の語は、どの読みで打っても IME からはまず出ない（学習も無い）か。"""
    if not on() or not ch or len(ch) != 1 or not _kanji(ch):
        return False
    if learned(ch):
        return False
    rs = readings_of(ch)
    if not rs:
        return False
    return not any(ime_plausible(ch, r) for r in rs)


def respell_faces(run, i, tail=''):
    """run（漢字の語の並び）の i 番目の1字を、同じ読み（別の読み・語幹を含む）で IME の先頭に出る身近な1字に替えて、
    1語として在る形になるものを返す。tail は並びの直後のかな（外れ の れ を含めて語になるかを見る）。
    返り値 [(置く表記（並びの分だけ）, 読み)]。"""
    try:
        import seed_japanese as S
    except Exception:
        return []
    ch = run[i]
    out = []
    for r in readings_of(ch):
        for c in _top(r)[:IME_TOP]:
            if len(c) != 1 or not _kanji(c) or c == ch or _rank(c) > COMMON_ONE:
                continue
            face = ''.join(run[:i]) + c + ''.join(run[i + 1:])
            ok = False
            for k in range(0, min(2, len(tail)) + 1):
                w = face + tail[:k]
                try:
                    if S.is_unit(w) is True and _rank(w) < NEW_WORD:
                        ok = True
                        break
                except Exception:
                    pass
            if ok and face not in [f for f, _ in out]:
                out.append((face, r))
    return out


KEY_COMMON = 480   # 1打を戻して届く語の身近さ（段がこれ以下）
MAX_READINGS = 48  # 並びの読みの組の上限


def _plausible_readings(ch):
    """この字を IME が上の方に返す読み。どれも無ければ字の読み全部（語幹を含む）。"""
    rs = readings_of(ch)
    good = [r for r in rs if ch in _top(r)[:IME_TOP]]
    return good or rs


def key_respell(parts, odd, before='', after=''):
    """並び（parts）の読みを組み、かなキーの1打を戻して身近な語（KEY_COMMON 以下）に届く表記を返す。
    odd[i] が真の字（IME の上に出ない字）は字の読み全部（語幹を含む）、他の1字は IME が上に返す読みで読む。
    組んだ読みそのものが語なら、IME はその語を返すので見ない（てんと → テント）。紫の所だけで使う。"""
    import itertools
    try:
        from contextual_repair import key_repairs
        import ime_reconvert as R
        from morphology import tokenize
    except Exception:
        return []
    choices = []
    for p, o in zip(parts, odd):
        if len(p) == 1 and _kanji(p):
            choices.append(readings_of(p) if o else _plausible_readings(p))
        else:
            choices.append([_hira(''.join(t.reading or t.surface for t in tokenize(p)))])
    face0 = ''.join(parts)
    out = []
    for combo in itertools.islice(itertools.product(*choices), MAX_READINGS):
        rd = ''.join(combo)
        if R._dict_faces(rd, 1):
            continue
        try:
            reps = key_repairs(rd, before, after)
        except Exception:
            continue
        for r in reps:
            r = getattr(r, 'reading', r)
            # 1字の打ち違い（同じ長さの読み）だけ: 抜け・足しは並びの区切りで揺れる（運痴 → 運）
            if len(r) != len(rd):
                continue
            nouns = {sf for sf, _l, _r, _c, pos in R._dict_table().get(r, ()) if pos == '名詞'}
            for f in R._dict_faces(r, 5):
                # 名詞として在る表記だけ（愛さ のような活用の切れ端は替え先にしない）
                if (f != face0 and f not in out and f in nouns and _rank(f) <= KEY_COMMON
                        and any(_kanji(c) for c in f)):
                    out.append(f)
    return out
