# -*- coding: utf-8 -*-
"""시간대 혼잡도 — 설문 Q7(주로 몇 시에 운동하는가)과 겹쳐 쓴다.

    from geo.crowding import get_crowding, slot_to_hour
    get_crowding("관악구", "평일", 19)

**이건 자치구 전체의 유동인구이지 운동시설 혼잡도가 아니다.**
중구의 낮 42만 명은 직장인이지 체육관 이용자가 아니다. 그래서
"한산해요/붐벼요"라고 단정하지 않고 "사람이 많은 편이에요" 수준으로만 말한다.

추천 순서·강도에 관여하지 않는다. 정보 표시 전용이다.
"""
import csv
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# 설문 운동시간대 → 대표 시각. 문항 문자열은 설문문항_v1.md 가 정본이다
SLOT_HOUR = {
    "아침/새벽(6-8시)": 7,
    "오전(8-12시)": 10,
    "점심(12-14시)": 13,
    "오후(14-18시)": 16,
    "저녁(18-22시)": 19,
    "일정하지 않음": None,
}


def _load():
    table = {}
    with io.open(os.path.join(DATA, "crowding.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["자치구"], row["요일유형"])
            table.setdefault(key, {})[int(row["시간대"])] = float(row["평균생활인구수"])
    return table


TABLE = _load()


def slot_to_hour(slot):
    return SLOT_HOUR.get(slot)


# 운동을 권할 수 있는 시간대. 새벽 3시가 '가장 여유롭다'고 안내하면 안 된다
ACTIVE_HOURS = tuple(range(5, 23))


def get_crowding(district, daytype="평일", hour=None):
    """반환: 수준 · 문구 · 최고/최저 시간대. 데이터가 없으면 None.

    비교와 추천은 **활동 가능 시간대(5~22시) 안에서만** 한다. 관악구는 주거지라
    새벽 3시가 인구 최대인데, 24시간을 통으로 비교하면 "저녁이 한산하다" 같은
    엉뚱한 결론이 나온다.
    """
    series = TABLE.get((district, daytype))
    if not series:
        return None

    active = {h: v for h, v in series.items() if h in ACTIVE_HOURS}
    values = sorted(active.values())
    peak_hour = max(active, key=active.get)
    low_hour = min(active, key=active.get)

    result = {
        "자치구": district,
        "요일유형": daytype,
        "최고시간": peak_hour,
        "최저시간": low_hour,
        "최고인구": round(active[peak_hour]),
        "최저인구": round(active[low_hour]),
        "시간대": hour,
        "수준": None,
        "문구": _base_phrase(district, daytype, peak_hour, low_hour),
    }

    if hour is None or hour not in active:
        return result

    value = active[hour]
    rank = sum(1 for v in values if v < value) / len(values)
    result["인구"] = round(value)
    if rank >= 0.75:
        result["수준"] = "많은 편"
    elif rank <= 0.25:
        result["수준"] = "적은 편"
    else:
        result["수준"] = "보통"
    result["문구"] = (f"{district}는 {_hour_label(hour)}에 사람이 {result['수준']}이에요. "
                      f"{_hour_label(low_hour)}가 가장 여유롭습니다")
    return result


def _base_phrase(district, daytype, peak_hour, low_hour):
    return (f"{district}는 {daytype} {_hour_label(peak_hour)}에 사람이 가장 많고 "
            f"{_hour_label(low_hour)}가 가장 적습니다")


def _hour_label(hour):
    """'5시'라고만 쓰면 새벽을 권하는 것처럼 읽힌다.
    문장에 '~가'로 이어붙이므로 항상 '시'로 끝맺는다."""
    if hour < 7:
        return f"이른 아침 {hour}시"
    if hour >= 21:
        return f"늦은 저녁 {hour}시"
    return f"{hour}시"


if __name__ == "__main__":
    for gu in ("중구", "관악구"):
        for daytype in ("평일", "주말"):
            info = get_crowding(gu, daytype, hour=19)
            print(f"{gu} {daytype} 19시 → {info['수준']:>4} "
                  f"(최고 {info['최고시간']:>2}시 {info['최고인구']:,} / "
                  f"최저 {info['최저시간']:>2}시 {info['최저인구']:,})")
        print("   ", get_crowding(gu, "평일", 19)["문구"])
