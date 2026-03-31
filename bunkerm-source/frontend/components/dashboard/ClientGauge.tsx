'use client'

/**
 * Semi-circular gauge with a non-linear scale:
 *   0 → 100 → 500 → 1 000 → 5 000 → 10 000
 * Each segment occupies an equal arc (36°) of the 180° half-circle.
 */

const BREAKPOINTS = [0, 100, 500, 1000, 5000, 10000]
const NUM_SEGMENTS = BREAKPOINTS.length - 1   // 5
const SEGMENT_DEGREES = 180 / NUM_SEGMENTS    // 36° each

const SEGMENT_COLORS = ['#22c55e', '#84cc16', '#eab308', '#f97316', '#ef4444']

// Map a client value to a 0-1 fraction along the arc
function valueToFraction(value: number): number {
  const clamped = Math.max(0, Math.min(value, BREAKPOINTS[BREAKPOINTS.length - 1]))
  for (let i = 0; i < NUM_SEGMENTS; i++) {
    const lo = BREAKPOINTS[i]
    const hi = BREAKPOINTS[i + 1]
    if (clamped <= hi) {
      const segFraction = (clamped - lo) / (hi - lo)
      return (i + segFraction) / NUM_SEGMENTS
    }
  }
  return 1
}

// Convert a 0-1 fraction to SVG (x,y) on the arc
// Arc goes from 180° (left) to 0° (right) counter-clockwise
// fraction 0 → left end  (180°),  fraction 1 → right end (0°)
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
  total: number
  maximum: number
}

export default function ClientGauge({ connected, total, maximum }: Props) {
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
    const startFrac = i / NUM_SEGMENTS
    const endFrac = (i + 1) / NUM_SEGMENTS
    const p1 = fractionToXY(startFrac, outerR, cx, cy)
    const p2 = fractionToXY(endFrac, outerR, cx, cy)
    const p3 = fractionToXY(endFrac, innerR, cx, cy)
    const p4 = fractionToXY(startFrac, innerR, cx, cy)
    // large-arc-flag: 0 (each segment < 180°)
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
  const needleFrac = valueToFraction(connected)
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
        {BREAKPOINTS.slice(1, -1).map((_, i) => {
          const frac = (i + 1) / NUM_SEGMENTS
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
        {BREAKPOINTS.map((bp, i) => {
          const frac = i / NUM_SEGMENTS
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
        <text x={cx} y={cy - 20} textAnchor="middle" fontSize={22} fontWeight="bold" fill="currentColor">
          {connected}
        </text>
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize={9} fill="currentColor" fillOpacity={0.55}>
          connected
        </text>
      </svg>

      {/* legend row */}
      <div className="flex gap-4 text-xs text-muted-foreground">
        <span>Total: <strong className="text-foreground">{total}</strong></span>
        <span>Max ever: <strong className="text-foreground">{maximum}</strong></span>
      </div>

      <p className="text-[10px] text-muted-foreground/60 italic">⚠ Non-linear scale</p>
    </div>
  )
}
