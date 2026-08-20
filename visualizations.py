import matplotlib
matplotlib.use("Agg")          # no display needed; must precede pyplot

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
  
from config import FIGURES_DIR, CONTRIBUTION_MARGIN_PER_UNIT
import capacity_analysis
import bottleneck_analysis
import oee_analysis
import downtime_analysis
import process_control
import scenario_analysis
import cost_analysis
import simulation
  
  # One meaning per colour: red = the constraint, everything else is context
RED = "#c0392b"
NAVY = "#2c3e50"
BLUE = "#2980b9"
GREEN = "#27ae60"
AMBER = "#e67e22"
GREY = "#95a5a6"
LIGHT = "#dfe6e9"

CAUSE_ORDER = ["Equipment Breakdown", "Material Shortage", "Changeover / Setup",
                 "Quality Issue", "Operator Unavailability", "Minor Stoppages"]


def _style(ax, title, subtitle=None, xlabel=None, ylabel=None):
      """Consistent framing, with the finding in the subtitle."""
      ax.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=18)
      if subtitle:
          ax.text(0.0, 1.02, subtitle, transform=ax.transAxes, fontsize=9.5,
                  color="#555555", ha="left", va="bottom")
      if xlabel:
          ax.set_xlabel(xlabel, fontsize=10)
      if ylabel:
          ax.set_ylabel(ylabel, fontsize=10)
      ax.grid(axis="y", alpha=0.25, linestyle="--")
      ax.set_axisbelow(True)
      for side in ("top", "right"):
          ax.spines[side].set_visible(False)


def _save(fig, filename):
      path = FIGURES_DIR / filename
      fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
      plt.close(fig)
      return path


def _short(names):
      """Stage names are long; wrap them for axis labels."""
      return [n.replace(" ", "\n", 1) if len(n) > 12 else n for n in names]


  # --------------------------------------------------------------------------
  # 1. The bottleneck argument, in one image
  # --------------------------------------------------------------------------
def chart_capacity_ladder(df):
      stages = capacity_analysis.stage_capacity(df).sort_values("stage_index")
      bottleneck = stages.loc[stages["effective_capacity_per_day"].idxmin(), "stage"]
      line_capacity = stages["effective_capacity_per_day"].min()

      x = np.arange(len(stages))
      width = 0.27
      fig, ax = plt.subplots(figsize=(12, 6))

      ax.bar(x - width, stages["theoretical_capacity_per_day"], width,
             label="Theoretical (nameplate)", color=LIGHT, edgecolor=GREY)
      colours = [RED if s == bottleneck else BLUE for s in stages["stage"]]
      ax.bar(x, stages["effective_capacity_per_day"], width,
             label="Effective (demonstrated)", color=colours)
      ax.bar(x + width, stages["actual_good_units_per_day"], width,
             label="Actual good output", color=NAVY)

      ax.axhline(line_capacity, color=RED, linestyle="--", linewidth=1.4)
      ax.text(len(stages) - 0.45, line_capacity, f"  line capacity\n  {line_capacity:,.0f}/day",
              color=RED, fontsize=9, va="center", fontweight="bold")

      ax.set_xticks(x)
      ax.set_xticklabels(_short(stages["stage"]), fontsize=9)
      ax.legend(frameon=False, fontsize=9, loc="upper right")
      _style(ax, "Capacity by stage: the line can only run as fast as its slowest stage",
             f"{bottleneck} has the lowest effective capacity, so it sets output for the whole "
             f"line. Note it does NOT have the lowest nameplate capacity.",
             ylabel="Good units per day")
      return _save(fig, "01_capacity_ladder.png")


  # --------------------------------------------------------------------------
  # 2. Machine-level OEE -- shows the worst machines are NOT at the constraint
  # --------------------------------------------------------------------------
