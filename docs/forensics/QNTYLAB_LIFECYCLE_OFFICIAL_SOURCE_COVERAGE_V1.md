# QntyLab — Lifecycle Official Source Coverage V1

`ARTIFACT_KIND: provenance_receipt`
`PHASE: Lifecycle Source Coverage Evidence Persistence`

## 0. Purpose and non-purpose

This document persists two already-completed, already-closed research results so
they are traceable from the repository rather than from chat history:

1. the **Catalog-48 census** of the frozen 60-target lifecycle-expansion set;
2. the **second-official-Binance-source feasibility probe** (Catalogs 49 / 161).

**No new research was performed while writing this receipt.** Network attempts
during this persistence task: **0**. Every number below was re-derived by reading
preserved local evidence, not by re-querying Binance. Nothing here is a new
scientific claim, and no lifecycle semantics, gate, or production module was
touched.

---

## 1. Frozen target authority

```text
ORDERED_TARGET_LIST_SHA256: 6a10d2d39c9f28dc267811092e6f5ab71abc093156cb7eec6f105c5a24c2c1e2
AUTHORITY_COMMIT:           07f793ac81483ce9cec5cbd80b1a637e7125990b
AUTHORITY_ARTIFACT:         experiments/data/step1_4_result.json
AUTHORITY_FIELD:            ordered_target_list   (162 entries; positions 1–60 = the census set)
DIGEST_RECHECK:             MATCH
```

Preimage format (`scripts/step1_4.py` @ `07f793a`):
`sha256(json.dumps(ordered_target_list, sort_keys=True, separators=(",", ":")).encode())`.

Recomputed during this task over the preserved census input copy of
`step1_4_result.json` — digest equals the historical frozen value exactly.
The batch-3 (positions 41–60) recovery lineage is recorded separately in
[QNTYLAB_SCOUT_LIFECYCLE_EXPANSION_V1_BATCH3_DIGEST_RECOVERY.md](QNTYLAB_SCOUT_LIFECYCLE_EXPANSION_V1_BATCH3_DIGEST_RECOVERY.md),
committed at `12f57d4`.

Batches are positional slices of that frozen list:
Batch 1 = positions 1–20, Batch 2 = 21–40, Batch 3 = 41–60.

---

## 2. Source identity — Binance Catalog 48

```text
SOURCE:        Binance CMS announcement catalog
CATALOG_ID:    48
CATALOG_NAME:  New Cryptocurrency Listing
ENDPOINT:      https://www.binance.com/bapi/composite/v1/public/cms/article/list/query
               ?type=1&catalogId=48&pageNo=<n>&pageSize=50
CORPUS_SIZE:   2225 article records (catalog-reported total; enumerated over 45 pages)
FIELDS_USED:   title, code, releaseDate   (titles only — no article bodies were fetched)
```

The census is a **title-level metadata scan**. Article bodies were never
retrieved for the 60 targets, so nothing here rests on body text.

---

## 3. Selector semantics actually used

Per target `<BASE>USDT`, a catalog record is classified from its title alone:

1. **Symbol binding** (required, else the record is ignored) — case-insensitive
   match of `<BASE>USDT`, `<BASE>/USDT`, `<BASE> USDT`, or a margin-type-prefixed
   form (`USDⓈ-M <BASE>`, `USDⓈ-Margined <BASE>`, `USDT-Margined <BASE>`,
   `USD-M <BASE>`, `USDⓂ-M <BASE>`).
2. **WRONG_PRODUCT** if the title contains any of: `quarterly`, `coin-m`, `coinm`,
   `busd`, `usdc`, `options`, `delivery`, `leveraged token`,
   `margin trading pair`, `will list`, `spot trading pair`; or matches
   `<BASE>USD` not followed by `T`.
3. **EXACT_LAUNCH_CANDIDATE** if title contains all of `futures`, `launch`,
   `perpetual`.
4. **POSSIBLE_BOUNDARY_CANDIDATE** if title contains `futures` and `launch`
   but not `perpetual`.
5. Otherwise ignored.

