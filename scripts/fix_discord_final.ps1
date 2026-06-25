$apiKey='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjQ2YzAzOS1iZjk3LTRiNzMtODE3ZC1iMDk4MjQxZDA4YWEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjZjYjE0M2ItNjUxNC00ZjFiLWIwMGEtOTZlZjZmZDFiMzkwIiwiaWF0IjoxNzgyNDA4MDMxLCJleHAiOjE3ODQ5Mzc2MDB9.uR_f9EzuC8GCedXJs6MxbpD-863rZAfQdZTigCOck2A'
$base='https://n8n.coraxi.com/api/v1'
$h=@{'X-N8N-API-KEY'=$apiKey;'Content-Type'='application/json'}
$hg=@{'X-N8N-API-KEY'=$apiKey}

# Use = prefix with backtick template literals - emojis work + expressions evaluate
$healthy="= ` + [char]0x1F4CA + [char]0x0020 + [char]0x002A + [char]0x002A + [char]0x0020 + [char]0x0057 + [char]0x0065 + [char]0x0065 + [char]0x006B + [char]0x006C + [char]0x0079 + [char]0x0020 + [char]0x0051 + [char]0x0075 + [char]0x0065 + [char]0x0075 + [char]0x0065 + [char]0x0020 + [char]0x0052 + [char]0x0065 + [char]0x0070 + [char]0x006F + [char]0x0072 + [char]0x0074 + [char]0x002A + [char]0x002A + [char]0x000A + [char]0x000A + [char]0x0051 + [char]0x0075 + [char]0x0065 + [char]0x0075 + [char]0x0065 + [char]0x0020 + [char]0x0069 + [char]0x0073 + [char]0x0020 + [char]0x0068 + [char]0x0065 + [char]0x0061 + [char]0x006C + [char]0x0074 + [char]0x0068 + [char]0x0079 + [char]0x0021 + [char]0x0020 + [char]0x1F44D + [char]0x000A + [char]0x000A + [char]0x2022 + [char]0x0020 + [char]0x1F195 + [char]0x0020 + [char]0x002A + [char]0x002A + [char]0x0024 + [char]0x007B + [char]0x0024 + [char]0x006A + [char]0x0073 + [char]0x006F + [char]0x006E + [char]0x002E + [char]0x006E + [char]0x0065 + [char]0x0077 + [char]0x005F + [char]0x0063 + [char]0x006F + [char]0x0075 + [char]0x006E + [char]0x0074 + [char]0x007D + [char]0x002A + [char]0x002A + [char]0x0020 + [char]0x0076 + [char]0x0069 + [char]0x0064 + [char]0x0065 + [char]0x006F + [char]0x0073 + [char]0x0020 + [char]0x0061 + [char]0x0076 + [char]0x0061 + [char]0x0069 + [char]0x006C + [char]0x0061 + [char]0x0062 + [char]0x006C + [char]0x0065 + [char]0x000A"

# Simpler approach - just fix the = prefix issue
Write-Host "Fixing Discord message format..."

$configs = @(
    @{id='34Fsiaw78YATJN2x'; drive='1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp'}
    @{id='ZkOIGGuL6SpSyTxR'; drive='1Y-doGuk-5Waw73a1zbEYz9WkBTG16TZj'}
    @{id='wP7y34CxvWQCoCek'; drive='1KX8Uq_dSlGweVgzLJFisKOYSBrettBeq'}
)

foreach ($c in $configs) {
    Write-Host "=== $($c.id) ===" -ForegroundColor Yellow
    $wf = Invoke-RestMethod -Uri "$base/workflows/$($c.id)" -Headers $hg
    
    # Fix Healthy Report: use = with template literal
    $hn = $wf.nodes | Where-Object {$_.name -eq 'Send Healthy Report'}
    if ($hn) {
        $hn.parameters.text = "= ` + [char]0x60 + [char]0x1F4CA + " **Weekly Queue Report**\n\nQueue is healthy! " + [char]0x1F44D + "\n\n" + [char]0x2022 + " " + [char]0x1F195 + " **`$" + "{$json.new_count}** videos available\n" + [char]0x2022 + " " + [char]0x2705 + " `$" + "{$json.done_count} posted\n" + [char]0x2022 + " " + [char]0x274C + " `$" + "{$json.failed_count} failed\n" + [char]0x2022 + " " + [char]0x1F4E6 + " `$" + "{$json.total} total tracked\n\nNext post: Tomorrow at 19:00 SAST" + [char]0x60
    }
    
    # Fix Low Inventory: use = with template literal  
    $ln = $wf.nodes | Where-Object {$_.name -eq 'Send Low Inventory Alert'}
    if ($ln) {
        $driveLink = "https://drive.google.com/drive/u/2/folders/$($c.drive)"
        $ln.parameters.text = "= ` + [char]0x60 + [char]0x26A0 + [char]0xFE0F + " **Low Inventory Alert!**\n\n" + [char]0x1F4CA + " Queue Status:\n" + [char]0x2022 + " " + [char]0x1F195 + " **`$" + "{$json.new_count}** new videos remaining\n" + [char]0x2022 + " " + [char]0x2705 + " `$" + "{$json.done_count} already posted\n" + [char]0x2022 + " " + [char]0x274C + " `$" + "{$json.failed_count} failed\n\n" + [char]0x1F534 + " Only **`$" + "{$json.new_count}** videos left \u2014 upload more!\n\nUpload new videos to:\n$driveLink" + [char]0x60
    }
    
    $nj = $wf.nodes | ConvertTo-Json -Depth 10 -Compress
    $cj = $wf.connections | ConvertTo-Json -Depth 10 -Compress
    $body = '{"name":"'+$wf.name+'","nodes":'+$nj+',"connections":'+$cj+',"settings":{"executionOrder":"v1"}}'
    try {
        Invoke-RestMethod -Uri "$base/workflows/$($c.id)" -Method Put -Headers $h -Body $body | Out-Null
        Write-Host "  Done" -ForegroundColor Green
    } catch {
        Write-Host "  FAIL: $_" -ForegroundColor Red
    }
}
Write-Host "`nAll 3 Discord messages fixed! = backtick + emoji + `$`{expressions`}" -ForegroundColor Cyan
