import numpy as np
import pandas as pd
  
from config import (
      DOWNTIME_REDUCTION,
      CHANGEOVER_REDUCTION,
      DEFECT_REDUCTION,
      EXTRA_MACHINES,
  )
from capacity_analysis import stage_capacity
from downtime_analysis import CAUSE_NAMES, CAUSE_COLS

MIN_DOWNTIME_FRACTION = 0.03
  
  
def _cause_column(keyword):
      for name, col in zip(CAUSE_NAMES, CAUSE_COLS):
          if keyword in name.lower():
              return col
      raise KeyError(f"no downtime cause matching '{keyword}'")


CHANGEOVER_COL = _cause_column("changeover")
QUALITY_ISSUE_COL = _cause_column("quality")

SCENARIOS = [
      dict(code="A", name="Baseline",
           description="The line as measured, no changes"),
      dict(code="B", name=f"Add {EXTRA_MACHINES} machine at the bottleneck",
           description="More parallel capacity at the constraining stage"),
      dict(code="C", name=f"Cut bottleneck downtime by {DOWNTIME_REDUCTION:.0%}",
           description="Maintenance and response-time focus on the constraint"),
      dict(code="D", name=f"Cut changeover time by {CHANGEOVER_REDUCTION:.0%} (SMED)",
           description="Quick-changeover practice applied line-wide"),
      dict(code="E", name=f"Cut defect rate by {DEFECT_REDUCTION:.0%}",
           description="Fewer defects and fewer quality-related stoppages, line-wide"),
      dict(code="F", name="Combined (B + C + D + E)",
           description="All four interventions together"),
  ]

  
def baseline_model(df):
      """Stage-by-stage model of the line, measured entirely from the data."""
      stages = stage_capacity(df)

      cause_totals = df.groupby("stage")[[CHANGEOVER_COL, QUALITY_ISSUE_COL]].sum()
      downtime_totals = df.groupby("stage")["downtime_min"].sum()

      rows = []
      for _, s in stages.iterrows():
          stage = str(s["stage"])
          machines = int(s["machines"])
          total_downtime = float(downtime_totals.loc[stage])

          rows.append(dict(
              stage_index=int(s["stage_index"]),
              stage=stage,
              machines=machines,
              ideal_cycle_time_sec=float(s["ideal_cycle_time_sec"]),
              planned_min_per_day_per_machine=float(s["available_hours_per_day"]) * 60.0 / machines,
              availability=float(s["availability"]),
              performance=float(s["performance"]),
              quality=float(s["quality"]),
              changeover_share=float(cause_totals.loc[stage, CHANGEOVER_COL]) / total_downtime,
              quality_issue_share=float(cause_totals.loc[stage, QUALITY_ISSUE_COL]) / total_downtime,
          ))
      return pd.DataFrame(rows).sort_values("stage_index").reset_index(drop=True)

  
def evaluate(model):
      """Compute capacity for every stage and find the line's constraint."""
      m = model.copy()
      m["planned_min_per_day"] = m["planned_min_per_day_per_machine"] * m["machines"]
      m["theoretical_capacity_per_day"] = (
          m["planned_min_per_day"] * 60.0 / m["ideal_cycle_time_sec"])
      m["oee"] = m["availability"] * m["performance"] * m["quality"]
      m["effective_capacity_per_day"] = m["theoretical_capacity_per_day"] * m["oee"]
      m["downtime_pct"] = (100.0 * (1.0 - m["availability"])).round(2)

      constraint = m.sort_values("effective_capacity_per_day").iloc[0]
      line_capacity = float(constraint["effective_capacity_per_day"])
      runner_up = m.sort_values("effective_capacity_per_day").iloc[1]

      return m, dict(
          bottleneck_stage=str(constraint["stage"]),
          line_capacity_per_day=line_capacity,
          second_constraint_stage=str(runner_up["stage"]),
          second_constraint_capacity_per_day=float(runner_up["effective_capacity_per_day"]),
          headroom_to_next_constraint_pct=round(
              100.0 * (float(runner_up["effective_capacity_per_day"]) / line_capacity - 1.0), 2),
      )


