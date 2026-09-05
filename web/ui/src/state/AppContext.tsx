/* 앱 전역 상태 — 바닐라 버전의 전역 `state` 객체와 `BD` 네임스페이스를 대체한다.
 *
 * 바닐라에서는 `app.js` 가 상태를 들고, `map.js` · `records.js` 가 `BD.state` 를
 * 통해 그것을 읽었다. 누가 언제 무엇을 바꾸는지 추적하기 어려웠다.
 * 여기서는 상태 변경이 전부 아래 Action 유니온 하나를 지나므로, 새 동작을 넣을 때
 * 어디를 건드려야 하는지가 타입으로 드러난다.
 *
 * 저장 정책(현행 유지):
 *   · 지역   → localStorage. 직접 고른 경우에만 남긴다.
 *   · 기록   → localStorage (useRecords 가 담당)
 *   · 답변·결과 → 메모리. 새로고침하면 사라지고 설문을 다시 한다.
 *
 * 답변을 저장해 설문을 건너뛰는 기능은 아직 넣지 않았다. 넣을 자리는
 * `SET_ANSWERS` 와 부트 시퀀스이며, 그때도 **결과가 아니라 답변**을 저장해야 한다
 * — 결과에는 그 시점의 날씨로 재정렬된 순서가 들어 있어 하루만 지나도 낡는다.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react';
import {
  fetchDistricts,
  fetchSports,
  fetchSurveySchema,
  requestServe,
} from '../api/endpoints';
import type {
  ServeResponse,
  SurveyAnswers,
  SurveySchema,
  종목마스터,
  지역,
} from '../api/types';

/** 하단 탭. null 이면 아직 온보딩 중이라 탭바를 감춘다. */
export type Tab = '홈' | '운동' | '지도' | '기록';

/** 지역을 어떻게 정했는지. 'manual' 만 localStorage 에 남는다
 *  — 자동 판정 결과를 저장하면 다른 동네에서 열었을 때 틀린 지역이 눌러붙는다. */
export type DistrictSource = 'auto' | 'manual' | 'override';

export const DISTRICT_KEY = 'badathon.district';

export interface AppState {
  /* 부트 시 한 번 받아오는 것들 */
  schema: SurveySchema | null;
  districts: 지역[];
  sports: 종목마스터[];
  booted: boolean;
  bootError: string | null;

  /* 사용자 컨텍스트 */
  district: string | null;
  districtSource: DistrictSource | null;
  coords: { lat: number; lon: number } | null;

  /* 설문 */
  answers: SurveyAnswers;
  step: number;

  /* 결과 */
  result: ServeResponse | null;
  submitting: boolean;
  submitError: string | null;

  /* 화면 */
  tab: Tab | null;
  surveyOpen: boolean;
}

const initialState: AppState = {
  schema: null,
  districts: [],
  sports: [],
  booted: false,
  bootError: null,
  district: null,
  districtSource: null,
  coords: null,
  answers: {},
  step: 0,
  result: null,
  submitting: false,
  submitError: null,
  // 바닐라의 renderIntro() 가 state.tab='홈' 으로 시작하는 것과 같다
  tab: '홈',
  surveyOpen: false,
};

type Action =
  | { type: 'BOOT_OK'; schema: SurveySchema; districts: 지역[]; sports: 종목마스터[] }
  | { type: 'BOOT_FAIL'; message: string }
  | { type: 'SET_DISTRICT'; district: string; source: DistrictSource }
  | { type: 'CLEAR_DISTRICT' }
  | { type: 'SET_COORDS'; coords: { lat: number; lon: number } | null }
  | { type: 'SET_ANSWER'; id: string; value: unknown }
  | { type: 'SET_ANSWERS'; answers: SurveyAnswers }
  | { type: 'SET_STEP'; step: number }
  | { type: 'OPEN_SURVEY' }
  | { type: 'SUBMIT_START' }
  | { type: 'SUBMIT_OK'; result: ServeResponse }
  | { type: 'SUBMIT_FAIL'; message: string }
  | { type: 'SET_TAB'; tab: Tab };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'BOOT_OK':
      return {
        ...state,
        booted: true,
        bootError: null,
        schema: action.schema,
        districts: action.districts,
        sports: action.sports,
      };

    case 'BOOT_FAIL':
      return { ...state, booted: true, bootError: action.message };

    case 'SET_DISTRICT':
      return { ...state, district: action.district, districtSource: action.source };

    case 'CLEAR_DISTRICT':
      return { ...state, district: null, districtSource: null };

    case 'SET_COORDS':
      return { ...state, coords: action.coords };

    case 'SET_ANSWER':
      return { ...state, answers: { ...state.answers, [action.id]: action.value } };

    case 'SET_ANSWERS':
      return { ...state, answers: action.answers };

    case 'SET_STEP':
      return { ...state, step: action.step };

    case 'OPEN_SURVEY':
      // 설문 중에는 탭바를 감춘다 — 바닐라의 `state.tab = null` 과 같다
      return { ...state, surveyOpen: true, step: 0, tab: null };

    case 'SUBMIT_START':
      return { ...state, submitting: true, submitError: null };

    case 'SUBMIT_OK':
      return {
        ...state,
        submitting: false,
        submitError: null,
        result: action.result,
        surveyOpen: false,
        // 지도에서 지역을 바꿔 다시 돌린 경우라면 그 화면에 머문다
        tab: state.tab && state.tab !== '홈' ? state.tab : '홈',
      };

    case 'SUBMIT_FAIL':
      return { ...state, submitting: false, submitError: action.message };

    case 'SET_TAB':
      return { ...state, tab: action.tab, surveyOpen: false };

    default:
      return state;
  }
}