def chart_oee_by_machine(df):
      machines = oee_analysis.oee_by_machine(df).sort_values("oee")
      stages = capacity_analysis.stage_capacity(df)
      bottleneck = stages.loc[stages["effective_capacity_per_day"].idxmin(), "stage"]

      colours = [RED if s == bottleneck else GREY for s in machines["stage"]]
      fig, ax = plt.subplots(figsize=(11, 7))
      ax.barh(machines["machine_id"], machines["oee"] * 100.0, color=colours)
      ax.axvline(85, color=GREEN, linestyle="--", linewidth=1.4)
      ax.text(85.4, 0.2, "world-class 85%", color=GREEN, fontsize=9, rotation=90, va="bottom")

      worst = machines.head(3)
      for i, (_, row) in enumerate(worst.iterrows()):
          ax.text(row["oee"] * 100.0 + 0.6, i, f" {row['stage']} · worst loss: {row['dominant_loss']}",
                  fontsize=8.5, va="center", color=NAVY)

      ax.set_xlim(0, 100)
      ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=RED),
                         plt.Rectangle((0, 0), 1, 1, color=GREY)],
                labels=[f"{bottleneck} (the constraint)", "other stages"],
                frameon=False, fontsize=9, loc="lower right")
      _style(ax, "OEE by machine, worst first",
             f"The three worst machines on the line are not at the constraint. Fixing them "
             f"would improve their own OEE and leave line output unchanged.",
             xlabel="OEE (%)")
      ax.grid(axis="x", alpha=0.25, linestyle="--")
      return _save(fig, "02_oee_by_machine.png")

  
  # --------------------------------------------------------------------------
  # 3. Where the lost time actually goes
  # --------------------------------------------------------------------------
def chart_oee_loss_breakdown(df):
      losses = oee_analysis.loss_breakdown_pct(df)
      line = oee_analysis.oee_line(df)

      order = [("productive_pct", "Fully productive", GREEN),
               ("downtime_pct", "Downtime loss", RED),
               ("speed_loss_pct", "Speed loss", AMBER),
               ("quality_loss_pct", "Quality loss", BLUE)]

      fig, ax = plt.subplots(figsize=(12, 3.4))
      left = 0.0
      for key, label, colour in order:
          value = float(losses[key])
          ax.barh([0], [value], left=left, color=colour, edgecolor="white", height=0.55)
          if value > 2.0:
              ax.text(left + value / 2.0, 0, f"{label}\n{value:.1f}%", ha="center",
                      va="center", fontsize=9.5, color="white", fontweight="bold")
          left += value

      ax.set_xlim(0, 100)
      ax.set_yticks([])
      ax.set_xlabel("Share of planned production time (%)", fontsize=10)
      ax.set_title("Every minute of planned time, accounted for",
                   fontsize=13, fontweight="bold", loc="left", pad=18)
      ax.text(0.0, 1.06,
              f"Whole-line OEE is {line['oee'] * 100:.1f}%. The largest single loss is "
              f"{line['dominant_loss']}, which is where improvement effort belongs.",
              transform=ax.transAxes, fontsize=9.5, color="#555555")
      for side in ("top", "right", "left"):
          ax.spines[side].set_visible(False)
      return _save(fig, "03_oee_loss_breakdown.png")

  
  # --------------------------------------------------------------------------
  # 4 & 5. Pareto -- line level, then at the constraint
  # --------------------------------------------------------------------------
def _pareto(pareto, title, subtitle, filename):
      pareto = pareto.sort_values("pareto_rank")
      x = np.arange(len(pareto))

      fig, ax = plt.subplots(figsize=(11.5, 6))
      ax.bar(x, pareto["pct_of_downtime"], color=BLUE, width=0.62)
      for i, v in enumerate(pareto["pct_of_downtime"]):
          ax.text(i, v + 0.7, f"{v:.1f}%", ha="center", fontsize=9, color=NAVY)

      ax2 = ax.twinx()
      ax2.plot(x, pareto["cumulative_pct"], color=RED, marker="o", linewidth=1.8, markersize=5)
      ax2.axhline(80, color=GREY, linestyle=":", linewidth=1.3)
      ax2.text(len(x) - 0.4, 80.8, "80%", color=GREY, fontsize=9)
      ax2.set_ylim(0, 105)
      ax2.set_ylabel("Cumulative share of downtime (%)", fontsize=10, color=RED)
      ax2.tick_params(axis="y", colors=RED)
      ax2.spines["top"].set_visible(False)

      ax.set_xticks(x)
      ax.set_xticklabels([c.replace(" / ", "/\n").replace(" ", "\n", 1) for c in pareto["cause"]],
                         fontsize=8.5)
      ax.set_ylim(0, max(pareto["pct_of_downtime"]) * 1.25)
      _style(ax, title, subtitle, ylabel="Share of downtime (%)")
      return _save(fig, filename)


