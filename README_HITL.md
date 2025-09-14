# HITL Local for GitHub Pages (No Cloud Backends)

- **UI**: GitHub Pages で配信（`web/index.html`）
- **API**: ローカルPC上で FastAPI を起動（HTTPS 推奨）
- **CORS**: `ALLOWED_ORIGINS` で GitHub Pages のオリジンを許可

## 1) GitHub Pages にデプロイ（UI）
`web/index.html` をあなたのリポジトリに配置し、Pages を有効化。例:
- URL 例: `https://leadlea.github.io/fe/hitl/index.html`

## 2) ローカルAPIを起動（HTTPS 推奨）
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2-1) 証明書を作成（自己署名）
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/localhost.key -out certs/localhost.crt -days 365 -subj "/CN=localhost"

# 2-2) HTTPSで起動（推奨: 8443）
uvicorn app:app --host 127.0.0.1 --port 8443 --ssl-keyfile certs/localhost.key --ssl-certfile certs/localhost.crt
```

> GitHub Pages (HTTPS) → `http://localhost:8000` は **混在コンテンツ** になる可能性があるため、**`https://localhost:8443`** を推奨。  
> Pages側の UI では API BASE の初期値を `https://localhost:8443` に設定済みです。必要に応じて変更できます。

## 3) CORS 設定
環境変数 `ALLOWED_ORIGINS`（カンマ区切り）で許可オリジンを設定。
```bash
export ALLOWED_ORIGINS="https://leadlea.github.io,https://*.github.io,https://localhost"
```
未設定でも `*.github.io` 等をデフォルト許可しています。社内ポリシーに応じて絞ってください。

## 4) 動作手順
1. ローカルAPIを HTTPS で起動（上記 2-2）。
2. GitHub Pages の URL（例: `https://leadlea.github.io/fe/hitl/`）を開く。
3. 右上の **API BASE** が `https://localhost:8443` になっていることを確認。
4. CSVを読み込んで編集 → 「再計算 API POST」を押すとローカルに保存されます。

## 5) 出力先
`out_edits/run-YYYYMMDD-HHMMSS/<stage_name>/` に以下を保存:
- `received.csv` / `patched.csv` / `patch.json` / `metadata.json`

## 6) トラブルシュート
- **CORSエラー**: `ALLOWED_ORIGINS` を適切に設定して再起動。
- **Mixed Contentエラー**: APIをHTTPSで起動し、API BASEを `https://localhost:8443` に。
- **自己署名の警告**: OSの証明書ストアに `localhost.crt` を信頼登録するか、ブラウザで一度許可してください。
- **ポート占有**: 別ポート指定可（UI側は API BASE を合わせて変更）。
