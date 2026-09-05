# -*- coding: utf-8 -*-
"""온보딩 설문 스키마 — 모델 파라미터에서 생성한다.

선택지의 `value` 는 **반드시** `preference_model.json` 의 범주 레벨과 글자 단위로 같아야
한다. 한 글자만 달라도 그 문항은 **에러 없이 무시되고** 배정 확률만 떨어진다.

그래서 이 모듈은 두 가지를 한다.
  1. `value` 를 파라미터 파일에서 그대로 읽어 온다 (손으로 적지 않는다)
  2. import 시점에 전 문항을 대조하고, 어긋나면 **즉시 예외를 던진다**

화면에 보이는 문구(`label`)는 사람이 읽기 좋은 쪽을 따로 둔다. 예를 들어 모델 범주는
"평일/휴일" 이지만 화면에는 "평일·휴일 모두" 로 보여준다 — UI 문구와 모델 범주를
분리해 두면 둘 다 자유로워진다.
"""
import csv
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS = os.path.join(ROOT, "assignment", "params", "preference_model.json")
MASTER = os.path.join(ROOT, "recommendation", "data", "sport_master.csv")

with io.open(PARAMS, encoding="utf-8") as f:
    _MODEL = json.load(f)

# 세그먼트마다 같은 범주 집합을 쓰므로 아무 세그먼트에서나 읽으면 된다
_INDICATORS = next(iter(_MODEL["segments"].values()))["indicators"]


def levels(indicator):
    return list(_INDICATORS[indicator]["levels"])


# 화면 문구. 키는 모델 범주(value), 값은 사람이 읽는 문구(label).
# 여기 없는 범주는 value 를 그대로 label 로 쓴다.
LABEL_OVERRIDE = {
    "운동요일_1": {"평일/휴일": "평일·휴일 모두", "휴일": "휴일 (주말·공휴일)"},
    "운동시간대_1": {"아침/새벽(6-8시)": "아침·새벽 (6-8시)"},
    "운동강도_1": {"저": "저 — 숨이 차지 않고 편안한 정도",
                   "중": "중 — 약간 숨이 차고 땀이 나는 정도",
                   "고": "고 — 숨이 많이 차고 힘든 정도"},
    "체력인지": {"전혀 체력이 좋지 않은 편이다": "전혀 좋지 않은 편이다",
                 "별로 체력이 좋지 않은 편이다": "별로 좋지 않은 편이다",
                 "보통이다": "보통이다",
                 "체력이 좋은 편이다": "좋은 편이다",
                 "매우 체력이 좋은 편이다": "매우 좋은 편이다"},
}

# 표시 순서. 파라미터 파일은 가나다순이라 그대로 쓰면 척도가 뒤섞인다
ORDER = {
    "운동빈도_1": ["한 달에 3번 이하", "일주일에 1번", "일주일에 2번", "일주일에 3번",
                   "일주일에 4번", "일주일에 5번", "일주일에 6번", "일주일에 7번(매일)"],
    "운동시간대_1": ["아침/새벽(6-8시)", "오전(8-12시)", "점심(12-14시)", "오후(14-18시)",
                     "저녁(18-22시)", "일정하지 않음"],
    "운동강도_1": ["저", "중", "고"],
    "체력인지": ["전혀 체력이 좋지 않은 편이다", "별로 체력이 좋지 않은 편이다", "보통이다",
                 "체력이 좋은 편이다", "매우 체력이 좋은 편이다"],
}

SELF_RATING = ["매우 낮은 편", "낮은 편", "보통", "높은 편", "매우 높은 편"]


def _options(indicator):
    available = set(levels(indicator))
    ordered = [v for v in ORDER.get(indicator, sorted(available)) if v in available]
    ordered += [v for v in sorted(available) if v not in ordered]
    override = LABEL_OVERRIDE.get(indicator, {})
    return [{"value": v, "label": override.get(v, v)} for v in ordered]


