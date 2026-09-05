"""B6. 추천 층.

두 축을 한 점수 안에서 저울질하지 않고 순서대로 적용한다.

    ① 종목 선택      ← 선호축만 (데이터 기반)
    ② 안전 필터       ← 부상·연령은 하드 컷, 강도는 순위 강등 (§ _apply_safety)
    ③ 강도·빈도 조절  ← 체력축
    ④ 보완 운동       ← 체력축 약한 부위

체력 배정 정확도가 50% 내외이므로 체력축은 종목 선택에 관여하지 않는다.
배정이 틀려도 "엉뚱한 종목"이 아니라 "강도가 한 단계 어긋남"으로 실패하게 만드는 구조다.
"""
import json
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"

MATRIX = pd.read_csv(DATA / "preference_sport_matrix.csv")
MASTER = pd.read_csv(DATA / "sport_master.csv")
FACILITY = pd.read_csv(DATA / "sport_facility_map.csv")
with open(DATA / "rules.json", encoding="utf-8") as f:
    RULES = json.load(f)

MASTER_BY_SPORT = MASTER.set_index("종목").to_dict("index")
FACILITY_BY_SPORT = FACILITY.set_index("종목").to_dict("index")
INTENSITY_ORDER = ["저", "중", "고"]
OVER_CAP_PENALTY = RULES["scoring"]["강도상한초과_감산비율"]


def recommend(preference_result=None, fitness_result=None, age=None,
              discomfort_areas=None, played_sports=None, interested_sports=None,
              survey=None, top_n=None):
    """설문 배정 결과 → 운동 추천.

    preference_result  : assign.assign_preference() 반환값. None 이면 비참여자
                         (선호 유형이 없으므로 '익숙한 운동'만 추천)
    fitness_result     : assign.assign_fitness() 반환값. 없으면 강도 조절·보완 생략
    discomfort_areas   : ["무릎", ...] 사용자가 직접 고른 불편 부위
    played_sports      : Q12 자주 해온 운동 (복수)
    interested_sports  : Q11 관심 있는 운동 (복수)
    survey             : 선호 문항 원본 {"운동목적", "운동시간대", "운동강도"}.
                         종목 속성과 맞춰 점수를 보정하는 데 쓴다

    추천은 두 갈래 + 기반 활동이다.
      기반 활동   — 걷기. 어느 유형에서든 1위라 추천 칸에 두면 다른 종목을 밀어낸다
      익숙한 운동 — 사용자가 고른 종목 중 지금 할 수 있는 것
      새로운 운동 — 고르지 않은 종목 중 같은 유형에서 적합도가 높은 것
    """
    discomfort_areas = set(discomfort_areas or [])
    chosen = _user_choice_weights(played_sports, interested_sports)
    class_id = preference_result["class_id"] if preference_result else None
    baseline_sports = set(RULES["기반활동"]["종목"])

    ranked = _score_sports(class_id) if class_id else []
    prescription = _prescribe(fitness_result, age)          # ③ 먼저 강도 상한을 정하고

    # 기반 활동은 두 갈래 어디에도 넣지 않고 따로 뺀다
    baseline = [s for s in ranked if s["종목"] in baseline_sports]
    ranked = [s for s in ranked if s["종목"] not in baseline_sports]

    familiar_pool = _familiar_pool(chosen, ranked, baseline_sports)
    new_pool = [s for s in ranked if s["종목"] not in chosen]

    familiar_pool = [_apply_survey(s, survey) for s in familiar_pool]
    familiar_pool.sort(key=lambda i: (i["사용자가중"], i["점수"] or 0), reverse=True)

    familiar, ex_familiar = _apply_safety(familiar_pool, age, discomfort_areas, prescription)
    new_items, ex_new = _apply_safety(_rescore_new(new_pool, survey), age,
                                      discomfort_areas, prescription)
    # 강도 상한 초과 종목은 점수가 깎인 채로 돌아온다. 여기서 다시 정렬해 반영한다
    familiar.sort(key=lambda i: (i["사용자가중"], i["점수"] or 0), reverse=True)
    new_items.sort(key=lambda i: (i["점수"] or 0), reverse=True)

    n_familiar = top_n or RULES["buckets"]["익숙한_개수"]
    n_new = top_n or RULES["buckets"]["새로운_개수"]

    return {
        "선호유형": None if not preference_result else {
            "class_id": class_id,
            "name": preference_result.get("name"),
            "probability": preference_result.get("probability"),
        },
        "체력유형": None if not fitness_result else {
            "segment": fitness_result["segment"],
            "confidence": fitness_result["confidence"],
            "ambiguous": fitness_result["ambiguous"],
            "alternative": fitness_result["alternative"],
        },
        "기반활동": _baseline_block(baseline, chosen),
        "익숙한운동": familiar[:n_familiar],
        "새로운운동": new_items[:n_new],
        "제외종목": ex_familiar + ex_new,
        "처방": prescription,
        "보완운동": _support_exercises(fitness_result),
        "안내": _guidance(fitness_result, prescription, familiar, ex_familiar, chosen),
        "면책": RULES["safety"]["면책"],
    }


