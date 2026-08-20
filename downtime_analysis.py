import numpy as np
import pandas as pd
  
from capacity_analysis import stage_capacity
from data_generation import CAUSE_COLUMNS

  # Accept either {cause: column} or [(cause, column), ...]
_PAIRS = (list(CAUSE_COLUMNS.items()) if isinstance(CAUSE_COLUMNS, dict)
        else list(CAUSE_COLUMNS))
CAUSE_NAMES = [c for c, _ in _PAIRS]
CAUSE_COLS = [col for _, col in _PAIRS]

PARETO_THRESHOLD = 0.80


def _check_columns(df):
      missing = [c for c in CAUSE_COLS if c not in df.columns]
      assert not missing, f"downtime cause columns missing from data: {missing}"


def downtime_by_cause(df, label="Whole line"):
      """Pareto table: causes ranked by minutes lost, with cumulative share."""
      _check_columns(df)

      n_shifts = len(df)
      planned_total = float(df["planned_time_min"].sum())
      downtime_total = float(df["downtime_min"].sum())

      rows = []
      for cause, col in _PAIRS:
          minutes = float(df[col].sum())
          rows.append(dict(
              scope=label,
              cause=cause,
              total_downtime_min=round(minutes, 0),
              avg_min_per_shift=round(minutes / n_shifts, 2),
              pct_of_downtime=round(100.0 * minutes / downtime_total, 2),
              pct_of_planned_time=round(100.0 * minutes / planned_total, 2),
          ))

      table = pd.DataFrame(rows).sort_values(
          "total_downtime_min", ascending=False).reset_index(drop=True)
      table["cumulative_pct"] = table["pct_of_downtime"].cumsum().round(2)
      table["pareto_rank"] = np.arange(1, len(table) + 1)

      # The parts must add up to the recorded whole
      assert abs(table["total_downtime_min"].sum() - downtime_total) < max(
          1.0, 0.0001 * downtime_total), "cause minutes do not sum to total downtime"
      return table


def pareto_verdict(pareto_table, threshold=PARETO_THRESHOLD):
      """State what the Pareto curve actually shows, without forcing 80/20."""
      target = 100.0 * threshold
      reached = pareto_table[pareto_table["cumulative_pct"] >= target]
      n_needed = int(reached["pareto_rank"].iloc[0]) if len(reached) else len(pareto_table)
      n_total = len(pareto_table)
      top_causes = list(pareto_table["cause"].head(n_needed))
      top_share = float(pareto_table["cumulative_pct"].iloc[n_needed - 1])
      causes_share_pct = 100.0 * n_needed / n_total

      verdict = (
          f"{n_needed} of {n_total} causes ({causes_share_pct:.0f}% of the cause list) "
          f"account for {top_share:.1f}% of downtime: {', '.join(top_causes)}. "
      )
      if n_needed <= 2:
          verdict += "The losses are highly concentrated, so a narrow countermeasure list is enough."
      elif n_needed >= 4:
          verdict += ("The losses are spread out rather than concentrated, so no single fix "
                      "will recover most of the downtime.")
      else:
          verdict += "The losses are moderately concentrated."

      return dict(
          causes_needed=n_needed,
          causes_total=n_total,
          top_causes=top_causes,
          cumulative_share_pct=round(top_share, 2),
          largest_cause=str(pareto_table["cause"].iloc[0]),
          largest_cause_share_pct=float(pareto_table["pct_of_downtime"].iloc[0]),
          verdict=verdict,
      )

  
def downtime_by_stage(df):
      """Total and per-shift downtime for each stage, in flow order."""
      _check_columns(df)
      rows = []
      for (stage_index, stage), g in df.groupby(["stage_index", "stage"], sort=True):
          planned = float(g["planned_time_min"].sum())
          downtime = float(g["downtime_min"].sum())
          rows.append(dict(
              stage_index=stage_index,
              stage=stage,
              total_downtime_min=round(downtime, 0),
              avg_min_per_shift=round(downtime / len(g), 2),
              downtime_pct_of_planned=round(100.0 * downtime / planned, 2),
              largest_cause=max(_PAIRS, key=lambda p: g[p[1]].sum())[0],
          ))
      return pd.DataFrame(rows).sort_values("stage_index").reset_index(drop=True)


def cause_by_stage_matrix(df, as_percent=True):
      """Cause-by-stage grid, for the heatmap. Percentages are within each stage."""
      _check_columns(df)
      grouped = df.groupby(["stage_index", "stage"])[CAUSE_COLS].sum()
      grouped = grouped.sort_index(level="stage_index")
      grouped.columns = CAUSE_NAMES
      if as_percent:
          grouped = grouped.div(grouped.sum(axis=1), axis=0).mul(100.0).round(2)
      grouped.index = grouped.index.get_level_values("stage")
      return grouped.reset_index()


