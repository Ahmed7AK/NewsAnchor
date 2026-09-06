import type { ReadingBalanceRef } from "../lib/types";
import { leanColor } from "./Spectrum";
import type { LeanLabel } from "../lib/types";

/**
 * What the feed has actually consisted of lately.
 *
 * Per-story balance scores can every one of them look healthy while the feed
 * as a whole is three outlets wearing a trench coat. This is the check on
 * that, and it is the number worth watching over time.
 */
export function BalancePanel({ data }: { data: ReadingBalanceRef }) {
  if (data.total_articles === 0) {
    return (
      <p className="empty-state">
        Nothing stored yet. Run a refresh, then come back after a few days —
        this view is about trends, not a single morning.
      </p>
    );
  }

  const top = data.by_source[0];
  const concentrated = top && top.share > 0.3;

  return (
    <section>
      {concentrated && (
        <p className="notice">
          {top.name} accounts for {(top.share * 100).toFixed(0)}% of everything you
          have been shown in the last {data.days} days. Consider adding sources, or
          lowering <code>max_source_share</code>.
        </p>
      )}

      <h3 style={{ fontSize: 15 }}>By spectrum position</h3>
      <table>
        <tbody>
          {Object.entries(data.by_lean)
            .sort((a, b) => b[1] - a[1])
            .map(([lean, count]) => (
              <tr key={lean}>
                <td style={{ width: 110 }}>
                  <span
                    className="badge"
                    style={{ background: leanColor(lean as LeanLabel) }}
                  >
                    {lean}
                  </span>
                </td>
                <td className="num" style={{ width: 60 }}>
                  {((count / data.total_articles) * 100).toFixed(0)}%
                </td>
                <td>
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{
                        width: `${(count / data.total_articles) * 100}%`,
                        background: leanColor(lean as LeanLabel),
                      }}
                    />
                  </div>
                </td>
              </tr>
            ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: 28, fontSize: 15 }}>By outlet</h3>
      <table>
        <thead>
          <tr>
            <th>outlet</th>
            <th className="num">articles</th>
            <th className="num">share</th>
          </tr>
        </thead>
        <tbody>
          {data.by_source.slice(0, 25).map((row) => (
            <tr key={row.id}>
              <td>{row.name}</td>
              <td className="num">{row.count}</td>
              <td className="num">{(row.share * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: 28, fontSize: 15 }}>By country</h3>
      <p style={{ fontSize: 14, color: "var(--muted)" }}>
        {Object.entries(data.by_country)
          .sort((a, b) => b[1] - a[1])
          .map(([country, n]) => `${country} ${((n / data.total_articles) * 100).toFixed(0)}%`)
          .join("  ·  ")}
      </p>
    </section>
  );
}
