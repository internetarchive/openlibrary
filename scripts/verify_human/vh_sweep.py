#!/usr/bin/env python3
"""Size a fail2ban jail for the verify_human challenge gate from nginx access logs,
BEFORE any config is written.

WHICH LOG LINE IS "A CHALLENGE"
-------------------------------
nginx never redirects. $should_challenge has exactly one consumer --
`proxy_set_header X-OL-Verify-Human` (openlibrary/docker/web_nginx.conf:167) -- and the
app decides, raising web.seeother (a 303) in CookieValidationProcessor.__call__
(openlibrary/plugins/openlibrary/processors.py:154-156). So ONE challenge produces
up to two access-log lines:

  1. a 303 on the ORIGINAL url        <- the challenge was ISSUED  (always logged)
  2. GET /verify_human?next=...       <- the client FOLLOWED the redirect (only then)

Counting (2) silently excludes every client that ignores 3xx -- curl without -L,
requests without allow_redirects, anything treating a redirect as a failed fetch.
That is precisely the population a jail exists to ban. So this script counts (1)
by default, and reports (2) alongside it: their ratio is the redirect-following
rate, which bounds how blind a /verify_human-only analysis would have been.

Completion is `POST /verify_human` (account.py:1428-1444). It is unvalidated and
always succeeds, so there is no failed verification to count. "Completed" means the
client followed the redirect AND ran the JS AND clicked -- evidence of a browser,
not proof of a human.

WHAT THIS CANNOT TELL YOU
-------------------------
* Field 1 of the `iacombined` format is $ip_hashed, not $remote_addr: md5(daily_seed
  + ip) truncated to 24 bits (olsystem/etc/nginx/logging.js). At production volume
  16.7M buckets are SATURATED, not lightly collided -- a large minority of buckets
  hold several real addresses and each bucket's event stream is their SUM. That is a
  first-order UPWARD bias on every ban count, worst at low thresholds. A real jail
  keys on raw IPs and does not have this problem.
* The seed rotates at midnight, so windows never cross a date boundary (can only
  under-ban) and cross-midnight ban concurrency is not measurable here.
* These are PRE-JAIL observations. Once a jail exists, banned traffic is dropped at
  the firewall and stops appearing, so the distribution is inflated for exactly the
  addresses a jail would silence. A knee picked from this curve will move.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import math
import re
import sys
from datetime import datetime

LINE_RE = re.compile(
    r"^(?P<ip>\S+)\s+(?P<host>\S+)\s+(?P<ruser>\S+)\s+"
    r"\[(?P<ts>[^\]]+)\]\s+"
    r'"(?P<request>(?:[^"\\]|\\.)*)"\s+'
    r"(?P<status>\d{3})\s+(?P<bytes>\S+)\s+"
    r'"(?P<referer>(?:[^"\\]|\\.)*)"\s+'
    r'"(?P<ua>(?:[^"\\]|\\.)*)"'
)

# $is_identifying_ua, openlibrary/docker/nginx.conf:69-77. A UA matching any of these
# is never challenged, so such a line must never appear as a challenge.
IDENTIFYING_UA_RE = re.compile(r"bot|spider|crawl|google|http|@", re.IGNORECASE)

VH_PATH = "/verify_human"

# Gated prefixes whose only realistic source of a GET+303 is the challenge redirect.
# /search is deliberately EXCLUDED: worksearch/code.py:762,770,779,795,809 redirect
# legitimately (ISBN/OLID lookups, param canonicalisation), which would contaminate
# the proxy. The v=/m=/page=/action= and $ua_suspicious triggers fire on arbitrary
# paths and are not identifiable from status alone. So "issued" is a LOWER BOUND on
# real challenges -- undercounting, never inventing.
ISSUED_PREFIXES = ("/subjects/", "/recentchanges", "/explore")


def opener(path: str):
    return gzip.open(path, "rt", errors="replace") if path.endswith(".gz") else open(path, errors="replace")


def parse_request(request: str) -> tuple[str, str]:
    parts = request.split(" ")
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[1].split("?", 1)[0]


class Corpus:
    def __init__(self) -> None:
        self.issued: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
        self.followed: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
        self.denied: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
        self.completed: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
        self.ua_of: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
        self.per_day_ips: dict[str, set[str]] = collections.defaultdict(set)
        self.total = 0
        self.unparsed = 0
        self.exempt_ua_seen = 0  # denominator: exempt-UA requests anywhere
        self.exempt_ua_challenged = 0  # numerator: exempt-UA lines that look challenged


def load(paths: list[str]) -> Corpus:
    c = Corpus()
    for path in paths:
        try:
            fh = opener(path)
        except OSError as exc:
            print(f"!! cannot open {path}: {exc}", file=sys.stderr)
            continue
        with fh:
            for line in fh:
                c.total += 1
                m = LINE_RE.match(line)
                if not m:
                    c.unparsed += 1
                    continue
                try:
                    # %z keeps this tz-aware; naive .timestamp() resolves in the
                    # runner's local zone and manufactures bans across a DST fall-back.
                    dt = datetime.strptime(m.group("ts"), "%d/%b/%Y:%H:%M:%S %z")
                except ValueError:
                    c.unparsed += 1
                    continue

                ip, ua, status = m.group("ip"), m.group("ua"), m.group("status")
                day = dt.strftime("%Y-%m-%d")
                key = (day, ip)
                c.per_day_ips[day].add(ip)
                exempt_ua = bool(IDENTIFYING_UA_RE.search(ua))
                if exempt_ua:
                    c.exempt_ua_seen += 1

                method, path_only = parse_request(m.group("request"))
                ts = dt.timestamp()

                if path_only == VH_PATH:
                    if method == "GET":
                        # A 403 here is ModSecurity denying the CHALLENGE PAGE itself,
                        # before the app runs: no template, no JS, no POST, no vf cookie.
                        # The visitor is locked out of the very page that would clear
                        # them. Rule 50055 (which carves ARGS:next out of the shell/RCE
                        # rules) is NOT on olsystem master -- verified with
                        # `git log --all -S'id:50055'`, which finds it only on
                        # security/redact-waf-log-secrets and modsec/sweep-2026-09-10.
                        # So this is live behaviour, and these addresses look exactly
                        # like scrapers to a no-completion rule.
                        (c.denied if status == "403" else c.followed)[key].append(ts)
                    elif method == "POST":
                        c.completed[key].append(ts)
                    continue

                if method == "GET" and status == "303" and path_only.startswith(ISSUED_PREFIXES):
                    c.issued[key].append(ts)
                    c.ua_of[key][ua] += 1
                    if exempt_ua:
                        c.exempt_ua_challenged += 1
    return c


def ban_trigger(times: list[float], maxretry: int, findtime_s: int) -> tuple[float, float] | None:
    """Earliest (window_start, trigger_time) where maxretry events fall within findtime.

    Mirrors fail2ban 0.10+: failures older than now-findtime are pruned on each new
    event and a ban fires when the retained count reaches maxretry.
    """
    if len(times) < maxretry:
        return None
    ts = sorted(times)
    for i in range(maxretry - 1, len(ts)):
        start = ts[i - maxretry + 1]
        if ts[i] - start <= findtime_s:
            return start, ts[i]
    return None


def peak_concurrent(bans: list[float], bantime_s: int) -> int:
    """Max simultaneously-active bans -- what ipset maxelem must accommodate."""
    if not bans:
        return 0
    events = sorted([(t, 1) for t in bans] + [(t + bantime_s, -1) for t in bans])
    cur = peak = 0
    for _t, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def parse_duration(text: str) -> int:
    """ "3h" -> 10800. A bare number is taken as seconds."""
    text = text.strip().lower()
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return int(text[:-1]) * mult[text[-1]] if text[-1] in mult else int(text)


def report_volumes(c: Corpus, event: str) -> None:
    n_issued = sum(len(v) for v in c.issued.values())
    n_followed = sum(len(v) for v in c.followed.values())
    n_denied = sum(len(v) for v in c.denied.values())
    n_completed = sum(len(v) for v in c.completed.values())

    print("=" * 80)
    print(f"verify_human jail simulation   (event = challenges {event.upper()})")
    print("=" * 80)
    print(f"lines read          : {c.total:,}  (unparsed {c.unparsed:,})")
    print(f"challenges ISSUED   : {n_issued:,}   GET+303 on {'|'.join(ISSUED_PREFIXES)} (lower bound)")
    print(f"challenges FOLLOWED : {n_followed:,}   GET {VH_PATH} -> 200")
    print(f"challenge DENIED    : {n_denied:,}   GET {VH_PATH} -> 403  <- LOCKED OUT, not evasive")
    print(f"completions         : {n_completed:,}   POST {VH_PATH}")
    if n_issued:
        print(f"redirect-follow rate: {100.0 * n_followed / n_issued:5.1f}%  <- clients invisible to a /verify_human-only count")
    if n_followed:
        print(f"completion rate     : {100.0 * n_completed / n_followed:5.1f}%  of successful followers clicked through")
    if n_followed + n_denied:
        print(f"lockout share       : {100.0 * n_denied / (n_followed + n_denied):5.1f}%  of challenge-page loads were 403'd")
    print(f"days covered        : {len(c.per_day_ips)}")


def report_exemption(c: Corpus) -> None:
    print()
    if c.exempt_ua_challenged:
        print(f"** WARNING: {c.exempt_ua_challenged:,} challenges to UAs that $is_identifying_ua should exempt.")
        return
    print("exemption check: 0 challenges to an $is_identifying_ua UA, out of")
    print(f"  {c.exempt_ua_seen:,} exempt-UA requests seen anywhere in the log.")
    if c.exempt_ua_seen == 0:
        print("  ** VACUOUS: no exempt-UA traffic in this sample, so this proves nothing.")


def report_collisions(c: Corpus) -> None:
    print()
    print("hash-collision load (24-bit $ip_hashed, 16,777,216 buckets):")
    for day in sorted(c.per_day_ips):
        n = len(c.per_day_ips[day])
        lam = n / 16_777_216
        multi = (1 - (1 + lam) * math.exp(-lam)) / (1 - math.exp(-lam)) if n else 0
        print(f"  {day}: {n:,} pseudonyms, load {lam:.3f}, ~{100 * multi:.1f}% of occupied buckets hold >1 real IP")


def report_distribution(events: dict[tuple[str, str], list[float]], event: str) -> None:
    print()
    print(f"challenge-count distribution per (day, pseudonym)  [{event}]:")
    dist = collections.Counter(len(v) for v in events.values())
    total_pairs = len(events) or 1
    seen = 0
    peak_bar = max(dist.values()) if dist else 1
    for count in sorted(dist):
        at_or_above = total_pairs - seen
        seen += dist[count]
        bar = "#" * min(50, dist[count] * 50 // peak_bar)
        print(f"  {count:>6} : {dist[count]:>8,} IPs  ({100.0 * at_or_above / total_pairs:6.2f}% >= this)  {bar}")


def report_sweep(
    c: Corpus,
    events: dict[tuple[str, str], list[float]],
    thresholds: list[int],
    findtime_min: int,
    findtime_s: int,
    bantimes: list[tuple[str, int]],
    event: str,
) -> None:
    print()
    print(f"threshold sweep (findtime={findtime_min}m, event={event}):")
    print("  RAW = ban on count alone.  NC = ban only if the address never completed")
    print("  a challenge AT OR AFTER the window that triggered the ban (a completion")
    print("  before it is stale and does not vouch for the burst).")
    print()
    hdr = f"  {'maxretry':>8} | {'RAW':>9} {'NC':>9} {'FP avoided':>11} {'of NC: LOCKED':>14} | " + " ".join(f"{'peak@' + b:>11}" for b, _ in bantimes)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for mr in thresholds:
        raw_keys, nc_keys, nc_times = [], [], []
        for key, times in events.items():
            trig = ban_trigger(times, mr, findtime_s)
            if not trig:
                continue
            window_start, trigger_t = trig
            raw_keys.append(key)
            if not any(ct >= window_start for ct in c.completed.get(key, ())):
                nc_keys.append(key)
                nc_times.append(trigger_t)
        locked = sum(1 for k in nc_keys if c.denied.get(k))
        peaks = " ".join(f"{peak_concurrent(nc_times, s):>11,}" for _b, s in bantimes)
        print(f"  {mr:>8} | {len(raw_keys):>9,} {len(nc_keys):>9,} {len(raw_keys) - len(nc_keys):>11,} {locked:>14,} | {peaks}")
    print()
    print("  'FP avoided' = addresses the RAW rule bans that had a browser complete a")
    print("  challenge inside the triggering window. 'peak@' = max simultaneously-active")
    print("  NC bans, i.e. the floor for ipset maxelem (set it explicitly: modsecurity-")
    print("  worldcat silently truncated at the 65,536 default).")
    print()
    print("  'of NC: LOCKED' = addresses the no-completion rule would ban that were 403'd")
    print("  on the challenge page. They could not complete; they were prevented. This is")
    print("  contamination CORRELATED with the ban signal, not noise: if it is non-trivial")
    print("  next to the knee, no threshold from this data is trustworthy until 50055 ships.")


def report_top(c: Corpus, events: dict[tuple[str, str], list[float]], event: str, top: int) -> None:
    print()
    print(f"top {top} by {event} count:")
    for key, times in sorted(events.items(), key=lambda kv: -len(kv[1]))[:top]:
        day, ip = key
        ua = c.ua_of[key].most_common(1)[0][0][:74] if c.ua_of[key] else "-"
        if c.completed.get(key):
            did = "completed"
        elif c.denied.get(key):
            did = "403 LOCKED OUT"
        else:
            did = "NEVER completed"
        span = (max(times) - min(times)) / 60 if len(times) > 1 else 0
        print(f"  {day} {ip:>15} {len(times):>7} over {span:>7.1f}m  {did:<15} {ua}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--maxretry", default="3,5,10,20,50,100")
    ap.add_argument("--findtime", type=int, default=15, help="window, minutes (default 15)")
    ap.add_argument("--bantime", default="3h,6h,24h", help="comma-separated, for ipset sizing")
    ap.add_argument("--event", choices=["issued", "followed"], default="issued")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    thresholds = [int(x) for x in args.maxretry.split(",")]
    findtime_s = args.findtime * 60
    bantimes = [(b, parse_duration(b)) for b in args.bantime.split(",")]

    c = load(args.logs)
    events = c.issued if args.event == "issued" else c.followed

    report_volumes(c, args.event)
    report_exemption(c)
    report_collisions(c)
    report_distribution(events, args.event)
    report_sweep(c, events, thresholds, args.findtime, findtime_s, bantimes, args.event)
    report_top(c, events, args.event, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
