---
name: mcd-saver-checkup
display_name: "麦门省钱体检"
display_name_en: "McDonald's Saver Checkup"
description: "麦当劳省钱体检：不看你想吃什么，先看你已经亏在哪。输入你实际的点法或历史订单，枚举所有可行买法（单点/套餐/券/满减），用麦当劳MCP的calculate-price逐个复算，报出差额、归因与凑单临界点。支持批量核价、HTML交互报告和离线恢复。触发词：省钱、体检、比价、买贵、凑单、满减、优惠券、套餐、差价、审计、复盘。"
description_zh: "麦当劳省钱体检Skill。输入实际点法或历史订单，枚举所有可行买法（单点/套餐/券/满减），用calculate-price逐个复算，报差额、归因与凑单临界点。支持最多批量核价、自动生成HTML交互报告、整数分精确计算和离线恢复。"
description_en: "A McDonald's China savings audit skill. Enumerate all purchase methods for your order, verify each via official calculate-price, and report price gaps, attribution, and bundle thresholds. Includes batch verification, interactive HTML reports, and offline recovery."
category: education
version: 2.0.0
author: lklbar666
---

# 麦门省钱体检

**核心定位**：不看你想吃什么，先看你已经亏在哪。方案由本地枚举，价格由官方判定。

## 什么时候用

- 用户给出「我常点X+Y+Z」，想知道有没有更省的买法
- 用户问「满60减12，我要不要凑」
- 用户想复盘历史订单「有没有买贵」
- 用户问「这两个套餐哪个更值」

## 什么时候不用

- 只想下单 → 用点餐流程
- 问营养/热量 → 用list-nutrition-foods
- 要求「保证最低价」→ 只能给当前接口口径下的最优，不能承诺

## 收集需求

从对话提取：门店或位置、实际点法（餐品+数量）、是否有券、预算上限。
默认单人、到店取餐。外送需注明配送费。缺门店时询问，不推测用户地址。

将偏好转成可检查约束：
- 实际餐品用required_codes和required_quantities
- 不要的餐品用excluded_codes，名称匹配用excluded_terms
- 不把父套餐计入实际餐品份数

## 工作流

### 第一步：取数

1. now-time-info → 判定当前时段（早餐/正餐）
2. query-nearby-stores → 定位门店
3. query-meals → 拉取门店菜单和价格
4. query-meal-detail → 读取套餐组成与可替换项

### 第二步：取优惠

5. query-store-coupons → 门店可用券
6. available-coupons → 可领券列表，提示「先领再算」
7. 满减与券默认二选一；数据标明可叠加才叠加

### 第三步：枚举候选买法

本地生成所有可行买法：
- 全部单点
- 套餐组合（哪些餐品可以被套餐覆盖）
- 套餐+补单点
- 套餐+券
- 单点+满减
- 单点+券

### 第四步：批量核价

对每个候选调用calculate-price，取官方应付金额。
宿主允许执行脚本时，优先读取@references/audit-plan.md，将完整核价参数写入体检计划，用scripts/quote_audits.py完成批量核价与自动比较。

核价规则：
- 请求中的门店、取餐方式、餐品和券保持一致
- 仅成功核价的方案进入比较
- 金额归一化为整数分，避免浮点误差
- 每次修改餐单都重新核价，不用旧价加减菜单价

### 第五步：排序归因

算差额，指出省在哪一项：
- 换套餐省了多少
- 用券省了多少
- 满减省了多少
- 套餐+券组合省了多少

### 第六步：凑单体检

对每个未达门槛的满减，计算：
- 还差多少达到门槛
- 最少加购多少钱的餐品
- 能省多少
- 净赚还是净亏（省的金额−加购金额）

### 第七步：生成报告

批量核价后自动生成：
- comparison.json：结构化比较结果
- audit-report.html：可交互报告（调预算、看差价、复制结果）

报告只提取展示字段，不嵌入原始请求、认证或券实例编码。

## 输出契约

```
一、你点的是        商品×数量，单点合计
二、能怎么买        表格：买法/实付/比原样省/备注（多得什么）
三、最优            一句话：哪个买法、实付多少、省多少
四、账单拆解        逐项列出套餐、券、满减各贡献多少
五、凑单体检        每个门槛：差多少、要加购多少、净赚/净亏
```

## 硬规则

- 每个金额必须来自calculate-price，不得自行估算
- 满减与券默认二选一
- 「多得」的商品必须显式标出，不能假装是同一样东西
- 结尾必须给一个可执行动作（领券/换套餐/别凑）
- 价格、库存和券适用性以官方当前结果为准

## 失败处理

- 核价失败：停止后续请求，保留已成功报价及失败原因，不自动重试
- 报告导出失败：终端仍保留有效结果，可从comparison.json离线恢复
- 401：提示检查连接器配置
- 429：停止本轮调用
- 遇到参数校验错误：立即停止，不轮换参数试探

## WorkBuddy兼容性

如WorkBuddy核价报告/items: must be array等数组校验问题，不再经同一入口重试。读取@references/workbuddy-compatibility.md，使用项目内的MCP直连脚本mcp_query.py，绕过延迟工具入口。

## 参考资料索引

| 文件 | 内容 |
|---|---|
| @references/audit-plan.md | 体检计划格式与批量核价参数 |
| @references/quote-format.md | 本地报价格式与数据结构 |
| @references/workbuddy-compatibility.md | WorkBuddy数组校验问题的直连方案 |

## 脚本索引

| 脚本 | 用途 |
|---|---|
| scripts/quote_audits.py | 批量核价与自动比较 |
| scripts/compare_audits.py | 离线金额检查、排序、Markdown输出 |
| scripts/report_audits.py | 生成HTML交互报告 |
| scripts/mcp_query.py | MCP直连客户端（绕过WorkBuddy校验问题） |
| scripts/audit.py | 省钱体检核心引擎（枚举+归因+凑单） |

## 适用边界

- 只查询和核价，不调用创建订单、支付、领券工具
- 仅覆盖本轮候选，不保证全菜单最低价
- 营养、配料与过敏原未纳入推荐
- 只读取用户本人授权范围内的数据
- 不存储Token与订单原文
