# cimb-rate-sgd-myr

A Python Discord bot agent that monitors the live CIMB SGD→MYR exchange rate and sends Discord DM alerts when the rate reaches a user-defined target. Built for Malaysians in Singapore transferring SGD→MYR.

**For your own deployment:** Fork this repo instead of cloning to have your own independent copy.

## Features

- **Live rate scraping** — polls the CIMB rate page every 3 seconds (configurable)
- **Automatic page reload** — refreshes page every 5 minutes to get fresh data
- **Discord DM alerts** — sends notifications when rate crosses your target
- **Peak-based triggering** — alert fires when current rate > peak_rate AND rate ≥ target; peak resets when rate drops below target
- **Active time windows** — set which hours (HH:MM format) alerts should trigger
- **Active days control** — select which days of the week (mon-sun) to monitor
- **Per-user JSON configs** — each user has their own config file in `config/` (no database)
- **7 slash commands** — `/register`, `/status`, `/settarget`, `/setwindow`, `/setdays`, `/toggle`, `/menu`
- **Interactive menu** — `/menu` opens button-based UI for changing settings on mobile
- **Self-service registration** — users run `/register Your Name` to create their account
- **Hot config reload** — detects config file changes within 1 second without restarting
- **Minimal Discord intents** — only uses the necessary permissions
- **Atomic file writes** — config updates are all-or-nothing; no data corruption on crash
- **GitHub Actions CI/CD** — push to main branch auto-deploys to VM in ~16 seconds
- **Systemd service** — runs 24/7 with automatic restart on crash or reboot

## Requirements

- **Python 3.11+** — confirmed in agent.py
- **Git** — to clone the repository
- **A Discord bot token** — create via Discord Developer Portal
- **Playwright & Chromium** — for browser automation to scrape the rate page
- **aiofiles** — for async file operations (see requirements.txt)

## File Structure

```
cimb-rate-sgd-myr/
├── agent.py                 Main scraper loop, page reload, peak tracking, alert logic
├── bot.py                   Discord bot, slash commands, interactive UI views
├── notifier.py              Discord DM embed builder and sender
├── config_loader.py         Atomic JSON read/write, file watcher for hot reload
├── config/                  Per-user JSON config files (gitignored)
├── .env.example             Template for environment variables
├── .github/
│   └── workflows/
│       └── deploy.yml       GitHub Actions CI/CD pipeline
├── docs/
│   └── deployment.md        Deployment guide and troubleshooting
├── requirements.txt         Python dependencies
├── cimb-agent.service       Systemd service unit file
└── README.md                This file
```

## Discord Bot Setup

Create your Discord bot token and add it to your server:

