# django_ma 신규 팀원용 Docker 개발환경 구축 체크리스트 (A-Z)

> 대상: `django_ma` 프로젝트에 처음 합류한 팀원  
> 기준 OS: **Windows 10/11**  
> 기준 개발 방식: **Docker로 DB/Redis/Celery를 실행하고, Django 웹은 우선 로컬 `runserver`로 병행**  
> 목적: **운영과 최대한 비슷한 개발환경을 빠르고 안정적으로 구축**

---

# 0. 이 문서의 목표

이 문서는 신규 팀원이 새 컴퓨터에서 `django_ma` 개발환경을 재현할 수 있도록,
아래 항목을 **처음부터 끝까지** 순서대로 설명하는 체크리스트입니다.

이 문서를 따르면 다음 상태까지 도달하는 것을 목표로 합니다.

- Git 저장소를 정상적으로 clone 했다.
- Docker Desktop이 정상 설치되었다.
- 개발용 `.env` 파일이 준비되었다.
- Docker로 `db`, `redis`를 실행할 수 있다.
- 필요 시 `celery`도 Docker로 실행할 수 있다.
- 로컬 Python 가상환경을 만들고 패키지를 설치했다.
- `python manage.py migrate`가 정상 동작한다.
- `python manage.py runserver`로 사이트에 접속할 수 있다.
- 기본 페이지와 주요 기능을 최소 검증했다.

---

# 1. 전체 구축 방식 요약

`django_ma`의 권장 개발 방식은 아래와 같습니다.

## 권장 개발 실행 구조

- **Docker 실행**
  - PostgreSQL (`db`)
  - Redis (`redis`)
  - 필요 시 Celery (`celery`)
- **로컬 실행**
  - Django 웹 서버 (`python manage.py runserver`)

이 구조를 쓰는 이유는 다음과 같습니다.

- DB/Redis/Celery 같은 인프라 의존성은 팀원별 차이가 나면 문제가 자주 생깁니다.
- 반면 Django 웹은 로컬에서 실행하면 템플릿/CSS/JS 수정 확인이 빠릅니다.
- 따라서 **인프라는 Docker로 통일**하고, **웹은 당분간 로컬 runserver로 병행**하는 것이 가장 실무적입니다.

---

# 2. 사전 준비물

아래 항목이 준비되어 있어야 합니다.

## 필수 준비물

- 회사/팀에서 공유받은 `django_ma` Git 저장소 접근 권한
- 인터넷 연결
- 관리자 권한이 있는 Windows 계정
- 최소 15~20GB 이상의 여유 디스크 공간
- 가능하면 16GB 이상의 메모리

## 계정/권한 준비

- GitHub 저장소 접근 권한
- 프로젝트 `.env.dev` 작성에 필요한 값 또는 `.env.dev.example`
- 필요 시 DB 초기 데이터 또는 테스트 계정 정보

---

# 3. 설치해야 할 프로그램 체크리스트

아래 프로그램을 설치합니다.

- [ ] Git
- [ ] Docker Desktop
- [ ] Python 3.x
- [ ] VS Code
- [ ] VS Code Python 확장
- [ ] VS Code Docker 확장 (권장)
- [ ] DBeaver 또는 pgAdmin (권장, 선택)

---

# 4. Windows 설정 점검

Docker Desktop은 Windows 환경에서 일부 사전 조건이 필요합니다.

## 확인 항목

- [ ] Windows 10/11 최신 업데이트 상태 확인
- [ ] BIOS에서 가상화(VT-x / AMD-V) 활성화 여부 확인
- [ ] WSL2 사용 가능 여부 확인
- [ ] Hyper-V / Virtual Machine Platform 관련 기능 활성화 여부 확인

## 권장 확인 방법

### 1) 작업 관리자에서 가상화 확인
- `Ctrl + Shift + Esc` → 성능 탭 → CPU
- 오른쪽 하단에 **가상화: 사용**으로 보이면 좋습니다.