Per-target class: `EXACT` if ≥1 exact candidate, else `POSSIBLE` if ≥1 possible
candidate, else `NONE`. `ambiguous_exact` is set when a target has **more than
one** exact candidate.

Note that "Relaunch" titles satisfy the `launch` substring test — this is the
source of the single ambiguity in §5.

---

## 4. Census result

```text
TOTAL_TARGETS:              60
EXACT_METADATA_COVERAGE:    43
POSSIBLE_ONLY:               0
NO_CANDIDATE:               17
AMBIGUOUS_EXACT:             1   (BNXUSDT)

BATCH_1 (pos 1–20):   15 / 20
BATCH_2 (pos 21–40):  15 / 20
BATCH_3 (pos 41–60):  13 / 20

SOURCE_ROLE:  PARTIAL_SOURCE
```

`PARTIAL_SOURCE` means: Catalog 48 locates an exactly-bound launch-shaped
announcement for 43 of 60 frozen targets and for none of the remaining 17. It is
a partial locator over this target set — not a complete one, and not (see §7) an
authority.

### Residual set — the exact 17 `NO_CANDIDATE` symbols

```text
BIOUSDT        BTCUSDT        CRCLUSDT       UNFIUSDT
JUPUSDT        LAYERUSDT      RVNUSDT        JASMYUSDT
KAITOUSDT      BANANAS31USDT  MANAUSDT       ETHFIUSDT
SIRENUSDT      LEVERUSDT      ENAUSDT        HBARUSDT
SAGAUSDT
```

Count = 17, all distinct. `POSSIBLE_ONLY` is 0: no target landed in the
`POSSIBLE` class, so the 60 split cleanly into 43 `EXACT` + 17 `NONE`.

---

## 5. BNXUSDT ambiguity

BNXUSDT (position 24, Batch 2) is the sole `ambiguous_exact` target: **two**
exact candidates survive the selector.

```text
940d0e48493e4627889c3f46371df70b  2023-02-22
  "Binance Futures to Relaunch USDⓈ-M BNX Perpetual Contracts with Up to 20X Leverage"
e15fac275e7a4e858dc4bb79ffc24c50
  "Binance Futures Will Launch USDT-Margined BNX Perpetual Contracts with Up to 25X Leverage"
```

It is counted once toward the 43. Which of the two (launch vs. relaunch) is the
correct boundary document is **not decided here** — the census records the
ambiguity and stops.

---

## 6. Preserved per-target matrix

`class` is the census classification; `article_code` / `release_date` are the
`best` (first) exact candidate where one exists. Full titles and the complete
exact-candidate lists per target live in the census output named in §9.