def _reduce_downtime(model, stages, overall=1.0, changeover=1.0, quality_issue=1.0):
      """Scale downtime components on the named stages and rebuild Availability.

      The three multipliers compose on each cause, so overlapping
      interventions never double-count:

          new downtime = old downtime x overall x
                         ( other_share
                           + changeover x changeover_share
                           + quality_issue x quality_issue_share )
      """
      m = model.copy()
      mask = m["stage"].isin(stages)

      downtime_fraction = 1.0 - m.loc[mask, "availability"]
      co_share = m.loc[mask, "changeover_share"]
      qi_share = m.loc[mask, "quality_issue_share"]
      other_share = 1.0 - co_share - qi_share

      scaled = downtime_fraction * overall * (
          other_share + changeover * co_share + quality_issue * qi_share)
      scaled = scaled.clip(lower=MIN_DOWNTIME_FRACTION)

      m.loc[mask, "availability"] = 1.0 - scaled
      return m
  
  
def _improve_quality(model, stages, defect_multiplier):
      """Scale the defect rate on the named stages and rebuild Quality."""
      m = model.copy()
      mask = m["stage"].isin(stages)
      defect_rate = 1.0 - m.loc[mask, "quality"]
      m.loc[mask, "quality"] = 1.0 - defect_rate * defect_multiplier
      return m


def _add_machines(model, stages, extra):
      m = model.copy()
      mask = m["stage"].isin(stages)
      m.loc[mask, "machines"] = m.loc[mask, "machines"] + extra
      return m

  
def build_scenario(baseline, code, bottleneck_stage, all_stages):
      """Return the modified stage model for one scenario code."""
      if code == "A":
          return baseline.copy()

      if code == "B":
          return _add_machines(baseline, [bottleneck_stage], EXTRA_MACHINES)

      if code == "C":
          return _reduce_downtime(baseline, [bottleneck_stage],
                                  overall=1.0 - DOWNTIME_REDUCTION)

      if code == "D":
          return _reduce_downtime(baseline, all_stages,
                                  changeover=1.0 - CHANGEOVER_REDUCTION)
  
      if code == "E":
          m = _reduce_downtime(baseline, all_stages,
                               quality_issue=1.0 - DEFECT_REDUCTION)
          return _improve_quality(m, all_stages, 1.0 - DEFECT_REDUCTION)

      if code == "F":
          m = _add_machines(baseline, [bottleneck_stage], EXTRA_MACHINES)
          # C applies only at the bottleneck; D and E apply line-wide
          m = _reduce_downtime(m, [bottleneck_stage], overall=1.0 - DOWNTIME_REDUCTION)
          m = _reduce_downtime(m, all_stages,
                               changeover=1.0 - CHANGEOVER_REDUCTION,
                               quality_issue=1.0 - DEFECT_REDUCTION)
          return _improve_quality(m, all_stages, 1.0 - DEFECT_REDUCTION)

      raise ValueError(f"unknown scenario code: {code}")
  

