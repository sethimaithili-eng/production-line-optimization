import numpy as np
import pandas as pd

from config import CONTROL_CHART_SIGMA, CONTROL_CHART_STAGE
from capacity_analysis import stage_capacity

  # d2 constant for a moving range of two consecutive observations
D2_MOVING_RANGE = 1.128
  
BASELINE_DAYS = 90
RUN_RULE_LENGTH = 8


def _smart_round(x, ndigits=None):
      """Round without destroying small values such as a 0.025 defect rate."""
      if ndigits is not None:
          return round(float(x), ndigits)
      if not np.isfinite(x) or x == 0:
          return float(x)
      magnitude = abs(x)
      if magnitude >= 100:
          return round(float(x), 1)
      if magnitude >= 1:
          return round(float(x), 2)
      if magnitude >= 0.01:
          return round(float(x), 5)
      return float(f"{x:.4g}")
  
  
def daily_stage_series(df, stage):
      """Collapse the shift-level records into one row per production day."""
      subset = df[df["stage"] == stage]
      assert len(subset) > 0, f"stage '{stage}' not found in the data"

      daily = subset.groupby("production_date").agg(
          planned_time_min=("planned_time_min", "sum"),
          operating_time_min=("operating_time_min", "sum"),
          downtime_min=("downtime_min", "sum"),
          units_produced=("units_produced", "sum"),
          good_units=("good_units", "sum"),
          defective_units=("defective_units", "sum"),
      ).reset_index()

      daily["production_date"] = pd.to_datetime(daily["production_date"])
      daily = daily.sort_values("production_date").reset_index(drop=True)
      daily["defect_rate"] = daily["defective_units"] / daily["units_produced"]
      daily["day_number"] = np.arange(1, len(daily) + 1)
      return daily


def _run_rule(values, centre, run_length=RUN_RULE_LENGTH):
      """Flag every point belonging to a run of `run_length` on one side."""
      values = np.asarray(values, dtype=float)
      flags = np.zeros(len(values), dtype=bool)
      side = np.sign(values - centre)

      streak, previous = 0, 0
      for i, s in enumerate(side):
          if s == 0:
              streak, previous = 0, 0
              continue
          streak = streak + 1 if s == previous else 1
          previous = s
          if streak >= run_length:
              flags[i - run_length + 1:i + 1] = True
      return flags


def individuals_chart(daily, value_col, baseline_days=BASELINE_DAYS,
                        sigma=CONTROL_CHART_SIGMA, floor_at_zero=True):
      """Individuals chart with limits fixed from the baseline period."""
      assert len(daily) > baseline_days + RUN_RULE_LENGTH, \
          "not enough production days to establish limits and then monitor"

      values = daily[value_col].to_numpy(dtype=float)
      baseline = values[:baseline_days]

      centre = float(baseline.mean())
      moving_range = np.abs(np.diff(baseline))
      sigma_hat = float(moving_range.mean()) / D2_MOVING_RANGE

      ucl = centre + sigma * sigma_hat
      lcl = centre - sigma * sigma_hat
      if floor_at_zero:
          lcl = max(0.0, lcl)

      chart = daily[["production_date", "day_number", value_col]].copy()
      chart["centre_line"] = centre
      chart["upper_control_limit"] = ucl
      chart["lower_control_limit"] = lcl
      chart["in_baseline"] = chart["day_number"] <= baseline_days
      chart["beyond_limits"] = (values > ucl) | (values < lcl)
      chart["run_of_eight"] = _run_rule(values, centre)
      chart["out_of_control"] = chart["beyond_limits"] | chart["run_of_eight"]

      params = dict(
          metric=value_col,
          chart_type="individuals",
          baseline_days=baseline_days,
          centre_line=_smart_round(centre),
          sigma_estimate=_smart_round(sigma_hat),
          sigma_multiplier=sigma,
          upper_control_limit=_smart_round(ucl),
          lower_control_limit=_smart_round(lcl),
          half_width=_smart_round(sigma * sigma_hat),
          points_total=int(len(chart)),
          points_beyond_limits=int(chart["beyond_limits"].sum()),
          points_in_long_run=int(chart["run_of_eight"].sum()),
          points_out_of_control=int(chart["out_of_control"].sum()),
          out_of_control_pct=round(100.0 * chart["out_of_control"].mean(), 2),
      )
      return chart, params


