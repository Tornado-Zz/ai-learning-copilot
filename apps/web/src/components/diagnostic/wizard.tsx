"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
} from "react";
import type { ReactNode } from "react";
import type { AnswerChoice, DiagnosticPaper, Question } from "@/lib/questions";
import { clearDraft, readDraft, writeDraft } from "@/lib/diagnostic-draft";

type WizardState = {
  answers: Record<string, AnswerChoice>;
  index: number;
  hydrated: boolean;
  restored: boolean;
  versionDiscarded: boolean;
  savedAt: number | null;
};

type WizardAction =
  | {
      type: "hydrate";
      answers: Record<string, AnswerChoice>;
      index: number;
      savedAt: number | null;
      versionDiscarded: boolean;
    }
  | { type: "answer"; questionId: string; choice: AnswerChoice }
  | { type: "goto"; index: number }
  | { type: "reset" }
  | { type: "saved"; at: number };

const INITIAL_STATE: WizardState = {
  answers: {},
  index: 0,
  hydrated: false,
  restored: false,
  versionDiscarded: false,
  savedAt: null,
};

function clampIndex(index: number, count: number): number {
  return Math.min(count - 1, Math.max(0, index));
}

function pruneAnswers(
  answers: Record<string, AnswerChoice>,
  questions: Question[],
): Record<string, AnswerChoice> {
  const pruned: Record<string, AnswerChoice> = {};
  for (const question of questions) {
    const choice = answers[question.id];
    if (choice) {
      pruned[question.id] = choice;
    }
  }
  return pruned;
}

function reducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "hydrate": {
      return {
        answers: action.answers,
        index: action.index,
        hydrated: true,
        restored: Object.keys(action.answers).length > 0,
        versionDiscarded: action.versionDiscarded,
        savedAt: action.savedAt,
      };
    }
    case "answer": {
      return {
        ...state,
        answers: { ...state.answers, [action.questionId]: action.choice },
      };
    }
    case "goto": {
      return { ...state, index: action.index };
    }
    case "reset": {
      return {
        answers: {},
        index: 0,
        hydrated: state.hydrated,
        restored: false,
        versionDiscarded: state.versionDiscarded,
        savedAt: null,
      };
    }
    case "saved": {
      return { ...state, savedAt: action.at };
    }
    default:
      return state;
  }
}

type WizardContextValue = {
  paper: DiagnosticPaper;
  answers: Record<string, AnswerChoice>;
  index: number;
  hydrated: boolean;
  restored: boolean;
  versionDiscarded: boolean;
  savedAt: number | null;
  current: Question;
  answeredCount: number;
  unansweredNumbers: number[];
  isComplete: boolean;
  answer: (questionId: string, choice: AnswerChoice) => void;
  goto: (index: number) => void;
  next: () => void;
  previous: () => void;
  reset: () => void;
  goToFirstUnanswered: () => void;
};

const WizardContext = createContext<WizardContextValue | null>(null);

export function DiagnosticWizardProvider({
  paper,
  children,
}: {
  paper: DiagnosticPaper;
  children: ReactNode;
}) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  useEffect(() => {
    const draft = readDraft();
    if (draft && draft.questionSetVersion !== paper.questionSetVersion) {
      clearDraft();
      dispatch({
        type: "hydrate",
        answers: {},
        index: 0,
        savedAt: null,
        versionDiscarded: true,
      });
      return;
    }
    if (!draft) {
      dispatch({ type: "hydrate", answers: {}, index: 0, savedAt: null, versionDiscarded: false });
      return;
    }
    dispatch({
      type: "hydrate",
      answers: pruneAnswers(draft.answers, paper.questions),
      index: clampIndex(draft.currentIndex, paper.questions.length),
      savedAt: draft.updatedAt > 0 ? draft.updatedAt : null,
      versionDiscarded: false,
    });
  }, [paper]);

  useEffect(() => {
    if (!state.hydrated) {
      return;
    }
    const saved = writeDraft({
      questionSetVersion: paper.questionSetVersion,
      ruleVersion: paper.ruleVersion,
      answers: state.answers,
      currentIndex: state.index,
      updatedAt: Date.now(),
    });
    if (saved) {
      dispatch({ type: "saved", at: Date.now() });
    }
  }, [state.hydrated, state.answers, state.index, paper.questionSetVersion, paper.ruleVersion]);

  const answer = useCallback((questionId: string, choice: AnswerChoice) => {
    dispatch({ type: "answer", questionId, choice });
  }, []);

  const goto = useCallback(
    (index: number) => {
      dispatch({ type: "goto", index: clampIndex(index, paper.questions.length) });
    },
    [paper.questions.length],
  );

  const reset = useCallback(() => {
    dispatch({ type: "reset" });
  }, []);

  const value = useMemo<WizardContextValue>(() => {
    const questions = paper.questions;
    const current = questions[state.index] ?? questions[0];
    const unansweredNumbers: number[] = [];
    for (const question of questions) {
      if (!state.answers[question.id]) {
        unansweredNumbers.push(question.number);
      }
    }
    const answeredCount = questions.length - unansweredNumbers.length;
    return {
      paper,
      answers: state.answers,
      index: state.index,
      hydrated: state.hydrated,
      restored: state.restored,
      versionDiscarded: state.versionDiscarded,
      savedAt: state.savedAt,
      current,
      answeredCount,
      unansweredNumbers,
      isComplete: paper.total > 0 && answeredCount >= paper.total,
      answer,
      goto,
      next: () => goto(state.index + 1),
      previous: () => goto(state.index - 1),
      reset,
      goToFirstUnanswered: () => {
        if (unansweredNumbers.length === 0) {
          return;
        }
        const first = unansweredNumbers[0];
        const target = questions.findIndex((question) => question.number === first);
        if (target >= 0) {
          goto(target);
        }
      },
    };
  }, [paper, state, answer, goto, reset]);

  return <WizardContext.Provider value={value}>{children}</WizardContext.Provider>;
}

export function useDiagnosticWizard(): WizardContextValue {
  const value = useContext(WizardContext);
  if (!value) {
    throw new Error("useDiagnosticWizard must be used inside DiagnosticWizardProvider");
  }
  return value;
}
