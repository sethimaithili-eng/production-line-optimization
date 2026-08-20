import numpy as np
import pandas as pd
  
from config import (SEED, START_DATE, N_DAYS, REST_WEEKDAY, SHIFTS,
                    PLANNED_MINUTES_PER_SHIFT, STAGES, STAGE_PARAMS,
                    DOWNTIME_CAUSES, DATA_DIR)

  # Map each shop-floor cause to its column name in the dataset
CAUSE_COLUMNS = {
    "Equipment Breakdown":     "dt_breakdown_min",
    "Material Shortage":       "dt_material_min",
    "Changeover / Setup":      "dt_changeover_min",
    "Quality Issue":           "dt_quality_min",
    "Operator Unavailability": "dt_operator_min",
    "Minor Stoppages":         "dt_minor_stops_min",
}

MAJOR_EVENT_PROB = 0.02      # ~2% of shifts suffer a major breakdown
RELIABILITY_DRIFT = 0.10     # downtime grows 10% over the 12 months
CSV_PATH = DATA_DIR / "production_data.csv"


def _production_dates():
    """Calendar of production days: every day except the weekly rest day."""
    all_days = pd.date_range(START_DATE, periods=N_DAYS, freq="D")
    return [d for d in all_days if d.weekday() != REST_WEEKDAY]


def _machine_roster(rng):
    """Build the machine list, giving each machine a persistent condition factor.

    The condition factor multiplies that machine's downtime, so within a
    stage one machine can be materially less reliable than the others --
    which is what makes a per-machine OEE ranking meaningful.
    """
    roster = []
    for stage_index, stage in enumerate(STAGES, start=1):
        p = STAGE_PARAMS[stage]
        for m in range(1, p["n_machines"] + 1):
            roster.append(dict(
                stage=stage,
                stage_index=stage_index,
                machine_id=f"{p['machine_prefix']}-{m:02d}",
                condition=float(rng.uniform(0.85, 1.20)),
            ))
    return roster
  
  
