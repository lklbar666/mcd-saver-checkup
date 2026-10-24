# 体检计划与批量核价

## 谁来准备计划

AI根据用户实际点法和真实门店数据构造体检计划。脚本不猜菜单、不自动挑选套餐。计划包含每种买法的实际组成和完整官方核价参数，不填价格。

`examples/plan-template.json`展示结构，所有编码均虚构，`data_kind: demo`禁止联网。实际计划写入`private/audit-plan.json`，标为`data_kind: live`。

## 顶层字段

- `data_kind`：真实计划为`live`；模板为`demo`
- `store`：实际门店编码，与每份`arguments.storeCode`完全相同
- `mode`：`pickup`到店取餐；外送为`delivery`
- `budget_cents`：整数分，不允许小数或负数
- `required_codes`：用户实际点的餐品编码
- `required_quantities`：实际编码到最低份数
- `excluded_codes`：明确不要的餐品编码
- `excluded_terms`：名称文字匹配排除
- `candidates`：候选买法，每份含唯一`id`、`title`、`items`、`conditions`、`arguments`

`items`按报价格式列出实际组成。父套餐用`container: true`，不计入必选数量。

`arguments`必须按官方当前工具schema构造。核价前确认金额单位为分。

## 候选买法类型

每份候选代表一种买法：

1. `single`：全部单点
2. `combo`：套餐覆盖部分餐品
3. `combo-plus`：套餐+补单点
4. `combo-coupon`：套餐+券
5. `single-discount`：单点+满减
6. `single-coupon`：单点+券

## 套餐和优惠券

- 套餐必须提供完整的`roundList`和每轮实际子项
- 券来自该用户该门店的当前可用券，使用时提供真实couponId
- 满减与券默认二选一
- 特调必须包含当前详情要求的selectedKey/unselectedKey

## 命令

```bash
# 本地结构检查，不联网
python skills/mcd-saver-checkup/scripts/quote_audits.py examples/plan-template.json --check-plan

# 真实计划：批量核价与比较
python skills/mcd-saver-checkup/scripts/quote_audits.py private/audit-plan.json --use-workbuddy-config --records-dir private/run-001
```

每轮使用新的空记录目录。指定记录目录后自动生成`comparison.json`和`audit-report.html`。

## 失败规则

1. 计划有冲突或组成不一致：整个计划拒绝，错误标明是哪份候选
2. 核价失败：停止后续候选，保留已成功结果，不重试
3. 价格缺失或回显不一致：不生成猜测价格
4. 比较时缺少必选数量或含排除项：归入未纳入

退出码：0完成；1核价失败；2计划或本地处理失败。
