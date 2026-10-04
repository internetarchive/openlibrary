# Team roles

The standard roles PAM seeds for a Project: the shared vocabulary for who does what.
This file reads on its own; you do not need to run pam or cmux to use it as a team standard.

## project_lead: Project Lead

Owns the Project: settings, docs, configuration; allocates reviewers; settles inter-lead disputes.

Permissions: manage_project, manage_epics, onboard_agents, allocate_reviewers.

## division_lead: Division / Epic Lead

Domain expert and epic manager for a set of Epics; unblocks agents as a consultant.

Permissions: manage_epics, onboard_agents.

## ada_agent: ADA agent

Atomic agent that owns one PR end to end (issue -> PR -> review -> merge -> cleanup).

The ADA process and manual ship with PAM at `pam/agents/ada/` (`AGENTS.md`, `docs/process.md`).

## agent: Agent

A general-purpose team member that is not the atomic development agent.

Edit this file to add Project-specific roles or tailor descriptions. PAM reads roles from the Store; this file is the human-readable standard.
