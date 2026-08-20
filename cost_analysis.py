import numpy as np
import pandas as pd
  
from config import CONTRIBUTION_MARGIN_PER_UNIT, COST_ASSUMPTIONS, EXTRA_MACHINES
from scenario_analysis import run_all_scenarios

DEMAND_REALISATION = 1.0 
MARGIN_MULTIPLIERS = (0.50, 0.75, 1.00, 1.25, 1.50)
REALISATION_LEVELS = (0.50, 0.70, 0.85, 1.00)
HORIZON_YEARS = 3

  
def scenario_costs():
      """Map each scenario to its one-time and recurring costs.

      Every figure is an assumption drawn from config.COST_ASSUMPTIONS.
      """
      c = COST_ASSUMPTIONS 
      machine_capex = c["machine_capex"] * EXTRA_MACHINES
      machine_operating = c["machine_annual_operating"] * EXTRA_MACHINES

      return {
          "A": dict(one_time=0.0, annual=0.0,
                    items="none (baseline)"),
          "B": dict(one_time=machine_capex, annual=machine_operating,
                    items=f"{EXTRA_MACHINES} machine purchase + annual running cost"),
          "C": dict(one_time=0.0, annual=c["maintenance_annual"],
                    items="enhanced maintenance programme (annual)"),
          "D": dict(one_time=c["smed_one_time"], annual=c["smed_annual"],
                    items="SMED setup, tooling and training + annual upkeep"),
          "E": dict(one_time=0.0, annual=c["quality_annual"],
                    items="quality improvement programme (annual)"),
          "F": dict(one_time=machine_capex + c["smed_one_time"],
                    annual=machine_operating + c["maintenance_annual"]
                    + c["smed_annual"] + c["quality_annual"],
                    items="all of the above combined"),
      }


def cost_benefit(summary, margin=CONTRIBUTION_MARGIN_PER_UNIT,
                   realisation=DEMAND_REALISATION):
      """Build the cost-benefit table for every scenario."""
      costs = scenario_costs()
      rows = []
  
      for _, s in summary.iterrows():
          code = s["scenario"]
          cost = costs[code]

          gain_units = float(s["annual_gain_units"])
          benefit = gain_units * margin * realisation
          net_annual = benefit - cost["annual"]

          if cost["one_time"] <= 0:
              payback = 0.0 if net_annual > 0 else np.nan
          elif net_annual > 0:
              payback = cost["one_time"] / net_annual
          else:
              payback = np.nan
  
          total_cost_horizon = cost["one_time"] + cost["annual"] * HORIZON_YEARS
          benefit_cost_ratio = (benefit * HORIZON_YEARS / total_cost_horizon
                                if total_cost_horizon > 0 else np.nan)

          rows.append(dict(
              scenario=code,
              name=s["name"],
              annual_gain_units=round(gain_units, 0),
              gain_pct=s["gain_pct"],
              one_time_cost=round(cost["one_time"], 0),
              annual_cost=round(cost["annual"], 0),
              annual_benefit=round(benefit, 0),
              net_annual_benefit=round(net_annual, 0),
              payback_years=round(payback, 2) if np.isfinite(payback) else np.nan,
              benefit_cost_ratio_3yr=round(benefit_cost_ratio, 2)
              if np.isfinite(benefit_cost_ratio) else np.nan,
              cumulative_net_3yr=round(net_annual * HORIZON_YEARS - cost["one_time"], 0),
              cost_items=cost["items"],
          ))

      table = pd.DataFrame(rows)
      _validate(table)
      return table


def _validate(table):
      baseline = table[table["scenario"] == "A"].iloc[0]
      assert baseline["annual_benefit"] == 0, "the baseline scenario cannot generate a benefit"
      assert baseline["one_time_cost"] == 0 and baseline["annual_cost"] == 0, \
          "the baseline scenario cannot incur a cost"

      improvements = table[table["scenario"] != "A"]
      assert (improvements["annual_gain_units"] > 0).all(), \
          "an improvement scenario produced no extra output"
      return True

  
