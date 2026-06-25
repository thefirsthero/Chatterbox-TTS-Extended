$apiKey='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjQ2YzAzOS1iZjk3LTRiNzMtODE3ZC1iMDk4MjQxZDA4YWEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjZjYjE0M2ItNjUxNC00ZjFiLWIwMGEtOTZlZjZmZDFiMzkwIiwiaWF0IjoxNzgyNDA4MDMxLCJleHAiOjE3ODQ5Mzc2MDB9.uR_f9EzuC8GCedXJs6MxbpD-863rZAfQdZTigCOck2A'
$base='https://n8n.coraxi.com/api/v1'
$h=@{'X-N8N-API-KEY'=$apiKey;'Content-Type'='application/json'}
$hg=@{'X-N8N-API-KEY'=$apiKey}

$healthyText = "📊 **Weekly Queue Report**`n`nQueue is healthy! 👍`n`n• 🆕 **{{ `$json.new_count }}** videos available`n• ✅ {{ `$json.done_count }} posted`n• ❌ {{ `$json.failed_count }} failed`n• 📦 {{ `$json.total }} total tracked`n`nNext post: Tomorrow at 19:00 SAST"

$lowInvTemplate = "⚠️ **Low Inventory Alert!**`n`n📊 Queue Status:`n• 🆕 **{{ `$json.new_count }}** new videos remaining`n• ✅ {{ `$json.done_count }} already posted`n• ❌ {{ `$json.failed_count }} failed`n`n🔴 Only **{{ `$json.new_count }}** videos left — upload more!`n`nUpload new videos to:`nDRIVE_LINK"

$configs = @(
    @{id='34Fsiaw78YATJN2x'; drive='1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp'}
    @{id='ZkOIGGuL6SpSyTxR'; drive='1Y-doGuk-5Waw73a1zbEYz9WkBTG16TZj'}
    @{id='wP7y34CxvWQCoCek'; drive='1KX8Uq_dSlGweVgzLJFisKOYSBrettBeq'}
)

foreach ($c in $configs) {
    Write-Host "=== $($c.id) ===" -ForegroundColor Yellow
    $wf = Invoke-RestMethod -Uri "$base/workflows/$($c.id)" -Headers $hg
    
    $hn = $wf.nodes | Where-Object {$_.name -eq 'Send Healthy Report'}
    if ($hn) { $hn.parameters.text = $healthyText }
    
    $ln = $wf.nodes | Where-Object {$_.name -eq 'Send Low Inventory Alert'}
    if ($ln) { $ln.parameters.text = $lowInvTemplate.Replace('DRIVE_LINK', "https://drive.google.com/drive/u/2/folders/$($c.drive)") }
    
    $nj = $wf.nodes | ConvertTo-Json -Depth 10 -Compress
    $cj = $wf.connections | ConvertTo-Json -Depth 10 -Compress
    $body = '{"name":"'+$wf.name+'","nodes":'+$nj+',"connections":'+$cj+',"settings":{"executionOrder":"v1"}}'
    try {
        Invoke-RestMethod -Uri "$base/workflows/$($c.id)" -Method Put -Headers $h -Body $body | Out-Null
        Write-Host "  Discord emojis fixed!" -ForegroundColor Green
    } catch {
        Write-Host "  FAIL: $_" -ForegroundColor Red
    }
}
Write-Host "`nDone! Emojis should render properly now."
