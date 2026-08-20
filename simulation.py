import numpy as np
import pandas as pd
  
from config import SEED, SHIFTS, PLANNED_MINUTES_PER_SHIFT
from capacity_analysis import stage_capacity
from downtime_analysis import breakdown_metrics

N_SIM_DAYS = 90
BUFFER_MINUTES = 15
MEAN_MINOR_STOP_MIN = 8.0
BUFFER_SWEEP = (1, 5, 15, 30, 60, 120)
AVAILABILITY_TOLERANCE_PP = 3.0
CAPACITY_TOLERANCE_PCT = 2.0

MINUTES_PER_DAY = len(SHIFTS) * PLANNED_MINUTES_PER_SHIFT
STATES = ["running", "stopped", "starved", "blocked"]


def build_stage_params(df):
      """Reliability and speed parameters for each stage, measured from the data."""
      stages = stage_capacity(df)
      breakdowns = breakdown_metrics(df, by="stage").set_index("stage")

      params = []
      for _, s in stages.iterrows():
          stage = str(s["stage"])
          availability = float(s["availability"])

          rate_major = float(breakdowns.loc[stage, "breakdowns_per_shift"])
          mean_major = float(breakdowns.loc[stage, "mean_min_per_breakdown"])

          # Stoppage minutes per machine-shift that the model must reproduce
          total_stop_min = (1.0 - availability) * PLANNED_MINUTES_PER_SHIFT
          major_stop_min = rate_major * mean_major
          other_stop_min = max(0.0, total_stop_min - major_stop_min)
          rate_minor = other_stop_min / MEAN_MINOR_STOP_MIN

          # Machines are only exposed to failure while actually running
          running_min_per_shift = PLANNED_MINUTES_PER_SHIFT * availability

          params.append(dict(
              stage_index=int(s["stage_index"]),
              stage=stage,
              machines=int(s["machines"]),
              units_per_machine_minute=60.0 / float(s["ideal_cycle_time_sec"])
              * float(s["performance"]),
              quality=float(s["quality"]),
              target_availability=availability,
              p_major_per_running_min=rate_major / running_min_per_shift,
              mean_major_min=mean_major,
              p_minor_per_running_min=rate_minor / running_min_per_shift,
              mean_minor_min=MEAN_MINOR_STOP_MIN,
          ))
      return pd.DataFrame(params).sort_values("stage_index").reset_index(drop=True)


def _validate_availability(params, state_pct):
      """The model must reproduce the Availability measured from the data.
  
      This is the check that catches a mis-calibrated failure process. If the
      simulated stopped-time does not match 1 - Availability, the reliability
      model is wrong and every output downstream of it is untrustworthy.
      """
      target = 100.0 * (1.0 - params["target_availability"].to_numpy())
      simulated = state_pct["stopped"].to_numpy()
      gap = np.abs(simulated - target)
      worst = int(np.argmax(gap))
      assert gap.max() < AVAILABILITY_TOLERANCE_PP, (
          f"Simulated downtime does not match the measured Availability at "
          f"{params['stage'].iloc[worst]}: simulated {simulated[worst]:.2f}% vs "
          f"measured {target[worst]:.2f}%. The reliability calibration is wrong.")


