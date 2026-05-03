# django_ma/board/management/commands/sync_kr_holidays.py
"""
대한민국 공휴일 수동 동기화 command.

사용 예:
  python manage.py sync_kr_holidays --year 2026
  python manage.py sync_kr_holidays --from-year 2025 --to-year 2028
  python manage.py sync_kr_holidays --window
  python manage.py sync_kr_holidays --year 2026 --dry-run
  python manage.py sync_kr_holidays --year 2026 --force
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from board.services.holidays import (
    HolidaySyncError,
    get_sync_window_years,
    sync_kr_holidays_for_year,
)


class Command(BaseCommand):
    help = "대한민국 공휴일 API 데이터를 KrHoliday DB 캐시에 동기화합니다."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, help="특정 연도만 동기화합니다.")
        parser.add_argument("--from-year", type=int, dest="from_year", help="동기화 시작 연도")
        parser.add_argument("--to-year", type=int, dest="to_year", help="동기화 종료 연도")
        parser.add_argument("--window", action="store_true", help="settings 기준 기본 window를 동기화합니다.")
        parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 API 응답/정규화 결과만 확인합니다.")
        parser.add_argument("--force", action="store_true", help="lock 및 manual/override 보호를 무시하고 덮어씁니다.")

    def handle(self, *args, **options):
        year = options.get("year")
        from_year = options.get("from_year")
        to_year = options.get("to_year")
        use_window = bool(options.get("window"))
        dry_run = bool(options.get("dry_run"))
        force = bool(options.get("force"))

        years = self._resolve_years(
            year=year,
            from_year=from_year,
            to_year=to_year,
            use_window=use_window,
        )

        self.stdout.write(self.style.NOTICE(f"대상 연도: {', '.join(map(str, years))}"))

        has_error = False

        for y in years:
            try:
                result = sync_kr_holidays_for_year(
                    y,
                    dry_run=dry_run,
                    force=force,
                )
                self.stdout.write(self.style.SUCCESS(f"[{y}] {result}"))
            except HolidaySyncError as exc:
                has_error = True
                self.stderr.write(self.style.ERROR(f"[{y}] 동기화 실패: {exc}"))
            except Exception as exc:
                has_error = True
                self.stderr.write(self.style.ERROR(f"[{y}] 예상치 못한 오류: {exc}"))

        if has_error:
            raise CommandError("일부 연도 동기화에 실패했습니다.")

    def _resolve_years(
        self,
        *,
        year: int | None,
        from_year: int | None,
        to_year: int | None,
        use_window: bool,
    ) -> list[int]:
        if year:
            return [year]

        if from_year or to_year:
            if not from_year or not to_year:
                raise CommandError("--from-year와 --to-year는 함께 지정해야 합니다.")
            if from_year > to_year:
                raise CommandError("--from-year는 --to-year보다 클 수 없습니다.")
            return list(range(from_year, to_year + 1))

        if use_window:
            return get_sync_window_years()

        raise CommandError("--year, --from-year/--to-year, --window 중 하나를 지정해야 합니다.")