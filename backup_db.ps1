# ============================================================
# backup_db.ps1
# django_ma 로컬 DB 백업 스크립트
#
# [수동 실행]
#   PS D:\coding\django_ma> .\backup_db.ps1
#
# [작업 스케줄러 자동 실행]
#   Register-BackupSchedule.ps1 으로 등록 후 자동 실행됨
# ============================================================

$ErrorActionPreference = "Stop"

# -- 설정 ----------------------------------------------------
$PG_USER     = "incar_ma"
$PG_DB       = "django_ma_local"
$COMPOSE_SVC = "db"
$BACKUP_DIR  = "D:\Backups\django_ma"
$RETAIN_DAYS = 90
$PROJECT_DIR = "D:\coding\django_ma"
# ------------------------------------------------------------

function Write-Step([string]$msg) {
    Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan
}
function Write-Ok([string]$msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}
function Write-Fail([string]$msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
}

# 0. 프로젝트 디렉토리 이동
Set-Location $PROJECT_DIR

# 1. 백업 폴더 생성
Write-Step "Step 1/6 - 백업 폴더 확인"
New-Item -ItemType Directory -Force $BACKUP_DIR | Out-Null
Write-Ok "저장 경로: $BACKUP_DIR"

# 2. DB 컨테이너 실행 여부 확인
Write-Step "Step 2/6 - DB 컨테이너 상태 확인"
$running = docker compose ps --services --filter "status=running" 2>$null
if ($running -notcontains $COMPOSE_SVC) {
    Write-Fail "DB 컨테이너($COMPOSE_SVC)가 실행 중이지 않습니다. docker compose up -d 후 재시도하세요."
    exit 1
}
Write-Ok "컨테이너 정상 실행 중"

# 3. pg_dump 실행
Write-Step "Step 3/6 - pg_dump 실행"
$ts       = Get-Date -Format "yyyy-MM-dd_HHmm"
$dumpName = "django_ma_prod_$ts.backup"
$tmpPath  = "/tmp/$dumpName"

docker compose exec -T $COMPOSE_SVC `
    pg_dump -Fc -Z9 --no-owner --no-privileges `
    -U $PG_USER -d $PG_DB -f $tmpPath

if ($LASTEXITCODE -ne 0) {
    Write-Fail "pg_dump 실패 (exit $LASTEXITCODE)"
    exit 1
}
Write-Ok "컨테이너 내 덤프 생성: $tmpPath"

# 4. 컨테이너 -> 로컬 복사
Write-Step "Step 4/6 - 로컬로 파일 복사"
$localPath = Join-Path $BACKUP_DIR $dumpName
docker compose cp "${COMPOSE_SVC}:${tmpPath}" $localPath

if ($LASTEXITCODE -ne 0) {
    Write-Fail "파일 복사 실패"
    exit 1
}

$item   = Get-Item $localPath
$sizeMB = [math]::Round($item.Length / 1MB, 1)
Write-Ok "저장 완료: $localPath ($sizeMB MB)"

# 5. 컨테이너 임시파일 정리
Write-Step "Step 5/6 - 컨테이너 임시파일 정리"
docker compose exec -T $COMPOSE_SVC rm -f $tmpPath | Out-Null
Write-Ok "임시파일 삭제 완료"

# 6. 90일 초과 백업 자동 삭제
Write-Step "Step 6/6 - 만료 백업 정리 (보관: $RETAIN_DAYS 일)"
$cutoff = (Get-Date).AddDays(-$RETAIN_DAYS)
$old    = Get-ChildItem $BACKUP_DIR -Filter "*.backup" |
          Where-Object { $_.LastWriteTime -lt $cutoff }

if ($old.Count -eq 0) {
    Write-Ok "삭제 대상 없음"
} else {
    $old | ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Ok "삭제: $($_.Name)"
    }
}

# 최종 요약
$total = (Get-ChildItem $BACKUP_DIR -Filter "*.backup").Count
Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkGray
Write-Host " 백업 완료" -ForegroundColor White
Write-Host "  파일 : $dumpName" -ForegroundColor White
Write-Host "  크기 : $sizeMB MB" -ForegroundColor White
Write-Host "  경로 : $BACKUP_DIR" -ForegroundColor White
Write-Host "  보관 : 총 $total 개 파일" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor DarkGray