def simulate(params, buffer_minutes=BUFFER_MINUTES, n_days=N_SIM_DAYS, seed=SEED,
               validate=True):
      """Run the coupled line and return daily output plus time-state accounting."""
      rng = np.random.default_rng(seed)
      n_stages = len(params)

      machines = params["machines"].to_numpy()
      rate = params["units_per_machine_minute"].to_numpy(dtype=float)
      quality = params["quality"].to_numpy(dtype=float)
      p_major = params["p_major_per_running_min"].to_numpy(dtype=float)
      mean_major = params["mean_major_min"].to_numpy(dtype=float)
      p_minor = params["p_minor_per_running_min"].to_numpy(dtype=float)
      mean_minor = params["mean_minor_min"].to_numpy(dtype=float)

      # One row per physical machine, mapped back to its stage
      stage_of_machine = np.repeat(np.arange(n_stages), machines)
      n_machines = len(stage_of_machine)
      down_remaining = np.zeros(n_machines, dtype=float)

      # Buffer size expressed in minutes of the slowest stage's output
      slowest_rate = float(np.min(rate * machines))
      buffer_capacity = buffer_minutes * slowest_rate
      buffers = np.zeros(n_stages - 1, dtype=float)

      state = np.zeros((n_stages, len(STATES)), dtype=float)   # machine-minutes
      daily_output = np.zeros(n_days, dtype=float)
      daily_scrap = np.zeros(n_days, dtype=float)

      for day in range(n_days):
          for _ in range(MINUTES_PER_DAY):
              # --- machine reliability -------------------------------------
              down_remaining = np.maximum(0.0, down_remaining - 1.0)
              up = down_remaining <= 0.0

              major_hit = up & (rng.random(n_machines) < p_major[stage_of_machine])
              minor_hit = up & ~major_hit & (rng.random(n_machines) < p_minor[stage_of_machine])

              if major_hit.any():
                  down_remaining[major_hit] = rng.exponential(
                      mean_major[stage_of_machine[major_hit]])
              if minor_hit.any():
                  down_remaining[minor_hit] = rng.exponential(
                      mean_minor[stage_of_machine[minor_hit]])
  
              # A machine that fails this minute is already stopped this minute
              up = down_remaining <= 0.0
              up_count = np.bincount(stage_of_machine[up], minlength=n_stages)

              # --- production, downstream first so space frees up first -----
              for i in range(n_stages - 1, -1, -1):
                  state[i, 1] += machines[i] - up_count[i]      # stopped
                  if up_count[i] == 0:
                      continue

                  capacity = up_count[i] * rate[i]
                  input_available = np.inf if i == 0 else buffers[i - 1]
                  # Only good units occupy the downstream buffer
                  space = np.inf if i == n_stages - 1 else (
                      buffer_capacity - buffers[i]) / quality[i]

                  processed = max(0.0, min(capacity, input_available, space))

                  # Attribute the up machines' minute proportionally
                  share = processed / capacity
                  state[i, 0] += up_count[i] * share            # running
                  idle = up_count[i] * (1.0 - share)
                  if idle > 0.0:
                      if input_available <= space:
                          state[i, 2] += idle                   # starved
                      else:
                          state[i, 3] += idle                   # blocked
  
                  good = processed * quality[i]
                  daily_scrap[day] += processed - good

                  if i > 0:
                      buffers[i - 1] -= processed
                  if i == n_stages - 1:
                      daily_output[day] += good
                  else:
                      buffers[i] += good

      machine_minutes = (n_days * MINUTES_PER_DAY * machines).astype(float)
      state_pct = pd.DataFrame(
          100.0 * state / machine_minutes[:, None], columns=STATES)
      state_pct.insert(0, "stage", params["stage"].to_numpy())

      # Every machine-minute must be in exactly one state
      assert np.allclose(state.sum(axis=1), machine_minutes, rtol=1e-9), \
          "Machine-minutes do not add up; the state accounting is incomplete."

      if validate:
          _validate_availability(params, state_pct)
  
      return dict(
          buffer_minutes=buffer_minutes,
          buffer_capacity_units=round(buffer_capacity, 0),
          n_days=n_days,
          daily_output=daily_output,
          mean_daily_output=float(daily_output.mean()),
          std_daily_output=float(daily_output.std()),
          min_daily_output=float(daily_output.min()),
          max_daily_output=float(daily_output.max()),
          total_scrap=float(daily_scrap.sum()),
          state_pct=state_pct,
          final_buffers=buffers.copy(),
      )
  
  
