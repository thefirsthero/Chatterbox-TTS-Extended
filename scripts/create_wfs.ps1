$apiKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjQ2YzAzOS1iZjk3LTRiNzMtODE3ZC1iMDk4MjQxZDA4YWEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjZjYjE0M2ItNjUxNC00ZjFiLWIwMGEtOTZlZjZmZDFiMzkwIiwiaWF0IjoxNzgyNDA4MDMxLCJleHAiOjE3ODQ5Mzc2MDB9.uR_f9EzuC8GCedXJs6MxbpD-863rZAfQdZTigCOck2A'
$ErrorActionPreference = 'Stop'
$base = 'https://n8n.coraxi.com/api/v1'
$h = @{ 'X-N8N-API-KEY' = $apiKey; 'Content-Type' = 'application/json' }
$hg = @{ 'X-N8N-API-KEY' = $apiKey }

$sA = '1tlR_MCm-sSmD4w59TV5AWf-rRx35tERR45zF2QGP2NU'
$dA = '1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp'
$sT = '1j44-JvopCDyEUzHH6nzdaKdY2qGSGOd6kCxzsQdvdBE'
$dT = '1Y-doGuk-5Waw73a1zbEYz9WkBTG16TZj'
$sF = '1bpqDFPQk1rbCGZkoRG-mvQLSvsBU1aOJxBUWEXl53qw'
$dF = '1KX8Uq_dSlGweVgzLJFisKOYSBrettBeq'

function Clone($src, $os, $ns, $od, $nd, $cron) {
    $nodes = $src | ConvertTo-Json -Depth 10 -Compress | ConvertFrom-Json
    foreach ($n in $nodes) {
        if ($n.parameters.sheetId -eq $os) { $n.parameters.sheetId = $ns }
        if ($n.parameters.documentId -and $n.parameters.documentId.PSObject.Properties.Name -contains 'value') {
            if ($n.parameters.documentId.value -eq $os) { $n.parameters.documentId.value = $ns }
            if ($n.parameters.documentId.cachedResultUrl) { $n.parameters.documentId.cachedResultUrl = $n.parameters.documentId.cachedResultUrl.Replace($os, $ns) }
        }
        if ($n.parameters.queryString) { $n.parameters.queryString = $n.parameters.queryString.Replace($od, $nd) }
        if ($n.parameters.text) { $n.parameters.text = $n.parameters.text.Replace($od, $nd) }
        if ($n.type -eq 'n8n-nodes-base.scheduleTrigger' -and $cron) {
            $n.parameters.rule.interval = @(@{field='cronExpression'; expression=$cron})
        }
    }
    return $nodes
}

function NewWf($name, $nodes, $conns) {
    $nj = $nodes | ConvertTo-Json -Depth 10 -Compress
    $cj = $conns | ConvertTo-Json -Depth 10 -Compress
    $body = '{"name":"' + $name + '","nodes":' + $nj + ',"connections":' + $cj + ',"settings":{}}'
    $r = Invoke-RestMethod -Uri "$base/workflows" -Method Post -Headers $h -Body $body
    return $r.id
}

Write-Host "Fetching..." -ForegroundColor Cyan
$dw = Invoke-RestMethod -Uri "$base/workflows/FZf4wvGIMwRNpS0O" -Headers $hg
$ww = Invoke-RestMethod -Uri "$base/workflows/34Fsiaw78YATJN2x" -Headers $hg

Write-Host "`n[1/4] TOMC Daily Publisher (21:00 SAST)" -ForegroundColor Yellow
$n = Clone $dw.nodes $sA $sT $dA $dT '0 19 * * *'
$id1 = NewWf 'TOMC - Daily Publisher (21:00 SAST)' $n $dw.connections
Write-Host "  Created: $id1" -ForegroundColor Green

Write-Host "`n[2/4] TIFU Daily Publisher (13:00 SAST)" -ForegroundColor Yellow
$n = Clone $dw.nodes $sA $sF $dA $dF '0 11 * * *'
$id2 = NewWf 'TIFU - Daily Publisher (13:00 SAST)' $n $dw.connections
Write-Host "  Created: $id2" -ForegroundColor Green

Write-Host "`n[3/4] TOMC Weekly Sync" -ForegroundColor Yellow
$n = Clone $ww.nodes $sA $sT $dA $dT $null
$id3 = NewWf 'TOMC - Weekly Queue Sync & Low Inventory Alert' $n $ww.connections
Write-Host "  Created: $id3" -ForegroundColor Green

Write-Host "`n[4/4] TIFU Weekly Sync" -ForegroundColor Yellow
$n = Clone $ww.nodes $sA $sF $dA $dF $null
$id4 = NewWf 'TIFU - Weekly Queue Sync & Low Inventory Alert' $n $ww.connections
Write-Host "  Created: $id4" -ForegroundColor Green

Write-Host "`n=== VERIFY ===" -ForegroundColor Cyan
$all = Invoke-RestMethod -Uri "$base/workflows" -Headers $hg
foreach ($w in $all.data) {
    $status = if ($w.active) { 'ON ' } else { 'OFF' }
    $color = if ($w.active) { 'Green' } else { 'Yellow' }
    Write-Host "  [$status] $($w.name)" -ForegroundColor $color
}
Write-Host "`nAll 4 created. Activate them in n8n UI (one click each)." -ForegroundColor Cyan