def _user_choice_weights(played_sports, interested_sports):
    """자주 해온 운동에 더 큰 가중. 둘 다 고르면 큰 쪽."""
    w_played = RULES["buckets"]["자주해온_가중"]
    w_interest = RULES["buckets"]["관심_가중"]
    weights = {}
    for sport in interested_sports or []:
        weights[sport] = max(weights.get(sport, 0), w_interest)
    for sport in played_sports or []:
        weights[sport] = max(weights.get(sport, 0), w_played)
    return weights


def _baseline_block(baseline, chosen):
    """기반 활동 — 걷기는 어느 유형에서든 1위라 추천 갈래를 밀어낸다. 그래서 여기로 빼둔다.

    계약상 계속 내보내지만 화면에는 싣지 않는다(2026-09-05) — 화면은 익숙한운동·새로운운동
    두 갈래만 보여준다. 지도·기록 등 다른 층은 이 값을 그대로 쓸 수 있다.
    """
    spec = RULES["기반활동"]
    out = []
    for sport in spec["종목"]:
        item = next((dict(s) for s in baseline if s["종목"] == sport), None)
        if item is None:
            meta = MASTER_BY_SPORT.get(sport)
            if meta is None:
                continue
            item = {"종목": sport, "강도": meta.get("강도"), "부담부위": _areas(meta),
                    "고령적합": meta.get("고령적합"), "실내외": meta.get("실내외")}
        item["처방"] = spec["처방"]
        item["근거"] = spec["근거"]
        item["이미하는중"] = sport in chosen
        item["시설"] = facility_query(sport)
        out.append(item)
    return out


def _apply_survey(item, survey):
    """설문 응답과 종목 속성을 맞춰 점수를 보정한다.

    선호축 점수가 주이고 이것은 보정이다. 크기는 순위를 뒤집기보다
    비슷한 후보 사이를 가르는 수준으로 잡았다.
    """
    if not survey or item.get("점수") is None:
        return item

    cfg = RULES["설문반영"]
    meta = MASTER_BY_SPORT.get(item["종목"], {})
    delta, reasons = 0, []

    want = survey.get("운동강도")
    have = item.get("강도")
    if want in INTENSITY_ORDER and have in INTENSITY_ORDER:
        gap = abs(INTENSITY_ORDER.index(want) - INTENSITY_ORDER.index(have))
        if gap == 0:
            delta += cfg["강도일치_가산"]
            reasons.append(f"원하시는 강도({want})와 맞음")
        elif gap >= 2:
            delta -= cfg["강도2단계차이_감산"]
            reasons.append(f"원하시는 강도({want})와 차이가 큼")

    if survey.get("운동목적") == "대인관계 및 사교":
        group = meta.get("그룹성")
        if group == "그룹":
            delta += cfg["사교목적_그룹가산"]
            reasons.append("여럿이 함께하는 종목")
        elif group == "혼합":
            delta += cfg["사교목적_혼합가산"]

    if survey.get("운동시간대") == "저녁(18-22시)" and meta.get("실내외") == "실내":
        delta += cfg["저녁시간대_실내가산"]
        reasons.append("저녁에 하기 좋은 실내 종목")

    if delta:
        item = dict(item)
        item["점수"] = round(item["점수"] + delta, 1)
        item["맞춤이유"] = reasons
    return item


def _familiar_pool(chosen, ranked, baseline_sports=frozenset()):
    """사용자가 고른 종목. 유형 적합도가 있으면 순위 보조로 쓴다.

    그 유형에서 표본이 적어 행렬에 없는 종목도 사용자가 골랐으면 포함한다 —
    본인이 하겠다는 운동을 데이터가 없다고 빼면 안 된다.
    """
    by_sport = {s["종목"]: s for s in ranked}
    pool = []
    for sport, weight in chosen.items():
        if sport in baseline_sports:
            continue  # 기반 활동은 따로 표시한다
        meta = MASTER_BY_SPORT.get(sport)
        if meta is None:
            continue  # 마스터에 없는 종목명은 무시
        item = dict(by_sport.get(sport) or {
            "종목": sport, "점수": None, "선호점수비율": None, "Lift": None,
            "강도": meta.get("강도", "미확인"), "부담부위": _areas(meta),
            "고령적합": meta.get("고령적합"), "실내외": meta.get("실내외"),
        })
        item["사용자가중"] = weight
        item["이유"] = ("자주 해오신 운동입니다" if weight >= RULES["buckets"]["자주해온_가중"]
                      else "관심 있다고 고르신 운동입니다")
        pool.append(item)

    pool.sort(key=lambda i: (i["사용자가중"], i["점수"] or 0), reverse=True)
    return pool