def compare_to_analytical(df, result):
      """Explain the gap between the analytical capacity and the simulated output.

      Two effects account for it, and they are separated here:
  
        Cumulative yield -- the bottleneck's good output still has to survive
          every downstream stage. Those stages scrap a little of it, so
          end-of-line output is below the bottleneck's own good output. The
          capacity model never multiplied the yields together.

        Coupling loss -- starvation and blocking. What remains after yield is
          accounted for.

      The simulated figure must not exceed the yield-adjusted capacity. A line
      cannot produce more than its constraint allows, so if it does, the model
      is wrong rather than the line being unexpectedly good.
      """
      stages = stage_capacity(df)
      ordered = stages.sort_values("stage_index")
      constraint = stages.sort_values("effective_capacity_per_day").iloc[0]

      analytical = float(constraint["effective_capacity_per_day"])
      downstream = ordered[ordered["stage_index"] > int(constraint["stage_index"])]
      cumulative_yield = float(np.prod(downstream["quality"].to_numpy())) if len(downstream) else 1.0

      yield_adjusted = analytical * cumulative_yield
      simulated = result["mean_daily_output"]

      assert simulated <= yield_adjusted * (1.0 + CAPACITY_TOLERANCE_PCT / 100.0), (
          f"Simulated output {simulated:,.0f}/day exceeds the constraint's "
          f"yield-adjusted capacity of {yield_adjusted:,.0f}/day. The line cannot "
          f"produce more than its bottleneck allows.")

      return dict(
          bottleneck_stage=str(constraint["stage"]),
          analytical_capacity_per_day=round(analytical, 0),
          downstream_cumulative_yield=round(cumulative_yield, 4),
          yield_adjusted_capacity_per_day=round(yield_adjusted, 0),
          simulated_output_per_day=round(simulated, 0),
          yield_loss_per_day=round(analytical - yield_adjusted, 0),
          coupling_loss_per_day=round(yield_adjusted - simulated, 0),
          coupling_loss_pct=round(100.0 * (yield_adjusted - simulated) / yield_adjusted, 2),
          total_gap_pct=round(100.0 * (analytical - simulated) / analytical, 2),
      )


def utilisation_table(params, state_pct):
      """Which stages are busy, which are waiting, and why."""
      table = state_pct.copy()
      table["measured_downtime_pct"] = (
          100.0 * (1.0 - params["target_availability"].to_numpy())).round(2)
      table["waiting_on_others_pct"] = (table["starved"] + table["blocked"]).round(2)
      table["limited_by"] = np.where(
          table["starved"] > table["blocked"], "upstream (starved)", "downstream (blocked)")
      table.loc[table["waiting_on_others_pct"] < 10.0, "limited_by"] = "itself (near-constraint)"
      return table[["stage", "running", "stopped", "measured_downtime_pct",
                    "starved", "blocked", "waiting_on_others_pct", "limited_by"]]

