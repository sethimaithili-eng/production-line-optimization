from pathlib import Path
  
  # ----------------------------------------------------------------------
  # Paths (relative to project root, so the repo is portable)
  # ----------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RESULTS_DIR = ROOT_DIR / "results"
FIGURES_DIR = RESULTS_DIR / "figures"

for _d in (DATA_DIR, RESULTS_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

  # ----------------------------------------------------------------------
  # Reproducibility
  # ----------------------------------------------------------------------
SEED = 42

  # ----------------------------------------------------------------------
  # Plant calendar
  # ----------------------------------------------------------------------
FACILITY_NAME = "BharatPack Consumer Products - Line 3"
PRODUCT_NAME = "500 ml packaged beverage"

START_DATE = "2024-04-01"
N_DAYS = 365                       # 12 months of operations
REST_WEEKDAY = 6                   # Sunday (Mon=0) - no production
SHIFTS = ["A (06:00-14:00)", "B (14:00-22:00)"]
PLANNED_MINUTES_PER_SHIFT = 480    # 8 h of planned production time

  # ----------------------------------------------------------------------
  # Production line: sequential stages, in flow order
  # ----------------------------------------------------------------------
STAGES = [
    "Raw Material Preparation",
    "Mixing",
    "Processing",
    "Filling",
    "Packaging",
    "Quality Inspection",
    "Dispatch",
]

  # ----------------------------------------------------------------------
  # The six standard downtime causes tracked on the shop floor
  # ----------------------------------------------------------------------
DOWNTIME_CAUSES = [
    "Equipment Breakdown",
    "Material Shortage",
    "Changeover / Setup",
    "Quality Issue",
    "Operator Unavailability",
    "Minor Stoppages",
]
  
  # ----------------------------------------------------------------------
  # Per-stage machine parameters
  #
  #   machine_prefix   : machine ID prefix (e.g. FIL -> FIL-01, FIL-02)
  #   n_machines       : machines running in parallel at this stage
  #   ideal_cycle_sec  : design cycle time, seconds per unit, PER MACHINE
  #                      (the "nameplate" speed used for OEE Performance)
  #   downtime_frac    : long-run share of planned time lost to all stops
  #                      (so Availability ~ 1 - downtime_frac)
  #   performance      : long-run speed factor vs ideal cycle time (<= 1.0)
  #   defect_rate      : share of produced units failing first-pass quality
  #   rework_share     : share of those defects that can be reworked
  #                      (the remainder is scrapped)
  #   breakdowns_mean  : mean number of breakdown events per shift
  #   operators        : operators manning the stage per shift
  #   cause_weights    : how downtime_frac splits across DOWNTIME_CAUSES
  #
  # DESIGN NOTE (documented deliberately, see README):
  #   Filling has the LOWEST effective capacity -> it is the bottleneck.
  #   Packaging has the HIGHEST downtime but MORE capacity headroom, so it
  #   is NOT the bottleneck. This is what makes the analysis worth doing:
  #   the noisiest machine is not the constraint.
  # ----------------------------------------------------------------------
STAGE_PARAMS = {
    "Raw Material Preparation": dict(
        machine_prefix="RMP", n_machines=2, ideal_cycle_sec=2.2,
        downtime_frac=0.07, performance=0.96,
        defect_rate=0.003, rework_share=0.50,
        breakdowns_mean=0.15, operators=2,
        cause_weights=[0.20, 0.35, 0.15, 0.05, 0.15, 0.10],
    ),
    "Mixing": dict(
        machine_prefix="MIX", n_machines=2, ideal_cycle_sec=2.6,
        downtime_frac=0.09, performance=0.94,
        defect_rate=0.012, rework_share=0.60,
        breakdowns_mean=0.25, operators=2,
        cause_weights=[0.30, 0.15, 0.25, 0.10, 0.10, 0.10],
    ),
    "Processing": dict(
        machine_prefix="PRC", n_machines=2, ideal_cycle_sec=2.4,
        downtime_frac=0.08, performance=0.95,
        defect_rate=0.008, rework_share=0.50,
        breakdowns_mean=0.22, operators=2,
        cause_weights=[0.28, 0.17, 0.20, 0.12, 0.13, 0.10],
    ),
    "Filling": dict(
        machine_prefix="FIL", n_machines=3, ideal_cycle_sec=4.0,
        downtime_frac=0.15, performance=0.90,
        defect_rate=0.025, rework_share=0.55,
        breakdowns_mean=0.45, operators=3,
        cause_weights=[0.32, 0.08, 0.28, 0.12, 0.06, 0.14],
    ),
    "Packaging": dict(
        machine_prefix="PKG", n_machines=3, ideal_cycle_sec=3.4,
        downtime_frac=0.22, performance=0.93,
        defect_rate=0.015, rework_share=0.70,
        breakdowns_mean=0.60, operators=4,
        cause_weights=[0.22, 0.10, 0.30, 0.06, 0.07, 0.25],
    ),
    "Quality Inspection": dict(
        machine_prefix="QCI", n_machines=2, ideal_cycle_sec=2.3,
        downtime_frac=0.06, performance=0.92,
        defect_rate=0.001, rework_share=0.30,
        breakdowns_mean=0.10, operators=3,
        cause_weights=[0.18, 0.12, 0.10, 0.20, 0.25, 0.15],
    ),
    "Dispatch": dict(
        machine_prefix="DSP", n_machines=2, ideal_cycle_sec=2.0,
        downtime_frac=0.05, performance=0.94,
        defect_rate=0.001, rework_share=0.20,
        breakdowns_mean=0.08, operators=3,
        cause_weights=[0.15, 0.20, 0.10, 0.05, 0.35, 0.15],
    ),
}

  # ----------------------------------------------------------------------
  # Improvement scenario knobs (applied at the bottleneck stage)
  # ----------------------------------------------------------------------
DOWNTIME_REDUCTION = 0.30      # Scenario C: cut bottleneck downtime 30%
CHANGEOVER_REDUCTION = 0.50    # Scenario D: SMED halves changeover time
DEFECT_REDUCTION = 0.50        # Scenario E: halve the defect rate
EXTRA_MACHINES = 1             # Scenario B: add 1 parallel machine

  # ----------------------------------------------------------------------
  # FINANCIAL ASSUMPTIONS -- SIMULATED, NOT REAL COMPANY DATA
  # Used only to rank interventions against each other.
  # ----------------------------------------------------------------------
CONTRIBUTION_MARGIN_PER_UNIT = 4.50    # INR of contribution per good unit

COST_ASSUMPTIONS = dict(
    # Scenario B: one additional filling machine
    machine_capex=4_500_000,           # INR, installed
    machine_annual_operating=900_000,  # INR/yr: operators, power, spares
    # Scenario C: planned-maintenance / reliability programme
    maintenance_annual=800_000,        # INR/yr
    # Scenario D: SMED / quick-changeover programme
    smed_one_time=650_000,             # INR, tooling + training
    smed_annual=150_000,               # INR/yr sustaining
    # Scenario E: quality improvement programme
    quality_annual=600_000,            # INR/yr
)

# Control-chart setting for statistical process control
CONTROL_CHART_SIGMA = 3        # +/- 3 sigma control limits
CONTROL_CHART_STAGE = "Filling"   # stage charted in detail