def _rescore_new(pool, survey=None):
    """'새로운 운동' 은 Lift 가중을 올려 그 유형을 차별화하는 종목이 드러나게 한다.

    익숙한 쪽이 안전판이라 이쪽은 탐색적이어도 된다.
    점수를 다시 매긴 뒤 설문 응답으로 보정한다.
    """
    if not pool:
        return pool
    w_lift = RULES["buckets"]["새로운_Lift_가중"]
    cap = RULES["scoring"]["Lift_상한"]

    shares = pd.Series([i["선호점수비율"] or 0 for i in pool])
    lifts = pd.Series([min(i["Lift"] or 1.0, cap) for i in pool])
    scores = (1 - w_lift) * _normalize(shares) + w_lift * _normalize(lifts)

    out = []
    for item, score in zip(pool, scores * 100):
        item = dict(item)
        item["점수"] = round(float(score), 1)
        out.append(_apply_survey(item, survey))
    return sorted(out, key=lambda i: i["점수"], reverse=True)


# ------------------------------------------------------------------
# ① 종목 선택 — 선호축만
# ------------------------------------------------------------------
def _score_sports(class_id):
    part = MATRIX[MATRIX["class_id"] == class_id].copy()
    if part.empty:
        raise ValueError(f"행렬에 없는 클래스: {class_id}")

    # 표본이 극소수인 종목은 Lift 가 과장되므로 먼저 잘라낸다.
    # (원 클러스터링의 특수운동 산출 기준과 동일)
    part = part[(part["참여가중인원"] >= RULES["scoring"]["최소_참여가중인원"])
                & (part["클래스참여율"] >= RULES["scoring"]["최소_클래스참여율"])]
    # "그 외 종목" 묶음은 사용자에게 제시할 수 없다
    recommendable = set(MASTER.loc[MASTER["추천가능"] == "Y", "종목"])
    part = part[part["운동종목"].isin(recommendable)]
    if part.empty:
        raise ValueError(f"추천 가능한 종목이 없다: {class_id}")

    w_share = RULES["scoring"]["선호점수비율_가중"]
    w_lift = RULES["scoring"]["Lift_가중"]
    lift_cap = RULES["scoring"]["Lift_상한"]

    share = part["선호점수비율"]
    lift = part["Lift"].fillna(1.0).clip(upper=lift_cap)

    part["점수"] = (w_share * _normalize(share) + w_lift * _normalize(lift)) * 100
    part = part.sort_values("점수", ascending=False)

    out = []
    for row in part.itertuples():
        meta = MASTER_BY_SPORT.get(row.운동종목, {})
        out.append({
            "종목": row.운동종목,
            "점수": round(float(row.점수), 1),
            "선호점수비율": round(float(row.선호점수비율), 1),
            "Lift": None if pd.isna(row.Lift) else round(float(row.Lift), 2),
            "강도": meta.get("강도", "미확인"),
            "부담부위": _areas(meta),
            "고령적합": meta.get("고령적합"),
            # 날씨 재정렬은 표현 계층에서 한다. 종목명으로 실내외를 추측하게 두지 않는다
            "실내외": meta.get("실내외"),
            "이유": _reason(row),
        })
    return out


def _normalize(series):
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-9:
        return series * 0 + 0.5
    return (series - lo) / (hi - lo)


def _reason(row):
    if pd.notna(row.Lift) and row.Lift >= 1.5 and row.클래스참여율 >= 3:
        return f"같은 유형에서 유독 많이 하는 종목 (평균 대비 {row.Lift:.1f}배)"
    if row.선호점수비율 >= 10:
        return f"같은 유형이 가장 많이 하는 종목 (선호도 {row.선호점수비율:.0f}%)"
    return "같은 유형에서 자주 선택되는 종목"


