# Deployment Guide

This document explains how the CI/CD pipeline works, how to set up GitHub Secrets, and how to manually deploy if needed.

## Overview

The project uses **GitHub Actions** to automatically deploy to the GCP VM whenever code is pushed to the `main` branch.

### Deployment Pipeline Flow

1. **Push to main** → GitHub Actions workflow triggers
2. **Checkout code** → Latest code is pulled from the repository
3. **SSH to VM** → GitHub Actions connects to the GCP VM using SSH
4. **Pull latest code** → `git pull origin main` on the VM
5. **Install dependencies** → `pip install -r requirements.txt` in the virtual environment
6. **Restart service** → `sudo systemctl restart cimb-agent`
7. **Verify status** → `sudo systemctl status cimb-agent` confirms the service is running

The entire pipeline is defined in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml).

---

## GitHub Secrets Setup

To enable automated deployments, you must configure three GitHub Secrets in your repository:

### Step 1: Get Your SSH Private Key from the VM

1. SSH into the GCP VM:
   ```bash
   ssh -i <your-local-key> <VM_USER>@<VM_EXTERNAL_IP>
   ```

2. Display the private SSH key:
   ```bash
   cat ~/.ssh/google_compute_engine
   ```

3. Copy the entire output, including:
   - `-----BEGIN RSA PRIVATE KEY-----` (first line)
   - All the key content in the middle
   - `-----END RSA PRIVATE KEY-----` (last line)

### Step 2: Add Secrets to GitHub

1. Go to your GitHub repository
2. Click **Settings** (top menu)
3. Click **Secrets and variables** → **Actions** (left sidebar)
4. Click **New repository secret** and add three secrets:

   | Secret Name | Value |
   |-------------|-------|
   | `VM_HOST` | External IP of your GCP VM (e.g., `35.184.135.76`) |
   | `VM_USER` | VM username (e.g., `ubuntu` or your GCP default user) |
   | `VM_SSH_KEY` | Full content of `~/.ssh/google_compute_engine` from the VM |

### Step 3: Verify the Setup

Push a small change to the `main` branch:

```bash
git add .
git commit -m "test deployment"
git push origin main
```

Go to **Actions** tab in GitHub and verify the workflow runs successfully. You should see the green checkmark when deployment completes.

---

## Manual Deployment (If Pipeline Fails)

If the GitHub Actions pipeline fails or you need to deploy manually:

### SSH into the VM

```bash
ssh -i <your-local-key> <VM_USER>@<VM_EXTERNAL_IP>
```

### Run the Deployment Commands

```bash
cd /opt/cimb-rate-sgd-myr

# Pull latest code
git pull origin main

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt --quiet

# Restart the service
sudo systemctl restart cimb-agent

# Verify status
sudo systemctl status cimb-agent --no-pager
```

---

## Checking Logs

To view real-time logs from the `cimb-agent` service:

```bash
# SSH into the VM
ssh -i <your-local-key> <VM_USER>@<VM_EXTERNAL_IP>

# Follow logs (Ctrl+C to exit)
sudo journalctl -u cimb-agent -f
```

To view the last 50 lines of logs:

```bash
sudo journalctl -u cimb-agent -n 50
```

---

## Checking Service Status

To check if the service is currently running:

```bash
# SSH into the VM
ssh -i <your-local-key> <VM_USER>@<VM_EXTERNAL_IP>

# View service status
sudo systemctl status cimb-agent

# Or for a one-liner without pager:
sudo systemctl status cimb-agent --no-pager
```

Expected output when running:
```
● cimb-agent.service - CIMB SGD→MYR Rate Alert Agent
     Loaded: loaded (/etc/systemd/system/cimb-agent.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-05-24 12:00:00 UTC; 2h 30min ago
     ...
```

---

## Troubleshooting

### Deployment failed in GitHub Actions

1. Check the **Actions** tab for error messages
2. Review the logs in the workflow run details
3. Verify GitHub Secrets are set correctly (Settings → Secrets)
4. Verify the VM is reachable at the IP in `VM_HOST`

### Service won't restart

1. SSH into the VM
2. Check service status: `sudo systemctl status cimb-agent`
3. View logs: `sudo journalctl -u cimb-agent -n 20`
4. Restart manually: `sudo systemctl restart cimb-agent`

### SSH authentication fails

1. Verify `VM_SSH_KEY` secret contains the full private key (including BEGIN/END lines)
3. Verify `VM_USER` secret is set correctly (to your SSH user)
3. Verify `VM_HOST` is the external IP of your GCP VM
4. Test SSH access manually from your local machine

---

## Files Modified by Deployment

The deployment pipeline modifies the following on the VM:

- Python dependencies installed in `/opt/cimb-rate-sgd-myr/.venv`
- Source code in `/opt/cimb-rate-sgd-myr` (via `git pull`)
- Service state (restart of `cimb-agent`)

Configuration files (`config/`, `.env`) are **not** overwritten by the deployment—only code changes are pulled.

---

## Questions or Issues?

- Check the GitHub Actions workflow at `.github/workflows/deploy.yml`
- Review service logs: `sudo journalctl -u cimb-agent -f`
- Check service status: `sudo systemctl status cimb-agent --no-pager`
