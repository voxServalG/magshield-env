# 0002: Gymnasium public environment contract

- **Status**: accepted
- **Date**: 2026-08-01
- **Context**: The exported result must be consumable by mainstream
  reinforcement-learning libraries without embedding training code.
- **Decision**: In the need for a standard single-agent interface, facing the
  cost of maintaining a private protocol, we choose Gymnasium `reset/step` over
  a custom environment API, gaining ecosystem compatibility while accepting
  Gymnasium as a runtime dependency.
- **Consequences**: Observation and action spaces are explicit and tested; the
  package still contains no trainer or algorithm integration.
- **Alternatives Considered**: A private reset/step protocol was rejected because
  every downstream user would need an adapter.