def generate(save=True):
    """Generate the full synthetic production dataset and return it."""
    rng = np.random.default_rng(SEED)
    dates = _production_dates()
    machines = _machine_roster(rng)
    n_days = len(dates)

    rows = []
    for day_i, date in enumerate(dates):
        # Gradual reliability degradation across the 12 months
        drift = 1.0 + RELIABILITY_DRIFT * (day_i / max(n_days - 1, 1))

        for shift in SHIFTS:
            for mach in machines:
                stage = mach["stage"]
                p = STAGE_PARAMS[stage]
                planned = float(PLANNED_MINUTES_PER_SHIFT)

                # ---------- 1. total downtime for this shift ----------
                expected_dt = planned * p["downtime_frac"] * mach["condition"] * drift
                # gamma(shape=4, scale=0.25) has mean 1.0 and CV 0.5
                downtime = expected_dt * rng.gamma(4.0, 0.25)

                major_event = rng.random() < MAJOR_EVENT_PROB
                if major_event:
                    downtime += planned * rng.uniform(0.15, 0.35)

                # never lose more than 70% of the shift
                downtime = float(np.clip(downtime, 0.0, planned * 0.70))

                # ---------- 2. split downtime across the six causes ----------
                shares = rng.dirichlet(np.array(p["cause_weights"]) * 25.0)
                if major_event:
                    # a major event is by definition a breakdown, so push
                    # weight onto that cause while keeping shares summing to 1
                    breakdown_vector = np.zeros(len(DOWNTIME_CAUSES))
                    breakdown_vector[0] = 1.0
                    shares = 0.45 * breakdown_vector + 0.55 * shares
                cause_minutes = downtime * shares

                # ---------- 3. operating time and output ----------
                operating = planned - downtime
                speed_factor = float(np.clip(
                    rng.normal(p["performance"], 0.04), 0.50, 0.995))
                units = int(np.floor(
                    operating * 60.0 * speed_factor / p["ideal_cycle_sec"]))
                units = max(units, 0)

                # ---------- 4. quality ----------
                defect_rate = float(np.clip(
                    rng.normal(p["defect_rate"], p["defect_rate"] * 0.35),
                    0.0, 0.25))
                defective = int(rng.binomial(units, defect_rate)) if units else 0
                rework = int(rng.binomial(defective, p["rework_share"])) if defective else 0
                scrap = defective - rework
                good = units - defective          # first-pass good units

                # ---------- 5. events and realised cycle time ----------
                breakdowns = int(rng.poisson(p["breakdowns_mean"] * mach["condition"]))
                if major_event:
                    breakdowns += 1
                actual_cycle = (operating * 60.0 / units) if units > 0 else np.nan

                row = dict(
                    production_date=date.date().isoformat(),
                    month=date.strftime("%Y-%m"),
                    weekday=date.strftime("%a"),
                    shift=shift,
                    stage=stage,
                    stage_index=mach["stage_index"],
                    machine_id=mach["machine_id"],
                    machines_at_stage=p["n_machines"],
                    operators=p["operators"],
                    planned_time_min=round(planned, 2),
                    downtime_min=round(downtime, 2),
                    operating_time_min=round(operating, 2),
                    setup_time_min=round(float(cause_minutes[2]), 2),
                    breakdown_count=breakdowns,
                    units_produced=units,
                    defective_units=defective,
                    rework_units=rework,
                    scrap_units=scrap,
                    good_units=good,
                    ideal_cycle_time_sec=p["ideal_cycle_sec"],
                    actual_cycle_time_sec=(round(actual_cycle, 3)
                                            if units > 0 else np.nan),
                    major_event=int(major_event),
                )
                # one column per downtime cause
                for cause, minutes in zip(DOWNTIME_CAUSES, cause_minutes):
                    row[CAUSE_COLUMNS[cause]] = round(float(minutes), 2)

                rows.append(row)

    df = pd.DataFrame(rows)
    validate(df)

    if save:
        df.to_csv(CSV_PATH, index=False)
    return df


def validate(df):
    """Logical checks -- the dataset is wrong if any of these fail."""
    assert len(df) > 0, "no rows generated"

    # No impossible physical quantities
    assert (df["operating_time_min"] >= 0).all(), "negative operating time"
    assert (df["downtime_min"] >= 0).all(), "negative downtime"
    assert (df["units_produced"] >= 0).all(), "negative production"
    assert (df["good_units"] >= 0).all(), "negative good units"
    assert (df["defective_units"] <= df["units_produced"]).all(), \
        "more defects than units produced"
    assert (df["rework_units"] <= df["defective_units"]).all(), \
        "more rework than defects"
    assert (df["scrap_units"] >= 0).all(), "negative scrap"

    # Time must balance: planned = operating + downtime
    time_gap = (df["planned_time_min"]
                - df["operating_time_min"]
                - df["downtime_min"]).abs()
    assert (time_gap < 0.01).all(), "planned time does not equal operating + downtime"

    # The six causes must sum to total downtime
    cause_sum = df[list(CAUSE_COLUMNS.values())].sum(axis=1)
    assert ((cause_sum - df["downtime_min"]).abs() < 0.05).all(), \
        "downtime causes do not sum to total downtime"

    # Actual cycle time can never beat the machine's design cycle time
    ran = df["units_produced"] > 0
    assert (df.loc[ran, "actual_cycle_time_sec"]
            >= df.loc[ran, "ideal_cycle_time_sec"] - 1e-6).all(), \
        "actual cycle time faster than ideal -- OEE Performance would exceed 100%"

    return True

  
def load():
    """Load the dataset from CSV, generating it first if it is missing."""
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH)
    return generate()


if __name__ == "__main__":
    data = generate()
    print(f"Rows generated: {len(data):,}")
    print(f"Production days: {data['production_date'].nunique()}")
    print(f"Machines: {data['machine_id'].nunique()}")
    print(f"Saved to: {CSV_PATH}")