# ------------------------------------------------------------------
# ② 안전 필터 — 부위·연령은 하드 컷, 강도는 원칙적으로 소프트
# ------------------------------------------------------------------
def _apply_safety(ranked, age, discomfort_areas, prescription):
    """부위·연령은 종목을 지우고, 강도는 순위를 내린다.

    강도까지 지우면 '판정하지 않는 설계'가 깨진다. 지침 원문도 저조형에 대해
    "가볍거나 중간 강도로 주 1회부터 시작해 점차 높인다"이지 고강도 금지가 아니다.
    실제 위험군(노인 + 전반적 저조형 + 배정 확정)에서만 하드 컷을 유지한다.
    """
    kept, demoted, excluded = [], [], []
    elderly = age is not None and age >= 65
    cap = prescription.get("권장강도상한")
    cap_idx = INTENSITY_ORDER.index(cap) if cap in INTENSITY_ORDER else len(INTENSITY_ORDER) - 1
    hard_gate = prescription.get("강도컷") == "하드"

    for item in ranked:
        reason = None
        overlap = discomfort_areas & set(item["부담부위"])
        intensity = item["강도"]
        over_cap = INTENSITY_ORDER.index(_effective_intensity(intensity)) > cap_idx

        if overlap:
            reason = f"불편 부위({', '.join(sorted(overlap))})와 겹쳐 제외"
        elif elderly and item["고령적합"] == "비권장":
            reason = "고령 사용자에게 기본 제외되는 종목"
        elif over_cap and hard_gate:
            reason = f"권장 강도 상한('{cap}')을 넘어 제외"

        if reason:
            excluded.append({"종목": item["종목"], "사유": reason})
            continue

        if intensity == "미확인":
            item = {**item, "주의": "강도 미확인 종목"}
        # 장소 연결 레이어가 바로 쓸 수 있게 검색 대상 시설을 붙인다
        item = {**item, "시설": facility_query(item["종목"])}

        if over_cap:
            # 맨 뒤로 밀어버리면 목록 길이에 잘려 사실상 삭제가 된다.
            # 점수를 깎아 두고 정렬에 맡긴다 — 적합도가 뚜렷이 높으면 배지를 달고 남는다.
            item = {**item, "강도주의": f"권장하는 강도('{cap}')보다 강한 편입니다. "
                                        f"낮은 강도로 짧게 시작해 보세요"}
            if item.get("점수") is not None:
                item = {**item, "점수": round(item["점수"] * OVER_CAP_PENALTY, 1)}
            demoted.append(item)
        else:
            kept.append(item)
    return kept + demoted, excluded


def _effective_intensity(intensity):
    """강도 미확인 종목은 '중'으로 간주한다.

    모른다는 이유로 상한을 그냥 통과시키면, 강도를 아는 종목만 잘려나가고
    강도를 모르는 종목이 그 자리를 차지하는 역전이 생긴다.
    """
    return intensity if intensity in INTENSITY_ORDER else "중"


def _areas(meta):
    value = meta.get("부담부위")
    if not isinstance(value, str) or not value:
        return []
    return [a for a in value.split("|") if a]


# ------------------------------------------------------------------
# 장소 연결 인계 — 실제 주변 시설 검색은 GIS 쪽에서 한다
# ------------------------------------------------------------------
def facility_query(sport):
    """이 종목을 하려면 어떤 시설을 찾아야 하는지 알려준다.

    반환값을 GIS 레이어가 받아 사용자 위치 기준으로 실제 장소를 검색한다.
    이 함수는 검색하지 않는다 — 검색 대상만 정한다.

    시설유형   : 세부시설 상위 후보 (검색 키워드). 국민생활체육조사 세부시설 분류 기준
    시설대분류 : 공공/민간/학교/직장/자가/기타
    신뢰도     : '낮음'이면 세부시설 응답률이 낮아 후보가 편향됐을 수 있다
    시설불필요 : 자가시설(집) 비율. 높으면 장소 연결이 덜 중요한 종목
    """
    row = FACILITY_BY_SPORT.get(sport)
    if row is None:
        return {"종목": sport, "시설유형": [], "시설대분류": [],
                "신뢰도": "없음", "비고": "표본 부족으로 시설 분포를 산출하지 않은 종목"}

    types, groups = [], []
    for i in (1, 2, 3):
        name = row.get(f"세부시설_{i}")
        if isinstance(name, str):
            types.append({"이름": name, "비율": row.get(f"세부시설_{i}_비율")})
    for i in (1, 2):
        name = row.get(f"시설대분류_{i}")
        if isinstance(name, str):
            groups.append({"이름": name, "비율": row.get(f"시설대분류_{i}_비율")})

    return {
        "종목": sport,
        "시설유형": types,
        "시설대분류": groups,
        "시설불필요_비율": row.get("시설불필요_비율"),
        "신뢰도": row.get("세부시설_신뢰도"),
        "표본": row.get("n"),
    }


