# Postiz Social Media Automation — n8n Implementation Guide

## Architecture Overview

Two workflows + a Google Sheets queue, triggered daily at 19:00 SAST.

```
┌───────────────────────────────────────────────────────────────┐
│                        Google Drive                           │
│   Folder: 1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp                  │
│   Users drop .mp4 files here                                  │
└────────────────────┬──────────────────────────────────────────┘
                     │
    ┌────────────────┴────────────────┐
    │                                 │
    ▼                                 ▼
┌───────────────┐           ┌────────────────────┐
│  Workflow 2   │           │    Workflow 1       │
│  Weekly Sync  │────populates──▶│  Daily Publisher    │
│  Sun 11:00    │           │  19:00 SAST daily   │
│               │           │                     │
│  • Scans Drive│           │  • Reads queue      │
│  • Syncs Sheet│           │  • Downloads video  │
│  • Alerts <7  │           │  • Uploads to Postiz│
└───────────────┘           │  • Schedules 3 posts│
                            │  • Marks done       │
                            └─────────────────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │     Postiz       │
                            │  Instagram       │
                            │  YouTube Shorts  │
                            │  TikTok (sandbox)│
                            └─────────────────┘
```

## Queue Management Strategy

**Google Sheets as the queue database:**

| Column | Field            | Description                           |
| ------ | ---------------- | ------------------------------------- |
| A      | `file_name`      | Video filename from Drive             |
| B      | `drive_file_id`  | Google Drive file ID                  |
| C      | `status`         | `new`, `processing`, `done`, `failed` |
| D      | `processed_date` | ISO datetime when posted              |
| E      | `error_message`  | Error details if failed               |

**Queue guarantees:**

1. **Used only once**: Status moves `new` → `processing` → `done`. Never re-picks `done`/`processing`.
2. **Predictable order**: FIFO — first uploaded, first posted (by sheet row order).
3. **Failed retries**: Status `failed` videos are re-picked on next run. Set max 3 retries.
4. **No duplicates**: Drive file IDs are deduplicated via the sync workflow.

## Low-Inventory Alert Strategy

**Notification method: Discord webhook** (chosen for reliability, speed, and zero cost).

- **Alert type 1 — Empty queue**: Fires daily at 19:00 SAST if no videos available.
- **Alert type 2 — Low inventory**: Fires weekly if < 7 unused videos remain.
- **Alert type 3 — Success confirmation**: Fires daily after a successful post.
- **Alert type 4 — Weekly summary**: Always fires on Sunday with queue stats.

## Platform-Specific Configurations

### YouTube Shorts

```json
"settings": {
  "__type": "youtube",
  "title": "Am I the as*hole?🤔 Follow for more!",
  "type": "public",
  "selfDeclaredMadeForKids": "no",
  "tags": [
    { "value": "shorts", "label": "shorts" },
    { "value": "reddit", "label": "reddit" },
    { "value": "redditstories", "label": "redditstories" }
  ]
}
```

### TikTok (Sandbox/Testing Mode)

```json
"settings": {
  "__type": "tiktok",
  "privacy_level": "SELF_ONLY",
  "duet": false,
  "stitch": false,
  "comment": true,
  "autoAddMusic": "no",
  "brand_content_toggle": false,
  "brand_organic_toggle": false,
  "content_posting_method": "UPLOAD"
}
```

> `"content_posting_method": "UPLOAD"` ensures TikTok uploads as draft/test — never auto-published.

### Instagram

```json
"settings": {
  "__type": "instagram"
}
```

## Error Handling & Retry Strategy

1. **Node-level**: Each HTTP node has retry-on-fail enabled (3 attempts, 30s backoff).
2. **Workflow-level**: "Continue on Fail" OFF on critical nodes — failure stops the run.
3. **Status tracking**: If any Postiz call fails, the sheet is updated to `failed` with error.
4. **Auto-retry**: Next day's run picks up the `failed` video again (up to 3 times).
5. **Discord alert**: All failures send an immediate notification.

## Step-by-Step Setup Instructions

### Pre-Setup Checklist

Before importing the workflows, gather these values:

- [ ] **Google Sheets URL** — Create a sheet named "Postiz Video Queue"
- [ ] **Postiz API Key** — From Postiz → Settings → API Keys
- [ ] **Postiz Integration IDs** — From the Postiz n8n node, use the "Get Channels" operation to discover:
  - [ ] Instagram integration ID
  - [ ] YouTube integration ID
  - [ ] TikTok integration ID
- [ ] **Discord Webhook URL** — From Discord → Server Settings → Integrations → Webhooks
- [ ] **Google Drive Folder ID**: `1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp` (already known)

### Step 1: Install Postiz Community Node

1. Open n8n: https://n8n.coraxi.com/home/workflows
2. Go to **Settings** (⚙️) → **Community Nodes**
3. Click **Install a community node**
4. Enter: `n8n-nodes-postiz`
5. Click **Install**
6. Refresh the page

