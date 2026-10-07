# Team roles

The standard roles PAM seeds for a Project: the shared vocabulary for who does what.
This file reads on its own; you do not need to run pam or cmux to use it as a team standard.

## lead: Lead

Owns a part of the Project — the whole thing, a division, or an epic — and coordinates and unblocks
the agents under it. **Seniority is the reporting tree (reports_to), not the role:** the coordinator
is simply the Lead at the root, a division lead is a Lead that reports to it, and so on. For a
Project's `.pam` Team, "Lead" is what we mean — we don't distinguish Project Lead from Division Lead
as separate roles.

Permissions: manage_project, manage_epics, onboard_agents, allocate_reviewers.

(`project_lead` and `division_lead` remain as deprecated aliases of `lead` so older records resolve;
new members should be onboarded as `lead`.)

## ada_agent: ADA agent

Atomic agent that owns one PR end to end (issue -> PR -> review -> merge -> cleanup).

The ADA process and manual ship with PAM at `pam/agents/ada/` (`AGENTS.md`, `docs/process.md`).

## agent: Agent

A general-purpose team member that is not the atomic development agent.

Edit this file to add Project-specific roles or tailor descriptions. PAM reads roles from the Store; this file is the human-readable standard.
