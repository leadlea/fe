# 富士電機 HITL Orchestrator MVP（Pages + Local API）

**デモUI（GitHub Pages）**: https://leadlea.github.io/fe/hitl.html  
**目的**: 既存のスクリプト群を「変更せず」に、**PDF → ETL → CSV編集（HITL）→ 再実行 → 図面（Mermaid/SVG）**まで一気通貫で回す最小実装。  
**LLM**: Amazon Bedrock / **Claude 3.5 Sonnet**（02〜04ステップ）。

---

## クイックスタート

### 0) 前提
- macOS / Linux、Python 3.11+、Chrome or Safari
- AWS 認証: `~/.aws/credentials` の **[default]** もしくは環境変数（`AWS_ACCESS_KEY_ID/SECRET`）
- 権限: `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`, `bedrock:ListFoundationModels`
- リージョン例: `ap-northeast-1`

### 1) ローカルAPIの起動（HTTPS推奨）
```bash
cd ~/fe/hitl_orchestrator_local

# 初回のみ（仮想環境 & 依存）
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 証明書（初回のみ）
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes   -keyout certs/localhost.key -out certs/localhost.crt   -days 365 -subj "/CN=localhost"

# 起動（defaultプロファイルを使用）
export AWS_REGION=ap-northeast-1
OUTPUT_ROOT="$HOME/fe/out" ./start_https.sh
# → API: https://localhost:8443
```

> Pages は HTTPS で配信されるため、**API も HTTPS（https://localhost:8443）** を使ってください。初回はブラウザで証明書を許可してください。

### 2) Pages UI の使い方（https://leadlea.github.io/fe/hitl.html）

1. **API BASE** が `https://localhost:8443` になっていることを確認し「Save」。  
2. **「PDFをドロップ」**（例: `5.pdf`）。左上に `run_id: run-YYYYMMDD-HHMMSS` が表示されます。  
3. 左ペインの **ステップを順に実行**：  
   - `01_convert` → `02_header_map` → `03_fix_rows` → `04_heavy` → `05_size`  
   - 02〜04は Bedrock/Claude 3.5 Sonnet を使用します。  
4. 中央の **CSVエディタ**：  
   - 入力欄に `run-YYYYMMDD-HHMMSS/fe_list.csv`（※ `out/` は不要）→ **読込**  
   - セルを編集 → **保存**。必要に応じて `05_size` を再実行すると図面に反映されます。  
   - ※ 横に長いときはテーブルの**横スクロール**が有効。  
5. 右の **図面(Mermaid)**：  
   - 入力欄に **`B_full/wiring.md`** と入れて **読込**（※ `out/` は不要）  
   - 図の見た目は `wiring.md`（Mermaid）由来。必要に応じて再生成してください。

---

## パイプライン構成

`hitl_orchestrator_local/pipeline.json`

```jsonc
{
  "steps": [
    { "name": "01_convert",
      "cmd": "mkdir -p {out_dir}/{run_id} && python convert_motor_list.py --pdf {pdf} --out {out_dir}/{run_id}/fe_list.csv",
      "outputs": ["{out_dir}/{run_id}/fe_list.csv"]
    },
    { "name": "02_header_map",
      "cmd": "mkdir -p {out_dir}/{run_id} && python llm_header_map.py --in {out_dir}/{run_id}/fe_list.csv --out {out_dir}/{run_id}/fe_list_norm.csv --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0 --sample_rows 5",
      "outputs": ["{out_dir}/{run_id}/fe_list_norm.csv"]
    },
    { "name": "03_fix_rows",
      "cmd": "mkdir -p {out_dir}/{run_id} && python llm_fix_rows.py --in {out_dir}/{run_id}/fe_list_norm.csv --out {out_dir}/{run_id}/fe_list_fixed.csv --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0",
      "outputs": ["{out_dir}/{run_id}/fe_list_fixed.csv"]
    },
    { "name": "04_heavy",
      "cmd": "mkdir -p {out_dir}/{run_id} && python heavy_from_llm.py --in {out_dir}/{run_id}/fe_list_fixed.csv --out {out_dir}/{run_id}/fe_list_heavy.csv --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0",
      "outputs": ["{out_dir}/{run_id}/fe_list_heavy.csv"]
    },
    { "name": "05_size",
      "cmd": "mkdir -p {out_dir}/B_full && python size_from_fe_auto.py --in {out_dir}/{run_id}/fe_list_heavy.csv --out_drives {out_dir}/B_full/drive_list.csv --out_xfmr {out_dir}/B_full/xfmr_list.csv --out_mermaid {out_dir}/B_full/wiring.md",
      "outputs": ["{out_dir}/B_full/drive_list.csv","{out_dir}/B_full/xfmr_list.csv","{out_dir}/B_full/wiring.md"]
    }
  ]
}
```

> `--model` は環境変数に置き換えてもOKです（例：`"$BEDROCK_MODEL"`）。

---

## Mermaid → SVG/PNG（任意）

```bash
cd ~/fe
# Mermaidコードだけ抽出
sed -n '/```mermaid/,/```/p' out/B_full/wiring.md | sed '1d;$d' > out/B_full/wiring.mmd

# SVG 出力
npx -y @mermaid-js/mermaid-cli -i out/B_full/wiring.mmd -o out/B_full/wiring.svg

# 透過背景・サイズ調整例
npx -y @mermaid-js/mermaid-cli -i out/B_full/wiring.mmd -o out/B_full/wiring.svg -b transparent --width 1600 --scale 1.2

# PNG 出力
npx -y @mermaid-js/mermaid-cli -i out/B_full/wiring.mmd -o out/B_full/wiring.png
```

---

## GitHub Pages に成果物を載せる（任意）

`docs/out/B_full/` にコピーして push します（CI が Pages に反映）。

```bash
cd ~/fe
mkdir -p docs/out/B_full
cp -f out/B_full/{drive_list.csv,xfmr_list.csv,wiring.md,wiring.svg} docs/out/B_full/
git add docs/out/B_full
git commit -m "docs: publish wiring (SVG) and CSVs"
git push
```

---

## トラブルシュート

- **APIに繋がらない / `ERR_CERT_AUTHORITY_INVALID`**  
  - API は `https://localhost:8443` を使用。自己署名証明書をブラウザで一度「許可」。

- **Bedrock: AccessDenied / Model not found**  
  - IAM 権限を付与（少なくとも `bedrock:InvokeModel(*)`）。  
  - `export AWS_REGION=ap-northeast-1`（利用可能リージョンのモデルIDを使用）。  
  - 確認: `aws sts get-caller-identity` / `aws bedrock list-foundation-models --region $AWS_REGION`

- **`size_from_fe_auto.py: ambiguous option --out`**  
  - 本MVPは `--out_drives/--out_xfmr/--out_mermaid` を使用します（修正済み）。

- **CSVが横に長くて見切れる**  
  - UIは横スクロール対応。列幅が厳しい場合はブラウザ拡大率も併用。

- **02で `FutureWarning: applymap`**  
  - 実行には影響なし。必要なら `llm_header_map.py` の `applymap(jfix)` → `map(jfix)` に置換。

---

## 開発メモ

- **変更しない**原則：既存の `convert_* / *_map / *_rows / *from_llm / size_from_fe_*` を改変せず、オーケストレータから引数で制御。  
- 保存先 `out/`、一時 `runs/` は **.gitignore** 済み。鍵/証明書 (`certs/`) もコミットされません。  
- LLM モデル切替は `pipeline.json` か `BEDROCK_MODEL` 環境変数で。

---

© 富士電機 PoC / MVP（HITL Orchestrator）。
