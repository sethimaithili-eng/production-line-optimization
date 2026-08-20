import numpy as np
import pandas as pd
  
from capacity_analysis import (
    stage_capacity,
    machine_capacity,
    identify_bottleneck,
)


def _year_month(df):
    """Calendar month label, derived from the date so no extra column is needed."""
    return pd.to_datetime(df["production_date"]).dt.to_period("M").astype(str)


def constraint_ranking(stage_table):
    """Every stage ranked from most to least constraining."""
    t = stage_table.sort_values("effective_capacity_per_day").reset_index(drop=True)
    floor_capacity = float(t.loc[0, "effective_capacity_per_day"])

    t["constraint_rank"] = np.arange(1, len(t) + 1)
    # How much more this stage can deliver than the bottleneck can
    t["capacity_above_bottleneck_pct"] = (
        100.0 * (t["effective_capacity_per_day"] / floor_capacity - 1.0)).round(2)
    t["is_bottleneck"] = t["constraint_rank"] == 1

    cols = ["constraint_rank", "stage", "machines", "ideal_cycle_time_sec",
            "actual_cycle_time_sec", "theoretical_capacity_per_day",
            "effective_capacity_per_day", "capacity_above_bottleneck_pct",
            "capacity_utilisation_pct", "downtime_pct", "defect_pct", "oee",
            "is_bottleneck"]
    return t[cols]


def bottleneck_loss_decomposition(stage_table, production_days):
    """Split the bottleneck's lost capacity into stopped / slow / defective.

    The three losses multiply out of the OEE definition:

        good      = theoretical x A x P x Q
        downtime  = theoretical x (1 - A)
        slow      = theoretical x A x (1 - P)
        defective = theoretical x A x P x (1 - Q)

    so the four terms add back to theoretical capacity exactly. Each loss
    is priced in units per day and units per year, which is the input the
    scenario and cost modules need.
    """
    bn = stage_table.sort_values("effective_capacity_per_day").iloc[0]
    theoretical = float(bn["theoretical_capacity_per_day"])
    a = float(bn["availability"])
    p = float(bn["performance"])
    q = float(bn["quality"])

    good = theoretical * a * p * q
    downtime_units = theoretical * (1.0 - a)
    slow_units = theoretical * a * (1.0 - p)
    defect_units = theoretical * a * p * (1.0 - q)
    assert abs(good + downtime_units + slow_units + defect_units - theoretical) < 1.0, \
        "bottleneck loss decomposition does not add back to theoretical capacity"

    rows = [
        ("Stopped time (downtime)", downtime_units, "Availability"),
        ("Running slow (speed loss)", slow_units, "Performance"),
        ("Defective output (quality loss)", defect_units, "Quality"),
    ]
    table = pd.DataFrame([
        dict(loss_type=name,
            oee_component=component,
            units_lost_per_day=round(units, 0),
            units_lost_per_year=round(units * production_days, 0),
            pct_of_design_capacity=round(100.0 * units / theoretical, 2))
        for name, units, component in rows
    ]).sort_values("units_lost_per_day", ascending=False).reset_index(drop=True)

    summary = dict(
        bottleneck_stage=bn["stage"],
        design_capacity_per_day=round(theoretical, 0),
        demonstrated_capacity_per_day=round(good, 0),
        total_capacity_lost_per_day=round(theoretical - good, 0),
        total_capacity_lost_per_year=round((theoretical - good) * production_days, 0),
        largest_single_loss=table.loc[0, "loss_type"],
        largest_single_loss_units_per_day=float(table.loc[0, "units_lost_per_day"]),
        recoverable_pct_of_design=round(100.0 * (theoretical - good) / theoretical, 2),
    )
    return table, summary

  
def bottleneck_machines(df, bottleneck_stage):
    """The individual machines inside the bottleneck stage, worst first.

    Once the constraining STAGE is known, the next question is which of its
    machines is dragging it down -- that is where maintenance effort goes.
    """
    machines = machine_capacity(df)
    subset = machines[machines["stage"] == bottleneck_stage].copy()
    return subset.sort_values("effective_capacity_per_day").reset_index(drop=True)


def throughput_summary(df, stage_table):
    """Line throughput expressed per hour, per shift, per day and per year."""
    bn = stage_table.sort_values("effective_capacity_per_day").iloc[0]

    production_days = int(df["production_date"].nunique())
    n_shifts = int(df["shift"].nunique())
    minutes_per_shift = float(df["planned_time_min"].median())
    # Calendar production window per day, NOT machine-hours summed over machines
    line_hours_per_day = n_shifts * minutes_per_shift / 60.0

    per_day = float(bn["effective_capacity_per_day"])

    return dict(
        bottleneck_stage=bn["stage"],
        production_days_per_year=production_days,
        shifts_per_day=n_shifts,
        line_hours_per_day=round(line_hours_per_day, 2),
        good_units_per_hour=round(per_day / line_hours_per_day, 0),
        good_units_per_shift=round(per_day / n_shifts, 0),
        good_units_per_day=round(per_day, 0),
        good_units_per_year=round(per_day * production_days, 0),
    )
  
  
def stage_throughput_rates(df, stage_table):
    """Good units per hour of line time for every stage, for the ladder chart."""
    n_shifts = int(df["shift"].nunique())
    minutes_per_shift = float(df["planned_time_min"].median())
    line_hours_per_day = n_shifts * minutes_per_shift / 60.0

    out = stage_table[["stage_index", "stage", "theoretical_capacity_per_day",
                        "effective_capacity_per_day"]].copy()
    out["design_units_per_hour"] = (
        out["theoretical_capacity_per_day"] / line_hours_per_day).round(0)
    out["demonstrated_units_per_hour"] = (
        out["effective_capacity_per_day"] / line_hours_per_day).round(0)
    return out.sort_values("stage_index").reset_index(drop=True)

  
