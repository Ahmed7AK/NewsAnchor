import type { LeanLabel, SourcesRef } from "../lib/types";
import { leanColor } from "./Spectrum";

/**
 * The roster, and how well it covers the spectrum.
 *
 * This panel exists because a feed cannot be more balanced than its inputs.
 * If the roster is lopsided, every "coverage gap" the digest reports is
 * suspect, and the reader deserves to see that directly rather than infer it.
 */
export function SourcesPanel({ data }: { data: SourcesRef }) {
  const counts = Object.entries(data.spectrum) as [LeanLabel, string[]][];
  const widest = Math.max(...counts.map(([, ids]) => ids.length), 1);

  return (
    <section>
      {data.warnings.map((warning) => (
        <p className="notice" key={warning}>
          {warning}
        </p>
      ))}

      <table>
        <thead>
          <tr>
            <th>position</th>
            <th className="num">sources</th>
            <th>coverage</th>
          </tr>
        </thead>
        <tbody>
          {counts.map(([lean, ids]) => (
            <tr key={lean}>
              <td>
                <span
                  className="badge"
                  style={{ background: leanColor(lean) }}
                >
                  {lean}
                </span>
              </td>
              <td className="num">{ids.length}</td>
              <td>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{
                      width: `${(ids.length / widest) * 100}%`,
                      background: leanColor(lean),
                    }}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: 28, fontSize: 15 }}>All sources</h3>
      <table>
        <thead>
          <tr>
            <th>outlet</th>
            <th>position</th>
            <th>country</th>
            <th className="num">feeds</th>
          </tr>
        </thead>
        <tbody>
          {data.sources.map((source) => (
            <tr key={source.id} style={{ opacity: source.enabled ? 1 : 0.45 }}>
              <td>
                <a href={source.homepage} target="_blank" rel="noopener noreferrer">
                  {source.name}
                </a>
                {source.state_affiliated && (
                  <span className="tag state">state-affiliated</span>
                )}
                {!source.enabled && <span className="tag">off</span>}
                {source.feed_count === 0 && <span className="tag">no feed</span>}
              </td>
              <td>
                <span
                  className="badge"
                  style={{ background: leanColor(source.lean_label) }}
                >
                  {source.lean_label}
                </span>
              </td>
              <td>{source.country}</td>
              <td className="num">{source.feed_count}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 20 }}>
        Lean values are a coarse editorial starting point, not licensed ratings,
        and they say nothing about accuracy. Edit them in{" "}
        <code>data/sources.yaml</code> — the app reads that file at runtime.
      </p>
    </section>
  );
}
