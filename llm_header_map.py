#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_header_map.py — 見出し・単位マッピングをLLMで決定して正規化
使い方:
  python llm_header_map.py --in out/5/fe_list.csv --out out/5/fe_list_norm.csv \
    --provider bedrock --model anthropic.claude-3-5-sonnet-20240620-v1:0
  # OpenAI例:
  # python llm_header_map.py --in ... --out ... --provider openai --model gpt-4o-mini
"""
import argparse, os, re, json, sys
import pandas as pd

CJK = r"\u3040-\u30FF\u4E00-\u9FFF\uFF00-\uFFEF"
CANON = {
  "用途": ["用途","種類","設備名","機器名","名称","備考"],
  "出力(kW)": ["出力(kW)","kW","容量","出力"],
  "電圧(V)": ["電圧(V)","電圧","定格電圧","電 圧","V","ACV"],
  "rpm_base": ["rpm_base","ベース","ベ ー ス","ベース rpm","rpm ベース","base","ベースr/m"],
  "rpm_top":  ["rpm_top","トップ","ト ッ プ","トップ rpm","rpm トップ","top","トッpr/m"],
  "torque_kgm": ["torque_kgm","定格トルク","トルク","kgm","定格 ト ル ク"]
}

def jfix(s: str) -> str:
    s = s.replace("ｒ/ｍ","rpm").replace("Ｒ／Ｍ","rpm").replace("Ｒ/Ｍ","rpm").replace("r/m","rpm")
    s = re.sub(r"(?<=\d)[\s,]+(?=\d)", "", s)  # 1 , 500 → 1500
    s = re.sub(r"\s*~\s*", "-", s)
    s = re.sub(fr"(?<=[{CJK}])\s+(?=[{CJK}])", "", s)
    return s.strip()

# ---- LLM client（Bedrock/OpenAI） ----
class LLM:
    def __init__(self, provider, model):
        self.provider = provider; self.model = model
        if provider=="bedrock":
            import boto3
            self.cli = boto3.client("bedrock-runtime")
        elif provider=="openai":
            from openai import OpenAI
            self.cli = OpenAI()
        else:
            raise RuntimeError("provider must be bedrock or openai")

    def complete_json(self, system_prompt, user_obj, max_tokens=1024):
        txt = json.dumps(user_obj, ensure_ascii=False)
        if self.provider=="bedrock":
            body = {
              "anthropic_version":"bedrock-2023-05-31",
              "max_tokens":max_tokens,
              "temperature":0,
              "system":system_prompt,
              "messages":[{"role":"user","content":[{"type":"text","text":txt}]}]
            }
            out = self.cli.invoke_model(modelId=self.model, body=json.dumps(body))
            return json.loads(out["body"].read()).get("content",[{}])[0].get("text","{}")
        else:
            out = self.cli.chat.completions.create(
                model=self.model, temperature=0, max_tokens=max_tokens,
                response_format={"type":"json_object"},
                messages=[{"role":"system","content":system_prompt},
                          {"role":"user","content":txt}]
            )
            return out.choices[0].message.content or "{}"

SYSTEM = """あなたは製造業の表データ整形アシスタントです。
与えられたヘッダ配列とサンプル行を見て、次の正規化キーに**確実に**マップしてください:
["用途","出力(kW)","電圧(V)","rpm_base","rpm_top","torque_kgm"]。
不要列は "IGNORE"。出力は必ずJSON: {"mapping": {"原列名": "正規化名 or IGNORE"}} のみ。説明やコードフェンスは不要。
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--provider", choices=["bedrock","openai"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--sample_rows", type=int, default=10)
    args = ap.parse_args()

    df = pd.read_csv(args.inp)
    headers = list(df.columns)
    sample = df.head(args.sample_rows).astype(str).map(jfix).to_dict(orient="records")

    llm = LLM(args.provider, args.model)
    user = {"headers": headers, "sample": sample, "canon": list(CANON.keys())}
    txt = llm.complete_json(SYSTEM, user)
    try:
        mapping = json.loads(txt).get("mapping", {})
    except Exception as e:
        print("[ERROR] JSON parse failed:", e, file=sys.stderr); sys.exit(2)

    # ヘッダ置換
    new_cols = []
    for h in headers:
        m = mapping.get(h, h)
        if m=="IGNORE": new_cols.append(h)  # いったん残す（削除すると列ズレ発生のため）
        else: new_cols.append(m)
    df.columns = new_cols

    # セル正規化
    for c in df.columns:
        if df[c].dtype==object:
            df[c] = df[c].astype(str).map(jfix)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print("✓ Wrote normalized CSV:", args.out)
    # マッピングも保存
    with open(os.path.splitext(args.out)[0] + "_header_map.json","w",encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print("✓ Wrote header map JSON")

if __name__=="__main__":
    main()