### 2) PowerShell에서 WSL 상태 확인
관리자 PowerShell에서:

```powershell
wsl --status
```

정상이라면 기본 배포판/버전 정보가 보이거나, WSL 관련 상태를 확인할 수 있습니다.

---

# 5. Git 설치

## 체크리스트
- [ ] Git 공식 설치 파일 다운로드
- [ ] 기본 옵션으로 설치
- [ ] PowerShell 또는 CMD에서 `git --version` 확인

## 확인 명령

```powershell
git --version
```

정상 예시:

```powershell
git version 2.xx.x.windows.x
```

---

# 6. Docker Desktop 설치

## 체크리스트
- [ ] Docker Desktop 다운로드
- [ ] 설치 중 WSL2 관련 옵션 활성화
- [ ] 설치 후 Windows 재부팅
- [ ] Docker Desktop 실행 확인

## 설치 후 확인

```powershell
docker --version
docker compose version
```

정상 예시:

```powershell
Docker version xx.x.x
Docker Compose version v2.x.x
```

## 추가 확인

```powershell
docker run hello-world
```

정상이라면 hello-world 이미지가 내려받아지고 테스트 메시지가 출력됩니다.

---

# 7. Python 설치

`django_ma`는 현재 로컬 `runserver` 병행 방식을 권장하므로 Python 설치가 필요합니다.

## 체크리스트
- [ ] Python 설치 파일 다운로드
- [ ] 설치 시 **Add Python to PATH** 체크
- [ ] 설치 완료 후 버전 확인

## 확인 명령

```powershell
python --version
pip --version
```

---

# 8. VS Code 설치

## 체크리스트
- [ ] VS Code 설치
- [ ] Python 확장 설치
- [ ] Docker 확장 설치 (권장)
- [ ] GitHub 로그인 (권장)

---

# 9. 프로젝트 저장 위치 결정

프로젝트를 저장할 로컬 폴더를 미리 정합니다.

## 권장 예시

```text
C:\workspace\django_ma
```

또는

```text
D:\projects\django_ma
```

## 주의

- 경로에 한글/공백이 너무 많으면 일부 툴에서 번거로울 수 있습니다.
- 가능한 한 **짧고 단순한 경로**를 권장합니다.

---

# 10. 저장소 clone

## 체크리스트
- [ ] 적절한 작업 폴더로 이동
- [ ] Git 저장소 clone
- [ ] 프로젝트 루트 진입

## 예시 명령

```powershell
cd C:\workspace
git clone <저장소_URL>
cd django_ma
```

## 확인 항목
- [ ] `manage.py` 파일이 보인다.
- [ ] `web_ma` 폴더가 보인다.
- [ ] `requirements.txt`가 보인다.
- [ ] `docker-compose.dev.yml` 또는 관련 개발용 파일이 보인다.

---

# 11. 브랜치 전략 확인

팀에서 사용하는 브랜치 전략을 먼저 확인합니다.

## 체크리스트
- [ ] 기본 브랜치가 `main`인지 `master`인지 확인
- [ ] 개인 작업용 브랜치 생성 규칙 확인
- [ ] 직접 push 가능한 브랜치 범위 확인

## 예시

```powershell
git branch -a
```

개인 브랜치 생성 예시:

```powershell
git checkout -b feature/your-name-init-env
```

---

# 12. 환경변수 파일 준비

개발환경에서 가장 중요한 단계입니다.

## 체크리스트
- [ ] `.env.dev.example` 파일 확인
- [ ] 이를 복사해 `.env.dev` 생성
- [ ] 필요한 값 수정
- [ ] 운영용 `.env.prod`를 절대 건드리지 않음

## 예시 명령

PowerShell:

```powershell
Copy-Item .env.dev.example .env.dev
```

또는 수동 복사 후 이름 변경

## 핵심 원칙