def bottleneck_downtime_cost(df, stage_table=None):
      """Translate the bottleneck's downtime causes into units of lost output.

      Design basis   : minutes x 60 / ideal cycle time -- ties to the loss
                       decomposition in bottleneck_analysis.py.
      Realistic basis: design basis x Performance x Quality -- what would
                       actually have been produced and sold, since the stage
                       does not run at design speed with zero defects.
      """
      stages = stage_capacity(df) if stage_table is None else stage_table
      bn = stages.sort_values("effective_capacity_per_day").iloc[0]
      stage_name = str(bn["stage"])

      subset = df[df["stage"] == stage_name]
      n_days = int(df["production_date"].nunique())
      ideal_cycle = float(bn["ideal_cycle_time_sec"])
      units_per_minute = 60.0 / ideal_cycle
      realisation = float(bn["performance"]) * float(bn["quality"])

      pareto = downtime_by_cause(subset, label=stage_name)
      pareto["design_units_lost_per_day"] = (
          pareto["total_downtime_min"] * units_per_minute / n_days).round(0)
      pareto["saleable_units_lost_per_day"] = (
          pareto["design_units_lost_per_day"] * realisation).round(0)
      pareto["saleable_units_lost_per_year"] = (
          pareto["saleable_units_lost_per_day"] * n_days).round(0)

      # Cross-check against the availability loss computed from OEE
      expected = float(bn["theoretical_capacity_per_day"]) * (1.0 - float(bn["availability"]))
      actual = float(pareto["design_units_lost_per_day"].sum())
      assert abs(actual - expected) <= max(5.0, 0.01 * expected), (
          f"downtime-to-units conversion ({actual:,.0f}/day) disagrees with the "
          f"OEE availability loss ({expected:,.0f}/day)")

      return pareto, stage_name
def pareto_comparison(line_pareto, bottleneck_pareto, stage_name):
      """Does the line-wide ranking point at the same cause as the bottleneck?"""
      line_top = str(line_pareto["cause"].iloc[0])
      bn_top = str(bottleneck_pareto["cause"].iloc[0])
      line_rank_of_bn_top = int(
          line_pareto.loc[line_pareto["cause"] == bn_top, "pareto_rank"].iloc[0])

      if line_top == bn_top:
          verdict = (f"Both rankings agree: {bn_top} is the largest downtime cause line-wide "
                     f"and at the bottleneck ({stage_name}), so it is the clear first target.")
      else:
          verdict = (
              f"The rankings disagree. Line-wide, the biggest cause is {line_top}, but at the "
              f"bottleneck ({stage_name}) it is {bn_top} -- which ranks only #"
              f"{line_rank_of_bn_top} line-wide. Fixing {line_top} would mostly recover time at "
              f"stages that already have spare capacity, so {bn_top} is the target that "
              f"actually raises line output.")

      return dict(line_top_cause=line_top, bottleneck_top_cause=bn_top,
                  rankings_agree=bool(line_top == bn_top), verdict=verdict)


def changeover_analysis(df, stage_table=None):
      """Changeover / setup time: how much, where, and what it costs at the constraint."""
      changeover_col = dict(_PAIRS).get("Changeover/Setup")
      if changeover_col is None:
          # fall back to whichever cause name mentions changeover
          changeover_col = next(col for cause, col in _PAIRS
                                if "changeover" in cause.lower() or "setup" in cause.lower())

      stages = stage_capacity(df) if stage_table is None else stage_table
      bn = stages.sort_values("effective_capacity_per_day").iloc[0]
      stage_name = str(bn["stage"])
      n_days = int(df["production_date"].nunique())

      total = float(df[changeover_col].sum())
      bn_subset = df[df["stage"] == stage_name]
      bn_total = float(bn_subset[changeover_col].sum())

      units_per_minute = 60.0 / float(bn["ideal_cycle_time_sec"])
      realisation = float(bn["performance"]) * float(bn["quality"])

      per_stage = df.groupby("stage")[changeover_col].agg(["sum", "mean"]).round(2)
      per_stage.columns = ["total_changeover_min", "avg_changeover_min_per_shift"]

      return dict(
          line_total_changeover_min=round(total, 0),
          line_changeover_pct_of_downtime=round(100.0 * total / float(df["downtime_min"].sum()), 2),
          line_changeover_pct_of_planned=round(100.0 * total / float(df["planned_time_min"].sum()), 2),
          bottleneck_stage=stage_name,
          bottleneck_changeover_min_total=round(bn_total, 0),
          bottleneck_changeover_min_per_shift=round(float(bn_subset[changeover_col].mean()), 2),
          bottleneck_changeover_min_per_day=round(bn_total / n_days, 2),
          bottleneck_saleable_units_lost_per_day=round(
              bn_total / n_days * units_per_minute * realisation, 0),
          bottleneck_saleable_units_lost_per_year=round(
              bn_total * units_per_minute * realisation, 0),
          by_stage=per_stage.reset_index(),
      )

  
