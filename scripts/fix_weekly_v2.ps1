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

// available_count = new-in-sheet + new-from-drive = total available queue
const availableCount = sheetNew + results.length;
const driveTotal = driveItems.length;

return [{
  new_files_count: results.length,
  available_count: availableCount,
  drive_total: driveTotal,
  low_inventory: availableCount < 7,
  total_tracked: trackedIds.size + results.length
}];
'@

$wfIds = @('34Fsiaw78YATJN2x','ZkOIGGuL6SpSyTxR','wP7y34CxvWQCoCek')
$wfNames = @('AITAH Weekly','TOMC Weekly','TIFU Weekly')

for ($i=0; $i -lt $wfIds.Count; $i++) {
    $id = $wfIds[$i]
    Write-Host "`n=== $($wfNames[$i]) ($id) ===" -ForegroundColor Yellow
    
    # Fetch
    $wf = Invoke-RestMethod -Uri "$base/workflows/$id" -Headers $hg
    $wasActive = $wf.active
    Write-Host "  Currently active: $wasActive"
    
    # Deactivate if active
    if ($wasActive) {
        Invoke-RestMethod -Uri "$base/workflows/$id" -Method Put -Headers $h -Body '{"active":false}' 2>$null
        Write-Host "  Deactivated for editing" -ForegroundColor Gray
    }
    
    # Update Compute Inventory
    $cn = $wf.nodes | Where-Object { $_.name -eq 'Compute Inventory' }
    if ($cn) { $cn.parameters.jsCode = $newComputeCode }
    
    # Update Sync Queue Logic
    $sn = $wf.nodes | Where-Object { $_.name -eq 'Sync Queue Logic' }
    if ($sn) { $sn.parameters.jsCode = $newSyncCode }
    
    # Save (just nodes changed, no additional fields touched)
    $payload = @{ name=$wf.name; nodes=$wf.nodes; connections=$wf.connections; settings=$wf.settings }
    $body = $payload | ConvertTo-Json -Depth 10 -Compress
    try {
        Invoke-RestMethod -Uri "$base/workflows/$id" -Method Put -Headers $h -Body $body | Out-Null
        Write-Host "  Saved!" -ForegroundColor Green
    } catch {
        Write-Host "  Save FAILED: $_" -ForegroundColor Red
        # Try without settings
        $payload2 = @{ name=$wf.name; nodes=$wf.nodes; connections=$wf.connections }
        $body2 = $payload2 | ConvertTo-Json -Depth 10 -Compress
        try {
            Invoke-RestMethod -Uri "$base/workflows/$id" -Method Put -Headers $h -Body $body2 | Out-Null
            Write-Host "  Saved (no settings)!" -ForegroundColor Green
        } catch {
            Write-Host "  Save FAILED again: $_" -ForegroundColor Red
        }
    }
    
    # Reactivate
    if ($wasActive) {
        Invoke-RestMethod -Uri "$base/workflows/$id" -Method Put -Headers $h -Body '{"active":true}' 2>$null
        Write-Host "  Reactivated" -ForegroundColor Gray
    }
}

Write-Host "`n=== DONE ===" -ForegroundColor Cyan
Write-Host "Run a Weekly Sync to test: the Discord message should now show the actual Drive video count"