- `.env.dev`는 **개발 전용**입니다.
- 운영 DB 접속 정보가 들어가면 안 됩니다.
- `DB_NAME`, `DB_HOST`, `DB_PORT`, `REDIS_URL`이 개발용으로 맞는지 반드시 확인합니다.

---

# 13. .env.dev에서 꼭 확인할 항목

아래 항목은 반드시 확인합니다.

## 기본 항목
- [ ] `APP_ENV=dev`
- [ ] `DEBUG=True`
- [ ] 개발용 `SECRET_KEY`

## DB 항목
- [ ] `DB_NAME`이 개발용 이름인지 확인
- [ ] `DB_HOST=127.0.0.1` 또는 팀 표준값인지 확인
- [ ] `DB_PORT=5433` 등 개발용 포트인지 확인

## Redis/Celery 항목
- [ ] `REDIS_URL=redis://127.0.0.1:6379/0`
- [ ] `CELERY_BROKER_URL` 확인
- [ ] `CELERY_RESULT_BACKEND` 확인

## 절대 금지
- [ ] 운영 DB 주소 입력 금지
- [ ] 운영용 비밀키 재사용 금지
- [ ] 운영 Redis 주소 사용 금지

---

# 14. Docker Desktop 상태 확인

Docker를 실제로 띄우기 전에 Desktop이 정상 실행 중인지 확인합니다.

## 체크리스트
- [ ] Docker Desktop 아이콘이 작업 표시줄에 정상 표시
- [ ] Engine running 상태 확인
- [ ] 첫 실행 시 로그인 필요 여부 확인

## 명령 확인

```powershell
docker info
```

오류 없이 정보가 출력되면 정상입니다.

---

# 15. 개발용 compose 파일 확인

프로젝트 루트에서 `docker-compose.dev.yml` 파일을 확인합니다.

## 체크리스트
- [ ] `db` 서비스가 있다.
- [ ] `redis` 서비스가 있다.
- [ ] 필요 시 `celery` 서비스가 있다.
- [ ] 필요 시 `web` 서비스 또는 profile 기반 설정이 있다.
- [ ] 포트 충돌 가능성을 검토했다.

## 권장 포트 예시
- PostgreSQL: 호스트 `5433`
- Redis: 호스트 `6379`
- Django web: 호스트 `8000`

---

# 16. 처음으로 Docker 컨테이너 실행

우선 가장 기본인 `db`, `redis`만 올립니다.

## 체크리스트
- [ ] 프로젝트 루트에서 compose 실행
- [ ] 에러 없이 컨테이너 생성 확인
- [ ] 컨테이너 상태 확인

## 예시 명령

```powershell
docker compose -f docker-compose.dev.yml up -d db redis
```

## 상태 확인

```powershell
docker compose -f docker-compose.dev.yml ps
```

정상이라면 `db`, `redis`가 `running` 상태여야 합니다.

---

# 17. Docker 로그 확인

실행만 됐다고 끝이 아닙니다. 초기화 에러가 없는지 로그를 확인합니다.

## 체크리스트
- [ ] DB 로그 확인
- [ ] Redis 로그 확인
- [ ] fatal 에러 없음 확인

## 예시 명령

```powershell
docker compose -f docker-compose.dev.yml logs db
docker compose -f docker-compose.dev.yml logs redis
```

## DB 로그에서 확인할 것
- 데이터 디렉터리 초기화 완료
- listening 상태
- authentication fatal 없음

---

# 18. PostgreSQL 포트 연결 확인

컨테이너 DB가 떠 있어도 포트 바인딩이 꼬일 수 있습니다.

## 체크리스트
- [ ] `5433` 같은 개발용 포트가 실제로 열려 있는지 확인
- [ ] 기존 로컬 PostgreSQL과 충돌 없는지 확인

## 점검 방법

```powershell
netstat -ano | findstr 5433
```

