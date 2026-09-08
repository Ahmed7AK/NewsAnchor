export type LeanLabel = "left" | "lean-left" | "center" | "lean-right" | "right" | "unrated";

export const SPECTRUM: LeanLabel[] = ["left", "lean-left", "center", "lean-right", "right"];

export interface SourceRef {
  id: string;
  name: string;
  lean: number | null;
  lean_label: LeanLabel;
  country: string | null;
  tier: string | null;
  state_affiliated: boolean;
  paywall: string | null;
}

export interface NewsroomRef {
  id: string;
  name: string;
  lean: number | null;
  lean_label: LeanLabel;
}

export interface ArticleRef {
  id: string;
  title: string;
  url: string;
  summary: string;
  published_at: string;
  syndicated_from: string | null;
  source: SourceRef;
  /** Who actually reported it -- the wire, for syndicated copy. */
  newsroom: NewsroomRef;
  /** How many outlets carried this newsroom's copy. Only set inside by_lean. */
  carried_by?: number;
}

export interface StoryRef {
  id: string;
  headline: string;
  lead_source_id: string;
  newest: string;
  articles: ArticleRef[];
  by_lean: Partial<Record<LeanLabel, ArticleRef[]>>;
  lean_histogram: Partial<Record<LeanLabel, number>>;
  unrated_newsrooms: number;
  coverage_gaps: LeanLabel[];
  balance_score: number;
  diversity_score: number;
  prominence: number;
  rank_score: number;
  neutral_summary: string;
  source_count: number;
  reprint_count: number;
}

export interface DigestRef {
  generated_at: string;
  window_start: string;
  article_count: number;
  source_count: number;
  warnings: string[];
  errors: string[];
  llm_summaries_enabled: boolean;
  stories: StoryRef[];
}

export interface SourcesRef {
  sources: (SourceRef & {
    homepage: string;
    enabled: boolean;
    feed_count: number;
    notes: string;
  })[];
  spectrum: Record<string, string[]>;
  warnings: string[];
  pollable_leans: number[];
}

export interface ReadingBalanceRef {
  days: number;
  total_articles: number;
  by_source: { id: string; name: string; count: number; share: number }[];
  by_lean: Record<string, number>;
  by_country: Record<string, number>;
}
