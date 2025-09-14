from __future__ import annotations
import os, io, csv, json, pathlib, subprocess, shlex, datetime, typing as T
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

APP_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent if (APP_DIR / "app.py").exists() else APP_DIR
RUNS_DIR = APP_DIR / "runs"
OUT_DIR = APP_DIR / "out"  # 既存と共用したい場合は実行時に OUTPUT_ROOT で上書き可能
OUTPUT_ROOT = pathlib.Path(os.getenv("OUTPUT_ROOT", str(OUT_DIR)))
RUNS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

def now_id() -> str:
    return datetime.datetime.utcnow().strftime("run-%Y%m%d-%H%M%S")

# ---- CORS ----
allowed = os.getenv("ALLOWED_ORIGINS", "https://*.github.io,https://github.io,https://localhost").split(",")
allowed = [o.strip() for o in allowed if o.strip()]
app = FastAPI(title="HITL Orchestrator (Local)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in allowed else allowed,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# Static mounts (成果物の直接配信)
app.mount("/runs", StaticFiles(directory=RUNS_DIR), name="runs")
app.mount("/out", StaticFiles(directory=OUTPUT_ROOT), name="out")
app.mount("/ui", StaticFiles(directory=APP_DIR / "web", html=True), name="ui")

@app.get("/", include_in_schema=False)
def root():
    idx = APP_DIR / "web" / "index.html"
    if not idx.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(idx)

# ---- Pipeline config ----
class Step(BaseModel):
    name: str
    cmd: str
    outputs: T.List[str] = []

DEFAULT_STEPS: T.List[Step] = []

def file_exists(p: pathlib.Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False

def detect_default_steps() -> T.List[Step]:
    steps: T.List[Step] = []
    # If known scripts exist, propose default commands (best-effort)
    scripts = {
        "convert_motor_list.py": "python convert_motor_list.py --in {pdf} --out {out_dir}/{run_id}/fe_list.csv",
        "llm_header_map.py": "python llm_header_map.py {out_dir}/{run_id}/fe_list.csv {out_dir}/{run_id}/fe_list_norm.csv",
        "llm_fix_rows.py": "python llm_fix_rows.py {out_dir}/{run_id}/fe_list_norm.csv {out_dir}/{run_id}/fe_list_fixed.csv",
        "heavy_from_llm.py": "python heavy_from_llm.py {out_dir}/{run_id}/fe_list_fixed.csv {out_dir}/{run_id}/fe_list_heavy.csv",
        "size_from_fe_auto.py": "python size_from_fe_auto.py --in {out_dir}/{run_id}/fe_list_heavy.csv --out {out_dir}/B_full"
    }
    exists = [k for k in scripts.keys() if file_exists(REPO_ROOT / k)]
    if not exists:
        # Fallback: just copy uploaded PDF to out to prove the flow
        steps.append(Step(name="echo", cmd="echo Pipeline OK for {pdf} > {out_dir}/{run_id}/pipeline_ok.txt", outputs=[f"{OUTPUT_ROOT}/{{run_id}}/pipeline_ok.txt"]))
        return steps
    # Build steps based on presence
    if "convert_motor_list.py" in exists:
        steps.append(Step(name="01_convert", cmd=scripts["convert_motor_list.py"], outputs=[f"{OUTPUT_ROOT}/{{run_id}}/fe_list.csv"]))
    if "llm_header_map.py" in exists:
        steps.append(Step(name="02_header_map", cmd=scripts["llm_header_map.py"], outputs=[f"{OUTPUT_ROOT}/{{run_id}}/fe_list_norm.csv"]))
    if "llm_fix_rows.py" in exists:
        steps.append(Step(name="03_fix_rows", cmd=scripts["llm_fix_rows.py"], outputs=[f"{OUTPUT_ROOT}/{{run_id}}/fe_list_fixed.csv"]))
    if "heavy_from_llm.py" in exists:
        steps.append(Step(name="04_heavy", cmd=scripts["heavy_from_llm.py"], outputs=[f"{OUTPUT_ROOT}/{{run_id}}/fe_list_heavy.csv"]))
    if "size_from_fe_auto.py" in exists:
        steps.append(Step(name="05_size", cmd=scripts["size_from_fe_auto.py"], outputs=[f"{OUTPUT_ROOT}/B_full/drive_list.csv", f"{OUTPUT_ROOT}/B_full/xfmr_list.csv", f"{OUTPUT_ROOT}/B_full/wiring.md"]))
    return steps

def load_pipeline() -> T.List[Step]:
    cfg = APP_DIR / "pipeline.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            steps = [Step(**s) for s in data.get("steps", [])]
            if steps:
                return steps
        except Exception as e:
            print("pipeline.json load error:", e)
    return detect_default_steps()

# ---- Helpers ----
def fmt_cmd(cmd: str, run_id: str, pdf_path: pathlib.Path) -> str:
    return cmd.format(
        pdf=str(pdf_path),
        run_id=run_id,
        runs_dir=str(RUNS_DIR),
        out_dir=str(OUTPUT_ROOT),
        repo_root=str(REPO_ROOT),
    )

def run_shell(cmd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, shell=True, cwd=str(REPO_ROOT), capture_output=True, text=True)
        out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, out
    except Exception as e:
        return 999, str(e)

def ensure_parents(p: pathlib.Path):
    p.parent.mkdir(parents=True, exist_ok=True)

# ---- API ----
@app.get("/api/config")
def get_config():
    steps = load_pipeline()
    return {"steps": [s.model_dump() for s in steps], "repo_root": str(REPO_ROOT), "out_dir": str(OUTPUT_ROOT), "runs_dir": str(RUNS_DIR)}

@app.post("/api/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルをアップロードしてください")
    run_id = now_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = run_dir / "input.pdf"
    content = await file.read()
    pdf_path.write_bytes(content)
    return {"ok": True, "run_id": run_id, "pdf": f"/runs/{run_id}/input.pdf"}

class ExecBody(BaseModel):
    run_id: str
    step_index: int

@app.post("/api/exec_step")
def exec_step(body: ExecBody):
    steps = load_pipeline()
    if body.step_index < 0 or body.step_index >= len(steps):
        raise HTTPException(status_code=400, detail="step_index が不正です")
    run_id = body.run_id
    pdf_path = RUNS_DIR / run_id / "input.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF が見つかりません。先にアップロードしてください。")
    step = steps[body.step_index]
    cmd = fmt_cmd(step.cmd, run_id, pdf_path)
    code, log = run_shell(cmd)
    # Save log
    log_path = RUNS_DIR / run_id / f"{step.name}.log"
    ensure_parents(log_path)
    log_path.write_text(log, encoding="utf-8")
    # Check outputs
    outputs = [o.format(run_id=run_id, out_dir=str(OUTPUT_ROOT)) for o in step.outputs]
    exist_map = {o: (OUTPUT_ROOT / pathlib.Path(o.replace(str(OUTPUT_ROOT), '').lstrip('/'))).exists() if o.startswith(str(OUTPUT_ROOT)) else pathlib.Path(o).exists() for o in outputs}
    return {"ok": code == 0, "exit_code": code, "log": log, "outputs": exist_map, "cmd": cmd}

@app.get("/api/log")
def get_log(run_id: str, step_name: str):
    p = RUNS_DIR / run_id / f"{step_name}.log"
    if not p.exists():
        raise HTTPException(status_code=404, detail="log not found")
    return PlainTextResponse(p.read_text(encoding="utf-8"))

@app.get("/api/read_text")
def read_text(path: str):
    p = pathlib.Path(path)
    if not p.is_absolute():
        # allow relative to OUT_DIR or RUNS_DIR
        op = OUTPUT_ROOT / path
        rp = RUNS_DIR / path
        if op.exists():
            p = op
        elif rp.exists():
            p = rp
        else:
            raise HTTPException(status_code=404, detail="file not found")
    if not p.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return PlainTextResponse(p.read_text(encoding="utf-8"))

@app.get("/api/read_csv")
def read_csv(path: str):
    p = pathlib.Path(path)
    if not p.is_absolute():
        p = OUTPUT_ROOT / path
    if not p.exists():
        raise HTTPException(status_code=404, detail="csv not found")
    text = p.read_text(encoding="utf-8")
    return PlainTextResponse(text)

class SaveCSV(BaseModel):
    path: str
    csv: str

@app.post("/api/save_csv")
def save_csv(body: SaveCSV):
    p = pathlib.Path(body.path)
    if not p.is_absolute():
        p = OUTPUT_ROOT / body.path
    ensure_parents(p)
    p.write_text(body.csv, encoding="utf-8")
    return {"ok": True, "path": str(p)}

@app.get("/api/health")
def health():
    return {"ok": True}
