# 0004: Textual as the interactive front end

- **Status**: accepted
- **Date**: 2026-08-01
- **Context**: Environment construction requires revisiting several related
  sections and reviewing errors before export.
- **Decision**: In the need for a navigable terminal workflow, facing the limits
  of a one-way prompt sequence, we choose Textual over raw `input()` prompts,
  gaining editable screens and testable UI state while accepting one UI
  dependency.
- **Consequences**: TUI logic remains a thin client of the same builder API used
  by automation.
- **Alternatives Considered**: A sequential prompt wizard was rejected because
  users cannot efficiently review and revise a complete physical definition.
