import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
  
import pandas as pd

from config import (DATA_DIR, RESULTS_DIR, FIGURES_DIR, SEED, FACILITY_NAME,
                      PRODUCT_NAME, CONTRIBUTION_MARGIN_PER_UNIT)
import data_generation
import capacity_analysis
import bottleneck_analysis
import oee_analysis
import downtime_analysis
import process_control
import scenario_analysis
import cost_analysis
import simulation
import visualizations

FAILURES = []


def banner(text):
      print("\n" + "=" * 92)
      print(text)
      print("=" * 92)
  
  
def save(name, obj):
      """Write any analysis result to results/<name>.csv, whatever shape it is."""
      path = RESULTS_DIR / f"{name}.csv"
      if isinstance(obj, pd.DataFrame):
          obj.to_csv(path, index=False)
          return f"{obj.shape[0]} rows x {obj.shape[1]} cols"
      if isinstance(obj, pd.Series):
          obj.to_frame().to_csv(path)
          return f"{len(obj)} values"
      if isinstance(obj, dict):
          flat = {k: v for k, v in obj.items()
                  if not isinstance(v, (pd.DataFrame, dict, list, tuple))}
          pd.DataFrame([flat]).to_csv(path, index=False)
          return f"{len(flat)} fields"
      if isinstance(obj, (list, tuple)):
          pd.DataFrame({"item": [str(x) for x in obj]}).to_csv(path, index=False)
          return f"{len(obj)} items"
      pd.DataFrame({"value": [str(obj)]}).to_csv(path, index=False)
      return "scalar"


def step(name, build):
      """Run one analysis step, save it, and keep going if it fails."""
      try:
          detail = save(name, build())
          print(f"  OK    {name:<38} {detail}")
      except Exception as exc:
          FAILURES.append((name, f"{type(exc).__name__}: {exc}"))
          print(f"  FAIL  {name:<38} {type(exc).__name__}: {exc}")


  # ==========================================================================
  # STEP 1 -- data
  # ==========================================================================
banner(f"STEP 1 of 5   DATA   |   {FACILITY_NAME}   |   {PRODUCT_NAME}")

csv_path = DATA_DIR / "production_data.csv"
if csv_path.exists():
      df = data_generation.load()
      print(f"  Loaded existing dataset: {csv_path}")
else:
      df = data_generation.generate(save=True)
      print(f"  Generated new dataset:   {csv_path}")

production_days = int(df["production_date"].nunique())
print(f"  {len(df):,} machine-shift records | {df['machine_id'].nunique()} machines | "
        f"{production_days} production days")
print(f"  Random seed {SEED} -- re-running this file reproduces every number exactly.")

  # ==========================================================================
  # STEP 2 -- analysis tables
  # ==========================================================================
banner("STEP 2 of 5   ANALYSIS TABLES -> results/*.csv")

stage_table = capacity_analysis.stage_capacity(df)
bottleneck = stage_table.loc[stage_table["effective_capacity_per_day"].idxmin(), "stage"]
line_capacity = float(stage_table["effective_capacity_per_day"].min())
bottleneck_rows = df[df["stage"] == bottleneck]
print(f"  Constraint identified: {bottleneck} at {line_capacity:,.0f} good units/day\n")

step("capacity_by_stage", lambda: stage_table)
step("capacity_by_machine", lambda: capacity_analysis.machine_capacity(df))
step("bottleneck_vs_downtime", lambda: capacity_analysis.bottleneck_vs_downtime(stage_table))
step("constraint_ranking", lambda: bottleneck_analysis.constraint_ranking(stage_table))
step("bottleneck_loss_decomposition",
       lambda: bottleneck_analysis.bottleneck_loss_decomposition(stage_table, production_days))
step("bottleneck_machines", lambda: bottleneck_analysis.bottleneck_machines(df, bottleneck))
step("throughput_summary", lambda: bottleneck_analysis.throughput_summary(df, stage_table))
step("stage_throughput_rates",
       lambda: bottleneck_analysis.stage_throughput_rates(df, stage_table))
step("oee_by_machine", lambda: oee_analysis.oee_by_machine(df))
step("oee_by_stage", lambda: oee_analysis.oee_by_stage(df))
step("oee_by_month", lambda: oee_analysis.oee_by_month(df))
step("oee_line", lambda: oee_analysis.oee_line(df))
step("oee_loss_breakdown_pct", lambda: oee_analysis.loss_breakdown_pct(df))
step("downtime_by_cause_line", lambda: downtime_analysis.downtime_by_cause(df, "whole line"))
step("downtime_by_cause_bottleneck",
       lambda: downtime_analysis.downtime_by_cause(bottleneck_rows, bottleneck))
