/* 서버 응답 계약 — 실제 `/api/serve` 응답에서 뽑았다(추측 아님).
 *
 * 이 파일이 프론트에서 유일하게 "서버가 무엇을 주는가"를 아는 곳이다.
 * 기존 바닐라 버전에서는 이 구조가 코드 어디에도 적혀 있지 않아서,
 * 화면을 고칠 때마다 `serve.py` 와 `recommend.py` 를 되짚어야 했다.
 *
 * 백엔드가 바뀌면 여기부터 고친다. 그러면 타입 검사가 고칠 화면을 전부 짚어준다.
 * 근거 문서: docs/인터페이스_명세.md
 */

/* ---------------- 공통 스칼라 ---------------- */

/** sport_master.csv 의 대표 강도. 기록 화면의 달성률 가중치(중 1, 고 2)가 이 값을 신뢰한다. */
export type 강도 = '저' | '중' | '고' | '미확인';

export type 실내외 = '실내' | '실외' | '혼합';

export type 고령적합 = '적합' | '주의' | '부적합';

/** 시설 매핑의 표본 신뢰도. '없음' 이면 시설 검색 조건 자체가 비어 있다. */
export type 신뢰도 = '높음' | '보통' | '낮음' | '없음';

/** 추천 갈래 — 화면의 세 구획과 1:1 로 대응한다. */
export type 갈래 = '기반활동' | '익숙한운동' | '새로운운동';

/* ---------------- 시설 ---------------- */

export interface 비율항목 {
  이름: string;
  비율: number;
}

/** 종목이 "어떤 종류의 시설에서 이뤄지는가" — 실제 시설 목록이 아니라 통계적 분포다.
 *  실제 주변 시설은 `/api/facilities` 가 따로 준다. */
export interface 시설조건 {
  종목: string;
  시설유형: 비율항목[];
  시설대분류: 비율항목[];
  시설불필요_비율: number;
  신뢰도: 신뢰도;
  표본: number;
  비고?: string;
}

/* ---------------- 추천 종목 ---------------- */

/** 추천 한 칸. 세 갈래가 같은 형태를 쓰되 일부 필드만 갈래별로 붙는다. */
export interface 추천종목 {
  종목: string;
  점수: number;
  선호점수비율: number;
  Lift: number;
  강도: 강도;
  부담부위: string[];
  고령적합: 고령적합;
  실내외: 실내외;
  /** 화면에 그대로 노출된다. 수치 괄호는 `plain()` 이 떼어낸다. */
  이유: string;
  시설: 시설조건;
  원본순위: number;
  display_rank: number;

  /* --- 기반활동에만 --- */
  /** 지침 문구. "중강도로 주 150분을 채우는 가장 쉬운 수단" */
  처방?: string;
  /** 공개 지침 출처. docs/근거자료_운동처방.md */
  근거?: string;
  이미하는중?: boolean;

  /* --- 익숙한운동·새로운운동에만 --- */
  맞춤이유?: string[];
  /** 사용자가 직접 고른 종목에 붙는 가중치 */
  사용자가중?: number;

  /* --- 환경 재정렬이 붙였을 때만 (표현 계층, api/context.py) --- */
  /** "비 예보 — 오늘은 실내가 편해요". 이 값이 있으면 타일에 "오늘 추천" 을 붙인다. */
  환경배지?: string;

  /** 권장 강도 상한을 넘을 때 붙는 주의 문구. 안전 관련이라 화면에서 지우면 안 된다. */
  강도주의?: string;
}

export interface 제외종목 {
  종목: string;
  사유: string;
}

/* ---------------- 유형 배정 ---------------- */

export interface 선호유형 {
  class_id: string;
  name: string;
  /** 0~1. 화면에는 숫자로 노출하지 않는다(§11). */
  probability: number;
}

export interface 체력유형 {
  segment: string;
  confidence: number;
  /** 확신도가 낮아 대안을 병기해야 하는 상태. PRD 의 "확신도 낮으면 대안 유형 병기" 가 이것이다. */
  ambiguous: boolean;
  alternative: string | null;
}

