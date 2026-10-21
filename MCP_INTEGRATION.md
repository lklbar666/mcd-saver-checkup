# MCP 集成说明

本项目基于 **麦当劳中国 MCP Server**（`https://mcp.mcd.cn`，streamable HTTP，`Authorization: Bearer <MCP_TOKEN>`）。

## 一、使用的 Tool

| Tool | 在本项目中的用途 | 调用时机 |
|---|---|---|
| `now-time-info` | 判定当前时段（早餐/正餐），避免用错菜单 | 每次会话开始 |
| `query-nearby-stores` | 定位门店，拿到该店菜单与可用券 | 用户首次给出位置 |
| `query-meals` | 拉取当前门店可售餐品与价格 | 构建比价基础数据 |
| `query-meal-detail` | 读取套餐组成与可替换项，用于判断「套餐是否覆盖你的需求」 | 枚举套餐方案时 |
| `query-store-coupons` | 该门店可用的券 | 券方案计算 |
| `available-coupons` / `auto-bind-coupons` | 麦麦省可领券列表；用户确认后一键领取 | 给出「领券后再买」建议时 |
| `calculate-price` | **核心**：对每个候选方案精算应付总额（含配送费、优惠） | 每个方案一次 |
| `order-list` | 历史订单，用于「习惯审计」 | 功能 ③ |

## 二、调用链

```
用户：帮我体检一下：巨无霸 + 中薯条 + 中可乐

1. now-time-info            → 当前时段，确认用哪套菜单
2. query-nearby-stores      → 门店 id
3. query-meals(store)       → 餐品列表 + 价格
4. query-meal-detail(...)   → 套餐组成（用于判断覆盖关系）
5. query-store-coupons      → 可用券
6. [本地引擎]                → 枚举「单点 / 套餐组合 / 补单点」的候选方案
7. calculate-price(每方案)  → 官方口径的应付金额（逐个复算）
8. [本地引擎]                → 排序、算差额、归因、算加购临界点
9. 输出报告
```

**关键设计**：第 6、8 步在本地完成，第 7 步回到官方接口。也就是说——**方案由本地算，价格由官方定**。这样既避免「模型拍脑袋报价」，也让每个数字都能被用户复算。

## 三、为什么不用一次 `calculate-price` 就算完

`calculate-price` 只回答「这一篮子多少钱」，不回答「还有没有更便宜的买法」。
省钱的关键在**搜索空间**：同一组需求可以由「单点」「某套餐」「套餐+补单点」等多种方式满足，价格差异往往来自套餐结构与券的适用范围。

本项目把 `calculate-price` 当作**裁判**而不是**顾问**：本地枚举候选，官方接口逐个判价。

## 四、业务价值

| 对用户 | 对麦当劳 |
|---|---|
| 知道同一顿饭的多种买法与真实差额 | 把「比价」从站外拉回站内，减少用户去第三方比价 |
| 避免「为满减而多买」的隐性浪费 | 券的核销路径更短（一键领券 → 直接下单） |
| 有可核对、可分享的账单 | 省钱话题天然带传播，且结论对品牌中立偏正面 |

## 五、边界与合规

- 只读取用户**本人**授权范围内的数据（订单、券、积分），不存储 Token 与订单原文。
- 不代替用户下单；如需下单，走 `create-order` 且由用户显式确认。
- 价格与库存以接口实时返回为准；本项目不做价格承诺。
- 配置文件仅使用环境变量占位符，不含真实 Token（见参赛声明的信息安全条款）。

## 六、字段适配说明

麦当劳 MCP 的返回结构以官方文档为准。`scripts/mcd_mcp.py` 只做传输与 `tools/call` 封装，**不做字段假设**；`scripts/audit.py` 通过 `data/mock_menu.json` 定义的内部结构解耦。
首次接入时执行：

```bash
python scripts/mcd_mcp.py --ping          # 验证 Token
python scripts/mcd_mcp.py --tools         # 列出可用工具
python scripts/mcd_mcp.py --dump query-meals '{"storeId": "..."}' --out raw.json
```

把真实返回字段映射进 `data/menu.json`（结构与 `mock_menu.json` 相同），引擎即可用真实数据运行。