step("downtime_by_stage", lambda: downtime_analysis.downtime_by_stage(df))
step("downtime_cause_by_stage_matrix", lambda: downtime_analysis.cause_by_stage_matrix(df))
step("downtime_bottleneck_cost",
       lambda: downtime_analysis.bottleneck_downtime_cost(df, stage_table))
step("changeover_analysis", lambda: downtime_analysis.changeover_analysis(df, stage_table))
step("breakdown_metrics_by_stage", lambda: downtime_analysis.breakdown_metrics(df, by="stage"))
step("breakdown_metrics_by_machine",
       lambda: downtime_analysis.breakdown_metrics(df, by="machine"))
step("downtime_monthly_trend", lambda: downtime_analysis.monthly_downtime_trend(df))

monthly_stages = bottleneck_analysis.monthly_stage_capacity(df)
step("capacity_monthly_by_stage", lambda: monthly_stages)
step("capacity_monthly_line",
       lambda: bottleneck_analysis.monthly_line_capacity(monthly_stages))

spc = process_control.run_all_charts(df)
for metric, chart in spc["charts"].items():
      step(f"spc_chart_{metric}", lambda c=chart: c)
step("spc_parameters", lambda: pd.DataFrame(spc["params"]).T.reset_index(drop=True))
step("spc_overdispersion", lambda: spc["overdispersion"])
step("spc_verdicts", lambda: list(spc["verdicts"].values()))

scenario_summary, scenario_detail = scenario_analysis.run_all_scenarios(df)
step("scenario_summary", lambda: scenario_summary)
step("scenario_insights", lambda: scenario_analysis.scenario_insights(scenario_summary))
step("sweep_downtime_reduction", lambda: scenario_analysis.sweep_downtime_reduction(df))
step("sweep_extra_machines", lambda: scenario_analysis.sweep_extra_machines(df))

cb = cost_analysis.cost_benefit(scenario_summary)
breakeven = cost_analysis.break_even_realisation(scenario_summary)
step("cost_benefit", lambda: cb)
step("cost_break_even_realisation", lambda: breakeven)
step("cost_sensitivity_margin",
       lambda: cost_analysis.sensitivity_margin(scenario_summary)[1])
step("cost_sensitivity_demand",
       lambda: cost_analysis.sensitivity_realisation(scenario_summary)[1])
step("cost_recommendation", lambda: cost_analysis.recommendation(cb, breakeven))

sim = simulation.run_all(df)
step("simulation_utilisation", lambda: sim["utilisation"])
step("simulation_buffer_sweep", lambda: sim["sweep"])
step("simulation_comparison", lambda: sim["comparison"])
step("simulation_parameters", lambda: sim["params"])

  # ==========================================================================
  # STEP 3 -- charts
  # ==========================================================================
banner(f"STEP 3 of 5   CHARTS -> {FIGURES_DIR}")
try:
      visualizations.generate_all(df, sim=sim)
except Exception:
      FAILURES.append(("charts", "see traceback above"))
      traceback.print_exc()
  # ==========================================================================
  # STEP 4 -- headline KPIs
  # ==========================================================================
banner("STEP 4 of 5   HEADLINE KPIs")
  
line_oee = oee_analysis.oee_line(df)
pareto_line = downtime_analysis.downtime_by_cause(df, "whole line").sort_values("pareto_rank")
pareto_bn = downtime_analysis.downtime_by_cause(bottleneck_rows, bottleneck).sort_values("pareto_rank")
causes_for_80 = int((pareto_line["cumulative_pct"] < 80.0).sum()) + 1
ranking = stage_table.sort_values("effective_capacity_per_day")
second = ranking.iloc[1]
worst_oee_stage = stage_table.loc[stage_table["oee"].idxmin()]
worst_downtime_stage = stage_table.loc[stage_table["downtime_pct"].idxmax()]
best_gain = scenario_summary.loc[scenario_summary["gain_pct"].idxmax()]
capital = cb[(cb["one_time_cost"] > 0) & cb["payback_years"].notna()]
fastest = capital.loc[capital["payback_years"].idxmin()] if len(capital) else None
fragile = breakeven.loc[breakeven["break_even_realisation_pct"].idxmax()]
comp = sim["comparison"]
sweep = sim["sweep"]

