# partner/services/grades.py
from __future__ import annotations

from typing import Tuple

from accounts.models import CustomUser
from partner.models import SubAdminTemp
from partner.views.utils import to_str


def ensure_subadmin_temp_for_users(users_qs) -> None:
    """leader 사용자 중 SubAdminTemp가 없는 경우 최소필드로 자동 생성.
    team_a/b/c, position은 건드리지 않음 (NULL 유지).
    """
    user_ids = list(users_qs.values_list("id", flat=True))
    if not user_ids:
        return

    existing_ids = set(
        SubAdminTemp.objects.filter(user_id__in=user_ids).values_list("user_id", flat=True)
    )
    missing_ids = [uid for uid in user_ids if uid not in existing_ids]
    if not missing_ids:
        return

    missing_users = (
        CustomUser.objects.filter(id__in=missing_ids)
        .only("id", "name", "part", "branch", "grade")
    )

    SubAdminTemp.objects.bulk_create(
        [
            SubAdminTemp(
                user=u,
                name=to_str(u.name) or "-",
                part=to_str(u.part) or "-",
                branch=to_str(u.branch) or "-",
                grade="leader",
                level="-",
            )
            for u in missing_users
        ],
        ignore_conflicts=True,
    )


def process_grades_excel(df, user) -> Tuple[int, int]:
    """엑셀 DataFrame에서 SubAdminTemp 팀/직급 최신화.
    Returns (created, updated).
    정책:
      - team_a/b/c, position: 업로드값으로 반영
      - level: 기존값 유지 (없으면 "-")
      - grade: 기존값 유지 (비어있으면 CustomUser.grade로 채움)
      - name/part/branch: CustomUser 기준 동기화
    """
    # 1. DataFrame에서 (user_id → row) 매핑 추출
    row_data: dict[str, object] = {}
    for _, row in df.iterrows():
        user_id = to_str(row.get("사번"))
        if user_id:
            row_data[user_id] = row

    if not row_data:
        return 0, 0

    # 2. CustomUser 일괄 조회
    cu_map: dict[str, CustomUser] = {
        str(u.id): u
        for u in CustomUser.objects.filter(id__in=list(row_data.keys()))
        .only("id", "name", "part", "branch", "grade")
    }

    valid_user_ids = [uid for uid in row_data if uid in cu_map]
    if not valid_user_ids:
        return 0, 0

    # 3. 기존 SubAdminTemp 일괄 조회
    sa_map: dict[str, SubAdminTemp] = {
        str(sa.user_id): sa
        for sa in SubAdminTemp.objects.filter(
            user_id__in=[cu_map[uid].id for uid in valid_user_ids]
        )
    }

    # 4. 생성/수정 목록 분리
    to_create: list[SubAdminTemp] = []
    to_update: list[SubAdminTemp] = []

    for user_id in valid_user_ids:
        cu = cu_map[user_id]
        row = row_data[user_id]

        team_a   = to_str(row.get("팀A"))   or "-"
        team_b   = to_str(row.get("팀B"))   or "-"
        team_c   = to_str(row.get("팀C"))   or "-"
        position = to_str(row.get("직급"))  or "-"

        sa = sa_map.get(str(cu.id))
        if sa is None:
            to_create.append(
                SubAdminTemp(
                    user=cu,
                    name=to_str(cu.name)   or "-",
                    part=to_str(cu.part)   or "-",
                    branch=to_str(cu.branch) or "-",
                    grade=to_str(cu.grade) or "basic",
                    level="-",
                    team_a=team_a,
                    team_b=team_b,
                    team_c=team_c,
                    position=position,
                )
            )
        else:
            sa.name     = to_str(cu.name)   or "-"
            sa.part     = to_str(cu.part)   or "-"
            sa.branch   = to_str(cu.branch) or "-"
            sa.team_a   = team_a
            sa.team_b   = team_b
            sa.team_c   = team_c
            sa.position = position
            if not to_str(getattr(sa, "grade", "")):
                sa.grade = to_str(cu.grade) or "basic"
            if not to_str(getattr(sa, "level", "")):
                sa.level = "-"
            to_update.append(sa)

    created = len(to_create)
    updated = len(to_update)

    if to_create:
        SubAdminTemp.objects.bulk_create(to_create, ignore_conflicts=True)

    if to_update:
        SubAdminTemp.objects.bulk_update(
            to_update,
            ["name", "part", "branch", "team_a", "team_b", "team_c", "position", "grade", "level"],
            batch_size=500,
        )

    return created, updated
