# 富士電機 AI推進PoC（LLMチップ統合版）

本リポジトリは、OCR＋ルールベースの既存フローに **5つのLLMチップ**（見出し正規化／行フィクサー／重負荷判定／アノマリ要約／SKUランク）を**非破壊に挿入**し、抽出精度と説明可能性、SKU着地を強化した実証の手順とコードを提供します。

## リポジトリ構成（例）
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

> 既存の配置そのままでOKです。`src/` へ移動したくない場合は、パスを README と Makefile で調整してください。

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

## 再現手順（end-to-end）

```bash
# 1) OCR結果からFEリストを生成（既存フロー）
python src/convert_motor_list.py --pdf xxx.pdf ... --out out/5/fe_list.csv

# 2) LLMヘッダ正規化
python src/llm_header_map.py --in out/5/fe_list.csv --out out/5/fe_list_norm.csv \
  --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0

# 3) LLM行フィクサー（全行 / 監査ログ出力）
python src/llm_fix_rows.py --in out/5/fe_list_norm.csv --out out/5/fe_list_fixed.csv \
  --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0 \
  --max_retries 4 --max_tokens 1024 --diff out/5/diff_fix.csv

# 4) 重負荷判定（理由つき）
python src/heavy_from_llm.py --in out/5/fe_list_fixed.csv --out out/5/fe_list_heavy.csv \
  --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0

# 5) 自動選定＋根拠文＋結線図
python src/size_from_fe_auto.py \
  --in out/5/fe_list_heavy.csv out/7/fe_list_heavy.csv \
  --out_drives out/B_full/drive_list.csv \
  --out_xfmr out/B_full/xfmr_list.csv \
  --out_mermaid out/B_full/wiring.md \
  --pf 0.85 --eta 0.90 --inv_margin 1.15 --heavy_margin 1.25 \
  --xfmr_diversity 0.90 --xfmr_harmonic 1.10 --xfmr_spare 1.20 \
  --skip_dc --filter_suspicious_for_diagram --auto_heavy --explain

# 6) アノマリ要約（QC）
python src/anomaly_from_llm.py --in out/5/fe_list_heavy.csv out/7/fe_list_heavy.csv \
  --out out/QC/qc_anomaly_llm.csv \
  --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0

# 7) SKU候補Top3
python src/sku_map_llm.py \
  --drives out/B_full/drive_list.csv --catalog data/catalog_skus.csv \
  --out out/B_full/sku_candidates_llm.csv --freq 50 \
  --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0
```

## LLMの使いどころ（勘所）
- **見出しマッピング**：列名ゆらぎを正規化 → ルール追加なしでも通る
- **行フィクサー**：桁/単位/ギブリッシュ補正（Pydanticで厳格検証）
- **重負荷判定**：用途テキスト＋数値から「標準/重負荷」決定（根拠付き）
- **アノマリ要約**：機械検知の結果を日本語で要約し、レビューを短縮
- **SKUランク**：丸めkW→実在SKU（Top3＋理由）に着地

## 監査・再現性
- **差分ログ**：`out/*/diff_fix*.csv` に Before/After を保存
- **ヘッダマップ**：`*_header_map.json` に列名変換根拠を保存
- **設計根拠**：`size_from_fe_auto.py --explain` で各行の説明文を出力
- **TR整合**：`sum(入力kVA) ≈ xfmr 合算kVA(素)` をCIでチェック

## セキュリティ & 秘匿情報
- AWSキーや顧客データは **Git管理下に置かない**。`.env` を使うかプロファイル注入。
- 共有用には **サンプルデータ**（ダミー）と生成物のみをコミット推奨。

## GitHub Pages（ダッシュボード公開）
- `docs/executive_summary.html` をコミット → Settings > Pages > Branch: main / folder: `/docs`
- `docs/` から `../out/...` を参照するため、ビルド時に `out/` もコミット or CIでコピー。

## ライセンス
社内限定の場合は PRIVATE。外部公開するなら MIT などを検討。
