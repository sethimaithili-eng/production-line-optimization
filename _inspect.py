import pandas as pd

import data_generation
import scenario_analysis
import cost_analysis

df = data_generation.load()

  
def describe(name, thing):
      if isinstance(thing, pd.DataFrame):
          print(f"{name}: DataFrame {thing.shape}")
          print(f"    cols = {list(thing.columns)}")
          print(f"    head =\n{thing.head(3).to_string(index=False)}")
      elif isinstance(thing, dict):
          print(f"{name}: dict keys = {list(thing.keys())}")
      elif isinstance(thing, (list, tuple)):
          print(f"{name}: {type(thing).__name__} len={len(thing)}")
          for i, item in enumerate(thing):
              print(f"    [{i}] {type(item).__name__}")
              if isinstance(item, pd.DataFrame):
                  print(f"        cols = {list(item.columns)}")
              elif isinstance(item, dict):
                  print(f"        keys = {list(item.keys())}")
              else:
                  print(f"        value = {str(item)[:200]}")
      else:
          print(f"{name}: {type(thing).__name__} = {str(thing)[:200]}")

  
print("=" * 80)
result = scenario_analysis.run_all_scenarios(df)
describe("run_all_scenarios", result)

  # The first element is the scenario summary table
summary = result[0]

print("=" * 80)
for label, call in [
      ("cost_benefit", lambda: cost_analysis.cost_benefit(summary)),
      ("break_even_realisation", lambda: cost_analysis.break_even_realisation(summary)),
      ("sensitivity_margin", lambda: cost_analysis.sensitivity_margin(summary)),
      ("sensitivity_realisation", lambda: cost_analysis.sensitivity_realisation(summary)),
      ("scenario_costs", lambda: cost_analysis.scenario_costs()),
  ]:
      print("-" * 80)
      try:
          describe(label, call())
      except Exception as exc:
          print(f"{label}: FAILED -> {type(exc).__name__}: {exc}")

print("-" * 80)
try:
      describe("scenario_insights", scenario_analysis.scenario_insights(summary))
except Exception as exc:
      print(f"scenario_insights: FAILED -> {type(exc).__name__}: {exc}")