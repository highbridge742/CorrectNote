# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
# -*- coding: utf-8 -*-
"""Pure helpers for per-part-of-speech display font sizes."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import math
import re
import unicodedata


POS_LABELS = (
    ('名詞', '名詞'),
    ('名詞（サ変）', '名詞（サ変）'),
    ('数詞', '数詞'),
    ('英字', '英字'),
    ('動詞', '動詞'),
    ('形容詞', '形容詞'),
    ('形容動詞', '形容動詞'),
    ('副詞', '副詞'),
    ('連体詞', '連体詞'),
    ('接続詞', '接続詞'),
    ('感動詞', '感動詞'),
    ('助詞', '助詞'),
    ('助動詞', '助動詞'),
    ('接頭詞', '接頭詞'),
    ('記号', '記号'),
    ('フィラー', 'フィラー'),
    ('その他', 'その他'),
    # English articles (a / an / the) have their own row (2026-10-26 うにさん「冠詞を独立した項目にする」).
    # Last here so the existing rows keep their tag numbers; the dialog shows it after 連体詞.
    ('冠詞', '冠詞'),
    # Pronouns — Japanese (名詞:代名詞) and English (en_pos O) — have their own row too
    # (2026-10-26 うにさん「フォントサイズカラーの代名詞も独立する。1.2倍、緑明るい」).
    # Last for the same reason; the dialog shows it right after 名詞.
    ('代名詞', '代名詞'),
    # English prepositions have their own row, apart from 助詞 (2026-11-01 うにさん「助詞と前置詞を別々の項目に
    # 分け、助詞を0.9倍に変更。前置詞は1.0倍」). Last for the same reason; the dialog shows it right after 助詞.
    ('前置詞', '前置詞'),
    # Compound particles (janome 助詞・…・連語: によって・について・として・における) have their own row, apart from
    # the short particles (2026-11-01 うにさん「「によって」「として」…まで小さくなると読みにくくもなる」). Default 1.0
    # and the 助詞 colour; the dialog shows it right after 助詞.
    ('助詞（複合）', '助詞（複合）'),
)
ARTICLE = '冠詞'
PRONOUN = '代名詞'
PREPOSITION = '前置詞'
COMPOUND_PARTICLE = '助詞（複合）'
POS_CATEGORIES = tuple(key for key, _label in POS_LABELS)
# Rows of the per-POS dialog: the headings also name the English parts of
# speech each row takes (en_pos), and 英字 — now only the English words the
# dictionary does not know — is shown last as その他英字 (2026-10-14 うにさん
# 「英字を、その他英字として下へ移す。見出しに、代名詞や前置詞、冠詞も書き加える」).
# Keys, tags and saved settings keep the order and names above.
POS_DIALOG_LABELS = {'連体詞': '連体詞・限定詞', '英字': 'その他英字'}
_DIALOG_ORDER = [item for item in POS_LABELS
                 if item[0] not in ('英字', ARTICLE, PRONOUN, PREPOSITION, COMPOUND_PARTICLE)]
_DIALOG_ORDER.insert([k for k, _l in _DIALOG_ORDER].index('助詞') + 1, (PREPOSITION, PREPOSITION))
_DIALOG_ORDER.insert([k for k, _l in _DIALOG_ORDER].index('助詞') + 1, (COMPOUND_PARTICLE, COMPOUND_PARTICLE))
_DIALOG_ORDER.insert([k for k, _l in _DIALOG_ORDER].index('連体詞') + 1, (ARTICLE, ARTICLE))
_DIALOG_ORDER.insert([k for k, _l in _DIALOG_ORDER].index('名詞') + 1, (PRONOUN, PRONOUN))
POS_DIALOG_ROWS = tuple(
    (key, POS_DIALOG_LABELS.get(key, label))
    for key, label in _DIALOG_ORDER + [item for item in POS_LABELS if item[0] == '英字'])
POS_LABEL_BY_KEY = dict(POS_LABELS)
POS_FONT_TAGS = {key: 'pos_font_' + str(index)
                 for index, key in enumerate(POS_CATEGORIES)}
# Colours live on their own tags: a font-less tag can be recoloured, added
# and removed without Tk laying the lines out again (rows stay still while
# the mouse moves over the colour palette).  うに 2026-10-13
POS_COLOR_TAGS = {key: 'pos_color_' + str(index)
                  for index, key in enumerate(POS_CATEGORIES)}
# 2026-11-01 うにさん（画像のとおり）「サイズ処理前後で文字が小さくなるのが大きくなるより、大きいものが小さくなるほうが
# 見栄えがよかった。フォントのデフォルトサイズを12、品詞は画像の倍率に変更」: 本文の字を 12 にして、内容語を 1.0・
# 機能語や記号を 0.8〜0.9 に下げる形（前は 11 の字に内容語を 1.1〜1.2 で上げていた）
POS_FONT_DEFAULTS = {'名詞': 1.0, PRONOUN: 1.1, '名詞（サ変）': 0.9, '数詞': 1.1, '動詞': 1.0, '形容詞': 1.0,
                     '形容動詞': 0.9, '副詞': 1.0, '連体詞': 0.9, ARTICLE: 0.8, '接続詞': 0.9, '感動詞': 0.9,
                     '助詞': 0.8, COMPOUND_PARTICLE: 0.9, PREPOSITION: 0.9, '助動詞': 1.0, '接頭詞': 0.9,
                     '記号': 0.9, 'フィラー': 1.3, 'その他': 0.9, '英字': 1.0}
MULTIPLIER_MIN = 0.5
MULTIPLIER_MAX = 2.0
_COLOR = re.compile(r'#[0-9a-fA-F]{6}')


# Text-colour candidates: one column per hue, one row per shade, light at
# the top and deep at the bottom. Gray comes first for subdued text.
HUES = (('グレー', None), ('赤', 0), ('朱', 18), ('橙', 32), ('黄', 50),
        ('黄緑', 85), ('緑', 130), ('青緑', 170), ('水色', 195),
        ('青', 215), ('藍', 238), ('紫', 275), ('赤紫', 315))
SHADES = (('ごく明るい', .90), ('とても明るい', .82), ('明るい', .70),
          ('やや明るい', .58), ('中間', .47), ('やや濃い', .36), ('濃い', .26))
_GRAYS = (.95, .88, .74, .60, .46, .32, .16)


def _hls(hue, lightness, saturation):
    import colorsys
    rgb = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
    return '#' + ''.join('%02x' % round(value * 255) for value in rgb)


def _palette():
    rows = []
    for (_shade, lightness), gray in zip(SHADES, _GRAYS):
        row = []
        for _name, hue in HUES:
            if hue is None:
                row.append(_hls(0, gray, 0))
            else:
                row.append(_hls(hue, lightness, .78))
        rows.append(tuple(row))
    return tuple(rows)


PALETTE_ROWS = _palette()
PALETTE = tuple(color for row in PALETTE_ROWS for color in row)
PALETTE_NAMES = {color: f'{name}・{shade}'
                 for row, (shade, _l) in zip(PALETTE_ROWS, SHADES)
                 for color, (name, _hue) in zip(row, HUES)}


def palette_color(hue_name, shade_name):
    """The palette entry for a named hue and shade, e.g. ('緑', 'とても明るい')."""
    return PALETTE_ROWS[[s for s, _l in SHADES].index(shade_name)][
        [h for h, _v in HUES].index(hue_name)]


# Colours used until the user picks others; '' keeps the pane's colour.
# Light and dark keep their own colours (2026-10-13 うにさん「ライトモードと
# ダークモードで別管理にする」); these are the dark ones.
POS_COLOR_DEFAULTS = {key: '' for key in POS_CATEGORIES}
POS_COLOR_DEFAULTS.update({'名詞': palette_color('緑', 'ごく明るい'),
                           '数詞': palette_color('緑', 'とても明るい'),
                           PRONOUN: palette_color('緑', '明るい'),
                           'フィラー': palette_color('朱', '明るい'),
                           # 2026-11-01 うにさん「（その他英字の）色を藍・とても明るい」
                           '英字': palette_color('藍', 'とても明るい'),
                           '記号': palette_color('グレー', '明るい')})
POS_COLOR_DEFAULTS_LIGHT = {key: '' for key in POS_CATEGORIES}
POS_COLOR_DEFAULTS_LIGHT.update({'名詞': palette_color('青緑', '濃い'),
                                 '数詞': palette_color('緑', 'やや濃い'),
                                 # 緑・明るい as it reads on white (display_color: 明るい ↔ 中間)
                                 PRONOUN: palette_color('緑', '中間'),
                                 # 朱・明るい as it reads on white (the same mirror as 代名詞)
                                 'フィラー': palette_color('朱', '中間'),
                                 # 藍・とても明るい as it reads on white (display_color: とても明るい ↔ やや濃い)
                                 '英字': palette_color('藍', 'やや濃い'),
                                 '記号': palette_color('グレー', 'やや濃い')})


def color_defaults(dark=True):
    return dict(POS_COLOR_DEFAULTS if dark else POS_COLOR_DEFAULTS_LIGHT)


def colors_key(dark=True):
    """Settings key holding the POS colours of one mode."""
    return 'pos_font_colors' if dark else 'pos_font_colors_light'


def current_colors(settings):
    """POS colours of the mode the panes are drawn in now."""
    dark = bool(settings is not None and settings.get('dark_mode'))
    value = settings.get(colors_key(dark)) if settings is not None else None
    return normalize_colors(value, dark)


def display_color(color, dark):
    """A dark-mode POS colour as it reads on the light pane.

    Until 2026-10-13 only the dark colours were kept and the light pane drew
    them through this mirror; it now only carries those choices over into
    the light colours once (settings migration). On the light pane the same
    hue is drawn at the mirrored shade (ごく明るい↔濃い,
    とても明るい↔やや濃い, …), so a pale yellow that reads on dark stays
    readable on white (2026-10-12 うにさん「ライトモードとダークモードで、
    カラーを切り替える」). The mapping is its own inverse."""
    if not color or dark:
        return color
    color = color.lower()
    for r, row in enumerate(PALETTE_ROWS):
        if color in row:
            return PALETTE_ROWS[len(PALETTE_ROWS) - 1 - r][row.index(color)]
    if not _COLOR.fullmatch(color):
        return color
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*(int(color[i:i + 2], 16) / 255
                                   for i in (1, 3, 5)))
    return _hls(h * 360, 1 - l, s)


def normalize_multipliers(value):
    """Merge a saved mapping with defaults and discard invalid entries."""
    result = dict(POS_FONT_DEFAULTS)
    if not isinstance(value, dict):
        return result
    for key in POS_CATEGORIES:
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            continue
        number = float(number)
        if (math.isfinite(number)
                and MULTIPLIER_MIN <= number <= MULTIPLIER_MAX):
            result[key] = number
    if ARTICLE not in value:
        result[ARTICLE] = result['連体詞']     # settings from before 冠詞 had its own row
    return result


def normalize_colors(value, dark=True):
    """Per-POS text colours; an empty string keeps the pane's own colour.

    A missing entry takes its default (of the dark or light mode); a saved
    empty string stays empty."""
    result = color_defaults(dark)
    if not isinstance(value, dict):
        return result
    for key in POS_CATEGORIES:
        color = value.get(key)
        if color == '':
            result[key] = ''
        elif isinstance(color, str) and _COLOR.fullmatch(color):
            result[key] = color.lower()
    if ARTICLE not in value:
        result[ARTICLE] = result['連体詞']     # settings from before 冠詞 had its own row
    return result


def has_colors(value, dark=True):
    """Whether at least one POS has a chosen colour."""
    return any(normalize_colors(value, dark).values())


def has_adjustments(value):
    """Whether at least one POS uses a non-default display multiplier."""
    return any(multiplier != 1.0
               for multiplier in normalize_multipliers(value).values())


def font_size(base_size, multiplier):
    """Multiply a point size and round any fractional result upward."""
    try:
        base = Decimal(str(base_size))
        scale = Decimal(str(multiplier))
        if not base.is_finite() or not scale.is_finite():
            return int(base_size)
        return int((base * scale).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return int(base_size)


def major_pos(pos):
    """Return the configured top-level POS bucket for a tokenizer label."""
    value = str(pos or '')
    if value in POS_LABEL_BY_KEY:
        return value
    major, separator, sub = value.partition(':')
    if major == '名詞' and separator and sub.startswith('サ変'):
        return '名詞（サ変）'
    if major == '名詞' and separator and sub.split(':')[0] == '数':
        return '数詞'
    if major == '名詞' and separator and sub.split(':')[0] == PRONOUN:
        return PRONOUN
    if major == '助詞' and separator and '連語' in sub.split(':'):
        return COMPOUND_PARTICLE
    return major if major in POS_LABEL_BY_KEY else 'その他'


def _mark_char(c):
    """句読点・括弧・引用符・記号（数学・通貨・★♪○■ のような絵の記号も。janome は辞書に無い記号を名詞と付ける）。"""
    return unicodedata.category(c)[0] in 'PS'


_TARI = ('たり', 'だり')
_TARI_HOSTS = ('動詞', '形容詞', '助動詞')


def _dictionary_conjunction(surface):
    """janome の辞書に、同じ字の接続詞が在るか（表示だけ・読めなければ False）。"""
    try:
        from morphology import dictionary_base_pos
        found = dictionary_base_pos(surface)
    except Exception:
        return False
    return bool(found) and any(item.startswith('接続詞') for item in found)


# Digits inside a joined noun (``3個``, ``３本目``) are still numerals.
_DIGITS = re.compile(r'[0-9０-９]+')
_NUMERAL_HOSTS = ('名詞', '名詞（サ変）', '記号', 'その他')


def spans(text, tokens):
    """Return accurate ``(major_pos, start, end)`` runs for presentation."""
    result = []
    for token in tokens or ():
        try:
            surface, pos, _reading, start, end = token[:5]
            start = int(start)
            end = int(end)
        except (TypeError, ValueError, IndexError):
            continue
        if not (0 <= start < end <= len(text)
                and text[start:end] == surface):
            continue
        major = major_pos(pos)
        if (major != 'その他' and any(unicodedata.category(c)[0] == 'N' for c in surface)
                and all(unicodedata.category(c)[0] == 'N' or _mark_char(c) or c.isspace() for c in surface)):
            # 数の字と記号だけの並び（① ½ ² ②、: janome は 名詞・サ変接続 と付ける）は、数の字を数詞・記号を記号に
            # 分ける（2026-11-01）
            position = start
            while position < end:
                kind = '数詞' if unicodedata.category(text[position])[0] == 'N' else '記号'
                stop = position + 1
                while stop < end and ('数詞' if unicodedata.category(text[stop])[0] == 'N' else '記号') == kind:
                    stop += 1
                result.append((kind, position, stop))
                position = stop
            continue
        if major != 'その他' and surface.strip() and all(_mark_char(c) or c.isspace() for c in surface):
            # 記号だけの並びは記号（2026-11-01 うにさん「英語の記号に見える部分が名詞判定」: janome は辞書に無い
            # ASCII の記号 <= (*) -> && - , や ★♪○■ を 名詞・サ変接続 と付ける）。品詞の分からない字（その他）はそのまま
            major = '記号'
        if major == '記号':
            pass
        elif major == '助詞' and len(surface) >= 2 and _dictionary_conjunction(surface):
            # 助詞と付いても、辞書に同じ字の接続詞が在れば接続詞の書式（および・ならびに: 2026-11-01 うにさん。
            # janome は前の語によって および を接続助詞と付けることがある）。1字の助詞（が）は触らない
            major = '接続詞'
        elif surface in _TARI and result and result[-1][2] == start and result[-1][0] in _TARI_HOSTS:
            # 動詞・形容詞・助動詞の直後の たり・だり は前の語の書式（なかったり・見たり: 2026-11-01 うにさん。
            # janome は たり を並立助詞とも助動詞とも付け、同じ たり の大きさが揃わなかった）
            major = result[-1][0]
        if major not in _NUMERAL_HOSTS:
            result.append((major, start, end))
            continue
        position = start
        for match in _DIGITS.finditer(surface):
            a, z = start + match.start(), start + match.end()
            if position < a:
                result.append((major, position, a))
            result.append(('数詞', a, z))
            position = z
        if position < end:
            result.append((major, position, end))
    return _join_latin(text, _join_number_marks(text, result))


# A decimal point or a thousands comma between digits belongs to the number
# (``3.14``, ``1,000``, ``２．５``), whatever POS the tokenizer gave it.
# So does a minus sign right before the digits (``-5``, ``－５``, ``−3.2``,
# ``-1,234.5``) when nothing number- or letter-like stands before it: ``7-3``,
# ``2026-10-26`` and ``a-1`` keep their hyphen as a symbol
# (2026-10-26 うにさん「数字の前のマイナスを、数詞のフォントカラーに含める」).
_MINUS = '\\-－−﹣'
_NUMBER = re.compile(
    r'(?<![0-9０-９A-Za-zＡ-Ｚａ-ｚÀ-ÖØ-öø-ÿ.,．，_＿])[{0}][0-9０-９]+(?:[.,．，][0-9０-９]+)*'
    r'|[0-9０-９]+(?:[.,．，][0-9０-９]+)+'.format(_MINUS))


# Latin letters are shown by their English part of speech (en_pos), or as
# 英字 when unknown, whatever POS the tokenizer gave them (it calls most of
# them nouns), with the periods and underscores joined to them
# (``file_name.txt``, ``e.g.`` stay 英字). Digits keep 数詞 (2026-10-13 うにさん).
_LETTER = 'A-Za-zＡ-Ｚａ-ｚÀ-ÖØ-öø-ÿ'
_LATIN = re.compile(r'[._．＿]*[{0}]+(?:[._．＿]+[{0}]+)*[._．＿]*'.format(_LETTER))


def _join_latin(text, runs):
    words = [match.span() for match in _LATIN.finditer(text)]
    if not words:
        return tuple(runs)
    # English words take their own part of speech (en_pos: noun → 名詞,
    # verb → 動詞, preposition → 助詞, ...); unknown words stay 英字
    # (2026-10-14 うにさん「英文の品詞判定」).
    try:
        from en_pos import categories
        kinds = categories(text, words)
    except Exception:
        kinds = ['英字'] * len(words)
    result = []
    for major, start, end in runs:
        if major == '数詞':
            result.append((major, start, end))
            continue
        position = start
        for (a, z), kind in zip(words, kinds):
            a, z = max(a, start), min(z, end)
            if a >= z:
                continue
            if position < a:
                result.append((major, position, a))
            result.append((kind, a, z))
            position = z
        if position < end:
            result.append((major, position, end))
    return tuple(result)


def _join_number_marks(text, runs):
    numbers = [match.span() for match in _NUMBER.finditer(text)]
    if not numbers:
        return tuple(runs)
    result = []
    for major, start, end in runs:
        position = start
        for a, z in numbers:
            a, z = max(a, start), min(z, end)
            if a >= z:
                continue
            if position < a:
                result.append((major, position, a))
            result.append(('数詞', a, z))
            position = z
        if position < end:
            result.append((major, position, end))
    return tuple(result)
