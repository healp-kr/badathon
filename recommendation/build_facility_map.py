"""종목 → 필요 시설 유형 매핑 (GIS 연결용 인계 데이터).

장소 검색 자체는 이 모듈의 일이 아니다. 추천 알고리즘은 "이 종목을 하려면 어떤
시설을 찾아야 하는가"까지만 알려주고, 실제 주변 시설 검색은 GIS 데이터 쪽에서 한다.

두 가지를 뽑는다.
  시설대분류 — '주 이용시설'(공공/민간/학교/직장/자가/기타). 참여자 전원이 응답해 신뢰도 높음
  세부시설   — '자주 이용하는 체육시설의 세부시설'(69종). 실제 검색 키워드가 되지만
               공공·민간·기타 시설 이용자만 응답해 종목에 따라 커버리지가 낮다

산출: data/sport_facility_map.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "data"

MIN_N = 30          # 종목 표본 하한
TOP_DETAIL = 3      # 세부시설 상위 몇 개까지
LOW_COVERAGE = 0.6  # 이 아래면 저신뢰로 표시


def main():
    src = (ROOT / "analysis" / "최종 클러스터링 결과" / "lca_refit_local.py").read_text(encoding="utf-8")
    ns = {"__file__": str(ROOT / "analysis" / "최종 클러스터링 결과" / "lca_refit_local.py")}
    exec(compile(src.split("# ===== CELL 4")[0], "prep", "exec"), ns)
    raw, analysis_df = ns["raw"], ns["analysis_df"]

    book = pd.ExcelFile(ROOT / "analysis" / "국민생활체육조사" / "2024년_국민생활체육조사_파일설계서.xlsx")
    codes = book.parse("코드정보", header=1)
    codes.columns = ["코드번호", "항목명", "코드", "의미", "특이사항"]

    detail_codes = _code_map(codes, "세부시설")
    main_codes = _code_map(codes, "주 이용시설")

    ids = np.arange(1, len(raw) + 1)

    # 시설 대분류 — 종목별 분포
    main_col = "주로 참여하는 체육활동 (주 이용시설)_1~3순위_BASE: 규칙적 체육활동 참여자_1"
    main_df = pd.DataFrame({"응답자ID": ids,
                            "대분류": pd.to_numeric(raw[main_col], errors="coerce")}).dropna()
    main_df["대분류"] = main_df["대분류"].astype(int).map(main_codes)

    # 세부시설 — 복수응답 롱포맷
    detail_cols = [c for c in raw.columns if "세부시설" in c]
    parts = []
    for col in detail_cols:
        t = pd.DataFrame({"응답자ID": ids,
                          "세부": pd.to_numeric(raw[col], errors="coerce")}).dropna()
        parts.append(t)
    detail_df = pd.concat(parts, ignore_index=True)
    detail_df["세부"] = detail_df["세부"].astype(int).map(detail_codes)

    base = analysis_df[["응답자ID", "운동종목_1"]].rename(columns={"운동종목_1": "종목"})
    n_by_sport = base.groupby("종목").size()

    rows = []
    for sport, size in n_by_sport.items():
        if size < MIN_N or "그 외 종목" in sport:
            continue
        members = base[base["종목"] == sport]

        m = members.merge(main_df, on="응답자ID")
        main_share = (m["대분류"].value_counts(normalize=True) * 100).round(1)

        d = members.merge(detail_df, on="응답자ID")
        coverage = d["응답자ID"].nunique() / size
        detail_share = (d["세부"].value_counts(normalize=True) * 100).round(1)

        row = {
            "종목": sport,
            "n": int(size),
            "시설대분류_1": _nth(main_share, 0, "name"),
            "시설대분류_1_비율": _nth(main_share, 0, "value"),
            "시설대분류_2": _nth(main_share, 1, "name"),
            "시설대분류_2_비율": _nth(main_share, 1, "value"),
            "시설불필요_비율": float(main_share.get("자가시설", 0.0)),
            "세부시설_응답률": round(coverage * 100, 1),
            "세부시설_신뢰도": "낮음" if coverage < LOW_COVERAGE else "보통",
        }
        for i in range(TOP_DETAIL):
            row[f"세부시설_{i + 1}"] = _nth(detail_share, i, "name")
            row[f"세부시설_{i + 1}_비율"] = _nth(detail_share, i, "value")
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("n", ascending=False)
    out.to_csv(OUT / "sport_facility_map.csv", index=False, encoding="utf-8-sig")

    print(f"저장: {OUT / 'sport_facility_map.csv'}  ({len(out)}종목)")
    print("\n종목별 1순위 검색 대상 시설:")
    for r in out.itertuples():
        flag = " ※저신뢰" if r.세부시설_신뢰도 == "낮음" else ""
        print(f"  {r.종목[:24]:26s} n={r.n:4d}  {str(r.세부시설_1)[:34]:36s}"
              f" {r.세부시설_1_비율}%{flag}")


def _code_map(codes, keyword):
    sub = codes[codes["항목명"].astype(str).str.contains(keyword, na=False)]
    first = sub[sub["항목명"] == sub["항목명"].iloc[0]]
    return {int(r.코드): r.의미 for r in first.itertuples()}


def _nth(series, i, what):
    if len(series) <= i:
        return None
    return series.index[i] if what == "name" else float(series.iloc[i])


if __name__ == "__main__":
    main()
