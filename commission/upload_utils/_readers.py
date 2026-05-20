# django_ma/commission/upload_utils/_readers.py

from __future__ import annotations

"""
commission 업로드 파일 reader SSOT.

지원 순서:
1. HTML table로 내려온 Excel 유사 파일
2. xlsx/xlsm 계열(openpyxl)
3. xls OLE2 계열(xlrd 필요)
4. csv/tsv/semicolon 텍스트 fallback

핸들러는 파일 포맷을 직접 판별하지 않고 이 모듈을 경유한다.
"""

import io
import os
from html.parser import HTMLParser

import pandas as pd

# =========================================================
# Excel readers (xlsx/xls/html/tsv/csv)
# =========================================================
def _decode_bytes_best_effort(raw: bytes) -> str:
    """한국어 엑셀/CSV에서 자주 쓰이는 인코딩 순서로 최대한 텍스트를 복원한다."""
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_first_html_table(file_path: str) -> pd.DataFrame:
    """
    HTML table 형식으로 내려온 Excel 유사 파일을 DataFrame으로 읽는다.

    일부 내부 시스템은 확장자가 .xls여도 실제 내용은 HTML table이다.
    이 경우 pandas read_excel보다 HTMLParser 기반 파싱이 안정적이다.
    """
    with open(file_path, "rb") as f:
        raw = f.read()
    text = _decode_bytes_best_effort(raw)

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_table = False
            self.in_tr = False
            self.in_cell = False
            self.table_found = False
            self.rows = []
            self.cur_row = []
            self.cur_cell = []

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag == "table" and not self.table_found:
                self.in_table = True
                self.table_found = True
            elif self.in_table and tag == "tr":
                self.in_tr = True
                self.cur_row = []
            elif self.in_table and self.in_tr and tag in ("td", "th"):
                self.in_cell = True
                self.cur_cell = []

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag == "table" and self.in_table:
                self.in_table = False
            elif tag == "tr" and self.in_tr:
                self.in_tr = False
                if any(c.strip() for c in self.cur_row):
                    self.rows.append(self.cur_row)
            elif tag in ("td", "th") and self.in_cell:
                self.in_cell = False
                cell_text = " ".join("".join(self.cur_cell).split())
                self.cur_row.append(cell_text)

        def handle_data(self, data):
            if self.in_cell and data:
                self.cur_cell.append(data)

    p = TableParser()
    p.feed(text)

    if not p.rows:
        raise ValueError("HTML 테이블을 찾지 못했습니다. (table/tr/td 없음)")

    header = p.rows[0]
    data_rows = p.rows[1:]

    max_len = max(len(header), *(len(r) for r in data_rows)) if data_rows else len(header)
    header = (header + [""] * max_len)[:max_len]
    norm_rows = [(r + [""] * max_len)[:max_len] for r in data_rows]

    df = pd.DataFrame(norm_rows, columns=[str(c).strip() for c in header])

    # 컬럼명 중복 방지
    new_cols, used = [], {}
    for i, c in enumerate(df.columns):
        name = (c or "").strip() or f"COL_{i+1}"
        if name in used:
            used[name] += 1
            name = f"{name}_{used[name]}"
        else:
            used[name] = 1
        new_cols.append(name)
    df.columns = new_cols
    return df


def _read_text_table(file_path: str) -> pd.DataFrame:
    """
    csv/tsv/semicolon 텍스트 테이블을 추정 로딩한다.

    구분자 추정 실패 또는 read_csv 실패 시 한 줄짜리 COL_1 DataFrame으로 fallback한다.
    이 fallback은 업로드 실패 원인 확인용으로 최소 원문을 보존하기 위한 방어다.
    """
    with open(file_path, "rb") as f:
        raw = f.read()
    text = _decode_bytes_best_effort(raw)

    head = text[:5000]
    tab_cnt = head.count("\t")
    comma_cnt = head.count(",")
    semi_cnt = head.count(";")

    if tab_cnt >= max(comma_cnt, semi_cnt) and tab_cnt > 0:
        sep = "\t"
    elif comma_cnt >= semi_cnt and comma_cnt > 0:
        sep = ","
    elif semi_cnt > 0:
        sep = ";"
    else:
        sep = None

    buf = io.StringIO(text)
    try:
        if sep is None:
            return pd.read_csv(buf, engine="python")
        return pd.read_csv(buf, sep=sep, engine="python")
    except Exception:
        return pd.DataFrame({"COL_1": [line for line in text.splitlines() if line.strip()]})