def breakdown_metrics(df, by="stage"):
      """Breakdown frequency and mean repair duration, per stage or per machine."""
      breakdown_col = dict(_PAIRS).get("Equipment Breakdown", CAUSE_COLS[0])
      keys = ["stage_index", "stage"] if by == "stage" else ["stage_index", "stage", "machine_id"]

      rows = []
      for key, g in df.groupby(keys, sort=True):
          events = float(g["breakdown_count"].sum())
          minutes = float(g[breakdown_col].sum())
          operating = float(g["operating_time_min"].sum())

          record = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
          record.update(
              breakdown_events=int(events),
              breakdowns_per_shift=round(float(g["breakdown_count"].mean()), 2),
              breakdown_downtime_min=round(minutes, 0),
              mean_min_per_breakdown=round(minutes / events, 1) if events > 0 else np.nan,
              running_min_per_breakdown=round(operating / events, 1) if events > 0 else np.nan,
          )
          rows.append(record)
      out = pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)
      return out.drop(columns=["stage_index"])


def monthly_downtime_trend(df):
      """Average downtime minutes per shift by month and cause, for the trend chart."""
      _check_columns(df)
      d = df.copy()
      d["year_month"] = pd.to_datetime(d["production_date"]).dt.to_period("M").astype(str)
      trend = d.groupby("year_month")[CAUSE_COLS].mean().round(2)
      trend.columns = CAUSE_NAMES
      trend["Total"] = trend.sum(axis=1).round(2)
      return trend.reset_index()

  
if __name__ == "__main__":
      import data_generation

      data = data_generation.load()
      stages = stage_capacity(data)
  
      print("=" * 100)
      print("PARETO OF DOWNTIME CAUSES -- WHOLE LINE")
      print("=" * 100)
      line = downtime_by_cause(data)
      print(line[["pareto_rank", "cause", "total_downtime_min", "avg_min_per_shift",
                  "pct_of_downtime", "cumulative_pct"]].to_string(index=False))
      print("\n  " + pareto_verdict(line)["verdict"])

      print("\n" + "=" * 100)
      bn_pareto, bn_stage = bottleneck_downtime_cost(data, stages)
      print(f"PARETO OF DOWNTIME CAUSES -- AT THE BOTTLENECK ({bn_stage})")
      
      print("\n" + "=" * 100)
      bn_pareto, bn_stage = bottleneck_downtime_cost(data, stages)
      print(f"PARETO OF DOWNTIME CAUSES -- AT THE BOTTLENECK ({bn_stage})")
      print("=" * 100)
      print(bn_pareto[["pareto_rank", "cause", "total_downtime_min", "pct_of_downtime",
                       "cumulative_pct", "saleable_units_lost_per_day",
                       "saleable_units_lost_per_year"]].to_string(index=False))
      print("\n  " + pareto_verdict(bn_pareto)["verdict"])
      
      print("\n" + "=" * 100)
      print("DOES THE LINE-WIDE PARETO POINT AT THE RIGHT TARGET?")
      print("=" * 100)
      print("  " + pareto_comparison(line, bn_pareto, bn_stage)["verdict"])
      
      print("\n" + "=" * 100)
      print("DOWNTIME BY STAGE")
      print("=" * 100)
      print(downtime_by_stage(data).to_string(index=False))
      
      print("\n" + "=" * 100)
      print("CAUSE MIX WITHIN EACH STAGE (% of that stage's downtime)")
      print("=" * 100)
      print(cause_by_stage_matrix(data).to_string(index=False))
      
      print("\n" + "=" * 100)
      print("CHANGEOVER / SETUP TIME")
      print("=" * 100)
      co = changeover_analysis(data, stages)
      print(f"  Line changeover time        : {co['line_total_changeover_min']:,.0f} min "
            f"({co['line_changeover_pct_of_downtime']:.1f}% of all downtime, "
            f"{co['line_changeover_pct_of_planned']:.1f}% of planned time)")
      print(f"  At the bottleneck ({co['bottleneck_stage']})   : "
            f"{co['bottleneck_changeover_min_per_shift']:.1f} min/shift, "
            f"{co['bottleneck_changeover_min_per_day']:.1f} min/day")
      print(f"  Saleable output forgone     : "
            f"{co['bottleneck_saleable_units_lost_per_day']:,.0f} units/day, "
            f"{co['bottleneck_saleable_units_lost_per_year']:,.0f} units/year")
      
      print("\n" + "=" * 100)
      print("BREAKDOWN FREQUENCY AND DURATION BY STAGE")
      print("=" * 100)
      print(breakdown_metrics(data).to_string(index=False))
      
      print("\n" + "=" * 100)
      print("MONTHLY DOWNTIME TREND (avg minutes per shift)")
      print("=" * 100)
      print(monthly_downtime_trend(data).to_string(index=False))