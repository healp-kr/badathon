# 바다톤 — 운동 추천 앱 세그멘테이션

국민생활체육조사(선호축) + 국민체력측정통계(체력축)로 사용자를 분류하고 운동을 추천한다.

**처음 보신다면 [docs/발표_진행상황.md](docs/발표_진행상황.md) 부터.** 전체 진행 상황이 정리돼 있다.
**직접 만져보시려면 `cd web/ui && npm run dev`.**

> **2026-09-05 — 정적 앱이 되었다.** 백엔드(FastAPI)를 걷어내고 배정·추천·지도·시설
> 계산 전부를 브라우저 안으로 옮겼다. 학습이 없어 계산만 하면 되는 구조였기에 가능했다.
> 서버가 없으므로 **설문 답변이 기기를 벗어나지 않고**, GitHub Pages 에 무료로 영구히
> 올라간다. 파이썬 엔진은 그대로 남아 **정답지 역할**을 한다 —
> `web/ui/tests/golden/` 이 그것이고, TS 포팅이 4,768건 전부를 재현하지 못하면 배포가 막힌다.

---

## 폴더

```
├─ serve.py              단일 진입점. 앱·GIS 는 이 함수 하나만 알면 된다
├─ logging_schema.py     로그 11종 이벤트
├─ test_serve.py         진입점 테스트 32항목
│
├─ assignment/           배정 층 — 설문 → 선호 유형 1개 + 체력 유형 1개
│   ├─ params/           모델 파라미터 JSON 2종 ← 실제로 쓰이는 것
│   ├─ assign.py         배정 함수 (학습 없음, 계산만)
│   ├─ build_params.py   클러스터링 결과 → params 재생성
│   └─ test_assign.py    배정 테스트 33항목 (원본 6,602명 재현)
│
├─ recommendation/       추천 층 — 유형 → 종목·강도·보완 운동
│   ├─ data/             종목 마스터·선호 행렬·규칙·시설 매핑 ← 실제로 쓰이는 것
│   ├─ recommend.py      추천 함수
│   ├─ build_*.py        data/ 재생성 스크립트
│   ├─ demo.py           사람이 읽는 추천 예시 4종
│   └─ review_48cells.py 48셀 검수표 생성 → docs/48셀_검수.md
│
├─ api/                  위치·환경 컨텍스트 층 (2026-08-13 신규)
│   ├─ districts.json    지원 지역 정의 — **지역 정보의 유일한 출처**
│   ├─ locate.py         좌표 → 자치구 (경계 폴리곤 point-in-polygon)
│   ├─ weather_api_v17.py 기상청 초단기예보·자외선·통합대기환경지수
│   └─ context.py        셋을 합성 + 10분 캐시 + **날씨 재정렬(표현 계층)**
│
├─ geo/                  공간 데이터 층 (2026-08-13 신규)
│   ├─ *.csv, *.geojson  원본 패키지 (체육시설 776·예약 57·경계·생활인구)
│   ├─ data/             런타임 인덱스 ← 실제로 쓰이는 것
│   ├─ build_*.py        data/ 재생성 스크립트
│   ├─ facility.py       종목 → 주변 시설·예약·접근성
│   ├─ mapdata.py        지도용 핀 묶음 (facility.py 결과를 지도 모양으로)
│   └─ crowding.py       시간대 혼잡도
│
├─ web/                  백엔드 + 프론트 (FastAPI, 2026-08-13 신규)
│   ├─ main.py           엔드포인트 11종. **serve() 를 임포트하는 유일한 곳**
│   │                    + ui/dist 를 루트에 마운트 (빌드본으로 띄울 때)
│   ├─ schema.py         설문 스키마 생성 + **모델 범주 대조(어긋나면 서버가 안 뜬다)**
│   ├─ sink.py           로그 JSONL 싱크 → logs/
│   └─ ui/               모바일 웹 화면 — React + TypeScript + Vite (2026-09-04 개편)
│       ├─ src/api/      엔드포인트 래퍼와 응답 타입. 백엔드 계약이 사는 곳
│       ├─ src/state/    AppContext — 전역 상태를 액션 하나로 모은다
│       ├─ src/features/ 화면 없이 검증되는 순수 규칙 (설문 진행·검증, 지도 훅)
│       ├─ src/screens/  S1 온보딩 · S2 결과 · S4 지도 · S5 기록
│       ├─ src/components/ 공용 조각 (히어로·종목 행·바텀시트·탭바)
│       ├─ src/engine/  **파이썬 엔진의 TypeScript 포팅** — 브라우저가 직접 계산한다
│       ├─ tests/golden/ 파이썬이 만든 정답지. 손으로 고치지 말 것
│       ├─ public/context/ Actions 가 굽는 날씨. 없으면 배지만 안 뜬다
│       └─ dist/         `npm run build` 결과. Leaflet 도 번들에 들어간다 (CDN 아님)
│
├─ tools/                빌드 도구 (2026-09-05 정적화)
│   ├─ make_engine_data.py  CSV·파라미터 → web/ui/src/engine/data/*.json
│   ├─ make_golden.py       배정·추천의 정답지 194건 → tests/golden/serve.json
│   ├─ make_golden_geo.py   지도·시설·혼잡도의 정답지 → tests/golden/geo.json
│   └─ fetch_context.py     날씨·대기·자외선 → public/context/*.json (Actions 가 매시간)
│
├─ .github/workflows/    빌드·검증·배포 + 날씨 갱신 (한 파일)
├─ demo_layers.py        **화면 없이 전체 흐름 확인** (위치→날씨→추천→시설→혼잡도)
├─ prototype/            팀 공유용 웹 폼 (디자인·시설검색 없음)
├─ docs/                 문서 전부
├─ analysis/             클러스터링 단계 (2026-08-07 종료·확정)
└─ archive/              내려받은 원본 zip
```

