# django_ma/scripts/security_grep_core.ps1
<#
CORE INFRA Security Grep

목적:
- CSP style-src 'self' 전환 전 inline style/script 잔존 여부 확인
- .file.url / .image.url 직접 노출 여부 확인
- 위험 이벤트 핸들러 onclick/onsubmit/onchange 잔존 여부 확인

사용:
  powershell -ExecutionPolicy Bypass -File .\scripts\security_grep_core.ps1

성공:
  위험 패턴 0건이면 exit 0

실패:
  하나라도 발견되면 exit 1
#>

$ErrorActionPreference = "Stop"

$patterns = @(
  @{
    Name = "direct file/image url"
    Regex = "\.file\.url|\.image\.url"
    Path = "templates|board|manual|partner|commission|dash"
  },
  @{
    Name = "inline style/script/event handler"
    Regex = "<style>|style=|onclick=|onsubmit=|onchange="
    Path = "templates|board|manual|partner|commission|dash"
  },
  @{
    Name = "raw safe manual render"
    Regex = "\|safe"
    Path = "manual"
  }
)

$failed = $false

foreach ($p in $patterns) {
  Write-Host ""
  Write-Host "=== Check: $($p.Name) ==="

  $cmd = "rg `"$($p.Regex)`" . -g `"*.html`" -g `"*.py`""
  $result = Invoke-Expression $cmd

  if ($LASTEXITCODE -eq 0) {
    $failed = $true
    Write-Host $result
  } else {
    Write-Host "OK"
  }
}

if ($failed) {
  Write-Host ""
  Write-Host "Security grep failed."
  exit 1
}

Write-Host ""
Write-Host "Security grep passed."
exit 0