1. Visit [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and name it (e.g., "CIMB Rate Bot")
3. Go to the **Bot** tab → click **Add Bot**
4. Under **TOKEN**, click **Reset Token** and copy the entire token
5. Save this token as your `DISCORD_BOT_TOKEN` in `.env` (see Section 8)
6. Under **Privileged Gateway Intents**, turn OFF all intents (you don't need them)
7. Go to **OAuth2** → **URL Generator**
8. Under **Scopes**, check: `bot` and `applications.commands`
9. Under **Permissions**, check: `Send Messages`
10. Copy the generated authorization URL, paste into your browser, select your server, and authorize
11. Your bot is now in your server and ready to use

**To find your own Discord User ID:**
- Open Discord and go **Settings** → **Advanced** → enable **Developer Mode**
- Right-click your username anywhere and select **Copy User ID**
- Save this for your user config file (see Section 7)

## Quick Start — Local Setup

### 1. Clone and Setup Environment

```bash
git clone https://github.com/yourusername/cimb-rate-sgd-myr.git
cd cimb-rate-sgd-myr
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your DISCORD_BOT_TOKEN
```

### 4. Create Your User Config

Create a JSON file in `config/user_{YOUR_DISCORD_ID}.json`:

```json
{
  "name": "Your Name",
  "discord_user_id": "YOUR_DISCORD_ID_HERE",
  "target_rate": 3.1000,
  "active_start": "09:00",
  "active_end": "19:00",
  "active_days": ["mon", "tue", "wed", "thu", "fri"],
  "enabled": true,
  "last_alerted_at": null,
  "peak_rate": 0.0
}
```

**To find your Discord User ID:**
- Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
- Right-click your username and select "Copy User ID"

### 5. Run the Agent

```bash
python agent.py
```

The agent will start scraping the CIMB rate page every 3 seconds and reload the page every 5 minutes.

### 6. Register via Discord (Optional)

Alternatively, send a DM to your bot with `/register Your Name` to auto-create your config.

Then use `/status` to see the live rate and `/menu` to configure settings.

## User Config File

Each user has a JSON file in the `config/` directory named `user_{discord_user_id}.json`. Create one manually or via `/register` command.

**Example: `config/user_123456789012345678.json`**

```json
{
  "name": "Sean",
  "discord_user_id": "123456789012345678",
  "target_rate": 3.1000,
  "active_start": "09:00",
  "active_end": "19:00",
  "active_days": ["mon", "tue", "wed", "thu", "fri"],
  "enabled": true,
  "last_alerted_at": null,
  "peak_rate": 0.0
}
```

**Config Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | User's display name |
| `discord_user_id` | string | Discord numeric user ID (required for DMs) |
| `target_rate` | float | SGD→MYR rate threshold for alerts (e.g., 3.1000) |
| `active_start` | string | Alert start time in HH:MM format (24-hour, e.g., 09:00) |
| `active_end` | string | Alert end time in HH:MM format (24-hour, e.g., 19:00) |
| `active_days` | array | Days to monitor: `["mon", "tue", "wed", "thu", "fri", "sat", "sun"]` |
| `enabled` | boolean | `true` to enable alerts, `false` to disable |
| `last_alerted_at` | string \| null | ISO 8601 timestamp of most recent alert |
| `peak_rate` | float | Tracks highest rate since target was crossed; resets when rate < target |

**Peak Rate Logic:**
- When `rate >= target_rate`, the bot tracks the peak
- Alert only fires if `rate > peak_rate` AND the current time is within active window + active days
- When `rate < target_rate`, peak_rate resets to 0

## Environment Variables

Create a `.env` file in the project root. See `.env.example` for a template.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | — | Bot token from Discord Developer Portal |
| `DISCORD_GUILD_ID` | No | — | Discord server ID for instant command sync |
| `SCRAPE_INTERVAL_MS` | No | 3000 | Milliseconds between rate reads |
| `IDLE_SLEEP_MS` | No | 60000 | Milliseconds to sleep when all users are outside active window |
| `MAX_NULL_STREAK` | No | 5 | Consecutive null reads before forcing page reload |
| `PAGE_RELOAD_INTERVAL_MS` | No | 300000 | Milliseconds between full page reloads (5 minutes) |
| `TIMEZONE` | No | Asia/Singapore | Timezone for active window checks |
| `CIMB_RATE_URL` | No | https://www.cimbclicks.com.sg/sgd-to-myr | CIMB rate page URL |
| `PLAYWRIGHT_USER_DATA_DIR` | No | .playwright | Playwright cache directory |
| `CONFIG_DIR` | No | config | Directory containing user JSON config files |

**Example `.env` file:**

```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_server_id
SCRAPE_INTERVAL_MS=3000
IDLE_SLEEP_MS=60000
MAX_NULL_STREAK=5
PAGE_RELOAD_INTERVAL_MS=300000
TIMEZONE=Asia/Singapore
CIMB_RATE_URL=https://www.cimbclicks.com.sg/sgd-to-myr
CONFIG_DIR=config
```

## Slash Commands

All commands are Discord slash commands (type `/` in any DM to the bot):

| Command | Arguments | Description |
|---------|-----------|-------------|
| `/register` | `name: str` | Register as a new user; creates your config file with default settings |
| `/status` | — | Display live rate, your target, active window, and all current settings |
| `/settarget` | `rate: float` | Set your target SGD→MYR rate (e.g., 3.1050) |
| `/setwindow` | `start: str` `end: str` | Set active alert window (HH:MM format, e.g., 09:00 19:00) |
| `/setdays` | `days: str` | Set active days (space or comma-separated, e.g., "mon tue wed thu fri") |
| `/toggle` | `mode: on \| off` | Enable or disable alerts |
| `/menu` | — | Open interactive settings panel with buttons for all config options |

**Command Restrictions:**
- All commands work in direct messages (DMs) to the bot
- `/menu` command opens ephemeral (visible only to you) button interface
- All commands require user to be registered first (use `/register` if not registered)

## /menu Interactive Interface

The `/menu` command opens a phone-friendly settings panel (ephemeral — visible only to you):

- **Set Target Rate** — Opens modal to enter your target SGD→MYR rate
- **Set Window** — Opens modal to enter start and end times (HH:MM format)
- **Toggle On/Off** — Button choices to enable or disable alerts
- **Set Days** — Interactive button panel with all 7 days; tap to toggle (✅ or ❌), then Save

All interactions are ephemeral and only visible to you.

## Adding a New User

### Method 1: Self-Registration (Easiest)

1. User sends DM to the bot: `/register Your Full Name`
2. Bot creates config file automatically with defaults
3. User runs `/menu` to customize settings
4. Done — user is registered and alerts are enabled

### Method 2: Manual Config Creation

1. Create a new JSON file in `config/user_{DISCORD_ID}.json`:

```json
{
  "name": "New User",
  "discord_user_id": "987654321098765432",
  "target_rate": 3.1200,
  "active_start": "09:00",
  "active_end": "17:00",
  "active_days": ["mon", "tue", "wed", "thu", "fri"],
  "enabled": true,
  "last_alerted_at": null,
  "peak_rate": 0.0
}
```

2. The config watcher detects the new file within 1 second
3. No restart needed — agent activates immediately

## Deployment to Server

### Systemd Service Setup

The `cimb-agent.service` file configures the agent to run as a systemd service:

```ini
[Service]
Type=simple
User=cimbagent
WorkingDirectory=/opt/cimb-rate-sgd-myr
EnvironmentFile=/opt/cimb-rate-sgd-myr/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/cimb-rate-sgd-myr/.venv/bin/python /opt/cimb-rate-sgd-myr/agent.py
Restart=always
RestartSec=3
```

**Key points:**
- Runs as non-privileged user `cimbagent`
- Automatically restarts on crash (after 3 seconds)
- Reads environment from `.env` file
- Keeps Python output unbuffered for live logs
- Uses the virtual environment Python executable

### Service Management

```bash
# Check status
sudo systemctl status cimb-agent

# Start/stop/restart
sudo systemctl start cimb-agent
sudo systemctl stop cimb-agent
sudo systemctl restart cimb-agent

# Enable auto-start on reboot
sudo systemctl enable cimb-agent

# View live logs
sudo journalctl -u cimb-agent -f

# View recent logs
sudo journalctl -u cimb-agent -n 50
```

**For complete deployment guide, see [docs/deployment.md](docs/deployment.md).**

## GitHub Actions CI/CD Pipeline

Automatic deployment to your VM whenever you push to the `main` branch.

### Deployment Flow (defined in `.github/workflows/deploy.yml`)

1. **Trigger:** Push to `main` branch
2. **Checkout:** Latest code is pulled
3. **SSH to VM** with configured credentials
4. **Reset repo** to origin/main (hard reset for clean deployment)
5. **Install dependencies:** `pip install -r requirements.txt`
6. **Copy systemd service:** `sudo cp cimb-agent.service /etc/systemd/system/`
7. **Reload systemd:** `sudo systemctl daemon-reload`
8. **Restart service:** `sudo systemctl restart cimb-agent`
9. **Verify status:** Check service is running
10. **Complete:** Deployment finished (~16 seconds total)

### Setup GitHub Secrets

Go to your GitHub repository **Settings** → **Secrets and variables** → **Actions** and add:

| Secret | Value |
|--------|-------|
| `VM_HOST` | External IP of your deployment VM (e.g., `35.184.135.76`) |
| `VM_USER` | SSH username on the VM (e.g., `ubuntu`) |
| `VM_SSH_KEY` | Full private SSH key for authentication (include BEGIN/END lines) |

### Manual Deployment (if needed)

SSH into your VM and run:

```bash
cd /opt/cimb-rate-sgd-myr
git fetch origin main
git reset --hard origin/main
source .venv/bin/activate
pip install -r requirements.txt --quiet
sudo cp cimb-agent.service /etc/systemd/system/cimb-agent.service
sudo systemctl daemon-reload
sudo systemctl restart cimb-agent
sudo systemctl status cimb-agent --no-pager -l
```

## Security & Secrets

**Never commit these to Git** (protected by `.gitignore`):
- `.env` — Discord bot token
- `config/` — user config files with Discord IDs
- SSH keys — never commit private keys

**Always use GitHub Secrets for CI/CD credentials:**
- `VM_HOST` — VM IP address
- `VM_USER` — SSH username
- `VM_SSH_KEY` — Private SSH key

**Config files are atomic:**
- All writes go through temp file then atomic rename
- No data loss or corruption on crash
- File watcher detects changes within 1 second

## Useful VM Commands

Commands for managing the agent on your GCP VM:

| Command | Description |
|---------|-------------|
| `sudo systemctl status cimb-agent` | Check if agent is running |
| `sudo systemctl start cimb-agent` | Start the agent |
| `sudo systemctl stop cimb-agent` | Stop the agent |
| `sudo systemctl restart cimb-agent` | Restart the agent |
| `sudo systemctl enable cimb-agent` | Auto-start on reboot |
| `sudo journalctl -u cimb-agent -f` | View live logs (follow mode) |
| `sudo journalctl -u cimb-agent --lines=50` | View last 50 log lines |
| `free -h` | Check memory and swap usage |
| `df -h` | Check disk usage |
| `sudo systemctl reload-or-restart cimb-agent` | Reload config (no downtime) |

## Code Architecture

### agent.py — Main Scraper Loop

**Key functions:**

- `load_settings()` — Reads environment variables into typed Settings
- `fetch_live_rate(page)` — Evaluates JavaScript on CIMB page to extract current rate
- `parse_rate_value(raw)` — Converts raw value to float
- `is_within_active_window()` — Checks if current time is in active window
- `is_active_day()` — Checks if today is in active_days list
- `any_user_active()` — Checks if at least one user should be monitored now
- `process_user_alert()` — Applies peak tracking logic and sends alerts
- `poll_forever()` — Main infinite loop that continuously scrapes and checks alerts

**Peak Tracking Logic:**

```python
if rate < target:
    if peak_rate > 0:
        reset peak_rate to 0.0
elif rate > peak_rate and is_active_now():
    send alert and update peak_rate
```

### bot.py — Discord Commands

**Key classes:**

- `RateHunterBot(commands.Bot)` — Main Discord bot with minimal intents
- `RateCommands(commands.Cog)` — Slash command handler
- `MenuView(discord.ui.View)` — Interactive settings menu buttons
- `SetTargetModal`, `SetWindowModal` — Input dialogs
- `ToggleView`, `DaySelectView` — Button-based UI controls

**Slash commands implemented:**
- `/register`, `/status`, `/settarget`, `/setwindow`, `/setdays`, `/toggle`, `/menu`

### config_loader.py — Config Management

**Key functions:**

- `start()` — Load configs and start file watcher
- `get_all_users()` — Return all user configs (thread-safe copies)
- `get_user_by_discord_id()` — Lookup one user's config
- `update_user_fields()` — Atomically update config fields
- `create_user()` — Create new user config file
- `_watch_loop()` — Poll for file changes every 1 second
- `_write_json_atomic()` — Write through temp file for atomicity

### notifier.py — DM Alerts

**Key function:**

- `send_rate_alert(payload)` — Resolve Discord user and send embed DM

## What is NOT Implemented

- **Rate history** — only live monitoring, no data storage
- **Rate prediction** — no ML or forecasting
- **Multiple rate sources** — only CIMB's public page
- **Web dashboard** — Discord-only interface
- **Actual fund transfers** — monitoring only, no banking integration
- **Direct API access** — only reads from public webpage
- **Webhook notifications** — Discord DMs only
- **Alternative messaging** — Telegram/Email/SMS not supported

## Documentation

- [docs/deployment.md](docs/deployment.md) — Detailed deployment guide and troubleshooting
