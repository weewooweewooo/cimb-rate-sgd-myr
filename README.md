# cimb-rate-sgd-myr

A Discord bot that monitors the live public CIMB SGD→MYR exchange rate and sends DM alerts when a target rate is reached. The bot scrapes the CIMB Clicks rate page every 3 seconds using Playwright and notifies users in real-time. It's designed for personal use or small groups who want automatic rate notifications without any banking integration or login. No credentials are stored, no banking APIs are used—it's just a simple public rate monitor with Discord alerts.

## Features

- **Live rate scraping every 3 seconds** — stays on top of rate changes
- **Discord DM alerts** — instant notification when your target rate is hit
- **Per-user config** — each person has their own settings and target rate
- **Active window** — set which hours of the day to monitor
- **Active days** — choose which days of the week to monitor (weekdays only, or custom)
- **Max alerts per rate crossing** — limit how many times you get alerted for the same rate
- **Auto-reset** — alert counter resets when rate drops below your target
- **Slash commands** — control everything from Discord without leaving the chat
- **/menu with buttons and modals** — easy mobile-friendly UI for changing settings
- **Self-registration** — users register themselves via /register slash command
- **CI/CD auto-deploy** — push to GitHub and it auto-deploys to your VM
- **24/7 hosting on GCP e2-micro** — free tier, always running

## Requirements

Before you start, you need:

- **Python 3.11** (not 3.12 — Playwright is not compatible with 3.12)
- **Git** — to clone the repository
- **A Discord account** — to use the bot
- **A Discord bot token** — create one in the Discord Developer Portal (see Section 5)
- **A GCP account** (optional) — if you want 24/7 hosting. Free tier includes e2-micro VM
- **A private Discord server** — create one for testing, or use an existing private server. The bot needs to be in the same server as the users it alerts

## Project File Structure

```
cimb-rate-sgd-myr/
├── agent.py              # Main scraper loop and alert logic
├── bot.py                # Discord slash commands and modals
├── notifier.py           # Discord DM embed sender
├── config_loader.py      # Atomic JSON config read/write/watch
├── config/               # Per-user config files (gitignored)
│   └── sean.json         # Example user config
├── .env                  # Secrets and settings (gitignored)
├── .env.example          # Template for .env
├── .gitignore            # Protects secrets from being committed
├── requirements.txt      # Python dependencies
├── setup.sh              # Install script
├── cimb-agent.service    # Systemd service file for Linux
├── .github/
│   └── workflows/
│       └── deploy.yml    # GitHub Actions CI/CD pipeline
├── docs/
│   └── deployment.md     # Deployment reference guide
└── README.md             # This file
```

## Discord Bot Setup

Create your Discord bot by following these steps:

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it **CIMB Rate Bot** (or whatever you prefer)
3. Go to the **Bot** tab → click **Add Bot**
4. Under **TOKEN** → click **Reset Token** → copy the entire token (this is your `DISCORD_BOT_TOKEN`)
5. Under **Privileged Gateway Intents** → turn OFF all three intents (message content intent, etc.)
6. Go to **OAuth2** → **URL Generator**
7. Under **Scopes**, check: `bot` and `applications.commands`
8. Under **Bot Permissions**, check: `Send Messages`
9. Copy the generated URL → open it in your browser → select your private Discord server and authorize
10. Your bot is now in your server ✓

**How to get your Discord user ID:**
1. In Discord, go to **Settings** → **Advanced** → enable **Developer Mode**
2. Right-click your profile anywhere (username, avatar in DMs, etc.)
3. Click **Copy User ID**
4. You'll use this when creating your user config file

## Local Setup (Windows)

Follow these steps to run the agent on your Windows machine:

**1. Clone the repository:**

```powershell
git clone https://github.com/YOUR_USERNAME/cimb-rate-sgd-myr.git
cd cimb-rate-sgd-myr
```

