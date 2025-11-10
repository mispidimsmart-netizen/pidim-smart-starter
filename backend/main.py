# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd, requests, time
from io import BytesIO, StringIO
from typing import Dict, Any

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRkcagLu_YrYgQxmsO3DnHn90kqALkw9uDByX7UBNRUjaFKKQdE3V-6fm5ZcKGk_A/pub?gid=2143275417&single=true&output=csv"
CACHE_TTL = 60 * 5

app = FastAPI(title="PIDIM SMART Reports API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_cache: Dict[str, Any] = {}
def _now() -> float: return time.time()

def _get_cached_df() -> pd.DataFrame:
    key = "df"
    if key in _cache and (_now() - _cache[key]["ts"]) < CACHE_TTL:
        return _cache[key]["df"]
    txt = requests.get(SHEET_CSV_URL, timeout=30).text
    df = pd.read_csv(StringIO(txt), low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    _cache[key] = {"df": df, "ts": _now()}
    return df

def _col_by_pos(df: pd.DataFrame, pos: int) -> str:
    pos = max(0, min(len(df.columns) - 1, pos - 1))
    return df.columns[pos]

def _clean_branch(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    bad = s.str.lower().isin(["", "nan", "none", "null", "branch name"])
    return s.mask(bad, None)

def _ensure_slno(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "Sl No" in d.columns:
        d["Sl No"] = range(1, len(d) + 1)
        return d
    d.insert(0, "Sl No", range(1, len(d) + 1))
    return d

def _pos(col: str) -> int:
    col = "".join([c for c in col if c.isalpha()])
    v = 0
    for ch in col.upper():
        v = v * 26 + (ord(ch) - 64)
    return v

BRANCH = _pos("G"); LOAN_TYPE = _pos("AN"); LOAN_AMOUNT = _pos("AQ"); POULTRY_TYPE = _pos("T"); BIRDS_COL = _pos("U"); GRANTS = _pos("BL")

def compute_loan(df: pd.DataFrame) -> pd.DataFrame:
    b = _col_by_pos(df, BRANCH); t = _col_by_pos(df, LOAN_TYPE); a = _col_by_pos(df, LOAN_AMOUNT)
    w = df[[b, t, a]].copy(); w[b] = _clean_branch(w[b]); w[t] = w[t].astype(str).str.strip()
    w["_amt"] = pd.to_numeric(w[a], errors="coerce").fillna(0)
    def norm(x: str) -> str:
        x = (x or "").strip().lower()
        if "non" in x and "enterprise" in x: return "Non-Enterprise"
        if "enterprise" in x: return "Enterprise"
        return ""
    w["_type"] = w[t].apply(norm); w = w[w[b].notna()]
    g = (w.groupby([b, "_type"]).agg(**{"# of Loan":("_type","count"), "Amount of Loan":("_amt","sum")})
         .reset_index().rename(columns={b:"Branch Name","_type":"Types of Loan"}))
    order = {"Enterprise":0,"Non-Enterprise":1}; g["_o"]=g["Types of Loan"].map(order).fillna(99).astype(int)
    rows = []
    for br, gg in g.sort_values(["Branch Name","_o"]).groupby("Branch Name", sort=False):
        for _, r in gg.iterrows():
            rows.append({"Branch Name":br,"Types of Loan":r["Types of Loan"],"# of Loan":int(r["# of Loan"]),"Amount of Loan":float(r["Amount of Loan"] or 0)})
        rows.append({"Branch Name":f"{br} Total","Types of Loan":"","# of Loan":int(gg["# of Loan"].sum()),"Amount of Loan":float(gg["Amount of Loan"].sum())})
    if rows:
        tmp = pd.DataFrame(rows)
        rows.append({"Branch Name":"Grand Total","Types of Loan":"","# of Loan":int(tmp[tmp["Types of Loan"]!=""]["# of Loan"].sum()),"Amount of Loan":float(tmp[tmp["Types of Loan"]!=""]["Amount of Loan"].sum())})
    loan = pd.DataFrame(rows)
    bad = loan["Branch Name"].astype(str).str.strip().str.lower().isin(["branch name","nan","nan total"])
    loan = loan[~bad].copy()
    return _ensure_slno(loan)

def compute_poultry(df: pd.DataFrame) -> pd.DataFrame:
    b = _col_by_pos(df, BRANCH); t = _col_by_pos(df, POULTRY_TYPE); u = _col_by_pos(df, BIRDS_COL)
    w = df[[b,t,u]].copy(); w[b] = _clean_branch(w[b]); w[t]=w[t].astype(str).str.strip(); w[u]=pd.to_numeric(w[u], errors="coerce").fillna(0)
    w = w[w[b].notna()]
    def ptype(x: str) -> str|None:
        x = (x or "").lower()
        if "layer" in x: return "Layer Rearing"
        if "broiler" in x: return "Broiler Rearing"
        return None
    w["_ptype"]=w[t].apply(ptype); w=w[w["_ptype"].notna()]
    agg=(w.groupby([b,"_ptype"]).agg(**{"# of MEs":(t,"count"), "# of Birds":(u,"sum")}).reset_index().rename(columns={b:"Branch Name","_ptype":"Types of Poultry Rearing"}))
    totals = agg.groupby("Branch Name")[["# of MEs","# of Birds"]].sum().reset_index()
    totals["Types of Poultry Rearing"]=""
    out = pd.concat([agg, totals.assign(**{"Branch Name": totals["Branch Name"] + " Total"})], ignore_index=True)
    grand = pd.DataFrame([{"Branch Name":"Grand Total","Types of Poultry Rearing":"","# of MEs":int(agg["# of MEs"].sum()),"# of Birds":float(agg["# of Birds"].sum())}])
    out = pd.concat([out, grand], ignore_index=True)
    return _ensure_slno(out)

def compute_grants(df: pd.DataFrame) -> pd.DataFrame:
    b = _col_by_pos(df, BRANCH); g = _col_by_pos(df, GRANTS)
    w = df[[b,g]].copy(); w[b] = _clean_branch(w[b]); w[g]=pd.to_numeric(w[g], errors="coerce").fillna(0)
    w = w[w[b].notna()]
    cnt = w[w[g]>0].groupby(b).size().reset_index(name="Number on MEs")
    amt = w.groupby(b)[g].sum(min_count=1).reset_index(name="Amounts of Grants")
    rep = cnt.merge(amt, on=b, how="outer").fillna(0).rename(columns={b:"Branch Name"})
    grand = {"Branch Name":"Grand Total","Number on MEs":int(rep["Number on MEs"].sum()),"Amounts of Grants":float(rep["Amounts of Grants"].sum())}
    rep = pd.concat([rep, pd.DataFrame([grand])], ignore_index=True)
    return _ensure_slno(rep)

def _to_excel_bytes(dframes: dict[str, pd.DataFrame]) -> bytes:
    last_err = None
    for eng in ("xlsxwriter","openpyxl"):
        try:
            bio = BytesIO()
            with pd.ExcelWriter(bio, engine=eng) as writer:
                for name, df in dframes.items():
                    df.to_excel(writer, index=False, sheet_name=name[:31])
            bio.seek(0); return bio.getvalue()
        except Exception as e:
            last_err = e; continue
    raise RuntimeError(f"No Excel engine: {last_err}")

@app.get("/health")
def health(): return {"ok": True}

@app.get("/reports/fixed")
def fixed_reports():
    try:
        df = _get_cached_df()
        return {
            "loan": compute_loan(df).to_dict(orient="records"),
            "poultry": compute_poultry(df).to_dict(orient="records"),
            "grants": compute_grants(df).to_dict(orient="records"),
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/export/excel")
def export_excel():
    try:
        df = _get_cached_df()
        data = _to_excel_bytes({"Loan": compute_loan(df), "Poultry": compute_poultry(df), "Grants": compute_grants(df)})
        return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="pidim_reports.xlsx"'})
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/tasks/refresh")
def refresh_cache():
    _cache.pop("df", None)
    _ = _get_cached_df()
    return {"refreshed": True}