def p_chart(daily, baseline_days=BASELINE_DAYS, sigma=CONTROL_CHART_SIGMA):
      """Defect-rate p-chart with binomial limits that vary with daily volume.

      Retained deliberately so the overdispersion problem can be demonstrated
      and quantified rather than asserted. See the module docstring.
      """
      baseline = daily.iloc[:baseline_days]
      p_bar = float(baseline["defective_units"].sum() / baseline["units_produced"].sum())

      chart = daily[["production_date", "day_number", "units_produced",
                     "defective_units", "defect_rate"]].copy()
      n = chart["units_produced"].to_numpy(dtype=float)
      spread = sigma * np.sqrt(p_bar * (1.0 - p_bar) / n)

      chart["centre_line"] = p_bar
      chart["upper_control_limit"] = p_bar + spread
      chart["lower_control_limit"] = np.clip(p_bar - spread, 0.0, None)
      chart["in_baseline"] = chart["day_number"] <= baseline_days
      chart["beyond_limits"] = (
          (chart["defect_rate"] > chart["upper_control_limit"]) |
          (chart["defect_rate"] < chart["lower_control_limit"]))
      chart["run_of_eight"] = _run_rule(chart["defect_rate"], p_bar)
      chart["out_of_control"] = chart["beyond_limits"] | chart["run_of_eight"]

      params = dict(
          metric="defect_rate",
          chart_type="p-chart (binomial limits)",
          baseline_days=baseline_days,
          centre_line=_smart_round(p_bar),
          centre_line_pct=round(100.0 * p_bar, 3),
          sigma_multiplier=sigma,
          avg_daily_units=round(float(chart["units_produced"].mean()), 0),
          half_width=_smart_round(float(spread.mean())),
          points_total=int(len(chart)),
          points_beyond_limits=int(chart["beyond_limits"].sum()),
          points_in_long_run=int(chart["run_of_eight"].sum()),
          points_out_of_control=int(chart["out_of_control"].sum()),
          out_of_control_pct=round(100.0 * chart["out_of_control"].mean(), 2),
      )
      return chart, params

  
def overdispersion_check(p_params, individuals_params):
      """Quantify how much the real variation exceeds the binomial assumption."""
      binomial_half_width = float(p_params["half_width"])
      observed_half_width = float(individuals_params["half_width"])
      ratio = observed_half_width / binomial_half_width if binomial_half_width else np.nan

      overdispersed = ratio > 1.5
      if overdispersed:
          verdict = (
              f"Overdispersion confirmed. The binomial p-chart allows the daily defect rate "
              f"to move only +/-{100 * binomial_half_width:.3f} percentage points, but the "
              f"observed day-to-day variation is +/-{100 * observed_half_width:.3f} points -- "
              f"{ratio:.1f} times wider. The p-chart therefore flags "
              f"{p_params['out_of_control_pct']:.1f}% of days as abnormal, against "
              f"{individuals_params['out_of_control_pct']:.1f}% for the individuals chart. "
              f"With {p_params['avg_daily_units']:,.0f} units inspected per day the binomial "
              f"model is too optimistic about how steady the underlying rate is, so the "
              f"individuals chart is the one to act on.")
      else:
          verdict = (
              f"No material overdispersion: observed variation is {ratio:.1f} times the "
              f"binomial expectation, so the p-chart limits are usable.")

      return dict(
          binomial_half_width_pp=round(100 * binomial_half_width, 4),
          observed_half_width_pp=round(100 * observed_half_width, 4),
          dispersion_ratio=round(ratio, 2),
          overdispersed=bool(overdispersed),
          verdict=verdict,
      )

  
def drift_check(chart, value_col, baseline_days=BASELINE_DAYS):
      """Compare the baseline mean with the later period -- has the level moved?"""
      baseline_mean = float(chart.loc[chart["in_baseline"], value_col].mean())
      later_mean = float(chart.loc[~chart["in_baseline"], value_col].mean())
      change_pct = 100.0 * (later_mean / baseline_mean - 1.0) if baseline_mean else np.nan

      return dict(
          metric=value_col,
          baseline_mean=_smart_round(baseline_mean),
          monitoring_mean=_smart_round(later_mean),
          change_pct=round(change_pct, 2),
          direction="higher" if change_pct > 0 else "lower",
      )

  
def stability_verdict(chart, params):
      """Plain-language conclusion about whether the process is in control."""
      pct = params["out_of_control_pct"]
      metric = params["metric"].replace("_", " ")

      if params["points_out_of_control"] == 0:
          return (f"Daily {metric} stayed within its control limits on all "
                  f"{params['points_total']} production days. The variation is common cause, "
                  f"so day-to-day swings should not be investigated individually -- only a "
                  f"change to the process itself will shift the average.")

      parts = []
      if params["points_beyond_limits"]:
          parts.append(f"{params['points_beyond_limits']} day(s) beyond the 3-sigma limits")
      if params["points_in_long_run"]:
          parts.append(f"{params['points_in_long_run']} day(s) inside a run of "
                       f"{RUN_RULE_LENGTH} or more on one side of the centre line")

      return (f"Daily {metric} is NOT in statistical control: {', and '.join(parts)} "
              f"({pct:.1f}% of days). Special-cause variation is present, so part of the "
              f"loss is not inherent to the process and can be removed by finding what "
              f"changed rather than by re-engineering the stage.")


