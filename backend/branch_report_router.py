
from fastapi import APIRouter, HTTPException, Response, Query
import pandas as pd
from io import BytesIO
from calendar import month_name
import re
from typing import Any, Dict

router = APIRouter(prefix="/branch-disbursement", tags=["Branch Disbursement"])

# NOTE:
# This module is self-contained. Drop it into backend/ and then add in main.py:
#   from branch_report_router import router as branch_router
#   app.include_router(branch_router)
#
# It expects the same Google Sheet CSV schema you already use: at minimum
# columns: date, branch, disbursement and either loan_type or enterprise flag.
# If your columns are named differently, adjust the column map in _normalize().

SHEET_CSV_URL = None        # If None, caller must provide a DataFrame via dependency.
CACHE_GETTER = None         # Optionally set to a callable returning the live DataFrame.

def set_sheet_url(url: str):
    global SHEET_CSV_URL; SHEET_CSV_URL = url

def set_cache_getter(f):
    global CACHE_GETTER; CACHE_GETTER = f

def _fetch_df() -> pd.DataFrame:
    if CACHE_GETTER is not None:
        return CACHE_GETTER()
    if not SHEET_CSV_URL:
        raise RuntimeError("SHEET_CSV_URL not configured; call set_sheet_url() or set_cache_getter().")
    import requests
    import io
    r = requests.get(SHEET_CSV_URL, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))
    return df

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    # Try best-effort column mapping
    cols = {c.lower().strip(): c for c in df.columns}
    def pick(*cands):
        for c in cands:
            if c in cols: return cols[c]
        return None

    date_col = pick("date")
    branch_col = pick("branch","branch_name")
    disb_col = pick("disbursement","loan_disbursement","amount","disburse")
    loan_type_col = pick("loan_type","type","enterprise_flag","enterprise","is_enterprise","category")

    need = [date_col, branch_col, disb_col]
    if any(x is None for x in need):
        raise HTTPException(400, "Missing required columns (need: date, branch, disbursement).")

    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], errors="coerce"),
        "branch": df[branch_col].astype(str).fillna("").str.strip(),
        "disbursement": pd.to_numeric(df[disb_col], errors="coerce").fillna(0.0),
    })

    # classify enterprise vs non-enterprise
    ent = pd.Series(["Unknown"]*len(df))
    if loan_type_col:
        s = df[loan_type_col].astype(str).str.lower()
        ent = ent.where(~s.str.contains(r"^\s*$", na=True), "Unknown")
        ent = s.apply(lambda v: "Enterprise" if any(k in v for k in ["enterprise","enterp","ent"]) else ("Non-Enterprise" if any(k in v for k in ["non","micro","agri","general"]) else "Unknown"))
    out["segment"] = ent
    return out.dropna(subset=["date"])

def _month_label(value: str) -> str:
    # Accepts "YYYY-MM" or "YYYY-MM-DD"
    m = re.match(r"^(\d{4})-(\d{2})(?:-\d{2})?$", value)
    if not m: return value
    y, mm = int(m.group(1)), int(m.group(2))
    return f"{month_name[mm]} {y}"

@router.get("")
def get_branch_disbursement(month: str = Query(..., description="YYYY-MM"),
                             branch: str | None = None):
    df = _normalize(_fetch_df())
    # month filter
    target = pd.Period(month, freq="M")
    mdf = df[df["date"].dt.to_period("M") == target]
    if branch:
        mdf = mdf[mdf["branch"].str.contains(branch, case=False, na=False)]

    # aggregate by branch & segment
    agg = (mdf.groupby(["branch","segment"], as_index=False)
              .agg(disbursement=("disbursement","sum")))
    # total per branch
    totals = agg.groupby("branch", as_index=False).agg(total=("disbursement","sum"))
    # Pivot for table view (Branch | Enterprise | Non-Enterprise | Unknown | Total)
    pivot = agg.pivot_table(index="branch", columns="segment", values="disbursement", aggfunc="sum", fill_value=0.0).reset_index()
    for col in ["Enterprise","Non-Enterprise","Unknown"]:
        if col not in pivot.columns: pivot[col] = 0.0
    pivot["Total"] = pivot[["Enterprise","Non-Enterprise","Unknown"]].sum(axis=1)
    # sort by Total desc
    pivot = pivot.sort_values("Total", ascending=False).reset_index(drop=True)
    # No SL No in totals/rows by request: we won't create a serial column.
    header = {"title": f"Branch-wise Loan Disbursement — {_month_label(month)}"}
    grand = float(pivot["Total"].sum()) if len(pivot) else 0.0
    return {"header": header, "rows": pivot.to_dict(orient="records"), "grand_total": grand}

