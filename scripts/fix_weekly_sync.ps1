$apiKey='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjQ2YzAzOS1iZjk3LTRiNzMtODE3ZC1iMDk4MjQxZDA4YWEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjZjYjE0M2ItNjUxNC00ZjFiLWIwMGEtOTZlZjZmZDFiMzkwIiwiaWF0IjoxNzgyNDA4MDMxLCJleHAiOjE3ODQ5Mzc2MDB9.uR_f9EzuC8GCedXJs6MxbpD-863rZAfQdZTigCOck2A'
$ErrorActionPreference='Continue'
$base='https://n8n.coraxi.com/api/v1'
$h=@{'X-N8N-API-KEY'=$apiKey;'Content-Type'='application/json'}
$hg=@{'X-N8N-API-KEY'=$apiKey}

# New Compute Inventory code — smarter counting that includes Drive data
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

// Also count Drive files from Sync Queue Logic output (includes unsynced files)
let driveFiles = 0;
try {
  const syncOut = $('Sync Queue Logic').first().json;
  driveFiles = syncOut.available_count || 0;
} catch(e) {}

// Use the higher of sheet count vs sync count for "new"
const effectiveNew = Math.max(newCount, driveFiles);
const total = effectiveNew + doneCount + failedCount + processingCount;

return [{
  new_count: effectiveNew,
  done_count: doneCount,
  failed_count: failedCount,
  processing_count: processingCount,
  total: total,
  low_inventory: effectiveNew < 7
}];
'@

# Updated Sync Queue Logic — handles empty drives/sheets gracefully
$newSyncCode=@'
const driveItems = $input.all();
let queueItems = [];
try {
  queueItems = $('Read Current Queue').all();
} catch(e) {
  // Sheet might be empty — that's OK
}

const trackedIds = new Set();
for (const row of queueItems) {
  const d = row.json;
  if (d.drive_file_id) trackedIds.add(d.drive_file_id);
}

const results = [];
for (const item of driveItems) {
  const file = item.json;
  if (!trackedIds.has(file.id)) {
    results.push({
      file_name: file.name,
      drive_file_id: file.id,
      status: 'new'
    });
  }
}

let availableCount = 0;
for (const row of queueItems) {
  if (row.json.status === 'new') availableCount++;
}
availableCount += results.length;

// Count Drive items that are tracked but not "done"
let driveTotal = driveItems.length;

// available_count = new-in-sheet + newly-discovered-in-drive
// We use this in Compute Inventory as fallback
return [{
  new_files_count: results.length,
  available_count: availableCount,
  drive_total: driveTotal,
  low_inventory: availableCount < 7,
  total_tracked: trackedIds.size + results.length
}];
'@

# Workflow IDs to fix
$wfIds = @(
    @{id='34Fsiaw78YATJN2x';name='AITAH Weekly'}
    @{id='ZkOIGGuL6SpSyTxR';name='TOMC Weekly'}
    @{id='wP7y34CxvWQCoCek';name='TIFU Weekly'}
)

foreach ($wfInfo in $wfIds) {
    Write-Host "`nFixing: $($wfInfo.name) ($($wfInfo.id))" -ForegroundColor Yellow
    
    $wf = Invoke-RestMethod -Uri "$base/workflows/$($wfInfo.id)" -Headers $hg
    
    # Update Compute Inventory
    $cn = $wf.nodes | Where-Object { $_.name -eq 'Compute Inventory' }
    if ($cn) {
        $cn.parameters.jsCode = $newComputeCode
        Write-Host "  Updated Compute Inventory" -ForegroundColor Green
    }
    
    # Update Sync Queue Logic
    $sn = $wf.nodes | Where-Object { $_.name -eq 'Sync Queue Logic' }
    if ($sn) {
        $sn.parameters.jsCode = $newSyncCode
        Write-Host "  Updated Sync Queue Logic" -ForegroundColor Green
    }
    
    # Update Count Statuses to read full columns A-E (more robust)
    $cs = $wf.nodes | Where-Object { $_.name -eq 'Count Statuses' }
    if ($cs) {
        $cs.parameters.range = 'A2:E1000'
        $cs.parameters.options = @{continueOnFail=$true}
        Write-Host "  Updated Count Statuses (wider range + continue on fail)" -ForegroundColor Green
    }
    
    # Update Read Current Queue to continue on fail
    $rcq = $wf.nodes | Where-Object { $_.name -eq 'Read Current Queue' }
    if ($rcq) {
        if (-not $rcq.parameters.options) { $rcq.parameters | Add-Member -NotePropertyName 'options' -NotePropertyValue @{} -Force }
        $rcq.parameters.options | Add-Member -NotePropertyName 'continueOnFail' -NotePropertyValue $true -Force
        Write-Host "  Updated Read Current Queue (continue on fail)" -ForegroundColor Green
    }
    
    # Save via PUT
    $body = @{ name=$wf.name; nodes=$wf.nodes; connections=$wf.connections; settings=@{} } | ConvertTo-Json -Depth 10 -Compress
    try {
        Invoke-RestMethod -Uri "$base/workflows/$($wfInfo.id)" -Method Put -Headers $h -Body $body | Out-Null
        Write-Host "  Saved!" -ForegroundColor Green
    } catch {
        Write-Host "  Save error: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== ALL UPDATED ===" -ForegroundColor Cyan
Write-Host "Changes:"
Write-Host "  - Sync Queue Logic: handles empty sheets, tracks drive_total"
Write-Host "  - Compute Inventory: falls back to sync's available_count"
Write-Host "  - Count Statuses: reads full A2:E1000, continues on error"
Write-Host "  - Read Current Queue: continues on fail if sheet is empty"
