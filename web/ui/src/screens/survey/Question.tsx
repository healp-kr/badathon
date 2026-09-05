/* 문항 한 칸 — 다섯 유형(bool · number · choice · scale · multi)을 그린다.
 *
 * 바닐라에서는 문자열 HTML 을 만든 뒤 `bindQuestions()` 가 `data-q` 속성으로 다시
 * 찾아 핸들러를 붙였다. 그 과정에서 "숫자처럼 생긴 chips 값은 Number 로 바꾼다" 같은
 * 규칙이 바인딩 쪽에 숨어 있었다. 여기서는 유형별로 값이 명시적으로 만들어진다.
 */
import { useApp } from '../../state/AppContext';
import type { 문항 } from '../../api/types';

/** 미응답으로 막힌 문항으로 스크롤할 때 쓰는 앵커. `Survey` 가 같은 규칙으로 찾는다. */
export const anchorId = (questionId: string) => `q-${questionId}`;

interface QuestionProps {
  question: 문항;
  /** 있으면 이 문항이 진행을 막고 있다는 뜻이고, 문자열이 그 사유다. */
  problem?: string;
}

export default function Question({ question, problem }: QuestionProps) {
  const { answers, setAnswer } = useApp();
  const value = answers[question.id];
  const noteId = `${anchorId(question.id)}-problem`;

  return (
    <fieldset id={anchorId(question.id)} data-invalid={problem ? 'true' : undefined}>
      <legend>
        {question.text}
        {question.required && (
          <span className="req" aria-label="필수 항목">
            *
          </span>
        )}
      </legend>
      {question.help && <p className="muted">{question.help}</p>}
      <Body question={question} value={value} onPick={setAnswer} />
      {problem && (
        <p className="note bad" id={noteId} role="alert">
          {problem}
        </p>
      )}
    </fieldset>
  );
}

interface BodyProps {
  question: 문항;
  value: unknown;
  onPick(id: string, value: unknown): void;
}

function Body({ question, value, onPick }: BodyProps) {
  switch (question.type) {
    case 'bool':
      return (
        <div className="chips">
          {([['예', true], ['아니오', false]] as const).map(([label, v]) => (
            <button
              key={label}
              className="opt"
              type="button"
              aria-pressed={value === v}
              onClick={() => onPick(question.id, v)}
            >
              {label}
            </button>
          ))}
        </div>
      );

    case 'number':
      return (
        <input
          type="number"
          inputMode="numeric"
          value={value === undefined || value === null ? '' : String(value)}
          min={question.min ?? undefined}
          max={question.max ?? undefined}
          onChange={(e) =>
            onPick(question.id, e.target.value === '' ? undefined : Number(e.target.value))
          }
        />
      );

    case 'choice':
    case 'scale': {
      // scale 은 chips 로 눕히고 값이 숫자면 숫자로 저장한다 — 모델이 정수를 기대한다
      const numeric = question.type === 'scale';
      return (
        <div className={numeric ? 'chips' : ''}>
          {(question.options ?? []).map((o) => {
            const picked = numeric && /^\d+$/.test(o.value) ? Number(o.value) : o.value;
            return (
              <button
                key={o.value}
                className="opt"
                type="button"
                aria-pressed={value === picked}
                onClick={() => onPick(question.id, picked)}
              >
                {o.label}
              </button>
            );
          })}
        </div>
      );
    }

    case 'multi': {
      const picked = new Set((value as string[] | undefined) ?? []);
      return (
        <div className="chips">
          {(question.options ?? []).map((o) => (
            <button
              key={o.value}
              className="opt"
              type="button"
              aria-pressed={picked.has(o.value)}
              onClick={() => {
                const next = new Set(picked);
                if (next.has(o.value)) next.delete(o.value);
                else next.add(o.value);
                onPick(question.id, [...next]);
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      );
    }

    default:
      return null;
  }
}
