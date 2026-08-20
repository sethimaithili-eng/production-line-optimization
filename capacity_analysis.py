import numpy as np
import pandas as pd

from oee_analysis import _apq

  
def stage_capacity(df):
    """Capacity table, one row per process stage, in flow order."""
    n_days = df["production_date"].nunique()
    rows = []

    for (stage_index, stage), g in df.groupby(["stage_index", "stage"], sort=True):
        r = _apq(g)
        ideal_cycle = float(g["ideal_cycle_time_sec"].iloc[0])
        machines = int(g["machines_at_stage"].iloc[0])
        operators = int(g["operators"].iloc[0])

        planned_min_per_day = r["planned_time_min"] / n_days
        operating_min_per_day = r["operating_time_min"] / n_days

        theoretical_per_day = planned_min_per_day * 60.0 / ideal_cycle
        effective_per_day = theoretical_per_day * r["oee"]

        units_per_day = r["units_produced"] / n_days
        good_per_day = r["good_units"] / n_days

        # Demonstrated average cycle time: operating seconds per unit made
        actual_cycle = ((r["operating_time_min"] * 60.0 / r["units_produced"])
                        if r["units_produced"] > 0 else np.nan)

        rows.append(dict(
            stage_index=stage_index,
            stage=stage,
            machines=machines,
            operators_per_shift=operators,
            ideal_cycle_time_sec=round(ideal_cycle, 2),
            actual_cycle_time_sec=round(actual_cycle, 2),
            available_hours_per_day=round(planned_min_per_day / 60.0, 2),
            operating_hours_per_day=round(operating_min_per_day / 60.0, 2),
            theoretical_capacity_per_day=round(theoretical_per_day, 0),
            effective_capacity_per_day=round(effective_per_day, 0),
            actual_units_per_day=round(units_per_day, 0),
            actual_good_units_per_day=round(good_per_day, 0),
            capacity_utilisation_pct=round(100.0 * units_per_day / theoretical_per_day, 2),
            downtime_pct=round(100.0 * (1.0 - r["availability"]), 2),
            defect_pct=round(100.0 * (1.0 - r["quality"]), 2),
            availability=r["availability"],
            performance=r["performance"],
            quality=r["quality"],
            oee=r["oee"],
        ))

    table = pd.DataFrame(rows).sort_values("stage_index").reset_index(drop=True)                                                                                                                                           
    _validate_capacity(table)
    return table


def machine_capacity(df):
    """Same capacity view but per individual machine, for utilisation charts."""
    n_days = df["production_date"].nunique()
    rows = []
    for (stage_index, stage, machine_id), g in df.groupby(
        ["stage_index", "stage", "machine_id"], sort=True):
        r = _apq(g)
        ideal_cycle = float(g["ideal_cycle_time_sec"].iloc[0])
        planned_min_per_day = r["planned_time_min"] / n_days
        theoretical_per_day = planned_min_per_day * 60.0 / ideal_cycle
        units_per_day = r["units_produced"] / n_days

        rows.append(dict(
            stage_index=stage_index,
            stage=stage,
            machine_id=machine_id,
            theoretical_capacity_per_day=round(theoretical_per_day, 0),
            effective_capacity_per_day=round(theoretical_per_day * r["oee"], 0),
            actual_units_per_day=round(units_per_day, 0),
            capacity_utilisation_pct=round(100.0 * units_per_day / theoretical_per_day, 2),
            downtime_pct=round(100.0 * (1.0 - r["availability"]), 2),
            oee=r["oee"],
            breakdowns_per_shift=round(float(g["breakdown_count"].mean()), 2),
        ))

    return pd.DataFrame(rows).sort_values(
        ["stage_index", "machine_id"]).reset_index(drop=True)


def _validate_capacity(table):
    """Consistency checks on the capacity arithmetic."""
    assert (table["theoretical_capacity_per_day"] > 0).all(), \
        "non-positive theoretical capacity"
    assert (table["effective_capacity_per_day"] > 0).all(), \
        "non-positive effective capacity"
    assert (table["effective_capacity_per_day"]
            <= table["theoretical_capacity_per_day"] + 1).all(), \
        "effective capacity exceeds theoretical capacity"
    assert (table["actual_cycle_time_sec"]
            >= table["ideal_cycle_time_sec"] - 1e-6).all(), \
        "actual cycle time faster than design cycle time"
    assert (table["capacity_utilisation_pct"] <= 100.01).all(), \
        "capacity utilisation above 100%"

    # The identity: theoretical x OEE must reproduce observed good output
    gap = (table["effective_capacity_per_day"]
            - table["actual_good_units_per_day"]).abs()
    tolerance = 0.01 * table["actual_good_units_per_day"] + 2.0
    assert (gap <= tolerance).all(), (
        "effective capacity does not reproduce actual good output -- "
        "OEE or capacity maths is inconsistent"
    )
    return True
  
  
