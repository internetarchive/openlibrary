# Analytics

> **Status:** `partial`
> **Sources:** codebase investigation against `origin/master` 2026-08-05 (`templates/site/head.html`, `templates/site/footer.html`, `js/ol.analytics.js`, `core/matomo.py`, `admin/vitals.py`); live MTM container contents and production Matomo figures supplied by Mek 2026-08-05; PRs #13038, #13213, #12910, #12227; issues #13020, #13261
> **Last ingested:** 2026-08-05

Open Library runs **four independent telemetry systems**. Knowing which one is authoritative for a given question is most of the work — they disagree, and each has blind spots the others don't.

See [[analytics-events]] for the mechanics of client-side event wiring, and [[core-vitals]] for the product metrics computed on top of Matomo.

---

## The four systems

| System | What it holds | Where it lives | Blocked by ad-blockers / DNT? |
|---|---|---|---|
| **Athena** | IA-wide pageview + custom event pings | `athena.archive.org/0.gif` | Blockable; **ignores DNT** |
| **Matomo** (+ MTM) | OL's own analytics: visits, events, custom dimensions | `apollo.archive.org` (tracking + MTM), `matomo.archive.org` (Reporting API) | Blockable; **respects DNT** |
| **statsd → Graphite** | Server-side counters and gauges | `stats.increment(...)` in Python | **No — server-side, lossless** |
| **Sentry** | Frontend and backend errors | `window.OL_SENTRY` | Not an analytics system; don't use for counting |

**The rule of thumb:** if a number must be *correct* (funnel conversion, "did this feature work"), it has to come from **statsd**. Both client-side systems undercount by an unknown, variable factor. Use Matomo for behavioural shape and segmentation, not for ground truth.

---

## Athena

IA's shared, organisation-wide analytics. Loaded in the footer as a **blocking** script:

```html
<script src="/cdn/archive.org/athena.js"></script>   <!-- footer.html:23 -->
<script src="/static/build/js/all.js"></script>       <!-- footer.html:25 -->
```

It exposes `window.archive_analytics`. OL wraps it in `js/ol.analytics.js`:

- `initAnalytics()` — guards on `if (window.archive_analytics)`, calls `set_up_event_tracking()`, defines
  `ol_send_event_ping()`, sends the pageview, and registers the delegated click handler for
  `[data-ol-link-track]`.
- `ol_send_event_ping({category, action, label})` → `archive_analytics.send_ping({service:'ol', kind:'event', ec, ea, el, ev, ...})` → a `POST` to `athena.archive.org/0.gif`.

Note the param names are Athena's: **`ec` / `ea` / `el`**. Matomo's are `e_c` / `e_a` / `e_n`. This is
the fastest way to tell which system a network request belongs to.

