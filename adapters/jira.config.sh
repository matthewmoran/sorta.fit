#!/usr/bin/env bash
# Jira adapter configuration — status and transition IDs for SF project
# Discovered from inkrp.atlassian.net

# Status ID -> display name
STATUS_10103="To Do"
STATUS_10107="Refined"
STATUS_10108="Agent"
STATUS_10104="In Progress"
STATUS_10109="QA"
STATUS_10105="Done"
STATUS_10106="Backlog"

# How to transition a card TO each status (transition IDs from Jira)
TRANSITION_TO_10103=11
TRANSITION_TO_10107=3
TRANSITION_TO_10108=4
TRANSITION_TO_10104=21
TRANSITION_TO_10109=5
TRANSITION_TO_10105=31
TRANSITION_TO_10106=2
