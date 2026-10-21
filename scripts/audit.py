#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦门省钱体检 · 差价引擎

输入：你想要/已经点的一单（商品名或商品编码 + 数量）
输出：
  1. 所有可行买法的实付对比（原样单点 / 换套餐 / 用券 / 凑满减）
  2. 最优方案与差额
  3. 差额归因（亏在哪一步）
  4. 凑单临界建议（为了满减加购，到底省不省）

设计原则：
  - 纯标准库，无第三方依赖
  - 每个数字都能用 MCP 的 calculate-price 复算 —— 引擎只做「枚举 + 比价」，
    价格永远来自数据源，不自行编造
  - 数据源可以是 MCP 实时返回，也可以是离线 JSON（用于演示与回归测试）

用法：
  python scripts/audit.py --demo
  python scripts/audit.py --menu data/mock_menu.json --basket "巨无霸,中薯条,可口可乐"
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- 数据模型
@dataclass(frozen=True)
class Item:
    id: str
    name: str
    price: float
    category: str = ""


@dataclass(frozen=True)
class Combo:
    id: str
    name: str
    price: float
    includes: Tuple[str, ...]          # item_id 列表
    replaceable: bool = False          # 是否允许替换组内商品


@dataclass(frozen=True)
class Coupon:
    id: str
    name: str
    kind: str                          # amount（立减）/ percent（折扣）/ threshold（满减）
    value: float                       # 金额或折扣率（0.9 = 9 折）
    min_spend: float = 0.0
    item_ids: Tuple[str, ...] = ()     # 限定商品；空表示全场
    stackable: bool = False            # 是否可与满减叠加（默认不可，宁可保守）


@dataclass
class Plan:
    label: str
    cost: float                        # 正餐合计（不含配送）
    detail: List[str] = field(default_factory=list)
    surplus: List[str] = field(default_factory=list)   # 多得但没要求的东西
    coupon: Optional[str] = None
    combo_ids: List[str] = field(default_factory=list)
    note: str = ""


# --------------------------------------------------------------------------- 工具
def money(x: float) -> str:
    return ("%.2f" % x).rstrip("0").rstrip(".") if x % 1 else "%d" % x