# 근력 운동 판정 (O13). `sport_master.csv` 35종목 중 지침이 말하는 "근력운동"
# (저항·웨이트 트레이닝)에 모호함 없이 해당하는 것은 이 하나뿐이다.
# 넓히려면 종목별 확인이 먼저다 — 지금 늘리지 않는다.
STRENGTH_SPORTS = {"보디빌딩(헬스)"}


def _master_rows():
    with io.open(MASTER, encoding="utf-8-sig") as f:
        return [row for row in csv.DictReader(f) if row["추천가능"] == "Y"]


def _sports():
    """Q11·Q12 선택지. 추천 대상이 아닌 '[...] 그 외 종목' 묶음은 뺀다."""
    return [row["종목"] for row in _master_rows()]


def sport_catalog():
    """종목 목록 + 기본 강도. 기록 화면(S5-b 직접입력)이 쓴다.

    강도를 프론트에 하드코딩하면 `sport_master.csv` 와 조용히 어긋난다 —
    달성률 계산의 근거가 되는 값이므로 여기서만 나가야 한다.
    """
    return [{"종목": row["종목"],
             "강도": row["강도"],
             "실내외": row["실내외"] or None,
             "근력": row["종목"] in STRENGTH_SPORTS}
            for row in _master_rows()]


def build_schema():
    return {
        "version": _MODEL.get("note", ""),
        "note": "value 를 그대로 serve() 에 보낼 것. label 은 화면 표시용이다",
        "steps": [
            {"id": "screening", "title": "시작하기", "questions": [
                {"id": "규칙적참여", "type": "bool", "required": True,
                 "text": "최근 1년간 규칙적으로 운동하고 계신가요?",
                 "help": "주 1회 이상 또는 꾸준히 반복하는 운동이 하나라도 있으면 '예'",
                 "skip_to_if_false": "sports"},
                {"id": "나이", "type": "number", "required": True, "text": "나이 (만)",
                 "min": 1, "max": 120},
                {"id": "성별", "type": "choice", "required": True, "text": "성별",
                 "options": [{"value": "남", "label": "남"}, {"value": "여", "label": "여"}]},
            ]},
            # 여섯 문항이 통째로 선호유형 배정의 입력이다. 하나라도 비면 배정이 안 되고
            # '비슷한 분들의 선택' 칸이 빈다 — 그래서 전부 required 다.
            {"id": "pattern", "title": "운동 패턴", "questions": [
                {"id": "운동요일", "type": "choice", "required": True,
                 "text": "주로 언제 운동하시나요?",
                 "options": _options("운동요일_1")},
                {"id": "운동빈도", "type": "choice", "required": True,
                 "text": "얼마나 자주 하시나요?",
                 "options": _options("운동빈도_1")},
                {"id": "운동시간대", "type": "choice", "required": True,
                 "text": "주로 몇 시에 하시나요?",
                 "options": _options("운동시간대_1")},
                {"id": "운동목적", "type": "choice", "required": True,
                 "text": "운동하는 주된 이유는 무엇인가요?",
                 "options": _options("운동목적_1")},
                {"id": "운동강도", "type": "choice", "required": True,
                 "text": "운동 강도는 어느 정도인가요?",
                 "options": _options("운동강도_1")},
                {"id": "체력인지", "type": "choice", "required": True,
                 "text": "본인의 체력 상태를 어떻게 생각하시나요?",
                 "options": _options("체력인지")},
            ]},
            # 관심운동은 '이미 하고 계신 운동' 칸의 유일한 입력이다. 비면 두 갈래 중
            # 하나가 통째로 사라지므로 필수로 받는다. 자주해온운동은 가중치만 올리므로 선택.
            {"id": "sports", "title": "관심 운동", "questions": [
                {"id": "관심운동", "type": "multi", "required": True,
                 "text": "관심 있는 운동을 골라주세요",
                 "help": "하나 이상 골라주세요. 해보고 싶은 것도 괜찮습니다",
                 "options": [{"value": s, "label": s} for s in _sports()]},
                {"id": "자주해온운동", "type": "multi", "text": "그동안 자주 해온 운동을 골라주세요",
                 "options": [{"value": s, "label": s} for s in _sports()]},
            ]},
            {"id": "fitness", "title": "체력 자가평가",
             "note": "모두 '같은 나이·성별의 또래와 비교해서' 답한다. "
                     "절대평가로 받으면 분위 매핑이 성립하지 않는다",
             "questions": _fitness_questions()},
            {"id": "body", "title": "마지막", "questions": [
                {"id": "키", "type": "number", "text": "키(cm)", "min": 100, "max": 220},
                {"id": "몸무게", "type": "number", "text": "몸무게(kg)", "min": 25, "max": 200},
                {"id": "불편부위", "type": "multi", "text": "불편한 부위가 있으신가요?",
                 "options": [{"value": a, "label": a}
                             for a in ("무릎", "허리", "어깨", "발목", "손목")]},
            ]},
        ],
    }


