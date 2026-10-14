# PelagicLens — Models

**Scientific modelling layer for ocean-aware fisheries signal reliability**

This directory contains the ecological, fisheries, and statistical modelling components of **PelagicLens**, developed for the **Copernicus Marine Service Hackathon 2026**.

The purpose of this module is not simply to predict fish habitat. It is to determine whether ocean-driven changes in fish distribution and observation overlap can alter the meaning of fisheries and survey abundance indices.

> **Did the stock change, or did our ability to observe it change?**

---

## 1. Scientific objective

PelagicLens addresses a central problem in fisheries observation:

> **Can ocean-driven changes in the spatial distribution of pelagic fish explain and predict temporal variation in availability, detectability, or catchability, and thereby identify periods when abundance indices cease to be proportionally representative of stock status?**

The modelling workflow links:

```text
OCEAN
  ↓
FISH
  ↓
OBSERVATION
  ↓
SIGNAL
  ↓
DECISION
```

This repository component focuses primarily on **FISH** and **SIGNAL**, while exchanging data with the `ocean/` and `geospatial/` modules.

---

## 2. Observation model

PelagicLens starts from a simplified abundance-index model:

\[
I_t = q_t B_t \exp(\epsilon_t)
\]

where:

- \(I_t\) = observed fisheries or survey abundance index;
- \(B_t\) = underlying abundance or biomass;
- \(q_t\) = effective observation coefficient;
- \(\epsilon_t\) = observation error.

For pelagic species, \(q_t\) may integrate processes related to:

- availability;
- catchability;
- detectability;
- spatial coverage;
- population–survey overlap;
- population–fleet overlap;
- aggregation and concentration;
- vertical and horizontal redistribution.

The key scientific premise is that:

\[
q_t \neq \text{constant}
\]

when oceanographic conditions substantially alter fish distribution or the observation process.

Therefore:

\[
\Delta I_t
\]

does not necessarily imply an equivalent:

\[
\Delta B_t
\]

because part of the observed change may originate from:

\[
\Delta q_t
\]

---

## 3. Scientific hypotheses

### H1 — Ocean-driven redistribution

Oceanographic variability modifies the spatial organisation of pelagic fish.

Expected responses include changes in:

- centre of gravity;
- occupied area;
- spatial concentration;
- aggregation;
- habitat compression or expansion;
- coastal–offshore position;
- vertical distribution where suitable data are available.

---

### H2 — Redistribution modifies observability

Changes in fish distribution alter the overlap between the stock and the observation system.

This may modify:

- survey coverage;
- acoustic availability;
- detectability;
- fleet accessibility;
- encounter probability;
- the fraction of the population effectively represented by the observed index.

---

### H3 — Observation changes produce a dynamic \(q_t\)

Changes in distribution, concentration, and observation overlap generate temporal variation in the effective observation coefficient:

\[
q_t = f(E_t,D_t,O_t)
\]

where:

- \(E_t\) = environmental state;
- \(D_t\) = fish spatial distribution;
- \(O_t\) = observation-system configuration.

---

### H4 — Ocean-informed interpretation improves index reliability

An observation model that includes environmental state, fish redistribution, and observation overlap should better identify periods when an abundance index is not directly comparable with historical or baseline conditions.

---

## 4. Initial demonstration case

### Candidate species

**European anchovy**  
*Engraulis encrasicolus*

### Candidate region

**Bay of Biscay / Iberian shelf**

The exact study domain will be fixed after confirming the spatial and temporal compatibility of:

1. biological observations;
2. scientific survey coverage;
3. Copernicus Marine physical products;
4. Copernicus Marine biogeochemical products.

The modelling design must follow the strongest available biological dataset rather than forcing the data into a predetermined algorithm.

---

## 5. End-to-end scientific architecture

The minimum scientific workflow is:

