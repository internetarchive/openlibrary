# Analytics Events (client-side)

> **Status:** `partial`
> **Sources:** codebase investigation against `origin/master` 2026-08-05 (`js/ol.analytics.js`, `js/banner-analytics.js`, `components/lit/OlBanner.js`, `plugins/upstream/account.py`, `fastapi/account.py`, `templates/site/head.html`); PRs #13038, #12910, #12849, #12764; issue #13020; filed as #13261
> **Last ingested:** 2026-08-05

How Open Library custom interaction events reach Matomo — and the two-pipeline split that has now silently swallowed events three separate times.

See [[core-vitals]] for Matomo *scoring* (Retention Score, dimension 1, `MatomoClient`). This page is about **event tracking wiring**, which is a different failure surface.

---

## The single most important fact

**There are two analytics pipelines, and only one of them reaches Matomo.**

| Path | Call | Lands in |
|---|---|---|
| Athena (IA-wide) | `window.archive_analytics.ol_send_event_ping({category, action, label})` | **Athena only — NOT Matomo** |
| Matomo | `trackEvent(category, action, label)` from `js/ol.analytics.js` → `window._paq.push(['trackEvent', …])` | **Matomo** |
| Matomo (declarative) | `data-ol-link-track="Category\|Action\|Label"` attribute, matched by an **MTM DOM trigger** | **Matomo** |

