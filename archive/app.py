from __future__ import annotations
import os, io, csv, json, pathlib, datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

APP_DIR = pathlib.Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
OUTPUT_ROOT = pathlib.Path(os.getenv("OUTPUT_ROOT", str(APP_DIR / "out_edits")))

# ---------- Models ----------
class Metadata(BaseModel):
    stage: str = Field(..., description="例: 30_motor_list_normalized.csv")
    role: str = Field(..., description="production|calibration 等")
    aggregate: bool = True
    conf_threshold: float | None = None

class PatchOp(BaseModel):
    op: str = Field(..., description="replace のみ対応(MVP)")
    row_index: int | None = None
    row_key: str | None = None
    column: str
    old: str | None = None
    value: str | None = None

class Patch(BaseModel):
    meta: dict = {}
    ops: list[PatchOp] = []

class RecalcRequest(BaseModel):
    metadata: Metadata
    csv: str
    patch: Patch | None = None

# ---------- App ----------
app = FastAPI(title="HITL Local API (Pages mode)")

# CORS: allow GitHub Pages origin(s)
allowed = os.getenv("ALLOWED_ORIGINS", "https://*.github.io,https://github.io,https://localhost,https://127.0.0.1").split(",")
allowed = [o.strip() for o in allowed if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in allowed else allowed,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# Static UI
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

@app.get("/", include_in_schema=False)
def root():
    idx = WEB_DIR / "index.html"
    if not idx.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(idx)

# ---------- Utils ----------
def parse_csv_to_dicts(csv_text: str):
    f = io.StringIO(csv_text)
    rows = list(csv.reader(f))
    if not rows: return [], []
    headers = rows[0]
    dicts = []
    for r in rows[1:]:
        if len(r) < len(headers): r = r + [""] * (len(headers) - len(r))
        elif len(r) > len(headers): r = r[:len(headers)]
        dicts.append({h: (r[i] if i < len(r) else "") for i, h in enumerate(headers)})
    return headers, dicts

def dicts_to_csv(headers, dicts):
    out = io.StringIO(); w = csv.writer(out, lineterminator="\n")
    w.writerow(headers)
    for d in dicts: w.writerow([d.get(h, "") for h in headers])
    return out.getvalue()

def detect_key(headers):
    for c in ("row_id","id","item_no"):
        if c in headers: return c
    return None

def apply_patch(headers, rows, patch: Patch | None):
    if not patch or not patch.ops: return rows, 0
    key_col = detect_key(headers)
    by_key = {}
    if key_col:
        for i,d in enumerate(rows):
            k = str(d.get(key_col, ""))
            if k: by_key[k] = i
    applied = 0
    for op in patch.ops:
        if op.op != "replace": continue
        idx = None
        if op.row_key is not None and key_col: idx = by_key.get(str(op.row_key))
        if idx is None and op.row_index is not None and 0 <= op.row_index < len(rows): idx = op.row_index
        if idx is None or op.column not in headers: continue
        if op.old is not None:
            cur = rows[idx].get(op.column, "")
            if str(cur) != str(op.old):
                # skip conflict in MVP
                pass
        rows[idx][op.column] = "" if op.value is None else str(op.value)
        applied += 1
    return rows, applied

def now_run_id(): return datetime.datetime.utcnow().strftime("run-%Y%m%d-%H%M%S")
def ensure_dir(p: pathlib.Path): p.mkdir(parents=True, exist_ok=True)

# ---------- API ----------
@app.post("/api/recalculate")
def recalc(req: RecalcRequest):
    if not req.csv or not req.metadata or not req.metadata.stage:
        raise HTTPException(status_code=400, detail="metadata.stage と csv は必須です")
    headers, dicts = parse_csv_to_dicts(req.csv)
    if not headers:
        raise HTTPException(status_code=400, detail="CSVにヘッダ行がありません")

    patched, applied = apply_patch(headers, dicts, req.patch)
    csv_patched = dicts_to_csv(headers, patched)

    run_id = now_run_id()
    stage_name = req.metadata.stage.replace(".csv","")
    stage_dir = OUTPUT_ROOT / run_id / stage_name
    ensure_dir(stage_dir)
    (stage_dir / "received.csv").write_text(req.csv, encoding="utf-8")
    (stage_dir / "patched.csv").write_text(csv_patched, encoding="utf-8")
    (stage_dir / "metadata.json").write_text(
        json.dumps(req.metadata.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if req.patch:
        (stage_dir / "patch.json").write_text(
            json.dumps(req.patch.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return JSONResponse({
        "ok": True,
        "saved": {
            "run_id": run_id,
            "stage_dir": str(stage_dir),
            "received_csv_path": str(stage_dir / "received.csv"),
            "patched_csv_path": str(stage_dir / "patched.csv"),
            "patch_path": str(stage_dir / "patch.json") if req.patch else None,
            "metadata_path": str(stage_dir / "metadata.json"),
        },
        "summary": { "rows": len(patched), "cols": len(headers), "applied_ops": applied }
    })

@app.get("/api/health")
def health(): return {"ok": True}
