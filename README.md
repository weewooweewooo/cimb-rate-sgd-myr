# cimb-rate-sgd-myr

Python background agent that monitors the live public CIMB
SGD→MYR exchange rate and sends Discord DM alerts when a
user's target rate threshold is crossed.

## Stack

- Python 3.11+
- Playwright async (persistent Chromium, no page reload per cycle)
- discord.py (slash commands + DM alerts)
- Per-user JSON config files in config/
- systemd for 24/7 Linux VM hosting

## File structure

- agent.py — main async loop, scraper, adaptive polling, alert logic
- bot.py — Discord slash commands scoped to DM
- notifier.py — rich embed DM sender
- config_loader.py — atomic JSON read/write with file watcher
- config/*.json — one file per user (gitignored)
- .env — runtime secrets (gitignored)

## Setup

### 1. Clone and configure

    git clone <repo-url> /opt/cimb-rate-sgd-myr
    cd /opt/cimb-rate-sgd-myr
    cp .env.example .env
    nano .env  # fill in DISCORD_BOT_TOKEN

### 2. Install dependencies

    bash setup.sh

### 3. Add yourself as a user

Create config/sean.json (or any name):

    {
      "name": "Sean",
      "discord_user_id": "YOUR_DISCORD_USER_ID",
      "target_rate": 3.1000,
      "buffer": 0.0009,
      "active_start": "09:00",
      "active_end": "19:00",
      "enabled": true,
      "cooldown_minutes": 30,
      "last_alerted_at": null
    }

### 4. Run

    python3 agent.py

### 5. Deploy with systemd (GCP VM)

    sudo cp cimb-agent.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable cimb-agent
    sudo systemctl start cimb-agent
    sudo journalctl -u cimb-agent -f

## How to get your Discord user ID

1. Discord Settings → Advanced → enable Developer Mode
2. Right-click your profile → Copy User ID
3. Paste into discord_user_id in your config JSON

## Adding a new user

1. Create config/<name>.json using the structure above
2. Give them the bot's Discord username so they can DM it
3. No restart needed — config watcher picks it up automatically

## Slash commands (DM the bot)

- /status — live rate, your config, last alert time
- /settarget rate — update your target rate
- /setbuffer value — update your buffer
- /setwindow start end — set active window (HH:MM format)
- /toggle on|off — enable or disable your alerts
- /setcooldown minutes — set cooldown between alerts

/setwindow controls both when you receive alerts AND when the
scraper runs. If all users are outside their windows, the
scraper pauses entirely to save VM resources.

## Environment variables

- DISCORD_BOT_TOKEN — your Discord bot token (required)
- SCRAPE_INTERVAL_NORMAL_MS — poll interval, normal band (default 3000)
- SCRAPE_INTERVAL_NEAR_MS — poll interval, near band (default 800)
- SCRAPE_INTERVAL_CRITICAL_MS — poll interval, critical band (default 200)
- IDLE_SLEEP_MS — sleep when all users outside window (default 60000)
- MAX_NULL_STREAK — null reads before page reload (default 5)
- TIMEZONE — active window timezone (default Asia/Singapore)
- CIMB_RATE_URL — source page URL
- PLAYWRIGHT_USER_DATA_DIR — Chromium profile directory
- CONFIG_DIR — config folder path

## Notes

- No database — JSON files are the only state
- last_alerted_at is written per user for cooldown tracking
- Playwright browser stays open between polls — only JS
  evaluation runs each cycle, not a full page load
- Scraper pauses automatically when no users are in their
  active window, resumes automatically when any window opens
- Adding or editing a config file takes effect within 1 second
  with no restart required