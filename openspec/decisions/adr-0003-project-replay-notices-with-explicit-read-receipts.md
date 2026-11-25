# ADR-0003: Project replay notices with explicit read receipts

## Status

Accepted for the replay-notice implementation.

## Context

The pinned fork summarizes historical weeks using its summon, event, bundle,
and replay-mail policies. Its notice catalogue records indexes while reading;
its HTML can fetch and cache remote artwork. Both violate the iOS query boundary.

## Decision

Record notice enablement and retention during explicit campaign initialization.
Derive each week's identity, native dates, and summary from the saved replay
calendar and existing canonical iOS policies. Keep rendering separate from
selection and use local artwork URLs only. Persist native year/index read masks
through an atomic NoticeReadUpdateRequest command, preserving existing receipts.

## Consequences

News/catalogue/page queries never initialize, grant, download, or save. Old pages
can be reopened after leaving the eight-week list; future weeks remain closed.
Native UTC dates preserve saved-timezone rollover and DST. Legacy notice behavior
retains its original path. Preparing missing art and replay home banners remains
part of the subsequent asset/hosting stage.

Affected files: `revival_notices.py`, `revival_notice_commands.py`,
`revival_notice_pages.py`, `exvius_actions.py`, `capture_server.py`,
`revival_campaign.py`, and `ios_server/queries.py`.