def chart_pareto_line(df):
      pareto = downtime_analysis.downtime_by_cause(df, "whole line")
      verdict = downtime_analysis.pareto_verdict(pareto, 0.80)
      n_needed = int((pareto.sort_values("pareto_rank")["cumulative_pct"] < 80.0).sum()) + 1
      return _pareto(pareto, "Downtime causes across the whole line",
                     f"{n_needed} of 6 causes are needed to reach 80% of downtime, so this is not "
                     f"a clean 80/20 -- the losses are more evenly spread than the rule suggests.",
                     "04_pareto_line.png")


def chart_pareto_bottleneck(df):
      stages = capacity_analysis.stage_capacity(df)
      bottleneck = stages.loc[stages["effective_capacity_per_day"].idxmin(), "stage"]
      sub = df[df["stage"] == bottleneck]
      pareto = downtime_analysis.downtime_by_cause(sub, bottleneck)
      top2 = pareto.sort_values("pareto_rank").head(2)
      return _pareto(pareto, f"Downtime causes at the constraint ({bottleneck})",
                     f"This is the ranking that matters. Only downtime here costs the line output. "
                     f"{top2.iloc[0]['cause']} and {top2.iloc[1]['cause']} together are "
                     f"{top2['pct_of_downtime'].sum():.1f}% of it.",
                     "05_pareto_bottleneck.png")


  # --------------------------------------------------------------------------
  # 6. Cause by stage -- different stages fail for different reasons
  # --------------------------------------------------------------------------
def chart_cause_stage_heatmap(df):
      matrix = downtime_analysis.cause_by_stage_matrix(df, as_percent=True)
      stages = matrix["stage"].tolist()
      causes = [c for c in CAUSE_ORDER if c in matrix.columns]
      values = matrix[causes].to_numpy(dtype=float)

      fig, ax = plt.subplots(figsize=(11, 5.6))
      im = ax.imshow(values, cmap="OrRd", aspect="auto", vmin=0, vmax=values.max())

      for i in range(values.shape[0]):
          for j in range(values.shape[1]):
              v = values[i, j]
              ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9,
                      color="white" if v > values.max() * 0.6 else NAVY)

      ax.set_xticks(np.arange(len(causes)))
      ax.set_xticklabels([c.replace(" / ", "/\n").replace(" ", "\n", 1) for c in causes], fontsize=8.5)
      ax.set_yticks(np.arange(len(stages)))
      ax.set_yticklabels(stages, fontsize=9)
      ax.set_title("Each stage's downtime, split by cause (% of that stage's downtime)",
                   fontsize=13, fontweight="bold", loc="left", pad=18)
      ax.text(0.0, 1.03,
              "Not every stage has a maintenance problem. Reading across the rows shows which "
              "stages need engineering, which need materials, and which need people.",
              transform=ax.transAxes, fontsize=9.5, color="#555555")
      fig.colorbar(im, ax=ax, shrink=0.8, label="% of stage downtime")
      return _save(fig, "06_cause_by_stage_heatmap.png")


  # --------------------------------------------------------------------------
  # 7. Control chart on the constraint's daily output
  # --------------------------------------------------------------------------
def _control_panel(ax, chart, value_col, params, label, scale=1.0, unit=""):
      x = chart["day_number"]
      y = chart[value_col] * scale
      baseline_end = int(chart.loc[chart["in_baseline"], "day_number"].max())
      ax.axvspan(x.min(), baseline_end, color=LIGHT, alpha=0.55, zorder=0)
      ax.text(baseline_end, ax.get_ylim()[1], " Phase I: limits set here ",
              fontsize=8, color=GREY, va="top")
  
      ax.plot(x, y, color=NAVY, linewidth=0.9, marker="o", markersize=2.4, zorder=2)
      ax.axhline(params["centre_line"] * scale, color=GREEN, linewidth=1.4)
      ax.axhline(params["upper_control_limit"] * scale, color=RED, linestyle="--", linewidth=1.2)
      ax.axhline(params["lower_control_limit"] * scale, color=RED, linestyle="--", linewidth=1.2)

      violations = chart[chart["out_of_control"]]
      if len(violations):
          ax.scatter(violations["day_number"], violations[value_col] * scale,
                     color=RED, s=42, zorder=3, marker="o", edgecolor="white", linewidth=0.8)

      ax.text(x.max(), params["upper_control_limit"] * scale, " UCL", color=RED,
              fontsize=8.5, va="center")
      ax.text(x.max(), params["lower_control_limit"] * scale, " LCL", color=RED,
              fontsize=8.5, va="center")
      ax.set_ylabel(f"{label}{unit}", fontsize=10)
      ax.grid(alpha=0.2, linestyle="--")
      ax.set_axisbelow(True)
      for side in ("top", "right"):
          ax.spines[side].set_visible(False)