\[
E(x,t)
\rightarrow
D(x,t)
\rightarrow
O(x,t)
\rightarrow
\Omega_t
\rightarrow
Signal_t
\rightarrow
Decision_t
\]

where:

- \(E(x,t)\) = oceanographic state;
- \(D(x,t)\) = estimated fish spatial state;
- \(O(x,t)\) = observation-system intensity or coverage;
- \(\Omega_t\) = effective spatial overlap;
- \(Signal_t\) = diagnostic of potential observation change;
- \(Decision_t\) = operational interpretation.

The first hackathon milestone is deliberately simple:

> **ONE REAL DATE → ONE REAL MAP → ONE END-TO-END SIGNAL**

Only after this vertical slice works should the workflow be expanded to time series and forecast mode.

---

# 6. OCEAN → environmental predictors

Environmental information is supplied by the `ocean/` module and should be based primarily on **Copernicus Marine** products.

The candidate predictor set is intentionally restricted to variables with plausible ecological mechanisms.

## Core candidate variables

- sea temperature;
- temperature anomaly;
- salinity;
- chlorophyll-a and/or primary production;
- mixed-layer depth;
- dissolved oxygen, where suitable;
- zonal current velocity;
- meridional current velocity;
- current speed.

## Derived environmental metrics

When justified:

- thermal gradients;
- frontal intensity;
- climatological anomalies;
- current magnitude;
- mesoscale indicators.

Variable selection should avoid adding predictors only because they are available.

Each predictor must have:

1. an ecological justification;
2. adequate spatial and temporal coverage;
3. compatible resolution;
4. acceptable collinearity;
5. demonstrable predictive value under validation.

---

# 7. FISH → spatial population model

The FISH component reconstructs the spatial state of the population as:

\[
D(x,t)=f(E(x,t),space,time)
\]

The exact meaning of \(D(x,t)\) depends on the biological observations available.

---

## 7.1 Response hierarchy

PelagicLens will use the strongest response variable supported by open data.

### Preferred hierarchy

```text
spatial biomass
      ↓
acoustic / survey density
      ↓
relative density
      ↓
presence–absence
      ↓
presence-only occurrence
```

Quantitative density or biomass observations are preferred because they provide a stronger basis for evaluating redistribution, concentration, and observation overlap.

---

## 7.2 Modelling modes

### Mode 1 — Habitat suitability

**Data:** presence-only occurrence records.

**Response:**

```text
occurrence
```

**Output:**

```text
relative habitat suitability
```

This is the fallback option and should not be interpreted as biomass.

---

### Mode 2 — Distribution

**Data:** presence–absence observations.

**Response:**

```text
presence / absence
```

**Output:**

```text
probability of occurrence
```

---

### Mode 3 — Relative density

**Data:** quantitative survey observations such as NASC, catches, or density proxies.

**Response:**

```text
relative density
```

**Output:**

```text
predicted spatial density
```

---

### Mode 4 — Spatial biomass

**Data:** calibrated quantitative acoustic or survey biomass observations.

**Response:**

```text
biomass
```

**Output:**

```text
predicted spatial biomass
```

This is the preferred scientific endpoint where appropriate open data are available.

---

# 8. Candidate modelling approaches

PelagicLens prioritises models that are:

- interpretable;
- reproducible;
- spatially explicit;
- computationally feasible during the hackathon;
- capable of uncertainty estimation;
- compatible with blocked validation.

## Primary statistical candidates

- GAM;
- GAMM;
- delta-GAM;
- hurdle models;
- spatiotemporal models.

## Machine-learning benchmarks

- Random Forest;
- Gradient Boosting.

Machine-learning methods are treated as predictive benchmarks, not as replacements for ecological interpretation.

The objective is **not** to identify the most complex model.

The objective is to identify the simplest model that produces:

1. ecologically credible spatial predictions;
2. adequate predictive skill;
3. stable spatial indicators;
4. interpretable uncertainty;
5. useful downstream information for OBSERVATION and SIGNAL.

