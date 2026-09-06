import { useState } from "react";
import type { ArticleRef, LeanLabel, StoryRef } from "../lib/types";
import { SPECTRUM } from "../lib/types";
import { Spectrum, leanColor } from "./Spectrum";

const ORDER: LeanLabel[] = [...SPECTRUM, "unrated"];

/**
 * One story, shown as how each part of the spectrum reported it.
 *
 * The default view deliberately shows at most one headline per spectrum
 * position rather than every article. Listing eight outlets from the same
 * lean is the reading experience this app exists to replace -- it looks like
 * breadth while adding none.
 */
export function StoryCard({ story }: { story: StoryRef }) {
  const [expanded, setExpanded] = useState(false);

  const groups = ORDER.map((lean) => [lean, story.by_lean[lean] ?? []] as const).filter(
    ([, items]) => items.length > 0,
  );

  const hiddenCount = story.articles.length - groups.length;

  return (
    <article className="story">
      <h2>{story.headline}</h2>

      {story.neutral_summary && <p className="neutral">{story.neutral_summary}</p>}

      <Spectrum histogram={story.lean_histogram} gaps={story.coverage_gaps} />

      <div className="metrics">
        <span>balance {story.balance_score.toFixed(2)}</span>
        <span>diversity {story.diversity_score.toFixed(2)}</span>
        <span>
          {story.source_count} outlet{story.source_count === 1 ? "" : "s"}
        </span>
        {story.reprint_count > 0 && (
          <span className="warn">
            {story.reprint_count} wire reprint{story.reprint_count === 1 ? "" : "s"}
          </span>
        )}
        {story.coverage_gaps.length > 0 && (
          <span className="warn">silent: {story.coverage_gaps.join(", ")}</span>
        )}
      </div>

      <div className="coverage">
        {groups.map(([lean, items]) => (
          <Row key={lean} lean={lean} articles={expanded ? items : items.slice(0, 1)} />
        ))}
      </div>

      {hiddenCount > 0 && (
        <button className="more" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "show one per position" : `show all ${story.articles.length} articles`}
        </button>
      )}
    </article>
  );
}

function Row({ lean, articles }: { lean: LeanLabel; articles: ArticleRef[] }) {
  return (
    <>
      {articles.map((article, index) => (
        <div className="coverage-row" key={article.id}>
          {index === 0 ? (
            <span className="badge" style={{ background: leanColor(lean) }}>
              {lean}
            </span>
          ) : (
            <span />
          )}
          <div>
            <a href={article.url} target="_blank" rel="noopener noreferrer">
              {article.title}
            </a>
            <div className="outlet">
              {article.source.name}
              {article.syndicated_from && (
                <span className="tag">via {article.syndicated_from}</span>
              )}
              {article.source.state_affiliated && (
                <span className="tag state">state-affiliated</span>
              )}
              {article.source.paywall === "hard" && <span className="tag">paywall</span>}
              {article.source.country && article.source.country !== "US" && (
                <span className="tag">{article.source.country}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