def identify_bottleneck(stage_table):
    """Find the constraint, the runner-up, and the resulting line capacity."""
    ranked = stage_table.sort_values("effective_capacity_per_day").reset_index(drop=True)
    first, second = ranked.iloc[0], ranked.iloc[1]

    line_capacity = float(first["effective_capacity_per_day"])
    headroom_pct = 100.0 * (float(second["effective_capacity_per_day"]) / line_capacity - 1.0)

    return dict(
        bottleneck_stage=first["stage"],
        bottleneck_capacity_per_day=line_capacity,                                                                                                                                                                         
        bottleneck_utilisation_pct=float(first["capacity_utilisation_pct"]),
        bottleneck_oee=float(first["oee"]),
        bottleneck_downtime_pct=float(first["downtime_pct"]),
        bottleneck_cycle_time_sec=float(first["actual_cycle_time_sec"]),
        second_constraint_stage=second["stage"],
        second_constraint_capacity_per_day=float(second["effective_capacity_per_day"]),
        # How far the bottleneck can be improved before the next stage takes over
        improvement_headroom_pct=round(headroom_pct, 2),
        line_capacity_per_day=line_capacity,
    )


def bottleneck_vs_downtime(stage_table):                                                                                                                                                                                   
    """Show explicitly whether the worst-downtime stage is the bottleneck.

    Returns a dict plus a plain-English verdict, computed from the data --
    this is the 'downtime is not the same as bottleneck' evidence.
    """
    worst_downtime = stage_table.sort_values("downtime_pct", ascending=False).iloc[0]
    constraint = stage_table.sort_values("effective_capacity_per_day").iloc[0]
    same = bool(worst_downtime["stage"] == constraint["stage"])

    if same:
        verdict = (f"{constraint['stage']} is both the worst-downtime stage and the "
                    f"bottleneck, so in this line the two coincide.")
    else:
        verdict = (
            f"{worst_downtime['stage']} loses the most time "
            f"({worst_downtime['downtime_pct']:.1f}% downtime) but is NOT the "
            f"bottleneck: even after those losses it can still deliver "
            f"{worst_downtime['effective_capacity_per_day']:,.0f} good units/day. "
            f"{constraint['stage']} is the constraint at only "
            f"{constraint['effective_capacity_per_day']:,.0f} good units/day, "
            f"because its cycle time of {constraint['actual_cycle_time_sec']:.2f} s "
            f"because its cycle time of {constraint['actual_cycle_time_sec']:.2f} s "
            f"across {constraint['machines']} machines caps output before downtime "
            f"is even considered."
        )
      
    return dict(
        worst_downtime_stage=worst_downtime["stage"],
        worst_downtime_pct=float(worst_downtime["downtime_pct"]),
        bottleneck_stage=constraint["stage"],
        bottleneck_downtime_pct=float(constraint["downtime_pct"]),
        same_stage=same,
        verdict=verdict,
    )
  
  
if __name__ == "__main__":
    import data_generation
      
    data = data_generation.load()
    stages = stage_capacity(data)
    
    print("=" * 100)
    print("PRODUCTION LINE CAPACITY LADDER (flow order)")
    print("=" * 100) 
    show = ["stage", "machines", "ideal_cycle_time_sec", "actual_cycle_time_sec",
            "theoretical_capacity_per_day", "effective_capacity_per_day",
            "capacity_utilisation_pct", "downtime_pct", "oee"]
    print(stages[show].to_string(index=False))
      
    bn = identify_bottleneck(stages)
    print("\n" + "=" * 100)
    print("BOTTLENECK")
    print("=" * 100)
    print(f"  Bottleneck stage        : {bn['bottleneck_stage']}")
    print(f"  Line capacity           : {bn['bottleneck_capacity_per_day']:,.0f} good units/day")
    print(f"  Bottleneck utilisation  : {bn['bottleneck_utilisation_pct']:.2f}%")
    print(f"  Bottleneck OEE          : {bn['bottleneck_oee']:.2%}")
    print(f"  Second constraint       : {bn['second_constraint_stage']} "
        f"({bn['second_constraint_capacity_per_day']:,.0f} good units/day)")
    print(f"  Headroom before the second constraint takes over: "
        f"{bn['improvement_headroom_pct']:.1f}%")
      
    print("\n" + "=" * 100)
    print("DOWNTIME IS NOT THE SAME AS THE BOTTLENECK")
    print("=" * 100)
    print("  " + bottleneck_vs_downtime(stages)["verdict"])