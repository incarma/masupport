# ============================================================
# restore_db.ps1
# django_ma 로컬 개발 DB 복원 스크립트
# E:\backup\django_ma\ 에서 가장 최근 .backup 파일을 자동 선택하여
# django_ma_dev 로 완전 덮어쓰기 복원 + 권한 설정까지 진행합니다.
#
# [최초 1회] 아래 설정부에서 비밀번호를 직접 입력하세요.
#   $PG_PASS : postgres 계정 비밀번호
#
# [실행 방법]
#   PS E:\coding\django_ma> .\restore_db.ps1
# ============================================================

$ErrorActionPreference = "Stop"

# -- 설정 (최초 1회 수정) ------------------------------------
$PG_BIN      = "C:\Program Files\PostgreSQL\18\bin"
$PG_HOST     = "127.0.0.1"
$PG_PORT     = "5432"
$PG_USER     = "postgres"
$PG_PASS     = "INcar851!"   # <-- postgres 비밀번호 입력
$DJANGO_USER = "django_ma_dev_user"
$TARGET_DB   = "django_ma_dev"
$BACKUP_DIR  = "E:\backup\django_ma"
# ------------------------------------------------------------

# PGPASSWORD 환경변수 설정 (psql/pg_restore 비밀번호 자동 주입)
$env:PGPASSWORD = $PG_PASS

function Write-Step([string]$msg) {
    Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan
}
function Write-Ok([string]$msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}
function Write-Fail([string]$msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
}
function Invoke-Psql([string]$db, [string]$sql, [switch]$OnErrorStop) {
    $psqlArgs = @("-U", $PG_USER, "-h", $PG_HOST, "-p", $PG_PORT, "-d", $db)
    if ($OnErrorStop) { $psqlArgs += @("-v", "ON_ERROR_STOP=1") }
    $psqlArgs += @("-c", $sql)
    & "$PG_BIN\psql.exe" @psqlArgs
}

# 0. 최신 백업 파일 자동 선택
Write-Step "Step 0/6 - 복원 파일 선택"

if (-not (Test-Path $BACKUP_DIR)) {
    Write-Fail "백업 폴더가 존재하지 않습니다: $BACKUP_DIR"
    exit 1
}

$latest = Get-ChildItem $BACKUP_DIR -Filter "*.backup" |
          Sort-Object LastWriteTime -Descending |
          Select-Object -First 1

if ($null -eq $latest) {
    Write-Fail "백업 파일이 없습니다: $BACKUP_DIR"
    exit 1
}

$dumpFile = $latest.FullName
$sizeMB   = [math]::Round($latest.Length / 1MB, 1)
Write-Ok "선택된 파일 : $($latest.Name)"
Write-Ok "파일 크기   : $sizeMB MB"
Write-Ok "생성 시각   : $($latest.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"

# 진행 여부 확인
Write-Host ""
Write-Host "  위 파일로 [$TARGET_DB] 를 완전 덮어쓰기합니다." -ForegroundColor Yellow
Write-Host "  계속하려면 Enter, 취소하려면 Ctrl+C 를 누르세요." -ForegroundColor Yellow
Read-Host "Enter 를 눌러 계속"

# 1. 기존 연결 강제 종료
Write-Step "Step 1/6 - 기존 연결 종료"
Invoke-Psql "postgres" "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$TARGET_DB' AND pid<>pg_backend_pid();" | Out-Null
Write-Ok "연결 종료 완료"

# 2. DB 삭제 후 재생성
Write-Step "Step 2/6 - DB 삭제 및 재생성"
& "$PG_BIN\dropdb.exe" -U $PG_USER -h $PG_HOST -p $PG_PORT $TARGET_DB
if ($LASTEXITCODE -ne 0) { Write-Fail "dropdb 실패"; exit 1 }
Write-Ok "DB 삭제 완료: $TARGET_DB"

& "$PG_BIN\createdb.exe" -U $PG_USER -h $PG_HOST -p $PG_PORT $TARGET_DB
if ($LASTEXITCODE -ne 0) { Write-Fail "createdb 실패"; exit 1 }
Write-Ok "DB 재생성 완료: $TARGET_DB"

# 3. pg_restore 실행
Write-Step "Step 3/6 - pg_restore 실행 (시간이 걸릴 수 있습니다)"
& "$PG_BIN\pg_restore.exe" `
    -U $PG_USER -h $PG_HOST -p $PG_PORT `
    -d $TARGET_DB `
    --no-owner --no-privileges `
    "$dumpFile"

if ($LASTEXITCODE -ne 0) {
    Write-Fail "pg_restore 실패 (exit $LASTEXITCODE)"
    exit 1
}
Write-Ok "복원 완료"

# 4. 권한 설정
Write-Step "Step 4/6 - 권한 설정 ($DJANGO_USER)"

# 현재 소유/권한 상태 확인
Write-Host "  [현재 소유/권한 상태]" -ForegroundColor DarkGray
Invoke-Psql $TARGET_DB "SELECT nspname, pg_catalog.pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname='public';"
Invoke-Psql $TARGET_DB "SELECT schemaname, tablename, tableowner FROM pg_tables WHERE tablename='django_migrations';"

# 권한 부여 실행
$grants = @(
    "ALTER SCHEMA public OWNER TO $DJANGO_USER;",
    "GRANT ALL ON SCHEMA public TO $DJANGO_USER;",
    "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DJANGO_USER;",
    "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DJANGO_USER;",
    "GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO $DJANGO_USER;",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DJANGO_USER;",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DJANGO_USER;",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO $DJANGO_USER;"
)

foreach ($sql in $grants) {
    Invoke-Psql $TARGET_DB $sql -OnErrorStop | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "권한 설정 실패: $sql"
        exit 1
    }
}
Write-Ok "권한 설정 완료"

# 5. 검증 쿼리
Write-Step "Step 5/6 - 복원 검증"

Write-Host "  [DB 기본 정보]" -ForegroundColor DarkGray
Invoke-Psql $TARGET_DB "SELECT now() AS current_time, current_database() AS db_name;"

Write-Host "  [deposit_upload_log 최신 업로드 / 총 건수]" -ForegroundColor DarkGray
Invoke-Psql $TARGET_DB "SELECT max(uploaded_at) AS last_upload, count(*) AS total FROM deposit_upload_log;"

Write-Ok "검증 쿼리 완료 -- 운영 DB 와 동일한 값이면 성공"

# 6. PGPASSWORD 환경변수 정리
Write-Step "Step 6/6 - 마무리"
$env:PGPASSWORD = ""
Write-Ok "PGPASSWORD 환경변수 초기화 완료"

# 최종 요약
Write-Host ""
Write-Host "==========================================" -ForegroundColor DarkGray
Write-Host " 복원 완료" -ForegroundColor White
Write-Host "  파일 : $($latest.Name)" -ForegroundColor White
Write-Host "  대상 : $TARGET_DB" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor DarkGray