def _read_text_table_matrix(file_path: str, skiprows: int = 0) -> pd.DataFrame:
    """raw matrix 기반 핸들러용 텍스트 reader. header=None 형태를 유지한다."""
    with open(file_path, "rb") as f:
        raw = f.read()
    text = _decode_bytes_best_effort(raw)

    head = text[:5000]
    tab_cnt = head.count("\t")
    comma_cnt = head.count(",")
    semi_cnt = head.count(";")

    if tab_cnt >= max(comma_cnt, semi_cnt) and tab_cnt > 0:
        sep = "\t"
    elif comma_cnt >= semi_cnt and comma_cnt > 0:
        sep = ","
    elif semi_cnt > 0:
        sep = ";"
    else:
        sep = None

    buf = io.StringIO(text)
    if sep is None:
        return pd.read_csv(buf, engine="python", header=None, skiprows=skiprows)
    return pd.read_csv(buf, sep=sep, engine="python", header=None, skiprows=skiprows)


def _read_head_bytes(file_path: str, n: int = 4096) -> bytes:
    """파일 시그니처 판별용 선두 bytes를 읽는다. 실패 시 빈 bytes 반환."""
    try:
        with open(file_path, "rb") as f:
            return f.read(n)
    except Exception:
        return b""


def _is_html_bytes(head: bytes) -> bool:
    """파일 선두부 기준 HTML table 계열 여부를 판별한다."""
    head_l = head.lstrip().lower()
    return head_l.startswith(b"<html") or head_l.startswith(b"<!doctype") or head_l.startswith(b"<table")


def _read_excel_safely(file_path: str, original_name: str = "") -> pd.DataFrame:
    """
    업로드 파일을 안전하게 DataFrame(header=0)로 읽는다.
    - HTML table / xlsx / xls / csv(tsv) 모두 대응
    - 반환 DataFrame은 header=0 기준이다.
    """
    ext = os.path.splitext((original_name or file_path))[1].lower()
    head = _read_head_bytes(file_path)

    if _is_html_bytes(head):
        return _parse_first_html_table(file_path)

    is_zip = head.startswith(b"PK\x03\x04")
    is_ole2 = head.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1")

    if is_zip or ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        return pd.read_excel(file_path, header=0, engine="openpyxl")

    if is_ole2:
        try:
            import xlrd  # noqa: F401
        except Exception:
            raise ValueError(
                "업로드 실패: 현재 서버에 .xls 처리 모듈(xlrd)이 없습니다.\n"
                "엑셀에서 '다른 이름으로 저장' → .xlsx로 저장 후 업로드해주세요."
            )
        return pd.read_excel(file_path, header=0, engine="xlrd")

    return _read_text_table(file_path)


def _read_excel_raw_matrix(
    file_path: str,
    original_name: str,
    skiprows: int,
    header_none: bool = True,
) -> pd.DataFrame:
    """
    업로드 파일을 header=None 형태의 matrix(DataFrame)로 읽는다.
    - HTML table / xlsx / xls / csv(tsv) 모두 대응
    - 반환 DataFrame은 기본적으로 header=None matrix 형태다.
    """
    ext = os.path.splitext((original_name or file_path))[1].lower()
    head = _read_head_bytes(file_path)

    if _is_html_bytes(head):
        df_html = _parse_first_html_table(file_path)
        values = df_html.to_numpy().tolist()
        values = values[skiprows:] if skiprows else values
        return pd.DataFrame(values)

    is_zip = head.startswith(b"PK\x03\x04")
    is_ole2 = head.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1")

    if is_zip or ext in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        return pd.read_excel(
            file_path,
            header=None if header_none else 0,
            skiprows=skiprows,
            engine="openpyxl",
        )

    if is_ole2:
        try:
            import xlrd  # noqa: F401
        except Exception:
            raise ValueError(
                "업로드 실패: 현재 서버에 .xls 처리 모듈(xlrd)이 없습니다.\n"
                "엑셀에서 '다른 이름으로 저장' → .xlsx로 저장 후 업로드해주세요."
            )
        return pd.read_excel(
            file_path,
            header=None if header_none else 0,
            skiprows=skiprows,
            engine="xlrd",
        )

    return _read_text_table_matrix(file_path, skiprows=skiprows)