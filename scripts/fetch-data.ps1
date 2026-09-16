# Fetch the MaleCNS v1.0 connectome tables into the local cache. Resumable, size-verified, never committed.
#
#   .\scripts\fetch-data.ps1 [-WithSynapsePoints]
#
# The cache root comes from CONECTOMA_DATA_ROOT; see docs/guides/02_fetch-the-connectome.md.
param([switch]$WithSynapsePoints)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$base = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
$files = @(
  "body-annotations-male-cns-v1.0-minconf-0.5.feather",
  "body-neurotransmitters-male-cns-v1.0.feather",
  "connectome-weights-male-cns-v1.0-minconf-0.5.feather"
)
if ($WithSynapsePoints) { $files += "syn-points-male-cns-v1.0-minconf-0.5.feather" }

if (-not $env:CONECTOMA_DATA_ROOT) {
  Write-Host "CONECTOMA_DATA_ROOT is not set. Point it at a directory with room for the tables."
  exit 1
}

$dest = Join-Path $env:CONECTOMA_DATA_ROOT "malecns"
if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Force $dest | Out-Null }

foreach ($name in $files) {
  $url = "$base/$name"
  $target = Join-Path $dest $name
  $head = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing
  $expected = [int64]$head.Headers['Content-Length'][0]

  if ((Test-Path $target) -and ((Get-Item $target).Length -eq $expected)) {
    Write-Host "[fetch] $name already complete ($expected bytes)"
    continue
  }

  Write-Host "[fetch] $name ($expected bytes)"
  curl.exe -fSL -C - -o $target $url
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[fetch] FAILED: curl exited $LASTEXITCODE for $name. Re-run to resume."
    exit 1
  }

  $actual = (Get-Item $target).Length
  if ($actual -ne $expected) {
    Write-Host "[fetch] FAILED: $name is $actual bytes, expected $expected. Re-run to resume."
    exit 1
  }
}

Write-Host "[fetch] cache ready at $dest"
Write-Host "[fetch] next: python data-pipeline/run.py build-connectome"
