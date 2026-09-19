# Progress Reporting

Use this reference when the user wants external notifications or when deciding what progress is worth reporting.

## Goal

Keep the user informed without turning worker logs into noise.

## Report

Send an update for meaningful events:

- the execution plan is established;
- a major milestone completes;
- a major blocker, failure, or delay appears;
- a user decision is required;
- independent review finds significant rework;
- the work is verified complete.

Do not report every worker message, command, retry, or routine status check.

## Format

Keep updates short. Prefer:

```text
Status: Backend implementation complete; frontend integration is in progress.
Important: API response shape changed as planned and tests pass.
Action needed: None.
```

For a problem:

```text
Status: Backend task is temporarily blocked by provider quota.
Important: Worker context is preserved; reset is expected at 17:33.
Action needed: None. Independent frontend work is continuing.
```

## External channels

If a Discord webhook or similar endpoint is configured, the Lead should send the message directly using an available HTTP/script/tool capability. Do not create a reporting subagent solely to relay status.

Never include secrets, authentication data, private source code, or large raw logs. Treat webhook URLs as secrets.

Reporting integration is optional; absence of a webhook must not affect the Lead's core behavior.