---

# 9. Minimum FISH outputs

For every valid model prediction \(D(x,t)\), the workflow should estimate a reduced set of spatial indicators.

## MVP priority

```text
fish_prediction
centre_of_gravity
occupied_area
spatial_concentration
habitat_compression
prediction_uncertainty
```

## Secondary indicators

If time and data allow:

```text
coastal_offshore_displacement
depth_shift
spatial_fragmentation
spatial_persistence
ocean_anomaly_exposure
```

The hackathon MVP should prioritise a small number of scientifically defensible indicators rather than a large catalogue of metrics.

---

# 10. Spatial indicators

## 10.1 Centre of gravity

A weighted geographic centre can be estimated from predicted density or biomass:

\[
COG_t =
\frac{\sum_x xD(x,t)}
{\sum_x D(x,t)}
\]

Changes in the centre of gravity provide information on directional redistribution.

---

## 10.2 Occupied area

Occupied area represents the spatial extent containing biologically relevant predicted occurrence, density, or biomass.

The thresholding rule must be explicitly documented.

Possible approaches include:

- fixed ecological threshold;
- prediction quantile;
- percentage of total predicted density/biomass.

The same definition must be used across baseline and current periods.

---

## 10.3 Spatial concentration

Spatial concentration should quantify whether the predicted population becomes more spatially aggregated even if total abundance remains similar.

This metric is important because increasing concentration can increase local encounter rates and potentially modify CPUE or survey detectability.

---

## 10.4 Habitat compression

Habitat compression is defined relative to a reference condition.

Conceptually:

\[
HC_t =
\frac{A_t-A_{baseline}}
{A_{baseline}}
\]

where \(A_t\) is occupied area.

Negative values indicate contraction.

The exact implementation may be revised depending on the selected response variable.

---

# 11. OBSERVATION → observation-system representation

The observation process is represented as:

\[
O(x,t)
\]

where \(O(x,t)\) describes the spatial coverage or intensity of the system generating the observed index.

Possible sources include:

- scientific survey transects;
- acoustic survey coverage;
- sampling stations;
- fleet footprint;
- fishing effort;
- vessel positions;
- simulated vessel telemetry.

Observed and simulated observation systems must always be clearly distinguished.

---

# 12. Effective spatial overlap

The initial overlap metric is:

\[
\Omega_t =
\frac{\sum_x D(x,t)O(x,t)}
{\sum_x D(x,t)}
\]

where \(\Omega_t\) represents the relative fraction of the predicted resource distribution covered by or accessible to the observation system.

This metric allows comparison between:

```text
fish distribution
        +
observation footprint
        ↓
effective coverage
```

### Important scientific constraint

\[
\Omega_t \neq q_t
\]

The overlap metric is **not** a direct estimate of catchability.

It is a potential explanatory variable for temporal variation in availability, detectability, or catchability.

This distinction must remain explicit in the scientific interpretation.

---

# 13. Observation outputs

Priority outputs include:

```text
survey_overlap
fleet_overlap
relative_coverage
unobserved_high_density_area
fish_observation_centroid_distance
sampling_representativeness
overlap_uncertainty
```

These outputs provide the bridge between spatial ecology and the SIGNAL layer.

---

# 14. SIGNAL → index reliability diagnosis

The SIGNAL layer integrates environmental state, fish redistribution, and observation overlap.

Conceptually:

\[
q_t=f(E_t,D_t,O_t)
\]

and:

\[
E_t + D_t + O_t
\rightarrow
Risk(|\Delta q_t|>\delta)
\]

where \(\delta\) represents a scientifically relevant departure from reference conditions.

For the hackathon MVP, this should be implemented as a **quantitative risk indicator**.

It should only be called a probability if a suitable calibration dataset and probabilistic validation are available.

---

## 14.1 MVP SIGNAL outputs