export interface 라우팅 {
  preference_segment: string;
  fitness_group: string;
  display_age_group: string;
  skip_reason: {
    /** null 이 아니면 그 축은 배정되지 않았다(예: 19세 미만 → 체력 미배정). */
    preference: string | null;
    fitness: string | null;
  };
}

/* ---------------- 처방 ---------------- */

export interface 처방 {
  기준: { 유산소: string; 근력: string; 근거: string };
  생애주기: string;
  조정: {
    세그먼트: string;
    시작규칙: string | null;
    메시지: string;
    근거: string;
  };
  강도조정단계: number;
  강도컷: string;
  /** 개인별 강도 상한. 안전 관련이라 화면에서 지우면 안 된다. */
  권장강도상한: 강도;
}

export interface 보완운동 {
  축: string;
  z: number;
  운동: string[];
  처방: string;
  근거: string;
  표현: string;
}

export interface 시설검색조건 {
  종목: string;
  갈래: 갈래;
  시설유형: string[];
  시설대분류: string[];
  시설불필요_비율: number;
  신뢰도: 신뢰도;
}

/* ---------------- 환경 컨텍스트 ---------------- */

/** 기상청 초단기예보 + 통합대기환경지수 + 자외선. 표현 계층이며, 실패해도 추천은 유효하다.
 *  `조회` 의 각 플래그가 false 면 그 배지를 숨긴다 — 핵심 기능은 계속 동작한다. */
/** 환경 배지 한 칸. 화면에는 첫 번째 것만 쓴다. */
export interface 환경배지 {
  문구: string;
  종류?: string;
}

export interface 환경 {
  district: string;
  생성시각: string;
  판정: string;
  실외권장: boolean;
  배지: 환경배지[];
  요약: string;
  기온: number | null;
  강수: string | null;
  하늘: string | null;
  대기: string | null;
  자외선: number | null;
  조회: { 날씨: boolean; 대기: boolean; 자외선: boolean };
}

/* ---------------- /api/serve 응답 전체 ---------------- */

export interface ServeResponse {
  request_id: string;
  생성시각: string;
  api_version: string;
  /** 파라미터가 바뀌면 자동으로 바뀌는 12자리 해시. 어느 버전이 낸 결과인지 로그에서 되짚는다. */
  model_version: string;
  라우팅: 라우팅;
  선호유형: 선호유형 | null;
  체력유형: 체력유형 | null;
  기반활동: 추천종목[];
  익숙한운동: 추천종목[];
  새로운운동: 추천종목[];
  제외종목: 제외종목[];
  처방: 처방;
  보완운동: 보완운동[];
  시설검색조건: 시설검색조건[];
  안내: string[];
  면책: string;
  /** 지원 지역 밖이거나 외부 API 실패 시 없다. */
  환경?: 환경 | null;
  /** 환경에 따라 실내 종목을 앞으로 당겼는지 */
  재정렬?: boolean;
  session_id: string;
}

export interface ServeRequest {
  payload: SurveyPayload;
  district?: string | null;
  session_id?: string | null;
  user_id?: string | null;
}

/* ---------------- 설문 ---------------- */

export type 자가평가축 =
  | '근력' | '유연성' | '근지구력' | '순발력' | '하지근기능' | '협응력평형';

/** 서버로 보내는 설문 응답. 키는 `web/schema.py` 가 정하며 모델 범주와 대조된다
 *  — 어긋나면 서버가 아예 뜨지 않는다. */
export interface SurveyPayload {
  나이?: number;
  성별?: '남' | '여';
  키?: number;
  몸무게?: number;
  규칙적참여?: boolean;
  운동빈도?: string;
  운동요일?: string;
  운동시간대?: string;
  운동목적?: string;
  운동강도?: string;
  체력인지?: string;
  자주해온운동?: string[];
  관심운동?: string[];
  체력자가평가?: Partial<Record<자가평가축, number>>;
  불편부위?: string[];
}

