import type { DigestRef, ReadingBalanceRef, SourcesRef } from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const fetchDigest = () => get<DigestRef>("/api/digest");
export const fetchSources = () => get<SourcesRef>("/api/sources");
export const fetchReadingBalance = (days = 30) =>
  get<ReadingBalanceRef>(`/api/reading-balance?days=${days}`);

export async function refresh(options: {
  windowHours?: number;
  minSources?: number;
  includeStateAffiliated?: boolean;
  summarise?: boolean;
}): Promise<DigestRef> {
  const params = new URLSearchParams({
    window_hours: String(options.windowHours ?? 24),
    min_sources: String(options.minSources ?? 1),
    include_state_affiliated: String(options.includeStateAffiliated ?? false),
    summarise: String(options.summarise ?? false),
  });
  const response = await fetch(`/api/refresh?${params}`, { method: "POST" });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<DigestRef>;
}