⚠️ **Athena does NOT forward anything into Matomo.** No pipeline exists in either direction
(confirmed by @scottbarnes on #13020). An Athena ping is not evidence a Matomo event was recorded.

---

## Matomo

OL's own analytics instance. **Site ID 6** = openlibrary.org. Version **5.11.2** (confirmed 2026-08-05).

Three distinct pieces, easily conflated:

| Piece | Host | Purpose |
|---|---|---|
| Tag Manager (MTM) container | `apollo.archive.org/js/container_7cLc1b4U.js` | Fires tags on DOM triggers |
| Tracking endpoint | `apollo.archive.org` | Receives events/pageviews |
| Reporting API | `matomo.archive.org` | Read data back out (IP-restricted) |

Bootstrapped in `templates/site/head.html`, gated on `$if not is_bot() and not ctx.get('disable_analytics')`:

```js
var _paq = window._paq = window._paq || [];
_paq.push(['setCustomDimension', 1, <days since registration>]);   // #12227
// one-shot ActivationSuccess on email activation
var _mtm = window._mtm = window._mtm || [];
_mtm.push({'mtm.startTime': ..., 'event': 'mtm.Start'});
g.async = true; g.src = 'https://apollo.archive.org/js/container_7cLc1b4U.js';   // ASYNC
```

Two consequences of that gate worth remembering: `is_bot()` reads `req_context.get().is_bot`, so a
request classified as a bot gets **no analytics at all**, server-side; and `verify_human.html` sets
`disable_analytics` deliberately.

### Custom dimension 1 — "Days Since Registration"

Set per visit from `get_days_registered()` (`openlibrary/accounts/__init__.py`, #12227). Buckets are
discrete, not cumulative: `visitor`, `d0`, `d1+` (1–6d), `d7+`, `d14+`, `d30+`, `d90+`. Read back via
`Live.getLastVisitsDetails` as a **flat `dimension1` field** — *not* nested under `customDimensions`.
This is the foundation of the [[core-vitals]] Retention Score.

`setUserId` is **not** wired anywhere, so registered patrons cannot be tracked across visits — which
is why Retention Score is a snapshot metric, not a cohort one.

### Reporting API access

`openlibrary/core/matomo.py` (`MatomoClient`) — read-only, exact-match method allowlist, POSTs so the
token stays out of query strings. Token is `matomo_api` in `openlibrary.yml`. **Still unmerged as of
2026-08-05** — it lives in PR #13213, not on master.

`matomo.archive.org` is IP-restricted to IA's network. Production reaches it directly; from a dev
machine use an allowlisted forward proxy (`HTTPS_PROXY`) — see [[core-vitals]].

---

## statsd → Graphite

The only lossless counter. Plain Python:

```python
from openlibrary.core import stats
stats.increment("ol.account.verify.success")
```

Existing counters worth knowing: `ol.account.xauth.login` (**every** xauth login — not scoped to any
sub-flow), `ol.account.verify.success` / `.fail`, `ol.account.safe_mode`,
`ol.verify_human.challenged` / `.verified`.

Core Vitals emits `stats.ol.retention.*`, `stats.ol.engagement.*`, `ol.stats.content_value_score`.

**Reach for this whenever the question is "how often does X actually happen?"** No ad-blocker, no
DNT, no script-load race. If a funnel matters, instrument both the numerator and the denominator
here — a success counter with no impression counter cannot produce a rate.

---

## Choosing a system

| Question | Use | Why not the others |
|---|---|---|
| How many patrons did X? | **statsd** | Client-side undercounts unpredictably |
| What's the conversion rate of a funnel? | **statsd** (both ends) | Needs a lossless denominator |
| How do patrons move through the UI? | Matomo | statsd has no session/segment model |
| Behaviour split by patron tenure | Matomo (dimension 1) | Only Matomo has it |
| Is an event firing at all, right now? | Browser Network tab | Reports lag; see the traps below |
| Did a specific known visit do X? | Matomo Visits Log | Near-real-time, per-visit |

---

## Traps

Every one of these has cost real investigation time.

- **Matomo respects DNT; Athena does not.** With `DNT: 1`, a click produces a visible
  `athena.archive.org/0.gif` and **no Matomo request whatsoever**. A healthy page looks broken. Check
  request headers before concluding an event is lost.
- **`window._paq` becomes an object, not an array.** The array is only the pre-load placeholder; once
  the tracker initialises it is replaced by a tracker object with a `push` method. So
  `Array.isArray(window._paq) === false` is the **healthy** state. Test `typeof window.Matomo ===
  'object'` instead.
- **A `_paq.push` spy can miss MTM-fired events.** MTM's tags may call the tracker directly rather
  than going through the queue, so wrapping `push` is not a reliable observer. Watch the network.
- **MTM's container is `async`; Athena's script is blocking.** Athena's click handler is bound during
  page load; MTM's may not be. A fast click on an above-the-fold CTA can reach Athena and miss Matomo.
- **The MTM container config is not in the repo.** Tags, triggers, and variables live server-side and
  can only be read in the Matomo UI. Never infer them from code — see [[analytics-events]] for the
  confirmed contents.
- **DevTools console context.** OL pages embed archive.org iframes; if the context dropdown is on a
  frame, `document.querySelector` and `window._paq` both lie. Check `window.top === window`.
- **bfcache.** Going "back" to a banner can restore a page whose cookie was already cleared; you may
  be inspecting a stale render.
- **A `Closes #NNNN` line can close an issue whose real ask was "verify in the admin UI."** #13020 was
  auto-closed one second after #13038 merged; the verification never happened, and three PRs were
  built on an unconfirmed assumption for six weeks.

---

## Dependencies

**Depends on:** IA's `athena.js` CDN script · the MTM container (@cdrini administers) · statsd/Graphite ·
`get_days_registered()` for dimension 1.

**Depended on by:** [[core-vitals]] (Retention, Engagement, Participation scores) · any Behaviour →
Events reporting · funnel analysis.

---

*See [[README]] · [[METHODOLOGY]] for ingest rules*
