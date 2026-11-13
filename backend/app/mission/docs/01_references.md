# NASA Space Health & Fatigue Risk Management — Verified References

> **Strict Usage Rule for AI Agents:**
> This file is the **sole source of truth** for scientific claims, factors, and countermeasures in `02_requirements.md` and `catalogue.py`.
> - Do NOT invent URLs, study statistics, or numeric thresholds not explicitly written below.
> - Any threshold, numeric default, or rule logic not explicitly stated in these sources MUST be labeled as `"proposed system logic"` or `"configurable assumption"`, never as a NASA finding.

---

## 1. NASA Human Research Program (HRP) — Risk of Performance Decrements and Adverse Health Outcomes Resulting from Sleep Loss, Circadian Desynchronization, and Work Overload

- **Source ID:** `NASA-HRP-Sleep-Risk`
- **Title:** Evidence Report: Risk of Performance Decrements and Adverse Health Outcomes Resulting from Sleep Loss, Circadian Desynchronization, and Work Overload
- **Organization:** NASA Human Research Program (HRP) — Behavioral Health and Performance (BHP)
- **URL:** https://humanresearchroadmap.nasa.gov/evidence/reports/Sleep.pdf
- **Validated Findings & Concepts:**
  - **Primary Risk Drivers:** Astronaut cognitive and operational performance decrements during spaceflight are driven by three interrelated factors: acute and chronic sleep loss (sleep restriction), circadian desynchronization (misalignment between endogenous circadian rhythms and scheduled work/rest cycles), and work overload.
  - **Operational Causes in Spaceflight:** Sleep curtailment and circadian misalignment frequently occur due to mission-critical scheduling demands, shifting sleep-wake schedules (slam-shifts), docking/undocking operations, extravehicular activities (EVAs), high workload periods, and environmental factors (noise, light, microgravity).
  - **Performance Impacts:** Sleep loss and circadian misalignment impair sustained attention (vigilance), working memory, cognitive throughput, reaction time, decision-making, and emotional regulation, increasing the risk of operational errors during critical tasks.
  - **Evidence-Based Countermeasures Mentioned:**
    1. **Schedule & Workload Management:** Protecting adequate sleep opportunities in mission timelines, avoiding abrupt phase shifts where operationally feasible, and managing workload distribution before high-criticality operations.
    2. **Lighting Countermeasures:** Strategic use of dynamic/blue-enriched lighting (wavelength and intensity management) to support circadian alignment and alertness during wake periods, paired with light restriction prior to scheduled sleep.
    3. **Strategic Napping / Rest Opportunities:** Scheduled rest or nap periods as a fatigue mitigation strategy when consolidated nocturnal sleep is disrupted by mission operations.
    4. **Sleep Hygiene & Environmental Optimization:** Controlling cabin light, noise, and temperature to improve sleep quality.

---

## 2. NASA Fatigue Management & Countermeasures — Operational Guidance (NASA Ames Fatigue Countermeasures Group)

- **Source ID:** `NASA-TM-Fatigue-Countermeasures`
- **Title:** Fatigue Countermeasures in Aviation and Spaceflight Operations (NASA Technical Memorandum / Ames Research Center Fatigue Countermeasures Group)
- **Organization:** NASA Ames Research Center
- **URL:** https://ntrs.nasa.gov/citations/20030062186
- **Validated Findings & Concepts:**
  - **Circadian Window of Low Alertness (WOCL):** Human alertness and cognitive performance follow a circadian rhythm, with predictable troughs during the biological night (Window of Circadian Low) where error rates and sleepiness peak.
  - **Cumulative Sleep Debt:** Consecutive days of restricted sleep produce cumulative performance degradation, and subjective self-assessment of fatigue often underestimates objective cognitive impairment.
  - **Recovery Requirements:** Recovery from cumulative sleep restriction requires extended sleep opportunities rather than single short rest breaks; insufficient recovery intervals between demanding shifts sustain elevated fatigue risk.
  - **Evidence-Based Countermeasures Mentioned:**
    1. **Task Timing & Criticality Alignment:** Scheduling high-alertness and safety-critical tasks during peak circadian alertness windows rather than during circadian troughs.
    2. **Protected Rest Breaks & Recovery Gaps:** Inserting structured rest breaks during prolonged high-workload periods to mitigate acute performance decline.
    3. **Pre-Mission / Pre-Event Sleep Banking & Schedule Stabilization:** Stabilizing sleep-wake timing prior to demanding operational phases.

---

## 3. NASA-STD-3001 Volume 2 — NASA Spaceflight Human-System Standard (Human Performance, Workload, and Work-Rest Cycles)

- **Source ID:** `NASA-STD-3001-Vol2`
- **Title:** NASA Spaceflight Human-System Standard, Volume 2: Human Factors, Habitability, and Environmental Health
- **Organization:** National Aeronautics and Space Administration (NASA)
- **URL:** https://standards.nasa.gov/standard/NASA/NASA-STD-3001-VOL-2
- **Validated Findings & Concepts:**
  - **Work-Rest & Sleep Allocation:** Spaceflight mission schedules must allocate sufficient daily time for sleep, personal hygiene, meals, and off-duty recovery to sustain crew health and operational performance across mission durations.
  - **Workload Assessment:** Mission tasks vary in cognitive and physical demand; sustained excessive workload without adequate recovery degrades human-system performance and increases error probability.
  - **Lighting & Circadian Support:** Spacecraft lighting systems are required to support both visual task performance and circadian entrainment through spectrum and illuminance control.
  - **Decision-Support & Human-in-the-Loop Principle:** Automated mission planning and health monitoring tools serve to assist flight surgeons, mission planners, and crew members; final operational and medical decisions remain with human authorities (Crew, Flight Surgeon / Medical Operations, and Mission Control).

---

## Summary of Allowed Evidence-Based Countermeasures (For Module 5 & `catalogue.py`)

Only the following countermeasures are backed by the references above (non-pharmacological, operational/behavioral only):
1. **Protect / Reschedule Sleep Opportunity** (`NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2`)
2. **Align High-Criticality Tasks with Peak Alertness Windows / Avoid Circadian Trough** (`NASA-HRP-Sleep-Risk`, `NASA-TM-Fatigue-Countermeasures`)
3. **Insert Structured Recovery / Rest Break Between Demanding Tasks** (`NASA-TM-Fatigue-Countermeasures`, `NASA-STD-3001-Vol2`)
4. **Redistribute High-Workload Tasks Across Schedule Windows** (`NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2`)
5. **Adjust Lighting Exposure Schedule for Circadian Alignment** (`NASA-HRP-Sleep-Risk`, `NASA-STD-3001-Vol2`)
6. **Strategic Short Nap / Rest Opportunity During Extended Operations** (`NASA-HRP-Sleep-Risk`)
7. **Optimize Sleep Environment (Light/Noise Reduction)** (`NASA-HRP-Sleep-Risk`)