포트 충돌이 있으면 compose 포트를 바꾸거나 기존 로컬 PostgreSQL 서비스를 중지해야 합니다.

---

# 19. 가상환경 생성

이제 로컬 Django 실행을 위한 Python 가상환경을 만듭니다.

## 체크리스트
- [ ] 프로젝트 루트에서 가상환경 생성
- [ ] 가상환경 활성화
- [ ] pip 업그레이드

## 예시 명령

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

프롬프트 앞에 `(venv)`가 붙으면 정상입니다.

---

# 20. Python 패키지 설치

## 체크리스트
- [ ] `requirements.txt` 기반 설치
- [ ] 에러 로그 확인
- [ ] psycopg/psycopg2 계열 설치 에러 여부 확인

## 예시 명령

```powershell
pip install -r requirements.txt
```

## 설치가 오래 걸릴 수 있는 항목
- `psycopg2` 계열
- `pandas`
- `openpyxl`
- `celery`
- 기타 C 빌드 의존성 있는 패키지

---

# 21. VS Code에서 인터프리터 선택

## 체크리스트
- [ ] VS Code로 프로젝트 열기
- [ ] Python interpreter를 `venv`로 지정
- [ ] 터미널이 자동으로 `venv`를 인식하는지 확인

## 확인 방법
- `Ctrl + Shift + P`
- `Python: Select Interpreter`
- 프로젝트의 `venv` 선택

---

# 22. Django 환경 체크

로컬에서 Django 설정이 잘 읽히는지 점검합니다.

## 체크리스트
- [ ] `.env.dev` 반영 여부 확인
- [ ] settings import 에러 없음 확인
- [ ] 기본 검사 통과

## 예시 명령

```powershell
python manage.py check
```

오류가 있으면 우선 이 단계에서 해결해야 합니다.

---

# 23. DB 마이그레이션 적용

## 체크리스트
- [ ] 개발 DB가 맞는지 재확인
- [ ] 마이그레이션 실행
- [ ] 에러 없음을 확인

## 예시 명령

```powershell
python manage.py migrate
```

## 주의

이 단계에서 가장 중요한 것은 **연결 대상이 개발 DB인지**입니다.
운영 DB에 실수로 연결된 상태에서 migrate를 실행하면 매우 위험합니다.

---

# 24. 슈퍼유저 생성 여부 확인

필요하다면 관리자 계정을 생성합니다.

## 체크리스트
- [ ] 팀에서 공용 테스트 계정이 있는지 확인
- [ ] 없으면 로컬용 슈퍼유저 생성

## 예시 명령

```powershell
python manage.py createsuperuser
```

---

# 25. Django runserver 실행

이제 로컬 웹 서버를 실행합니다.

## 체크리스트
- [ ] `runserver` 실행
- [ ] 브라우저 접속 확인
- [ ] 기본 페이지 렌더링 확인

## 예시 명령

```powershell
python manage.py runserver
```

기본 접속 주소:

```text
http://127.0.0.1:8000/
```

---

# 26. 로그인 검증

## 체크리스트
- [ ] 로그인 페이지 접속 가능
- [ ] 테스트 계정으로 로그인 가능
- [ ] 로그인 후 기본 랜딩 페이지 진입 가능
- [ ] 로그아웃 가능

---

# 27. 기본 페이지 최소 검증

신규 팀원은 최소한 아래를 한 번씩 열어보는 것이 좋습니다.

## 체크리스트
- [ ] 홈 또는 랜딩 페이지
- [ ] board 앱 주요 페이지
- [ ] partner 앱 주요 페이지
- [ ] manual 앱 주요 페이지
- [ ] commission 앱 주요 페이지
- [ ] dash 앱 주요 페이지

## 목적
- URL reverse 문제 확인
- 템플릿 누락 여부 확인
- 정적파일 오류 확인
- 권한 기반 메뉴/접근 상태 확인

---

# 28. 정적파일 로딩 확인