def chart_control_output(df):
      spc = process_control.run_all_charts(df)
      chart = spc["charts"]["good_units"]
      params = spc["params"]["good_units"]
      stage = spc["stage"]
      verdict = spc["verdicts"]["good_units"]
      drift = spc["drift"]["good_units"]

      fig, ax = plt.subplots(figsize=(13, 5.6))
      _control_panel(ax, chart, "good_units", params, "Good units per day")
      ax.set_xlabel("Production day", fontsize=10)
      ax.set_title(f"Individuals control chart: daily good output at {stage}",
                   fontsize=13, fontweight="bold", loc="left", pad=18)
      ax.text(0.0, 1.03,
              f"{params['points_out_of_control']} of {params['points_total']} days out of control "
              f"({params['out_of_control_pct']:.1f}%). Baseline mean {drift['baseline_mean']:,.0f} "
              f"vs later mean {drift['monitoring_mean']:,.0f} ({drift['change_pct']:+.1f}%, "
              f"{drift['direction']}).",
              transform=ax.transAxes, fontsize=9.5, color="#555555")
      return _save(fig, "07_control_chart_output.png")
  
  
  # --------------------------------------------------------------------------
  # 8. The overdispersion finding: right chart vs textbook chart
  # --------------------------------------------------------------------------
def chart_control_defect_rate(df):
      spc = process_control.run_all_charts(df)
      over = spc["overdispersion"]

      fig, axes = plt.subplots(2, 1, figsize=(13, 8.4), sharex=True)

      ind_chart, ind_params = spc["charts"]["defect_rate"], spc["params"]["defect_rate"]
      _control_panel(axes[0], ind_chart, "defect_rate", ind_params, "Defect rate", 100.0, " (%)")
      axes[0].set_title("Individuals chart on daily defect rate -- the chart that works",
                        fontsize=12, fontweight="bold", loc="left", pad=12)
      axes[0].text(0.0, 1.02,
                   f"{ind_params['points_out_of_control']} of {ind_params['points_total']} days "
                   f"flagged ({ind_params['out_of_control_pct']:.1f}%). Limits come from the "
                   f"observed day-to-day variation.",
                   transform=axes[0].transAxes, fontsize=9, color="#555555")

      p_chart, p_params = spc["charts"]["defect_rate_p_chart"], spc["params"]["defect_rate_p_chart"]
      x = p_chart["day_number"]
      axes[1].plot(x, p_chart["defect_rate"] * 100.0, color=NAVY, linewidth=0.9,
                   marker="o", markersize=2.4)
      axes[1].plot(x, p_chart["centre_line"] * 100.0, color=GREEN, linewidth=1.4)
      axes[1].plot(x, p_chart["upper_control_limit"] * 100.0, color=RED, linestyle="--", linewidth=1.2)
      axes[1].plot(x, p_chart["lower_control_limit"] * 100.0, color=RED, linestyle="--", linewidth=1.2)
      viol = p_chart[p_chart["out_of_control"]]
      axes[1].scatter(viol["day_number"], viol["defect_rate"] * 100.0, color=RED, s=26,
                      zorder=3, edgecolor="white", linewidth=0.5)
      axes[1].set_ylabel("Defect rate (%)", fontsize=10)
      axes[1].set_xlabel("Production day", fontsize=10)
      axes[1].grid(alpha=0.2, linestyle="--")
      axes[1].set_axisbelow(True)
      for side in ("top", "right"):
          axes[1].spines[side].set_visible(False)
      axes[1].set_title("p-chart on the same data -- the textbook chart, and why it fails here",
                        fontsize=12, fontweight="bold", loc="left", pad=12)
      axes[1].text(0.0, 1.02,
                   f"{p_params['points_out_of_control']} of {p_params['points_total']} days flagged "
                   f"({p_params['out_of_control_pct']:.1f}%). With "
                   f"{p_params['avg_daily_units']:,.0f} units inspected daily the binomial limits "
                   f"collapse to ±{over['binomial_half_width_pp']:.3f} pp, "
                   f"{over['dispersion_ratio']:.1f}x narrower than real variation.",
                   transform=axes[1].transAxes, fontsize=9, color="#555555")

      fig.suptitle("Choosing the right control chart matters more than drawing one",
                   fontsize=13.5, fontweight="bold", x=0.09, ha="left", y=0.99)
      fig.tight_layout(rect=[0, 0, 1, 0.97])
      return _save(fig, "08_control_chart_defect_rate.png")


  # --------------------------------------------------------------------------
  # 9. Is the bottleneck structural or a bad month?
  # --------------------------------------------------------------------------
