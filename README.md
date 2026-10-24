![Python 3.10+](assets/badges/python.svg) ![零第三方依赖](assets/badges/stdlib.svg) ![离线预览免Token](assets/badges/preview.svg) ![MCP官方核价](assets/badges/mcp.svg) ![MIT许可](assets/badges/license.svg)

<h3 align="center">不看你想吃什么，先看你已经亏在哪。</h3>

<p align="center">基于麦当劳中国MCP的省钱审计Skill。<br>输入你实际的点法，枚举所有买法，用官方calculate-price逐个复算，报差额、归因与凑单临界点。</p>

<p align="center">
<a href="#先看效果">先看效果</a> · <a href="#安装使用">安装使用</a> · <a href="#如何工作">如何工作</a> · <a href="#使用问答">使用问答</a>
</p>

## 先看效果

**同一顿饭，换个买法能省多少？** 适合想知道自己常点的组合有没有更便宜买法、犹豫要不要为满减凑单的用户。

| 你现在想做什么 | 从这里开始 |
|---|---|
| 看看差价报告 | 查看[示例](examples/demo-quotes.json)：不同买法的核价对比 |
| 用自己的门店核价 | [安装Skill](#安装使用)，连接自己的麦当劳MCP |

每次核价后自动生成`audit-report.html`，可以调预算、看差价、复制结果。报告只包含本轮有效报价，不联网。

## 真实案例

> 帮我体检一下：巨无霸+中薯条+中可乐

```
按单点算：45元

| 买法 | 实付 | 比原样省 |
|---|---:|---:|
| 巨无霸套餐+立减5元 | 34.5 | 10.5 |
| 单点+满40减8 | 37 | 8 |
| 单点 | 39 | 6 |

最优：巨无霸套餐+立减5元，实付34.5元，省10.5元。

凑单体检：满45减6还差10.5，最少加购14元才够，
只减6元→净亏8元，不建议凑。
```

| 还可以这样问 | 它会处理什么 |
|---|---|
| 不要可乐，汉堡保留 | 替换后对完整餐单重新核价 |
| 满60减12要不要凑 | 算加购临界点，判断净赚还是净亏 |
| 复盘最近订单 | 用历史订单对比所有买法 |

## 安装使用

需要支持远程MCP的AI客户端（WorkBuddy、Cherry Studio、Cursor等），以及麦当劳MCP Token。配套脚本需要Python 3.10+，使用标准库，无第三方依赖。

1. 到[麦当劳MCP平台](https://open.mcd.cn/mcp)登录、激活Token，连接`https://mcp.mcd.cn`，协议Streamable HTTP。
2. 下载并解压仓库。WorkBuddy运行`./install.ps1`，或导入`skills/mcd-saver-checkup`文件夹。
3. 新开会话，发送：

```text
使用麦门省钱体检技能。帮我体检：巨无霸+中薯条+中可乐。
用我的麦当劳MCP枚举所有买法，逐个核价，报差额和凑单临界点。不下单。
```

[详细点击步骤](docs/quick-start.md)

## 如何工作

AI负责理解需求、查询真实菜单和枚举候选买法；官方`calculate-price`返回整单应付金额；本地脚本按整数分检查预算、份数、去重和排序。

| 容易卡住的地方 | 怎样处理 |
|---|---|
| 看得到套餐价，不清楚实际组成 | 核对套餐轮次、替换项与实际数量 |
| 换了餐品，还在沿用旧价格 | 每次修改都重新核价 |
| 不知道省在套餐还是券 | 逐项归因：套餐、券、满减各贡献多少 |
| 为满减凑单可能亏 | 算加购临界点，判断净赚还是净亏 |
| 后面的接口失败，前面结果丢了 | 停止后续请求，保留成功报价 |
| 报告导出失败 | 从comparison.json离线恢复 |

## 验证记录

| 范围 | 验证内容 |
|---|---|
| Python逻辑 | 离线回归，含预算检查、去重、导出失败恢复 |
| 页面逻辑 | 模拟DOM场景，含复制回退、结果清理 |
| 安装升级 | 临时配置目录检查，含旧文件清理、私人记录保留 |

## 使用问答

<details>
<summary><b>必须用WorkBuddy吗？核价报数组错误怎么办？</b></summary>

支持远程MCP的客户端都可以。WorkBuddy出现数组校验问题时，使用项目内的Python直连路径mcp_query.py，见[兼容说明](skills/mcd-saver-checkup/references/workbuddy-compatibility.md)。

</details>

<details>
<summary><b>Token和私人信息保存在哪里？</b></summary>

认证只从用户私有配置或环境变量读取，项目不提供Token代理。原始请求和响应留在本机`private/`，已被Git忽略。分享前请脱敏。

</details>

<details>
<summary><b>能保证最低价吗？</b></summary>

不能。结果只覆盖本轮枚举的候选买法，不保证全菜单最低价。价格以官方当前结果为准。

</details>

## 项目结构

```text
mcd-saver-checkup/
├── skills/mcd-saver-checkup/
│   ├── SKILL.md              # 技能定义
│   ├── references/           # 参考文档
│   │   ├── audit-plan.md
│   │   ├── quote-format.md
│   │   └── workbuddy-compatibility.md
│   └── scripts/              # 可执行脚本
│       ├── quote_audits.py   # 批量核价
│       ├── compare_audits.py # 离线比较
│       ├── report_audits.py  # 报告生成
│       ├── mcp_query.py      # MCP直连
│       └── audit.py          # 体检引擎
├── tests/                    # 测试
├── docs/                     # 文档
├── examples/                 # 示例
├── data/                     # 数据
└── assets/badges/            # 徽章
```

[版本说明](CHANGELOG.md) · [MCP集成](MCP_INTEGRATION.md)

## 边界

- 只查询和核价，不下单、不支付、不领券
- 仅覆盖本轮候选，不保证全菜单最低价
- 营养、配料与过敏原未纳入
- 不存储Token与订单原文

## 许可与声明

本项目原创Skill、脚本和示例使用[MIT License](LICENSE)。完整[参赛声明](CONTEST_DECLARATION.md)已保留原文。

本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。使用麦当劳MCP须遵守官方服务规则。

项目中的菜单数据、示例报价和核价结果仅用于技术演示，价格及餐品供应状态以麦当劳官方渠道实时返回为准。本项目不构成营养、医疗或投资建议。
