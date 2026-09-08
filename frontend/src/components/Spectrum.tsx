import { SPECTRUM, type LeanLabel } from "../lib/types";

const COLOR: Record<LeanLabel, string> = {
  left: "var(--left)",
  "lean-left": "var(--lean-left)",
  center: "var(--center)",
  "lean-right": "var(--lean-right)",
  right: "var(--right)",
  unrated: "var(--unrated)",
};

export function leanColor(lean: LeanLabel): string {
  return COLOR[lean] ?? COLOR.unrated;
}

/**
 * The story's coverage across the spectrum, at a glance.
 *
 * An empty cell is drawn rather than omitted: the absence of coverage is the
 * information. A dashed amber cell means we do poll outlets there and none of
 * them ran it.
 */
export function Spectrum({
  histogram,
  gaps,
  unrated = 0,
}: {
  histogram: Partial<Record<LeanLabel, number>>;
  gaps: LeanLabel[];
  unrated?: number;
}) {
  return (
    <div className="spectrum" role="img" aria-label={describe(histogram, gaps, unrated)}>
      {SPECTRUM.map((lean) => {
        const count = histogram[lean] ?? 0;
        const isGap = gaps.includes(lean);
        return (
          <div
            key={lean}
            className={`cell${count === 0 ? " empty" : ""}${isGap ? " gap" : ""}`}
            style={count > 0 ? { background: leanColor(lean) } : undefined}
            title={`${lean}: ${count} newsroom${count === 1 ? "" : "s"}`}
          >
            {count > 0 ? count : isGap ? "none" : "·"}
          </div>
        );
      })}

      {/* Outlets with no meaningful position on a US left-right axis -- mostly
          international. Shown as a separate trailing cell rather than folded
          into "center", but shown, because a story covered only by
          international outlets would otherwise render as an empty row that
          looks identical to no coverage at all. */}
      {unrated > 0 && (
        <div
          className="cell unrated-cell"
          style={{ background: leanColor("unrated") }}
          title={`${unrated} unrated / international newsroom${unrated === 1 ? "" : "s"}`}
        >
          {unrated} intl
        </div>
      )}
    </div>
  );
}

function describe(
  histogram: Partial<Record<LeanLabel, number>>,
  gaps: LeanLabel[],
  unrated: number,
): string {
  const covered = SPECTRUM.filter((l) => (histogram[l] ?? 0) > 0);
  const parts = [
    covered.length
      ? `Covered by ${covered.map((l) => `${histogram[l]} ${l}`).join(", ")}`
      : "No outlets with a rated position covered this",
  ];
  if (unrated > 0) parts.push(`${unrated} unrated or international newsroom(s)`);
  if (gaps.length) parts.push(`no coverage from ${gaps.join(", ")}`);
  return parts.join("; ") + ".";
}
