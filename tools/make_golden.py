# -*- coding: utf-8 -*-
"""골든 파일 생성기 — TypeScript 포팅의 정답지.

정적화(브라우저에서 전부 계산)로 옮기면서 제일 위험한 것은 **조용한 불일치**다.
화면은 멀쩡히 뜨는데 배정 결과가 미묘하게 달라지는 경우, 눈으로는 못 잡는다.
`test_assign.py` 가 지키던 "원본 6,602명 100% 재현" 도 그때 함께 무너진다.

그래서 포팅 **전에** 파이썬 엔진의 입출력을 얼려 둔다. TS 포팅은 이 파일을
한 글자도 틀리지 않게 재현해야 한다.

    python tools/make_golden.py            # → web/ui/tests/golden/*.json

케이스는 무작위가 아니라 **경계를 노려서** 만든다. 라우팅 경계 세 개(선호 60 ·
체력 65 · 표시 60)가 서로 다르고, 결측 조합이 배정을 건너뛰게 하므로 그쪽을 두껍게 깐다.

휘발성 필드(request_id · 생성시각)는 제외한다. `model_version` 은 파라미터 파일의
해시라 TS 가 같은 값을 만들 수 없으므로 여기서 빼고, 대신 메타에 한 번만 적어
"어느 파라미터로 만든 정답지인가" 를 남긴다.
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from serve import serve, model_fingerprint, RequestError  # noqa: E402
from web.schema import build_schema, sport_catalog       # noqa: E402

OUT_DIR = os.path.join(ROOT, "web", "ui", "tests", "golden")

# 휘발성 — 호출할 때마다 달라진다. 비교 대상이 아니다.
VOLATILE = ("request_id", "생성시각", "model_version")


def _sports():
    return [row["종목"] for row in sport_catalog()]


def _levels(*values):
    """체력 자가평가 5축. 축 이름은 나이대에 따라 갈리므로 둘 다 만들어 둔다."""
    adult = ["근력", "유연성", "근지구력", "순발력"]
    elderly = ["근력", "유연성", "하지근기능", "협응력평형"]
    out = {}
    for axes in (adult, elderly):
        for i, axis in enumerate(axes):
            out[axis] = values[i % len(values)]
    return out


def cases():
    """입력 케이스. 경계와 결측을 노린다."""
    sports = _sports()
    s0, s1, s2 = sports[0], sports[1], sports[2]

    base = {
        "운동요일": "평일", "운동빈도": "일주일에 3번",
        "운동시간대": "저녁(18-22시)", "운동목적": "건강 유지 및 체력증진",
        "운동강도": "중", "체력인지": "보통이다",
    }

    out = []

    # 1) 라우팅 경계 — 선호 60 / 체력 65 / 표시 60 이 서로 다르다
    for age in (18, 19, 24, 25, 59, 60, 61, 64, 65, 66, 74, 75, 119):
        for sex in ("남", "여"):
            for regular in (True, False):
                out.append({
                    "이름": f"라우팅 age={age} {sex} 참여={regular}",
                    "payload": {
                        "나이": age, "성별": sex, "규칙적참여": regular,
                        **base,
                        "관심운동": [s0], "자주해온운동": [s1],
                        "체력자가평가": _levels(3, 3, 3, 3),
                        "키": 170, "몸무게": 65,
                    },
                })

    # 2) 결측 조합 — 어느 항목이 빠지면 어느 배정이 건너뛰는가
    missing_sets = [
        ("최소", ["운동요일", "운동빈도", "운동시간대", "운동목적", "운동강도",
                  "체력인지", "관심운동", "자주해온운동", "체력자가평가",
                  "키", "몸무게", "불편부위"]),
        ("패턴없음", ["운동요일", "운동빈도", "운동시간대", "운동목적",
                      "운동강도", "체력인지"]),
        ("체력평가없음", ["체력자가평가"]),
        ("신체정보없음", ["키", "몸무게"]),
        ("키만없음", ["키"]),
        ("종목없음", ["관심운동", "자주해온운동"]),
        ("관심만", ["자주해온운동"]),
        ("자주만", ["관심운동"]),
        ("전부있음", []),
    ]
    full = {
        "나이": 34, "성별": "남", "규칙적참여": True, **base,
        "관심운동": [s0, s1], "자주해온운동": [s1, s2],
        "체력자가평가": _levels(4, 2, 3, 2),
        "키": 175, "몸무게": 72, "불편부위": ["무릎"],
    }
    for name, drop in missing_sets:
        payload = {k: v for k, v in full.items() if k not in drop}
        out.append({"이름": f"결측 {name}", "payload": payload})
        # 노인 경로에서도 같은 결측을 본다
        elderly = dict(payload)
        elderly["나이"] = 70
        out.append({"이름": f"결측 {name} (노인)", "payload": elderly})

    # 3) 자가평가 응답 전 구간 — 분위 매핑과 최근접 중심이 갈리는 지점
    for level in (1, 2, 3, 4, 5):
        for age, label in ((34, "성인"), (70, "노인")):
            out.append({
                "이름": f"자가평가 전축={level} ({label})",
                "payload": {
                    "나이": age, "성별": "여", "규칙적참여": True, **base,
                    "관심운동": [s0], "자주해온운동": [s1],
                    "체력자가평가": _levels(level, level, level, level),
                    "키": 160, "몸무게": 55,
                },
            })
    # 축이 서로 엇갈리는 경우 — 중심 간 거리가 가까워져 ambiguous 가 뜬다
    for combo in ((1, 5, 1, 5), (5, 1, 5, 1), (1, 1, 5, 5), (2, 4, 3, 1)):
        out.append({
            "이름": f"자가평가 엇갈림 {combo}",
            "payload": {
                "나이": 45, "성별": "남", "규칙적참여": True, **base,
                "관심운동": [s0], "자주해온운동": [s1],
                "체력자가평가": _levels(*combo), "키": 178, "몸무게": 90,
            },
        })

    # 4) 체형 — 신체조성 회귀가 나이대별 모델을 타는지
    for height, weight in ((150, 40), (160, 55), (175, 72), (185, 110), (200, 60)):
        for age in (22, 34, 52, 68, 80):
            out.append({
                "이름": f"체형 {height}/{weight} age={age}",
                "payload": {
                    "나이": age, "성별": "남", "규칙적참여": True, **base,
                    "관심운동": [s0], "자주해온운동": [s1],
                    "체력자가평가": _levels(3, 3, 3, 3),
                    "키": height, "몸무게": weight,
                },
            })

    # 5) 안전 필터 — 불편 부위별 제외·강등
    areas = ["무릎", "허리", "어깨", "발목", "손목"]
    for area in areas:
        out.append({
            "이름": f"불편부위 {area}",
            "payload": {
                "나이": 55, "성별": "여", "규칙적참여": True, **base,
                "관심운동": sports[:6], "자주해온운동": sports[6:10],
                "체력자가평가": _levels(3, 3, 3, 3),
                "키": 162, "몸무게": 60, "불편부위": [area],
            },
        })
    out.append({
        "이름": "불편부위 전부",
        "payload": {
            "나이": 72, "성별": "남", "규칙적참여": True, **base,
            "관심운동": sports[:8], "자주해온운동": sports[8:12],
            "체력자가평가": _levels(2, 2, 2, 2),
            "키": 168, "몸무게": 70, "불편부위": areas,
        },
    })

    # 6) 선호 문항 전 범주 — LCA posterior 가 문항마다 제대로 곱해지는지
    schema = build_schema()
    for step in schema["steps"]:
        for question in step["questions"]:
            if question["id"] not in base:
                continue
            for option in question["options"]:
                payload = {
                    "나이": 40, "성별": "남", "규칙적참여": True, **base,
                    "관심운동": [s0], "자주해온운동": [s1],
                    "체력자가평가": _levels(3, 3, 3, 3),
                    "키": 172, "몸무게": 68,
                }
                payload[question["id"]] = option["value"]
                out.append({
                    "이름": f"선호범주 {question['id']}={option['value']}",
                    "payload": payload,
                })

    # 7) 종목 선택 — 전 종목을 한 번씩 관심운동으로
    for sport in sports:
        out.append({
            "이름": f"관심종목 {sport}",
            "payload": {
                "나이": 30, "성별": "여", "규칙적참여": True, **base,
                "관심운동": [sport], "자주해온운동": [],
                "체력자가평가": _levels(3, 3, 3, 3),
                "키": 165, "몸무게": 58,
            },
        })

    # 8) 모델에 없는 값 — 조용히 무시되는 경로가 유지되는지
    out.append({
        "이름": "알 수 없는 범주·종목",
        "payload": {
            "나이": 34, "성별": "남", "규칙적참여": True, **base,
            "운동목적": "없는목적", "관심운동": ["수영"], "자주해온운동": ["없는종목"],
            "체력자가평가": _levels(3, 3, 3, 3), "키": 175, "몸무게": 72,
        },
    })

    # 9) top_n 변주 — 표현 계층이 넉넉히 받아 재정렬하는 경로
    for top_n in (3, 6, 10):
        out.append({
            "이름": f"top_n={top_n}",
            "top_n": top_n,
            "payload": {
                "나이": 34, "성별": "남", "규칙적참여": True, **base,
                "관심운동": [s0, s1], "자주해온운동": [s2],
                "체력자가평가": _levels(3, 3, 3, 3), "키": 175, "몸무게": 72,
            },
        })

    # 10) 거절되어야 하는 입력 — 오류 메시지까지 같아야 한다
    for name, payload in [
        ("빈 payload", {}),
        ("나이 없음", {"성별": "남"}),
        ("성별 없음", {"나이": 30}),
        ("성별 오타", {"나이": 30, "성별": "M"}),
        ("나이 0", {"나이": 0, "성별": "남"}),
        ("나이 120", {"나이": 120, "성별": "남"}),
        ("키 음수", {"나이": 30, "성별": "남", "키": -1}),
        ("몸무게 0", {"나이": 30, "성별": "남", "몸무게": 0}),
        ("자가평가 범위 밖", {"나이": 30, "성별": "남", "체력자가평가": {"근력": 6}}),
        ("자가평가 실수", {"나이": 30, "성별": "남", "체력자가평가": {"근력": 3.5}}),
        ("관심운동 문자열", {"나이": 30, "성별": "남", "관심운동": "축구"}),
    ]:
        out.append({"이름": f"거절 {name}", "payload": payload, "거절기대": True})

    return out


def round_cases():
    """반올림 정답지 — 파이썬 `round()` 는 은행가 반올림이라 JS 와 갈린다.

    경계(정확한 타이)와 '타이처럼 보이지만 아닌 값', 그리고 엔진이 실제로 다루는
    범위의 난수를 섞는다. 시드를 고정해 매번 같은 케이스가 나오게 한다.
    """
    import random
    random.seed(0)
    pairs = []

    # 정확한 타이 — x 가 1/2**(n+1) 의 홀수 배일 때만 생긴다
    for n in range(0, 4):
        for j in range(-41, 42, 2):
            pairs.append((j / 2 ** (n + 1), n))

    # .x5 처럼 보이지만 이진수로는 타이가 아닌 값
    for n in (0, 1, 2, 3):
        for base in (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.85,
                     0.95, 1.05, 2.675, 1.005):
            pairs.append((base, n))
            pairs.append((-base, n))

    # 엔진이 실제로 다루는 범위 (점수 0~100 · z -3~3)
    for _ in range(4000):
        pairs.append((random.uniform(-120, 120), random.choice([0, 1, 2, 3])))

    return [{"x": x, "n": n, "want": round(x, n)} for x, n in pairs]


def strip(result):
    return {k: v for k, v in result.items() if k not in VOLATILE}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    records, rejected, failed = [], 0, 0

    for case in cases():
        entry = {"이름": case["이름"], "payload": case["payload"]}
        if case.get("top_n") is not None:
            entry["top_n"] = case["top_n"]
        try:
            result = serve(case["payload"], top_n=case.get("top_n"))
        except RequestError as exc:
            entry["거절"] = str(exc)
            rejected += 1
        else:
            if case.get("거절기대"):
                print(f"  [경고] 거절될 줄 알았는데 통과: {case['이름']}")
                failed += 1
            entry["결과"] = strip(result)
        records.append(entry)

    payload = {
        "note": "TypeScript 포팅의 정답지. tools/make_golden.py 가 만든다. 손으로 고치지 말 것.",
        "model_version": model_fingerprint(),
        "제외필드": list(VOLATILE),
        "케이스수": len(records),
        "거절수": rejected,
        "cases": records,
    }
    path = os.path.join(OUT_DIR, "serve.json")
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    rounds = round_cases()
    rpath = os.path.join(OUT_DIR, "round.json")
    with io.open(rpath, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rounds, f, ensure_ascii=False)
        f.write("\n")

    size = os.path.getsize(path) / 1024
    print(f"반올림 케이스 {len(rounds)}건 → {os.path.relpath(rpath, ROOT)}")
    print(f"케이스 {len(records)}건 (통과 {len(records) - rejected} · 거절 {rejected})")
    print(f"model_version {payload['model_version']}")
    print(f"→ {os.path.relpath(path, ROOT)}  ({size:.0f}KB)")
    if failed:
        print(f"\n거절 기대가 어긋난 케이스 {failed}건 — 확인 필요")
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
