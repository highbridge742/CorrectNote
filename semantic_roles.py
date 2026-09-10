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

"""General semantic roles for an explicit accusative object.
Design and counterexamples: GPT-6, 2026-09-11. No typo/answer pairs or personal data.
This is positive ranking evidence after anomaly detection, not a prohibition or a detector.
Unknown or unmatched categories provide no evidence. Metaphor, metonymy and omitted
arguments remain possible. This is a small, versioned classification of ordinary
words and grammatical roles; it is not intended to describe all Japanese semantics.
"""
KNOWLEDGE_VERSION = '2026-09-11b'

NOUN_GROUPS={
 'information':'理由 原因 結果 意味 意図 事情 状況 状態 条件 仕様 手順 方法 概要 詳細 情報 内容 データ 記録 履歴 数値 値 住所 名前 氏名 番号 日時 時刻 日程 予定 計画 事実'.split(),
 'text':'文章 文 文字 文字列 単語 語句 書類 資料 書面 文書 本 書籍 新聞 雑誌 冊子 原稿 記事 報告書 説明書 手紙 メール 図 表 画像 写真 図面'.split(),
 'person':'人 人員 社員 部員 学生 先生 友人 家族 客 子供 子ども 利用者 作者 担当者 選手'.split(),
 'object':'荷物 道具 部品 材料 机 椅子 家具 服 衣服 靴 鉛筆 用紙 箱 袋 容器 鍵 窓 扉 戸'.split(),
 'money':'金 お金 資金 財産 費用 料金 代金 寄付金'.split(),
 'event':'会議 会合 集会 大会 試合 競技 選挙 授業 講義 式 会見 行事 催し'.split(),
 'process':'作業 仕事 処理 操作 計算 解析 検査 実験 調査 開発 印刷 通信 接続'.split(),
 'place':'場所 会場 部屋 教室 会議室 席 座席 宿 施設 店舗 建物 公園 道路'.split(),
 'food':'食事 料理 食品 食べ物 ご飯 パン 肉 魚 野菜 果物 菓子 お菓子'.split(),
 'drink':'水 茶 牛乳 飲料 飲み物 汁 スープ'.split(),
 'medicine':'薬 錠剤 カプセル'.split(),
}
PREDICATE_GROUPS=(
 ('information text','説明 解説 記述 表示 記録 報告 通知 伝達 提示 理解 把握 確認 検証 比較'),
 ('text','印刷 出版 再版 製本 校正 校閲 添削 翻訳 朗読 音読 書写 転記'),
 ('person','募集 採用 雇用 招待 招聘 招へい 救助'),
 ('money object food text','寄付 寄附 寄贈 提供 贈与'),
 ('event','休会 閉会 開会 開催 棄権 欠席'),
 ('event process','中止 再開 継続 実施 開始 終了'),
 ('object text food','並べる 整列 整理 運搬 保管 収納'),
 ('object text money','貸す 借りる'),
 ('object text money food','渡す 返す 戻す 預ける'),
 ('object text food','運ぶ 片付ける 買う 売る'),
 ('place event','予約'),
 ('food','食べる 食う 調理 料理 試食'),
 ('drink medicine','飲む'),
 ('medicine','服用'),
)
NOUN_ROLES={}
for role,words in NOUN_GROUPS.items():
 for w in words:NOUN_ROLES.setdefault(w,set()).add(role)
VERB_ROLES={}
for roles,words in PREDICATE_GROUPS:
 for w in words.split():VERB_ROLES.setdefault(w,set()).update(roles.split())


from functools import lru_cache


def object_before(context, start, tokenize):
    """Use an explicit を head across contiguous simple dative/location arguments."""
    parts=[t for t in tokenize(context) if t[4]<=start]
    if not parts or parts[-1][4]!=start:return ''
    i=len(parts)-1;edge=start
    for _ in range(3):
        if i<1:return ''
        particle=parts[i];noun=parts[i-1]
        if (not particle[1].startswith('助詞:格助詞') or particle[4]!=edge
                or noun[4]!=particle[3] or not noun[5] or not noun[1].startswith('名詞')):
            return ''
        if particle[0]=='を':
            return '' if '固有名詞' in noun[1] or '接尾' in noun[1] else noun[0]
        if particle[0] not in ('に','で','へ'):return ''
        # 別の述語や助詞を越えない。受け手・場所を表す既知の名詞句だけ。
        j=i-1
        while j>0 and i-j<4 and parts[j-1][4]==parts[j][3] and parts[j-1][5] and parts[j-1][1].startswith('名詞'):
            j-=1
        edge=parts[j][3];i=j-1
    return ''


@lru_cache(maxsize=4096)
def predicate_roles(surface):
    if surface in VERB_ROLES:return frozenset(VERB_ROLES[surface])
    from morphology import tokenize,dictionary_inflections
    parts=tokenize(surface)
    # 名詞の列から一部だけを拾って、その候補全体の動作の意味にしない。
    if not parts or parts[0].pos!='動詞' or not parts[0].has_reading:return frozenset()
    t=parts[0];roles=set()
    for pos,form,base,rd in dictionary_inflections(t.surface) or ():
        if pos.startswith('動詞,') and form==t.infl_form and rd==t.reading:
            roles.update(VERB_ROLES.get(base,()))
    return frozenset(roles)


def support(object_word, predicate):
    """Positive fit only: unclassified or other senses are not incompatibilities."""
    return bool(NOUN_ROLES.get(object_word,set()) & predicate_roles(predicate))


@lru_cache(maxsize=4096)
def _action_head(surface, following):
    """Only use predicate roles where a native verb/suru attachment exists."""
    from morphology import tokenize
    parts=tokenize(surface)
    if not parts or not parts[0].has_reading:return ''
    first=parts[0]
    if first.pos=='動詞':return surface
    if first.pos!='名詞' or not first.pos_sub.startswith('サ変接続'):return ''
    rest=parts[1:] if len(parts)>1 else tokenize(following)
    if rest and rest[0].has_reading and rest[0].pos=='動詞' and rest[0].base_form=='する':
        return first.surface
    return ''


def candidate_evidence(object_word, surface, following):
    """Expose the source and roles used for ranking, including no-fit results."""
    if object_word not in NOUN_ROLES:return None
    head=_action_head(surface,following[:8])
    if not head:return None
    nominal=frozenset(NOUN_ROLES[object_word]);predicate=predicate_roles(head)
    return dict(version=KNOWLEDGE_VERSION,object=object_word,predicate=head,
                object_roles=sorted(nominal),predicate_roles=sorted(predicate),
                shared_roles=sorted(nominal & predicate))


def candidate_support(object_word, surface, following):
    evidence=candidate_evidence(object_word,surface,following)
    return bool(evidence and evidence['shared_roles'])