def monthly_stage_capacity(df):
    """Recompute the full capacity table separately for each calendar month."""
    d = df.copy()
    d["year_month"] = _year_month(d)

    frames = []
    for year_month, g in d.groupby("year_month", sort=True):
        table = stage_capacity(g)
        table.insert(0, "year_month", year_month)
        frames.append(table)
    return pd.concat(frames, ignore_index=True)
  
  
def monthly_line_capacity(monthly_stages):
    """The constraining stage and resulting line capacity, month by month."""
    idx = monthly_stages.groupby("year_month")["effective_capacity_per_day"].idxmin()
    out = monthly_stages.loc[idx, ["year_month", "stage", "effective_capacity_per_day",
                                    "oee", "downtime_pct"]]
    return out.rename(columns={
        "stage": "bottleneck_stage",
        "effective_capacity_per_day": "line_capacity_per_day",
        "oee": "bottleneck_oee",
        "downtime_pct": "bottleneck_downtime_pct",
    }).sort_values("year_month").reset_index(drop=True)


def bottleneck_stability(monthly_line):
    """Did the constraint stay in one place over the study period?"""
    counts = monthly_line["bottleneck_stage"].value_counts()
    n_months = int(len(monthly_line))
    dominant = str(counts.index[0])
    months_held = int(counts.iloc[0])

    if len(counts) == 1:
        verdict = (f"The bottleneck was {dominant} in all {n_months} months. It is a "
                    f"structural constraint, so targeted investment there is justified.")
    else:
        others = ", ".join(f"{k} ({v} months)" for k, v in counts.items() if k != dominant)
        verdict = (f"The bottleneck was {dominant} in {months_held} of {n_months} months, "
                    f"but moved in the rest: {others}. A wandering constraint means "
                    f"improvements must be re-checked after each change.")

    return dict(
        months_analysed=n_months,
        dominant_bottleneck=dominant,
        months_as_bottleneck=months_held,
        share_of_months_pct=round(100.0 * months_held / n_months, 1),
        constraint_moved=bool(len(counts) > 1),
        month_counts=counts.to_dict(),
        verdict=verdict,
    )


if __name__ == "__main__":
    import data_generation

    data = data_generation.load()
    stages = stage_capacity(data)
    days = int(data["production_date"].nunique())
    bn = identify_bottleneck(stages)
    print("=" * 105)
    print("CONSTRAINT RANKING (most constraining first)")
    print("=" * 105)
    ranking = constraint_ranking(stages)
    print(ranking[["constraint_rank", "stage", "effective_capacity_per_day",
                    "capacity_above_bottleneck_pct", "downtime_pct", "oee"]]
        .to_string(index=False))

    print("\n" + "=" * 105)
    print(f"WHAT THE BOTTLENECK COSTS  ({bn['bottleneck_stage']})")
    print("=" * 105)
    losses, loss_summary = bottleneck_loss_decomposition(stages, days)
    print(losses.to_string(index=False))
    print(f"\n  Design capacity        : {loss_summary['design_capacity_per_day']:,.0f} units/day")
    print(f"  Demonstrated capacity  : {loss_summary['demonstrated_capacity_per_day']:,.0f} good units/day")
    print(f"  Capacity lost          : {loss_summary['total_capacity_lost_per_day']:,.0f} units/day "
        f"({loss_summary['recoverable_pct_of_design']:.1f}% of design)")
    print(f"  Annualised loss        : {loss_summary['total_capacity_lost_per_year']:,.0f} units "
        f"over {days} production days")
    print(f"  Largest single loss    : {loss_summary['largest_single_loss']} "
        f"({loss_summary['largest_single_loss_units_per_day']:,.0f} units/day)")

    print("\n" + "=" * 105)
    print(f"MACHINES INSIDE THE BOTTLENECK STAGE (worst first)")
    print("=" * 105)
    print(bottleneck_machines(data, bn["bottleneck_stage"])[
        ["machine_id", "effective_capacity_per_day", "capacity_utilisation_pct",
        "downtime_pct", "breakdowns_per_shift", "oee"]].to_string(index=False))

    print("\n" + "=" * 105)
    print("LINE THROUGHPUT (set by the bottleneck)")
    print("=" * 105)
    for k, v in throughput_summary(data, stages).items():
        label = k.replace("_", " ").capitalize()
        print(f"  {label:<28}: {v:,}" if isinstance(v, (int, float)) else f"  {label:<28}: {v}")

    print("\n" + "=" * 105)
    print("IS THE BOTTLENECK STABLE?")
    print("=" * 105)
    monthly = monthly_line_capacity(monthly_stage_capacity(data))
    print(monthly.to_string(index=False))
    stability = bottleneck_stability(monthly)
    print("\n  " + stability["verdict"])

    print("\n" + "=" * 105)
    print("IMPROVEMENT CEILING")
    print("=" * 105)
    print(f"  Raising {bn['bottleneck_stage']} by more than "
          f"{bn['improvement_headroom_pct']:.1f}% moves the constraint to "
        f"{bn['second_constraint_stage']}.")
    print(f"  Maximum line capacity from fixing {bn['bottleneck_stage']} alone: "
        f"{bn['second_constraint_capacity_per_day']:,.0f} good units/day.")