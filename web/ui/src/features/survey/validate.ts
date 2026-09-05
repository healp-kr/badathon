/* 설문 응답 검증 — 이 스텝을 넘어가도 되는가.
 *
 * `steps.ts` 와 같은 이유로 화면에서 떼어냈다. 순수 함수이고, 화면 없이 검증할 수 있어야 한다.
 *
 * 검증은 **보이는 문항에만** 건다. 비참여자에게 감춘 운동 패턴 스텝이나, 나이 때문에
 * 뜨지 않는 체력 축을 미응답으로 잡으면 넘어갈 수 없는 화면이 된다 — 호출부가
 * `activeSteps` · `visibleQuestions` 를 먼저 통과시킨 목록을 넘겨야 한다.
 */
import type { SurveyAnswers, 문항 } from '../../api/types';

/** 문항 id → 그 문항 아래에 띄울 사유. 비어 있으면 다음으로 넘어가도 된다. */
export type Problems = Map<string, string>;

export function findProblems(questions: 문항[], answers: SurveyAnswers): Problems {
  const problems: Problems = new Map();

  for (const question of questions) {
    const value = answers[question.id];

    if (question.required && isBlank(question, value)) {
      problems.set(question.id, question.type === 'multi' ? '하나 이상 골라주세요' : '답해 주세요');
      continue;
    }

    /* 범위는 값이 있을 때만 본다 — 필수가 아닌 키·몸무게도 오타는 잡아야 한다.
     * 나이가 범위를 벗어나면 라우팅이 엉뚱한 세그먼트로 가므로 여기서 막는 편이 낫다. */
    if (question.type === 'number' && typeof value === 'number') {
      if (Number.isNaN(value)) {
        problems.set(question.id, '숫자로 입력해 주세요');
      } else if (question.min != null && value < question.min) {
        problems.set(question.id, `${question.min} 이상으로 입력해 주세요`);
      } else if (question.max != null && value > question.max) {
        problems.set(question.id, `${question.max} 이하로 입력해 주세요`);
      }
    }
  }

  return problems;
}

/** `bool` 의 false 와 `number` 의 0 은 답을 안 한 것이 아니다. */
function isBlank(question: 문항, value: unknown): boolean {
  if (value === undefined || value === null || value === '') return true;
  if (question.type === 'multi') return !Array.isArray(value) || value.length === 0;
  return false;
}