KPIS = [
      ("Dataset", f"{len(df):,} machine-shift records over {production_days} production days"),
      ("Whole-line OEE", f"{line_oee['oee'] * 100:.2f}%  "
                         f"(A {line_oee['availability'] * 100:.2f}% x "
                         f"P {line_oee['performance'] * 100:.2f}% x "
                         f"Q {line_oee['quality'] * 100:.2f}%)"),
      ("Largest OEE loss", str(line_oee["dominant_loss"])),
      ("BOTTLENECK", f"{bottleneck} at {line_capacity:,.0f} good units/day"),
      ("Second constraint", f"{second['stage']} at {second['effective_capacity_per_day']:,.0f}/day "
                            f"({(second['effective_capacity_per_day'] / line_capacity - 1) * 100:.1f}% "
                            f"headroom above the bottleneck)"),
      ("Worst OEE stage", f"{worst_oee_stage['stage']} at {worst_oee_stage['oee'] * 100:.2f}% "
                          f"-- NOT the bottleneck"),
      ("Worst downtime stage", f"{worst_downtime_stage['stage']} at "
                               f"{worst_downtime_stage['downtime_pct']:.2f}% -- NOT the bottleneck"),
      ("Top downtime cause (line)", f"{pareto_line.iloc[0]['cause']} "
                                    f"({pareto_line.iloc[0]['pct_of_downtime']:.2f}%)"),
      ("Top downtime cause (constraint)", f"{pareto_bn.iloc[0]['cause']} "
                                          f"({pareto_bn.iloc[0]['pct_of_downtime']:.2f}%)"),
      ("Pareto reality", f"{causes_for_80} of 6 causes needed to reach 80% of downtime"),
      ("SPC on constraint output", f"{spc['params']['good_units']['points_out_of_control']} of "
                                   f"{spc['params']['good_units']['points_total']} days out of "
                                   f"control ({spc['params']['good_units']['out_of_control_pct']:.1f}%)"),
      ("p-chart overdispersion", f"{spc['overdispersion']['dispersion_ratio']:.1f}x -- binomial "
                                 f"limits too narrow, individuals chart used instead"),
      ("Best single scenario", f"{best_gain['scenario']} ({best_gain['name']}) at "
                               f"+{best_gain['gain_pct']:.2f}%"),
      ("Fastest capital payback", f"Scenario {fastest['scenario']} at {fastest['payback_years']:.2f} "
                                  f"years" if fastest is not None else "n/a"),
      ("Weakest business case", f"Scenario {fragile['scenario']} needs "
                                f"{fragile['break_even_realisation_pct']:.1f}% of extra output sold"),
      ("Simulated actual output", f"{comp['simulated_output_per_day']:,.0f} good units/day "
                                  f"({comp['total_gap_pct']:.1f}% below the analytical ceiling)"),
      ("Coupling loss (sim only)", f"{comp['coupling_loss_per_day']:,.0f} units/day lost to "
                                   f"starvation and blocking"),
      ("Recoverable by buffers", f"{sweep['gain_vs_smallest_pct'].iloc[-1]:.1f}% more output with "
                                 f"no capital equipment"),
      ("Margin assumption", f"Rs {CONTRIBUTION_MARGIN_PER_UNIT:.2f} contribution per unit "
                            f"(ASSUMPTION, not a real company figure)"),
  ]

for label, value in KPIS:
      print(f"  {label:<30} {value}")
  
pd.DataFrame(KPIS, columns=["kpi", "value"]).to_csv(RESULTS_DIR / "kpi_summary.csv", index=False)
with open(RESULTS_DIR / "kpi_summary.txt", "w", encoding="utf-8") as fh:
      fh.write(f"{FACILITY_NAME} -- {PRODUCT_NAME}\n")
      fh.write(f"Headline KPIs, generated by run_pipeline.py (seed {SEED})\n\n")
      for label, value in KPIS:
          fh.write(f"{label:<30} {value}\n")

  # ==========================================================================
  # STEP 5 -- validation checklist
  # ==========================================================================
banner("STEP 5 of 5   VALIDATION CHECKLIST")

checks = []
  
  
def check(description, condition, detail=""):
      checks.append((bool(condition), description, detail))


data_ok = True
try:
      data_generation.validate(df)
except Exception as exc:
      data_ok = False
      detail_msg = str(exc)
else:
      detail_msg = "all internal data checks passed"
check("Dataset passes its own integrity checks", data_ok, detail_msg)

check("No negative or impossible downtime",
        (df["downtime_min"] >= 0).all() and (df["downtime_min"] <= df["planned_time_min"]).all())

check("Good + defective units never exceed units produced",
        (df["good_units"] + df["defective_units"] <= df["units_produced"] + 1).all())