def chart_bottleneck_stability(df):
      monthly = bottleneck_analysis.monthly_stage_capacity(df)
      monthly["label"] = monthly["year_month"].astype(str)
      stages = capacity_analysis.stage_capacity(df)
      bottleneck = stages.loc[stages["effective_capacity_per_day"].idxmin(), "stage"]

      labels = sorted(monthly["label"].unique())
      x = np.arange(len(labels))
  
      fig, ax = plt.subplots(figsize=(12.5, 6.2))
      for stage, group in monthly.groupby("stage"):
          group = group.set_index("label").reindex(labels)
          is_constraint = stage == bottleneck
          ax.plot(x, group["effective_capacity_per_day"],
                  color=RED if is_constraint else GREY,
                  linewidth=2.6 if is_constraint else 1.1,
                  marker="o" if is_constraint else None, markersize=4,
                  alpha=1.0 if is_constraint else 0.65,
                  label=stage if is_constraint else None, zorder=3 if is_constraint else 1)
          if not is_constraint:
              ax.text(len(labels) - 0.9, group["effective_capacity_per_day"].iloc[-1],
                      f" {stage}", fontsize=7.5, color=GREY, va="center")

      months_constraining = int((monthly.loc[monthly.groupby("label")["effective_capacity_per_day"]
                                .idxmin(), "stage"] == bottleneck).sum())
      ax.set_xticks(x)
      ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8.5)
      ax.legend(frameon=False, fontsize=9.5, loc="upper right")
      _style(ax, "Effective capacity by stage, month by month",
             f"{bottleneck} is the lowest line in {months_constraining} of {len(labels)} months. "
             f"The constraint is structural, not a bad month -- so it is worth spending capital on.",
             ylabel="Effective capacity (good units/day)")
      return _save(fig, "09_bottleneck_stability.png")


  # --------------------------------------------------------------------------
  # 10. Scenarios, and why gains do not add up
  # --------------------------------------------------------------------------
def chart_scenario_comparison(df):
      summary, _ = scenario_analysis.run_all_scenarios(df)
      summary = summary.sort_values("scenario")

      singles = summary[summary["scenario"].isin(list("BCDE"))]
      additive = float(singles["gain_pct"].sum())
      combined = float(summary.loc[summary["scenario"] == "F", "gain_pct"].iloc[0])

      x = np.arange(len(summary))
      colours = [GREY if s == "A" else (GREEN if s == "F" else BLUE) for s in summary["scenario"]]

      fig, ax = plt.subplots(figsize=(12, 6.4))
      ax.bar(x, summary["line_capacity_per_day"], color=colours, width=0.6)
      baseline = float(summary.loc[summary["scenario"] == "A", "line_capacity_per_day"].iloc[0])
      ax.axhline(baseline, color=GREY, linestyle="--", linewidth=1.2)

      for i, (_, row) in enumerate(summary.iterrows()):
          ax.text(i, row["line_capacity_per_day"] + 260,
                  f"{row['line_capacity_per_day']:,.0f}\n+{row['gain_pct']:.2f}%",
                  ha="center", fontsize=9, color=NAVY, fontweight="bold")
          if row["constraint_moved"]:
              ax.text(i, baseline * 0.45, f"constraint moves to\n{row['bottleneck_stage']}",
                      ha="center", fontsize=8, color=RED, style="italic")

      ax.set_xticks(x)
      ax.set_xticklabels([f"{s}\n{n}" for s, n in zip(summary["scenario"], summary["name"])],
                         fontsize=8.2)
      ax.set_ylim(0, summary["line_capacity_per_day"].max() * 1.16)
      _style(ax, "Line capacity under each improvement scenario",
             f"The four single improvements add to +{additive:.2f}% on paper, but doing all of them "
             f"delivers +{combined:.2f}%. Treating gains as additive would overstate the result by "
             f"{(additive / combined - 1) * 100:.0f}%.",
             ylabel="Line capacity (good units/day)")
      return _save(fig, "10_scenario_comparison.png")

  
  # --------------------------------------------------------------------------
  # 11. Which investment is actually worth making
  # --------------------------------------------------------------------------
