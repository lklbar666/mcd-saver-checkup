#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把麦当劳 MCP 的实时菜单转成差价引擎的内部格式。

输入：MCP（query-meals + query-meal-detail）
输出：data/menu.json（结构与 data/mock_menu.json 一致）

用法：
  export MCD_MCP_TOKEN=...
  python scripts/load_menu.py --store 1950564 --out data/menu.json
  python scripts/load_menu.py --store 1950564 --detail-limit 12   # 只抓前 12 个套餐的组成
"""
from __future__ import annotations

import argparse
import json
import os
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcd_mcp import McpClient, extract_payload  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMBO_HINT = re.compile(r"(套餐|三件套|两件套|四件套|组合|拼盘|分享装|双人|单人餐)")


def price_of(v) -> float:
    """菜单里价格是字符串（"33.5"）或数字，统一成 float。"""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else 0.0


def diff_of(s) -> float:
    """套餐内选项的 diffPrice，形如 "+ ¥3"。"""
    if not s:
        return 0.0
    neg = "-" in str(s)
    v = price_of(s)
    return -v if neg else v


def fetch_menu(c: McpClient, store: str, order_type: int, be_type: int) -> dict:
    res = c.call("query-meals", {"storeCode": store, "orderType": order_type, "beType": be_type})
    p = extract_payload(res)
    if not p or not p.get("data"):
        raise SystemExit("query-meals 无有效返回")
    return p["data"]


def combo_members(c: McpClient, store: str, order_type: int, be_type: int, code: str) -> list:
    """取套餐各轮次的默认选项，返回 [(item_code, qty)]。"""
    res = c.call("query-meal-detail", {"storeCode": store, "orderType": order_type,
                                       "beType": be_type, "code": code})
    p = extract_payload(res)
    d = (p or {}).get("data") or {}
    out = []
    for rnd in d.get("rounds") or []:
        choices = rnd.get("choices") or []
        if not choices:
            continue
        # 优先默认项，否则第一项
        pick = next((x for x in choices if x.get("isDefault") in (1, True)), choices[0])
        qty = int(pick.get("quantity") or 1)
        if pick.get("code"):
            out.append((str(pick["code"]), pick.get("name") or "", qty))
    return out


def fetch_coupons(c: McpClient, items: list) -> tuple[list, list]:
    """解析麦麦省券列表（Markdown 文本）。只处理「X 元 <商品名>」与「免费 <商品名>」两类。"""
    res = c.call("available-coupons", {})
    txt = "".join(b.get("text", "") for b in res.get("content", []) if isinstance(b, dict))
    names = {i["name"]: i for i in items}
    found, unknown = [], []
    for raw in re.findall(r"优惠券标题：([^\s\\]+)", txt):
        title = raw.strip()
        m = re.match(r"^(\d+(?:\.\d+)?)元(.+)$", title)
        free = re.match(r"^免费(.+)$", title)
        if m:
            price, target = float(m.group(1)), m.group(2).strip()
        elif free:
            price, target = 0.0, free.group(1).strip()
        else:
            unknown.append(title); continue
        hit = names.get(target) or next(
            (names[n] for n in difflib.get_close_matches(target, list(names), n=1, cutoff=0.75)), None)
        if not hit:
            unknown.append(title); continue
        off = round(hit["price"] - price, 2)
        if off <= 0:
            unknown.append(title); continue
        found.append({"id": "ms_" + hit["id"], "name": title, "kind": "amount",
                      "value": off, "min_spend": 0, "item_ids": [hit["id"]], "stackable": False})
    return found, unknown


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--order-type", type=int, default=1)
    ap.add_argument("--be-type", type=int, default=1)
    ap.add_argument("--out", default=str(ROOT / "data" / "menu.json"))
    ap.add_argument("--detail-limit", type=int, default=10, help="最多抓几个套餐的组成")
    ap.add_argument("--no-coupons", action="store_true", help="不抓麦麦省可领券")
    a = ap.parse_args(argv)

    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    c = McpClient(token)
    c.initialize()
    data = fetch_menu(c, a.store, a.order_type, a.be_type)
    meals = data.get("meals") or {}
    print("餐品 %d 个" % len(meals))

    items, combos = [], []
    combo_codes = []
    for code, m in meals.items():
        name = m.get("name") or code
        cur = price_of(m.get("currentPrice")) or price_of(m.get("originalPrice"))
        items.append({"id": str(code), "name": name, "price": round(cur, 2),
                      "category": "", "orig": price_of(m.get("originalPrice"))})
        if COMBO_HINT.search(name):
            combo_codes.append((code, name))

    # 套餐内商品的编码与单点编码不是一套，必须按名称对齐
    name_to_id = {}
    for i in items:
        name_to_id.setdefault(i["name"], i["id"])
    def canon(code: str, name: str) -> str:
        if code in {i["id"] for i in items}:
            return code
        if not name:
            return code
        hit = difflib.get_close_matches(name, list(name_to_id), n=1, cutoff=0.6)
        return name_to_id[hit[0]] if hit else code

    print("疑似套餐 %d 个，抓前 %d 个的组成…" % (len(combo_codes), a.detail_limit))
    for code, name in combo_codes[:a.detail_limit]:
        try:
            members = combo_members(c, a.store, a.order_type, a.be_type, code)
        except Exception as e:
            print("  ✗ %s %s：%s" % (code, name, e))
            continue
        if not members:
            continue
        price = next(i["price"] for i in items if i["id"] == code)
        mapped = [(canon(c0, n0), q) for c0, n0, q in members if n0 and n0 != name]
        combos.append({"id": str(code), "name": name, "price": price,
                       "includes": [c0 for c0, q in mapped for _ in range(q)]})
        print("  ✓ %-22s %6.1f 元  含 %s" % (name, price,
              "、".join("%s%s" % (next((i["name"] for i in items if i["id"] == c0), c0),
                                  "" if q == 1 else "×%d" % q) for c0, q in mapped)))

    coupons, unknown = ([], [])
    if not a.no_coupons:
        try:
            coupons, unknown = fetch_coupons(c, items)
            print("可领券 %d 张（无法自动计算 %d 张）" % (len(coupons), len(unknown)))
            for cp in coupons:
                print("  ✓ %-22s 省 %5.1f 元" % (cp["name"], cp["value"]))
            for u in unknown:
                print("  – %s（需人工判断）" % u)
        except Exception as e:
            print("  ✗ 券获取失败：%s" % e)

    out = {"_notice": "由 scripts/load_menu.py 从麦当劳 MCP 实时生成；价格随门店与时段变化",
           "currency": "CNY", "store": a.store,
           "items": items, "combos": combos, "coupons": coupons, "promos": []}
    Path(a.out).write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode("utf-8"))
    print("\n已写入 %s（items %d / combos %d）" % (a.out, len(items), len(combos)))
    print("提示：券与满减需另取（query-store-coupons / available-coupons），当前留空。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
