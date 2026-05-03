"""
CSS 스코프 루트 밖 규칙 탐지.
css_scope_check.sh에서 호출: python scripts/harness/_css_scope_check.py
"""
import io
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(".")
OK = "[OK]"
NG = "[NG]"
VIOLATIONS = []


def split_selectors(sel_text):
    """
    콤마로 구분된 CSS 선택자를 분리한다.
    :is(), :not(), :where() 등 괄호 안의 콤마는 분리하지 않는다.
    """
    parts = []
    depth = 0
    current = []
    for ch in sel_text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(ch)
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def get_top_level_selectors(css_text):
    """
    CSS depth=0 최상위 선택자를 추출한다.
    @at-rules 및 주석은 제외한다.
    """
    css_clean = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)

    selectors = []
    depth = 0
    current = []
    line = 1
    sel_start = 1

    for ch in css_clean:
        if ch == "\n":
            line += 1
        if ch == "{":
            if depth == 0:
                sel = "".join(current).strip()
                if sel and not sel.startswith("@"):
                    selectors.append((sel_start, sel))
            depth += 1
            current = []
            sel_start = line
        elif ch == "}":
            depth = max(0, depth - 1)
            current = []
            sel_start = line + 1
        else:
            if depth == 0:
                current.append(ch)

    return selectors


def check_scope(filepath, scope_prefixes, rule_id, description):
    fpath = ROOT / filepath
    if not fpath.exists():
        print(f"[SKIP] [{rule_id}] {filepath} 없음")
        return []

    text = fpath.read_text(encoding="utf-8", errors="ignore")
    top = get_top_level_selectors(text)

    violations = []
    for lineno, sel in top:
        parts = split_selectors(sel)
        for part in parts:
            if not part:
                continue
            # 스코프 prefix 중 하나로 시작하는 부분이 있으면 OK
            if any(part.startswith(p) for p in scope_prefixes):
                break
        else:
            # 어떤 부분도 scope_prefix로 시작하지 않으면 위반
            violations.append((filepath, lineno, sel.replace("\n", " ").strip()))

    if violations:
        print(f"{NG} [{rule_id}] {description}")
        for fp, ln, s in violations:
            print(f"     {fp}:{ln}: {s[:120]}")
        print()
    else:
        scope_repr = " / ".join(scope_prefixes[:3])
        print(f"{OK} {filepath}: '{scope_repr}' 스코프 정상")

    return violations


def check_forbidden(filepath, patterns, rule_id, description):
    fpath = ROOT / filepath
    if not fpath.exists():
        print(f"[SKIP] [{rule_id}] {filepath} 없음")
        return []

    text = fpath.read_text(encoding="utf-8", errors="ignore")
    violations = []
    for i, line in enumerate(text.splitlines(), 1):
        for pat in patterns:
            if re.search(pat, line):
                violations.append((filepath, i, line.strip()))
                break

    if violations:
        print(f"{NG} [{rule_id}] {description}")
        for fp, ln, ln_text in violations:
            print(f"     {fp}:{ln}: {ln_text}")
        print()
    else:
        print(f"{OK} {filepath}: 금지 패턴 없음")

    return violations


print("========================================")
print(" CSS 스코프 위반 탐지")
print("========================================")
print()

# ── 1. board.css: 모든 최상위 규칙이 .board-scope 하위여야 함 ────────────────
v = check_scope(
    "static/css/apps/board.css",
    [".board-scope", "#board-"],
    "CSS-SCOPE-01",
    "board.css: .board-scope 밖 최상위 규칙 (board.css는 .board-scope 전용)",
)
VIOLATIONS.extend(v)

# ── 2. partner.css: 모든 최상위 규칙이 파트너 앱 스코프 하위여야 함 ─────────
# #manage-*, #partner-*, #esign-confirm, .partner-*, .modal-*, #tableCheck*, #grade-*
partner_scopes = [
    "#manage-",
    "#partner-",
    "#esign-confirm",
    ".partner-",
    "#tableCheckModal",
    "#grade-",
    "#structure-",
    "#rate-",
    "#ratetable-",
    "#subadmin-",
    "#joinform-",
]
v = check_scope(
    "static/css/apps/partner.css",
    partner_scopes,
    "CSS-SCOPE-02",
    "partner.css: 파트너 앱 스코프 밖 최상위 규칙 (스코프 루트 ID/클래스 하위로 이동 필요)",
)
VIOLATIONS.extend(v)

# ── 3. base.css: 앱 전용 클래스/ID 존재 금지 ────────────────────────────────
v = check_forbidden(
    "static/css/base.css",
    [
        r"\.board-[a-z]",
        r"#manage-[a-z]",
        r"#partner-[a-z]",
        r"#dash-[a-z]",
        r"#commission-[a-z]",
        r"#manual-[a-z]",
        r"\.board-scope",
    ],
    "CSS-SCOPE-03",
    "base.css: 앱 전용 클래스/ID 존재 (앱 전용 CSS로 이동 필요)",
)
VIOLATIONS.extend(v)

# ── 4. apps/*.css: :root 전역 변수 선언 금지 ────────────────────────────────
print()
apps_dir = ROOT / "static" / "css" / "apps"
root_violations = []
if apps_dir.exists():
    for css_file in sorted(apps_dir.glob("*.css")):
        text = css_file.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if re.match(r"^\s*:root\s*\{", line):
                root_violations.append((str(css_file).replace("\\", "/"), i, line.strip()))

if root_violations:
    print(f"{NG} [CSS-SCOPE-04] apps/*.css: :root 전역 변수 선언 (앱 루트 ID 하위로 이동 필요)")
    for fp, ln, ln_text in root_violations:
        print(f"     {fp}:{ln}: {ln_text}")
    print()
    VIOLATIONS.extend(root_violations)
else:
    print(f"{OK} apps/*.css: :root 전역 변수 선언 없음")

# ── 결과 ─────────────────────────────────────────────────────────────────────
print()
print("========================================")
if not VIOLATIONS:
    print(f"{OK} CSS 스코프 점검 통과")
    sys.exit(0)
else:
    print(f"{NG} CSS 스코프 위반 {len(VIOLATIONS)}건 — docs/harness/QUALITY_RULES.md 확인 필요")
    sys.exit(1)
