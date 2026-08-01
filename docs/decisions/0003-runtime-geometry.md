# 0003: Runtime geometry response

- **Status**: accepted
- **Date**: 2026-08-01
- **Context**: Head or sensor motion changes where a fixed winding is evaluated,
  so a fixed response matrix cannot faithfully describe every pose.
- **Decision**: In the need for moving-grid environments, facing high repeated
  field-computation cost, we choose analytic finite-segment Biot-Savart with an
  identity-bound pose cache instead of fixed-matrix fallback or interpolation,
  gaining physical fidelity while accepting greater per-step cost.
- **Consequences**: Dynamic packages must include conductor geometry; repeated
  exact poses can reuse computed responses, but unseen poses are recomputed.
- **Alternatives Considered**: Silent fixed-matrix fallback and nearest-pose
  interpolation were rejected because they change the declared physical model.
