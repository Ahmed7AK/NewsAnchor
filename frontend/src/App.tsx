import { useCallback, useEffect, useState } from "react";
import { BalancePanel } from "./components/BalancePanel";
import { SourcesPanel } from "./components/SourcesPanel";
import { StoryCard } from "./components/StoryCard";
import { fetchDigest, fetchReadingBalance, fetchSources, refresh } from "./lib/api";
import type { DigestRef, ReadingBalanceRef, SourcesRef } from "./lib/types";

type Tab = "feed" | "sources" | "balance";

export default function App() {
  const [tab, setTab] = useState<Tab>("feed");
  const [digest, setDigest] = useState<DigestRef | null>(null);
  const [sources, setSources] = useState<SourcesRef | null>(null);
  const [balance, setBalance] = useState<ReadingBalanceRef | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [includeState, setIncludeState] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setDigest(await fetchDigest());
    } catch (exc) {
      // A missing digest is the expected first-run state, not a failure.
      setDigest(null);
      const message = exc instanceof Error ? exc.message : String(exc);
      if (!message.includes("No digest stored")) setError(message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (tab === "sources" && !sources) fetchSources().then(setSources).catch(() => {});
    if (tab === "balance") fetchReadingBalance().then(setBalance).catch(() => {});
  }, [tab, sources]);

  async function onRefresh() {
    setBusy(true);
    setError(null);
    try {
      setDigest(
        await refresh({
          includeStateAffiliated: includeState,
          summarise: digest?.llm_summaries_enabled ?? false,
        }),
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <header className="masthead">
        <h1>NewsAnchor</h1>
        <div className="meta">
          {digest ? (
            <>
              {new Date(digest.generated_at).toLocaleString()} · {digest.article_count}{" "}
              articles from {digest.source_count} sources · {digest.stories.length} stories
            </>
          ) : (
            "no digest yet"
          )}
        </div>
      </header>

      <div className="toolbar">
        <div className="tabs" role="tablist">
          {(["feed", "sources", "balance"] as Tab[]).map((name) => (
            <button
              key={name}
              role="tab"
              aria-selected={tab === name}
              onClick={() => setTab(name)}
            >
              {name === "balance" ? "my balance" : name}
            </button>
          ))}
        </div>

        <label className="toggle">
          <input
            type="checkbox"
            checked={includeState}
            onChange={(event) => setIncludeState(event.target.checked)}
          />
          include state media
        </label>

        <button className="primary" onClick={onRefresh} disabled={busy}>
          {busy ? "fetching…" : "refresh"}
        </button>
      </div>

      {error && <p className="notice error">{error}</p>}

      {tab === "feed" && (
        <>
          {digest?.warnings.map((warning) => (
            <p className="notice" key={warning}>
              {warning}
            </p>
          ))}
          {digest && digest.errors.length > 0 && (
            <p className="notice">
              {digest.errors.length} feed(s) failed this run — run{" "}
              <code>newsanchor sources check</code> to see which.
            </p>
          )}

          {!digest && !busy && (
            <p className="empty-state">
              Nothing here yet. Hit <strong>refresh</strong> to fetch the last 24
              hours, or run <code>newsanchor refresh</code>.
            </p>
          )}
          {digest?.stories.map((story) => (
            <StoryCard key={story.id} story={story} />
          ))}
        </>
      )}

      {tab === "sources" &&
        (sources ? <SourcesPanel data={sources} /> : <p className="empty-state">loading…</p>)}

      {tab === "balance" &&
        (balance ? <BalancePanel data={balance} /> : <p className="empty-state">loading…</p>)}
    </div>
  );
}
