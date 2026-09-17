/**
 * One ECharts wrapper, themed from the same tokens as everything else.
 *
 * Registering the theme under a name and passing that name (rather than an
 * inline `theme` object) is what lets a dark-mode switch repaint every chart
 * without remounting it — ECharts re-reads a registered theme on the next
 * render, and remounting would lose the zoom the reader had set.
 */

import ReactECharts from "echarts-for-react";
import * as echarts from "echarts";
import { useEffect, useMemo } from "react";

import { useAppearance } from "@/theme/AppearanceProvider";

const THEME = "video-analysis";

export interface ChartProps {
  option: Record<string, unknown>;
  /** Height in pixels. Charts are sized by their card, never by their data. */
  height?: number;
  /** Announced to screen readers in place of the canvas. */
  label: string;
  onEvents?: Record<string, (params: unknown) => void>;
}

export function Chart({ option, height = 280, label, onEvents }: ChartProps) {
  const { chartTheme, mode } = useAppearance();

  useEffect(() => {
    echarts.registerTheme(THEME, chartTheme);
  }, [chartTheme]);

  // The theme name is stable; `mode` in the key forces the one re-render that
  // a theme change needs, without tearing the instance down.
  const key = useMemo(() => `${THEME}-${mode}`, [mode]);

  return (
    <div role="img" aria-label={label}>
      <ReactECharts
        key={key}
        echarts={echarts}
        theme={THEME}
        option={option}
        notMerge
        lazyUpdate
        style={{ height, width: "100%" }}
        opts={{ renderer: "canvas" }}
        onEvents={onEvents}
      />
    </div>
  );
}