def break_even_realisation(summary, margin=CONTRIBUTION_MARGIN_PER_UNIT):
      """What share of the extra output must be sold to cover the annual cost?"""
      costs = scenario_costs()
      rows = [] 

      for _, s in summary.iterrows():
          code = s["scenario"]
          if code == "A":
              continue

          gain_units = float(s["annual_gain_units"])
          annual_cost = costs[code]["annual"]
          full_benefit = gain_units * margin
  
          share = annual_cost / full_benefit if full_benefit > 0 else np.nan
          rows.append(dict(
              scenario=code,
              name=s["name"],
              annual_cost=round(annual_cost, 0),
              benefit_at_full_demand=round(full_benefit, 0),
              break_even_realisation_pct=round(100.0 * share, 1),
              robustness=("robust -- covers its cost even if most extra output is unsold"
                          if share < 0.35 else
                          "moderate -- needs a substantial share of extra output sold"
                          if share < 0.60 else
                          "fragile -- depends on selling nearly all extra output"),
          ))
      return pd.DataFrame(rows)
  
  
def sensitivity_margin(summary, multipliers=MARGIN_MULTIPLIERS):
      """How payback and net benefit move as the assumed margin changes."""
      rows = []
      for m in multipliers:
          margin = CONTRIBUTION_MARGIN_PER_UNIT * m
          table = cost_benefit(summary, margin=margin)
          for _, r in table[table["scenario"] != "A"].iterrows():
              rows.append(dict(
                  margin_multiplier=m,
                  margin_per_unit=round(margin, 2),
                  scenario=r["scenario"],
                  net_annual_benefit=r["net_annual_benefit"],
                  payback_years=r["payback_years"],
              ))
      long = pd.DataFrame(rows)
      return long.pivot(index="scenario", columns="margin_per_unit",
                        values="payback_years"), long

  
def sensitivity_realisation(summary, levels=REALISATION_LEVELS):
      """How payback moves if only part of the extra output can be sold."""
      rows = []
      for level in levels: 
          table = cost_benefit(summary, realisation=level)
          for _, r in table[table["scenario"] != "A"].iterrows():
              rows.append(dict(
                  demand_realisation=level,
                  scenario=r["scenario"],
                  net_annual_benefit=r["net_annual_benefit"],
                  payback_years=r["payback_years"],
              ))
      long = pd.DataFrame(rows)
      return long.pivot(index="scenario", columns="demand_realisation",
                        values="net_annual_benefit"), long


def recommendation(cb, break_even):
      """Reasoned recommendation, derived from the computed table."""
      improvements = cb[cb["scenario"] != "A"].copy()
      viable = improvements[improvements["net_annual_benefit"] > 0]

      if not len(viable):
          return ["No scenario covers its own annual cost under these assumptions."]

      no_capital = viable[viable["one_time_cost"] == 0].sort_values(
          "net_annual_benefit", ascending=False)
      by_payback = viable[viable["one_time_cost"] > 0].sort_values("payback_years")
      biggest = viable.sort_values("net_annual_benefit", ascending=False).iloc[0]
      weakest = viable.sort_values("benefit_cost_ratio_3yr").iloc[0]
      fragile = break_even.sort_values("break_even_realisation_pct", ascending=False).iloc[0]

      notes = []

      if len(no_capital):
          first = no_capital.iloc[0]
          notes.append(
              f"Start with scenario {first['scenario']} ({first['name']}). It needs no capital "
              f"outlay, so there is nothing to pay back, and it returns "
              f"INR {first['net_annual_benefit']:,.0f} net per year "
              f"({first['benefit_cost_ratio_3yr']:.1f}x its cost over {HORIZON_YEARS} years).")

      if len(by_payback):
          first = by_payback.iloc[0]
          notes.append(
              f"Of the options requiring capital, scenario {first['scenario']} "
              f"({first['name']}) pays back fastest at {first['payback_years']:.2f} years on "
              f"INR {first['one_time_cost']:,.0f} invested.")

      notes.append(
          f"Scenario {biggest['scenario']} delivers the largest absolute return at "
          f"INR {biggest['net_annual_benefit']:,.0f} net per year, but it is also the largest "
          f"commitment (INR {biggest['one_time_cost']:,.0f} capital and "
          f"INR {biggest['annual_cost']:,.0f} per year).")

      notes.append(
          f"Scenario {weakest['scenario']} is the least efficient use of money "
          f"({weakest['benefit_cost_ratio_3yr']:.2f}x over {HORIZON_YEARS} years) and should be "
          f"the last one funded.")

      notes.append(
          f"The result most exposed to assumption risk is scenario {fragile['scenario']}: it "
          f"needs {fragile['break_even_realisation_pct']:.0f}% of its extra output to be sold "
          f"before it covers its annual cost. {fragile['robustness'].capitalize()}.")

      notes.append(
          "Sequencing matters as much as selection: because relieving the bottleneck moves the "
          "constraint, the scenarios should be funded one at a time and the capacity analysis "
          "re-run after each, rather than approved as a single package.")

      return notes 

  
