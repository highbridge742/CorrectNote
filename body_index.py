# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""本文の行 ⇔ 欄の行 の変換（2026-11-15 うにさん「本文と目次が同じ仕組みの中で動くことはできないのか。タイトルも描画する
ならそうしたほうがよい」）。

タイトルと目次を、本文の Text の中の本物の字（先頭の H 行）として置く形（title_toc の INLINE）で使う。アプリと Tk の決まり
ごと（クラスの束縛）は、今まで通り「1行目＝本文の1行目」で Text を呼ぶ。その呼び出しを Tcl の層で受け、
  入る: 絶対の「行.位置」「行.end」の行に H を足す（本物の欄の位置にする）
  出る: 返ってきた「行.位置」の行から H を引く（見出しの中の位置は本文の頭 1.0 に寄せる）
とする。+Nc・linestart・@x,y・印の名前（insert・sel.first など）・end は、そのまま（Tk が本物の位置で解く）。

ここは決まりだけ（画面は使わない）。どの命令のどの引数が位置かは translate() が持つ。
"""
import re
import sys

_BASE = re.compile(r'^(\s*)(\d+)\.(\d+|end)(?=$|[\s+\-])')
_INDEX = re.compile(r'^(\d+)\.(\d+)$')


_LEAD = frozenset('0123456789 	')


def shift_in(index, h):
    """アプリから来た位置の式の頭が絶対の「行.位置」なら、行に h を足す。それ以外はそのまま。"""
    if not h or not isinstance(index, str) or not index or index[0] not in _LEAD:
        return index        # insert・end・@x,y・印の名前など（一番多い）は正規表現を通さない（打つたびに数百回呼ばれる）
    m = _BASE.match(index)
    if not m:
        return index
    return '%s%d.%s%s' % (m.group(1), int(m.group(2)) + h, m.group(3), index[m.end():])


def shift_out(index, h):
    """Text から返った「行.位置」を本文の位置にする。見出しの中（行が h 以下）は本文の頭 1.0。"""
    if not h:
        return index
    text = index if isinstance(index, str) else str(index)
    dot = text.find('.')
    if dot <= 0:
        return index
    head, col = text[:dot], text[dot + 1:]
    if not (head.isdigit() and col.isdigit() and head.isascii() and col.isascii()):
        return index
    row = int(head) - h
    return '1.0' if row < 1 else '%d.%s' % (row, col)


def _out_list(value, h, tk_split):
    """位置の並び（tag ranges など）。"""
    if not value:
        return ()
    items = tk_split(value) if isinstance(value, str) else value
    return tuple([shift_out(str(v), h) for v in items])


def _back(index, h):
    """生の「行.位置」（Tk 自身の Undo の控え）を本文の位置にする。"""
    m = _BASE.match(str(index))
    if not m:
        return index
    row = int(m.group(2)) - h
    return '%s%d.%s%s' % (m.group(1), max(1, row), m.group(3), str(index)[m.end():])


def untranslate(args, h):
    """Tk 自身の Undo・Redo が欄の名前で呼び返す命令（生の位置）を、本文の位置にする（translate の逆）。Tk の控えに
    あるのは insert・delete・mark set・see だけだが、ほかの位置の命令も同じ形で直す。"""
    if not h or not args:
        return args
    args = list(args)
    cmd = str(args[0])

    def at(*positions):
        for p in positions:
            if p < len(args):
                args[p] = _back(args[p], h)
    if cmd in ('insert', 'see', 'index', 'dlineinfo', 'bbox'):
        at(1)
    elif cmd in ('delete', 'get', 'count'):
        at(*range(1, len(args)))
    elif cmd == 'replace':
        at(1, 2)
    elif cmd == 'compare':
        at(1, 3)
    elif cmd == 'mark' and len(args) > 3 and str(args[1]) == 'set':
        at(3)
    elif cmd == 'tag' and len(args) > 3 and str(args[1]) in ('add', 'remove'):
        at(*range(3, len(args)))
    return args


# 命令ごとの、位置の引数の場所。'all' = 頭の命令名より後ろの引数を全部（- で始まる指定は除く）
def translate(args, h, tk_split=lambda v: tuple(str(v).split())):
    """(新しい引数, 返り値を直す関数 or None)。h が 0 なら何もしない。"""
    if not h or not args:
        return args, None
    args = list(args)
    cmd = str(args[0])

    def at(*positions):
        for p in positions:
            if p < len(args):
                args[p] = shift_in(str(args[p]), h)

    def rest(start):
        for p in range(start, len(args)):
            a = str(args[p])
            if not a.startswith('-'):
                args[p] = shift_in(a, h)

    out = None
    if cmd in ('insert', 'see', 'dlineinfo', 'bbox'):
        at(1)
    elif cmd == 'index':
        at(1)
        out = lambda v: shift_out(v, h)
    elif cmd in ('delete', 'count'):
        rest(1)
    elif cmd == 'get':
        rest(1)
    elif cmd == 'compare':
        at(1, 3)
    elif cmd == 'replace':
        at(1, 2)
    elif cmd == 'mark' and len(args) > 1:
        sub = str(args[1])
        if sub == 'set':
            at(3)
        elif sub in ('next', 'previous'):
            at(2)
    elif cmd == 'tag' and len(args) > 1:
        sub = str(args[1])
        if sub in ('add', 'remove'):
            rest(3)
        elif sub == 'names':
            at(2)
        elif sub == 'ranges':
            out = lambda v: _out_list(v, h, tk_split)
        elif sub in ('nextrange', 'prevrange'):
            at(3, 4)
            out = lambda v: _out_list(v, h, tk_split)
    elif cmd == 'search':
        # search ?switches? pattern index ?stopIndex?: 位置は「--」か指定の後の、パターンの次から
        i = 1
        while i < len(args) and str(args[i]).startswith('-') and str(args[i]) != '--':
            i += 2 if str(args[i]) in ('-count',) else 1
        if i < len(args) and str(args[i]) == '--':
            i += 1
        at(i + 1, i + 2)
        out = lambda v: shift_out(v, h) if str(v) else v
    elif cmd == 'dump':
        rest(1)
        def fix(v):
            items = list(tk_split(v) if isinstance(v, str) else (v or ()))
            for k in range(2, len(items), 3):
                items[k] = shift_out(str(items[k]), h)
            return tuple(items)
        out = fix
    elif cmd in ('window', 'image') and len(args) > 1 and str(args[1]) == 'create':
        at(2)
    elif cmd == 'yview' and len(args) > 1 and str(args[1]) not in ('moveto', 'scroll', '-pickplace'):
        at(1)
        if args[1] == '%d.0' % (h + 1):
            args[1] = '1.0'         # 本文の1行目を上に置く＝文書の頭（見出しの上）へ
    elif cmd == 'yview' and len(args) > 2 and str(args[1]) == '-pickplace':
        at(2)
        if args[2] == '%d.0' % (h + 1):
            args[2] = '1.0'
    return args, out


# --- 本文の Text に掛ける（Tcl の層の一番内側＝Tk のすぐ上） -------------------------------------
# 見出しの行数 H は、ふだんは変えない（タイトル1行・目次の行・下の線1行。使わない行は隠す）。Tk 自身の Undo は
# 生の行番号で控えるので、H が変わると前の一手の行がずれる（2026-11-15 確かめた）。目次が入りきらない時だけ増やす
# （title_inline.grow）。H は分身（補正欄の書く道・別窓）と1つの入れ物（state）で分け合う。
# 書き換え（insert・delete・replace）・印（mark set）・タグ（tag add）の位置は、生の位置で本文の頭より前に来たら本文の頭に
# 寄せる（相対の式 insert-1c などは Tk が生の位置で解くので、本文の頭で BackSpace を押しても見出しを消さない・選択が
# 見出しへ伸びない）。
# 変換は Tcl の手続き（::cnbody::cmd）でする。Python の命令にすると、Tk を1回呼ぶたびに Python を行き来して、打つたびに
# 数百回ある tag nextrange が1回 5µs → 32µs になり、1打 約5ms 重くなった（2026-11-15 測った）。決まりは translate()
# と同じ（試験で照らし合わせる）。Tk 自身の Undo・Redo だけは Python の replay を通す。
_CLAMP = ('insert', 'delete', 'replace')

_TCL = r'''
namespace eval ::cnbody {variable cn 0}
proc ::cnbody::in {i h} {
    # 同じ位置の字（"120.0" など）は何度も来る: 一度直した答えを覚えておく（H ごと）
    if {[info exists ::cnbody::ci($h,$i)]} {return $::cnbody::ci($h,$i)}
    set got [in_ $i $h]
    if {[incr ::cnbody::cn] > 50000} {array unset ::cnbody::ci; array unset ::cnbody::co; set ::cnbody::cn 0}
    return [set ::cnbody::ci($h,$i) $got]
}
proc ::cnbody::in_ {i h} {
    # 正規表現は1回 8µs かかった（打つたびに数百回）: 文字列の操作で見る
    set dot [string first . $i]
    if {$dot < 1} {return $i}
    set r [string range $i 0 $dot-1]
    if {![string is digit -strict $r]} {
        if {[string is space -strict [string index $i 0]] &&
                [regexp {^(\s*)(\d+)\.(\d+|end)($|[\s+-].*)$} $i -> sp r col rest]} {
            return "$sp[expr {$r + $h}].$col$rest"
        }
        return $i
    }
    set tail [string range $i $dot+1 end]
    if {[string is digit -failindex clen $tail]} {set clen [string length $tail]}
    if {$clen == 0} {
        if {[string range $tail 0 2] ne "end"} {return $i}
        set clen 3
    }
    set next [string index $tail $clen]
    if {$next ne "" && $next ne " " && $next ne "+" && $next ne "-" && $next ne "	"} {return $i}
    return "[expr {$r + $h}].$tail"
}
proc ::cnbody::out {v h} {
    if {[info exists ::cnbody::co($h,$v)]} {return $::cnbody::co($h,$v)}
    set got [out_ $v $h]
    if {[incr ::cnbody::cn] > 50000} {array unset ::cnbody::ci; array unset ::cnbody::co; set ::cnbody::cn 0}
    return [set ::cnbody::co($h,$v) $got]
}
proc ::cnbody::out_ {v h} {
    set dot [string first . $v]
    if {$dot < 1} {return $v}
    set r [string range $v 0 $dot-1]
    set col [string range $v $dot+1 end]
    if {![string is digit -strict $r] || ![string is digit -strict $col]} {return $v}
    set r [expr {$r - $h}]
    if {$r < 1} {return 1.0}
    return $r.$col
}
proc ::cnbody::outlist {l h} {
    set got {}
    foreach x $l {lappend got [out $x $h]}
    return $got
}
proc ::cnbody::clamp {raw i h} {
    set head [expr {$h + 1}].0
    if {![catch {$raw compare $i < $head} before] && $before} {return $head}
    return $i
}
proc ::cnbody::cmd {raw var replay args} {
    upvar #0 $var h
    set n [llength $args]
    if {!$h || !$n} {tailcall $raw {*}$args}
    set c [lindex $args 0]
    switch -exact -- $c {
        cget - configure - xview - scan - peer - debug - sync - pendingsync {
            tailcall $raw {*}$args
        }
        insert {
            if {$n > 1} {lset args 1 [clamp $raw [in [lindex $args 1] $h] $h]}
            tailcall $raw {*}$args
        }
        see - dlineinfo - bbox {
            if {$n > 1} {lset args 1 [in [lindex $args 1] $h]}
            tailcall $raw {*}$args
        }
        index {
            if {$n > 1} {lset args 1 [in [lindex $args 1] $h]}
            return [out [$raw {*}$args] $h]
        }
        delete - replace {
            set last [expr {$c eq "delete" ? $n : min($n, 3)}]
            for {set k 1} {$k < $last} {incr k} {
                set a [lindex $args $k]
                if {[string index $a 0] ne "-"} {lset args $k [in $a $h]}
            }
            for {set k 1} {$k < min($n, 3)} {incr k} {
                set a [lindex $args $k]
                if {[string index $a 0] ne "-"} {lset args $k [clamp $raw $a $h]}
            }
            # Tk は「行の頭から end まで」を消すと、その前の改行も消す。本文の頭から end までだと見出しの最後の改行が
            # 消え、見出しが1行減る（タブの入れ替えで本文の1行目が見出しに呑まれた）。最後の改行の手前までにする
            if {$n > 2 && [string index [lindex $args 1] 0] ne "-"} {
                set head [expr {$h + 1}].0
                if {![catch {expr {[$raw compare [lindex $args 1] == $head] && [$raw compare [lindex $args 2] >= end]}} hit] && $hit} {
                    lset args 2 end-1c
                }
            }
            tailcall $raw {*}$args
        }
        count - get {
            for {set k 1} {$k < $n} {incr k} {
                set a [lindex $args $k]
                if {[string index $a 0] ne "-"} {lset args $k [in $a $h]}
            }
            tailcall $raw {*}$args
        }
        compare {
            if {$n > 1} {lset args 1 [in [lindex $args 1] $h]}
            if {$n > 3} {lset args 3 [in [lindex $args 3] $h]}
            tailcall $raw {*}$args
        }
        mark {
            set s [lindex $args 1]
            if {$s eq "set" && $n > 3} {
                lset args 3 [clamp $raw [in [lindex $args 3] $h] $h]
            } elseif {($s eq "next" || $s eq "previous") && $n > 2} {
                lset args 2 [in [lindex $args 2] $h]
            }
            tailcall $raw {*}$args
        }
        tag {
            set s [lindex $args 1]
            switch -exact -- $s {
                add - remove {
                    for {set k 3} {$k < $n} {incr k} {
                        set a [lindex $args $k]
                        if {[string index $a 0] ne "-"} {set a [in $a $h]}
                        if {$s eq "add"} {set a [clamp $raw $a $h]}
                        lset args $k $a
                    }
                    tailcall $raw {*}$args
                }
                names {
                    if {$n > 2} {lset args 2 [in [lindex $args 2] $h]}
                    tailcall $raw {*}$args
                }
                ranges {
                    return [outlist [$raw {*}$args] $h]
                }
                nextrange - prevrange {
                    if {$n > 3} {lset args 3 [in [lindex $args 3] $h]}
                    if {$n > 4} {lset args 4 [in [lindex $args 4] $h]}
                    return [outlist [$raw {*}$args] $h]
                }
                default {tailcall $raw {*}$args}
            }
        }
        search {
            set i 1
            while {$i < $n} {
                set a [lindex $args $i]
                if {[string index $a 0] ne "-" || $a eq "--"} {break}
                incr i [expr {$a eq "-count" ? 2 : 1}]
            }
            if {$i < $n && [lindex $args $i] eq "--"} {incr i}
            if {$i + 1 < $n} {lset args [expr {$i + 1}] [in [lindex $args [expr {$i + 1}]] $h]}
            if {$i + 2 < $n} {lset args [expr {$i + 2}] [in [lindex $args [expr {$i + 2}]] $h]}
            set r [$raw {*}$args]
            if {$r eq ""} {return ""}
            return [out $r $h]
        }
        dump {
            for {set k 1} {$k < $n} {incr k} {
                set a [lindex $args $k]
                if {[string index $a 0] ne "-"} {lset args $k [in $a $h]}
            }
            set r [$raw {*}$args]
            for {set k 2} {$k < [llength $r]} {incr k 3} {lset r $k [out [lindex $r $k] $h]}
            return $r
        }
        window - image {
            if {[lindex $args 1] eq "create" && $n > 2} {lset args 2 [in [lindex $args 2] $h]}
            tailcall $raw {*}$args
        }
        yview {
            # 本文の1行目を上に置く（1行目へ・Ctrl+Home）は、文書の頭＝見出しの上へ（いちばん上まで送った時と同じ所）
            set s [lindex $args 1]
            set head [expr {$h + 1}].0
            if {$n > 1 && $s ni {moveto scroll -pickplace}} {
                set s [in $s $h]
                if {$s eq $head} {set s 1.0}
                lset args 1 $s
            } elseif {$s eq "-pickplace" && $n > 2} {
                set s [in [lindex $args 2] $h]
                if {$s eq $head} {set s 1.0}
                lset args 2 $s
            }
            tailcall $raw {*}$args
        }
        edit {
            if {[lindex $args 1] in {undo redo}} {tailcall $replay {*}$args}
            tailcall $raw {*}$args
        }
        default {tailcall $raw {*}$args}
    }
}
'''


class _State(dict):
    """見出しの行数 H の入れ物（欄と分身で1つ）。H は Tcl の変数にも置く（変換の手続きが読む）。"""

    def __init__(self, tk_, var, h):
        super().__init__(h=int(h), var=var)
        self._tk = tk_
        tk_.setvar(var, int(h))

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == 'h':
            self._tk.setvar(self['var'], int(value))


def height(widget):
    """見出しの行数（変換を掛けていなければ 0）。"""
    state = getattr(widget, '_cn_body_state', None)
    return int(state['h']) if state else 0


def set_height(widget, h):
    widget._cn_body_state['h'] = int(h)


def install(widget, height, share=None):
    """widget の Tcl の命令を、本文の位置で呼べる形にする。height=見出しの行数。share: 分身なら元の欄の
    _cn_body_state（H を分け合う）。生の命令名を返す（見出しを書くのはこの名前で）。observe_text より前に掛けること
    （その後の観察者・Undo の控えは本文の位置で見る）。"""
    raw = widget._w + '_correctnote_raw'
    if getattr(widget, '_cn_body_raw', None):
        return widget._cn_body_raw
    tk_ = widget.tk
    if not int(tk_.call('info', 'exists', '::cnbody::loaded')):
        tk_.eval(_TCL)
        tk_.setvar('::cnbody::loaded', 1)
    tk_.call('rename', widget._w, raw)
    widget._cn_body_raw = raw
    state = share if share is not None else _State(tk_, '::cnbody::h(%s)' % raw, height)
    widget._cn_body_state = state

    def replay(*new):
        """Tk 自身の Undo・Redo。Tk は控えた一手を「欄の名前 insert/delete 生の位置」で呼び返す。その名前の命令（一番
        外の観察者・Undo の控えなど）は本文の位置で受けるので、呼び返しの間だけ欄の名前の前に1枚かぶせて、Tk からの
        呼び返し（この関数の tk.call から直に来たもの）だけ本文の位置に直す。観察者が途中で Python から呼ぶ分は、
        もともと本文の位置なのでそのまま（2026-11-15 Undo が本文の位置で H 行ずれ、末尾へ飛んで何も戻らなかった）。"""
        if state.get('replaying'):
            return tk_.call(raw, *new)
        top = widget._w
        hidden = top + '_correctnote_replay'
        me = sys._getframe()

        def from_tk(*a):
            if sys._getframe(1) is me:
                a = untranslate(a, state['h'])
            return tk_.call(hidden, *a)
        tk_.call('rename', top, hidden)
        tk_.createcommand(top, from_tk)
        dict.__setitem__(state, 'replaying', True)
        try:
            return tk_.call(raw, *new)
        finally:
            dict.__setitem__(state, 'replaying', False)
            try:
                tk_.deletecommand(top)
            except Exception:
                pass
            tk_.call('rename', hidden, top)

    replay_name = widget._w + '_correctnote_replaycmd'
    tk_.createcommand(replay_name, replay)
    tk_.call('interp', 'alias', '', widget._w, '', '::cnbody::cmd', raw, state['var'], replay_name)
    return raw
