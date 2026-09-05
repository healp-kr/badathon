/* 설문 진행 규칙 — 어떤 스텝과 문항이 보이는가.
 *
 * 바닐라의 `activeSteps()` · `visibleQuestions()` 를 옮겼다. 화면에서 떼어낸 이유는
 * 이 규칙이 순수 함수이고, 화면 없이도 검증할 수 있어야 하기 때문이다.
 */
import type { SurveyAnswers, 문항, 설문단계 } from '../../api/types';

/** 비참여자는 운동 패턴(§2) 스텝을 통째로 건너뛴다. */
export function activeSteps(steps: 설문단계[], answers: SurveyAnswers): 설문단계[] {
  if (answers['규칙적참여'] === false) {
    return steps.filter((s) => s.id !== 'pattern');
  }
  return steps;
}

/** 나이에 따라 체력 자가평가 축이 성인/노인으로 갈린다. */
export function visibleQuestions(step: 설문단계, answers: SurveyAnswers): 문항[] {
  const age = answers['나이'] as number | undefined;
  return step.questions.filter((q) => {
    if (q.age_from != null && (age == null || age < q.age_from)) return false;
    if (q.age_to != null && age != null && age > q.age_to) return false;
    return true;
  });
}