def run_all_scenarios(df):
      """Evaluate every scenario. Returns (summary table, per-scenario stage tables)."""
      baseline = baseline_model(df)
      production_days = int(df["production_date"].nunique())

      base_stages, base_result = evaluate(baseline)
      bottleneck = base_result["bottleneck_stage"]
      all_stages = list(baseline["stage"])

      # Scenario A must reproduce the measured line capacity
      measured = stage_capacity(df)["effective_capacity_per_day"].min()
      assert abs(base_result["line_capacity_per_day"] - measured) <= max(5.0, 0.01 * measured), (
          f"baseline model ({base_result['line_capacity_per_day']:,.0f}) does not reproduce "
          f"the measured line capacity ({measured:,.0f})")

      baseline_capacity = base_result["line_capacity_per_day"]
      rows, stage_tables = [], {}
  
      for spec in SCENARIOS:
          model = build_scenario(baseline, spec["code"], bottleneck, all_stages)
          stages, result = evaluate(model)
          stage_tables[spec["code"]] = stages

          capacity = result["line_capacity_per_day"]
          gain = capacity - baseline_capacity
  
          rows.append(dict(
              scenario=spec["code"],
              name=spec["name"],
              bottleneck_stage=result["bottleneck_stage"],
              constraint_moved=result["bottleneck_stage"] != bottleneck,
              line_capacity_per_day=round(capacity, 0),
              gain_units_per_day=round(gain, 0),
              gain_pct=round(100.0 * gain / baseline_capacity, 2),
              annual_good_units=round(capacity * production_days, 0),
              annual_gain_units=round(gain * production_days, 0),
              bottleneck_oee=round(float(
                  stages.loc[stages["stage"] == result["bottleneck_stage"], "oee"].iloc[0]), 4),
              headroom_to_next_pct=result["headroom_to_next_constraint_pct"],
          ))

      summary = pd.DataFrame(rows)
      assert summary.loc[summary["scenario"] == "A", "gain_pct"].iloc[0] == 0.0, \
          "the baseline scenario must show zero gain"
      return summary, stage_tables


def scenario_insights(summary):
      """Plain-language reading of the scenario table."""
      baseline_bottleneck = str(summary.loc[summary["scenario"] == "A", "bottleneck_stage"].iloc[0])
      improvements = summary[summary["scenario"] != "A"].copy()
      best = improvements.sort_values("gain_pct", ascending=False).iloc[0]
      singles = improvements[improvements["scenario"] != "F"]
      best_single = singles.sort_values("gain_pct", ascending=False).iloc[0]
      moved = improvements[improvements["constraint_moved"]]

      notes = [
          f"Baseline line capacity is {summary.loc[0, 'line_capacity_per_day']:,.0f} good "
          f"units/day, set by {baseline_bottleneck}.",

          f"The largest single-lever gain is scenario {best_single['scenario']} "
          f"({best_single['name']}) at {best_single['gain_pct']:+.1f}% "
          f"({best_single['gain_units_per_day']:+,.0f} units/day).",

          f"The combined scenario reaches {best['gain_pct']:+.1f}% "
          f"({best['annual_gain_units']:+,.0f} units/year), which is less than the sum of the "
          f"individual gains because the constraint moves once the bottleneck is relieved.",
      ]

      if len(moved):
          for _, row in moved.iterrows():
              notes.append(
                  f"In scenario {row['scenario']}, the constraint moves from "
                  f"{baseline_bottleneck} to {row['bottleneck_stage']}. Any further spend on "
                  f"{baseline_bottleneck} alone would add nothing: {row['bottleneck_stage']} "
                  f"now sets the pace.")
      else:
          notes.append(f"{baseline_bottleneck} remains the constraint in every scenario, so "
                       f"improvement there is never wasted within the range modelled.")

      return notes

  
def sweep_downtime_reduction(df, fractions=None):
      """What-if: line capacity as bottleneck downtime is progressively reduced."""
      if fractions is None:
          fractions = np.arange(0.0, 0.85, 0.05)

      baseline = baseline_model(df)
      _, base_result = evaluate(baseline)
      bottleneck = base_result["bottleneck_stage"]
      base_capacity = base_result["line_capacity_per_day"]

      rows = []
      for f in fractions:
          model = _reduce_downtime(baseline, [bottleneck], overall=1.0 - f)
          _, result = evaluate(model)
          rows.append(dict(
              downtime_reduction_pct=round(100.0 * f, 1),
              line_capacity_per_day=round(result["line_capacity_per_day"], 0),
              gain_pct=round(100.0 * (result["line_capacity_per_day"] / base_capacity - 1.0), 2),
              bottleneck_stage=result["bottleneck_stage"],
              still_the_bottleneck=result["bottleneck_stage"] == bottleneck,
          ))
      return pd.DataFrame(rows)

  
