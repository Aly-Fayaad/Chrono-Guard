import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Table2, LineChart as LineChartIcon } from "lucide-react";
import type { DetectionResult, HealthMeasurement, MetricType } from "../../shared/types";
import { buildBaseline } from "../../anomaly/baseline";
import { DEFAULT_CONFIG } from "../../anomaly/detector";
import { METRICS } from "../config";
import { metDay, metStamp } from "../lib/time";
import { fmtSigma } from "../lib/format";
import { Panel } from "./Panel";
import { SegmentedControl } from "./SegmentedControl";
import { StatusBadge, DETECTION_BADGE } from "./StatusBadge";

type Range = "7" | "14" | "30";

interface ChartPoint {
  day: string;
  ts: string;
  value: number | null;
  anomaly: number | null;
  invalid: number | null;
  deviation: number;
  quality: string;
}

function ChartTooltip({
  active,
  payload,
  unit,
}: {
  active?: boolean;
  payload?: { payload?: ChartPoint }[];
  unit: string;
}) {
  const p = payload?.[0]?.payload;
  if (!active || !p) return null;
  return (
    <div className="rounded-panel border border-hairline bg-raised px-3 py-2 font-mono text-[11px] leading-relaxed">
      <p className="text-regolith">{metStamp(p.ts)}</p>
      <p className="text-moonlight">
        {p.value ?? p.invalid ?? "—"} <span className="text-regolith">{unit}</span>
      </p>
      <p className={p.anomaly !== null ? "text-review" : "text-earth"}>
        {p.anomaly !== null ? fmtSigma(p.deviation) : `dev ${fmtSigma(p.deviation)}`}
      </p>
      <p className="text-ink">{p.quality === "valid" ? "quality: valid" : `quality: ${p.quality}`}</p>
    </div>
  );
}

/**
 * Personal-baseline chart: metric series against the crew member's own
 * median and ±z robust-deviation band. Anomaly points are filled orange
 * dots with a ring; quality-excluded readings are hollow slate dots.
 * Includes a "View as table" accessibility fallback.
 */