def load_menu(path: Path) -> Tuple[Dict[str, Item], List[Combo], List[Coupon]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = {i["id"]: Item(i["id"], i["name"], float(i["price"]), i.get("category", ""))
             for i in raw["items"]}
    combos = [Combo(c["id"], c["name"], float(c["price"]), tuple(c["includes"]),
                    bool(c.get("replaceable", False))) for c in raw.get("combos", [])]
    coupons = [Coupon(c["id"], c["name"], c["kind"], float(c["value"]),
                      float(c.get("min_spend", 0)), tuple(c.get("item_ids", [])),
                      bool(c.get("stackable", False)))
               for c in raw.get("coupons", [])]
    return items, combos, coupons


def resolve_basket(text: str, items: Dict[str, Item]) -> Dict[str, int]:
    """把「巨无霸,中薯条,可乐x2」解析成 {item_id: qty}。支持编码或名称片段。"""
    out: Dict[str, int] = {}
    for chunk in [c.strip() for c in text.replace("，", ",").split(",") if c.strip()]:
        qty = 1
        if "x" in chunk.lower():
            name, _, n = chunk.lower().rpartition("x")
            if n.strip().isdigit():
                qty, chunk = int(n), chunk[:len(name)]
        chunk = chunk.strip()
        hit = None
        if chunk in items:
            hit = chunk
        else:
            cands = [i for i in items.values() if chunk and chunk in i.name]
            if cands:
                cands.sort(key=lambda i: len(i.name))
                hit = cands[0].id
        if not hit:
            raise SystemExit("找不到商品：%s（先用 --list 看看有什么）" % chunk)
        out[hit] = out.get(hit, 0) + qty
    return out


# --------------------------------------------------------------------------- 比价
def combo_coverage(combo: Combo, wanted: Dict[str, int]) -> Dict[str, int]:
    """这个套餐能覆盖掉多少需求（不超过需求数量）。"""
    got: Dict[str, int] = {}
    for iid in combo.includes:
        if wanted.get(iid, 0) > got.get(iid, 0):
            got[iid] = got.get(iid, 0) + 1
    return got


def apply_coupon(cost: float, wanted: Dict[str, int], coupon: Coupon,
                 prices: Dict[str, float]) -> Tuple[float, bool, str]:
    """返回（优惠后金额, 是否可用, 说明）。"""
    if cost < coupon.min_spend:
        return cost, False, "未达门槛 %s" % money(coupon.min_spend)
    if coupon.item_ids:
        sub = sum(prices.get(i, 0) * q for i, q in wanted.items() if i in coupon.item_ids)
        if sub <= 0:
            return cost, False, "不含指定商品"
        base = sub
    else:
        base = cost
    if coupon.kind == "amount":
        off = min(coupon.value, base)
    elif coupon.kind == "percent":
        off = base * (1 - coupon.value)
    elif coupon.kind == "threshold":
        off = min(coupon.value, base)
    else:
        return cost, False, "未知券类型"
    return cost - off, True, "省 %s" % money(off)


def apply_promos(cost: float, promos: Sequence[dict]) -> Tuple[float, str]:
    """满减：取所有已满足门槛的活动中优惠最大的一条。"""
    best_off, best_name = 0.0, ""
    for pr in promos:
        if cost >= float(pr["threshold"]) and float(pr["off"]) > best_off:
            best_off, best_name = float(pr["off"]), pr.get("name") or "满%s减%s" % (
                money(float(pr["threshold"])), money(float(pr["off"])))
    return cost - best_off, best_name


def enumerate_plans(wanted: Dict[str, int], items: Dict[str, Item], combos: List[Combo],
                    coupons: Sequence[Coupon] = (), promos: Sequence[dict] = (),
                    max_combos: int = 4) -> List[Plan]:
    """枚举「套餐 + 补单点」的所有组合，再对每种组合试券。"""
    prices = {i.id: i.price for i in items.values()}
    relevant = [c for c in combos if any(i in wanted for i in c.includes)]
    plans: List[Plan] = []

    # 组合数控制：按「覆盖需求数」排序，只取前 N 个参与枚举
    relevant.sort(key=lambda c: -len(combo_coverage(c, wanted)))
    relevant = relevant[:10]

    for r in range(0, min(max_combos, len(relevant)) + 1):
        for combo_set in itertools.combinations(relevant, r):
            remaining = dict(wanted)
            cost = 0.0
            lines: List[str] = []
            surplus: List[str] = []
            for c in combo_set:
                cost += c.price
                lines.append("%s %s" % (c.name, money(c.price)))
                for iid in c.includes:
                    if remaining.get(iid, 0) > 0:
                        remaining[iid] -= 1
                    else:
                        surplus.append(items[iid].name if iid in items else iid)
            for iid, q in remaining.items():
                if q <= 0:
                    continue
                cost += prices[iid] * q
                lines.append("%s×%d %s" % (items[iid].name, q, money(prices[iid] * q)))
            if not combo_set:
                lines = ["%s×%d %s" % (items[i].name, q, money(prices[i] * q))
                         for i, q in wanted.items()]
            label = "单点" if not combo_set else " + ".join(c.name for c in combo_set)
            plans.append(Plan(label, round(cost, 2), lines, surplus,
                              combo_ids=[c.id for c in combo_set]))

    # 满减与券的叠加：默认二选一；只有券标了 stackable 才允许叠
    expanded: List[Plan] = []
    for p in plans:
        base_cost, base_detail = p.cost, list(p.detail)
        prom_cost, pname = apply_promos(base_cost, promos)
        prom_detail = base_detail + (["满减：%s（省 %s）" % (pname, money(base_cost - prom_cost))]
                                     if pname else [])

        # A. 不用券（可能已含满减）
        expanded.append(Plan(p.label, round(prom_cost, 2), prom_detail, p.surplus,
                             combo_ids=p.combo_ids))
        # B. 用券：默认只在不叠满减的原始价上算；stackable 才叠在满减后
        for cp in coupons:
            anchor = prom_cost if cp.stackable else base_cost
            new_cost, ok, note = apply_coupon(anchor, wanted, cp, prices)
            if ok and new_cost < prom_cost - 0.001:
                detail = base_detail + (["满减：%s（省 %s）" % (pname, money(base_cost - prom_cost))]
                                        if (pname and cp.stackable) else [])
                detail = detail + ["用券：%s（%s）%s" % (cp.name, note,
                                                        "" if cp.stackable else "，不与满减叠加")]
                expanded.append(Plan(p.label + " + " + cp.name, round(new_cost, 2), detail,
                                     p.surplus, coupon=cp.name, combo_ids=p.combo_ids))
    # 去重（同价同券只留一条）
    seen = set()
    uniq: List[Plan] = []
    for p in sorted(expanded, key=lambda x: x.cost):
        key = (round(p.cost, 2), p.label, p.coupon)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def threshold_advice(total: float, promos: Sequence[dict], items: Dict[str, Item]) -> List[str]:
    """满减凑单建议：加购到门槛是否真的划算。"""
    out = []
    cheapest = sorted(((i.price, i.name) for i in items.values()), key=lambda x: x[0])
    for pr in promos:
        need, off = float(pr["threshold"]), float(pr["off"])
        name = pr.get("name", "满%s减%s" % (money(need), money(off)))
        if total >= need:
            out.append("%s：已满足（当前 %s）" % (name, money(total)))
            continue
        gap = need - total
        # 找最便宜的组合把差额补上
        pick, spent = [], 0.0
        for price, iname in cheapest:
            if spent >= gap:
                break
            pick.append("%s(%s)" % (iname, money(price)))
            spent += price
        net = off - spent
        if net > 0:
            out.append("%s：差 %s，加购 %s 花 %s，省 %s → **划算，净省 %s**"
                       % (name, money(gap), " + ".join(pick), money(spent), money(off), money(net)))
        else:
            out.append("%s：差 %s，最少要加购 %s 花 %s，只减 %s → **不划算，净亏 %s**"
                       % (name, money(gap), " + ".join(pick), money(spent), money(off), money(-net)))
    return out


def audit(wanted: Dict[str, int], items: Dict[str, Item], combos: List[Combo],
          coupons: Sequence[Coupon], promos: Sequence[dict]) -> dict:
    prices = {i.id: i.price for i in items.values()}
    baseline = round(sum(prices[i] * q for i, q in wanted.items()), 2)
    plans = enumerate_plans(wanted, items, combos, coupons, promos)
    best = plans[0]
    verdict = threshold_advice(best.cost, promos, items)
    return {
        "basket": [{"id": i, "name": items[i].name, "qty": q,
                    "sum": round(prices[i] * q, 2)} for i, q in wanted.items()],
        "baseline": baseline,
        "plans": plans,
        "best": best,
        "saving": round(baseline - best.cost, 2),
        "threshold": verdict,
    }


# --------------------------------------------------------------------------- CLI
def render(result: dict) -> str:
    L = []
    L.append("## 你点的是")
    for b in result["basket"]:
        L.append("- %s ×%d　%s 元" % (b["name"], b["qty"], money(b["sum"])))
    L.append("")
    L.append("按单点算：**%s 元**" % money(result["baseline"]))
    L.append("")
    L.append("## 同样这些东西，能怎么买")
    L.append("")
    L.append("| 买法 | 实付 | 比原样省 | 备注 |")
    L.append("|---|---:|---:|---|")
    for p in result["plans"][:6]:
        note = ("多得 " + "、".join(p.surplus)) if p.surplus else ""
        L.append("| %s | %s | %s | %s |" % (p.label, money(p.cost),
                                            money(result["baseline"] - p.cost), note))
    L.append("")
    best = result["best"]
    L.append("**最优：%s，实付 %s 元，省 %s 元。**"
             % (best.label, money(best.cost), money(result["saving"])))
    L.append("")
    L.append("账单拆解：")
    for d in best.detail:
        L.append("- %s" % d)
    if best.surplus:
        L.append("- 顺带多得：%s" % "、".join(best.surplus))
    L.append("")
    if result["threshold"]:
        L.append("## 凑单体检（从最优方案出发）")
        for t in result["threshold"]:
            L.append("- %s" % t)
        L.append("")
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="麦门省钱体检 · 差价引擎")
    ap.add_argument("--menu", default=str(ROOT / "data" / "mock_menu.json"))
    ap.add_argument("--basket", default="")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--list", action="store_true", help="列出菜单")
    ap.add_argument("--out", default="", help="把报告写到文件")
    a = ap.parse_args(argv)

    items, combos, coupons = load_menu(Path(a.menu))
    promos = json.loads(Path(a.menu).read_text(encoding="utf-8")).get("promos", [])

    if a.list:
        for i in sorted(items.values(), key=lambda x: x.category):
            print("%-10s %-18s %6s" % (i.id, i.name, money(i.price)))
        return 0

    basket = "巨无霸,中薯条,可口可乐" if a.demo else a.basket
    if not basket:
        ap.error("要么给 --basket，要么用 --demo")

    wanted = resolve_basket(basket, items)
    res = audit(wanted, items, combos, coupons, promos)
    text = render(res)
    print(text)
    if a.out:
        Path(a.out).write_bytes(text.encode("utf-8"))
        print("\n（已写入 %s）" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