/** 설문 화면이 쓰는 답변 저장소. 자가평가 축이 평평하게 들어 있고,
 *  전송 직전 `buildPayload()` 가 `체력자가평가` 로 접는다. */
export type SurveyAnswers = Record<string, unknown>;

export interface 선택지 {
  value: string;
  label: string;
}

export type 문항유형 = 'bool' | 'number' | 'choice' | 'multi' | 'scale';

export interface 문항 {
  id: string;
  /** 화면에 뜨는 질문. `label` 이 아니다. */
  text: string;
  type: 문항유형;
  options?: 선택지[];
  help?: string;
  /** 비우고 다음으로 넘어갈 수 없다. `bool` 은 false 도 유효한 답이다. */
  required?: boolean;
  min?: number;
  max?: number;
  /** 이 나이 이상에게만 보인다. 체력 자가평가 축이 성인/노인으로 갈린다. */
  age_from?: number | null;
  /** 이 나이 이하에게만 보인다. */
  age_to?: number | null;
}

export interface 설문단계 {
  /** 'pattern' 스텝은 규칙적참여가 false 면 통째로 건너뛴다. */
  id: string;
  title: string;
  note?: string;
  questions: 문항[];
}

export interface SurveySchema {
  version: string;
  note: string;
  steps: 설문단계[];
}

/* ---------------- 지역·시설·지도 ---------------- */

export interface 지역 {
  district: string;
  /** [lat, lon] */
  center: [number, number];
}

export interface DistrictsResponse {
  districts: 지역[];
  note: string;
}

export interface LocateResponse {
  district: string | null;
  supported: boolean;
  reason?: string;
}

export interface 종목마스터 {
  종목: string;
  강도: 강도;
  실내외: 실내외;
  근력: boolean;
  /** '시설불필요' · '집' 이면 지도가 이 종목을 기본으로 고르지 않는다. */
  대체처리: string;
}

export interface SportsResponse {
  sports: 종목마스터[];
  note: string;
}

/* 거리 필드는 전부 `거리m` 이다 — `거리` 가 아니다. */
export interface 접근성 {
  지하철?: { 이름: string; 거리m: number; 노선?: string };
  버스?: { 이름: string; 거리m: number };
  주차장?: { 이름: string; 거리m: number; 장애인구역?: boolean; 요금?: string };
}

/** 체육시설 한 곳. 이름 필드는 `시설명` 이다. */
export interface 시설 {
  시설명: string;
  업종?: string;
  세부유형?: string;
  자치구?: string;
  주소?: string;
  전화번호?: string;
  위도: number;
  경도: number;
  /** 기준 좌표가 없으면 null 이다 — 지역만 고른 경우가 그렇다. */
  거리m: number | null;
  /** 네이버 지도 검색 링크 */
  지도?: string;
}

export interface FacilitiesResponse {
  종목: string;
  예약: 시설[];
  주변: 시설[];
  접근성: 접근성;
  확장: boolean;
  매칭없음: boolean;
  대체처리: string;
  사유?: string;
  확인필요: boolean;
}

export interface 지도핀 extends 시설 {
  예약: boolean;
  예약URL: string | null;
  유무료: string | null;
  예약건수: number;
  접근성?: 접근성;
}

export interface MapFacilitiesResponse {
  종목: string;
  핀: 지도핀[];
  좌표없는예약: 시설[];
  확장: boolean;
  매칭없음: boolean;
  매핑없음?: boolean;
  대체처리: string;
  사유: string;
  확인필요: boolean;
  중심: [number, number];
}

export interface CrowdingResponse {
  district: string;
  메시지: string;
  시간대: { 시각: number; 수준: string }[];
}

/* ---------------- 로그 이벤트 ---------------- */

/** logging_schema.py 의 11종. 소급 수집이 안 되므로 v1부터 남긴다. */
export interface EventRequest {
  event_type: string;
  session_id: string;
  request_id?: string | null;
  model_version?: string | null;
  user_id?: string | null;
  payload?: Record<string, unknown>;
}