def sweep_extra_machines(df, counts=(0, 1, 2, 3, 4)):
      """What-if: line capacity as machines are added at the bottleneck."""
      baseline = baseline_model(df)
      _, base_result = evaluate(baseline)
      bottleneck = base_result["bottleneck_stage"]
      base_capacity = base_result["line_capacity_per_day"]

      rows = []
      for n in counts:
          model = _add_machines(baseline, [bottleneck], n)
          _, result = evaluate(model)
          capacity = result["line_capacity_per_day"]
          rows.append(dict(
              extra_machines=n,
              line_capacity_per_day=round(capacity, 0),
              gain_pct=round(100.0 * (capacity / base_capacity - 1.0), 2),
              bottleneck_stage=result["bottleneck_stage"],
              still_the_bottleneck=result["bottleneck_stage"] == bottleneck,
          ))
      return pd.DataFrame(rows)


def diminishing_returns_point(sweep, gain_col="gain_pct", key_col=None):
      """Find where extra effort stops buying extra output."""
      plateau = sweep[~sweep["still_the_bottleneck"]]
      if not len(plateau):
          return dict(plateau_reached=False, note="the constraint never moves within this range")

      first = plateau.iloc[0]
      key_col = key_col or sweep.columns[0]
      return dict(
          plateau_reached=True,
          at=first[key_col],
          max_useful_gain_pct=float(sweep[sweep["still_the_bottleneck"]][gain_col].max()),
          new_bottleneck=str(first["bottleneck_stage"]),
          note=(f"beyond {key_col.replace('_', ' ')} = {first[key_col]}, the constraint moves to "
                f"{first['bottleneck_stage']} and further effort on the original bottleneck "
                f"adds nothing"),
      )


if __name__ == "__main__":
      import data_generation

      data = data_generation.load()
      summary, stage_tables = run_all_scenarios(data)

      print("=" * 110)
      print("SCENARIO COMPARISON  (all figures computed from the measured stage model)")
      print("=" * 110)
      print(summary[["scenario", "name", "line_capacity_per_day", "gain_units_per_day",
                     "gain_pct", "bottleneck_stage", "constraint_moved"]].to_string(index=False))

      print("\n" + "=" * 110)
      print("ANNUAL OUTPUT BY SCENARIO")
      print("=" * 110)
      print(summary[["scenario", "annual_good_units", "annual_gain_units",
                     "bottleneck_oee", "headroom_to_next_pct"]].to_string(index=False))

      print("\n" + "=" * 110)
      print("WHAT THE SCENARIOS SHOW")
      print("=" * 110)
      for i, note in enumerate(scenario_insights(summary), start=1):
          print(f"  {i}. {note}")
  
      print("\n" + "=" * 110)
      print("WHAT-IF: PROGRESSIVELY REDUCING BOTTLENECK DOWNTIME")
      print("=" * 110)
      dt_sweep = sweep_downtime_reduction(data)
      print(dt_sweep.to_string(index=False))
      dr = diminishing_returns_point(dt_sweep, key_col="downtime_reduction_pct")
      print(f"\n  Diminishing returns: {dr['note']}")

      print("\n" + "=" * 110)
      print("WHAT-IF: ADDING MACHINES AT THE BOTTLENECK")
      print("=" * 110)
      mc_sweep = sweep_extra_machines(data)
      print(mc_sweep.to_string(index=False))
      dr2 = diminishing_returns_point(mc_sweep, key_col="extra_machines")
      print(f"\n  Diminishing returns: {dr2['note']}")

      print("\n" + "=" * 110)
      print("STAGE CAPACITIES UNDER THE COMBINED SCENARIO (F)")
      print("=" * 110)
      print(stage_tables["F"][["stage", "machines", "availability", "performance", "quality",
                               "oee", "effective_capacity_per_day"]]
            .round(4).to_string(index=False))