| # | batch | symbol | class | article_code | release_date |
|---|---|---|---|---|---|
| 1 | 1 | BCHUSDT | EXACT | 360037742632 | 2019-12-19 |
| 2 | 1 | CHZUSDT | EXACT | e95ce5d56cfe4ef4acfb02a0769e6fd8 | 2021-01-21 |
| 3 | 1 | API3USDT | EXACT | 3e091344eaaa4632bbdc1e5ded1237e1 | 2022-02-21 |
| 4 | 1 | FETUSDT | EXACT | 92f8c95638d94627961641c0e6a9edef | 2023-01-13 |
| 5 | 1 | WIFUSDT | EXACT | 5c6cb594550247aea7c93a47c0156b17 | 2024-01-18 |
| 6 | 1 | BIOUSDT | NONE | - | - |
| 7 | 1 | INTCUSDT | EXACT | d592f6ba938746cbadaaf5a8a714abd6 | 2026-01-30 |
| 8 | 1 | BTCUSDT | NONE | - | - |
| 9 | 1 | SANDUSDT | EXACT | df96728782084fd2ab2ba51b6201b462 | 2021-01-25 |
| 10 | 1 | GMTUSDT | EXACT | b76223a20c604f718b1e124d1d049d0d | 2022-03-14 |
| 11 | 1 | AGIXUSDT | EXACT | 5f499de4a4d845adb7a8e472f151fa1a | 2023-02-15 |
| 12 | 1 | ONDOUSDT | EXACT | af6c1bbbe6ec406c8b2d087fe47c5554 | 2024-01-20 |
| 13 | 1 | TRUMPUSDT | EXACT | 82ac4437417c4876895c7262a4245bf0 | 2025-01-18 |
| 14 | 1 | CRCLUSDT | NONE | - | - |
| 15 | 1 | ETHUSDT | EXACT | 360036964392 | 2019-11-29 |
| 16 | 1 | UNFIUSDT | NONE | - | - |
| 17 | 1 | APEUSDT | EXACT | bb98f3f2625143fc9d5d98c3aae55b1a | 2022-03-17 |
| 18 | 1 | CFXUSDT | EXACT | 28408f1dd1ce440d874b795ccc40fe15 | 2023-02-20 |
| 19 | 1 | JUPUSDT | NONE | - | - |
| 20 | 1 | PIPPINUSDT | EXACT | 75d358bf598e4c8d9b841961d78c14c2 | 2025-01-24 |
| 21 | 2 | BZUSDT | EXACT | e7a10ca855524655ab3dea73add40ef4 | 2026-03-30 |
| 22 | 2 | XRPUSDT | EXACT | 360038497311 | 2020-01-06 |
| 23 | 2 | REEFUSDT | EXACT | 02895f23b535433e8563175cfb64d1cd | 2021-02-22 |
| 24 | 2 | BNXUSDT | EXACT (ambiguous) | 940d0e48493e4627889c3f46371df70b | 2023-02-22 |
| 25 | 2 | STXUSDT | EXACT | e0aa73262d384ed3a616a4a66f59c9b5 | 2023-02-21 |
| 26 | 2 | OMUSDT | EXACT | 8a72fa2ab4cd474f8e5d62c6158eaeef | 2024-02-13 |
| 27 | 2 | LAYERUSDT | NONE | - | - |
| 28 | 2 | CLUSDT | EXACT | e7a10ca855524655ab3dea73add40ef4 | 2026-03-30 |
| 29 | 2 | LTCUSDT | EXACT | 360038585151 | 2020-01-08 |
| 30 | 2 | RVNUSDT | NONE | - | - |
| 31 | 2 | JASMYUSDT | NONE | - | - |
| 32 | 2 | PERPUSDT | EXACT | e970674b8a4048f69088d21d53a11cb4 | 2023-03-03 |
| 33 | 2 | TONUSDT | EXACT | 57bb7f41d63a44b090b27c3df483344b | 2024-03-01 |
| 34 | 2 | KAITOUSDT | NONE | - | - |
| 35 | 2 | TRXUSDT | EXACT | 360038407872 | 2020-01-14 |
| 36 | 2 | CHRUSDT | EXACT | 86f5ef4c343c4acda8358918e3f77698 | 2021-03-12 |
| 37 | 2 | OPUSDT | EXACT | ce9176af28a148d4993972a1caeffda0 | 2022-06-01 |
| 38 | 2 | LQTYUSDT | EXACT | dc1fa8e36e8c4cbdb6f200bd3aac916e | 2023-03-09 |
| 39 | 2 | BOMEUSDT | EXACT | 543fca9191ba4f3d937d56035a60699a | 2024-03-16 |
| 40 | 2 | BANANAS31USDT | NONE | - | - |
| 41 | 3 | ETCUSDT | EXACT | 360038833831 | 2020-01-15 |
| 42 | 3 | MANAUSDT | NONE | - | - |
| 43 | 3 | INJUSDT | EXACT | c562f0d46b0e404c89d9eb8e56a70a2c | 2022-08-16 |
| 44 | 3 | ARBUSDT | EXACT | 2698359b2ceb45ff94365f060d616b88 | 2023-03-22 |
| 45 | 3 | ETHFIUSDT | NONE | - | - |
| 46 | 3 | SIRENUSDT | NONE | - | - |
| 47 | 3 | LINKUSDT | EXACT | 360038885371 | 2020-01-16 |
| 48 | 3 | ALICEUSDT | EXACT | 09e302f8a778456aa42e0df634cc4e8f | 2021-03-16 |
| 49 | 3 | LDOUSDT | EXACT | d6c6c06ddb074c829d90155b0aba661b | 2022-09-21 |
| 50 | 3 | LEVERUSDT | NONE | - | - |
| 51 | 3 | ENAUSDT | NONE | - | - |
| 52 | 3 | PAXGUSDT | EXACT | 407190c3e5894c679fb4dc1cd7de5982 | 2025-03-27 |
| 53 | 3 | XLMUSDT | EXACT | 360038969011 | 2020-01-19 |
| 54 | 3 | HBARUSDT | NONE | - | - |
| 55 | 3 | APTUSDT | EXACT | f9df5bba5e1c4f1e9289240d0f9344e2 | 2022-10-18 |
| 56 | 3 | BLURUSDT | EXACT | 00b84a2f4a9b44e184722acdbb6d2629 | 2023-04-27 |
| 57 | 3 | SAGAUSDT | NONE | - | - |
| 58 | 3 | FUNUSDT | EXACT | 08f802493a6a424db8906c07c0c0eb17 | 2025-03-31 |
| 59 | 3 | XMRUSDT | EXACT | 360039429631 | 2020-02-02 |
| 60 | 3 | ONEUSDT | EXACT | 45cb73bba8254e52b9c0d7ad597d0402 | 2021-03-17 |

