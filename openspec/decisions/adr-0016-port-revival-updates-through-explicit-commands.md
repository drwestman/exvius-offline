# ADR-0016: Port revival updates through explicit commands

Accepted for the approved d6e8858 migration.

Extend the canonical engine through iOS policy, command, projection and preparation
adapters. Pure rules receive master data and clocks; candidate commands run under
the existing lock and publish only after persistence. Legacy defaults remain intact.
Campaign upgrades require a matching save digest and preserve a private backup.
Historical payment ambiguity is reported, never inferred from inventory or logs.
Prepared native bytes and their advertised versions/checksums form one generation.
The original foundation pin remains provenance for unchanged capabilities; new
capabilities record their own upstream revision.
