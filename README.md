# cimb-rate-sgd-myr

Background agent that monitors the live public CIMB SGD→MYR exchange rate and sends Discord DM alerts when a user's target rate threshold is crossed.

## Stack

- Python 3.11+
- Playwright async (persistent Chromium context, JS evaluation per cycle)
- discord.py (slash commands + DM embeds)
- Per-user JSON config files in `config/`
- systemd for 24/7 Linux VM hosting
- aiofiles for atomic writes

## File Structure

| File | Purpose |
|------|---------|
| `agent.py` | Main scraping loop, rate polling, alert dispatch, user active window checks |
| `bot.py` | Discord bot with slash commands and settings modals (DM only) |
| `notifier.py` | Formats and sends Discord DM embeds with rate alerts |
| `config_loader.py` | Loads, watches, and atomically saves user config JSON files |
| `config/sean.json` | Example user config (gitignored) |
| `.env` | Runtime secrets: bot token, URLs, intervals (gitignored) |
| `cimb-agent.service` | systemd service file for Linux deployment |
| `setup.sh` | Install dependencies via pip |
| `requirements.txt` | Python dependencies |

## Setup

### 1. Clone and install

```bash
git clone <repo-url> /opt/cimb-rate-sgd-myr
cd /opt/cimb-rate-sgd-myr
bash setup.sh
```

### 2. Configure environment

```bash
cp .env.example .env
nano .env
```

Fill in:
- `DISCORD_BOT_TOKEN` — your Discord bot's token (required)
- `DISCORD_GUILD_ID` — (optional) guild ID for faster command sync
- Other settings have sensible defaults

### 3. Add yourself as a user

Create `config/<yourname>.json`:

```json
{
  "name": "Sean",
  "discord_user_id": "YOUR_DISCORD_USER_ID",
  "target_rate": 3.1000,
  "active_start": "09:00",
  "active_end": "19:00",
  "enabled": true,
  "cooldown_minutes": 30,
  "last_alerted_at": null,
  "max_alerts": 3,
  "alert_count": 0,
  "reset_margin": 0.0010
}
```

Get your Discord user ID:
1. Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
2. Right-click your profile → Copy User ID
3. Paste into `discord_user_id`

### 4. Run locally

```bash
python3 agent.py
```

### 5. Deploy on GCP e2-micro with systemd

```bash
# Copy service file
sudo cp cimb-agent.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable cimb-agent
sudo systemctl start cimb-agent

# View logs
sudo journalctl -u cimb-agent -f
```

## Adding a New User

**For admins:**
1. Create `config/<name>.json` using the structure above
2. Share the bot's Discord username with the user
3. No restart needed — the config watcher picks it up within 1 second

**For new users (via `/register` command):**
1. DM the bot `/register <your-name>`
2. Default settings will be created
3. Use `/menu` to customize

## Slash Commands (DM the bot)

All commands are **DM-only**.

| Command | Description |
|---------|-------------|
| `/register name` | Create your account and register for alerts |
| `/status` | Show live rate, your config, and last alert time |
| `/settarget rate` | Set target exchange rate (e.g., 3.1050) |
| `/setwindow start end` | Set active window in HH:MM format (e.g., 09:00 19:00) |
| `/toggle on/off` | Enable or disable alerts |
| `/setcooldown minutes` | Set minimum minutes between alerts |
| `/setmaxalerts count` | Set max alerts before automatic reset (0 = unlimited) |
| `/setresetmargin value` | Set rate drop needed to reset alert counter |
| `/resetalert` | Manually reset your alert count |
| `/menu` | Open interactive settings menu with buttons |

### About Active Window

Your `active_start` and `active_end` times control **both:**
- When alerts are sent to you
- When the scraper runs (pauses entirely if all users are outside their windows)

This saves VM resources during off-hours.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DISCORD_BOT_TOKEN` | (required) | Bot token from Discord Developer Portal |
| `DISCORD_GUILD_ID` | (none) | Optional guild ID for instant command sync |
| `SCRAPE_INTERVAL_MS` | 3000 | Poll rate in milliseconds |
| `IDLE_SLEEP_MS` | 60000 | Sleep duration when no users are active |
| `MAX_NULL_STREAK` | 5 | Reload page after N consecutive null reads |
| `TIMEZONE` | Asia/Singapore | Timezone for active window calculations |
| `CIMB_RATE_URL` | (see .env.example) | CIMB rate page URL |
| `PLAYWRIGHT_USER_DATA_DIR` | .playwright | Chromium profile directory |
| `CONFIG_DIR` | config | User config folder path |

## User Configuration Fields

Each user's JSON file contains:

| Field | Type | Purpose |
|-------|------|---------|
| `name` | string | Display name |
| `discord_user_id` | string | Discord user ID |
| `target_rate` | float | Rate threshold to trigger alerts |
| `active_start` | string | Window start time (HH:MM) |
| `active_end` | string | Window end time (HH:MM) |
| `enabled` | boolean | Whether alerts are active |
| `cooldown_minutes` | integer | Minimum minutes between alerts |
| `max_alerts` | integer | Max alerts before reset (0 = unlimited) |
| `alert_count` | integer | Current alert count (reset at `reset_rate`) |
| `reset_margin` | float | Rate drop from target to reset counter |
| `last_alerted_at` | string | ISO 8601 timestamp of last alert |

## Architecture Notes

- **No database** — JSON files are the only state
- **Atomic writes** — uses temp file + rename to prevent corruption
- **File watching** — config changes take effect within 1 second, no restart needed
- **Persistent browser** — Chromium stays open; only JS evaluation runs each cycle
- **Smart pausing** — scraper sleeps when all users are outside their windows
- **Cooldown tracking** — `last_alerted_at` prevents alert spam
- **Reset margin** — when rate drops below `target - reset_margin`, alert count resets to 0

## License

MIT
