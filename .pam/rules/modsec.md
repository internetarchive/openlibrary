# ModSec: WAF false-positive review process

Ported from `ol-ai/skills/modsec.md` (authoritative). ModSec turns a day's anonymized ModSecurity
error log into scoped, evidence-backed `olsystem` PRs. It is a repeatable process invoked when a new
day's anonymized log lands, not a standing agent. `olsystem` is private and security-sensitive, so this
process is admin/staff-only (see [[kb-reconciliation]] for the public/private split).

## When and how it runs

Trigger: a new dated log file appears on the OLModSecurityBot archive.org item (one file per day, from
openlibrary#13225's pipeline). There is no push notification yet. Invocation is either the coordinator
spinning up a one-off pass, or the ADA whose assigned task explicitly is the log review (check `cq`; do
not self-invoke for a code-feature issue). If several days have accumulated, work them oldest-first in
one session so cross-referencing against already-open PRs happens once.

Access: OLModSecurityBot credentials and a grant to review `olsystem`. Get these from the coordinator;
do not guess or reconstruct them from other bot credential files.

## Process

1. **Pull the day's log** from the OLModSecurityBot item (plaintext nginx `error.log` with inline
   ModSecurity denial lines). Confirm the format before assuming.
2. **Aggregate, never read raw.** A day's log can be ~12,000 denial lines. Use `grep`/aggregation (top
   rule IDs, top URIs, per-rule URIs/variables, repeat-IP check), never load the whole file into
   context. Cross-reference every high-count rule ID against the existing numbered exceptions in
   `olsystem/etc/modsecurity/openlibrary-rules.conf`; an already-exempted pattern that still fires is a
   regression, say so explicitly.
3. **Classify** each finding (this is the judgment part, not counting):
   - **Likely false positive:** high count, ordinary app traffic, especially spread across many
     distinct IPs hitting the same rule/endpoint (real users being blocked).
   - **Likely genuine attack, leave alone:** nonexistent routes (`.sql`/`.bak`, `/wp-admin`,
     `/cgi-bin`, exploit paths), known-scanner UAs, or one/few IPs hammering many fake paths. Candidate
     for the fail2ban jail, not an exemption.
   - **Ambiguous:** repeat hits from one IP on one rule/endpoint. Look at the actual request before
     deciding; when still unsure, say so in the report rather than picking a side.
   Never fold a false-positive-prone rule into the fail2ban known-attacks list, and never exempt a rule
   genuinely catching attacks. Getting this backwards either way is the failure mode of this process.
4. **One PR per fix, never bundled** (mek's rule, non-negotiable). Reviewers may accept some and reject
   others; a bundle makes a good fix wait on a contested one. Scope each fix as narrowly as the
   evidence supports (targeted `ctl:ruleRemoveById`/`ruleRemoveTargetById`, not a blanket
   `ruleEngine=Off`); scope by request field when the FP is field-tied, not URL. Check the current
   highest rule `id:` on fresh `origin/master` and note the numbering caveat in the PR body. Validate
   the fix against the real log data before opening; if the real tools are not available, validate the
   regex logic in isolation and say so.
5. **Open the PR discreetly** against `olsystem` through normal private review. Do NOT post a public
   `gh-bot` comment on any `openlibrary` issue; that old incident-response convention stopped applying
   once this became a routine pipeline. Branch off fresh `origin/master`; commit as the maintainer's
   own `olsystem` account (not `gh-bot`, which is for public openlibrary comments only).
6. **Report to the coordinator, not GitHub.** Comment on your `cq` task issue and message the
   coordinator with a one-line summary plus PR numbers. A day with nothing to propose is a valid,
   useful outcome: say so. The coordinator decides what becomes public-facing.

## Safety rules (non-negotiable)

This is production security infrastructure; a prior ModSecurity regression once blocked all editing
site-wide for hours before being caught.

- **PR-open is the entire ceiling of autonomous action.** Never merge an `olsystem` PR. Never run the
  provisioning/apply scripts. Never touch a live firewall, ipset, or ferm rule. A human reviews and
  merges every time, no exceptions, however strong the evidence looks.
- Never broadly disable the rule engine without specific evidence, and even then prefer the narrowest
  scope.
- Never add a rule ID to the fail2ban known-attacks filter without confirming from the log that it does
  not also fire on legitimate traffic. Getting this wrong bans real patrons.
- If a day's log shows something urgent (an active incident breaking legitimate traffic site-wide),
  escalate to the coordinator immediately rather than finishing the batch.
- If a classification is uncertain, say so in the report. Do not resolve uncertainty by guessing toward
  whichever action is less work.

## Scheduling

The live `modsec-daily-bundle` skill is the automation wrapper of this process; the launchd job
(`ada/fleet/modsec-daily/`) is the scheduled invocation mechanism.