```text
Habitat Compression
Observation/Fleet Overlap
Availability Shift
Catchability Shift Risk
Signal Reliability
Forecast Signal Risk
```

The interface should always separate:

```text
RAW INDEX
     ↕
OCEAN-AWARE INTERPRETATION
```

---

# 15. Baseline definition

All change indicators require an explicit reference state.

No metric such as:

```text
Habitat Compression
Availability Shift
Catchability Shift Risk
Signal Reliability
```

should be computed before the baseline is defined.

## Candidate baselines

- monthly climatology;
- seasonal climatology;
- historical survey mean;
- multi-year seasonal mean;
- recent reference period.

The final baseline will depend on:

1. biological sampling frequency;
2. survey seasonality;
3. available time series;
4. environmental seasonality.

The baseline must compare like with like.

For example, a spring survey should not be compared directly with an annual climatology if strong seasonal structure exists.

---

# 16. Validation strategy

Validation is a core scientific component rather than a final visual check.

Random cross-validation alone may strongly overestimate performance for spatially autocorrelated fisheries data.

---

## 16.1 Spatial validation

Prefer:

```text
spatial block cross-validation
```

when the amount of data permits.

The spatial block size should be informed by spatial autocorrelation and the effective scale of the sampling programme.

---

## 16.2 Temporal validation

When multiple years are available, prefer:

```text
leave-one-year-out
```

or:

```text
temporal holdout
```

to evaluate transferability between environmental conditions.

---

## 16.3 Model comparison

At minimum compare:

```text
simple baseline model
vs
ocean-informed model
```

When feasible:

```text
interpretable statistical model
vs
machine-learning benchmark
```

Evaluation metrics will depend on the response type.

Possible examples:

### Presence–absence

- AUC;
- TSS;
- log loss;
- calibration.

### Continuous density

- RMSE;
- MAE;
- deviance explained;
- correlation between observed and predicted values.

### Spatial performance

- ability to reproduce centre-of-gravity shifts;
- occupied-area changes;
- high-density spatial patterns.

---

# 17. Uncertainty

PelagicLens should communicate uncertainty explicitly.

Potential uncertainty sources include:

- biological observations;
- model parameters;
- environmental predictors;
- spatial extrapolation;
- forecast uncertainty;
- observation footprint;
- baseline definition.

The MVP should display uncertainty only when it can be estimated defensibly.

Uncertainty should not be converted into arbitrary confidence scores without a documented rule.

---

# 18. Avoiding circular validation

The same biological observations should not be used simultaneously to:

1. train the fish distribution model;
2. define the observation footprint;
3. validate the resulting SIGNAL metric;

unless this dependency is explicitly accounted for.

Whenever possible, validation should use independent years, surveys, spatial blocks, or observation sources.

---

# 19. Common modelling data contract

To allow interoperability between the `ocean/`, `models/`, `geospatial/`, `backend/`, and `frontend/` modules, the analytical table should converge toward a common structure.

```text
date
latitude
longitude

fish_response
fish_response_type

temperature
temperature_anomaly
salinity
chlorophyll
primary_production
oxygen
mixed_layer_depth

current_u
current_v
current_speed

fish_prediction
prediction_uncertainty

observation_intensity
observation_type

overlap
baseline_period
```

Not every variable will be required in the final model.

This structure defines interoperability, not mandatory model complexity.

---

# 20. Reproducibility

Every modelling run should record:

```text
species
study_area
biological_dataset
biological_dataset_version
copernicus_product_id
copernicus_dataset_id
variables
spatial_resolution
temporal_resolution
depth
download_date
model_type
model_formula
baseline_definition
validation_scheme
random_seed
```

The goal is that a team member can reproduce a result without relying on undocumented local decisions.

---

# 21. Scientific safeguards

PelagicLens will follow several explicit interpretation rules.

### Rule 1

Presence-only occurrence data will not be interpreted as biomass.

### Rule 2

Habitat suitability will not be called abundance.

