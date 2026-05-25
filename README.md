# cimb-rate-sgd-myr

A personal Python background agent that monitors the live CIMB SGD→MYR public exchange rate via Playwright scraping and sends Discord DM alerts when the rate crosses a user-defined target. Designed for Malaysians in Singapore who transfer SGD→MYR via CIMB.

## Features

- **Live rate scraping every 3 seconds** — detects rate changes in near real-time
- **Page reload every 60 seconds** — forces fresh data from CIMB server
- **Discord DM alerts** — instant notification when rate crosses your target
- **Peak tracking** — alert fires when rate ≥ target AND rate > peak_rate; resets when rate drops below target
- **Active window** — set which hours per day (HH:MM) to monitor
- **Active days** — set which days of the week (mon-sun) to monitor
- **Per-user config files** — each user has their own JSON settings (no database)
- **Slash commands** — `/register`, `/status`, `/settarget`, `/setwindow`, `/setdays`, `/toggle`, `/menu`
- **Phone-friendly button UI** — `/menu` opens button panels and modals for easy mobile configuration
- **Self-service registration** — users register themselves via `/register`
- **Hot config reload** — config changes detected and applied within 1 second
- **24/7 hosting on GCP free tier** — runs on e2-micro Ubuntu VM with systemd auto-restart
- **GitHub Actions CI/CD** — push to main branch, auto-deploys to VM in ~16 seconds
- **No database required** — config stored as JSON files per user
- **No banking integration** — only reads public rate page, no login or credentials

## Requirements

- **Python 3.11** (not 3.12 — Playwright incompatible with 3.12)
- **Git** — to clone the repository
- **A Discord bot token** — create via Discord Developer Portal (see Section 5)
- **A private Discord server** — bot must be in the same server as users to send DMs
- **GCP account** (optional) — for 24/7 hosting; free tier includes e2-micro VM (1GB swap required)

## File Structure

```
cimb-rate-sgd-myr/
├── agent.py              Main scraper loop, page reload, alert logic
├── bot.py                Discord slash commands, modals, button views
├── notifier.py           Discord DM embed sender
├── config_loader.py      Atomic JSON read/write, file watcher for hot reload
├── config/               Per-user JSON config files (gitignored)
├── .env                  Bot token and settings (gitignored)
├── .env.example          Template for .env variables
├── .gitignore            Prevents secrets from being committed
├── requirements.txt      Python dependencies
├── setup.sh              Installation script
├── cimb-agent.service    Systemd service unit file
├── .github/
│   └── workflows/
│       └── deploy.yml    GitHub Actions CI/CD pipeline
├── docs/
│   └── deployment.md     Detailed deployment reference
└── README.md             This file
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

## Local Setup — Windows

Run the agent on your Windows machine:

1. Clone the repository:
   ```powershell
   git clone https://github.com/weewooweewooo/cimb-rate-sgd-myr.git
   cd cimb-rate-sgd-myr
   ```

2. Create a virtual environment with Python 3.11:
   ```powershell
   py -3.11 -m venv .venv
   .venv\Scripts\activate
   ```
   *(Use Python 3.11 only — Playwright doesn't support 3.12)*

3. Copy the environment template and fill in your bot token:
   ```powershell
   copy .env.example .env
   # Edit .env in notepad and add your DISCORD_BOT_TOKEN
   ```

4. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   playwright install chromium
   ```

5. Create your user config file manually (see Section 7 for template)

6. Run the agent:
   ```powershell
   python agent.py
   ```

7. In your Discord server, use `/register Your Name` to create your account, or manually edit your config file

## User Config File

Each user has a JSON file in the `config/` directory. You can create one manually or use `/register`.

**Example config file: `config/sean.json`**

```json
{
  "name": "Sean",
  "discord_user_id": "123456789012345678",
  "target_rate": 3.1050,
  "active_start": "09:00",
  "active_end": "19:00",
  "active_days": ["mon", "tue", "wed", "thu", "fri"],
  "enabled": true,
  "last_alerted_at": "2024-05-20T14:32:15.123456+00:00",
  "peak_rate": 0.0
}
```

**User Config Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name for the user |
| `discord_user_id` | string | Discord numeric ID (required for DM alerts) |
| `target_rate` | float | SGD→MYR rate that triggers alerts (e.g., 3.1050) |
| `active_start` | string | Start hour in HH:MM format (24-hour) |
| `active_end` | string | End hour in HH:MM format (24-hour) |
| `active_days` | array | Days to monitor: `["mon", "tue", "wed", "thu", "fri", "sat", "sun"]` |
| `enabled` | boolean | `true` to enable alerts, `false` to disable |
| `last_alerted_at` | string | ISO 8601 timestamp of last alert (auto-updated) |
| `peak_rate` | float | Tracks peak rate since target was crossed; resets when rate drops below target |

## Environment Variables

