## 2026-11-14 - UTF metadata decoding can copy an entire sound bank
**Learning:** `sound_codec.Utf` discards decoded rows after counting them, but `cpk.table` still copied embedded AWB blob cells. Inspection of the largest source bank allocated 32,611,332 extra traced bytes. Constant blob cells also live in the retained schema, so discarding rows alone cannot remove those copies. Slicing the input (`raw[0:len(raw)]`) is only free for exact `bytes`; a `bytearray` bank was still copied whole.
**Action:** Validation-only readers use `cpk.check`, which shares `table`'s validation walk but builds no rows or blob payloads (constant blobs become `(offset, length)` spans). Pass a whole-buffer UTF without slicing. Prefer a separate query function over a flag that changes return types (an earlier `blob_views=True` memoryview variant was replaced after review).

## 2026-11-20 - Validate prepared startup assets once
**Learning:** `Gameplay.preflight()` and `Engine.initialize(prepared=True)` both validated the complete prepared snapshot. On a disposable current-data runtime, that repeated the 735-bank sound checksum and source-freshness walks and added about 15.6 seconds to startup.
**Action:** Keep the campaign-initialized guard in hosting, and let `Engine.initialize()` validate the prepared tables and art once before importing `capture_server`.

## 2026-11-21 - Cache static summon offer identities
**Learning:** A warm iOS summon projection serialized unchanged offer identities 780 times per call. A recursive Python freeze was 4.8x slower than the JSON encoder; a one-catalogue signature cache reduced the 1,053-row projection from about 22 ms to 2.5 ms and retained about 6.2 MB of traced Python allocations. The first cold call stayed about the same because it still builds the signatures.
**Action:** Cache only catalogue-derived signatures against the retained source tuple; recompute replay selection from campaign state and time on every query, and keep the cache bounded to one catalogue.

## 2026-11-22 - Stream sound GETs after verification
**Learning:** Native sound GET retained a full verified bank in memory. A 32.6 MB disposable bank increased process high-water RSS by 32.65 MB; streaming from a verified descriptor reduced request-attributable RSS to about 0.31 MB. Integrity still needs to be checked before response headers, including same-size edits.
**Action:** Open the contained bank with `O_NOFOLLOW`, recheck its size and digest on every request, rewind that same descriptor, and stream only the recorded length in bounded chunks. Do not cache sound integrity by file metadata.

## 2026-11-24 - Native News list builds unused detail projections
**Learning:** The `CQ4jTm2F` native list query runs under the canonical `STATE_LOCK`. `revival_notices.add_rows()` builds a full summary for every retained week, then uses only its caption; an eight-week synthetic baseline measured about 53 ms warm and profiled eight summon plans, eight event plans, and roughly 116,000 recursive copy calls.
**Action:** Keep native captions as a read-only projection separate from HTML summaries, and do not retain campaign- or time-dependent notice results across requests.

## 2026-11-25 - Support reads rebuild the full simulated friend catalogue twice
**Learning:** The iOS `GetReinforcementInfoRequest` reply adapter calls `friend_list` and `friend_reinforcements`; each independently builds all 200 generated peers. A disposable 15-friend/10-suggestion baseline measured 9.29 ms warm and profiled 400 `CompanionDirectory.by_id()` calls although both reply views needed the same request-local rows.
**Action:** Share one targeted request-local friend projection across the two iOS read views. Keep the full catalogue API for other callers and avoid cross-request caching of roster- or replay-dependent eligibility.

## 2026-11-26 - Vortex gate reads build the full summon plan
**Learning:** A fourteen-process native gate projection baseline measured 703 ms cold and 27.2 ms warm under the canonical request lock. Cold profiling attributed 630 ms to `revival_summons.event_context()` and its full `plan()` path, including 1,342 offer-identity encodings, although the gate only reads replay week, window, holiday, and anchor facts.
**Action:** Route only the event-gate projection through narrow replay-calendar facts. Keep full summon plans for exchanges and other consumers, fall back when the active holiday lacks event-history coverage, and do not cache campaign- or time-dependent facts across requests.