def run_all_charts(df, stage=None):
      """Build every control chart for the chosen stage. Returns a dict."""
      if stage is None:
          stages = stage_capacity(df)
          constraint = stages.sort_values("effective_capacity_per_day").iloc[0]["stage"]
          stage = CONTROL_CHART_STAGE if CONTROL_CHART_STAGE in set(df["stage"]) else constraint

      daily = daily_stage_series(df, stage)

      output_chart, output_params = individuals_chart(daily, "good_units")
      downtime_chart, downtime_params = individuals_chart(daily, "downtime_min")
      defect_ind_chart, defect_ind_params = individuals_chart(daily, "defect_rate")
      defect_p_chart, defect_p_params = p_chart(daily)

      charts = dict(good_units=output_chart, downtime_min=downtime_chart,
                    defect_rate=defect_ind_chart, defect_rate_p_chart=defect_p_chart)
      params = dict(good_units=output_params, downtime_min=downtime_params,
                    defect_rate=defect_ind_params, defect_rate_p_chart=defect_p_params)

      return dict(
          stage=stage,
          daily=daily,
          charts=charts,
          params=params,
          overdispersion=overdispersion_check(defect_p_params, defect_ind_params),
          drift={k: drift_check(charts[k], params[k]["metric"])
                 for k in ["good_units", "downtime_min", "defect_rate"]},
          verdicts={k: stability_verdict(charts[k], params[k]) for k in charts},
      )


if __name__ == "__main__":
      import data_generation

      data = data_generation.load()
      result = run_all_charts(data)

      print("=" * 100)
      print(f"STATISTICAL PROCESS CONTROL -- {result['stage']}")
      print(f"Limits established from the first {BASELINE_DAYS} production days, "
            f"then applied to all days")
      print("=" * 100)
  
      for metric in ["good_units", "downtime_min", "defect_rate"]:
          p = result["params"][metric]
          d = result["drift"][metric]
          print(f"\n--- {metric.replace('_', ' ').upper()} (individuals chart) "
                + "-" * max(0, 55 - len(metric)))
          print(f"  Centre line              : {p['centre_line']:,}")
          print(f"  Sigma estimate (MR/1.128): {p['sigma_estimate']:,}")
          print(f"  Control limits           : {p['lower_control_limit']:,} "
                f"to {p['upper_control_limit']:,}")
          print(f"  Days beyond limits       : {p['points_beyond_limits']} of {p['points_total']}")
          print(f"  Days in a run of {RUN_RULE_LENGTH}+      : {p['points_in_long_run']}")
          print(f"  Out of control           : {p['out_of_control_pct']:.1f}% of days")
          print(f"  Baseline vs later period : {d['baseline_mean']:,} -> "
                f"{d['monitoring_mean']:,} ({d['change_pct']:+.1f}%, {d['direction']})")
          print(f"\n  {result['verdicts'][metric]}")

      print("\n" + "=" * 100)
      print("DEFECT RATE: p-CHART vs INDIVIDUALS CHART")
      print("=" * 100)
      pc = result["params"]["defect_rate_p_chart"]
      ic = result["params"]["defect_rate"]
      print(f"  {'':<26}{'p-chart':>18}{'individuals':>18}")
      print(f"  {'centre line':<26}{pc['centre_line_pct']:>17.3f}%"
            f"{100 * ic['centre_line']:>17.3f}%")
      print(f"  {'limit half-width (pp)':<26}{100 * pc['half_width']:>18.3f}"
            f"{100 * ic['half_width']:>18.3f}")
      print(f"  {'days beyond limits':<26}{pc['points_beyond_limits']:>18}"
            f"{ic['points_beyond_limits']:>18}")
      print(f"  {'out of control (%)':<26}{pc['out_of_control_pct']:>18.1f}"
            f"{ic['out_of_control_pct']:>18.1f}")
      print(f"\n  {result['overdispersion']['verdict']}")

      print("\n" + "=" * 100)
      print("WORST 10 DAYS BY OUTPUT")
      print("=" * 100)
      worst = result["charts"]["good_units"].nsmallest(10, "good_units")
      print(worst[["production_date", "good_units", "lower_control_limit",
                   "beyond_limits", "run_of_eight"]].to_string(index=False))