'use client'

/**
 * Semi-circular gauge with a non-linear scale.
 * Breakpoints adapt to the configured maximum: proportions are always
 * [0%, 1%, 5%, 10%, 50%, 100%] of `maxAllowed` (default 10 000).
 * e.g. max=10000 → [0, 100, 500, 1000, 5000, 10000]
 *      max=5000  → [0,  50, 250,  500, 2500,  5000]
 */

const PROPORTIONS = [0, 0.01, 0.05, 0.10, 0.50, 1.0]
const SEGMENT_COLORS = ['#22c55e', '#84cc16', '#eab308', '#f97316', '#ef4444']

function computeBreakpoints(maxAllowed: number): number[] {
  return PROPORTIONS.map(p => Math.round(p * maxAllowed))
}

// Map a client value to a 0-1 fraction along the arc
function valueToFraction(value: number, breakpoints: number[]): number {
  const numSegments = breakpoints.length - 1
  const clamped = Math.max(0, Math.min(value, breakpoints[numSegments]))
  for (let i = 0; i < numSegments; i++) {
    const lo = breakpoints[i]
    const hi = breakpoints[i + 1]
    if (clamped <= hi) {
      const segFraction = (clamped - lo) / (hi - lo)
      return (i + segFraction) / numSegments
    }
  }
  return 1
}

// Convert a 0-1 fraction to SVG (x,y) on the arc
// fraction 0 → left end (180°),  fraction 1 → right end (0°)
function fractionToXY(fraction: number, r: number, cx: number, cy: number) {
  const angleDeg = 180 - fraction * 180
  const rad = (angleDeg * Math.PI) / 180
  return {
    x: cx + r * Math.cos(rad),
    y: cy - r * Math.sin(rad),
  }
}

function formatLabel(val: number): string {
  if (val >= 1000) return `${val / 1000}k`
  return String(val)
}

interface Props {
  connected: number
  maxAllowed?: number
}

export default function ClientGauge({ connected, maxAllowed = 10000 }: Props) {
  const breakpoints = computeBreakpoints(maxAllowed)
  const numSegments = breakpoints.length - 1

  const W = 280
  const H = 160
  const cx = W / 2
  const cy = H - 20          // baseline near bottom
  const outerR = 120
  const innerR = 78
  const needleR = 110
  const labelR = outerR + 14

  // Build arc paths for each coloured segment
  const segments = SEGMENT_COLORS.map((color, i) => {
    const startFrac = i / numSegments
    const endFrac = (i + 1) / numSegments
    const p1 = fractionToXY(startFrac, outerR, cx, cy)
    const p2 = fractionToXY(endFrac, outerR, cx, cy)
    const p3 = fractionToXY(endFrac, innerR, cx, cy)
    const p4 = fractionToXY(startFrac, innerR, cx, cy)
    return (
      <path
        key={i}
        d={`M ${p1.x} ${p1.y} A ${outerR} ${outerR} 0 0 0 ${p2.x} ${p2.y} L ${p3.x} ${p3.y} A ${innerR} ${innerR} 0 0 1 ${p4.x} ${p4.y} Z`}
        fill={color}
        opacity={0.85}
      />
    )
  })

  // Needle pointing at `connected` value
  const needleFrac = valueToFraction(connected, breakpoints)
  const np = fractionToXY(needleFrac, needleR, cx, cy)
  const baseL = fractionToXY(needleFrac - 0.04, innerR - 10, cx, cy)
  const baseR = fractionToXY(needleFrac + 0.04, innerR - 10, cx, cy)

  return (
    <div className="flex flex-col items-center gap-1">
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-label="Client usage gauge">
        {/* background half-circle track */}
        <path
          d={`M ${cx - outerR} ${cy} A ${outerR} ${outerR} 0 0 1 ${cx + outerR} ${cy}`}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.08}
          strokeWidth={outerR - innerR}
        />

        {/* coloured segments */}
        {segments}

        {/* gap lines between segments */}
        {breakpoints.slice(1, -1).map((_, i) => {
          const frac = (i + 1) / numSegments
          const outer = fractionToXY(frac, outerR + 2, cx, cy)
          const inner = fractionToXY(frac, innerR - 2, cx, cy)
          return (
            <line
              key={i}
              x1={outer.x} y1={outer.y}
              x2={inner.x} y2={inner.y}
              stroke="white"
              strokeWidth={1.5}
            />
          )
        })}

        {/* needle */}
        <polygon
          points={`${np.x},${np.y} ${baseL.x},${baseL.y} ${baseR.x},${baseR.y}`}
          fill="#1e293b"
          className="dark:fill-white"
        />
        {/* centre hub */}
        <circle cx={cx} cy={cy} r={8} fill="#1e293b" className="dark:fill-white" />
        <circle cx={cx} cy={cy} r={4} fill="white" className="dark:fill-slate-900" />

        {/* boundary labels */}
        {breakpoints.map((bp, i) => {
          const frac = i / numSegments
          const lp = fractionToXY(frac, labelR, cx, cy)
          return (
            <text
              key={i}
              x={lp.x}
              y={lp.y + 4}
              textAnchor="middle"
              fontSize={9}
              fill="currentColor"
              fillOpacity={0.6}
            >
              {formatLabel(bp)}
            </text>
          )
        })}

        {/* centre reading */}
        <text x={cx} y={cy - 14} textAnchor="middle" fontSize={26} fontWeight="bold" fill="currentColor">
          {connected}
        </text>
      </svg>

      <p className="text-[10px] text-muted-foreground/60 italic">⚠ Non-linear scale</p>
    </div>
  )
}