## 체크리스트
- [ ] 브라우저 개발자도구 Network 탭 확인
- [ ] CSS/JS가 200으로 로드되는지 확인
- [ ] 404 정적파일이 없는지 확인

## 특히 볼 것
- `base.css`
- `fixes.css`
- `plugins/datatables.css`
- 앱별 JS/CSS

---

# 29. DB 연결 실제 확인

화면이 보인다고 DB가 완전히 정상인 것은 아닙니다.

## 체크리스트
- [ ] 로그인 등 DB 조회 기능이 동작하는지 확인
- [ ] 관리자 페이지 또는 목록 페이지 데이터 로드 확인
- [ ] DB connection 에러 없음 확인

---

# 30. Redis 연결 확인

Redis는 Celery나 캐시가 필요한 경우 중요합니다.

## 체크리스트
- [ ] Redis 컨테이너 상태 정상
- [ ] Redis 관련 connection refused 없음
- [ ] Celery를 쓰지 않더라도 기본 연결 오류가 없는지 확인

## 로그 확인

```powershell
docker compose -f docker-compose.dev.yml logs redis
```

---

# 31. Celery 실행이 필요한 경우

비동기 작업을 테스트해야 한다면 Celery도 Docker로 올립니다.

## 체크리스트
- [ ] worker 프로필 또는 celery 서비스 실행
- [ ] worker 로그 확인
- [ ] task import 에러 없음 확인

## 예시 명령

```powershell
docker compose -f docker-compose.dev.yml --profile worker up -d celery
```

또는 팀 표준 명령 사용

## 로그 확인

```powershell
docker compose -f docker-compose.dev.yml logs -f celery
```

---

# 32. Celery 정상 동작 확인

## 체크리스트
- [ ] worker가 startup 완료 상태인지 확인
- [ ] 태스크 수신 로그 확인 가능
- [ ] 등록된 태스크 import 에러 없음

특히 `dash`, `accounts`, `commission` 관련 비동기 기능이 있다면 한 번 테스트합니다.

---

# 33. 파일/로그 디렉터리 확인

`django_ma`는 업로드/로그 중요도가 높은 편이므로 디렉터리를 확인합니다.

## 체크리스트
- [ ] `logs/` 디렉터리 확인
- [ ] `media/` 디렉터리 확인
- [ ] 필요 시 `var/dash_models` 등 보조 디렉터리 확인
- [ ] 권한 문제 없는지 확인

---

# 34. Git 기본 설정

팀원 PC에서는 최소한 아래 Git 설정을 해두는 것이 좋습니다.

## 체크리스트
- [ ] 사용자 이름 설정
- [ ] 사용자 이메일 설정
- [ ] 줄바꿈 정책 확인

## 예시 명령

```powershell
git config --global user.name "홍길동"
git config --global user.email "your_email@example.com"
```

줄바꿈 정책은 팀 표준이 있으면 그에 맞춥니다.

---

# 35. 첫 실행 후 꼭 해야 할 검증

아래는 반드시 수행하는 것을 권장합니다.

## 체크리스트
- [ ] `python manage.py check`
- [ ] `python manage.py migrate`
- [ ] 로그인 가능
- [ ] 주요 페이지 3개 이상 진입 가능
- [ ] 정적파일 404 없음
- [ ] Docker `db`, `redis` 정상 실행
- [ ] 필요 시 `celery` 정상 실행

---

# 36. 자주 발생하는 문제와 해결 가이드

## 문제 1. `docker compose` 명령이 안 먹는다

### 증상
- `docker` 명령을 찾을 수 없음
- Docker Desktop이 실행 안 됨

### 점검
- [ ] Docker Desktop 실행 여부
- [ ] 설치 후 재부팅 여부
- [ ] PATH 문제 여부

---

## 문제 2. Docker Desktop은 켜졌는데 engine이 안 올라온다

