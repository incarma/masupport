<#
    ============================================
      INCA Financial Service - venv Setup Script
      파일명 : Setup-IncarVenv.ps1
      기능   : venv 생성 → 활성화 → requirements.txt 기반 전체 패키지 설치
      ※ requirements.txt를 절대 덮어쓰지 않음
    ============================================
#>

# 1️⃣ 현재 작업 폴더 확인
Write-Host "🔍 현재 경로: $PWD" -ForegroundColor Cyan

# 2️⃣ Python 설치 여부 확인
Write-Host "🐍 Python 버전 확인 중..."
$pythonVersion = & py --version 2>$null
if (-not $pythonVersion) {
    Write-Host "❌ Python이 설치되어 있지 않습니다. PATH를 확인하세요." -ForegroundColor Red
    exit
}
Write-Host "✅ Python 버전: $pythonVersion" -ForegroundColor Green

# 3️⃣ requirements.txt 존재 여부 확인
# ← 추가: 없으면 설치 근거가 없으므로 중단
if (-not (Test-Path "requirements.txt")) {
    Write-Host "❌ requirements.txt 파일이 없습니다. 프로젝트 루트에서 실행하세요." -ForegroundColor Red
    exit
}
Write-Host "✅ requirements.txt 확인됨." -ForegroundColor Green

# 4️⃣ 가상환경 폴더 이름
$venvName = "venv"

# 5️⃣ 기존 venv 폴더가 있으면 삭제 여부 확인
if (Test-Path $venvName) {
    $confirm = Read-Host "⚠️ 기존 '$venvName' 폴더가 존재합니다. 새로 만들까요? (y/n)"
    if ($confirm -eq "y") {
        Remove-Item -Recurse -Force $venvName
        Write-Host "🧹 기존 venv 폴더 삭제 완료." -ForegroundColor Yellow
    } else {
        Write-Host "❌ 스크립트를 종료합니다." -ForegroundColor Red
        exit
    }
}

# 6️⃣ venv 생성
Write-Host "🪄 가상환경 '$venvName' 생성 중..."
py -m venv $venvName
Write-Host "✅ 가상환경 생성 완료." -ForegroundColor Green

# 7️⃣ PowerShell 정책 완화 (현재 세션 한정)
Write-Host "🔐 스크립트 실행 정책 설정 중 (현재 세션 한정)..."
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned -Force

# 8️⃣ 가상환경 활성화
Write-Host "🚀 가상환경 활성화 중..."
. ".\$venvName\Scripts\Activate.ps1"

# 9️⃣ pip 최신화
Write-Host "⬆️ pip 업그레이드 중..."
python -m pip install --upgrade pip

# 🔟 requirements.txt 기반 전체 패키지 설치
# ← 수정: 4개 수동 설치 + pip freeze 덮어쓰기 → requirements.txt 읽기로 교체
Write-Host "📦 requirements.txt 기반 패키지 전체 설치 중..."
pip install -r requirements.txt

# 1️⃣1️⃣ 결과 요약 출력
Write-Host "`n✅ 모든 설정 완료!" -ForegroundColor Green
Write-Host "-------------------------------------------"
Write-Host "📂 가상환경 경로 : $((Get-Item .\$venvName).FullName)"
Write-Host "📦 설치 기준     : requirements.txt (덮어쓰기 없음)"
Write-Host "💡 다음부터 활성화:"
Write-Host "    .\$venvName\Scripts\Activate.ps1"
Write-Host "-------------------------------------------"