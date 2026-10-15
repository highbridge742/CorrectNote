# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
# -*- coding: utf-8 -*-
"""Pure helpers for per-part-of-speech display font sizes."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import math
import re


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
)
POS_CATEGORIES = tuple(key for key, _label in POS_LABELS)
# Rows of the per-POS dialog: the headings also name the English parts of
# speech each row takes (en_pos), and 英字 — now only the English words the
# dictionary does not know — is shown last as その他英字 (2026-10-14 うにさん
# 「英字を、その他英字として下へ移す。見出しに、代名詞や前置詞、冠詞も書き加える」).
# Keys, tags and saved settings keep the order and names above.
POS_DIALOG_LABELS = {'名詞': '名詞・代名詞', '助詞': '助詞・前置詞',
                     '連体詞': '連体詞・冠詞', '英字': 'その他英字'}
POS_DIALOG_ROWS = tuple(
    (key, POS_DIALOG_LABELS.get(key, label))
    for key, label in [item for item in POS_LABELS if item[0] != '英字']
    + [item for item in POS_LABELS if item[0] == '英字'])
POS_LABEL_BY_KEY = dict(POS_LABELS)
POS_FONT_TAGS = {key: 'pos_font_' + str(index)
                 for index, key in enumerate(POS_CATEGORIES)}
# Colours live on their own tags: a font-less tag can be recoloured, added
# and removed without Tk laying the lines out again (rows stay still while
# the mouse moves over the colour palette).  うに 2026-10-13
POS_COLOR_TAGS = {key: 'pos_color_' + str(index)
                  for index, key in enumerate(POS_CATEGORIES)}
POS_FONT_DEFAULTS = {key: 1.0 for key in POS_CATEGORIES}
POS_FONT_DEFAULTS.update({'名詞': 1.1, '動詞': 1.1, '形容詞': 1.1, '副詞': 1.1,
                          '助動詞': 1.1, '数詞': 1.2})
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
                           '英字': palette_color('グレー', '明るい'),
                           '記号': palette_color('グレー', '明るい')})
POS_COLOR_DEFAULTS_LIGHT = {key: '' for key in POS_CATEGORIES}
POS_COLOR_DEFAULTS_LIGHT.update({'名詞': palette_color('青緑', '濃い'),
                                 '数詞': palette_color('緑', 'やや濃い'),
                                 '英字': palette_color('グレー', 'やや濃い'),
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
    return major if major in POS_LABEL_BY_KEY else 'その他'


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
_NUMBER = re.compile(r'[0-9０-９]+(?:[.,．，][0-9０-９]+)+')


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