def chart_cost_benefit(df):
      summary, _ = scenario_analysis.run_all_scenarios(df)
      cb = cost_analysis.cost_benefit(summary)
      breakeven = cost_analysis.break_even_realisation(summary).set_index("scenario")
      cb = cb[cb["scenario"] != "A"].copy()

      fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.8),
                                    gridspec_kw={"width_ratios": [1.15, 1]})

      x = np.arange(len(cb))
      ax.bar(x, cb["net_annual_benefit"] / 1e6, color=BLUE, width=0.6)
      for i, (_, row) in enumerate(cb.iterrows()):
          payback = ("no capital" if row["payback_years"] == 0
                     else f"{row['payback_years']:.2f} yr payback")
          ax.text(i, row["net_annual_benefit"] / 1e6 + 0.12,
                  f"₹{row['net_annual_benefit'] / 1e6:.2f}M\n{payback}",
                  ha="center", fontsize=8.5, color=NAVY)
      ax.set_xticks(x)
      ax.set_xticklabels(cb["scenario"], fontsize=10)
      ax.set_ylim(0, cb["net_annual_benefit"].max() / 1e6 * 1.25)
      _style(ax, "Net annual benefit by scenario",
             f"All values are ASSUMPTIONS (₹{CONTRIBUTION_MARGIN_PER_UNIT:.2f}/unit margin).",
             xlabel="Scenario", ylabel="Net annual benefit (₹ million)")

      be = breakeven.reindex(cb["scenario"])
      colours = [RED if v > 50 else GREEN for v in be["break_even_realisation_pct"]]
      ax2.barh(be.index, be["break_even_realisation_pct"], color=colours)
      ax2.axvline(50, color=GREY, linestyle=":", linewidth=1.3)
      ax2.text(51, -0.4, "half the extra output", fontsize=8.5, color=GREY)
      for i, v in enumerate(be["break_even_realisation_pct"]):
          ax2.text(v + 1.2, i, f"{v:.1f}%", fontsize=9, va="center", color=NAVY)
      ax2.set_xlim(0, max(be["break_even_realisation_pct"]) * 1.3)
      worst = be["break_even_realisation_pct"].idxmax()
      _style(ax2, "How much extra output must sell to break even",
             f"Scenario {worst} needs {be['break_even_realisation_pct'].max():.1f}% sold — "
             f"the only fragile option.",
             xlabel="Break-even demand realisation (%)")
      ax2.grid(axis="x", alpha=0.25, linestyle="--")
      fig.tight_layout()
      return _save(fig, "11_cost_benefit.png")
  
  
  # --------------------------------------------------------------------------
  # 12. Simulation: what OEE cannot see
  # --------------------------------------------------------------------------
def chart_simulation_time_states(df, sim=None):
      sim = sim or simulation.run_all(df)
      util = sim["utilisation"]
      comp = sim["comparison"]
      order = util.sort_values("running", ascending=True)
      fig, ax = plt.subplots(figsize=(12, 6.2))
      left = np.zeros(len(order))
      for col, label, colour in [("running", "Running", GREEN), ("stopped", "Own breakdown", RED),
                                 ("starved", "Starved (waiting upstream)", AMBER),
                                 ("blocked", "Blocked (downstream full)", BLUE)]:
          ax.barh(order["stage"], order[col], left=left, label=label, color=colour, height=0.62)
          for i, (v, l) in enumerate(zip(order[col], left)):
              if v > 6.0:
                  ax.text(l + v / 2.0, i, f"{v:.0f}", ha="center", va="center",
                          fontsize=8.5, color="white", fontweight="bold")
          left = left + order[col].to_numpy()

      ax.set_xlim(0, 100)
      ax.legend(frameon=False, fontsize=9, ncol=4, loc="upper center",
                bbox_to_anchor=(0.5, -0.09))
      _style(ax, "Where every machine-minute goes once the stages are linked",
             f"{comp['bottleneck_stage']} is the only stage barely waiting on anyone else — the "
             f"constraint confirming itself. Starvation and blocking cost "
             f"{comp['coupling_loss_per_day']:,.0f} units/day and appear in no OEE figure.",
             xlabel="Share of that stage's machine-minutes (%)")
      ax.grid(axis="x", alpha=0.25, linestyle="--")
      return _save(fig, "12_simulation_time_states.png")


  # --------------------------------------------------------------------------
  # 13. Buffers: capacity for no capital, up to a point
  # --------------------------------------------------------------------------