**런타임에 필요한 것은 `assignment/params/` 와 `recommendation/data/` 뿐이다.**
`analysis/` 와 `archive/` 는 파라미터를 다시 만들 때만 쓴다. 학습이 없으므로 모델 서버도,
원자료도 서비스에는 필요 없다.

## 문서

| 파일 | 내용 |
|---|---|
| [발표_진행상황.md](docs/발표_진행상황.md) | **전체 진행 상황.** 팀 공유용 |
| [인터페이스_명세.md](docs/인터페이스_명세.md) | **앱·GIS 가 볼 문서.** 입출력 계약·라우팅·로그·한계 |
| [분류알고리즘_사양.md](docs/분류알고리즘_사양.md) | 정답 라벨, 입력 변수, 스코어링 경로 |
| [설문문항_v1.md](docs/설문문항_v1.md) | 온보딩 문항 (C1 — 확정 대기) |
| [근거자료_운동처방.md](docs/근거자료_운동처방.md) | 추천 규칙의 공개 지침 출처 |
| [구현_워크로드.md](docs/구현_워크로드.md) | 작업 분해와 진행 상태 |
| [48셀_검수.md](docs/48셀_검수.md) | 선호 12 × 체력 4 전수 점검표 (B7 — 검수 대기) |

## 실행

**터미널 하나면 된다.** 백엔드가 없다.

```
cd web/ui && npm run dev          # http://localhost:5173
```

빌드본은 정적 파일이라 아무 웹서버에나 올리면 된다 (파일로 열어도 뜬다).

```
cd web/ui && npm run build        # → web/ui/dist/  (상대 경로라 어느 하위 경로든 동작)
```

**엔진이 파이썬과 같은 답을 내는지**는 이걸로 확인한다. 배포 전에 CI 가 같은 걸 돌린다.

```
cd web/ui && node tests/run.mjs   # 골든 4,768건 — 반올림·배정·추천·좌표·혼잡도·시설·지도
cd web/ui && npm run typecheck
```

파이썬 쪽은 이제 **빌드 도구이자 정답지**다. 서비스에는 쓰이지 않는다.

```
python tools/make_engine_data.py # CSV·파라미터 → 엔진 JSON (+ 모델 범주 대조)
python tools/make_golden.py      # 정답지 재생성 — 규칙·파라미터를 고쳤을 때만
python tools/make_golden_geo.py
python tools/fetch_context.py    # 날씨 갱신 (.env 인증키 필요)
python web/schema.py             # 설문 문항·선택지 확인 + 모델 범주 대조
python demo_layers.py            # 전체 흐름 4개 시나리오 (실시간 API 호출)
python prototype/app.py          # 프로토타입 (http://localhost:8000)
python assignment/test_assign.py # 배정 33항목 — 원본 6,602명 100% 재현
python test_serve.py             # 진입점 32항목
python recommendation/demo.py    # 추천 예시 4종
python api/locate.py             # 좌표 판정 확인 (부산 중구가 '지원 밖'으로 나와야 정상)
python geo/facility.py           # 종목별 시설 커버리지
python geo/mapdata.py            # 지도 핀 묶음 확인
```

바닐라 시절의 `_selftest.html` 은 화면과 함께 없어졌다 — 그 페이지가 검사하던 화면 전환·
정리(teardown) 버그는 언마운트가 맡으므로 구조적으로 사라졌다.

`tools/fetch_context.py` 는 `api/.env` 의 공공데이터포털 인증키가 필요하다. 없거나 실패하면
**환경 배지가 뜨지 않을 뿐, 추천·지도·기록은 정상 동작한다.**

파이썬은 전부 **프로젝트 루트에서** 실행한다 (`pip install -r requirements.txt`).
`web/main.py` 의 FastAPI 백엔드는 남아 있지만 화면이 더는 쓰지 않는다 —
서버로 되돌리고 싶으면 `web/ui/src/api/endpoints.ts` 만 다시 `fetch` 로 바꾸면 된다.

## 배포 — GitHub Pages

`.github/workflows/pages.yml` 하나가 전부 한다. main 에 올리면 배포되고, 매시 15분에
날씨를 새로 받아 커밋한 뒤 다시 배포한다.

배포 전에 **골든 검증이 통과해야 한다.** 파라미터나 규칙을 고쳤다면 `tools/make_golden*.py`
로 정답지를 다시 만들어 함께 커밋할 것 — CI 는 정답지를 만들지 않고 비교만 한다.

저장소 설정에서 두 가지가 필요하다.

| 위치 | 값 |
|---|---|
| Settings → Pages → Source | **GitHub Actions** |
| Settings → Secrets → Actions | `KMA_SERVICE_KEY_DECODED` · `KMA_SERVICE_KEY_ENCODED` |

인증키를 안 넣어도 배포는 된다. 환경 배지만 안 뜬다.

## 파라미터를 다시 만들 때

```
python assignment/build_params.py          # → assignment/params/*.json
python recommendation/build_matrix.py      # → recommendation/data/preference_sport_matrix.csv
python recommendation/build_facility_map.py
python recommendation/review_48cells.py    # → docs/48셀_검수.md
```

`analysis/최종 클러스터링 결과/` 를 읽는다. 파라미터가 바뀌면 `serve()` 가 내보내는
`model_version` 해시가 자동으로 바뀌므로, 어느 버전이 낸 결과인지 로그에서 되짚을 수 있다.
