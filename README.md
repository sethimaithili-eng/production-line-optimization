  # Production Line Bottleneck & Capacity Optimization

  A manufacturing engineering case study of a seven-stage FMCG packaging line,
  built to answer one question: **which stage limits output, and what is the
  cheapest way to raise it?**

  The short answer is that the line's sickest equipment is not its constraint.
  Packaging has the worst downtime (24.60%), the worst OEE (69.00%) and the
  three worst machines on the line — and fixing all of it would raise output by
  nothing. Filling is the constraint, because a 4.0-second cycle time caps its
  nameplate capacity below every other stage's.

  **No machine learning, no AI, no neural networks.** Every technique here is
  industrial engineering: capacity analysis, OEE, Pareto analysis, statistical
  process control, discrete simulation, and cost–benefit analysis. Every number
  in this README is produced by the code and can be regenerated with one command.

  ---

  ## 1. The line
  
  | # | Stage | Machines | Ideal cycle (s) | Operators/shift |
  |---|-------|----------|-----------------|-----------------|
  | 1 | Raw Material Preparation | 2 | 2.2 | 2 |
  | 2 | Mixing | 2 | 2.6 | 2 |
  | 3 | Processing | 2 | 2.4 | 2 |
  | 4 | **Filling** | 3 | **4.0** | 3 |
  | 5 | Packaging | 3 | 3.4 | 4 |
  | 6 | Quality Inspection | 2 | 2.3 | 3 |
  | 7 | Dispatch | 2 | 2.0 | 3 |

  Facility: *BharatPack Consumer Products – Line 3* (a fictional plant).
  Product: a 500 ml packaged beverage.
  Schedule: 2 shifts × 480 planned minutes, six days a week.

  ---

  ## 2. Headline results
  
  | Metric | Value |
  |---|---|
  | Records analysed | 10,016 machine-shift records over 313 production days |
  | Whole-line OEE | **80.21%** (A 86.92% × P 93.04% × Q 99.18%) |
  | Largest OEE loss | Availability |
  | **Bottleneck** | **Filling — 31,337 good units/day** |
  | Second constraint | Packaging — 35,068/day (11.9% headroom) |
  | Worst OEE stage | Packaging, 69.00% — *not* the bottleneck |
  | Worst downtime stage | Packaging, 24.60% — *not* the bottleneck |
  | Improvement ceiling from Filling alone | +11.9%, then the constraint moves |
  | Best combined scenario | +19.25% capacity |
  | Simulated actual output | 28,788/day, 8.1% below the analytical ceiling |
  | Validation checks passing | 16 of 16 |

  ---
  
  ## 3. Why the bottleneck is not the worst machine

  This is the central finding, and it is deliberately counter-intuitive.

  |  | Filling | Packaging |
  |---|---|---|
  | Downtime | 17.07% | **24.60%** (worst) |
  | OEE | 72.54% | **69.00%** (worst) |
  | Nameplate capacity | **43,200/day** (lowest) | 50,824/day |
  | **Effective capacity** | **31,337/day** ← constraint | 35,068/day |

  Packaging loses more time than Filling, but it starts from so much more
  nameplate capacity that it still ends up 11.9% faster. **Downtime is a
  symptom; capacity is the constraint.** A maintenance league table would have
  sent the improvement budget to the wrong stage.

  Three further checks confirm the constraint is real rather than an artefact:

  - **It is structural, not seasonal.** Filling had the lowest effective                                                                                                                                                    
    capacity in **all 12 months**, within a narrow band of 30,802–31,761/day.
  - **It is a design problem, not a sick machine.** Filling's three machines
    produce 10,277 / 10,328 / 10,734 units/day — near-identical. There is no
    bad machine to repair; the cycle time itself is the limit.
  - **The do-nothing baseline declines.** Downtime per shift drifts from
    60.41 to 67.12 minutes over the year (+11%), so output falls without
    intervention.

  ### Where the constraint's capacity goes

  Of Filling's 43,200/day nameplate:

  | Loss | Units/day |
  |---|---|
  | Downtime loss | 7,374 |
  | Speed loss | 3,690 |
  | Quality loss | 797 |
  | **Good output** | **31,337** |

  ---

  ## 4. Downtime analysis — and an honest Pareto                                                                                                                                                                            
  
  Across the whole line, **four of six causes are needed to reach 80%** of
  downtime (80.19% cumulative). This is *not* a clean 80/20, and it has not been
  forced into one. The losses are genuinely more spread out than the rule
  predicts, and saying so is more useful than manufacturing a tidy result.

  The ranking at the constraint differs from the line-wide ranking, and only the
  constraint's ranking matters for output:

  | Rank | Cause at Filling | Share of Filling downtime |
  |---|---|---|
  | 1 | Equipment Breakdown | 34.01% |
  | 2 | Changeover / Setup | 27.26% |

  Those two are worth roughly **1.24 million saleable units per year** — which is
  why the improvement scenarios target maintenance and changeover rather than
  being chosen for convenience.

  Two further findings shaped the recommendations:

  - **Filling and Packaging fail in opposite ways.** Packaging: 0.65 failures
    per shift averaging 42.2 minutes. Filling: 0.49 failures averaging 56.4
    minutes. Packaging fails often and briefly; Filling fails rarely and badly.
    They need different countermeasures — Packaging needs reliability work,
    Filling needs faster response and spares availability.
  - **Three of seven stages have non-maintenance root causes.** Quality
    Inspection and Dispatch are dominated by *Operator Unavailability*, and Raw
    Material Preparation by *Material Shortage*. Sending a maintenance team to
    those stages would achieve nothing.

  ---
  
  ## 5. Statistical process control — and choosing the right chart

  Control charts on the constraint's daily output use an **individuals (I)
  chart** with sigma estimated from the mean moving range (σ̂ = MR̄ / 1.128).
  Limits are set from a 90-day Phase I baseline and then applied forward, so the
  chart tests later production against an established baseline rather than
  against itself.

  Result: **19 of 313 days out of control (6.1%)** on the constraint's output —
  a process that is mostly stable with identifiable special causes.

  ### The p-chart failure, and why it is kept in the project

  The textbook chart for a defect *rate* is a p-chart. Applied here it flagged
  **141 of 313 days (50.5%)** as out of control — an obviously useless result.

  The diagnosis is **overdispersion**. With ~32,135 units inspected per day, the
  binomial limits collapse to ±0.262 percentage points, which is **4.7× narrower**
  than the real day-to-day variation. The binomial model assumes every unit has
  the same independent defect probability; in a real plant, whole shifts share
  conditions, so days vary far more than binomial sampling allows.

  The individuals chart on the same data flags **1 day**. That is the correct
  tool, and it is what the project uses. The p-chart is retained and documented
  because the diagnosis is more valuable than the chart: *"I built the textbook
  chart, it failed, I worked out why, and I used the right tool instead."*

  **Cp/Cpk is deliberately absent.** Those indices compare process spread to an
  engineering specification limit. There is no specification limit on daily
  output — a plant target is a business goal, not a tolerance — so computing Cpk
  against one would be meaningless.

  ---
  
  ## 6. Improvement scenarios

  All six scenarios recompute **all seven stages** and take the minimum
  effective capacity, so the constraint is free to move. Nothing is asserted.

  | | Scenario | Line capacity/day | Gain | Constraint after |
  |---|---|---|---|---|
  | A | Baseline | 31,339 | — | Filling |
  | B | Add 1 machine at the bottleneck | 35,067 | **+11.90%** | → Packaging |
  | C | Cut bottleneck downtime 30% | 33,275 | +6.18% | Filling |
  | D | Cut changeover 50% (SMED) | 32,220 | +2.81% | Filling |
  | E | Improve quality 50% | 32,116 | +2.48% | Filling |
  | F | Combined (B+C+D+E) | 37,371 | **+19.25%** | → Packaging |

  ### Gains do not add up

  The four single improvements total **+23.37%** on paper. Doing all of them
  delivers **+19.25%**. A naive additive model would overstate the result by
  **21%** — because once Filling is relieved, Packaging becomes the constraint
  and further Filling improvements stop converting into output.

  ### Two sweeps that show where to stop

  - **Extra machines at Filling:** 1, 2, 3 and 4 extra machines all deliver
    **exactly +11.90%**. The second machine buys literally nothing, because
    Packaging has already become the constraint. Buy one, then stop.
  - **Downtime reduction:** gains rise linearly up to about 55% reduction, then
    plateau. Beyond roughly 57%, further reduction is wasted effort.
  Under scenario F the line is very nearly balanced — Packaging 37,371 vs Mixing
  37,436, **0.17% apart**. That is a natural stopping point, and it emerged from
  the arithmetic rather than being chosen.

  ---
  
  ## 7. Cost–benefit analysis

  > **Every financial value in this project is an assumption used for
  > simulation.** No real company's revenue, costs or margins are used or
  > implied. The key assumption is a **contribution margin of ₹4.50 per unit** —
  > contribution margin, not selling price, because only the margin on
  > *incremental* units is a real benefit.

  | | Scenario | Capital | Annual cost | Net annual benefit | Payback | 3-yr BCR |
  |---|---|---|---|---|---|---|
  | B | Add machine | ₹4,500,000 | ₹900,000 | ₹4,350,658 | 1.03 yr | 2.19 |
  | C | Cut downtime | — | ₹800,000 | ₹1,925,722 | no capital | **3.41** |
  | D | SMED | ₹650,000 | ₹150,000 | ₹1,088,283 | **0.60 yr** | 3.38 |
  | E | Quality | — | ₹600,000 | ₹496,762 | no capital | 1.83 |
  | F | Combined | ₹5,150,000 | ₹2,450,000 | **₹6,046,846** | 0.85 yr | 2.04 |

  Scenarios C and E show no payback period because they require **no capital
  outlay** — there is nothing to pay back. That is a feature of the analysis,
  not a missing number.

  ### Sensitivity testing killed a scenario
  
  Every option was stress-tested against the two assumptions it depends on:
  the margin per unit, and how much of the extra output can actually be sold.

  | Scenario | Break-even share of extra output sold |
  |---|---|
  | D | 12.1% |
  | B | 17.1% |
  | F | 28.8% |
  | C | 29.4% |
  | **E** | **54.7%** |

  **Scenario E is fragile in three separate ways.** It needs more than half its
  extra output sold to break even; at half the assumed margin its payback
  disappears entirely; and at 50% demand realisation its net benefit turns
  **negative (−₹51,619)**. Every other scenario stays profitable under all three
  stresses. E looked acceptable in the headline table and failed the moment an
  assumption was leaned on.

  **No NPV or discounting is used**, because the cost of capital for a fictional
  plant is unknowable and inventing a discount rate would add false precision to
  an already-assumed cash flow. Simple undiscounted payback is stated for what
  it is.

  ---
  
  ## 8. Discrete simulation — what OEE cannot see

  Every analysis above measures each stage independently. A real line is
  **coupled**: when Filling stops, Packaging runs out of work (**starvation**),
  and Mixing has nowhere to send product (**blocking**). Neither loss appears in
  any OEE figure, because from the affected stage's own point of view nothing
  went wrong.

  A minute-by-minute simulation of 90 production days (86,400 time steps) with
  finite buffers between stages measures them. It is written in plain Python —
  **SimPy was considered and rejected**, because a fixed-sequence line with fixed
  cycle times does not need a process-based framework, and the time-stepped model
  is shorter, faster and fully explainable.

  ### The constraint confirms itself
  
  | Stage | Running | Own breakdown | Starved | Blocked | Waiting on others |
  |---|---|---|---|---|---|
  | Raw Material Prep | 61.42% | 8.54% | 0.00% | 30.04% | 30.04% |
  | Mixing | 73.79% | 11.79% | 0.50% | 13.92% | 14.42% |
  | Processing | 66.52% | 9.60% | 3.67% | 20.22% | 23.88% |
  | **Filling** | **77.52%** | 18.17% | 1.78% | 2.54% | **4.32%** |
  | Packaging | 62.02% | 26.19% | 11.22% | 0.56% | 11.78% |
  | Quality Inspection | 62.69% | 8.31% | 28.85% | 0.14% | 29.00% |
  | Dispatch | 53.33% | 6.00% | 40.67% | 0.00% | 40.67% |

  **Filling is the only stage on the line that is not waiting for somebody
  else** (4.32%, against 40.67% at Dispatch). The simulation was never told
  which stage was the bottleneck — it identified the same one from coupled flow
  alone. Two independent methods, one answer.

  Note also that **Packaging loses more time to its own breakdowns (26.19%) than
  to starvation (11.22%) and still is not the constraint.** Its equipment is
  genuinely the worst on the line. It is genuinely not what limits output.

  ### The analytical model is an upper bound

  | | Units/day |
  |---|---|
  | Analytical bottleneck capacity | 31,337 |                                                                                                                                                                               
  | × cumulative downstream yield (0.9828) | 30,799 |
  | **Simulated actual output** | **28,788** |
  | Lost to downstream scrap | 538 |
  | Lost to starvation and blocking | **2,011 (6.5%)** |

  Coupling costs **2,011 units/day** — about 629,000 units/year, or ₹2.83M of
  contribution margin at the assumed margin. That is the same order of magnitude
  as scenario C, and it requires no new machine.

  **This means every scenario capacity figure above is an upper bound, 8.1%
  optimistic.** The *relative* gains (+11.90%, +19.25%) hold, because coupling
  loss scales roughly with throughput. The absolute unit counts do not.

  ### Buffers buy capacity with no capital

  | Buffer between stages | Output/day | Extra gain |
  |---|---|---|
  | 1 min (40 units) | 22,530 | — |
  | 5 min (202) | 26,595 | +18.04 pp |
  | 15 min (605) | 28,706 | +9.37 pp |
  | 30 min (1,211) | 29,575 | +3.86 pp |
  | 60 min (2,422) | 30,147 | +2.54 pp |
  | 120 min (4,844) | 30,292 | +0.64 pp |

  Loosening the coupling recovers **34.5%** more output with no change to any
  machine. The practical stopping point is **around 60 minutes** — beyond that,
  quadrupling work-in-progress buys 0.6%. On a real beverage line, hygiene and
  shelf-life would cap the allowable buffer regardless of what the arithmetic
  prefers.

  ---
  
  ## 9. Recommendations, in order

  1. **Fund Scenario C first (enhanced maintenance at Filling).** No capital at
     risk, ₹1.93M net annual benefit, best 3-year return of any option at 3.41×.
  2. **Then Scenario D (SMED at Filling).** ₹650,000 buys the fastest payback on
     the board at 0.60 years, and changeover is 27.26% of the constraint's
     downtime.
  3. **Review buffer sizing before buying anything.** ~2,000 units of WIP between
     stages recovers output comparable to a capital project, subject to hygiene
     and shelf-life limits.
  4. **Only then consider Scenario B (a fourth Filling machine).** It is the
     largest single gain and pays back in 1.03 years — but buy exactly one. A
     second adds nothing.
  5. **Do not fund Scenario E as a capacity measure.** It needs 54.7% of extra
     output sold to break even and goes negative at 50% demand realisation. If
     quality work is justified, justify it on customer or compliance grounds,
     not on capacity.
  6. **Re-run the capacity analysis after each intervention.** The constraint
     moves to Packaging as soon as Filling is relieved. Funding improvements in
     sequence, with a re-analysis between each, avoids spending on a stage that
     has stopped being the limit.

  ---
  
  ## 10. How to run it

  Requires Python 3.10+.

  ```bash
  pip install -r requirements.txt
  python run_pipeline.py

  That single command regenerates the dataset, runs all nine analysis modules,
  writes 45 tables to results/, builds 13 charts into results/figures/,
  prints the headline KPIs and finishes with the validation checklist.

  The random seed is fixed at 42, so deleting data/ and results/ and
  re-running reproduces every number in this README exactly.

  Individual modules can also be run on their own, each printing its own
  analysis:

  python src/capacity_analysis.py
  python src/bottleneck_analysis.py
  python src/oee_analysis.py
  python src/downtime_analysis.py
  python src/process_control.py
  python src/scenario_analysis.py
  python src/cost_analysis.py
  python src/simulation.py
  
  ---

  11. Project structure

  production-line-optimization/
  ├── run_pipeline.py              one command reproduces everything
  ├── requirements.txt             5 packages, none of them AI/ML
  ├── README.md
  ├── data/
  │   └── production_data.csv      10,016 machine-shift records
  ├── results/
  │   ├── *.csv                    45 analysis tables
  │   ├── kpi_summary.txt          headline numbers
  │   ├── validation_checklist.csv 16 checks
  │   └── figures/                 13 charts
  └── src/
      ├── config.py                every parameter and assumption, one file
      ├── data_generation.py       synthetic dataset + integrity checks
      ├── capacity_analysis.py     theoretical vs effective capacity
      ├── bottleneck_analysis.py   constraint identification and stability
      ├── oee_analysis.py          the only place A, P and Q are defined
      ├── downtime_analysis.py     Pareto, MTTR/MTBF proxies, changeover
      ├── process_control.py       control charts, overdispersion diagnosis
      ├── scenario_analysis.py     scenarios A–F and what-if sweeps
      ├── cost_analysis.py         payback, BCR, sensitivity
      ├── simulation.py            coupled flow, starvation and blocking
      └── visualizations.py        all 13 charts

  ---

  12. Validation
  
  The pipeline finishes with 16 automated checks, all of which pass:

  - The dataset passes its own integrity checks
  - No negative or impossible downtime; downtime never exceeds planned time
  - Good + defective units never exceed units produced
  - Every OEE component lies between 0 and 1
  - OEE = Availability × Performance × Quality for every stage
  - Effective capacity reconciles with theoretical × OEE to within 0.002%
  - The bottleneck is the lowest effective capacity, not the highest downtime
  - The bottleneck is not simply the lowest OEE either
  - The constraint is the same stage in all 12 months
  - The baseline scenario shows exactly zero gain
  - The combined scenario gain is less than the sum of individual gains
  - The Pareto result was not forced to 80/20
  - Simulated downtime matches measured availability at every stage (≤1.59 pp)
  - Simulated output never exceeds the constraint's capacity
  - All 13 charts were written to disk
  - No financial figure is presented as a real company value

  Individual modules also assert internal identities at runtime — for example
  that the four OEE time buckets sum to planned time, and that the loss
  decomposition at the constraint sums back to nameplate capacity.

  ---

  13. Assumptions and limitations
  
  Stated plainly, because a study that hides its limitations cannot be trusted
  on its findings.

  The data is synthetic. No real plant was measured. Parameters in
  config.py were chosen to produce a realistic and deliberately
  counter-intuitive line — one where the worst equipment is not the constraint —
  because that is the case worth demonstrating. The analysis is real; the plant
  is not.

  All financial values are assumptions. The ₹4.50 contribution margin and
  every cost figure are inputs for simulation, labelled as such in config.py
  every cost figure are inputs for simulation, labelled as such in config.py
  and in every printed output. No real company's financials are used.
  
  Demand is assumed able to absorb extra output. This is why break-even
  demand realisation is computed for every scenario rather than assuming all
  extra units sell.
  
  The dataset does not enforce material conservation between stages. Each
  stage's record reflects its own capability, not what the stage upstream
  actually handed it. That coupling is exactly what simulation.py exists to
  model, and the 8.1% gap between the two models is the size of the omission.
  
  The simulation lumps non-breakdown downtime into 8-minute stoppages. The
  data records how many breakdowns occurred but not how many material, 
  changeover or operator stoppages, so their frequency is derived from an assumed
  mean duration. Splitting stoppages into major and minor classes matters, 
  because one long stop starves the next stage far more than several short ones
  totalling the same time.
  
  Simulated downtime runs 0.2–1.6 percentage points above the measured
  value, because a machine failing during a minute is counted as stopped for
  that whole minute. The bias is small and always pessimistic, which is the safe
  direction to be wrong.
  
  No NPV, IRR or discounting. The cost of capital is unknowable here, and
  inventing one would add false precision.
  
  Cp/Cpk is not computed, because there is no engineering specification limit
  on daily output to compute it against.
  
  Small rounding differences (~2 units, 0.006%) exist between modules that
  rebuild the same figure by different paths — for example 31,337 vs 31,339 for
  baseline line capacity. These are rounding artefacts, not disagreements.
  
  ---
  
  14. Techniques used
  
  Used: capacity analysis (theoretical / effective / actual), utilisation, 
  cycle time and throughput analysis, bottleneck identification via Theory of
  Constraints reasoning, OEE decomposition with loss attribution, Pareto
  analysis, MTTR and MTBF proxies, changeover and SMED analysis, statistical
  process control (individuals and p-charts, Western Electric rules 1 and 2,
  Phase I/II baselines, overdispersion diagnosis), discrete time-stepped
  simulation with finite buffers, scenario modelling, sensitivity analysis, and
  cost–benefit analysis with payback and benefit–cost ratios.
  
  Deliberately not used: machine learning, artificial intelligence, deep
  learning, neural networks, computer vision, forecasting models, or any
  technique that could not be explained on a whiteboard. Every method above is
  standard industrial engineering, chosen because the questions the project asks
  are capacity and constraint questions — and a constraint is found by
  arithmetic, not by prediction.