**2. Create a virtual environment with Python 3.11:**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
```

*(Important: Use Python 3.11, not 3.12. Playwright doesn't support 3.12 yet.)*

**3. Install dependencies:**

```powershell
pip install -r requirements.txt
playwright install chromium
```

**4. Create .env file:**

```powershell
copy .env.example .env
```

Then open `.env` in a text editor and fill in your `DISCORD_BOT_TOKEN`.

**5. Create your user config:**

Create a new file `config/sean.json` (replace `sean` with your name):

```json
{
  "name": "Sean",
  "discord_user_id": "YOUR_DISCORD_USER_ID",
  "target_rate": 3.1000,
  "active_start": "09:00",
  "active_end": "19:00",
  "active_days": ["mon", "tue", "wed", "thu", "fri"],
  "enabled": true,
  "cooldown_minutes": 30,
  "last_alerted_at": null,
  "max_alerts": 3,
  "alert_count": 0,
  "reset_margin": 0.0010
}
```

**6. Run the agent:**

```powershell
python agent.py
```

**Expected output:**

```
[bot] synced 10 global slash command(s)
[agent] bot ready — starting scrape loop
[bot] logged in as CIMB Rate Bot
[agent] rateList ready
[2026-05-24 14:32:01] rate=3.0820 next_sleep_ms=3000 users=1
[2026-05-24 14:32:04] rate=3.0820 next_sleep_ms=3000 users=1
```

The bot will start polling the CIMB rate every 3 seconds. If you see `rate=3.0820` (or similar), it's working!

## User Config File Reference

Each user has their own JSON config file in the `config/` directory. Here's the full example:

```json
{
  "name": "Sean",
  "discord_user_id": "YOUR_DISCORD_USER_ID",
  "target_rate": 3.1000,
  "active_start": "09:00",
  "active_end": "19:00",
  "active_days": ["mon", "tue", "wed", "thu", "fri"],
  "enabled": true,
  "cooldown_minutes": 30,
  "last_alerted_at": null,
  "max_alerts": 3,
  "alert_count": 0,
  "reset_margin": 0.0010
}
```

**Field Reference:**

| Field | Type | Description | Default |
|---|---|---|---|
| `name` | string | Display name for this user | — |
| `discord_user_id` | string | Your Discord user ID (from Developer Mode) | — |
| `target_rate` | float | Alert when rate is >= this value | 3.1000 |
| `active_start` | string | Start monitoring at this time (HH:MM format, 24-hour) | 09:00 |
| `active_end` | string | Stop monitoring at this time (HH:MM format, 24-hour) | 19:00 |
| `active_days` | array of strings | Days to monitor: `["mon", "tue", "wed", "thu", "fri"]` for weekdays only, or `["mon", "tue", "wed", "thu", "fri", "sat", "sun"]` for every day | weekdays |
| `enabled` | boolean | Enable or disable alerts for this user | true |
| `cooldown_minutes` | int | Minimum minutes between consecutive alerts for the same rate | 30 |
| `last_alerted_at` | string or null | Timestamp of last alert (managed by bot, don't edit) | null |
| `max_alerts` | int | Maximum alerts per rate crossing (0 = unlimited) | 3 |
| `alert_count` | int | Current alert count for this rate crossing (managed by bot, don't edit) | 0 |
| `reset_margin` | float | How far the rate must drop below target before resetting the alert counter | 0.0010 |

## Environment Variables

Create a `.env` file by copying `.env.example` and filling in the values. Here's what each variable does:

| Variable | Required | Description | Default |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Yes | Your Discord bot's token from the Developer Portal | — |
| `DISCORD_GUILD_ID` | No | Your Discord server ID for instant slash command sync (speeds up command registration from 1 hour to instant) | — |
| `CIMB_RATE_URL` | No | URL of the CIMB rate page to scrape | https://www.cimbclicks.com.sg/sgd-to-myr |
| `SCRAPE_INTERVAL_MS` | No | How often to poll the rate in milliseconds | 3000 |
| `IDLE_SLEEP_MS` | No | How long to sleep when no users are in their active window | 60000 |
| `MAX_NULL_STREAK` | No | Number of failed rate reads before reloading the page | 5 |
| `TIMEZONE` | No | Timezone for checking active windows (e.g., Asia/Singapore) | Asia/Singapore |
| `PLAYWRIGHT_USER_DATA_DIR` | No | Directory for Playwright browser profile | .playwright |
| `CONFIG_DIR` | No | Directory where user config files are stored | config |

## Slash Commands

All commands are available in Discord DMs with the bot. Here's the full list:

| Command | Description |
|---|---|
| `/register name` | Register yourself as a new user (bot creates your config automatically) |
| `/status` | Show the live SGD→MYR rate and your full current config |
| `/menu` | Open the button panel with modals for easy settings changes (phone-friendly) |
| `/settarget rate` | Set your target SGD→MYR rate (e.g., 3.1000) |
| `/setwindow start end` | Set your active monitoring window in HH:MM format (e.g., 09:00 19:00) |
| `/setdays days` | Set which days to monitor (e.g., mon tue wed thu fri) |
| `/toggle on/off` | Enable or disable your alerts |
| `/setcooldown minutes` | Set cooldown between consecutive alerts |
| `/setmaxalerts count` | Set maximum alerts per rate crossing (0 = unlimited) |
| `/setresetmargin value` | Set how far the rate must drop to reset the alert counter |
| `/resetalert` | Manually reset the alert count for the current rate |

All commands require you to be in the same Discord server as the bot and work in DMs with the bot.

## Adding a New User

There are two ways to add users:

### Method 1: Self-Registration (Recommended)

1. New user joins your private Discord server
2. They DM the bot: `/register name:TheirName`
3. The bot creates their config file automatically with default settings
4. They can immediately use all slash commands to customize their settings
5. No restart needed — the config watcher picks up the new file within 1 second

### Method 2: Manual (Admin Creates the File)

1. SSH into your VM (if deployed on GCP) or edit locally
2. Create a new file `config/theirname.json` with their settings
3. Fill in their `discord_user_id` and other preferences
4. The config watcher picks it up within 1 second
5. No restart needed

## GCP VM Deployment (24/7 Hosting)

Host your bot 24/7 on a free GCP e2-micro VM (Ubuntu 22.04).

### Step 1: Create GCP Account

Go to [https://console.cloud.google.com](https://console.cloud.google.com) and sign up. The e2-micro VM in us-central1 is covered by the free tier (up to 730 hours per month).

### Step 2: Create the VM

```bash
gcloud compute instances create cimb-rate-vm \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --image=projects/ubuntu-os-cloud/global/images/ubuntu-minimal-2204-jammy-v20260517 \
  --create-disk=size=10,type=pd-standard
