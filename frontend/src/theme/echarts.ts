/**
 * The ECharts theme, from the same tokens as everything else.
 *
 * A chart themed independently of the application around it is a chart whose
 * grid lines are a slightly different grey from the table beside it — and that
 * difference is visible precisely where a reader is comparing the two.
 */

import { DENSITY, FONT, INK, NEUTRAL, PAPER, SERIES, type Density } from "./tokens";

export function buildChartTheme(mode: "light" | "dark", density: Density) {
  const dark = mode === "dark";
  const text = dark ? INK[300] : NEUTRAL[600];
  const axis = dark ? INK[650] : NEUTRAL[200];
  const scale = DENSITY[density];

  return {
    color: [...SERIES],
    backgroundColor: "transparent",
    textStyle: { fontFamily: FONT.family, fontSize: scale.fontSize - 1, color: text },
    title: {
      textStyle: { color: dark ? INK[100] : NEUTRAL[900], fontWeight: 600 },
      subtextStyle: { color: dark ? INK[400] : NEUTRAL[500] },
    },
    grid: { left: 8, right: 8, top: 24, bottom: 8, containLabel: true },
    categoryAxis: {
      axisLine: { lineStyle: { color: axis } },
      axisTick: { show: false },
      axisLabel: { color: text },
      // No vertical grid lines: they add ink without adding information on a
      // category axis, and the bars already mark the categories.
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: text },
      splitLine: { lineStyle: { color: axis, type: "dashed" } },
    },
    legend: {
      textStyle: { color: text },
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 10,
    },
    tooltip: {
      backgroundColor: dark ? INK[750] : PAPER,
      borderColor: axis,
      borderWidth: 1,
      textStyle: { color: dark ? INK[100] : NEUTRAL[900], fontSize: scale.fontSize },
      axisPointer: { lineStyle: { color: dark ? INK[500] : NEUTRAL[400] }, crossStyle: { color: dark ? INK[500] : NEUTRAL[400] } },
    },
    line: { smooth: false, symbolSize: 6, lineStyle: { width: 2 } },
    bar: { itemStyle: { borderRadius: [3, 3, 0, 0] } },
    pie: {
      itemStyle: { borderColor: dark ? INK[800] : PAPER, borderWidth: 2 },
      label: { color: text },
    },
  };
}

export const CHART_THEME_NAME = "nucleus";
