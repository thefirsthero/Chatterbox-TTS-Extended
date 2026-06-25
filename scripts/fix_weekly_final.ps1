$apiKey='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjQ2YzAzOS1iZjk3LTRiNzMtODE3ZC1iMDk4MjQxZDA4YWEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjZjYjE0M2ItNjUxNC00ZjFiLWIwMGEtOTZlZjZmZDFiMzkwIiwiaWF0IjoxNzgyNDA4MDMxLCJleHAiOjE3ODQ5Mzc2MDB9.uR_f9EzuC8GCedXJs6MxbpD-863rZAfQdZTigCOck2A'
$ErrorActionPreference='Continue'
$base='https://n8n.coraxi.com/api/v1'
$h=@{'X-N8N-API-KEY'=$apiKey;'Content-Type'='application/json'}
$hg=@{'X-N8N-API-KEY'=$apiKey}

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

// Also count from Sync Queue Logic (includes unsynced Drive files)
let driveAvailable = 0;
try {
  const syncOut = $('Sync Queue Logic').first().json;
  driveAvailable = syncOut.available_count || 0;
} catch(e) {}
const effectiveNew = Math.max(newCount, driveAvailable);
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

$newSyncCode=@'
const driveItems = $input.all();
let queueItems = [];
try {
  queueItems = $('Read Current Queue').all();
} catch(e) {}

const trackedIds = new Set();
for (const row of queueItems) {
  if (row.json.drive_file_id) trackedIds.add(row.json.drive_file_id);
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

let sheetNew = 0;
for (const row of queueItems) {
  if (row.json.status === 'new') sheetNew++;
}

const availableCount = sheetNew + results.length;

return [{
  new_files_count: results.length,
  available_count: availableCount,
  drive_total: driveItems.length,
  low_inventory: availableCount < 7,
  total_tracked: trackedIds.size + results.length
}];
'@

$wfIds = @(
    @{id='34Fsiaw78YATJN2x';name='AITAH Weekly'}
    @{id='ZkOIGGuL6SpSyTxR';name='TOMC Weekly'}
    @{id='wP7y34CxvWQCoCek';name='TIFU Weekly'}
)

foreach ($w in $wfIds) {
    Write-Host "`n=== $($w.name) ===" -ForegroundColor Yellow
    $wf = Invoke-RestMethod -Uri "$base/workflows/$($w.id)" -Headers $hg
    
    # Update code nodes
    ($wf.nodes | Where-Object {$_.name -eq 'Compute Inventory'}).parameters.jsCode = $newComputeCode
    ($wf.nodes | Where-Object {$_.name -eq 'Sync Queue Logic'}).parameters.jsCode = $newSyncCode
    
    # Build raw JSON body (no PowerShell serialization artifacts)
    $nj = $wf.nodes | ConvertTo-Json -Depth 10 -Compress
    $cj = $wf.connections | ConvertTo-Json -Depth 10 -Compress
    $body = '{"name":"' + $wf.name + '","nodes":' + $nj + ',"connections":' + $cj + ',"settings":{"executionOrder":"v1"}}'
    
    try {
        Invoke-RestMethod -Uri "$base/workflows/$($w.id)" -Method Put -Headers $h -Body $body | Out-Null
        Write-Host "  UPDATED: Compute Inventory + Sync Queue Logic" -ForegroundColor Green
    } catch {
        Write-Host "  FAILED: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== ALL DONE ===" -ForegroundColor Cyan
Write-Host "Fixes applied to all 3 Weekly Sync workflows:"
Write-Host "  1. Compute Inventory now includes Drive file count (not just sheet)"
Write-Host "  2. Sync Queue Logic handles empty sheets gracefully"
Write-Host "  3. Empty drives will still send Discord notifications"
