import { create } from "zustand";

export type AnalyzeContext = {
  company_id?: string | null;
  fixture_id?: string | null;
  grade?: string | null;
  score?: number | null;
  rules_hit?: number | null;
  conflicts?: number | null;
  headline?: string | null;
};

type UiState = {
  selectedFixture: string;
  setSelectedFixture: (id: string) => void;
  analyzeContext: AnalyzeContext;
  setAnalyzeContext: (ctx: AnalyzeContext) => void;
};

export const useUiStore = create<UiState>((set) => ({
  selectedFixture: "risky",
  setSelectedFixture: (selectedFixture) => set({ selectedFixture }),
  analyzeContext: {},
  setAnalyzeContext: (analyzeContext) => set({ analyzeContext }),
}));
