# CIMB SGD->MYR Rate Hunter Agent (MVP)

Local-first Python background agent that reads the public CIMB SGD->MYR rate page and sends threshold alerts via Pushover.
The process is designed to run 24/7, while rate monitoring only runs during the configured active window (default `09:00-19:00` SGT).

## Safety Boundary

This project only reads the public page:

`https://www.cimbclicks.com.sg/sgd-to-myr`

It does **not**:
- log in to CIMB Clicks
- automate the CIMB mobile app
- initiate transfers or perform banking actions

## What It Does

1. Opens the public CIMB SGD->MYR page with Playwright
2. Extracts `getObject(encodeNamespace("rateList"))?.value`
3. Reads `rateList[0]` as current live rate
4. Applies alert threshold formula:

`alert_threshold = target_rate - buffer`

5. Monitors only inside configured active window
6. Uses adaptive polling intervals (normal/near/critical)
7. Sends Pushover alert on threshold hit (with cooldown)
8. Persists local state in `state.json` to avoid alert spam

## Setup (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
python -m src.main --once
python -m src.main
```

## Dry-Run Mode

- `alerts.dry_run: true` in config prints alerts to console instead of sending.
- You can force dry-run from CLI:

```powershell
python -m src.main --dry-run
```

In dry-run mode, real Pushover secrets are not required.

## Adaptive Interval Behavior

Outside active window:
- do not fetch CIMB rate
- calculate exact seconds until next `active_start`
- sleep until then in chunks of up to 30 minutes (for graceful logs/shutdown)
- default window is `09:00-19:00` Asia/Singapore

Inside active window:
- if `current_rate >= alert_threshold`:
  - send alert only if cooldown has passed
  - sleep `normal_seconds` or cooldown-aware interval
- else if `current_rate >= target_rate - critical_gap`:
  - sleep `critical_seconds`
- else if `current_rate >= target_rate - near_target_gap`:
  - sleep `near_target_seconds`
- else:
  - sleep `normal_seconds`

## CLI Flags

- `--once` fetch one cycle and exit
- `--headful` run Playwright in visible browser mode
- `--dry-run` force dry-run alerts
