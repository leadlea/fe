# 富士電機 AI推進PoC（LLMチップ統合版）

[![CI & Pages](https://github.com/leadlea/fe/actions/workflows/ci_pages.yml/badge.svg)](https://github.com/leadlea/fe/actions/workflows/ci_pages.yml)

> OCR＋ルール中心の既存ラインに **5つのLLMチップ**（見出し正規化／行フィクサー／重負荷判定／アノマリ要約／SKUランク）を**非破壊に挿入**し、抽出精度・説明可能性・SKU着地を強化するPoC。

- ダッシュボード（GitHub Pages）: **https://leadlea.github.io/fe/executive_summary.html**

---

## 構成（例）

```
.
├─ src/
│   ├─ convert_motor_list.py
│   ├─ size_from_fe.py
│   ├─ size_from_fe_auto.py
│   ├─ llm_header_map.py
│   ├─ llm_fix_rows.py
│   ├─ heavy_from_llm.py
│   ├─ anomaly_from_llm.py
│   └─ sku_map_llm.py
├─ data/
│   └─ catalog_skus.csv         # SKUサンプル（実SKUに差し替え可）
├─ out/                         # 生成物（Git管理外推奨）
├─ docs/
│   └─ executive_summary.html   # エグゼクティブサマリー（Mermaid/JSで自動集計）
├─ requirements.txt
├─ .env.example
├─ .gitignore
└─ README.md
```

> 既存の配置そのままでも動作します。`src/` への配置は任意。

---

## セットアップ

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Bedrockを使う場合
export AWS_REGION=ap-northeast-1
export AWS_PROFILE=your_profile   # もしくは AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
```

`requirements.txt`（例）:
```
pandas
numpy
pydantic>=2
boto3
joblib
```

---

## パイプライン（LLMチップ入り）

1. **見出し正規化**: `llm_header_map.py`
2. **行フィクサー**: `llm_fix_rows.py`（JSONスキーマ厳格＋Pydantic検証）
3. **重負荷判定**: `heavy_from_llm.py`（理由文つき）
4. **自動選定＋根拠文＋結線図**: `size_from_fe_auto.py`
5. **アノマリ要約（QC）**: `anomaly_from_llm.py`
6. **SKUランク**: `sku_map_llm.py`（実SKU Top3＋理由）

---

## 再現手順（end-to-end）

```bash
# 1) OCR→FEリスト（既存フローの例）
python src/convert_motor_list.py --pdf xxx.pdf ... --out out/5/fe_list.csv

# 2) LLMヘッダ正規化
python src/llm_header_map.py --in out/5/fe_list.csv --out out/5/fe_list_norm.csv   --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0

# 3) LLM行フィクサー（監査用diff出力）
python src/llm_fix_rows.py --in out/5/fe_list_norm.csv --out out/5/fe_list_fixed.csv   --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0   --max_retries 4 --max_tokens 1024 --diff out/5/diff_fix.csv

# 4) 重負荷判定（理由つき）
python src/heavy_from_llm.py --in out/5/fe_list_fixed.csv --out out/5/fe_list_heavy.csv   --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0

# 5) 自動選定＋根拠文＋結線図
python src/size_from_fe_auto.py   --in out/5/fe_list_heavy.csv out/7/fe_list_heavy.csv   --out_drives out/B_full/drive_list.csv   --out_xfmr out/B_full/xfmr_list.csv   --out_mermaid out/B_full/wiring.md   --pf 0.85 --eta 0.90 --inv_margin 1.15 --heavy_margin 1.25   --xfmr_diversity 0.90 --xfmr_harmonic 1.10 --xfmr_spare 1.20   --skip_dc --filter_suspicious_for_diagram --auto_heavy --explain

# 6) アノマリ要約（QC）
python src/anomaly_from_llm.py --in out/5/fe_list_heavy.csv out/7/fe_list_heavy.csv   --out out/QC/qc_anomaly_llm.csv   --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0

# 7) SKU候補Top3
python src/sku_map_llm.py   --drives out/B_full/drive_list.csv --catalog data/catalog_skus.csv   --out out/B_full/sku_candidates_llm.csv --freq 50   --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0
```

---

## LLMの使いどころ（勘所）と効果
- **見出しマッピング**：列名ゆらぎを正規化 → ルール追加なしでも通る  
- **行フィクサー**：桁/単位/用途のギブリッシュ補正（Pydanticで厳格検証） → kW/rpm/電圧の充足率↑、手修正↓  
- **重負荷判定**：用途＋数値で「標準/重負荷」決定（根拠付き） → マージン設定の納得感↑  
- **アノマリ要約**：IF/LOF検知を日本語説明 → QCレビュー時間↓、見逃し防止  
- **SKUランク**：丸めkW→実在SKU（Top3＋理由） → **机上kW→型番**へ最短導線  
- **根拠文自動生成**（`--explain`）→ 承認・監査に強い

---

## CI / GitHub Pages

- `.github/workflows/ci_pages.yml`  
  - **TR整合チェック**（∑入力kVA vs 合算kVA(素) が 1% 超差異なら失敗）  
  - `out/**` を `docs/out/**` にコピーし **Pagesへ自動デプロイ**  
  - `wiring.md` があれば Mermaid を SVG 化（サンドボックス解除設定付き）

> Settings → Pages → Source: **GitHub Actions** に設定。

---

## セキュリティ / 取り扱い
- 実データやAWSキーは **Gitに含めない**（`.gitignore`/環境変数/プロファイル注入）  
- 公開可否に応じて `data/`・`out/` はダミーを推奨

---

## ライセンス
社内限定（PRIVATE）の場合はライセンス表記なし。外部公開時は MIT 等を検討。
作成者：ビジョンコンサルティング　福原玄