# ------------------------------------------------------------------
# ③ 강도·빈도 처방
# ------------------------------------------------------------------
def _prescribe(fitness_result, age):
    stage = "노인" if (age is not None and age >= 65) else "성인"
    baseline = dict(RULES["baseline"][stage])
    result = {"기준": baseline, "생애주기": stage, "조정": None, "강도조정단계": 0,
              "강도컷": "소프트"}

    result["권장강도상한"] = _cap_intensity(0)
    if not fitness_result:
        return result

    adjust = RULES["segment_adjust"].get(fitness_result["segment"])
    if not adjust:
        return result

    # 배정이 모호한 것은 '체력이 낮다'가 아니라 '우리가 모른다'는 뜻이다.
    # 모른다는 이유로 상한을 낮추면 사용자의 44%가 고강도 종목을 통째로 잃는다.
    # 확신도는 종목을 지우는 데 쓰지 않고 안내 문구로만 알린다.
    steps = adjust.get("강도조정", 0)

    result["조정"] = {
        "세그먼트": fitness_result["segment"],
        "시작규칙": adjust.get("시작규칙"),
        "메시지": adjust.get("메시지"),
        "근거": adjust.get("근거"),
    }
    result["강도조정단계"] = steps
    result["권장강도상한"] = _cap_intensity(steps)

    # 상한 초과를 '제외'로 처리하는 경우는 실제 위험군 하나뿐이다 —
    # 노인 + 전반적 저조형 + 배정 확정. 그 밖에는 순위를 내리고 배지로 알린다.
    if stage == "노인" and steps < 0 and not fitness_result.get("ambiguous"):
        result["강도컷"] = "하드"
    return result


def _cap_intensity(steps):
    idx = max(0, min(len(INTENSITY_ORDER) - 1, 2 + steps))
    return INTENSITY_ORDER[idx]


# ------------------------------------------------------------------
# ④ 보완 운동
# ------------------------------------------------------------------
def _support_exercises(fitness_result, threshold=-0.3):
    if not fitness_result:
        return []
    z = fitness_result.get("z", {})
    weak = sorted((v, k) for k, v in z.items() if v < threshold)

    out = []
    for value, axis in weak:
        spec = RULES["weak_axis_support"].get(axis)
        if not spec or not spec["운동"]:
            continue  # 순발력처럼 근거가 없는 축은 제시하지 않는다
        out.append({
            "축": axis.replace("z_", ""),
            "z": round(float(value), 2),
            "운동": spec["운동"],
            "처방": spec["처방"],
            "근거": spec["근거"],
            "표현": "제안" if "없음" in spec["근거"] or "약함" in spec["근거"] else "지침",
        })
    return out[:2]


# ------------------------------------------------------------------
# 안내 문구
# ------------------------------------------------------------------
def _guidance(fitness_result, prescription, familiar, excluded_familiar, chosen):
    notes = []
    if chosen and not familiar and excluded_familiar:
        # 고른 종목이 전부 걸러진 경우 — 이유를 밝히지 않으면 사용자는 무시당했다고 느낀다
        notes.append("고르신 운동은 지금 단계에서 부담이 될 수 있어 대신 비슷한 종목을 담았습니다")
    elif not chosen:
        notes.append("관심 있는 운동을 골라주시면 더 맞는 추천을 드릴 수 있습니다")
    if fitness_result and fitness_result["ambiguous"]:
        notes.append(
            f"체력 유형이 '{fitness_result['segment']}'과 "
            f"'{fitness_result['alternative']}' 사이에 걸쳐 있습니다. "
            f"강도는 무리하지 않는 선에서 조절해 주세요")
    if prescription["강도조정단계"] < 0:
        notes.append(RULES["segment_adjust"]["전반적 저조형"]["시작규칙"])
    notes.extend(RULES["safety"]["상담안내"][:1])
    return notes


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "assignment"))
    sys.stdout.reconfigure(encoding="utf-8")
    from assign import assign_all

    r = assign_all(
        age=34, sex="남", regular_exercise=True,
        preference={"운동빈도": "일주일에 3번", "운동요일": "평일",
                    "운동시간대": "저녁(18-22시)", "운동목적": "건강 유지 및 체력증진",
                    "운동강도": "중", "체력인지": "보통이다"},
        fitness={"근력": 4, "근지구력": 2, "순발력": 3, "유연성": 2},
        height_cm=175, weight_kg=82)

    out = recommend(r["preference"], r["fitness"], age=34,
                    played_sports=["보디빌딩(헬스)"],
                    interested_sports=["배드민턴", "등산"],
                    discomfort_areas=["무릎"])
    print(json.dumps(out, ensure_ascii=False, indent=1))
