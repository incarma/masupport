# django_ma/partner/management/commands/sync_subadmin_temp.py
from django.core.management.base import BaseCommand
from accounts.models import CustomUser
from partner.models import SubAdminTemp

class Command(BaseCommand):
    help = "SubAdminTemp 테이블을 CustomUser (sub_admin 등급 기준)과 동기화"

    def handle(self, *args, **options):
        users = CustomUser.objects.filter(grade="leader")
        created, updated, deleted = 0, 0, 0

        # ✅ 1️⃣ 필요 사용자 추가/갱신
        for cu in users:
            obj, is_created = SubAdminTemp.objects.update_or_create(
                user=cu,
                defaults={
                    "name": cu.name,
                    "part": cu.part,
                    "branch": cu.branch,
                    "grade": cu.grade,
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1

        # ✅ 2️⃣ sub_admin이 아닌 사용자는 정리
        invalid_temps = SubAdminTemp.objects.exclude(user__grade="leader")
        deleted = invalid_temps.count()
        invalid_temps.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ SubAdminTemp 동기화 완료 — 신규 {created}건, 수정 {updated}건, 삭제 {deleted}건"
            )
        )