### Step 2: Set Up Credentials

Go to **Credentials** → **Add Credential** for each:

#### 2a. Google Drive OAuth2

- Type: `Google Drive OAuth2 API`
- Follow OAuth2 flow to authorize your Google account
- Ensure it has access to the folder `1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp`

#### 2b. Google Sheets OAuth2

- Type: `Google Sheets OAuth2 API`
- Use the same Google account

#### 2c. Postiz API

- Type: `Postiz API`
- **API Key**: Your Postiz API key
- **Host**: `https://postiz.coraxi.com/api`

#### 2d. Discord

- Type: `Discord`
- **Webhook URL**: Your Discord webhook URL

### Step 3: Create the Queue Spreadsheet

1. Go to https://sheets.new
2. Name it: `Postiz Video Queue`
3. Add headers in Row 1:
   ```
   A1: file_name | B1: drive_file_id | C1: status | D1: processed_date | E1: error_message
   ```
4. Copy the sheet URL

### Step 4: Discover Postiz Channel IDs

1. Create a temporary workflow with just:
   - **Manual Trigger** → **Postiz node** (Operation: "Get Channels")
2. Execute it
3. Note the integration IDs for Instagram, YouTube, and TikTok

### Step 5: Import Workflow 1 — Daily Publisher

1. In n8n, click **Import from File**
2. Select `n8n_workflows/workflow1_daily_publisher.json`
3. Replace ALL placeholders:
   - `YOUR_SHEET_URL_HERE` → Your Google Sheets URL
   - `YOUR_GOOGLE_DRIVE_CREDENTIAL` → Your Google Drive credential ID
   - `YOUR_POSTIZ_CREDENTIAL` → Your Postiz credential ID
   - `YOUR_DISCORD_CREDENTIAL` → Your Discord credential ID
   - `YOUR_INSTAGRAM_INTEGRATION_ID` → Instagram channel ID
   - `YOUR_YOUTUBE_INTEGRATION_ID` → YouTube channel ID
   - `YOUR_TIKTOK_INTEGRATION_ID` → TikTok channel ID
4. **Do NOT activate yet** — test first!

### Step 6: Import Workflow 2 — Weekly Sync

1. In n8n, click **Import from File**
2. Select `n8n_workflows/workflow2_weekly_sync.json`
3. Replace ALL placeholders (same as above)
4. **Do NOT activate yet**

### Step 7: Manual Queue Seeding

Run Workflow 2 once manually to populate the queue:

1. Open Workflow 2
2. Click **Test Workflow** (or Execute Workflow)
3. This will scan Drive and populate the sheet
4. Verify the sheet has your videos with status `new`

### Step 8: Test Workflow 1

1. Open Workflow 1
2. Click **Test Workflow**
3. Watch the execution:
   - ✅ Reads queue, finds first `new` video
   - ✅ Downloads from Drive
   - ✅ Uploads to Postiz
   - ✅ Creates 3 posts (Instagram, YouTube, TikTok)
   - ✅ Marks the row as `done`
   - ✅ Sends Discord notification
4. Check Postiz: https://postiz.coraxi.com/launches — verify posts are scheduled

### Step 9: Activate Both Workflows

1. Open Workflow 1 → Toggle **Active** (top-right switch)
2. Open Workflow 2 → Toggle **Active**
3. Both are now running on schedule

### Step 10: Verify the Schedule

- **Workflow 1** runs: Every day at 19:00 SAST (17:00 UTC)
- **Workflow 2** runs: Every Sunday at 11:00 SAST (09:00 UTC)

## Maintenance

### Adding New Videos

1. Upload .mp4 files to the Drive folder
2. Workflow 2 picks them up on Sunday (or run it manually)
3. Videos are posted one per day at 19:00 SAST

### Retrying Failed Posts

1. Open the Google Sheet
2. Change the status from `failed` back to `new`
3. The next daily run picks it up automatically

### Manual Override

- Change any row's status to `done` to skip it
- Change any row's status to `new` to re-post it
- Run either workflow manually at any time from n8n

### Monitoring

- Check Discord for daily success/failure notifications
- Check Discord for weekly inventory alerts
- Open the Google Sheet for full queue status
- Check n8n → Executions for detailed logs

## Troubleshooting

| Symptom                     | Likely Cause                  | Fix                                         |
| --------------------------- | ----------------------------- | ------------------------------------------- |
| "No videos" alert every day | Files not synced to sheet     | Run Workflow 2 manually                     |
| Postiz upload fails         | File too large (>500MB)       | Compress video before uploading             |
| YouTube post fails          | Missing title/tags            | Verify YouTube settings in Postiz node      |
| TikTok post fails           | Media not publicly accessible | Postiz handles hosting; check Postiz config |
| Sheets "Append" fails       | Sheet permissions             | Verify OAuth2 scope includes Sheets write   |
| Drive "Download" fails      | File moved/deleted            | Remove the row from the sheet               |
