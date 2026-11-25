# Native iOS upstream review — November 11, 2026

Reviewed `/Users/david/Projects/Exvius-revival-ios` at
`ae07888c731e3aff7e12c06f9ca4336ab5f9210c`, 15 commits beyond our original
`47a13c084f42cf1b83b53173d0c21065c78fc2de` reference. The reference checkout's
local `.gitignore` change was preserved. This review does not change the baseline
for features already ported and does not claim full parity with the new revision.

The reported failure is now narrower: Summon opens, but its loading indicator is
a blank square. The earlier report that no Home icons respond is not a confirmed
global input failure. No matching general spinner/UI-pack fix was found in these
commits. Upstream's NV summon animation fix concerns a completed draw's animation,
not the loading indicator, and its unit pictures concern News/Drop Rates pages.

## Applied diagnostic slice

Adapt the latest `client_reports.py` wire contract and the `590d4fb` policy fix:
off by default; request a device log on GameSetting only, once per app launch;
acknowledge queued uploads without storage when off. Ordinary home polling must
never repeatedly request a log. This integration adds native-only bounded private
storage, a dedicated 64 MiB upload limit, request-record redaction and a read-only
decoder. Uploads bypass the gameplay command pipeline and cannot update campaign
facts. Temporary opt-in will obtain the device's actual error before another UI fix.

## Remaining update slices

These need source-grounded ports and BDD against our profile/replay/transaction
boundaries. They are reviewed candidates, not implemented features.

| Priority | Upstream changes | Integration boundary |
| --- | --- | --- |
| Next native compatibility | `b49d696` Farplane scene exclusions; `ae07888` Convert table refetch | Prepare exclusions atomically; our complete version delivery already bumps every registered table, so reproduce a remaining Convert failure before adding another bump |
| Summon correctness | `80a0726`, `1c86d02`, `3ca7aa5`, `55ba872`: held-ticket listings, 5-star Select group/field, stale ticket handling, daily counts, NV animation | Reuse one effective offer/pool for listing/rates/draw and preserve atomic charges, limits and receipts |
| Roster and native menus | `0ff3c96`, `5c4a05f`, `55ba872`, `ae07888`: Vision Cards, Guide, search and NV awakening/refusal messages | Separate recorded ownership/history from pure listings; validate refusal replies without charging |
| Replay content/shops | `d15c9d7`, `1b65650`, `a8afb79`, `0ff3c96`, `84ff7a9`: story units, collection points, release corrections, Captain menu, event dates/order, hidden/clone quests | Keep campaign policy and recorded battle facts stable; publish prepared menu packs and metadata together |
| Battle rewards | `14da9f7`, `84ff7a9`, `5c4a05f`, `55ba872`, `ae07888`: lotteries, Global/currency drops, first clears/backpay, recipes, pots and quest Gil | Stage rewards and durable receipts once; distinguish already-paid rewards before any backpay; preserve legacy defaults |

`d69c1e9` adds the changelog. The large `responses.json` diff is mostly line-ending
churn: structural comparison finds no changed retained top-level values or added
keys; 87 old mission-specific bundles were removed. Do not replace our response
corpus or battle handling wholesale on the strength of that textual diff.

Full managed-pack validation, source-art gaps and remaining physical acceptance
checks stay open under [the main plan](IOS_SERVER_SOLID_CQRS_PLAN.md).

## Validation

The missing queued-report acknowledgment was RED before the adapter and GREEN
afterward. A separate route/request-ID mismatch regression also went RED, then
passed with dispatch isolation. The final full iOS suite passes **483 tests**,
including six report checks and real encrypted uploads larger than 4 MiB.
An additional **125 decoder/summon/completion/shop checks** and **three canonical
login checks** pass against isolated state and read-only shared masters. The
canonical login fixture uses an empty temporary area-overlay directory because
the selected corpus has no such directory; no artwork claim follows from it.

Strict OpenSpec adds no findings to its **417-error/three-warning** baseline.
Refreshed mapping/static drift has no tracked gaps, stale anchors or uncovered
files; five informational decision-freshness notices remain. Python syntax and
CRLF-aware whitespace checks pass. Git-based drift excludes new untracked files
until check-in; both new modules have explicit implementation anchors and BDD.

The final host restart preserves campaign bytes and CA identity; it retains
generation 2 without a data refresh. Physical recovery and actual device-log
contents remain pending the iPhone retry. The diagnostic invariant is recorded
in the iOS/server specs, with AP-005 covering repeated bulk telemetry from polling.

## Native WebView contract repair — November 12, 2026

Consulted the native Drop Rates form route and missing-ID catalogue fallback at
reference revision ae07888. The destination already advertised that URL but had
only the alternate banner-specific HTML route, producing an empty native 404.
Added a bounded iOS-only adapter and a small catalogue index while retaining the
existing effective-pool rates renderer. Form fields are request-local and never
logged as bodies; queries preserve campaign, RNG and ordinary request records.
All 490 iOS and 22 legacy summon tests pass. The hosted native form/query routes
now return valid rates HTML; the user subsequently confirms native unit names
and probabilities display correctly.
