"""Ordinary object senses for choosing same-reading actions."""
OBJECTS={
 'payable_due':('pay_due','税金 税 会費 月謝 授業料 保険料 代金 年金'.split()),
 'attained_result':('attain_result','成功 成果 勝利 好成績 結果 収益 利益'.split()),
 'studied_discipline':('master_discipline','学問 学業 学術 武術 剣術 柔術 茶道 華道'.split()),
 'governed_society':('govern_society','国 国家 領土 天下 領地 藩'.split()),
 'assigned_duty':('fulfill_role','司会 議長 委員長 座長 主役 講師 審判 代理 担当 案内役'.split()),
 'employer':('employment','会社 銀行 病院 学校 役所 企業 官庁 市役所 工場'.split()),
 'effort_goal':('make_effort','改善 向上 解決 合理化 効率化 軽減 削減 促進 普及 防止 維持 確保'.split()),
 'healable_condition':('healing','病気 風邪 怪我 けが 傷 虫歯 骨折 腹痛 頭痛'.split()),
 'repairable_form':('structural_repair','誤字 誤り 間違い 誤植 表記 文章 原稿 コード バグ 不具合 癖 姿勢'.split()),
 'repairable_device':('structural_repair','機械 時計 自転車 車 エアコン パソコン プリンター カメラ キーボード マウス'.split()),
 'measured_dimension':('dimension_measure','長さ 距離 幅 高さ 深さ 角度 温度 気温 体温 血圧 速度 視力 聴力 寸法 精度'.split()),
 'measured_duration':('time_measure','時間 秒数 タイム'.split()),
 'measured_mass':('mass_measure','重さ 重量 質量 分量'.split()),
 'desired_outcome':('planned_achievement','改善 向上 解決 実現 合理化 効率化 連携 調和 安全 成長'.split()),
}
ACTIONS={'pay_due':frozenset(('納める',)),
         'attain_result':frozenset(('収める',)),
         'master_discipline':frozenset(('修める',)),
         'govern_society':frozenset(('治める',)),'fulfill_role':frozenset(('務める',)),
         'employment':frozenset(('勤める',)),
         'make_effort':frozenset(('努める',)),'healing':frozenset(('治す',)),
         'structural_repair':frozenset(('直す',)),'dimension_measure':frozenset(('測る',)),
         'time_measure':frozenset(('計る',)),
         'mass_measure':frozenset(('量る',)),
         'planned_achievement':frozenset(('図る',))}


FAMILIES={
 'attainment_action':(('pay_due','attain_result','master_discipline','govern_society'),
     '支払うもの、得る成果、身に付ける学問、統治する対象から同読みの動詞を比較しています'),
 'duty_action':(('fulfill_role','employment','make_effort'),
     '引き受ける役割、勤務先、努力の目標を元の名詞と格から比較しています'),
 'measurement_action':(('dimension_measure','time_measure','mass_measure','planned_achievement'),
     '値を測定する対象と、達成を目指す事柄から同読みの動詞を比較しています'),
 'repair_action':(('healing','structural_repair'),
     '病気やけがを治す意味と、物や表記を直す意味を対象から比較しています'),
}

CASES={'employment':'に','make_effort':'に'}

def frames(source):
    if not any(c in source for c in ('を','に')) or not any(word in source for role,words in OBJECTS.values() for word in words):return ()
    from morphology import tokenize
    from literal_examples import protected_ranges,overlaps
    from context_meaning import action_frame
    parts=tokenize(source);out=[];protected=None
    meanings=[(word,role) for role,words in OBJECTS.values() for word in words]
    from morphology import native_spelling_only
    for i,case in enumerate(parts[:-1]):
        if case.pos!='助詞' or case.surface not in ('を','に'):continue
        for word,expected in meanings:
            if case.surface!=CASES.get(expected,'を'):continue
            start=case.start-len(word)
            if start<0 or source[start:case.start]!=word:continue
            units=[t for t in parts[:i] if start<=t.start and t.end<=case.start]
            if (not units or units[0].start!=start or units[-1].end!=case.start
                    or not all(t.has_reading for t in units)
                    or not native_spelling_only(''.join(t.reading for t in units),word)):continue
            kind,(roles,reason)=next((kind,family) for kind,family in FAMILIES.items() if expected in family[0])
            frame=action_frame(source,parts,i,start,kind,expected,roles,reason,case_surface=case.surface)
            if frame is None:continue
            if protected is None:protected=protected_ranges(source)
            if not overlaps(start,frame['evidence_end'],protected):out.append(frame)
    return tuple(out)