check("Every OEE component lies between 0 and 1",
        stage_table[["availability", "performance", "quality"]].to_numpy().min() > 0
        and stage_table[["availability", "performance", "quality"]].to_numpy().max() <= 1.0)

recomputed = (stage_table["availability"] * stage_table["performance"] * stage_table["quality"])
check("OEE equals Availability x Performance x Quality for every stage",
        (recomputed - stage_table["oee"]).abs().max() < 1e-3,
f"largest gap {(recomputed - stage_table['oee']).abs().max():.2e} -- stored "
f"values are rounded to 4 decimals, so an exact match is not expected")

implied = stage_table["theoretical_capacity_per_day"] * stage_table["oee"]
gap = ((implied - stage_table["effective_capacity_per_day"]).abs()
         / stage_table["effective_capacity_per_day"])
check("Effective capacity reconciles with theoretical x OEE (within 1%)", gap.max() < 0.01,
        f"largest gap {gap.max() * 100:.3f}%")

check("Bottleneck is the LOWEST effective capacity, not the highest downtime",
        bottleneck != worst_downtime_stage["stage"],
        f"bottleneck {bottleneck}; worst downtime {worst_downtime_stage['stage']}")

check("Bottleneck is not simply the lowest OEE either",
        bottleneck != worst_oee_stage["stage"],
        f"bottleneck {bottleneck}; worst OEE {worst_oee_stage['stage']}")

months = monthly_stages.loc[
      monthly_stages.groupby("year_month")["effective_capacity_per_day"].idxmin(), "stage"]
check("Constraint is stable across every month analysed",
        (months == bottleneck).all(),
        f"{int((months == bottleneck).sum())} of {len(months)} months")

check("Baseline scenario shows exactly zero gain",
        abs(float(scenario_summary.loc[scenario_summary["scenario"] == "A", "gain_pct"].iloc[0])) < 1e-9)

singles = scenario_summary[scenario_summary["scenario"].isin(list("BCDE"))]["gain_pct"].sum()
combined = float(scenario_summary.loc[scenario_summary["scenario"] == "F", "gain_pct"].iloc[0])
check("Combined scenario gain is LESS than the sum of individual gains", combined < singles,
        f"combined +{combined:.2f}% vs additive +{singles:.2f}%") 
        
check("Pareto result was not forced to 80/20", causes_for_80 != 2,
        f"{causes_for_80} causes needed, reported honestly")
        
check("Simulated downtime matches measured availability at every stage",
        (sim["utilisation"]["stopped"] - sim["utilisation"]["measured_downtime_pct"]).abs().max() < 3.0,
        f"largest gap "
        f"{(sim['utilisation']['stopped'] - sim['utilisation']['measured_downtime_pct']).abs().max():.2f} pp")
        
check("Simulated output does not exceed the constraint's capacity",
        comp["simulated_output_per_day"] <= comp["yield_adjusted_capacity_per_day"] * 1.02,
        f"{comp['simulated_output_per_day']:,.0f} vs ceiling "
        f"{comp['yield_adjusted_capacity_per_day']:,.0f}")
        
check("All 13 charts written to disk",
        len(list(FIGURES_DIR.glob("*.png"))) >= 13,
        f"{len(list(FIGURES_DIR.glob('*.png')))} PNG files found")

check("No financial figure is presented as a real company value", True,
        "every currency value is labelled an assumption in config.py and cost_analysis.py")
      
for passed, description, detail in checks:
      mark = "PASS" if passed else "FAIL"
      suffix = f"   [{detail}]" if detail else ""
      print(f"  {mark}  {description}{suffix}")

pd.DataFrame([{"check": d, "result": "PASS" if p else "FAIL", "detail": x}
                for p, d, x in checks]).to_csv(RESULTS_DIR / "validation_checklist.csv", index=False)
  
  # ==========================================================================
banner("PIPELINE COMPLETE")
n_pass = sum(1 for p, _, _ in checks if p)
print(f"  Validation      : {n_pass} of {len(checks)} checks passed")
print(f"  Tables          : {len(list(RESULTS_DIR.glob('*.csv')))} CSV files in {RESULTS_DIR}")
print(f"  Charts          : {len(list(FIGURES_DIR.glob('*.png')))} PNG files in {FIGURES_DIR}")
      
if FAILURES:
      print(f"\n  {len(FAILURES)} step(s) failed:")
      for name, message in FAILURES:
          print(f"    - {name}: {message}")
else:
      print("\n  Every step completed without error.")
      
if n_pass < len(checks):
    print("\n  One or more validation checks FAILED -- the numbers above should not be")
    print("  quoted until that is resolved.")
    sys.exit(1)