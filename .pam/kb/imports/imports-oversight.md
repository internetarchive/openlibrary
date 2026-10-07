# Imports — oversight rules

> **Status:** current · **Owner:** impa (Imports Division Lead)
> **Written:** 2026-09-28, at Mek's request via Ada
> **Rule for this page:** every watch below is a command, not an intention.
> A watch that exists only here is not a watch.

## 1. What I watch

| # | Watch | Command | Act when |
|---|---|---|---|
| W1 | **Completeness, not arrival** | `tools/completeness-watch.py` | any provider < 10% cover ratio on ≥20 works |
| W2 | **Liveness denominator** | `bookworm register --show` + arrivals | see §2 — never arrivals alone |
| W3 | **Prior work before filing** | `tools/prior-work.sh <topic>` | any hit I did not already know about |
| W4 | **Division memory** | `tools/imports-dept-status.sh` | vault unbacked, or wiki unpublished |
| W5 | **Teardown safety** | `tools/branch-pushed.sh <repo>` | anything but SAFE |
| W6 | **Queue depth** | `gh issue list --label "Priority: 2"` | > 25 open in my domain |

**W1 is the one that earns the page.** Bookdash: 814 works, **0%** cover ratio,
against Standard Ebooks at **100%**. One HTTP call, and it would have fired in
week one instead of year one. An arrival count showed 814 and read as success.

## 2. Arrival counts are ambiguous — always report a denominator

**The trap Ada named, and it is the sharpest thing in this page:** *a watch that
asks "did records arrive" cannot distinguish a dormant pipeline from a failing
one.* Both report zero.

That is the WAF-denials failure in a different subsystem: a metric improved
because the thing measuring it stopped. So:

> **Never report "N records arrived." Report "N arrived, from M feeds active,
> against K offered."**

Concretely, the two states that both look like zero:

- **Dormant** — `register --show` lists 0 active feeds. Nothing ran. *This is
  today's state,* and it is not a failure, it is an un-flipped switch.
- **Failing** — feeds active > 0 and arrivals still 0. This is the write-rate
  hypothesis: 79 of 94 Lenny records returned `internal-error` and every one
  succeeded on serial retry, cause never established.

**The active-feed count prints first, above any arrival total**, because an
encouraging number at the top is where people stop reading.

## 3. Cadence

**Per review cycle, not per day.** A daily cadence on a pipeline that is
switched off manufactures noise and trains me to skim.

**Off-cadence triggers — any one of these, immediately:**

- a merge to master touching `catalog/add_book/`, `core/imports.py`, or
  `bookworm/`
- **a feed activation** (the only moment W2's two states can change)
- an agent reporting a schema or contract change
- any report of records "not arriving" — because that phrase is exactly the
  ambiguous one in §2

## 4. Decide vs escalate

Ada asked me to write this line properly, so here it is without the flattering
version:

> **I decide anything inside the contract, the sequence, and the seams. I
> escalate only when a human must choose between options that are all
> available. Where I have gone wrong is not over-deciding — it is escalating a
> question I had not finished looking into, which arrives looking identical to
> a decision request.**

Three times in one day: a 401 became *"nothing to run against"*; egress became
*"only a prod check settles it"*; and the feed cursor became *"one query settles
it and I have no production DB access"* when `register --show` prints status
**and** cursor, read-only, needing no credentials.

**So the forcing rule, before any escalation naming access:**

> **Name the read-only command that would answer this, and say why it does not.
> If I cannot name one, I have not finished looking.**

And the subtraction that goes with it: when I put two items on Mek's page, I ask
which is actually agent-shaped. Of the two agents named for my division, the
feed-registry cron was **already written** (olsystem#458, +14 lines) and its
remainder needs production access, not an agent. One real ask beats two.

## 5. My blind spot

**Invariants I authored that no venue exercises.**

I froze a nine-marker import contract and exercised it in five venues, which
felt like thorough verification and was — *of the parts the venues touched.*
Marker [8] (global dedup on `source_id`) was my own invention, expressible in
no DDL, and therefore **exercised by nothing**. It survived five venues, a
freeze, and several days, and was wrong: master implements *both* scopes
deliberately, and my version would have broken legitimate re-imports.

The shape: **coverage measures the code, not the claims I added on top of it.**
Re-reading my own contract re-confirmed the belief that produced it. What caught
it was a different agent reading the same source.

**Counter-practice:** for any invariant I author that the schema cannot express,
name the venue that would fail if it were false — before freezing. If there
isn't one, it is a preference, and it gets labelled as one.

---

*See [[imports-plan-2026-09]] · [[bookworm-import-contract]] · [[METHODOLOGY]]*
