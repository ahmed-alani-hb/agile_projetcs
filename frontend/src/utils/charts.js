// Chart vocabulary — one system across every dashboard.
//
// These colours are not taste. They were run through a palette validator and
// the numbers below are its output; if you change a hex, re-run it rather than
// eyeballing the result.
//
// Why a *sequential* ramp rather than the board's status colours: the six agile
// statuses are an ordered workflow, not unrelated identities, and the board
// palette fails badly here — gray-400 reads as "no data", and Blocked (red)
// against Done (green) scores ΔE 7.4 for deuteranopes while sitting adjacent in
// a stack. That is exactly the pair a delivery chart most needs to separate.
//
// Why four bands and not six: a five-step single-hue ramp cannot hold ΔE ≥ 15
// between every adjacent pair across a usable lightness range. Rather than
// invent hues, the flow chart collapses to the four states a rollout actually
// steers on. Full six-status detail still exists — as a *bar* chart, where
// whitespace and direct labels carry identity instead of colour.

// Sequential indigo, light → dark, plus the reserved status red for Blocked.
// Validated (light, surface #fcfcfb):
//   CVD separation      worst adjacent ΔE 21.9 (protan) · 20.9 (tritan)   PASS
//   Normal-vision floor worst adjacent ΔE 22.4                            PASS
//   Contrast           #a5b4fc at 1.94:1 — under 3:1, so the legend is
//                      always present and a table view is offered. That is
//                      the required relief, not an optional nicety.
export const FLOW_COLORS = ['#a5b4fc', '#6366f1', '#312e81', '#dc2626']

// One hue for single-series magnitude. Same accent the rest of the app uses.
export const ACCENT = '#6366f1'
export const ACCENT_MUTED = '#a5b4fc'

// The workflow collapsed to what a rollout steers on. Order matters: it is the
// stacking order, and Blocked sits last because it is an exception, not a stage.
export const FLOW_BANDS = [
  { key: 'not_started', label: 'Not started', statuses: ['Backlog', 'To Do'] },
  { key: 'in_progress', label: 'In progress', statuses: ['In Progress', 'QA/Code Review'] },
  { key: 'done', label: 'Done', statuses: ['Done'] },
  { key: 'blocked', label: 'Blocked', statuses: ['Blocked'] },
]

/** Collapse a per-status count map into the four flow bands. */
export function toFlowBands(counts) {
  const out = {}
  for (const band of FLOW_BANDS) {
    out[band.key] = band.statuses.reduce((sum, status) => sum + (Number(counts[status]) || 0), 0)
  }
  return out
}

// AxisChart reads each point as `row[series.name]` — the series name IS the
// data key. These helpers own that mapping so a call site cannot get it wrong
// and silently render an empty chart.
const CATEGORY = 'label'

function shape(rows, seriesName) {
  return rows.map((row) => ({ [CATEGORY]: row.label, [seriesName]: row.value }))
}

/** Horizontal bars: magnitude, one hue, identity carried by the label.
 *  `rows` is [{label, value}]. */
export function magnitudeBars({ title, rows, seriesName, subtitle }) {
  return {
    title,
    subtitle,
    data: shape(rows, seriesName),
    colors: [ACCENT],
    swapXY: true,
    xAxis: { key: CATEGORY, type: 'category' },
    yAxis: { title: seriesName },
    series: [{ name: seriesName, type: 'bar', showDataLabels: true }],
  }
}

/** A single measure over time. Never paired with a second scale on one axis —
 *  two measures of different scale get two charts. */
export function trendColumns({ title, rows, seriesName, subtitle }) {
  return {
    title,
    subtitle,
    data: shape(rows, seriesName),
    colors: [ACCENT],
    xAxis: { key: CATEGORY, type: 'category' },
    yAxis: { title: seriesName },
    series: [{ name: seriesName, type: 'bar' }],
  }
}

export function formatDays(value) {
  if (value === null || value === undefined) return '—'
  const days = Number(value)
  if (!Number.isFinite(days)) return '—'
  return days === 1 ? '1 day' : `${Math.round(days * 10) / 10} days`
}