### 점검
- [ ] WSL2 설치 여부
- [ ] BIOS 가상화 활성화 여부
- [ ] Windows 기능(Hyper-V/Virtual Machine Platform) 확인

---

## 문제 3. DB 포트 충돌

### 증상
- `5433` 포트를 바인딩할 수 없다고 나옴

### 해결 방향
- [ ] 기존 로컬 PostgreSQL 서비스 중지
- [ ] compose에서 다른 포트로 변경
- [ ] `.env.dev`의 `DB_PORT`와 함께 맞춤

---

## 문제 4. `pip install -r requirements.txt` 실패

### 점검
- [ ] Python 버전이 프로젝트와 호환되는지
- [ ] 가상환경 활성화 여부
- [ ] 빌드 도구 누락 여부
- [ ] 사내망/프록시 문제 여부

---

## 문제 5. `python manage.py check`에서 환경변수 오류

### 점검
- [ ] `.env.dev` 파일 존재 여부
- [ ] 파일명 오타 여부
- [ ] settings가 읽는 env 파일 경로와 일치하는지

---

## 문제 6. `migrate` 시 운영 DB에 붙을까 걱정된다

### 대응
- [ ] `DB_NAME`, `DB_HOST`, `DB_PORT` 재확인
- [ ] 개발 포트(예: 5433) 사용 여부 확인
- [ ] 필요 시 `python manage.py shell`로 connection settings 확인

---

## 문제 7. 로그인은 되는데 CSS/JS가 깨진다

### 점검
- [ ] Network 탭에서 정적파일 404 확인
- [ ] 앱별 CSS 경로 확인
- [ ] `base.html`에서 정적파일 로딩 구조 확인

---

## 문제 8. Celery worker가 바로 죽는다

### 점검
- [ ] Redis 접속 가능 여부
- [ ] import 에러 로그 확인
- [ ] `.env.dev`의 `CELERY_*` 값 확인
- [ ] compose의 command가 팀 표준과 일치하는지 확인

---

# 37. 신규 팀원용 권장 실행 순서 요약

아래 순서만 따라도 대부분 구축됩니다.

## Step-by-step
- [ ] Git 설치
- [ ] Docker Desktop 설치
- [ ] Python 설치
- [ ] VS Code 설치
- [ ] 저장소 clone
- [ ] `.env.dev.example` 복사하여 `.env.dev` 생성
- [ ] `docker compose -f docker-compose.dev.yml up -d db redis`
- [ ] `python -m venv venv`
- [ ] `venv\Scripts\activate`
- [ ] `pip install -r requirements.txt`
- [ ] `python manage.py check`
- [ ] `python manage.py migrate`
- [ ] `python manage.py runserver`
- [ ] 브라우저에서 접속/로그인 확인
- [ ] 필요 시 `celery`도 Docker로 기동

---

# 38. 팀 표준 운영 수칙

## 반드시 지킬 것
- [ ] 운영용 `.env.prod`를 개발 PC에서 사용하지 않는다.
- [ ] 운영 DB 접속정보를 개발용 파일에 넣지 않는다.
- [ ] Docker 실행 전후 `docker compose ps`와 로그를 확인한다.
- [ ] `migrate` 전에는 연결 대상 DB를 반드시 재확인한다.
- [ ] 작업은 개인 브랜치에서 시작한다.

---

# 39. 배포 전 최종 검증 방식

평소에는 로컬 `runserver` 병행 방식을 쓰되, 배포 전에는 운영과 유사하게 한 번 더 검증하는 것이 좋습니다.

## 권장 흐름
- 일상 개발: `db`, `redis`, 필요 시 `celery`만 Docker
- 배포 전: `web`까지 포함해 전체 compose 실행 후 smoke test

## 예시

```powershell
docker compose -f docker-compose.dev.yml --profile worker --profile web up -d --build
```

이후 주요 기능을 간단히 점검합니다.

---

