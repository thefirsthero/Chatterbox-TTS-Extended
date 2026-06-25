$apiKey='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjQ2YzAzOS1iZjk3LTRiNzMtODE3ZC1iMDk4MjQxZDA4YWEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjZjYjE0M2ItNjUxNC00ZjFiLWIwMGEtOTZlZjZmZDFiMzkwIiwiaWF0IjoxNzgyNDA4MDMxLCJleHAiOjE3ODQ5Mzc2MDB9.uR_f9EzuC8GCedXJs6MxbpD-863rZAfQdZTigCOck2A'
$ErrorActionPreference='Continue'
$base='https://n8n.coraxi.com/api/v1'
$h=@{'X-N8N-API-KEY'=$apiKey;'Content-Type'='application/json'}
$hg=@{'X-N8N-API-KEY'=$apiKey}

# Fixed Compute Inventory: count from sheet first, only fall back to Drive when sheet is empty
$newComputeCode=@'
const rows = $input.all();
let newCount = 0, doneCount = 0, failedCount = 0, processingCount = 0;

for (const row of rows) {
  const status = (row.json.status || '').toLowerCase();
  if (status === 'new') newCount++;
  else if (status === 'done') doneCount++;
  else if (status === 'failed') failedCount++;
  else if (status === 'processing') processingCount++;
}

// Only fall back to Drive count if sheet is completely empty (no rows at all)
let effectiveNew = newCount;
let driveTotal = 0;
try {
  const syncOut = $('Sync Queue Logic').first().json;
  driveTotal = syncOut.drive_total || 0;
  if (rows.length === 0) {
    effectiveNew = syncOut.available_count || 0;
  }
} catch(e) {}

const total = effectiveNew + doneCount + failedCount + processingCount;

return [{
  new_count: effectiveNew,
  done_count: doneCount,
  failed_count: failedCount,
  processing_count: processingCount,
  total: total,
  drive_files: driveTotal,
  low_inventory: effectiveNew < 7
}];
'@

# Fixed Discord messages: remove = prefix, use proper n8n expressions
$healthyDiscordText=@'
📊 **Weekly Queue Report**

Queue is healthy! 👍

• 🆕 **{{ $json.new_count }}** videos available
• ✅ {{ $json.done_count }} posted
• ❌ {{ $json.failed_count }} failed
• 📦 {{ $json.total }} total tracked
• 💾 {{ $json.drive_files }} in Drive

Next post: Tomorrow at 19:00 SAST
'@

$lowInvDiscordText=@'
⚠️ **Low Inventory Alert!**

📊 Queue Status:
• 🆕 **{{ $json.new_count }}** new videos remaining
• ✅ {{ $json.done_count }} already posted
• ❌ {{ $json.failed_count }} failed

🔴 Only **{{ $json.new_count }}** videos left — upload more!

Upload new videos to:
https://drive.google.com/drive/u/2/folders/PLACEHOLDER_DRIVE_ID
'@

$wfConfigs = @(
    @{id='34Fsiaw78YATJN2x'; name='AITAH Weekly'; driveFolder='1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp'}
    @{id='ZkOIGGuL6SpSyTxR'; name='TOMC Weekly';  driveFolder='1Y-doGuk-5Waw73a1zbEYz9WkBTG16TZj'}
    @{id='wP7y34CxvWQCoCek'; name='TIFU Weekly';  driveFolder='1KX8Uq_dSlGweVgzLJFisKOYSBrettBeq'}
)

foreach ($cfg in $wfConfigs) {
    Write-Host "`n=== $($cfg.name) ===" -ForegroundColor Yellow
    $wf = Invoke-RestMethod -Uri "$base/workflows/$($cfg.id)" -Headers $hg
    
    # Fix Compute Inventory
    ($wf.nodes | Where-Object {$_.name -eq 'Compute Inventory'}).parameters.jsCode = $newComputeCode
    Write-Host "  Fixed Compute Inventory (sheet-first counting)" -ForegroundColor Green
    
    # Fix Discord messages (remove = prefix + fix emojis)
    $healthy = $wf.nodes | Where-Object {$_.name -eq 'Send Healthy Report'}
    if ($healthy) {
        $healthy.parameters.text = $healthyDiscordText
        Write-Host "  Fixed Healthy Report emojis" -ForegroundColor Green
    }
    
    $lowInv = $wf.nodes | Where-Object {$_.name -eq 'Send Low Inventory Alert'}
    if ($lowInv) {
        $text = $lowInvDiscordText.Replace('PLACEHOLDER_DRIVE_ID', $cfg.driveFolder)
        $lowInv.parameters.text = $text
        Write-Host "  Fixed Low Inventory Alert emojis + Drive link" -ForegroundColor Green
    }
    
    # Save
    $nj = $wf.nodes | ConvertTo-Json -Depth 10 -Compress
    $cj = $wf.connections | ConvertTo-Json -Depth 10 -Compress
    $body = '{"name":"' + $wf.name + '","nodes":' + $nj + ',"connections":' + $cj + ',"settings":{"executionOrder":"v1"}}'
    try {
        Invoke-RestMethod -Uri "$base/workflows/$($cfg.id)" -Method Put -Headers $h -Body $body | Out-Null
        Write-Host "  Saved!" -ForegroundColor Green
    } catch {
        Write-Host "  Save FAILED: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== FIXES APPLIED ===" -ForegroundColor Cyan
Write-Host "1. Inventory count: now from sheet first (only falls back to Drive when sheet empty)"
Write-Host "2. Emojis: removed = prefix from Discord messages"
Write-Host "3. Added drive_files count to report for reference"
Write-Host "`nRe-run the AITAH Weekly Sync. The sheet should repopulate from Drive,"
Write-Host "and the Discord message should show the correct sheet-based count + proper emojis."
