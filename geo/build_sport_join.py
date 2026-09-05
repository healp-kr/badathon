# -*- coding: utf-8 -*-
"""35종목 ↔ geo 시설 분류 매핑표 생성.

    python geo/build_sport_join.py   → geo/data/sport_facility_join.csv

**종목명은 sport_master.csv 에서 그대로 읽는다.** 손으로 적으면 쉼표가 든 이름
("축구, 풋살" · "요가, 필라테스, 태보")에서 반드시 틀린다.

MAPPING 은 판단이 들어간 부분이라 사람이 고치는 곳이다. 생성된 CSV 를 직접 고치지 말고
여기를 고친 뒤 다시 생성할 것 — 그래야 매핑의 출처가 한 곳에 남는다.

대체처리: 시설 검색 결과가 비었을 때 화면이 무엇을 대신 보여줄지 (S4-b)
  시설불필요 — "시설이 필요 없는 운동이에요" + 접근성 정보
  집         — "집에서도 할 수 있어요" + 보완운동 연결
  (빈칸)     — 시설 블록 자체를 숨김
"""
import csv
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(os.path.dirname(HERE), "recommendation", "data", "sport_master.csv")
OUT = os.path.join(HERE, "data", "sport_facility_join.csv")

# 종목 → (세부유형, 업종, 예약세부종목, 대체처리, 확인필요, 비고)
MAPPING = {
    "보디빌딩(헬스)": (
        ["체력단련장"], ["체력단련장업", "종합체육시설업"], [], "", False,
        "중구·관악구 최다 업종(237건). 커버리지 충분"),
    "[무도/격투기] 그 외 종목": (
        ["태권도", "권투", "검도", "합기도", "유도", "레슬링", "무도학원", "무도장"],
        ["체육도장업", "무도학원업", "무도장업"], [], "", False,
        "8개 세부유형 합계 약 120건"),
    "골프": (
        ["골프", "골프연습장", "스크린"], ["골프연습장업", "가상체험 체육시설업"],
        ["골프장"], "", True,
        "'스크린'(54건)은 가상체험 체육시설업. 스크린야구가 섞여 있을 수 있음"),
    "축구, 풋살": (
        ["축구", "축구장"], ["체육교습업"], ["축구장", "풋살장"], "", False, ""),
    "수영+아쿠아로빅, 수중발레+수구": (
        ["수영장"], ["수영장업"], ["수영장"], "", False,
        "시설 14건. 소량이지만 실물이 있다"),
    "암벽등반": (["인공암벽장"], ["인공암벽장업"], [], "", False, "5건"),
    "농구": (["농구", "구기체육관"], [], ["농구장"], "", True,
             "구기체육관(5건)은 다목적일 수 있음"),
    "배구": ([], [], ["배구장"], "", True, "전용 시설 없음. 예약 3건으로 대응"),
    "배드민턴": (["생활체육관", "구기체육관"], [], ["배드민턴장"], "", True, "전용 시설 없음"),
    "탁구": (["생활체육관"], [], ["탁구장"], "", True, "예약 1건뿐"),
    "야구+소프트볼": (["야구"], [], [], "", True, "'스크린'에 스크린야구가 섞였을 가능성"),
    "테니스+정구": (["테니스장"], [], ["테니스장"], "", False,
                    "시설 1건이지만 예약 25건이 본체"),
    "빙상(아이스하키, 스케이팅 포함)": (["빙상장"], ["빙상장업"], [], "", False, "1건"),
    "석궁, 양궁, 국궁": (["국궁장"], [], [], "", False, "1건"),
    "족구": ([], [], ["족구장"], "", False, "예약 1건"),
    "체조(맨손체조, 생활체조)": (["간이운동장"], [], [], "집", False,
                                 "간이운동장 6건 + 집에서 가능"),
    "걷기(속보 포함)": (["간이운동장"], [], [], "시설불필요", False,
                        "보행자 전용 도로가 본체(52%). 시설 검색 대상이 아니다"),
    "달리기(조깅, 마라톤 포함)": (["간이운동장"], [], [], "시설불필요", False, ""),
    "등산": ([], [], [], "", False, "산림 데이터 없음. 시설 블록 숨김"),
    "자전거, 사이클, 산악자전거": ([], [], [], "시설불필요", False, "자전거도로 데이터 없음"),
    "요가, 필라테스, 태보": ([], [], [], "집", False, "체육교습업에 요가 항목 없음"),
    "에어로빅": ([], [], [], "집", False, ""),
    "댄스스포츠": ([], ["무도학원업"], [], "집", True,
                   "무도학원업(9건)이 댄스스포츠일 가능성. 태권도 계열과 섞여 있음"),
    "줄넘기": ([], [], [], "집", False, ""),
    "훌라후프": ([], [], [], "집", False, ""),
    "육상(걷기, 달리기 제외한 종목)": (["간이운동장"], [], ["다목적경기장"], "", True, ""),
    "게이트볼": ([], [], [], "", False, "데이터 없음"),
    "승마": ([], [], [], "", False, "데이터 없음"),
    "인라인스케이트": ([], [], [], "", False, "데이터 없음"),
    "낚시": ([], [], [], "", False, "데이터 없음"),
}

FIELDS = ["종목", "시설_세부유형", "시설_업종", "예약_세부종목",
          "대체처리", "확인필요", "추천가능", "비고"]


def main():
    with io.open(MASTER, encoding="utf-8-sig") as f:
        master = list(csv.DictReader(f))

    rows, unmapped = [], []
    for entry in master:
        sport = entry["종목"]
        spec = MAPPING.get(sport)
        if spec is None:
            unmapped.append(sport)
            spec = ([], [], [], "", False, "추천가능=N 종목 — 매핑 불필요"
                    if entry["추천가능"] == "N" else "미매핑")
        detail, industry, reservation, fallback, check, note = spec
        rows.append({
            "종목": sport,
            "시설_세부유형": "|".join(detail),
            "시설_업종": "|".join(industry),
            "예약_세부종목": "|".join(reservation),
            "대체처리": fallback,
            "확인필요": "Y" if check else "N",
            "추천가능": entry["추천가능"],
            "비고": note,
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    matched = sum(1 for r in rows if r["시설_세부유형"] or r["시설_업종"] or r["예약_세부종목"])
    print(f"{OUT} — {len(rows)}종목")
    print(f"  시설 매칭 있음   {matched}")
    print(f"  대체처리로 넘김  {sum(1 for r in rows if r['대체처리'])}")
    print(f"  확인 필요        {sum(1 for r in rows if r['확인필요'] == 'Y')}")
    if unmapped:
        print("  MAPPING 미정의:", ", ".join(unmapped))


if __name__ == "__main__":
    main()