```

### Step 3: SSH into the VM

```bash
gcloud compute ssh cimb-rate-vm --zone=us-central1-a
```

### Step 4: Install System Dependencies

```bash
sudo apt update && sudo apt install -y git python3 python3-pip python3-venv nano
```

### Step 5: Clone the Repository

```bash
sudo git clone https://github.com/YOUR_USERNAME/cimb-rate-sgd-myr.git /opt/cimb-rate-sgd-myr
sudo chown -R $USER:$USER /opt/cimb-rate-sgd-myr
cd /opt/cimb-rate-sgd-myr
```

### Step 6: Create Virtual Environment and Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
bash setup.sh
```

### Step 7: Add Swap Space (Required for Chromium on e2-micro)

The e2-micro has only 1GB of RAM, which isn't enough for Chromium. Create a 1GB swap file:

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Step 8: Create .env File

```bash
nano .env
```

Paste your bot token and any other environment variables:

```
DISCORD_BOT_TOKEN=your_token_here
DISCORD_GUILD_ID=your_guild_id
```

### Step 9: Create Your User Config

```bash
mkdir -p config
nano config/sean.json
```

Paste your user config JSON:

```json
{
  "name": "Sean",
  "discord_user_id": "YOUR_DISCORD_USER_ID",
  "target_rate": 3.1000,
  "active_start": "09:00",
  "active_end": "19:00",
  "active_days": ["mon", "tue", "wed", "thu", "fri"],
  "enabled": true,
  "cooldown_minutes": 30,
  "last_alerted_at": null,
  "max_alerts": 3,
  "alert_count": 0,
  "reset_margin": 0.0010
}
```

### Step 10: Install systemd Service

```bash
sudo cp cimb-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cimb-agent
sudo systemctl start cimb-agent
```

### Step 11: Verify It's Running

```bash
sudo systemctl status cimb-agent
sudo journalctl -u cimb-agent -f
```

You should see the same log output as the local run. Press `Ctrl+C` to exit the log viewer.

## CI/CD Pipeline Setup

Auto-deploy code changes to your VM with GitHub Actions.

### Step 1: Generate SSH Key on VM

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/vm_deploy_key -N ""
cat ~/.ssh/vm_deploy_key.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### Step 2: Get the Private Key

```bash
cat ~/.ssh/vm_deploy_key
```