### Rule 3

Spatial overlap will not automatically be interpreted as catchability.

### Rule 4

A risk score will not be called a probability without calibration.

### Rule 5

Simulated vessel telemetry will never be presented as observed fisheries data.

### Rule 6

Forecast outputs will inherit uncertainty from both the ocean forecast and the ecological model.

### Rule 7

Model complexity must be justified by measurable improvement under appropriate validation.

These safeguards are important for both scientific credibility and product trust.

---

# 22. MVP development sequence

## M0 — Data feasibility

Identify the strongest open quantitative biological dataset for European anchovy.

Priority:

```text
spatial biomass
>
acoustic / survey density
>
relative density
>
presence–absence
>
presence-only
```

**Deliverable:** biological dataset decision.

---

## M1 — Fish × ocean integration

Create the first joined biological–environmental dataset.

Minimum target:

```text
one real survey or period
+
one biological response
+
3–5 oceanographic predictors
```

**Deliverable:** reproducible analytical table.

---

## M2 — First ecological model

Fit one interpretable model.

Initial preferred candidate:

```text
GAM
```

unless the data structure clearly requires another approach.

**Deliverable:** first real spatial prediction of \(D(x,t)\).

---

## M3 — Spatial indicators

Calculate at minimum:

```text
centre of gravity
occupied area
spatial concentration
```

**Deliverable:** current vs baseline spatial diagnostic.

---

## M4 — Observation overlap

Combine:

```text
D(x,t)
+
O(x,t)
```

to estimate:

```text
Ω_t
```

**Deliverable:** observed vs potentially unobserved resource distribution.

---

## M5 — SIGNAL prototype

Combine the key outputs into the first signal-reliability diagnostic.

**Deliverable:**

```text
Observed index
Habitat compression
Observation overlap
Catchability shift risk
Signal reliability
Main driver
```

---

## M6 — Forecast extension

When the historical/current workflow is scientifically stable:

```text
Copernicus forecast
        ↓
future E(x,t+h)
        ↓
future D(x,t+h)
        ↓
future overlap
        ↓
Forecast Signal Risk
```

**Deliverable:** first early-warning scenario.

---

# 23. MVP success criteria

The modelling component is considered hackathon-ready when it can demonstrate the following chain with real open data:

```text
1. Copernicus Marine describes an ocean condition or anomaly.

2. The FISH model estimates a biologically interpretable spatial response.

3. The spatial response changes overlap with an observation system.

4. PelagicLens quantifies that change.

5. SIGNAL explains how the observed abundance index should be interpreted.

6. DECISION communicates the result clearly without overstating scientific certainty.
```

A complete end-to-end demonstration is more valuable than multiple disconnected models.

---

# 24. What we are not building

For the hackathon MVP, PelagicLens is **not** intended to become:

- another generic habitat map;
- a fishing-ground recommendation system;
- a fully operational stock assessment model;
- an autonomous fisheries-management system;
- a black-box AI predictor;
- a claim that environmental variability explains every change in abundance indices.

The specific innovation is the connection:

```text
OCEAN CHANGE
      ↓
FISH REDISTRIBUTION
      ↓
OBSERVATION CHANGE
      ↓
INDEX RELIABILITY
      ↓
DECISION CONTEXT
```

---

# 25. Immediate next decision

Before implementing the final model, the next scientific task is:

> **Identify and verify the strongest open spatial dataset available for European anchovy in the selected European study region.**

That decision will determine:

- the response variable;
- the study domain;
- the temporal domain;
- the appropriate model family;
- the Copernicus Marine products;
- the validation strategy;
- the meaning of \(D(x,t)\).

No final ecological model should be selected before this step is complete.

---

## Scientific principle

PelagicLens should remain:

> **transparent, reproducible, ecologically interpretable, and explicit about uncertainty.**

For the hackathon, scientific credibility and an operational end-to-end story are more important than unnecessary model complexity.
