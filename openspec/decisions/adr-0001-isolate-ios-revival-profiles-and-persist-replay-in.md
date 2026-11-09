# ADR-0001: Isolate iOS revival profiles and persist replay initialization with the campaign

## Status

accepted (auto-accepted, unreviewed)

**Domains**: server

## Context

Keep the current canonical engine and legacy defaults; select an immutable profile before engine imports, separate shared content from private runtime paths, and commit the replay anchor and initialization marker together in the existing atomic player save. Queries only inspect persisted state.

## Decision

Isolate iOS revival profiles and persist replay initialization with the campaign

## Consequences



> Recorded by openlore decisions on 2026-11-09
> Decision ID: 381df222


