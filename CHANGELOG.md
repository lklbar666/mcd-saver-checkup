# 更新日志

## [2.0.0] - 2026-10-24

### 新增
- 标准Skill目录结构：skills/mcd-saver-checkup/，含SKILL.md、references/、scripts/
- 批量核价脚本quote_audits.py：一次完成所有候选买法的核价与比较
- 离线比较脚本compare_audits.py：整数分金额检查、排序、Markdown/JSON输出
- HTML交互报告生成report_audits.py：可调预算、看差价、复制结果
- MCP直连客户端mcp_query.py：绕过WorkBuddy数组校验问题
- references参考文档：audit-plan.md、quote-format.md、workbuddy-compatibility.md
- 测试套件：test_saver_checkup.py、test_reliability.py、test_reports.py、check_report.cjs
- 安装脚本install.ps1：自动备份旧版、部署技能目录
- MCP配置示例：mcp-config.example.json、mcp-config.workbuddy.example.json
- docs文档：quick-start.md、report-guide.md
- examples示例：批量验证、报价快照、计划模板
- .gitignore：private目录保护
- 整数分精确计算，避免浮点误差
- 失败处理：保留成功结果、不重试、离线恢复

### 保留
- 省钱体检核心定位：枚举所有买法，逐个复算
- audit.py核心引擎：枚举+归因+凑单体检
- 凑单临界点计算
- 差价归因（套餐/券/满减各贡献多少）

## [1.0.0] - 2026-10-20

### 初始版本
- 省钱体检Skill基础功能
- 枚举单点/套餐/券/满减买法
- calculate-price逐个复算
- 差额报告与凑单体检
- 菜单数据加载