def chart_buffer_returns(df, sim=None):
      sim = sim or simulation.run_all(df)
      sweep = sim["sweep"]
      x = np.arange(len(sweep))

      fig, ax = plt.subplots(figsize=(11.5, 6.2))
      ax.plot(x, sweep["mean_daily_output"], color=BLUE, marker="o", linewidth=2.2, markersize=6)
      for i, (_, row) in enumerate(sweep.iterrows()):
          ax.text(i, row["mean_daily_output"] + 260, f"{row['mean_daily_output']:,.0f}",
                  ha="center", fontsize=9, color=NAVY)

      ax2 = ax.twinx()
      ax2.bar(x, sweep["extra_gain_pct"].fillna(0.0), color=LIGHT, width=0.45, zorder=0)
      ax2.set_ylabel("Extra gain from this step (percentage points)", fontsize=9.5, color=GREY)
      ax2.bar(x, sweep["extra_gain_pct"].fillna(0.0), color=LIGHT, width=0.45, zorder=0)
      ax2.set_ylabel("Extra gain from this step (percentage points)", fontsize=9.5, color=GREY)
      ax2.tick_params(axis="y", colors=GREY)
      ax2.set_ylim(0, max(sweep["extra_gain_pct"].fillna(0.0)) * 3.2)
      ax2.spines["top"].set_visible(False)
      
      total = float(sweep["gain_vs_smallest_pct"].iloc[-1]) 
      ax.set_xticks(x)    
      ax.set_xticklabels([f"{int(m)} min\n{int(u):,} units" for m, u in
                          zip(sweep["buffer_minutes"], sweep["buffer_units"])], fontsize=8.5)
      ax.set_ylim(sweep["mean_daily_output"].min() * 0.93, sweep["mean_daily_output"].max() * 1.07)
      _style(ax, "Output against buffer stock between stages",
             f"Loosening the coupling recovers {total:.1f}% more output with no change to any "
             f"machine — but the grey bars flatten, so past ~60 minutes extra work-in-progress "
             f"buys almost nothing.",
             xlabel="Buffer size between each pair of stages",
             ylabel="Mean good units per day")
      return _save(fig, "13_buffer_returns.png")
  
  
  # --------------------------------------------------------------------------
def generate_all(df, sim=None):
      """Build every chart. The simulation is run once and shared by charts 12-13."""
      sim = sim or simulation.run_all(df)
      builders = [
          ("01 capacity ladder", lambda: chart_capacity_ladder(df)),
          ("02 OEE by machine", lambda: chart_oee_by_machine(df)),
          ("03 OEE loss breakdown", lambda: chart_oee_loss_breakdown(df)),
          ("04 Pareto - line", lambda: chart_pareto_line(df)),
          ("05 Pareto - bottleneck", lambda: chart_pareto_bottleneck(df)),
          ("06 cause by stage", lambda: chart_cause_stage_heatmap(df)),
          ("07 control chart - output", lambda: chart_control_output(df)),
          ("08 control chart - defects", lambda: chart_control_defect_rate(df)),
          ("09 bottleneck stability", lambda: chart_bottleneck_stability(df)),
          ("10 scenarios", lambda: chart_scenario_comparison(df)),
          ("11 cost-benefit", lambda: chart_cost_benefit(df)),
          ("12 simulated time states", lambda: chart_simulation_time_states(df, sim)),
          ("13 buffer returns", lambda: chart_buffer_returns(df, sim)),
      ]
      
      saved = [] 
      for label, build in builders:
          path = build()
          saved.append(path)
          print(f"  [{len(saved):>2}/13] {label:<32} -> {path.name}")
      return saved
  
      
if __name__ == "__main__":
      import data_generation
      
      data = data_generation.load()
      print("=" * 84)
      print(f"BUILDING ALL CHARTS -> {FIGURES_DIR}")
      print("=" * 84)
      paths = generate_all(data)
      print("=" * 84)
      print(f"{len(paths)} charts written. Open the figures folder in the sidebar to view them.")