def buffer_sweep(params, sizes=BUFFER_SWEEP, n_days=None, seed=SEED):
      """How much output do buffers between stages actually buy?"""
      days = n_days or max(20, N_SIM_DAYS // 3)
      rows = []
      for size in sizes:
          result = simulate(params, buffer_minutes=size, n_days=days, seed=seed)
          state = result["state_pct"]
          rows.append(dict(
              buffer_minutes=size,
              buffer_units=result["buffer_capacity_units"],
              mean_daily_output=round(result["mean_daily_output"], 0),
              starved_pct=round(float(state["starved"].mean()), 2),
              blocked_pct=round(float(state["blocked"].mean()), 2),
          ))

      sweep = pd.DataFrame(rows)
      smallest = float(sweep["mean_daily_output"].iloc[0])
      sweep["gain_vs_smallest_pct"] = (
          100.0 * (sweep["mean_daily_output"] / smallest - 1.0)).round(2)
      sweep["extra_gain_pct"] = sweep["gain_vs_smallest_pct"].diff().round(2)
      return sweep

  
def buffer_insight(sweep):
      """Where does extra buffer stock stop earning its keep?"""
      gains = sweep.dropna(subset=["extra_gain_pct"])
      worthwhile = gains[gains["extra_gain_pct"] >= 0.5]

      if not len(worthwhile):
          return ("Extra buffer stock beyond the smallest level tested adds under 0.5% output "
                  "at every step, so the line is not meaningfully buffer-limited.")

      last = worthwhile.iloc[-1]
      total = float(sweep["gain_vs_smallest_pct"].iloc[-1])
      return (f"Buffer stock is worth adding up to about {last['buffer_minutes']:.0f} minutes of "
              f"bottleneck output ({last['buffer_units']:,.0f} units between stages); beyond "
              f"that each step adds under 0.5%. Going from the smallest to the largest buffer "
              f"tested raises output by {total:.1f}%, which is the share of the coupling loss "
              f"that buffer stock alone can recover, with no change to any machine. The "
              f"remainder is inherent to the stages themselves.")


def run_all(df, n_days=N_SIM_DAYS):
      """Everything the pipeline and dashboard need from the simulation."""
      params = build_stage_params(df)
      result = simulate(params, n_days=n_days)
      return dict(
          params=params,
          result=result,
          utilisation=utilisation_table(params, result["state_pct"]),
          comparison=compare_to_analytical(df, result),
          sweep=buffer_sweep(params),
      )
  
  
if __name__ == "__main__":
      import data_generation

      data = data_generation.load()
      params = build_stage_params(data)
  
      print("=" * 104)
      print("SIMULATION INPUTS (all calibrated from the measured data)")
      print("=" * 104)
      show = params[["stage", "machines", "units_per_machine_minute", "quality",
                     "target_availability", "p_major_per_running_min", "mean_major_min",
                     "p_minor_per_running_min"]].copy()
      show["units_per_machine_minute"] = show["units_per_machine_minute"].round(2)
      print(show.round(5).to_string(index=False))

      print(f"\nSimulating {N_SIM_DAYS} production days x {MINUTES_PER_DAY} minutes "
            f"({N_SIM_DAYS * MINUTES_PER_DAY:,} time steps)...")
      result = simulate(params)

      print("\n" + "=" * 104)
      print("SIMULATED LINE OUTPUT")
      print("=" * 104)
      print(f"  Buffer between stages    : {result['buffer_minutes']} minutes "
            f"({result['buffer_capacity_units']:,.0f} units)")
      print(f"  Mean good units per day  : {result['mean_daily_output']:,.0f}")
      print(f"  Day-to-day std deviation : {result['std_daily_output']:,.0f}")
      print(f"  Worst / best day         : {result['min_daily_output']:,.0f} / "
            f"{result['max_daily_output']:,.0f}")

      print("\n" + "=" * 104)
      print("WHERE EACH MACHINE-MINUTE GOES (% of each stage's own machine-minutes)")
      print("=" * 104)
      print(utilisation_table(params, result["state_pct"]).round(2).to_string(index=False))
      print("\n  'stopped' should track 'measured_downtime_pct' -- that is the reliability model")
      print("  reproducing the real data. 'starved' and 'blocked' are caused by OTHER stages")
      print("  and appear in no OEE calculation anywhere in this project.")

      print("\n" + "=" * 104)
      print("SIMULATED vs ANALYTICAL CAPACITY -- ACCOUNTING FOR THE GAP")
      print("=" * 104)
      comp = compare_to_analytical(data, result)
      print(f"  Analytical bottleneck capacity ({comp['bottleneck_stage']}) : "
            f"{comp['analytical_capacity_per_day']:,.0f} units/day")
      print(f"  x cumulative downstream yield ({comp['downstream_cumulative_yield']:.4f})  : "
            f"{comp['yield_adjusted_capacity_per_day']:,.0f} units/day")
      print(f"  Simulated actual output                       : "
            f"{comp['simulated_output_per_day']:,.0f} units/day")
      print(f"\n  Lost to downstream scrap    : {comp['yield_loss_per_day']:,.0f} units/day")
      print(f"  Lost to starvation/blocking : {comp['coupling_loss_per_day']:,.0f} units/day "
            f"({comp['coupling_loss_pct']:.1f}%)")
      print(f"  Total gap vs analytical     : {comp['total_gap_pct']:.1f}%")

      print("\n" + "=" * 104)
      print("WHAT DO BUFFERS BETWEEN STAGES BUY?")
      print("=" * 104)
      sweep = buffer_sweep(params)
      print(sweep.to_string(index=False))
      print(f"\n  {buffer_insight(sweep)}")
      print("\n  Note: sweep rows use a shorter run than the headline figure above, so the")
      print("  15-minute row will differ slightly. Compare rows to each other, not to the top.")