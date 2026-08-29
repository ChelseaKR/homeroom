# 0000. Record architecture decisions

Status: Accepted
Date: 2026-08-07
Deciders: Chelsea Kelly-Reif

## Context

We need a record of the architecturally-significant decisions made in this
repo: what was decided, why, and what it costs. Per
`STANDARDS/DOCUMENTATION-STANDARD.md` §3, decisions live as ADRs, not as
roadmap edits.

## Decision

We will use Architecture Decision Records (MADR format), as described by
Michael Nygard, numbered sequentially in `docs/adr/`. ADRs are immutable once
`Accepted`; a later decision that changes course adds a new ADR with
`Status: Superseded by NNNN` rather than editing this one.

Any PR touching a guardrail (no-outing/grounding/consent/identity-inference),
a `permissions:` block, or a coverage/eval threshold links an ADR.

## Consequences

Decisions are diffable, reviewable, and never silently lost in chat/PR
descriptions.
