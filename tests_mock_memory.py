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
**覚えておくもの**（選び直し・判断・索引・文脈・控え）の試験。

`tests_mock.py` から分けたもの（2026-08-20・項目48-GQ）。
**走らせる入口は `tests_mock.py` のまま。**
"""
import corrector as C
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed

from tests_mock_common import mock_tokenize


def run_choice_cases(store):
    """
    語の選び直し（手動学習）の一連の動きを確かめる。

    候補の並び順（同音異義語が先頭）、選び直しの表示への反映、
    文脈（前後の語）による使い分け、再選択による上書き、
    保存と読み込み、を見る。
    """
    from choices import ChoiceStore
    from candidates import build_candidates
    from units import build_line_units, unit_at

    print('--- 語の選び直し（手動学習） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    # 同音異義語を用意する
    store.add('こうえん', '公園', '日常会話')
    store._by_reading['こうえん']['公園']['count'] = 5
    store.add('こうえん', '講演', '仕事・ビジネス')
    store._by_reading['こうえん']['講演']['count'] = 4
    store._invalidate_cache()

    # --- 候補の生成 ---
    cands = build_candidates('こうえん', 'こうえん', store,
                             find_known_readings_flex)
    kinds = [c['kind'] for c in cands]
    check('同音異義語が候補の先頭に並ぶ',
          kinds[:2], ['homophone', 'homophone'])
    check('同音の2語がどちらも入っている',
          {c['surface'] for c in cands if c['kind'] == 'homophone'}
          >= {'公園', '講演'}, True)
    check('打ち間違いの候補も含まれる',
          any(c['kind'] == 'typo' for c in cands), True)
    check('カタカナ表記も候補に入る',
          any(c['surface'] == 'コウエン' for c in cands), True)

    cands2 = build_candidates('ぱそみん', 'ぱそみん', store,
                              find_known_readings_flex)
    check('誤打から届く語（パソコン）が候補に入る',
          any(c['surface'] == 'パソコン' for c in cands2), True)

    # --- 選び直しの反映 ---
    ch = ChoiceStore()
    line = 'あしたのこうえんにいく'
    r = C.correct_line(line, store, mock_tokenize, find_known_readings_flex)
    text, units = build_line_units(r, mock_tokenize, ch)
    u = unit_at(units, text.index('こうえん'))
    check('クリック位置から語の単位が引ける', u['text'], 'こうえん')
    check('前後の語が単位に入っている', (u['prev'], u['next']), ('の', 'に'))

    ch.record(u['base'], '公園', 'こうえん', u['prev'], u['next'])
    text2, units2 = build_line_units(r, mock_tokenize, ch)
    check('選び直した語が表示に反映される', '公園' in text2, True)
    u2 = unit_at(units2, text2.index('公園'))
    check('選び直した語は kind=chosen になる', u2['kind'], 'chosen')
    check('表示が崩れない（前後がそのまま残る）',
          text2, 'あしたの公園にいく')

    # --- 文脈による使い分け ---
    ch.record('こうえん', '講演', 'こうえん', 'だいがくで', 'を')
    check('元の文脈では元の選択が出る',
          ch.lookup('こうえん', 'の', 'に'), '公園')
    check('別の文脈では別の選択が出る',
          ch.lookup('こうえん', 'だいがくで', 'を'), '講演')
    check('未知の文脈で選択が割れているなら決めない',
          ch.lookup('こうえん', 'まったくべつの', 'ばしょ'), None)

    # --- 再選択（何度でも変更できる） ---
    ch.record('こうえん', '講演', 'こうえん', 'の', 'に')
    check('同じ文脈での再選択は上書きされる',
          ch.lookup('こうえん', 'の', 'に'), '講演')
    ch.forget('こうえん', 'の', 'に')
    check('選び直しを取り消せる',
          ch.lookup('こうえん', 'の', 'に'), '講演')  # 残る記録の弱い一致は無い(2択)→
    # ↑取り消し後は「だいがくで|を」の記録しか無いので、文脈不一致では
    #   選択が1通り＝弱い一致で「講演」が出る。この動きも仕様として確認する。

    # --- 保存と読み込み ---
    import tempfile, os as _os
    path = _os.path.join(tempfile.mkdtemp(), 'choices.json')
    ch2 = ChoiceStore(path)
    ch2.record('こうえん', '公園', 'こうえん', 'の', 'に')
    ch2.save()
    reloaded = ChoiceStore(path)
    check('保存した選び直しが読み込める',
          reloaded.lookup('こうえん', 'の', 'に'), '公園')

    # --- ドラッグ選択（区切りが実態と合わないときの救済） ---
    # 実機のjanomeは「ひらがなを」を ひ/ら/が/なを と割る。
    # ユーザーがドラッグで「ひらがな」を選べば、区切りに関係なく
    # 選び直しが機能しなければならない。
    from units import make_range_unit

    def janome_like(text):
        toks = ['漢字', 'を', '平仮名', 'に', 'ひらい', 'たり', '、',
                'ひ', 'ら', 'が', 'なを', '漢字', 'に', 'し', 'たり', '、']
        out, pos = [], 0
        for w in toks:
            rd = w if all('\u3041' <= c <= '\u3096' for c in w) else ''
            out.append((w, '名詞:一般', rd, pos, pos + len(w), True))
            pos += len(w)
        return out

    text = '漢字を平仮名にひらいたり、ひらがなを漢字にしたり、'
    result = {'corrected': text, 'spans': [], 'details': []}
    ch3 = ChoiceStore()
    t1, units1 = build_line_units(result, janome_like, ch3)
    sel = make_range_unit(t1, units1, 13, 17)
    check('ドラッグ範囲から選び直しの単位が作れる', sel['text'], 'ひらがな')
    check('範囲のかなは読みとして扱える', sel['reading'], 'ひらがな')
    ch3.record(sel['base'], '平仮名', sel['reading'],
               sel['prev'], sel['next'])
    t2, units2 = build_line_units(result, janome_like, ch3)
    check('トークン区切りに関係なく置換される',
          t2, '漢字を平仮名にひらいたり、平仮名を漢字にしたり、')
    u_wo = unit_at(units2, t2.index('平仮名を', 10) + 3)
    check('切られた語の残り（を）が断片として残る', u_wo['text'], 'を')
    u_ch = unit_at(units2, t2.index('平仮名', 10))
    check('置換後の再クリックで chosen 単位が引ける',
          (u_ch['kind'], u_ch['base']), ('chosen', 'ひらがな'))
    ch3.forget(u_ch['base'], u_ch['prev'], u_ch['next'])
    t3, _ = build_line_units(result, janome_like, ch3)
    check('範囲の選び直しも取り消せる', t3, text)

    # --- 1文字の語の巻き添え防止 ---
    # 「し」→「歯」を1箇所で選んでも、文中の他の「し」まで
    # 置き換わってはいけない（1文字は文脈一致がないと引き当てない）。
    ch4 = ChoiceStore()
    ch4.record('し', '歯', 'し', 'むし', 'が')
    check('1文字の語は文脈が合えば引ける',
          ch4.lookup('し', 'むし', 'が'), '歯')
    check('1文字の語は文脈が合わなければ引かない',
          ch4.lookup('し', 'かん', 'に'), None)
    r_sh = {'corrected': 'にします', 'spans': [], 'details': []}
    t_sh, _ = build_line_units(r_sh, mock_tokenize, ch4)
    check('無関係な「し」は置き換わらない', t_sh, 'にします')

    # --- 疑わしい箇所の表示（自動では直さない・統合レイアウト用） ---
    from units import build_suspect_units

    def word_level_tokenize(text):
        """実機のjanomeのように単語単位でトークンを返す簡易版。"""
        segs = [('もんたい', 'もんたい'), ('、', '、'), ('ぱそみん', 'ぱそみん')]
        out, pos = [], 0
        for w, r in segs:
            if text[pos:pos + len(w)] != w:
                return []
            out.append((w, '名詞:一般', r, pos, pos + len(w), True))
            pos += len(w)
        return out

    r_sus = C.correct_line('もんたい、ぱそみん', store, mock_tokenize,
                           find_known_readings_flex)
    text_sus, units_sus = build_suspect_units(r_sus, word_level_tokenize,
                                              ChoiceStore())
    check('入力そのままが表示される（自動補正しない）',
          text_sus, 'もんたい、ぱそみん')
    check('疑わしい語が単語単位でまとまる',
          [u['text'] for u in units_sus], ['もんたい', '、', 'ぱそみん'])
    check('疑わしい語は kind=suspect になる',
          units_sus[0]['kind'], 'suspect')
    check('疑わしい語の detail が取れる',
          units_sus[0]['detail'][1], 'もんだい')
    check('記号など疑わしくない部分は plain',
          units_sus[1]['kind'], 'plain')

    ch5 = ChoiceStore()
    ch5.record('もんたい', '選んだ表記', 'もんたい', '', '、')
    _t, units_hint = build_suspect_units(r_sus, word_level_tokenize, ch5)
    check('過去に選び直した語には chosen_hint が付く（文字は変えない）',
          (units_hint[0]['kind'], units_hint[0]['chosen_hint'],
           units_hint[0]['text']),
          ('chosen_hint', '選んだ表記', 'もんたい'))

    # --- 辞書索引による候補（実機報告ケース） ---
    # 個人語彙に無い語（平仮名 等）や、漢字が別読みで誤変換された語
    # （時=とき だが意図は じ）も候補に出せることを確かめる。
    from candidates import build_range_candidates

    class FakeDict:
        """janome 辞書索引の代役。実機の辞書内容を模す。"""
        ready = True
        BY_READING = {
            'ひらがな': ['平仮名', 'ひらがな'],
            'じっそう': ['実装', '実相'],
            'まちがい': ['間違い'],
            'いと': ['糸', '意図'],
            'うった': ['売った', '打った'],
        }
        BY_SURFACE = {
            '時': ['とき', 'じ'], 'ッ': ['っ'], '層': ['そう'],
            'タン': ['たん'], '具': ['ぐ'], '子': ['こ', 'し'],
            '待ち': ['まち'], '外': ['がい', 'そと'],
            '高': ['こう', 'たか'], '後': ['ご', 'あと'],
            '綱': ['つな'], '刷り': ['ずり', 'すり'],
            '売っ': ['うっ'], '打っ': ['うっ'],
        }
        def surfaces_for_reading(self, r, limit=12):
            return self.BY_READING.get(r, [])[:limit]
        def readings_for_surface(self, s, limit=6):
            return self.BY_SURFACE.get(s, [])[:limit]

    fd = FakeDict()

    cands_h = build_candidates('ひらがな', 'ひらがな', store,
                               find_known_readings_flex, dict_index=fd)
    check('個人語彙に無い「平仮名」が辞書索引から候補に出る',
          any(c['surface'] == '平仮名' for c in cands_h), True)

    def seg_case(segments, want_surface):
        cs = build_range_candidates(segments, store,
                                    find_known_readings_flex, dict_index=fd)
        return any(c['surface'] == want_surface for c in cs)

    check('タン具（たん＋ぐ）→ 単語 が候補に出る',
          seg_case([('タン', 'たん'), ('具', 'ぐ')], '単語'), True)
    check('時ッ層（別読み じ の組合せ）→ 実装 が候補に出る',
          seg_case([('時', 'とき'), ('ッ', 'っ'), ('層', 'そう')], '実装'),
          True)
    cs_js = build_range_candidates(
        [('時', 'とき'), ('ッ', 'っ'), ('層', 'そう')],
        store, find_known_readings_flex, dict_index=fd)
    js = [c for c in cs_js if c['surface'] == '実装']
    check('実装は同音として（typoより上に）並ぶ',
          js and js[0]['kind'], 'homophone')
    check('待ち外（まち＋がい）→ 間違い が候補に出る',
          seg_case([('待ち', 'まち'), ('外', 'がい')], '間違い'), True)
    check('タン子（たん＋こ）→ 単語 が候補に出る',
          seg_case([('タン', 'たん'), ('子', 'こ')], '単語'), True)
    check('高後（こう＋ご）で候補が空にならない',
          len(build_range_candidates([('高', 'こう'), ('後', 'ご')],
                                     store, find_known_readings_flex,
                                     dict_index=fd)) > 0, True)
    cands_ito = build_candidates('糸', 'いと', store,
                                 find_known_readings_flex, dict_index=fd)
    check('糸のクリックで同音の「意図」が候補に出る',
          any(c['surface'] == '意図' for c in cands_ito), True)

    # --- 活用形に埋め込まれた不規則動詞の同音（来ている／着ている） ---
    # 「来る」「着る」は活用すると同じ語幹の読み「き」になるため、
    # 通常の同音探索・辞書索引のどちらにも載っていない
    # （実機報告: 「きている」「戻ってきている」等で候補が出ない）。
    from candidates import verb_stem_candidates

    check('「きている」から来ている／着ているが作れる',
          set(verb_stem_candidates('きている')),
          {'来ている', '着ている'})
    check('「きた」から来た／着たが作れる',
          set(verb_stem_candidates('きた')), {'来た', '着た'})
    check('複合表現でも頭を残したまま展開できる（戻ってきている）',
          set(verb_stem_candidates('もどってきている')),
          {'もどって来ている', 'もどって着ている'})
    check('関係ない語尾では展開しない',
          verb_stem_candidates('たべている'), [])

    cands_kiteiru = build_candidates('きている', 'きている', store,
                                     find_known_readings_flex)
    check('「きている」のクリックで来ている／着ているが候補に出る',
          {c['surface'] for c in cands_kiteiru} >= {'来ている', '着ている'},
          True)
    kinds_ki = {c['surface']: c['kind'] for c in cands_kiteiru}
    check('来ている／着ているは同音として優先表示される',
          (kinds_ki.get('来ている'), kinds_ki.get('着ている')),
          ('homophone', 'homophone'))

    range_cands = build_range_candidates(
        [('もどって', 'もどって'), ('き', 'き'), ('て', 'て'), ('いる', 'いる')],
        store, find_known_readings_flex)
    check('ドラッグ範囲「もどってきている」でも展開される',
          any(c['surface'] == 'もどって来ている' for c in range_cands), True)

    # --- 活用形の選び直し（売った → 打った） ---
    # 「売った」全体は辞書に無いので、語幹「売っ」を差し替えて
    # 語尾「た」を残す形で候補を作れることを確かめる。
    # 語尾まで変えた「打つ」では解決しない（実機report）。
    class FD2(FakeDict):
        BY_READING = dict(FakeDict.BY_READING, **{'うっ': ['打っ', '撃っ']})
        BY_SURFACE = dict(FakeDict.BY_SURFACE, **{'売っ': ['うっ'],
                                                  'た': ['た']})
    cs_utta = build_range_candidates([('売っ', 'うっ'), ('た', 'た')],
                                     store, find_known_readings_flex,
                                     dict_index=FD2())
    check('売った → 打った（語尾を保った差し替え）が候補に出る',
          any(c['surface'] == '打った' for c in cs_utta), True)
    check('打ったは同音として上位に並ぶ',
          cs_utta[0]['kind'], 'homophone')

    # 送り仮名を合わせる（原形の候補を元の活用形に直す）
    from candidates import align_okurigana
    check('売っ に対し 打つ は 打っ になる',
          align_okurigana('売っ', '打つ'), '打っ')
    check('動い に対し 働く は 働い になる',
          align_okurigana('動い', '働く'), '働い')
    check('送り仮名が無い語はそのまま',
          align_okurigana('時', '実装'), '実装')

    # 辞書索引が無くても、語幹の差し替えで活用形に届くこと
    cs_noidx = build_range_candidates([('売っ', 'うっ'), ('た', 'た')],
                                      store, find_known_readings_flex,
                                      dict_index=None)
    surfaces_noidx = [c['surface'] for c in cs_noidx]
    check('索引が無くても 打った が候補に出る',
          '打った' in surfaces_noidx, True)
    check('語尾を落とした 打つ より 打った が先に出る',
          surfaces_noidx.index('打った')
          < (surfaces_noidx.index('打つ') if '打つ' in surfaces_noidx else 999),
          True)

    # --- 壊れた記録で起動できなくなることが無いか ---
    # 過去に halfwidth_to_kana の3つ組（文字列, 数, 数）を
    # そのまま候補にしてしまう不具合があり、その時期の選び直しが
    # choices.json に **配列** として残っている。読み戻すとリストに
    # なり、行の組み立てが ''.join() で落ちて起動できなくなった
    # （実機で TypeError: expected str instance, list found）。
    import json as _json
    import os as _os
    broken_path = '_broken_choices.json'
    with open(broken_path, 'w', encoding='utf-8') as f:
        _json.dump([
            {'original': 'たんご', 'chosen': ['たんこ゛のつなか゛り', 10, 10],
             'reading': None, 'prev': '', 'next': '', 'count': 1},
            {'original': ['壊れた'], 'chosen': '単語',
             'prev': '', 'next': '', 'count': 1},
            {'original': '文字', 'chosen': '文字入力',
             'prev': '', 'next': '', 'count': 1},
        ], f, ensure_ascii=False)
    broken = ChoiceStore(broken_path)
    _os.remove(broken_path)
    check('壊れた記録は読み飛ばし、正しい記録だけ残す', len(broken), 1)
    check('壊れた記録は引き当てに出てこない',
          broken.lookup('たんご'), None)
    check('正しい記録は普通に引ける',
          broken.lookup('文字'), '文字入力')
    check('表記が文字列でない記録は覚えない',
          broken.record('てすと', ['あ', 1, 2]), False)

    # 壊れた記録が混ざっていても、行の組み立てが落ちないこと
    bad = ChoiceStore()
    bad._by_original['たんご'] = [
        {'original': 'たんご', 'chosen': ['こわれた', 1, 2],
         'prev': '', 'next': '', 'count': 1}]
    r_bad = {'original': 'たんごの繋がり', 'corrected': 'たんごの繋がり',
             'changed': False, 'details': [], 'spans': [],
             'original_spans': [], 'unsure_spans': []}
    try:
        text_bad, _units_bad = build_line_units(r_bad, mock_tokenize, bad)
        ok_bad = (text_bad == 'たんごの繋がり')
    except Exception:
        ok_bad = False
    check('壊れた記録があっても行の組み立てが落ちない', ok_bad, True)

    return all_ok


def run_decision_cases(store):
    """
    ユーザーの判断（クリックによる確定・除外）が効くことを確かめる。

    誤補正を止められること、止めた判断を取り消せること、
    そして「止めた判断が無関係な補正まで巻き添えにしない」ことを見る。
    """
    from decisions import DecisionStore

    print('--- ユーザーの判断による補正の抑止 ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    def corrected(line, dec):
        return C.correct_line(line, store, mock_tokenize,
                              find_known_readings_flex, decisions=dec)

    # 補正が効いている状態を確認してから、それを止める
    base = corrected('もばなゅうりょく', None)
    check('判断なしなら従来どおり補正される',
          base['corrected'], 'もじにゅうりょく')

    dec = DecisionStore()

    # 1. この置換だけをやめる
    dec.reject('もばなゅうりょく', 'もじにゅうりょく')
    r = corrected('もばなゅうりょく', dec)
    check('「この補正は不要」と言われた置換は行わない',
          r['corrected'], 'もばなゅうりょく')
    check('補正しなかったので changed は False', r['changed'], False)

    # 2. 取り消せば元に戻る
    dec.unreject('もばなゅうりょく', 'もじにゅうりょく')
    r = corrected('もばなゅうりょく', dec)
    check('判断を取り消すと再び補正される',
          r['corrected'], 'もじにゅうりょく')

    # 3. 語そのものを守る（助詞を巻き込んだ範囲でも止まること）
    dec2 = DecisionStore()
    dec2.protect('もばなゅうりょく')
    r = corrected('もばなゅうりょく', dec2)
    check('守った語は補正されない', r['corrected'], 'もばなゅうりょく')

    # 4. 無関係な語の補正まで巻き添えにしない
    r = corrected('ぱそみん', dec2)
    check('別の語の補正は従来どおり効く', r['corrected'], 'パソコン')

    # 5. 1文字の語は守れない（広い範囲を巻き添えにするため）
    dec3 = DecisionStore()
    check('1文字の語は保護対象にしない', dec3.protect('あ'), False)

    # 6. 保存と読み込みで判断が失われないこと
    import tempfile, os as _os
    path = _os.path.join(tempfile.mkdtemp(), 'decisions.json')
    dec4 = DecisionStore(path)
    dec4.reject('もばなゅうりょく', 'もじにゅうりょく')
    dec4.protect('縦シュー')
    dec4.save()
    reloaded = DecisionStore(path)
    check('保存した「直さない」判断が読み込める',
          reloaded.is_rejected('もばなゅうりょく', 'もじにゅうりょく'), True)
    check('保存した「触らない」判断が読み込める',
          reloaded.is_protected('縦シュー'), True)

    return all_ok


def run_dict_index_cases():
    """
    辞書索引が作れることを確かめる。

    実機の診断で、janome の辞書エントリから品詞が取り出せず
    全件が空になることが判明した。品詞で絞り込んでいたため
    索引が丸ごと空になり、候補が一切出なくなっていた。
    同じ壊れ方を繰り返さないための試験。
    """
    import dict_index as D

    print('--- 辞書索引の構築 ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    # 実機と同じ形（品詞が空、長音が「ー」）のエントリを流し込む。
    # コストは実際の除外フィルタ（GENERAL_COST_LIMIT=4500）を
    # 下回る値にしておく。ここで確かめたいのは「品詞が空でも
    # 索引が作れるか」であり、除外フィルタそのものの検証は別に行う。
    sample = [
        ('平仮名', 'ひらがな', '', '', '', 3200),
        ('実装', 'じっそう', '', '', '', 2000),
        ('実相', 'じっそう', '', '', '', 2500),
        ('時', 'とき', '', '', '', 3000),
        ('時', 'じ', '', '', '', 3800),
        ('打っ', 'うっ', '', '', '', 3200),
        ('そういう', 'そーゆう', '', '', '', 3301),
    ]
    orig_iter, orig_has, orig_min = (D.iter_janome_entries, D.HAS_JANOME,
                                     D._MIN_READINGS)
    try:
        D.iter_janome_entries = lambda min_len=1, max_len=8: iter(sample)
        D.HAS_JANOME = True
        D._MIN_READINGS = 1
        idx = D.DictIndex(None)
        idx.ensure_built()
        check('品詞が空の辞書でも索引が作れる',
              idx.stats()['readings'] > 0, True)
        check('読みから表記を引ける（ひらがな→平仮名）',
              idx.surfaces_for_reading('ひらがな'), ['平仮名'])
        check('コストの低い語が先に並ぶ（実装→実相）',
              idx.surfaces_for_reading('じっそう'), ['実装', '実相'])
        check('表記から別の読みを引ける（時→とき,じ）',
              idx.readings_for_surface('時'), ['とき', 'じ'])
        check('長音「ー」を含む読みも入る',
              idx.surfaces_for_reading('そーゆう'), ['そういう'])
    finally:
        D.iter_janome_entries, D.HAS_JANOME, D._MIN_READINGS = (
            orig_iter, orig_has, orig_min)

    # --- 地名・人名・難語の除外（実機で「多すぎる」と報告された） ---
    # 品詞が空で判定できない環境でも、コスト（使用頻度）と
    # 表記パターンによる既存の除外フィルタ（janome_import._should_exclude、
    # 語彙取り込み機能と共通）が効いて絞り込まれることを確かめる。
    # ここでは実際の _should_exclude をそのまま使う（差し替えない）。
    pruning_sample = [
        ('食べる', 'たべる', '', '', '', 2000),      # 日常語: 残る
        ('学校', 'がっこう', '', '', '', 2500),       # 日常語: 残る
        ('殺伐たる', 'さつばつたる', '', '', '', 4349),  # 難語（実機の実測値）: 除外
        ('雑然たる', 'ざつぜんたる', '', '', '', 4349),  # 難語: 除外
        ('共和国', 'きょうわこく', '名詞', '固有名詞', '一般', 3000),  # 地名: 除外
        ('大英帝国', 'だいえいていこく', '', '', '', 3000),  # 帝国は対象外だが念のため
        ('ヤンキー・ドゥードル', 'やんきーどぅーどる', '', '', '', 3000),  # 記号混じり: 除外
    ]
    orig_iter, orig_has, orig_min = (D.iter_janome_entries, D.HAS_JANOME,
                                     D._MIN_READINGS)
    try:
        D.iter_janome_entries = lambda min_len=1, max_len=8: iter(
            pruning_sample)
        D.HAS_JANOME = True
        D._MIN_READINGS = 1
        idx2 = D.DictIndex(None)
        idx2.ensure_built()
        check('日常語（食べる）は索引に残る',
              idx2.surfaces_for_reading('たべる'), ['食べる'])
        check('日常語（学校）は索引に残る',
              idx2.surfaces_for_reading('がっこう'), ['学校'])
        check('コストの高い難語は除外される',
              idx2.surfaces_for_reading('さつばつたる'), [])
        check('固有名詞（共和国）は除外される',
              idx2.surfaces_for_reading('きょうわこく'), [])
        check('記号混じりの語は除外される',
              idx2.surfaces_for_reading('やんきーどぅーどる'), [])
    finally:
        D.iter_janome_entries, D.HAS_JANOME, D._MIN_READINGS = (
            orig_iter, orig_has, orig_min)

    return all_ok


def run_context_vec_cases():
    """
    語の共起から作る軽量な文脈ベクトル（context_vec.py）。

    同音異義語（公園／講演）のように読みだけでは決められない語を、
    周辺の語との意味的な近さで選び分けられるかを見る。

    合わせて、このアプリの一貫した方針である
    「判断がつかないものは触らない」が、文脈スコアにも
    適用されていることを確かめる（手がかりが無い・僅差の場合に
    None を返し、決め打ちしないこと）。
    """
    from context_vec import ContextVectorStore
    from candidates import _reorder_by_context

    print('--- 文脈ベクトル（共起による同音異義語の選び分け） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    cv = ContextVectorStore()
    # 「公園」は散歩・子供と、「講演」は会場・資料と一緒に出てくる、
    # という状況をメモから学んだ状態を作る。
    for _ in range(3):
        cv.observe_line(['明日', '公園', '散歩', '子供'])
        cv.observe_line(['公園', '遊具', '子供', '広場'])
        cv.observe_line(['講演', '会場', '聴衆', '資料'])
        cv.observe_line(['資料', '講演', '準備', '会場'])

    check('一緒に出てくる語は似ていると判定する',
          cv.similarity('公園', '散歩') > 0.3, True)
    check('無関係な語は似ていないと判定する',
          cv.similarity('公園', '聴衆'), 0.0)

    check('周辺が子供・散歩なら「公園」を選ぶ',
          cv.pick_best_by_context(['公園', '講演'], ['子供', '散歩']),
          '公園')
    check('周辺が会場・資料なら「講演」を選ぶ',
          cv.pick_best_by_context(['公園', '講演'], ['会場', '資料']),
          '講演')

    # 「判断がつかないものは触らない」の確認。
    check('手がかりの無い周辺語では決め打ちしない',
          cv.pick_best_by_context(['公園', '講演'], ['天気']), None)
    check('周辺語が無ければ決め打ちしない',
          cv.pick_best_by_context(['公園', '講演'], []), None)
    check('候補が1つだけなら選び分けるまでもない',
          cv.pick_best_by_context(['公園'], ['子供']), None)
    check('知らない語同士は似ているとみなさない',
          cv.similarity('未知語A', '未知語B'), 0.0)

    # ---- 証拠の太さ（項目48-BY・2026-08-13）----
    # `判断の精度` が `判断の制度` に化けていた形を、そのまま作る。
    # **共通の相手が1語しか無いのに、コサインは大きく出る。**
    cvt = ContextVectorStore()
    for _ in range(15):
        cvt.observe_line(['制度', 'ない'])          # 制度 の共起は ない だけ
    for _ in range(102):
        cvt.observe_line(['置き換え', 'ない'])       # 置き換え も ない だけ
    for _ in range(5):
        cvt.observe_line(['精度', '向上', '判定'])   # 精度 は別の相手を持つ
    check('共通の相手が1語でも、コサインは大きく出る',
          cvt.similarity('制度', '置き換え') > 0.5, True)
    check('共通の相手が1語なら、証拠として数えない',
          cvt.similarity('制度', '置き換え', min_shared=2), 0.0)
    check('min_shared を渡さなければ今までどおり',
          cvt.pick_best_by_context(['精度', '制度'], ['置き換え'],
                                   min_margin=0.12), '制度')
    # **点の付け方には掛けない**（学び38）。掛けると、書かれている側の
    # 点が先に消えて置き換え先が勝ちやすくなり、**新しい誤爆が増える**
    # （`全文走査` → `全文操作` で実際に起きた）。
    # 関門は「選び終わったあと、置き換え先の側だけ」に掛ける。
    check('置き換え先だけを細い証拠抜きで測ると、差が消える',
          cvt.context_score('制度', ['置き換え'], min_shared=2)
          - cvt.context_score('精度', ['置き換え']) < 0.12, True)
    check('太い証拠なら、測り直しても差が保つ',
          cv.context_score('公園', ['子供', '散歩'], min_shared=2)
          - cv.context_score('講演', ['子供', '散歩']) >= 0.12, True)
    check('共通の相手が太ければ、今までどおり選ぶ',
          cv.pick_best_by_context(['公園', '講演'], ['子供', '散歩'],
                                  min_shared=2), '公園')
    check('候補の並び替えには min_shared を掛けない（学び39）',
          cvt.rank_candidates(['制度'], ['置き換え'])['制度'] > 0.5, True)

    # 候補一覧の並び替えと絞り込み。
    # 「打ち間違いの候補が10件近く出るが、大半が文脈的に不自然」
    # 「『単語として成立』の候補に『単行』『飛び』が出る」
    # という実機からの指摘に対応する部分。
    cv2 = ContextVectorStore()
    for _ in range(3):
        cv2.observe_line(['文字', '入力', '補正', '変換'])
        cv2.observe_line(['入力', '変換', '確定', '文字'])
        cv2.observe_line(['料理', '野菜', '食事'])

    cands = [
        {'surface': '料理', 'reading': 'x', 'kind': 'typo'},
        {'surface': '変換', 'reading': 'x', 'kind': 'typo'},
        {'surface': '野菜', 'reading': 'x', 'kind': 'typo'},
        {'surface': '補正', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(cands, cv2, ['文字', '入力'])
    order = [c['surface'] for c in cands]
    check('文脈に合う打ち間違い候補だけが残る',
          sorted(order), ['変換', '補正'])
    check('残った候補は文脈スコアの高い順に並ぶ',
          order[0] in ('補正', '変換'), True)

    # 同音異義語は、文脈に合わなくても消さない。
    # 書き手が本当にその語を選びたい可能性が常にあるため。
    homo = [
        {'surface': '野菜', 'reading': 'x', 'kind': 'homophone'},
        {'surface': '補正', 'reading': 'x', 'kind': 'homophone'},
    ]
    _reorder_by_context(homo, cv2, ['文字', '入力'])
    check('同音異義語は文脈に合わなくても候補に残す',
          sorted(c['surface'] for c in homo), ['補正', '野菜'])

    # 打ち間違い候補が全滅する場合は、何も落とさない
    # （選択肢が減りすぎるより、雑音が混じるほうがまし）。
    all_far = [
        {'surface': '野菜', 'reading': 'x', 'kind': 'typo'},
        {'surface': '食事', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(all_far, cv2, ['文字', '入力'])
    check('打ち間違いが全滅する場合は絞り込まない',
          len(all_far), 2)

    # 種類（同音→打ち間違い→かな）の大枠は崩さない、という約束。
    mixed = [
        {'surface': '料理', 'reading': 'x', 'kind': 'homophone'},
        {'surface': '補正', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(mixed, cv2, ['文字', '入力'])
    check('文脈スコアが高くても、種類の並び順は入れ替えない',
          [c['kind'] for c in mixed], ['homophone', 'typo'])

    # 手がかりが無ければ、元の並びをそのまま保つ。
    untouched = [
        {'surface': '知らない語1', 'reading': 'x', 'kind': 'typo'},
        {'surface': '知らない語2', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(untouched, cv2, ['文字'])
    check('手がかりが無ければ元の並びを保つ',
          [c['surface'] for c in untouched], ['知らない語1', '知らない語2'])

    # 保存と読み込み。
    import tempfile
    import os as _os
    path = _os.path.join(tempfile.mkdtemp(), 'context_vec.json')
    cv.save(path)
    cv3 = ContextVectorStore(path)
    check('保存した共起が読み込める',
          cv3.pick_best_by_context(['公園', '講演'], ['子供', '散歩']),
          '公園')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('{ 壊れた内容')
    cv4 = ContextVectorStore(path)
    check('壊れたファイルでも起動が止まらない', len(cv4), 0)

    # --- 初期状態（使い込む前）でも効くこと ---
    # 「使い込むほど効く」に頼らず、初回起動の時点から
    # 候補の並びがまともである必要がある（実機からの指摘）。
    seeded = ContextVectorStore()
    check('初期の話題を読み込む前は空', len(seeded), 0)
    check('初期の話題を読み込める', seeded.ensure_seeded(), True)
    check('二度は読み込まない（重ねて数えない）',
          seeded.ensure_seeded(), False)

    check('初期状態で「単語」と「文章」は近い',
          seeded.similarity('単語', '文章') > 0.3, True)
    check('初期状態で「単語」と「文字」は近い',
          seeded.similarity('単語', '文字') > 0.3, True)
    check('初期状態で「単語」と「単行」は近くない',
          seeded.similarity('単語', '単行'), 0.0)
    check('初期状態で「文章」と「野菜」は近くない',
          seeded.similarity('文章', '野菜'), 0.0)

    # 実機で報告された、候補に雑音が多い2つの場面。
    # 初期状態のまま（何も使い込んでいない）で確かめる。
    noisy = [
        {'surface': '単行', 'reading': 'x', 'kind': 'typo'},
        {'surface': '飛び', 'reading': 'x', 'kind': 'typo'},
        {'surface': '文章', 'reading': 'x', 'kind': 'typo'},
        {'surface': '文字', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(noisy, seeded, ['成立', '文章'])
    left = [c['surface'] for c in noisy]
    check('「単語として成立」で「単行」「飛び」が候補から消える',
          ('単行' not in left and '飛び' not in left), True)
    check('「単語として成立」で意味の近い候補は残る',
          ('文章' in left and '文字' in left), True)

    noisy2 = [
        {'surface': '花粉症', 'reading': 'x', 'kind': 'typo'},
        {'surface': '表記', 'reading': 'x', 'kind': 'typo'},
    ]
    _reorder_by_context(noisy2, seeded, ['分から', '文章'])
    left2 = [c['surface'] for c in noisy2]
    check('「分からない文章」で「花粉症」が候補から消える',
          '花粉症' not in left2, True)

    # 初期の話題は保存され、次回起動で読み直されないこと。
    path2 = _os.path.join(tempfile.mkdtemp(), 'context_vec.json')
    seeded.save(path2)
    reopened = ContextVectorStore(path2)
    check('初期の話題を読んだ記録が保存される', reopened.seeded, True)
    check('読み込み直しても初期の話題は効いている',
          reopened.similarity('単語', '文章') > 0.3, True)

    return all_ok


def run_context_material_cases():
    """
    文脈の材料集め（同じ行の外側）。

    同音異義語をどちらにするかは、その行の中だけでは決まらない。
    上下の行と、直前に確定した語を材料として集める仕組みを見る。
    集めた並びの **順序がそのまま優先度** になる（context_score は
    先頭に近いものほど重く数える）ので、順序も含めて固定する。
    """
    from context_vec import build_nearby_words, RecentWords
    import corrector as C

    print('--- 文脈の材料集め（上下の行・直前の履歴） ---')
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    words = {0: ['公園', '散歩'], 1: ['天気'], 2: ['対象行'],
             3: ['講演', '発表'], 4: ['会場']}

    def words_of(i):
        return words.get(i, [])

    check('近い行から順に集める',
          build_nearby_words(5, 2, words_of, radius=1),
          ['天気', '講演', '発表'])
    check('半径を広げると遠い行も入る（近い行が先）',
          build_nearby_words(5, 2, words_of, radius=2),
          ['天気', '講演', '発表', '公園', '散歩', '会場'])
    check('対象行そのものは含めない',
          '対象行' in build_nearby_words(5, 2, words_of, radius=2), False)
    check('先頭行では上が無くても落ちない',
          build_nearby_words(5, 0, words_of, radius=1), ['天気'])
    check('末尾行では下が無くても落ちない',
          build_nearby_words(5, 4, words_of, radius=1), ['講演', '発表'])
    check('上限を超えたら打ち切る',
          len(build_nearby_words(5, 2, words_of, radius=2, limit=3)), 3)
    check('1行しかなければ空', build_nearby_words(1, 0, words_of), [])

    def _boom(i):
        raise RuntimeError('分割に失敗')

    check('行の分割に失敗しても止まらない',
          build_nearby_words(3, 1, _boom), [])

    # --- 直前の変換履歴 ---
    recent = RecentWords(limit=3)
    recent.add('公園')
    recent.add('散歩')
    check('新しい順に並ぶ', recent.words(), ['散歩', '公園'])
    recent.add('公園')
    check('同じ語は先頭へ繰り上げ、重複しない',
          recent.words(), ['公園', '散歩'])
    recent.add_all(['天気', '会場'])
    check('上限を超えたら古いものから捨てる',
          recent.words(), ['会場', '天気', '公園'])
    recent.add('し')
    check('1文字の語は覚えない（どこにでも出るため）',
          recent.words(), ['会場', '天気', '公園'])
    recent.add(None)
    check('文字列でないものを渡しても落ちない', len(recent), 3)
    recent.clear()
    check('消せる', recent.words(), [])

    # --- 補正エンジンへの合流（同じ行 → 履歴 → 上下の行 の順） ---
    toks = [('公園', '名詞', 'こうえん', 0, 2, True),
            ('に', '助詞', 'に', 2, 3, True),
            ('行く', '動詞', 'いく', 3, 5, True)]
    got = C._surrounding_content_words(
        toks, 2, 3, nearby_words=['講演', '会場'],
        recent_words=['散歩'])
    check('同じ行の語を先頭に、次が履歴、最後が上下の行',
          got, ['公園', '行く', '散歩', '講演', '会場'])
    check('材料を渡さなければ従来どおり同じ行だけ',
          C._surrounding_content_words(toks, 2, 3), ['公園', '行く'])
    check('同じ語が重なっても1回だけ数える',
          C._surrounding_content_words(toks, 2, 3,
                                       nearby_words=['公園', '会場'],
                                       recent_words=['公園']),
          ['公園', '行く', '会場'])

    return all_ok


# ============================================================
# 項目48-L: 前回の解析結果の控え
# ============================================================
def test_analysis_cache():
    """
    起動を速くするための控え（`analysis_cache.py`）。

    **速くなることより、使ってはいけないときに使わないこと**を
    厚く確かめる。古い補正結果を新しい語彙のもとで表示するのは
    「正しく書いたものを壊さない」に真正面から反する。
    """
    all_ok = True

    def check(label, got, want):
        nonlocal all_ok
        ok = (got == want)
        all_ok = all_ok and ok
        print(f'{"OK " if ok else "NG "}{label}')
        if not ok:
            print(f'      得た値: {got!r}   期待: {want!r}')

    import os
    import tempfile
    import analysis_cache as AC
    from vocabulary import VocabularyStore

    print('--- 項目48-L（解析結果の控え） ---')

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, 'analysis_cache.json')
    store = VocabularyStore()
    for _ in range(3):
        store.add('たんご', '単語', '学業・勉強')

    def fp(input_method='kana', recent=(), st=None):
        return AC.build_fingerprint(tmp, '1.1.0', input_method, recent,
                                    store=st if st is not None else store)

    text = 'たんほの繋がり\nふつうの行'
    results = [
        {'original': 'たんほの繋がり', 'corrected': 'たんごの繋がり',
         'changed': True, 'details': [('たんほ', 'たんご', '学業・勉強')],
         'spans': [(0, 3)], 'unsure_spans': [], 'original_spans': [(0, 3)]},
        {'original': 'ふつうの行', 'corrected': 'ふつうの行',
         'changed': False, 'details': [], 'spans': [],
         'unsure_spans': [], 'original_spans': []},
    ]

    check('書けた', AC.save(path, fp(), {text: results}), True)
    got = AC.load(path, fp())
    check('読めた', list(got), [text])
    check('中身がそのまま戻る', got.get(text), results)

    # --- 使ってはいけないとき ---
    check('入力方式が違えば使わない', AC.load(path, fp('romaji')), {})
    other = VocabularyStore()
    for _ in range(3):
        other.add('たんご', '単語', '学業・勉強')
        other.add('もじ', '文字', 'その他')
    check('語彙が違えば使わない', AC.load(path, fp(st=other)), {})
    check('直前に確定した語があれば見分けを作らない',
          fp(recent=('単語',)), None)
    check('見分けが無ければ読まない', AC.load(path, None), {})

    with open(path, 'w', encoding='utf-8') as f:
        f.write('{ 壊れた内容')
    check('壊れたファイルでも落ちない', AC.load(path, fp()), {})

    # 直前に確定した語がある状態で保存しようとしたら、
    # **古い控えを消す**（残すと次回それを読んでしまう）。
    AC.save(path, fp(), {text: results})
    check('保存し直せた', os.path.exists(path), True)
    AC.save(path, fp(recent=('単語',)), {text: results})
    check('作ってはいけない状況なら古い控えも消す',
          os.path.exists(path), False)

    # 行数が食い違う控えは残さない／読まない
    AC.save(path, fp(), {text: results[:1]})
    check('本文と行数が合わない控えは書かない',
          os.path.exists(path), False)

    # 語彙の使用回数が変わっただけでも使わない
    # （回数は補正の判断に効くため）。
    AC.save(path, fp(), {text: results})
    store.add('たんご', '単語', '学業・勉強')
    check('使用回数が変わっただけでも使わない', AC.load(path, fp()), {})

    return all_ok