def _fitness_questions():
    """65세 기준으로 문항 세트가 갈린다. 선호축(60세)과 경계가 다르다 — 의도된 설계."""
    scale = [{"value": i + 1, "label": text} for i, text in enumerate(SELF_RATING)]
    common = [
        {"id": "근력", "text": "무거운 물건을 들거나 힘을 쓸 때, 또래와 비교해 힘이 센 편인가요?"},
        {"id": "유연성", "text": "앉아서 상체를 앞으로 굽힐 때, 또래보다 유연한 편인가요?"},
    ]
    adult = [
        {"id": "근지구력", "text": "같은 동작을 반복할 때, 또래보다 오래 지속할 수 있나요?"},
        {"id": "순발력", "text": "제자리에서 멀리 뛰거나 순간적으로 튀어나갈 때, 또래보다 잘하는 편인가요?"},
    ]
    elderly = [
        {"id": "하지근기능", "text": "의자에 앉았다 일어서기를 반복할 때, 또래보다 수월한 편인가요?"},
        {"id": "협응력평형", "text": "걷다가 방향을 바꾸거나 한 발로 설 때, 또래보다 균형을 잘 잡나요?"},
    ]
    def block(items, age_from, age_to):
        return [{**q, "type": "scale", "required": True, "options": scale,
                 "age_from": age_from, "age_to": age_to} for q in items]
    return (block(common, 19, None) + block(adult, 19, 64) + block(elderly, 65, None))


# ------------------------------------------------------------------
# 가드레일 — 어긋나면 서버가 뜨지 않는다
# ------------------------------------------------------------------
INDICATOR_OF = {"운동빈도": "운동빈도_1", "운동요일": "운동요일_1", "운동시간대": "운동시간대_1",
                "운동목적": "운동목적_1", "운동강도": "운동강도_1", "체력인지": "체력인지"}


def validate():
    problems = []
    schema = build_schema()
    for step in schema["steps"]:
        for question in step["questions"]:
            indicator = INDICATOR_OF.get(question["id"])
            if not indicator:
                continue
            allowed = set(levels(indicator))
            sent = {o["value"] for o in question["options"]}
            if sent - allowed:
                problems.append(f"{question['id']}: 모델에 없는 값 {sorted(sent - allowed)}")
            if allowed - sent:
                problems.append(f"{question['id']}: 빠진 범주 {sorted(allowed - sent)}")
    if problems:
        raise RuntimeError("설문 선택지가 모델 범주와 어긋납니다:\n  " + "\n  ".join(problems))
    return True


validate()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    schema = build_schema()
    for step in schema["steps"]:
        print(f"[{step['id']}] {step['title']}")
        for question in step["questions"]:
            options = question.get("options") or []
            preview = ", ".join(str(o["label"]) for o in options[:4])
            more = f" …({len(options)}개)" if len(options) > 4 else ""
            print(f"   {question['id']:12} {question['type']:7} {preview}{more}")
    print("\n검증 통과 — 선택지 value 가 모델 범주와 일치합니다")
