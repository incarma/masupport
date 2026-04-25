# ============================================================
# Register-BackupSchedule.ps1
# 백업 스크립트를 Windows 작업 스케줄러에 등록합니다.
#
# [실행 방법] 최초 1회만 실행
#   PS D:\coding\django_ma> .\Register-BackupSchedule.ps1
#
# [등록 확인]
#   Get-ScheduledTask -TaskName "django_ma_db_backup"
#
# [등록 해제]
#   Unregister-ScheduledTask -TaskName "django_ma_db_backup" -Confirm:$false
# ============================================================

$ErrorActionPreference = "Stop"

# -- 설정 ----------------------------------------------------
$TASK_NAME   = "django_ma_db_backup"
$BACKUP_TIME = "03:00"
$SCRIPT_PATH = Join-Path $PSScriptRoot "backup_db.ps1"
# ------------------------------------------------------------

# backup_db.ps1 존재 여부 확인
if (-not (Test-Path $SCRIPT_PATH)) {
    Write-Host "  [FAIL] backup_db.ps1 을 찾을 수 없습니다: $SCRIPT_PATH" -ForegroundColor Red
    Write-Host "         이 스크립트와 backup_db.ps1 을 같은 폴더에 두세요." -ForegroundColor Yellow
    exit 1
}

# 기존 동명 작업 있으면 제거 후 재등록
$existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
    Write-Host "  기존 작업 제거 후 재등록합니다." -ForegroundColor Yellow
}

# 작업 구성
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -NoProfile -ExecutionPolicy Bypass -File `"$SCRIPT_PATH`""

$trigger = New-ScheduledTaskTrigger -Daily -At $BACKUP_TIME

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable `
    -DontStopOnIdleEnd

$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName  $TASK_NAME `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -Principal $principal `
    -Force | Out-Null

# 등록 결과 출력
$task = Get-ScheduledTask -TaskName $TASK_NAME
Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkGray
Write-Host " 작업 스케줄러 등록 완료" -ForegroundColor Green
Write-Host "  작업명  : $($task.TaskName)" -ForegroundColor White
Write-Host "  실행    : 매일 $BACKUP_TIME" -ForegroundColor White
Write-Host "  스크립트: $SCRIPT_PATH" -ForegroundColor White
Write-Host ""
Write-Host "  [즉시 테스트 실행]" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$TASK_NAME'" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor DarkGray