Copy the entire output (including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`).

### Step 3: Get Your VM's External IP

```bash
curl ifconfig.me
```

Copy the IP address.

### Step 4: Allow systemctl Without Password Prompt

```bash
echo "$USER ALL=(ALL) NOPASSWD: /bin/systemctl" | sudo tee /etc/sudoers.d/cimb-agent
```

### Step 5: Add GitHub Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these three secrets:

| Secret | Value |
|---|---|
| `VM_HOST` | Your VM's external IP address from Step 3 |
| `VM_USER` | Your VM username (usually the default user) |
| `VM_SSH_KEY` | The full private key content from Step 2 (include the BEGIN and END lines) |

### Step 6: Deploy

Push any commit to the `main` branch:

```bash
git push origin main
```

The GitHub Actions pipeline will run automatically and deploy to your VM in ~16 seconds. Watch the progress in the **Actions** tab of your GitHub repo.

## Useful Commands

Quick reference for common tasks:

| Command | Description |
|---|---|
| `sudo systemctl status cimb-agent` | Check if the agent is currently running |
| `sudo systemctl restart cimb-agent` | Stop and restart the agent (picks up .env changes) |
| `sudo systemctl stop cimb-agent` | Stop the agent |
| `sudo systemctl start cimb-agent` | Start the agent |
| `sudo journalctl -u cimb-agent -f` | Watch live logs in real-time (press Ctrl+C to exit) |
| `sudo journalctl -u cimb-agent -n 50` | Show the last 50 log lines |
| `git pull` | Manually pull the latest code from GitHub |
| `cat config/sean.json` | View your config file |
| `.venv/bin/activate` | Activate the virtual environment (if needed for manual testing) |

## Troubleshooting

### EPIPE crash on startup

**Symptom:** The bot crashes with an EPIPE error when you try to start it on the VM.

**Cause:** Not enough swap space for Chromium to load.

**Fix:** Add 1GB swap space (see Section 11, Step 7). Restart the service after adding swap.

### rate=None in logs

**Symptom:** All rate readings show `rate=None` in the logs.

**Cause:** The CIMB page is taking a long time to load, or it loaded before the page fully rendered.

**Fix:** Wait 30–60 seconds on first startup. Playwright needs time to initialize the browser and load the page. If it continues to show `None`, the CIMB page structure may have changed.

### Slash commands not showing in Discord

**Symptom:** You DM the bot but don't see any slash command suggestions.

**Cause:** Global command sync takes up to 1 hour. If you added a DISCORD_GUILD_ID, you can speed this up.

**Fix:** Add `DISCORD_GUILD_ID` to your `.env` file. This makes commands sync to that specific server instantly instead of waiting for global sync. If you don't have a Guild ID, you can get it by right-clicking your server name in Discord (with Developer Mode on) → Copy Server ID.

### Bot not sending DMs

**Symptom:** The agent runs fine but you never get a DM alert when the rate hits your target.

**Cause:** The bot is not in the same server as you.

**Fix:** Make sure you've authorized the bot to your private server using the OAuth2 URL from Section 5, Step 9. The bot must be in the same server as the users it's alerting.

### playwright not found error

**Symptom:** You get `ModuleNotFoundError: No module named 'playwright'` when running `python agent.py`.

**Cause:** You used Python 3.12, which is not supported by Playwright yet.

**Fix:** Use Python 3.11:
```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### Config changes not taking effect

**Symptom:** You edit your config file and save it, but the agent is still using the old settings.

**Cause:** The config file wasn't actually saved, or the watcher didn't pick up the change.

**Fix:** The config watcher checks for changes every 1 second automatically. Make sure you're editing the correct file (e.g., `config/sean.json` not a copy). No restart is needed—just save the file and changes take effect within 1 second.

## Security Notes

- **Never commit `.env`** — it is in `.gitignore` and contains your bot token. If you accidentally commit it, rotate your token immediately.
- **Never commit `config/*.json`** — these files contain real Discord user IDs and should remain private.
- **Keep your Discord bot token secret** — anyone with it can control your bot and read/send messages in your servers.
- **Rotate your VM SSH key if exposed** — if you suspect the private key was compromised, generate a new one and update your GitHub secrets.
- **The agent only reads public data** — it scrapes the public CIMB Clicks rate page. No banking credentials are ever stored or used.
- **No authentication needed** — the agent works with no banking login or credentials. It's purely a public rate monitor.
