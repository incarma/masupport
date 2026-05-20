# django_ma/commission/tests.py
from __future__ import annotations

"""
commission app 공통 회귀 방지 테스트.

목적:
- 기능 변화 0 리팩토링 시 핵심 helper 정책이 깨지지 않도록 보호한다.
- upload handler / rate_example normalizer 공통 helper 계약을 고정한다.
- upload_utils / fail token / deposit service / download response 회귀를 방지한다.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase
from openpyxl import Workbook

from accounts.models import CustomUser
from commission.models import DepositOther, DepositSurety
from commission.services.deposit import calc_filtered_totals, calc_keep_totals_all
from commission.services.rate_example_normalizers._common.decimal import (
    decimal_percent_value,
)
from commission.services.rate_example_normalizers._common.excel import (
    build_merged_value_map,
    cell_value_with_merged,
)
from commission.upload_handlers._common import safe_cell_text, upload_result
from commission.upload_utils import (
    EMPTY_LIKE_VALUES,
    _extract_emp7_from_a,
    _is_empty_like,
    _norm_emp_id,
)
from commission.views._excel_export import XLSX_MIME, rows_to_excel_response
from commission.views.downloads import _can_download_fail_payload
from commission.views.utils_fail_excel import FAIL_TTL_SECONDS, store_fail_rows_as_excel


# =============================================================================
# RateExample Decimal helper
# =============================================================================
class RateExampleCommonDecimalTests(SimpleTestCase):
    def test_decimal_percent_value_scales_excel_percent_number_format(self):
        self.assertEqual(
            decimal_percent_value(Decimal("0.7"), number_format="0%"),
            Decimal("70.0"),
        )

    def test_decimal_percent_value_keeps_plain_number(self):
        self.assertEqual(decimal_percent_value("160"), Decimal("160"))

    def test_decimal_percent_value_keeps_percent_text_by_default(self):
        self.assertEqual(decimal_percent_value("0.8%"), Decimal("0.8"))

    def test_decimal_percent_value_can_scale_small_percent_text(self):
        self.assertEqual(
            decimal_percent_value("0.8%", scale_small_percent_text=True),
            Decimal("80.0"),
        )

    def test_decimal_percent_value_returns_none_for_empty(self):
        self.assertIsNone(decimal_percent_value(""))
        self.assertIsNone(decimal_percent_value(None))
        self.assertIsNone(decimal_percent_value("-"))

    def test_decimal_percent_value_keeps_already_scaled_percent(self):
        self.assertEqual(decimal_percent_value("80%"), Decimal("80"))


# =============================================================================
# Upload handler common helper
# =============================================================================
class UploadHandlerCommonTests(SimpleTestCase):
    def test_safe_cell_text_normalizes_empty_like_values(self):
        self.assertEqual(safe_cell_text(None), "")
        self.assertEqual(safe_cell_text("nan"), "")
        self.assertEqual(safe_cell_text("none"), "")
        self.assertEqual(safe_cell_text("-"), "")

    def test_safe_cell_text_strips_normal_values(self):
        self.assertEqual(safe_cell_text("  지급  "), "지급")
        self.assertEqual(safe_cell_text(1234567), "1234567")

    def test_upload_result_contract(self):
        self.assertEqual(
            upload_result(
                inserted_or_updated=3,
                missing_users=2,
                missing_sample=["1000001", "1000002"],
            ),
            {
                "inserted_or_updated": 3,
                "missing_users": 2,
                "missing_sample": ["1000001", "1000002"],
            },
        )

    def test_upload_result_default_contract(self):
        self.assertEqual(
            upload_result(),
            {
                "inserted_or_updated": 0,
                "missing_users": 0,
                "missing_sample": [],
            },
        )

    def test_upload_result_always_returns_list_for_missing_sample(self):
        result = upload_result(inserted_or_updated=1, missing_users=0)
        self.assertIsInstance(result["missing_sample"], list)
        self.assertEqual(result["missing_sample"], [])

    def test_upload_result_preserves_zero_values(self):
        self.assertEqual(
            upload_result(
                inserted_or_updated=0,
                missing_users=0,
                missing_sample=[],
            ),
            {
                "inserted_or_updated": 0,
                "missing_users": 0,
                "missing_sample": [],
            },
        )


# =============================================================================
# Upload utils helper
# =============================================================================
class UploadUtilsConvertTests(SimpleTestCase):
    def test_empty_like_values_are_exported_as_frozenset(self):
        self.assertIsInstance(EMPTY_LIKE_VALUES, frozenset)
        self.assertIn("", EMPTY_LIKE_VALUES)
        self.assertIn("nan", EMPTY_LIKE_VALUES)
        self.assertIn("none", EMPTY_LIKE_VALUES)
        self.assertIn("-", EMPTY_LIKE_VALUES)

    def test_is_empty_like_normalizes_common_empty_values(self):
        self.assertTrue(_is_empty_like(None))
        self.assertTrue(_is_empty_like(""))
        self.assertTrue(_is_empty_like("  "))
        self.assertTrue(_is_empty_like("nan"))
        self.assertTrue(_is_empty_like("None"))
        self.assertTrue(_is_empty_like("-"))
        self.assertFalse(_is_empty_like("0"))
        self.assertFalse(_is_empty_like("1234567"))

    def test_norm_emp_id_keeps_string_pk_policy(self):
        self.assertEqual(_norm_emp_id("1234567.0"), "1234567")
        self.assertEqual(_norm_emp_id(" 1234567 "), "1234567")
        self.assertEqual(_norm_emp_id(1234567), "1234567")
        self.assertEqual(_norm_emp_id(None), "")
        self.assertEqual(_norm_emp_id("nan"), "")
        self.assertEqual(_norm_emp_id("-"), "")

    def test_extract_emp7_from_a_uses_existing_slice_policy(self):
        self.assertEqual(_extract_emp7_from_a("X1234567Z"), "1234567")
        self.assertEqual(_extract_emp7_from_a("ABC7654321X"), "7654321")
        self.assertEqual(_extract_emp7_from_a("1234567"), "")
        self.assertEqual(_extract_emp7_from_a("ABC12X456Z"), "")
        self.assertEqual(_extract_emp7_from_a(None), "")


# =============================================================================
# RateExample Excel helper
# =============================================================================
class RateExampleCommonExcelTests(SimpleTestCase):
    def test_build_merged_value_map_propagates_top_left_value(self):
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "상품명"
        ws.merge_cells("A1:A3")

        merged_map = build_merged_value_map(ws)

        self.assertEqual(merged_map[(1, 1)], "상품명")
        self.assertEqual(merged_map[(2, 1)], "상품명")
        self.assertEqual(merged_map[(3, 1)], "상품명")

    def test_cell_value_with_merged_uses_real_value_first(self):
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "병합값"
        ws.merge_cells("A1:A3")
        ws["B2"] = "실제값"

        merged_map = build_merged_value_map(ws)

        self.assertEqual(cell_value_with_merged(ws, merged_map, 2, 2), "실제값")

    def test_cell_value_with_merged_falls_back_to_merged_map(self):
        wb = Workbook()
        ws = wb.active
        ws["A1"] = "전파값"
        ws.merge_cells("A1:A3")

        merged_map = build_merged_value_map(ws)

        self.assertEqual(cell_value_with_merged(ws, merged_map, 3, 1), "전파값")

    def test_cell_value_with_merged_returns_none_for_plain_empty_cell(self):
        wb = Workbook()
        ws = wb.active

        merged_map = build_merged_value_map(ws)

        self.assertIsNone(cell_value_with_merged(ws, merged_map, 5, 5))


# =============================================================================
# Fail token / Excel response helper
# =============================================================================
class CommissionExcelHelperTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_store_fail_rows_as_excel_returns_cache_token(self):
        token = store_fail_rows_as_excel(
            rows=[
                {"user_id": "1000001", "reason": "사용자 미존재"},
                {"user_id": "1000002", "reason": "스코프 제외"},
            ],
            filename="upload_fail_test.xlsx",
            owner_id="admin01",
        )

        self.assertTrue(token)

        payload = cache.get(f"commission:upload_fail:{token}")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["filename"], "upload_fail_test.xlsx")
        self.assertEqual(payload["owner_id"], "admin01")
        self.assertIsInstance(payload["content"], bytes)
        self.assertGreater(len(payload["content"]), 0)
        self.assertEqual(FAIL_TTL_SECONDS, 60 * 60)

    def test_store_fail_rows_as_excel_returns_empty_for_no_rows(self):
        token = store_fail_rows_as_excel(
            rows=[],
            filename="empty.xlsx",
            owner_id="admin01",
        )
        self.assertEqual(token, "")

    def test_rows_to_excel_response_smoke(self):
        response = rows_to_excel_response(
            rows=[{"user_id": "1000001", "amount": 1234}],
            sheet_name="smoke",
            filename="테스트.xlsx",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_MIME)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("filename*=", response["Content-Disposition"])
        self.assertGreater(len(response.content), 0)


# =============================================================================
# Deposit service
# =============================================================================
class DepositServiceAggregateTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            id="1000001",
            name="테스트",
            password="pw",
            grade="basic",
        )

    def test_calc_filtered_totals(self):
        DepositSurety.objects.create(
            user=self.user,
            product_name="GA개인 보증",
            amount=1000,
            status="유지",
        )
        DepositSurety.objects.create(
            user=self.user,
            product_name="일반 보증",
            amount=2000,
            status="유지",
        )
        DepositOther.objects.create(
            user=self.user,
            product_name="기타",
            product_type="수수료 채권",
            amount=3000,
            status="유지인",
        )
        DepositOther.objects.create(
            user=self.user,
            product_name="기타",
            product_type="일반 채권",
            amount=4000,
            status="유지",
        )

        surety_total, other_total = calc_filtered_totals(self.user.pk)

        self.assertEqual(surety_total, 1000)
        self.assertEqual(other_total, 3000)

    def test_calc_keep_totals_all(self):
        DepositSurety.objects.create(
            user=self.user,
            product_name="GA개인 보증",
            amount=1000,
            status="유지",
        )
        DepositSurety.objects.create(
            user=self.user,
            product_name="GA개인 보증",
            amount=2000,
            status="해지",
        )
        DepositOther.objects.create(
            user=self.user,
            product_name="기타",
            product_type="수수료 채권",
            amount=3000,
            status="유지",
        )
        DepositOther.objects.create(
            user=self.user,
            product_name="기타",
            product_type="수수료 채권",
            amount=4000,
            status="유지인",
        )

        surety_keep_all, other_keep_all = calc_keep_totals_all(self.user.pk)

        self.assertEqual(surety_keep_all, 1000)
        self.assertEqual(other_keep_all, 3000)


# =============================================================================
# Fail download permission helper
# =============================================================================
class FailDownloadPermissionTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.superuser = CustomUser.objects.create_user(
            id="9000001",
            name="관리자",
            password="pw",
            grade="superuser",
            is_superuser=True,
        )
        self.other_superuser = CustomUser.objects.create_user(
            id="9000002",
            name="타관리자",
            password="pw",
            grade="superuser",
            is_superuser=True,
        )
        self.basic = CustomUser.objects.create_user(
            id="1000001",
            name="일반",
            password="pw",
            grade="basic",
        )

    def _request_for(self, user):
        request = self.factory.get("/commission/download/upload-fail/")
        request.user = user
        return request

    def test_owner_superuser_can_download_new_token(self):
        request = self._request_for(self.superuser)

        self.assertTrue(
            _can_download_fail_payload(
                request,
                {"owner_id": str(self.superuser.pk)},
            )
        )

    def test_other_superuser_cannot_download_owner_bound_token(self):
        request = self._request_for(self.other_superuser)

        self.assertFalse(
            _can_download_fail_payload(
                request,
                {"owner_id": str(self.superuser.pk)},
            )
        )

    def test_legacy_token_without_owner_allows_superuser_only(self):
        self.assertTrue(
            _can_download_fail_payload(
                self._request_for(self.superuser),
                {"owner_id": ""},
            )
        )
        self.assertFalse(
            _can_download_fail_payload(
                self._request_for(self.basic),
                {"owner_id": ""},
            )
        )