BZUSDT (21) and CLUSDT (28) share article code `e7a10ca855524655ab3dea73add40ef4`
— a multi-symbol bulk launch announcement matched by both targets.

---

## 7. REQUIRED SEMANTIC DISTINCTION

```text
Catalog metadata match != authenticated lifecycle authority.
```

Catalog 48 is a **metadata locator / partial source**. An `EXACT` row above means
only: *a Binance-published announcement title exists that binds this exact
USDT-margined perpetual symbol and reads as a launch announcement.*

It does **not**, on its own, establish any of:

* launch authority;
* delist authority;
* continuous tradability;
* suspension-free lifecycle state;
* interval eligibility.

Separately, and not to be merged or redefined:

```text
MarketObservation
=
authenticated evidence that an exact instrument instance was observed at t
```

A `MarketObservation` is **not** a lifecycle transition. Neither concept may be
collapsed into the other, and neither is upgraded by this receipt.

---

## 8. Complementary-source feasibility probe (Catalogs 49 / 161)

Question asked (already closed): does a **second official Binance source** recover
any of the 17 Catalog-48 residuals?

Catalog taxonomy as enumerated from the same CMS endpoint at `catalogId=0`:

| catalogId | catalogName | total |
|---|---|---|
| 48 | New Cryptocurrency Listing | 2225 |
| 49 | Latest Binance News | 4374 |
| 93 | Latest Activities | 3022 |
| 161 | Delisting | 421 |
| 157 | Maintenance Updates | 576 |
| 51 | API Updates | 81 |
| 128 | Crypto Airdrop | 53 |

Frozen complementary families: **49 (Latest Binance News)** and
**161 (Delisting)**. Catalog 161's coverage begins ~2022-03, so it structurally
cannot reach the older launch-era boundaries.

**Residual positive controls (exactly 4):** `BTCUSDT`, `MANAUSDT`, `ENAUSDT`,
`BIOUSDT`.
**Fake negative control:** `ZZZZNOTREALUSDT`.

```text
RESIDUAL_POSITIVE_CONTROLS_RECOVERED: 0 / 4
  BTCUSDT_RECOVERED:  NO
  MANAUSDT_RECOVERED: NO
  ENAUSDT_RECOVERED:  NO
  BIOUSDT_RECOVERED:  NO

FAKE_CONTROL: REJECTED   (ZZZZNOTREALUSDT → NO_QUALIFYING_BOUNDARY_DOCUMENT_FOUND)

PREFERRED_SOURCE_B: NONE
VERDICT: NO_USEFUL_SECOND_OFFICIAL_SOURCE_FOUND
```

Recorded observations behind the 0/4 (preserved, not re-run):

