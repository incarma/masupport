"""
Celery beat_schedule 'task' 이름과 @shared_task(name=) 등록명 불일치 탐지.
celery_check.sh에서 호출: python scripts/harness/_celery_check.py
"""
import io
import re
import sys
from pathlib import Path

# Windows CP949 터미널 대응: stdout을 UTF-8로 재래핑
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(".")

OK = "[OK]"
NG = "[NG]"

# ── 1. beat_schedule에서 "task" 값 추출 ─────────────────────────────────────
celery_file = ROOT / "web_ma" / "celery.py"
if not celery_file.exists():
    print(f"{NG} web_ma/celery.py 파일을 찾을 수 없습니다.")
    sys.exit(1)

celery_src = celery_file.read_text(encoding="utf-8")

beat_tasks = {}
entry_pattern = re.compile(
    r'"([^"]+)"\s*:\s*\{[^}]*?"task"\s*:\s*"([^"]+)"',
    re.DOTALL,
)
for m in entry_pattern.finditer(celery_src):
    beat_tasks[m.group(1)] = m.group(2)

if not beat_tasks:
    print(f"[WARN] beat_schedule에서 task 항목을 찾지 못했습니다.")
    sys.exit(0)

print(f"beat_schedule 등록 task ({len(beat_tasks)}건):")
for entry, task in beat_tasks.items():
    print(f"  [{entry}] -> {task}")
print()

# ── 2. @shared_task(name=) 등록명 추출 ──────────────────────────────────────
# task.py (단수), tasks.py (복수), tasks/__init__.py, tasks/**/*.py 모두 탐색
registered_tasks = {}

glob_patterns = [
    "**/task.py",           # board/task.py (단수)
    "**/tasks.py",          # 앱/tasks.py (복수)
    "**/tasks/__init__.py", # 앱/tasks/__init__.py
    "**/tasks/**/*.py",     # 앱/tasks/하위/*.py
]

task_files = []
for pat in glob_patterns:
    task_files.extend(ROOT.glob(pat))

# 중복 제거, migrations/__pycache__ 제외
EXCLUDE_PARTS = {"migrations", "__pycache__", "venv", ".venv", "node_modules", "site-packages"}
task_files = [
    f for f in dict.fromkeys(task_files)
    if not any(p in EXCLUDE_PARTS for p in f.parts)
]

shared_task_pattern = re.compile(
    r'@(?:shared_task|app\.task)\s*\([^)]*?name\s*=\s*["\']([^"\']+)["\']'
)

for fpath in task_files:
    try:
        src = fpath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for m in shared_task_pattern.finditer(src):
        name = m.group(1)
        lineno = src[: m.start()].count("\n") + 1
        rel = str(fpath).replace("\\", "/").lstrip("./")
        registered_tasks[name] = f"{rel}:{lineno}"

print(f"@shared_task(name=) 등록 태스크 ({len(registered_tasks)}건):")
for name, loc in registered_tasks.items():
    print(f"  {name}  <- {loc}")
print()

# ── 3. beat_schedule에 있는 task가 @shared_task에 없는 경우 탐지 ─────────────
mismatches = [
    (entry, task)
    for entry, task in beat_tasks.items()
    if task not in registered_tasks
]

# ── 4. 결과 출력 ─────────────────────────────────────────────────────────────
print("========================================")
if not mismatches:
    print(f"{OK} Celery task 이름 점검 통과")
    sys.exit(0)
else:
    print(f"{NG} beat_schedule <-> @shared_task(name=) 불일치 {len(mismatches)}건")
    print()
    for entry_name, task in mismatches:
        print(f"  [불일치] beat_schedule 항목: '{entry_name}'")
        print(f"           task 값:             '{task}'")
        print(f"           -> @shared_task(name='{task}') 등록 없음")
        print()
    print("  힌트: celery -A web_ma inspect registered 로 실제 등록명 확인")
    sys.exit(1)