@router.get("/export/excel")
def export_excel(month: str = Query(..., description="YYYY-MM"),
                 branch: str | None = None):
    import xlsxwriter
    df = _normalize(_fetch_df())
    target = pd.Period(month, freq="M")
    mdf = df[df["date"].dt.to_period("M") == target]
    if branch:
        mdf = mdf[mdf["branch"].str.contains(branch, case=False, na=False)]

    # aggregate
    agg = (mdf.groupby(["branch","segment"], as_index=False)
              .agg(disbursement=("disbursement","sum")))
    pivot = agg.pivot_table(index="branch", columns="segment", values="disbursement", aggfunc="sum", fill_value=0.0).reset_index()
    for col in ["Enterprise","Non-Enterprise","Unknown"]:
        if col not in pivot.columns: pivot[col] = 0.0
    pivot["Total"] = pivot[["Enterprise","Non-Enterprise","Unknown"]].sum(axis=1)
    pivot = pivot.sort_values(["branch"]).reset_index(drop=True)

    # Build nicely formatted workbook with merged branch names for consecutive duplicates (not needed after sort by branch)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pivot.to_excel(writer, index=False, sheet_name="Branch Disbursement")
        wb = writer.book
        ws = writer.sheets["Branch Disbursement"]

        title = f"Branch-wise Loan Disbursement — {_month_label(month)}"
        # Insert title row
        ws.write(0, 0, title, wb.add_format({"bold": True, "font_size": 14}))

        # Shift table down by 2 rows visually (already wrote at row 0 by pandas),
        # so we'll rewrite with more control:
    # Rebuild from scratch to control layout
    buf = BytesIO()
    with xlsxwriter.Workbook(buf) as wb:
        ws = wb.add_worksheet("Branch Disbursement")
        f_title = wb.add_format({"bold": True, "font_size": 14})
        f_hdr = wb.add_format({"bold": True, "bg_color": "#E8F3FF", "bottom":1})
        f_num = wb.add_format({"num_format": "#,##0"})
        f_total = wb.add_format({"bold": True, "num_format": "#,##0", "top":1})
        f_seg_lbl = wb.add_format({"italic": True, "align": "center"})
        # Title
        ws.write(0, 0, title, f_title)

        # Header row at row 2
        headers = ["Branch","Enterprise","Non-Enterprise","Unknown","Total"]
        for ci, h in enumerate(headers):
            ws.write(2, ci, h, f_hdr)

        # Sort by branch to group merging
        pivot = pivot.sort_values("branch").reset_index(drop=True)

        # Write rows, track merge ranges for branch
        r0 = 3
        row = r0
        i = 0
        while i < len(pivot):
            branch = pivot.loc[i, "branch"]
            j = i
            # Find consecutive rows with the same branch (after grouping, there should be 1 per branch; still keeping logic)
            while j+1 < len(pivot) and pivot.loc[j+1, "branch"] == branch:
                j += 1
            # write rows i..j
            for k in range(i, j+1):
                ws.write(row, 1, pivot.loc[k, "Enterprise"], f_num)
                ws.write(row, 2, pivot.loc[k, "Non-Enterprise"], f_num)
                ws.write(row, 3, pivot.loc[k, "Unknown"], f_num)
                ws.write(row, 4, pivot.loc[k, "Total"], f_num)
                row += 1
            # merge branch name across those rows
            ws.merge_range(r0 + (row - r0 - (j - i + 1)), 0, row-1-1, 0, branch, None) if (j-i+1) > 1 else ws.write(row-1-1, 0, branch)
            i = j + 1

        # Column widths
        ws.set_column(0, 0, 24)  # Branch
        ws.set_column(1, 4, 16)  # numbers

        # Grand total (single line only, no extra "sum below grand total")
        grand = float(pivot["Total"].sum()) if len(pivot) else 0.0
        ws.write(row+1, 3, "Grand Total", f_total)
        ws.write(row+1, 4, grand, f_total)

        # Visualization: simple legend text under totals
        ws.write(row+3, 1, "Enterprise", f_seg_lbl)
        ws.write(row+3, 2, "Non-Enterprise", f_seg_lbl)

    data = buf.getvalue()
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="branch_disbursement.xlsx"'})