Create a `.env` file in the project root with these variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | — | Bot token from Discord Developer Portal |
| `DISCORD_GUILD_ID` | No | — | Your Discord server ID (optional; enables instant command sync) |
| `CIMB_RATE_URL` | No | `https://www.cimbclicks.com.sg/sgd-to-myr` | CIMB rate page URL |
| `SCRAPE_INTERVAL_MS` | No | `3000` | Milliseconds between rate reads (3 seconds) |
| `PAGE_RELOAD_INTERVAL_MS` | No | `60000` | Milliseconds between page reloads (60 seconds) |
| `IDLE_SLEEP_MS` | No | `60000` | Milliseconds to sleep when no user is active |
| `MAX_NULL_STREAK` | No | `5` | Consecutive null reads before force-reload |
| `TIMEZONE` | No | `Asia/Singapore` | Timezone for active window checks |
| `CONFIG_DIR` | No | `config` | Directory containing user JSON files |

**Example `.env` file:**

```
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_server_id_here
SCRAPE_INTERVAL_MS=3000
PAGE_RELOAD_INTERVAL_MS=60000
IDLE_SLEEP_MS=60000
TIMEZONE=Asia/Singapore
```

## Slash Commands

All commands are available as slash commands in Discord (type `/` in any DM or channel):

| Command | Arguments | Description |
|---------|-----------|-------------|
| `/register` | `name: str` | Register yourself as a new user; creates your config file |
| `/status` | — | Show live rate, target, active window, enabled status, and all settings |
| `/menu` | — | Open button panel with options to change settings via buttons and modals |
| `/settarget` | `rate: float` | Set your target SGD→MYR rate (e.g., 3.1050) |
| `/setwindow` | `start: str` `end: str` | Set active hours in HH:MM format (e.g., 09:00 19:00) |
| `/setdays` | `days: str` | Set active days (e.g., "mon tue wed thu fri") |
| `/toggle` | `mode: on \| off` | Enable or disable alerts |

**Note:** All commands work in DMs and require you to be registered (use `/register` first).

## /menu Button Interface

The `/menu` command opens a phone-friendly settings panel with buttons:

- **Set Target Rate** → Opens modal to input your target rate
- **Set Window** → Opens modal to input start and end hours (HH:MM format)
- **Toggle On/Off** → Button choices to enable or disable alerts
- **Set Days** → Interactive button panel with 7 day toggle buttons (✅ active, ❌ inactive); tap to toggle, then Save

All `/menu` interactions are ephemeral (only visible to you).

## Adding a New User

### Method 1: Self-service via Discord (Easiest)

1. Have the user join your Discord server
2. User runs `/register Your Full Name` in any DM to the bot
3. User uses `/menu` to configure their settings
4. Done — user is registered and alerts are enabled

### Method 2: Manual config file creation

1. SSH into your VM (or edit locally before deploying):
   ```bash
   gcloud compute ssh cimb-rate-vm --zone=us-central1-a --project=your-project-id
   cd cimb-rate-sgd-myr
   ```

2. Create a new JSON file in the `config/` directory:
   ```bash
   cat > config/newuser.json << 'EOF'
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
   EOF
   ```

3. The agent detects the new file within 1 second and activates it automatically (no restart needed)

## GCP VM Deployment

Deploy the agent to a GCP e2-micro VM (free tier) running 24/7:

1. Create a GCP project and enable Compute Engine API

2. Create an e2-micro VM:
   - Zone: `us-central1-a`
   - OS Image: Ubuntu 22.04 LTS
   - Boot disk: 10GB
   - Create and note the SSH key

3. SSH into your VM:
   ```bash
   gcloud compute ssh cimb-rate-vm --zone=us-central1-a --project=your-project-id
   ```

4. Create 1GB swapfile (required for Chromium to run without EPIPE crashes):
   ```bash
   sudo fallocate -l 1G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

5. Update system and install Python 3.11:
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3.11 python3.11-venv git
   ```

6. Clone the repository:
   ```bash
   git clone https://github.com/weewooweewooo/cimb-rate-sgd-myr.git
   cd cimb-rate-sgd-myr
   ```

7. Create virtual environment and install dependencies:
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

8. Create `.env` file with your bot token:
   ```bash
   cat > .env << 'EOF'
   DISCORD_BOT_TOKEN=your_token_here
   DISCORD_GUILD_ID=your_server_id
   EOF
   ```

9. Create initial user config(s) in `config/` directory (see Section 7)

10. Create systemd service file:
    ```bash
    sudo cp cimb-agent.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable cimb-agent
    sudo systemctl start cimb-agent
    ```

11. Verify it's running:
    ```bash
    sudo systemctl status cimb-agent
    sudo journalctl -u cimb-agent -f
    ```

The agent will now run 24/7 and restart automatically on VM reboot or crash.

## CI/CD Pipeline Setup

Deploy automatically from GitHub to your VM:

1. Generate an SSH key pair on your local machine:
   ```bash
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/vm_deploy_key -N ""
   ```

2. Add the public key to your VM:
   ```bash
   gcloud compute ssh cimb-rate-vm --zone=us-central1-a --command="echo '$(cat ~/.ssh/vm_deploy_key.pub)' >> ~/.ssh/authorized_keys"
   ```

3. Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions**

4. Create these secrets:
   - `VM_HOST`: Your VM's external IP address
   - `VM_USER`: `ubuntu`
   - `VM_SSH_KEY`: Paste the entire contents of `~/.ssh/vm_deploy_key` (private key)

5. The `.github/workflows/deploy.yml` file is already configured in the repository

6. On every push to `main`, GitHub Actions will:
   - SSH into your VM
   - Pull the latest code
   - Install dependencies
   - Restart the systemd service
   - Deploy complete in ~16 seconds

View deployment logs in your GitHub repository under **Actions** tab.

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

## Troubleshooting

### EPIPE crash on VM startup

**Symptom:** Agent crashes immediately with "BrokenPipeError: [Errno 32] Broken pipe"

**Cause:** e2-micro has only 1GB RAM. Chromium needs swap space.

**Fix:**
```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

Then restart: `sudo systemctl restart cimb-agent`

### Agent shows rate=None for 60+ seconds on VM startup

**Symptom:** First read returns `rate=None` and takes 60 seconds to resolve

**Cause:** `wait_for_function()` on e2-micro can take 60 seconds on first load due to low CPU/memory

**Workaround:** This is normal on first startup. Subsequent scrapes are much faster (3-5 seconds). Be patient.

### Slash commands not appearing in Discord

**Symptom:** `/register`, `/menu`, etc. don't show up in Discord

**Cause:** Bot token is invalid or bot is not in your server

**Fix:**
1. Verify `DISCORD_BOT_TOKEN` is correct in `.env`
2. Verify bot is in your Discord server (check Members list)
3. Restart agent: `sudo systemctl restart cimb-agent`
4. Wait 30 seconds and try again

**Optional:** Add `DISCORD_GUILD_ID` to `.env` with your server's numeric ID for instant command sync (otherwise takes up to 1 hour).

### Bot cannot send DMs to user

**Symptom:** Agent finds a matching rate but user doesn't receive alert DM

**Cause:** Bot is not in a server shared with the user, or user has DMs disabled

**Fix:**
1. Verify bot is in the same Discord server as the user
2. Have the user check **Settings** → **Privacy & Safety** → allow DMs from server members
3. Verify user's `discord_user_id` in their config file matches their actual Discord ID

### Playwright/Chromium errors on startup

**Symptom:** `ModuleNotFoundError: No module named 'playwright'` or Chromium won't launch

**Cause:** Playwright not installed or wrong Python version (3.12 instead of 3.11)

**Fix:**
1. Verify Python version: `python3 --version` (must be 3.11.x, not 3.12)
2. Reinstall Playwright:
   ```bash
   pip install --upgrade playwright
   playwright install chromium
   ```

### Rate value is stuck or stale

**Symptom:** Rate value doesn't update for more than 5 minutes

**Cause:** Page reload may be delayed or JavaScript on CIMB's site is not updating

**Workaround:**
- First page reload happens `PAGE_RELOAD_INTERVAL_MS` (default 60s) after startup, then every 60s after that
- Check logs: `sudo journalctl -u cimb-agent -f` — look for `[agent] page reloaded successfully`
- If stuck, restart: `sudo systemctl restart cimb-agent`

### Agent keeps crashing and restarting

**Symptom:** Agent restarts every few minutes (`systemctl status` shows restart loop)

**Cause:** Usually a config file syntax error or missing required field

**Fix:**
1. Check logs: `sudo journalctl -u cimb-agent -f`
2. Look for JSON parse errors in `config/` files
3. Validate JSON: `python3 -m json.tool config/username.json`
4. Delete/fix the corrupted file and restart: `sudo systemctl restart cimb-agent`

## What is Not Implemented

The following features are deliberately not implemented:

- **Rate history storage** — rates are not stored in a database or log file; only live monitoring
- **Rate prediction** — no ML or statistical prediction of future rates
- **Multi-source rate comparison** — only CIMB's public rate is monitored
- **Web dashboard** — no web UI; only Discord commands and buttons
- **Banking automation** — no actual fund transfers or bank integration
- **Direct API access** — CIMB rate data comes only from page reload of the public website, not a direct API
- **Rate CSV export** — no historical data export capability
- **Webhook integration** — alerts go only to Discord DMs, no webhooks
- **Telegram/Email alerts** — only Discord DMs supported

## Security Notes

- **Bot token is secret** — never commit `.env` to Git; it's in `.gitignore`
- **User IDs are in config files** — user Discord IDs are stored in JSON in `config/`; keep `config/` directory private
- **No banking credentials stored** — the agent only reads the public CIMB rate page; no logins, passwords, or API keys for banking
- **SSH key for deployment** — keep your VM SSH key safe; add it only to GitHub Secrets, never commit it
- **Discord server should be private** — use a private Discord server for bot testing/deployment
- **User configs are atomic** — config file writes are atomic (all-or-nothing); no data loss on crash
- **File watcher detects changes** — new config files are detected within 1 second without restarting the agent
