# django_ma/commission/upload_utils/_readers.py

from __future__ import annotations

import io
import os
from html.parser import HTMLParser

import pandas as pd

# =========================================================
# Excel readers (xlsx/xls/html/tsv/csv)
# =========================================================
def _decode_bytes_best_effort(raw: bytes) -> str:
    """utf-8/cp949 등으로 최대한 텍스트 복원."""
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_first_html_table(file_path: str) -> pd.DataFrame:
    """엑셀이 HTML 테이블로 내려오는 케이스 대응(첫 table 파싱)."""
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
    """csv/tsv/세미콜론 등 텍스트 테이블 추정 로딩."""
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
    """텍스트 테이블을 header=None 형태의 matrix로 로딩."""
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
    try:
        with open(file_path, "rb") as f:
            return f.read(n)
    except Exception:
        return b""


def _is_html_bytes(head: bytes) -> bool:
    head_l = head.lstrip().lower()
    return head_l.startswith(b"<html") or head_l.startswith(b"<!doctype") or head_l.startswith(b"<table")


def _read_excel_safely(file_path: str, original_name: str = "") -> pd.DataFrame:
    """
    업로드 파일을 안전하게 DataFrame(header=0)로 읽는다.
    - HTML table / xlsx / xls / csv(tsv) 모두 대응
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