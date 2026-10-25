param(
    [int]$Users = 3,
    [int]$Rate = 1,
    [string]$Duration = "1m",
    [string]$TargetHost = "http://localhost:8000"
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Results = Join-Path $Root "results"
New-Item -ItemType Directory -Path $Results -Force | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Base = Join-Path $Results "locust_$Stamp"

locust -f (Join-Path $Root "load_test_sse.py") `
    --host $TargetHost `
    --headless `
    -u $Users `
    -r $Rate `
    -t $Duration `
    --html "$Base.html" `
    --csv $Base

Write-Host "HTML: $Base.html"
Write-Host "CSV:  $Base*.csv"