interface AppContextValue extends AppState {
  setDistrict(district: string, source: DistrictSource): void;
  clearDistrict(): void;
  setCoords(coords: { lat: number; lon: number } | null): void;
  setAnswer(id: string, value: unknown): void;
  setStep(step: number): void;
  openSurvey(): void;
  submit(): Promise<void>;
  setTab(tab: Tab): void;
}

const AppContext = createContext<AppContextValue | null>(null);

/** 자가평가 축은 답변 저장소에 평평하게 들어 있다가 전송 직전 접힌다. */
const SELF_AXES = [
  '근력', '유연성', '근지구력', '순발력', '하지근기능', '협응력평형',
] as const;

/** 화면 답변 → 서버 payload. 빈 값은 보내지 않는다. */
export function buildPayload(answers: SurveyAnswers): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  const rating: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(answers)) {
    if (value === undefined || value === null || value === '') continue;
    if ((SELF_AXES as readonly string[]).includes(key)) {
      rating[key] = value;
      continue;
    }
    payload[key] = value;
  }

  if (Object.keys(rating).length) payload['체력자가평가'] = rating;
  return payload;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  /* 부트 — 설문 문항·지역·종목 마스터를 한 번에 받는다. */
  useEffect(() => {
    let alive = true;
    Promise.all([fetchSurveySchema(), fetchDistricts(), fetchSports()])
      .then(([schema, districts, sports]) => {
        if (!alive) return;
        dispatch({
          type: 'BOOT_OK',
          schema,
          districts: districts.districts,
          sports: sports.sports,
        });

        // 직접 골라둔 지역이 있으면 복원한다
        try {
          const saved = localStorage.getItem(DISTRICT_KEY);
          if (saved && districts.districts.some((d) => d.district === saved)) {
            dispatch({ type: 'SET_DISTRICT', district: saved, source: 'manual' });
          }
        } catch {
          /* 사파리 프라이빗 모드 등 — 지역 복원은 없어도 그만이다 */
        }
      })
      .catch((error: unknown) => {
        if (!alive) return;
        dispatch({
          type: 'BOOT_FAIL',
          message: error instanceof Error ? error.message : '불러오지 못했어요',
        });
      });
    return () => {
      alive = false;
    };
  }, []);

  const setDistrict = useCallback((district: string, source: DistrictSource) => {
    dispatch({ type: 'SET_DISTRICT', district, source });
    // 자동 판정은 저장하지 않는다 — 다른 동네에서 열면 틀린 값이 눌러붙는다
    if (source === 'manual') {
      try {
        localStorage.setItem(DISTRICT_KEY, district);
      } catch { /* 저장 실패는 무시한다 */ }
    }
  }, []);

  const clearDistrict = useCallback(() => {
    dispatch({ type: 'CLEAR_DISTRICT' });
    try {
      localStorage.removeItem(DISTRICT_KEY);
    } catch { /* 무시 */ }
  }, []);

  const setCoords = useCallback(
    (coords: { lat: number; lon: number } | null) =>
      dispatch({ type: 'SET_COORDS', coords }),
    [],
  );

  const setAnswer = useCallback(
    (id: string, value: unknown) => dispatch({ type: 'SET_ANSWER', id, value }),
    [],
  );

  const setStep = useCallback(
    (step: number) => dispatch({ type: 'SET_STEP', step }),
    [],
  );

  const openSurvey = useCallback(() => dispatch({ type: 'OPEN_SURVEY' }), []);

  const setTab = useCallback((tab: Tab) => dispatch({ type: 'SET_TAB', tab }), []);

  /* 처방 요청. 지역을 바꿔 다시 돌릴 때도 같은 함수를 쓴다
   * — 그래야 세션이 이어지고 로그가 한 줄기로 남는다. */
  const submit = useCallback(async () => {
    dispatch({ type: 'SUBMIT_START' });
    try {
      const result = await requestServe({
        payload: buildPayload(state.answers),
        district: state.district,
        session_id: state.result?.session_id ?? null,
      });
      dispatch({ type: 'SUBMIT_OK', result });
    } catch (error: unknown) {
      const detail =
        error && typeof error === 'object' && 'detail' in error
          ? String((error as { detail: unknown }).detail)
          : '다시 시도해 주세요.';
      dispatch({ type: 'SUBMIT_FAIL', message: detail });
    }
  }, [state.answers, state.district, state.result?.session_id]);

  const value = useMemo<AppContextValue>(
    () => ({
      ...state,
      setDistrict,
      clearDistrict,
      setCoords,
      setAnswer,
      setStep,
      openSurvey,
      submit,
      setTab,
    }),
    [state, setDistrict, clearDistrict, setCoords, setAnswer, setStep, openSurvey, submit, setTab],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp 은 AppProvider 안에서만 쓸 수 있습니다');
  return ctx;
}
