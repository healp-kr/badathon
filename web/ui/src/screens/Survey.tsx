/* S1 온보딩 — 13문항.
 *
 * 스텝과 문항의 노출 규칙은 `features/survey/steps.ts` 가, 넘어가도 되는지는
 * `features/survey/validate.ts` 가 정한다. 화면은 그 결과를 그리기만 한다.
 *
 * 나이가 없으면 체력 문항 세트를 못 정하므로, 보일 문항이 하나도 없는 스텝은 건너뛴다.
 */
import { useEffect, useState } from 'react';
import { activeSteps, visibleQuestions } from '../features/survey/steps';
import { findProblems, type Problems } from '../features/survey/validate';
import Question, { anchorId } from './survey/Question';
import { useApp } from '../state/AppContext';
import styles from './Survey.module.css';

export default function Survey() {
  const { schema, answers, step, setStep, submit, submitError } = useApp();
  /* 처음부터 빨갛게 칠하지 않는다 — [다음]을 눌러 막힌 뒤에야 사유를 보여준다. */
  const [problems, setProblems] = useState<Problems>(new Map());

  const steps = schema ? activeSteps(schema.steps, answers) : [];
  const current = steps[step];
  const questions = current ? visibleQuestions(current, answers) : [];

  /* 스텝이 바뀌면 위로. 긴 문항 목록에서 중간부터 보이면 답을 빠뜨린다. */
  useEffect(() => {
    window.scrollTo(0, 0);
    setProblems(new Map());
  }, [step]);

  /* 보일 문항이 없는 스텝은 지나친다(예: 나이 미입력 시 체력 축).
   * 렌더 중 상태를 바꾸지 않도록 effect 로 미룬다. */
  useEffect(() => {
    if (current && questions.length === 0) setStep(step + 1);
  }, [current, questions.length, step, setStep]);

  if (!current || questions.length === 0) return <p className="loading">준비 중…</p>;

  const last = step === steps.length - 1;

  function advance(delta: number) {
    const next = step + delta;
    if (next < 0) return;

    /* 뒤로 갈 때는 막지 않는다 — 앞 스텝의 답을 고치러 가는 길이다. */
    if (delta > 0) {
      const found = findProblems(questions, answers);
      if (found.size > 0) {
        setProblems(found);
        const first = questions.find((q) => found.has(q.id));
        if (first) {
          const el = document.getElementById(anchorId(first.id));
          el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
      }
      setProblems(new Map());
    }

    if (next >= steps.length) {
      void submit();
      return;
    }
    setStep(next);
  }

  return (
    <>
      <div className={styles.progress}>
        <div style={{ width: `${(step / steps.length) * 100}%` }} />
      </div>

      <h1>{current.title}</h1>
      {current.note && <p className="muted">{current.note.split('.')[0]}.</p>}
      <p className="note">
        <span className="req">*</span> 표시는 필수 항목이에요
      </p>

      <form onSubmit={(e) => e.preventDefault()}>
        {questions.map((q) => (
          <Question key={q.id} question={q} problem={problems.get(q.id)} />
        ))}
      </form>

      {problems.size > 0 && (
        <p className="note bad" role="alert">
          답하지 않은 필수 항목이 {problems.size}개 있어요
        </p>
      )}

      {/* 서버가 거절한 경우. 이걸 안 띄우면 [결과 보기] 가 먹통으로만 보인다. */}
      {submitError && (
        <p className="note bad" role="alert">
          결과를 만들지 못했어요 — {submitError}
        </p>
      )}

      <button className="primary" type="button" onClick={() => advance(1)}>
        {last ? '결과 보기' : '다음'}
      </button>

      {step > 0 && (
        <button className="ghost" type="button" onClick={() => advance(-1)}>
          이전
        </button>
      )}
    </>
  );
}
