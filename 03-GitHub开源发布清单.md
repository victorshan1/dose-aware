# 知醒 DoseAware：GitHub 开源发布清单

这份清单用于把本地已经完成的 v0.1 原型发布到 GitHub。核心代码不需要继续修改。

## 1. 创建空仓库

在 GitHub 创建公开仓库：

- Repository name：`dose-aware`
- Description：`面向发作性睡病场景的开源服药安全参考系统：确定性状态机、设备模拟器、Web 演示与故障测试。`
- Visibility：Public
- 不勾选 README、`.gitignore` 和 License（本地已经具备）

建议 Topics：

```text
narcolepsy medication-safety digital-health fastapi python sqlite state-machine assistive-technology open-source
```

## 2. 推送本地仓库

将 `<你的用户名>` 替换为 GitHub 用户名：

```bash
cd "C:/Users/victo/WorkBuddy/2026-10-01-15-11-05/dose-aware"
git remote add origin https://github.com/<你的用户名>/dose-aware.git
git push -u origin main
```

如果已经添加过 `origin`，使用：

```bash
git remote set-url origin https://github.com/<你的用户名>/dose-aware.git
git push -u origin main
```

## 3. 发布后检查

- GitHub 仓库首页能正确显示中文 README；
- 右侧 About 显示 Apache-2.0 License；
- Actions/代码扫描没有提示密钥泄露；
- 仓库里没有 `.db`、`.env`、`.venv-packages`、`__pycache__`；
- `docs/` 下的中文文件名和链接可正常打开；
- 默认分支为 `main`；
- Issues 已开启，方便患者、照护者和开发者反馈。

## 4. 建议建立的第一个 Release

- Tag：`v0.1.0`
- Title：`知醒 DoseAware v0.1.0 — 核心闭环原型`
- 状态：Pre-release

Release 摘要：

```markdown
知醒 DoseAware 是面向发作性睡病场景的开源服药安全参考系统。本版本完成了“提醒—响应—开盒—记录—防重复—异常升级”核心闭环，并提供 Python 硬件模拟器、FastAPI 服务、SQLite 持久化、患者/照护者 Web 演示与 21 项自动化测试。

重要边界：开盒不等于已经服药；当前项目不是医疗器械，不构成医学建议，也未经真实患者、实体硬件和监管场景验证。
```

## 5. 第一条推广文案

```markdown
我把一次没能在线下继续完成的罕见病黑客松项目，整理成了一个开源仓库：知醒 DoseAware。

它面向发作性睡病患者在刚醒、意识模糊、小睡后醒来时可能遇到的服药安全问题，尝试用确定性状态机完成提醒、开盒记录、防重复和异常通知。项目包含 FastAPI、SQLite、Python 硬件模拟器、患者/照护者 Web 页面和 21 项测试。

它没有实体药盒，也不是医疗器械。开盒不等于服药，AI 也不参与剂量、安全间隔或解锁决策。

如果它能给后来者一点参考，就有价值；如果不能，也算为这次比赛、为这个真实的问题，留下一个小小的符号。

GitHub：<仓库链接>
```

## 6. 暂时不要承诺的内容

- 不写“可直接用于患者”；
- 不写“防止漏服或重复服药”；应写“用于验证相关流程”；
- 不写“AI 智能决策剂量”；
- 不写“已验证震动能够唤醒患者”；
- 不写“医疗级”“临床级”“已通过认证”。

## 当前本地验证结果

- 自动化测试：21 项通过；
- 许可证：Apache-2.0 官方完整文本；
- 敏感信息：未发现真实 API Key、私钥或密码；
- git 跟踪：未包含数据库、缓存、虚拟依赖目录和 `.env`；
- 核心功能：保持 v0.1，不再为发布临时扩展功能。