Athena does **not** forward events into Matomo. Confirmed by @scottbarnes on
[#13020](https://github.com/internetarchive/openlibrary/issues/13020) and documented in
[#13038](https://github.com/internetarchive/openlibrary/pull/13038).

`ol_send_event_ping` still looks like the house style — it is the older, more widely-copied idiom
(`Carousel.js`, `lazy-carousel.js`, `index.js`, `banner-analytics.js` all use it). **Copying it is
how this bug keeps getting reintroduced.** If an event needs to appear in Matomo, it must go through
`trackEvent()` or carry a `data-ol-link-track` attribute in the light DOM.

### The two paths are independent — Athena does NOT forward to Matomo

This is the single most misunderstood thing here, so state it exactly. A click on a
`data-ol-link-track` element is read by **two separate systems that do not feed each other**:

```
click on [data-ol-link-track="Category|Action|Label"]
   ├─→ OL's own jQuery handler (ol.analytics.js) → ol_send_event_ping → athena.archive.org/0.gif
   └─→ MTM trigger Data_OL_Link_Track → tag OL_Data_Link_Tracker → Matomo event
```

**Confirmed MTM container contents** (verified against the live container 2026-08-05 — this had
never been written down anywhere, and its absence caused a full investigation to stall):

| Type | Names |
|---|---|
| Tags | `Matomo Analytics`, **`OL_Data_Link_Tracker`**, `Search result item chapter click`, `Search result item subjects click` |
| Triggers | **`Data_OL_Link_Track`**, `Pageview`, `Search result item chapters click`, `Search result item subjects click` |
| Variables | `Matomo Configuration`, **`OL_EventCategory`**, **`OL_EventAction`**, **`OL_EventName`** |

So both of these are true at once, and they are not in conflict:
- There is **no Athena → Matomo pipeline** (confirmed by @scottbarnes on #13020).
- Attribute-tagged events **do** reach Matomo — because MTM independently watches the same clicks.

The practical consequence: an element **with** the attribute reports to Matomo; an element
**without** it (Shadow DOM internals, or a Lit-rendered button like `.ol-banner__close`) does not,
no matter how many Athena pings it sends.

### ⚠️ Matomo respects Do-Not-Track — Athena does not

This will make a healthy page look broken during manual testing. With `DNT: 1` set, clicking a
tracked element produces a visible `athena.archive.org/0.gif` request and **no Matomo request at
all** — because the `Matomo Configuration` variable honours DNT while Athena ignores it.

Confirmed 2026-08-05: this exact observation was briefly misread as "the MTM trigger doesn't
exist," when the trigger was fine and the tester simply had DNT enabled. **Before concluding a
Matomo event is missing from a network capture, check for `dnt: 1` in the request headers.** Test
with DNT off, or verify against Matomo's Events report rather than the network tab.

### Useful discriminator: which categories can only come from which path

Only these seven call `trackEvent()`/`_paq` in code — everything else in Matomo's Events report
must have arrived via the MTM attribute trigger: `SearchModal`, `SearchFilter`, `SearchSort`,
`ResultsFilter`, `SearchLayout`, `BookOptions`, `Account`. So if an attribute-only category
(`ReadingLog`, `StarRating`, `Share`, `HeaderBar`, `MyBooksSidebar`, `Download`,
`YearlyReadingGoals`, `CheckInForm`) appears in Matomo, the MTM trigger is working. Note
`BookOptions` uses both mechanisms and cannot discriminate.

### ⚠️ The attribute must be in the SERVER-RENDERED DOM — JS-applied attributes do not report

**Put `data-ol-link-track` in the template, never via `setAttribute()`.**

Evidence (2026-08-05): of all `data-ol-link-track` usages in the codebase, **59 template files carry
it statically** and exactly **one** applies it dynamically —
`templates/account/view.html:30`, which does
`link.setAttribute('data-ol-link-track', 'PreserveIntent|Continue')` inside a `DOMContentLoaded`
handler. That one is the only event with an inexplicably low Matomo count: roughly **10/day against
~3,500 registrations/day** (~0.3%), on a prominent above-the-fold call-to-action where a double-digit
percentage would be expected.

The two paths behave differently on a dynamically-added attribute, which is what makes this
diagnosable:

| Reader | Mechanism | Sees a JS-added attribute? |
|---|---|---|
| OL → Athena | `$(document).on('click', '[data-ol-link-track]')` — jQuery delegation, evaluated at click time | **Yes** |
| MTM → Matomo | `Data_OL_Link_Track` trigger + `OL_EventCategory`/`OL_EventAction` variables | **Apparently not** |

That asymmetry was observed directly: clicking Continue on production produced an
`athena.archive.org/0.gif` with `ec=PreserveIntent&ea=Continue`, while Matomo recorded nothing.

⚠️ The exact MTM-side reason is **not yet confirmed** — most likely the `OL_Event*` variables are
DOM-Element-type variables resolved at container load (Pageview scope) rather than at click time. To
confirm, use **MTM Preview/Debug mode** and watch whether `Data_OL_Link_Track` fires and what the
variables resolve to. Do not treat the mechanism as settled until that is done; only the *symptom*
(Athena yes / Matomo no) is established.

**The fix, regardless of mechanism:** render the attribute server-side. For this banner the `<a>` is
already built in `get_pending_action_banner()` (`plugins/upstream/mybooks.py`), so the attribute
belongs in that f-string, which also makes the inline `DOMContentLoaded` script redundant.

### The MTM trigger cannot see into Shadow DOM

Matomo ingests declarative events via a Matomo Tag Manager DOM trigger keyed on
`data-ol-link-track`. That trigger is a selector-based click matcher, so an attribute on an element
inside a **Shadow root is invisible to it**. This is why the Lit search modal and `ol-toggle`
needed `trackEvent()` (#13038).

⚠️ The MTM container config lives server-side (`https://apollo.archive.org/js/container_7cLc1b4U.js`)
and is **not readable from the repo**. "The trigger keys on `data-ol-link-track`" is sourced from
#13038/#13020, not verified directly. Matomo admin is @cdrini.

### Known recurrences of this exact bug

| When | Where | Fix |
|---|---|---|
| 2026-06-25 | Search-funnel events (#12948) never reached Matomo | #13038 — added `trackEvent()`, dropped the Athena ping |
| 2026-07-17 | `PreserveIntent\|Dismiss` (#12910 replaced the attribute with an Athena ping) | #13261 → PR #13264 |
| 2026-08-04 | Book Preview / Search Inside events | `4e9a1e02e` in `dialog.js` |

### The `_paq` path is confirmed working in production (2026-08-05)

Do not re-litigate this. Behaviour → Events, production, site 6:

```
SearchModal  9,325 events
  Open 3,076 · ResultsShown 2,658 · SeeAllResults 1,730 · ResultClick 1,076 · NoResults 785
```

These are the events #13038 rewired, and they can **only** have arrived via `_paq` — `SearchModal`
is a Shadow DOM Lit component, which is exactly why the `data-ol-link-track` DOM trigger cannot see
it. So `trackEvent()` → `_paq` → Matomo demonstrably works.

Two things worth keeping from how long this took to establish:

- It had never actually been verified before 2026-08-05. #13020 (the issue asking for admin-side
  confirmation) was **auto-closed one second after #13038 merged**, by its `Closes #13020` line —
  not by anyone checking Matomo. Three PRs were built on an unconfirmed pattern. A `Closes` line
  closing an issue whose actual ask was "verify in the admin UI" is a real failure mode: the code
  landed, the verification never happened, and the issue looked done.
- It also settles the ad-blocker question **quantitatively**: 9,325 events get through, so privacy
  tooling is a partial discount, not a suppressor. An event sitting at exactly 0 against that
  baseline is *absence* (a wiring bug), not *low usage*. Use that as the discriminator.

---

## `alwaysUseSendBeacon` — absent, but a no-op (do not "fix" it)

#13038's PR body states `head.html` now pushes `['alwaysUseSendBeacon']`. **It does not.** The
string appears nowhere on `origin/master`, and `git log -S alwaysUseSendBeacon` shows it was never
added to `head.html`.

**This is harmless.** Confirmed 2026-08-05: the instance is **Matomo 5.11.2**, and
`alwaysUseSendBeacon` has been **on by default since Matomo 4**. So the missing push changes
nothing, and adding it would be a no-op.

⚠️ This page previously claimed the absence caused "a silent partial undercount across every
navigation-adjacent event." **That was wrong** — asserted from #13038's description without checking
the tracker version, and it briefly sent an investigation looking for event loss that does not
exist. The lesson generalises: before treating a missing Matomo tracker option as a defect, check
the instance version against when that option became the default.

---

## `<ol-banner>` renders into the LIGHT DOM

Easy to get wrong, because most Lit components do the opposite. `OlBanner` overrides:

```js
createRenderRoot() { return this; }
```

So there is **no shadow root**. Its `connectedCallback()` captures the server-rendered children,
moves them into a `_content` span, and re-renders them inside its own structure — but all of that
stays in the light DOM. Practical consequences:

- `container.querySelector('.some-child')` from an inline template script **does work**.
- Click events are **not retargeted**, so `$(document).on('click', '[data-ol-link-track]')` and the
  MTM trigger both work on banner children.
- Therefore a banner *can* use the declarative `data-ol-link-track` path. It does not need
  `trackEvent()` — which makes the #12910 regression avoidable rather than inherent.

`ol-banner-dismiss` is dispatched with `bubbles: true, composed: true`, so a `document`-level
listener does receive it. The dismiss **button** itself (`.ol-banner__close`, rendered by
`OlBanner.render()`) carries **no** `data-ol-link-track`, so the MTM trigger has nothing to match —
which is why Dismiss tracking has to be added deliberately.

---

## Preserve Intent: the metric is blind to its own success path

Feature background: #9409, shipped via #12764 (mechanism), #12849 (tracking), #13095 (verify-redirect
removal). An unauthenticated action is stashed in a `pending_action` cookie and resumed after
login/registration.

**The banner — and therefore all `PreserveIntent` event tracking — only renders on the *degraded*
path.** In `plugins/upstream/account.py` (~617–625):

```python
if not is_safe_redirect(redirect) or any(path in redirect for path in blacklist):
    redirect = "/account/books"                        # cookie KEPT  → banner renders
else:
    web.setcookie("pending_action", "", expires=-1)    # cookie CLEARED → straight to the action
```

- Safe redirect (the normal case — `js/index.js` sends `/account/login?redirect=<targetUrl>`):
  cookie cleared, patron goes **directly** to the intended action. **No banner, no event.**
  Every *successful* resumption is invisible to the metric.
- Banner only appears when redirect is empty/unsafe/blacklisted. Blacklist: `/account/login`,
  `/account/create`, `/account/verify`.
- ⇒ The dominant producer of banner impressions is the **register → verify-email** flow, because
  `/account/verify` is blacklisted — *not* ordinary login. This is why the numbers look like a
  handful per day rather than tracking real feature usage.
- The FastAPI twin (`fastapi/account.py` ~236–280) has the same branch but falls back to `/`
  instead of `/account/books`. `account/view.html` is not rendered at `/`, so **that path produces
  no banner at all**.
- Cookie TTL is 36h (`max-age=129600`, `queueAction` in `js/utils.js`) — older intent is dropped.
- Trigger surface is 6 templates carrying `.js-login-intent`: `ReadButton`, `LoanStatus`,
  `StarRatings`, `follow/follow`, `my_books/primary_action`, `type/edition/modal_links`.

**Do not read `PreserveIntent|Continue` as "how often Preserve Intent works."** It measures how
often it *nearly failed and the patron recovered manually*.

---

## There is no server-side ground truth for `pending_action`

Tempting and wrong: `stats.increment("ol.account.xauth.login")` sits **after** the if/else in
`account.py` and fires on **every** xauth login. It is a general login counter and cannot serve as a
denominator for pending-action resumptions.

No counter exists on either `pending_action` branch. Adding one to **both** (cleared/happy and
fallback) is the only way to measure the feature independently of client-side analytics — and the
only way to see the happy path at all. Recommended in #13261; not built.

---

## Debugging recipe

Spy on the Matomo queue in DevTools (from #13038):

```js
const o = _paq.push.bind(_paq); _paq.push = (...a) => { console.log('PAQ', ...a); return o(...a); };
```

If an interaction logs nothing here, it is not reaching Matomo — regardless of whether an Athena
ping fired. Checking the network tab for an Athena ping proves nothing about Matomo.

To force the Preserve Intent banner locally: set a `pending_action` cookie to
`encodeURIComponent(JSON.stringify({action, name, url, type}))` and load `/account/books` while
logged in. Note `get_pending_action_banner()` returns `""` for a cookie value of `"1"` or for
missing `action`/`url`, so a malformed cookie fails silently.

---

## Common Confusion

- **"The event fires, I saw the network request"** — an Athena ping is not a Matomo event. See the
  two-pipeline table above.
- **"It's just ad-blockers"** — real, but it cannot explain a *zero*. A structurally-absent path and
  a blocked beacon look similar in a dashboard and are diagnosed completely differently. Quantify
  before blaming blockers.
- **"Lit component ⇒ Shadow DOM ⇒ needs `trackEvent()`"** — not for `ol-banner`, which renders into
  the light DOM.
- **Low event count ≠ low feature usage** — for Preserve Intent the metric only covers the fallback
  path (above).

---

## Dependencies

**Depends on:** Matomo Tag Manager container (server-side config, @cdrini) · IA `archive_analytics`
/ athena.js (CDN-loaded, guarded by `if (window.archive_analytics)`) · `head.html` analytics block
(skipped entirely for bots and when `ctx.disable_analytics` is set).

**Depended on by:** [[core-vitals]] Engagement/Retention scoring · any Behaviour → Events reporting.

---

*See [[README]] · [[METHODOLOGY]] for ingest rules*