# 40. 신규 팀원 인수인계 시 함께 전달하면 좋은 것

## 함께 전달 권장
- [ ] `.env.dev.example`
- [ ] 개발용 Dockerfile / compose 파일
- [ ] 테스트 계정 정보
- [ ] DB 초기화 또는 샘플 데이터 가이드
- [ ] 브랜치 전략 문서
- [ ] 자주 쓰는 명령어 모음
- [ ] 장애 시 문의할 담당자

---

# 41. 자주 쓰는 명령어 모음

## Docker

```powershell
docker compose -f docker-compose.dev.yml up -d db redis
docker compose -f docker-compose.dev.yml --profile worker up -d celery
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml logs db
docker compose -f docker-compose.dev.yml logs redis
docker compose -f docker-compose.dev.yml logs -f celery
docker compose -f docker-compose.dev.yml down
```

## Python / Django

```powershell
venv\Scripts\activate
pip install -r requirements.txt
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Git

```powershell
git status
git pull
git checkout -b feature/your-branch-name
git add .
git commit -m "init dev environment"
git push -u origin feature/your-branch-name
```

---

# 42. 최종 완료 기준 (Definition of Ready)

아래 항목이 모두 체크되면 신규 팀원의 개발환경 구축은 완료된 것입니다.

## 최종 완료 체크리스트
- [ ] Git 설치 완료
- [ ] Docker Desktop 설치 및 실행 확인 완료
- [ ] Python 설치 완료
- [ ] VS Code 설치 완료
- [ ] 저장소 clone 완료
- [ ] `.env.dev` 생성 완료
- [ ] `db`, `redis` Docker 실행 완료
- [ ] 가상환경 생성 및 패키지 설치 완료
- [ ] `python manage.py check` 통과
- [ ] `python manage.py migrate` 완료
- [ ] `python manage.py runserver` 접속 성공
- [ ] 로그인 확인 완료
- [ ] 주요 페이지 최소 검증 완료
- [ ] 필요 시 Celery 실행 및 로그 확인 완료

---

# 43. 팀원에게 마지막으로 꼭 강조할 것

신규 팀원에게는 아래 3가지를 반드시 강조하는 것이 좋습니다.

## 1) 운영 DB와 개발 DB를 절대 혼동하지 말 것
`django_ma`는 내부 업무지원 성격이 강하므로, 잘못된 DB 연결은 위험합니다.

## 2) 인프라는 Docker로, 웹은 우선 로컬로
처음부터 모든 것을 컨테이너로 돌리기보다, 익숙한 `runserver` 방식과 병행하는 것이 안정적입니다.

## 3) 문제 생기면 가장 먼저 로그를 볼 것
- Django 터미널 로그
- Docker compose logs
- 브라우저 개발자도구 Network/Console

이 3개만 잘 봐도 대부분의 원인을 찾을 수 있습니다.

---

# 44. 부록: 신규 팀원 빠른 시작용 초압축 버전

아주 빠르게 시작해야 할 경우 아래만 먼저 진행해도 됩니다.

```powershell
# 1) 저장소 받기
cd C:\workspace
git clone <저장소_URL>
cd django_ma

# 2) env 파일 준비
Copy-Item .env.dev.example .env.dev

# 3) Docker로 DB/Redis 실행
docker compose -f docker-compose.dev.yml up -d db redis

# 4) Python 가상환경
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 5) Django 실행
python manage.py check
python manage.py migrate
python manage.py runserver
```

접속:

```text
http://127.0.0.1:8000/
```

---

이 문서는 `django_ma`의 개발환경을 신규 팀원 PC에 안정적으로 재현하기 위한 기본 체크리스트입니다.  
실제 팀 운영에서는 여기에 **저장소 URL**, **브랜치 전략**, **테스트 계정**, **초기 데이터 로드 절차**를 추가해 최종 버전으로 관리하는 것을 권장합니다.