if __name__ == "__main__":
      import data_generation

      data = data_generation.load()
      summary, _ = run_all_scenarios(data)

      print("=" * 108)
      print("FINANCIAL ASSUMPTIONS -- ILLUSTRATIVE VALUES, NOT REAL COMPANY DATA")
      print("=" * 108)
      print(f"  Contribution margin per unit      : INR {CONTRIBUTION_MARGIN_PER_UNIT:,.2f}  (ASSUMPTION)")
      for key, value in COST_ASSUMPTIONS.items():
          print(f"  {key:<34}: INR {value:,.0f}  (ASSUMPTION)")
      print(f"  Demand realisation                : {DEMAND_REALISATION:.0%}  (ASSUMPTION -- "
            f"share of extra output assumed sold)")
      print(f"  Discounting                       : none; simple undiscounted payback")

      cb = cost_benefit(summary)

      print("\n" + "=" * 108)
      print("COST-BENEFIT BY SCENARIO")
      print("=" * 108)
      print(cb[["scenario", "annual_gain_units", "one_time_cost", "annual_cost",
                "annual_benefit", "net_annual_benefit", "payback_years",
                "benefit_cost_ratio_3yr"]].to_string(index=False))
      print("\n  payback_years = 0.00 means no capital outlay is required.")
      print("  NaN means the scenario does not cover its annual cost.")

      print("\n" + "=" * 108)
      print(f"CUMULATIVE NET BENEFIT OVER {HORIZON_YEARS} YEARS")
      print("=" * 108)
      print(cb[["scenario", "name", "cumulative_net_3yr", "cost_items"]].to_string(index=False))

      be = break_even_realisation(summary)
      print("\n" + "=" * 108)
      print("HOW MUCH OF THE EXTRA OUTPUT MUST ACTUALLY BE SOLD?")
      print("=" * 108)
      print(be[["scenario", "annual_cost", "benefit_at_full_demand",
                "break_even_realisation_pct", "robustness"]].to_string(index=False))

      pivot_margin, _ = sensitivity_margin(summary)
      print("\n" + "=" * 108)
      print("SENSITIVITY: PAYBACK YEARS vs CONTRIBUTION MARGIN (INR per unit)")
      print("=" * 108)
      print(pivot_margin.round(2).to_string())
      print("\n  0.00 = no capital outlay. NaN = does not cover its annual cost.")

      pivot_demand, _ = sensitivity_realisation(summary)
      print("\n" + "=" * 108)
      print("SENSITIVITY: NET ANNUAL BENEFIT (INR) vs SHARE OF EXTRA OUTPUT SOLD")
      print("=" * 108)
      print(pivot_demand.round(0).to_string())

      print("\n" + "=" * 108)
      print("RECOMMENDATION")
      print("=" * 108)
      for i, note in enumerate(recommendation(cb, be), start=1):
          print(f"  {i}. {note}")