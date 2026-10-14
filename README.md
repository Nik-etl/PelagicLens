# PelagicLens

**Ocean-aware fisheries signal reliability**

PelagicLens is a platform that transforms Copernicus Marine oceanographic information into actionable intelligence for interpreting fisheries indicators under changing ocean conditions.

Rather than only predicting where fish may occur, PelagicLens evaluates how ocean-driven changes in fish distribution, concentration, and accessibility can affect what scientific surveys and fishing fleets actually observe.

> **Did the stock change, or did our ability to observe it change?**

---

### Architecture Workflow

The project operates through a 5-layer pipeline:

1. **OCEAN**  
   Ingestion and processing of physical and biogeochemical data from Copernicus Marine, including observed and forecast ocean conditions.

2. **FISH**  
   Spatiotemporal modelling of pelagic species distribution and spatial responses to environmental variability.

3. **OBSERVATION**  
   Quantification of the overlap between predicted fish distribution and observation systems, including scientific surveys, fleet footprints, and simulated vessel telemetry.

4. **SIGNAL**  
   Evaluation of changes in availability, catchability, observability, and the reliability of fisheries or abundance indices.

5. **DECISION**  
   Translation of model outputs into interpretable diagnostics, early-warning signals, and decision context for fisheries scientists and managers.

---

### Core Workflow

```text
Copernicus Marine
        ↓
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

The objective is to identify situations where changes in ocean conditions may alter the relationship between observed fisheries indicators and the underlying stock.

---

### Initial Demonstration Case

The initial open-data demonstration will focus on a European pelagic fish case, with **European anchovy (*Engraulis encrasicolus*)** as the current candidate species.

The final study area, biological dataset, and temporal coverage will be selected based on data availability and compatibility with Copernicus Marine products.

---

### Repository Structure

```text
PelagicLens/
├── backend/      # APIs, data pipelines and telemetry
├── docs/         # Project and scientific documentation
├── frontend/     # Dashboard and user interface
├── geospatial/   # Spatial processing and overlap analysis
├── models/       # Ecological and fisheries modelling
└── ocean/        # Copernicus Marine data and ocean indicators
```

---

*Built for the Copernicus Marine Service Hackathon 2026.*
