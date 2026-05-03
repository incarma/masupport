"""
EX-01: except: pass 예외 삼키기 패턴 탐지
quality_lint.sh에서 호출: python scripts/harness/_except_check.py
"""
import io
import os
import re
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SKIP_DIRS = {"migrations", "tests", "__pycache__", ".git", "node_modules"}

violations = []

for dirpath, dirnames, filenames in os.walk("."):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

    for fname in filenames:
        if not fname.endswith(".py"):
            continue
        if fname.startswith("test_") or fname == "conftest.py":
            continue

        fpath = os.path.join(dirpath, fname)
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            continue

        for i, line in enumerate(lines):
            if not re.search(r"^\s*except[^:]*:\s*$", line):
                continue
            if i + 1 >= len(lines):
                continue
            if not re.match(r"^\s*pass\s*$", lines[i + 1]):
                continue
            ctx = "".join(lines[max(0, i - 1): min(len(lines), i + 3)])
            if re.search(r"log(?:ger|_action)|logging\.", ctx):
                continue

            rel = fpath.replace("\\", "/").lstrip("./")
            violations.append(f"{rel}:{i + 1}: {line.rstrip()}")
            violations.append(f"{rel}:{i + 2}: {lines[i + 1].rstrip()}")

if violations:
    print("\n".join(violations))
