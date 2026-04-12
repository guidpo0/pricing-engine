# GitHub Actions Setup

This document explains how to set up and configure the GitHub Actions workflow for updating investment data.

## Overview

The workflow (`update-investments.yml`) automatically updates market data every 4 hours by:

1. **Health Check** - Wakes up the Render container (if sleeping)
2. **History Status** - Checks current data status
3. **Update Cache** - Calls `/investments/update-cache` to fetch and save all data
4. **Verify Update** - Confirms data was saved to PostgreSQL

## Required Configuration

### 1. Repository Variables

Go to your GitHub repository → Settings → Variables → Actions:

| Variable       | Value                           | Description         |
| -------------- | ------------------------------- | ------------------- |
| `API_BASE_URL` | `https://your-app.onrender.com` | Your Render app URL |

### 2. Repository Secrets

Go to your GitHub repository → Settings → Secrets → Actions:

| Secret           | Value                                          | Description                                          |
| ---------------- | ---------------------------------------------- | ---------------------------------------------------- |
| `API_AUTH_TOKEN` | The value from `API_AUTH_TOKEN` in your `.env` | Token for authenticating with the Pricing Engine API |

### 3. Render Configuration

Make sure your Render app has:

- **Environment Variables:**
  - `API_AUTH_TOKEN` - Must match the secret above
  - `DATABASE_URL` - PostgreSQL connection string
- **Health Check:** Configure `/health` as the health check endpoint

## Workflow Execution Visibility

Each workflow run provides detailed logging for each step:

### Step 1: Health Check

```
📡 STEP 1: Health Check (Wake Up Container)
💤 Attempting to wake up Render container...
📊 HTTP Status Code: 200
📦 Response Body:
{
  "status": "ok",
  "curves_last_updated": "2026-04-12T08:00:00Z",
  "vna_last_updated": "2026-04-12T09:00:00Z",
  "curves_using_fallback": false,
  "vna_using_fallback": false
}
✅ Container is awake and healthy!
```

### Step 2: History Status

```
📜 STEP 2: Check History Status
📊 Querying /investments/history-status...
✅ Historical data exists
   • Last Updated: 2026-04-12T10:00:00Z
```

### Step 3: Update Cache

```
🔄 STEP 3: Update All Investments
📡 Calling POST /investments/update-cache...
📈 Update Results:
   • Overall Status: success
   • Updated At: 2026-04-12T14:00:00Z

📊 Individual Updates:
   • Yield Curves: success
   • Inflation/VNA: success
   • BR Stocks (15 updated): success
   • US Stocks (10 updated): success
   • Crypto (5 updated): success
   • Currencies (8 updated): success
```

## Manual Trigger

You can manually trigger the workflow from the GitHub Actions tab:

1. Go to **Actions** tab
2. Select **Update Investments Data**
3. Click **Run workflow**
4. Optionally enable **Force wakeup**

## Cron Schedule

The workflow runs every 4 hours:

- 00:00 UTC
- 04:00 UTC
- 08:00 UTC
- 12:00 UTC
- 16:00 UTC
- 20:00 UTC

To change the schedule, edit the cron expression in `.github/workflows/update-investments.yml`:

```yaml
on:
  schedule:
    - cron: "0 */4 * * *" # Every 4 hours
```

## Troubleshooting

### Container Not Waking Up

- Check Render dashboard for app status
- Verify health check endpoint is working: `curl https://your-app.onrender.com/health`

### Authentication Failed (401)

- Verify `API_AUTH_TOKEN` secret matches the value in Render
- Check the token is correctly set in Render environment variables

### Update Failed

- Check workflow logs for specific error details
- Verify PostgreSQL connection is working
- Check API logs in Render dashboard

### Rate Limiting

- The workflow includes delays between requests to respect rate limits
- If you see 429 errors, consider reducing the number of tracked tickers or increasing delays