export function BaselineChartPanel({
  metric,
  series,
  detection,
}: {
  metric: MetricType;
  series: HealthMeasurement[];
  detection: DetectionResult;
}) {
  const [range, setRange] = useState<Range>("14");
  const [asTable, setAsTable] = useState(false);
  const meta = METRICS[metric];
  const zt = DEFAULT_CONFIG.zThreshold;

  const { points, baseline } = useMemo(() => {
    const sorted = [...series].sort((a, b) => a.recordedAt.localeCompare(b.recordedAt));
    const bl = buildBaseline(sorted.slice(0, -DEFAULT_CONFIG.trendWindow));
    const sliced = sorted.slice(-Number(range));
    const pts: ChartPoint[] = sliced.map((m) => {
      const deviation = bl ? (m.value - bl.median) / bl.scale : 0;
      const valid = m.quality === "valid";
      const anomaly = valid && bl && Math.abs(deviation) >= zt;
      return {
        day: metDay(m.recordedAt),
        ts: m.recordedAt,
        value: valid ? m.value : null,
        anomaly: anomaly ? m.value : null,
        invalid: valid ? null : m.value,
        deviation,
        quality: m.quality,
      };
    });
    return { points: pts, baseline: bl };
  }, [series, range, zt]);

  const band = baseline ? zt * baseline.scale : 0;
  const badge = DETECTION_BADGE[detection.status];

  return (
    <Panel
      label={`Baseline — ${meta.label}`}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setAsTable((v) => !v)}
            aria-pressed={asTable}
            className="motion-fade inline-flex min-h-[36px] items-center gap-1.5 rounded border border-hairline px-2.5 text-[11px] text-regolith hover:text-moonlight"
          >
            {asTable ? <LineChartIcon size={12} aria-hidden /> : <Table2 size={12} aria-hidden />}
            {asTable ? "View as chart" : "View as table"}
          </button>
          <SegmentedControl<Range>
            options={[
              { value: "7", label: "7d" },
              { value: "14", label: "14d" },
              { value: "30", label: "30d" },
            ]}
            value={range}
            onChange={setRange}
            ariaLabel="Chart time range"
            size="sm"
          />
        </div>
      }
    >
      {asTable ? (
        <div className="max-h-72 overflow-auto rounded border border-hairline">
          <table className="tnum w-full text-left text-[12px]">
            <caption className="px-3 py-2 text-left label-eyebrow">
              {meta.label} readings, last {range} days
            </caption>
            <thead className="bg-raised text-regolith">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Time (MET)</th>
                <th scope="col" className="px-3 py-2 font-medium">Value</th>
                <th scope="col" className="px-3 py-2 font-medium">Deviation</th>
                <th scope="col" className="px-3 py-2 font-medium">Quality</th>
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((p) => (
                <tr key={p.ts} className="border-t border-hairline">
                  <td className="px-3 py-1.5 text-regolith">{metStamp(p.ts)}</td>
                  <td className="px-3 py-1.5 text-moonlight">
                    {p.value ?? p.invalid ?? "—"} {meta.unit}
                  </td>
                  <td className={`px-3 py-1.5 ${Math.abs(p.deviation) >= zt ? "text-review" : "text-earth"}`}>
                    {fmtSigma(p.deviation)}
                  </td>
                  <td className={`px-3 py-1.5 ${p.quality === "valid" ? "text-nominal" : "text-ink"}`}>
                    {p.quality}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          className="h-64 w-full"
          role="img"
          aria-label={`${meta.label} over the last ${range} days with personal baseline. ${badge.label}.`}
        >
          <ResponsiveContainer>
            <LineChart data={points} margin={{ top: 8, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="rgba(200,215,230,0.10)" vertical={false} />
              <XAxis
                dataKey="day"
                tick={{ fontSize: 10, fill: "#8A96A3", fontFamily: "IBM Plex Mono, monospace" }}
                stroke="rgba(200,215,230,0.15)"
                interval="preserveStartEnd"
                minTickGap={28}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fontSize: 10, fill: "#8A96A3", fontFamily: "IBM Plex Mono, monospace" }}
                width={38}
                stroke="rgba(200,215,230,0.15)"
              />
              <Tooltip content={<ChartTooltip unit={meta.unit} />} cursor={{ stroke: "rgba(200,215,230,0.2)" }} />
              {baseline && (
                <>
                  <ReferenceArea
                    y1={baseline.median - band}
                    y2={baseline.median + band}
                    fill="rgba(242,107,58,0.05)"
                    stroke="none"
                  />
                  <ReferenceLine
                    y={baseline.median}
                    stroke="#8A96A3"
                    strokeDasharray=""
                    label={{ value: "median", fontSize: 10, fill: "#8A96A3", position: "insideLeft" }}
                  />
                  <ReferenceLine y={baseline.median + band} stroke="#F26B3A" strokeDasharray="5 4" strokeOpacity={0.8} />
                  <ReferenceLine y={baseline.median - band} stroke="#F26B3A" strokeDasharray="5 4" strokeOpacity={0.8} />
                </>
              )}
              <Line dataKey="value" stroke="#4C9AFF" strokeWidth={1.8} dot={{ r: 2, fill: "#4C9AFF", strokeWidth: 0 }} connectNulls={false} isAnimationActive={false} />
              <Line dataKey="anomaly" stroke="none" dot={{ r: 4, fill: "#F26B3A", stroke: "#E8EDF2", strokeWidth: 1.5 }} connectNulls={false} isAnimationActive={false} />
              <Line dataKey="invalid" stroke="none" dot={{ r: 3.5, fill: "#0A0E14", stroke: "#6B7684", strokeWidth: 1.5 }} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Anomaly explanation card */}
      <div className="mt-4 flex flex-col gap-1.5 rounded-panel border border-hairline bg-raised p-3.5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge variant={badge.variant} label={badge.label} />
          {detection.event && (
            <span className="font-mono text-[11px] uppercase tracking-wider text-regolith">
              {detection.event.kind}
            </span>
          )}
        </div>
        <p className="text-[12px] leading-relaxed text-regolith">
          {detection.event?.explanation ?? detection.reason ?? "Readings are being compared against your personal baseline (median and robust deviation)."}
        </p>
      </div>
    </Panel>
  );
}