* **BTCUSDT** — Catalog 49 locates two 2019-09 platform-level articles
  (`360033314152` "Binance Futures Official Launch"; `360033273472` "Binance
  Launches Futures Trading Platforms"). Bodies retrieved at the time; neither
  binds the symbol `BTCUSDT` nor the term "perpetual" — platform go-live notices,
  so no exact-contract binding.
* **MANAUSDT / ENAUSDT / BIOUSDT** — no target-specific article located in
  Catalog 49. In Catalog 48 the nearest articles bind the *wrong instrument
  variant* (MANA → Coin-Margined; ENA → USDC-Margined; BIO → `BIOUSDC`), which is
  why the census already classified them `NONE`.

**Mechanical ceiling found:** no Binance-owned keyword/full-text search endpoint
exists for this CMS — `keyword=` on `list/query`, `article/search/query`,
`search/pc/general` and `apex/search/general` all returned 400/404. The only
deterministic access is chronological pagination (`pageSize` max 50) plus
`article/detail/query?articleCode=`. Any Source B built on this CMS is therefore
blind to boundary language that appears only in article bodies, independent of
catalog choice.

---

## 9. Evidence pointers and what is / is not preserved

**Preserved and durable (in-repo, committed):**

* the frozen target authority and its digest — `experiments/data/step1_4_result.json`
  @ `07f793a`, field `ordered_target_list`;
* the batch-3 recovery lineage — `docs/forensics/QNTYLAB_SCOUT_LIFECYCLE_EXPANSION_V1_BATCH3_DIGEST_RECOVERY.md` @ `12f57d4`;
* everything stated in this receipt, including the full 60-row census matrix (§6),
  selector definition (§3), and the probe outcome (§8).

**Preserved only as ephemeral session scratch at the time of writing** — outside
the repository, under
`/tmp/claude-1000/-home-swirky-DevHub-repos-QntyLab/50023a72-3046-4dfe-8edd-3739d7d51cae/scratchpad/`,
and expected to disappear:

```text
catalog48_records.json   sha256 11a28df819ad29948b5d568749ccfffffb97ac63987faf86acb9bf58e37b4414   (2225 records)
census60_results.json    sha256 788bb59e9608e3f355946b1fcb6f0c4a5b026e4505673bbb5aab36efc4216e14   (60 rows)
census.py                sha256 e6981cc7efc3155dbecea9d34fb6ce0b0d3be2c49943632af159c6964eb8d768   (selector)
run_census.py            sha256 5457c90e1509491442a09b009d6362f6b34d40fb5671ad53481fe8be3bac9180   (driver)
step1_4_result.json      sha256 ead50d55963495341b74d3ffe76c29ad2a1432a66a2e5fa1ef5f1f9f5ec2cb76   (census input copy)
pages/page_1..45.json                                                                              (raw catalog-48 pages)
```

**Explicitly NOT preserved anywhere:**

* the raw Catalog-48 page corpus and the census scripts are **not** committed to
  this repository, so the digests above are attestations only — they cannot be
  re-verified once the scratch directory is gone;
* article **bodies** for the 43 exact matches were never fetched, so no
  body-level boundary text exists for any target;
* the Catalog 49 / 161 probe produced **no** committed artifact; its raw
  responses were transient `/tmp` files. §8 is the durable record of it.

A future researcher can re-derive §4–§6 from scratch by re-enumerating
Catalog 48 with the endpoint in §2 and applying the selector in §3 to the frozen
list at `07f793a`. That would be a **new** enumeration against a live, growing
corpus, so exact article codes may differ for multi-symbol bulk announcements;
it was deliberately not done here.

---

## 10. Verdict

```text
CATALOG_48_SOURCE_ROLE:      PARTIAL_SOURCE  (43 / 60 exact metadata coverage)
SECOND_OFFICIAL_SOURCE:      NO_USEFUL_SECOND_OFFICIAL_SOURCE_FOUND
NEW_SCIENTIFIC_RESULT_CLAIMED: NONE
NETWORK_ATTEMPTS_THIS_TASK:  0
PRODUCTION_CODE_CHANGED:     NONE
```
