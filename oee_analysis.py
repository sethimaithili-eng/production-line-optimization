import numpy as np
import pandas as pd

  # Widely used industry reference point for a "world class" line
WORLD_CLASS_OEE = 0.85


def _apq(g):
    """Compute OEE components and the minute-based loss breakdown for a group."""
    planned = float(g["planned_time_min"].sum())
    operating = float(g["operating_time_min"].sum())
    units = float(g["units_produced"].sum())
    good = float(g["good_units"].sum())
    defective = float(g["defective_units"].sum())
    rework = float(g["rework_units"].sum())
  
    # Ideal (design) minutes needed for the units actually made
    ideal_all_min = float((g["ideal_cycle_time_sec"] * g["units_produced"]).sum()) / 60.0
    ideal_good_min = float((g["ideal_cycle_time_sec"] * g["good_units"]).sum()) / 60.0

    availability = operating / planned if planned > 0 else 0.0
    performance = ideal_all_min / operating if operating > 0 else 0.0
    quality = good / units if units > 0 else 0.0
    oee = availability * performance * quality

    downtime_loss_min = planned - operating
    speed_loss_min = operating - ideal_all_min
    quality_loss_min = ideal_all_min - ideal_good_min
    productive_min = ideal_good_min

    return dict(
        planned_time_min=round(planned, 1),
        operating_time_min=round(operating, 1),                                                                                                                                                                           
        units_produced=int(units),
        good_units=int(good),
        defective_units=int(defective),
        rework_units=int(rework),
        availability=round(availability, 4),                                                                                                                                                                              
        performance=round(performance, 4),
        quality=round(quality, 4),
        oee=round(oee, 4),
        downtime_loss_min=round(downtime_loss_min, 1),
        speed_loss_min=round(speed_loss_min, 1),
        quality_loss_min=round(quality_loss_min, 1),
        productive_time_min=round(productive_min, 1),
    )
  
  
def _dominant_loss(row):
    """Which of the three OEE components is costing the most minutes."""
    losses = {
        "Availability": row["downtime_loss_min"],
        "Performance": row["speed_loss_min"],
        "Quality": row["quality_loss_min"],
    }
    return max(losses, key=losses.get)


def _table(df, keys):
    """Build an OEE table grouped by the given key columns."""                                                                                                                                                            
    rows = []
    for key, g in df.groupby(keys, sort=True):
        if not isinstance(key, tuple):
            key = (key,)
        record = dict(zip(keys, key))
        record.update(_apq(g))
        rows.append(record)

    out = pd.DataFrame(rows)
    out["dominant_loss"] = out.apply(_dominant_loss, axis=1)                                                                                                                                                              
    _validate_time_identity(out)
    return out


def _validate_time_identity(table):
    """Planned time must equal the sum of the four loss buckets."""
    total = (table["downtime_loss_min"] + table["speed_loss_min"]
            + table["quality_loss_min"] + table["productive_time_min"])
    gap = (total - table["planned_time_min"]).abs()
    assert (gap < 1.0).all(), (
        "OEE time-loss buckets do not add up to planned time -- "
        "the OEE decomposition is inconsistent"
    )
    # Components must be genuine percentages
    for col in ("availability", "performance", "quality", "oee"):
        assert (table[col] >= 0).all(), f"{col} is negative"
        assert (table[col] <= 1.0001).all(), f"{col} exceeds 100%"
    return True

  
def oee_by_machine(df):
    """OEE for every individual machine, ranked worst-to-best OEE."""
    table = _table(df, ["stage_index", "stage", "machine_id"])
    table = table.sort_values("oee").reset_index(drop=True)
    table["oee_rank_worst_first"] = np.arange(1, len(table) + 1)
    return table


def oee_by_stage(df):
    """OEE aggregated to the process-stage level, in flow order."""
    table = _table(df, ["stage_index", "stage"])
    return table.sort_values("stage_index").reset_index(drop=True)


def oee_by_month(df):
    """Monthly OEE, used for the trend chart."""
    return _table(df, ["month"]).sort_values("month").reset_index(drop=True)


def oee_line(df):
    """Single whole-line OEE summary."""
    record = _apq(df)
    record["dominant_loss"] = _dominant_loss(record)
    return record
  
  
def loss_breakdown_pct(df):
    """Where planned production time goes, as a percentage of planned time.

    This answers 'where is production time being lost?' in the form a
    plant manager expects: four numbers that sum to 100%.
    """
    r = _apq(df)
    planned = r["planned_time_min"]
    return dict(
        downtime_pct=round(100.0 * r["downtime_loss_min"] / planned, 2),
        speed_loss_pct=round(100.0 * r["speed_loss_min"] / planned, 2),
        quality_loss_pct=round(100.0 * r["quality_loss_min"] / planned, 2),
        productive_pct=round(100.0 * r["productive_time_min"] / planned, 2),
    )


if __name__ == "__main__":
    import data_generation

    data = data_generation.load()

    line = oee_line(data)
    print("=" * 62)
    print("WHOLE-LINE OEE")
    print("=" * 62)
    print(f"  Availability : {line['availability']:.2%}")
    print(f"  Performance  : {line['performance']:.2%}")
    print(f"  Quality      : {line['quality']:.2%}")
    print(f"  OEE          : {line['oee']:.2%}")
    print(f"  Biggest loss : {line['dominant_loss']}")

    print("\nWHERE PLANNED TIME GOES (% of planned production time)")
    for k, v in loss_breakdown_pct(data).items():
        print(f"  {k:18s}: {v:6.2f}%")

    print("\nOEE BY STAGE (flow order)")
    stage = oee_by_stage(data)
    print(stage[["stage", "availability", "performance", "quality",
                "oee", "dominant_loss"]].to_string(index=False))

    print("\nWORST 5 MACHINES BY OEE")
    mach = oee_by_machine(data)
    print(mach.head(5)[["machine_id", "stage", "availability", "performance",
                        "quality", "oee", "dominant_loss"]].to_string(index=False))