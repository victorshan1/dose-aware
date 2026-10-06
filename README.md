# 知醒 DoseAware

> 醒来即知，服药更安心。

面向发作性睡病患者的开源服药安全系统。第一阶段通过确定性服药状态机和 Python 硬件模拟器，验证“提醒—响应—开盒—记录—防重复—异常升级”闭环；未来可按统一设备协议接入 ESP32、T5-core 或实体药盒。

## 当前状态

这是 **v0.1 核心闭环原型**：

- 已实现确定性服药会话状态机；
- 已实现设备事件和设备命令协议；
- 已实现重复事件幂等处理；
- 已实现正常开盒、保护期锁定、重复开盒风险、无响应升级和应急解锁逻辑；
- 已实现 Python CLI 场景模拟器和交互式虚拟药盒；
- 交互式药盒支持提醒、患者响应、开盒、断网/上线、低电量和应急解锁事件；
- 已实现 SQLite 持久化，会话、事件幂等、审计和照护者通知可在服务重启后恢复；
- 已实现会话列表、会话详情、审计记录和通知查询 API；
- 已实现响应式患者端与照护者端 Web，可运行四类数字孪生场景；
- 已实现 21 个状态机、API、Web、设备模拟和故障场景自动化测试；
- 患者端支持隐私模式切换，照护者端支持确认异常通知；
- 真实远程通知和实体硬件仍属于下一阶段；
- 当前没有实体硬件，模拟器结果不等于真实震动、机械锁或实际服药证明。

**开盒不等于已服药。**系统只记录设备观察到的开盒和响应事件。

## 快速运行

需要 Python 3.11 或更高版本。

```bash
python -m pip install -e ".[test]"
pytest
```

如果不安装为 editable package，也可以使用项目内隔离依赖运行：

```bash
PYTHONPATH=".venv-packages;src;." python -m pytest
PYTHONPATH=".venv-packages;src;." python -m simulator duplicate-open
```

Windows PowerShell 示例：

```powershell
$env:PYTHONPATH = ".venv-packages;src;."
python -m pytest
python -m simulator night-dose
```

## 运行模拟场景

```bash
python -m simulator night-dose
python -m simulator duplicate-open
python -m simulator no-response
python -m simulator post-nap

# 交互式虚拟药盒
python -m simulator --interactive
```

交互式模式支持：

```text
help              查看操作
status            查看设备遥测和当前会话
remind            启动提醒
ack               患者响应
open              打开目标药格
close             关闭药格
escalate          升级提醒
offline / online  模拟断网和恢复
low-battery       模拟低电量
emergency-unlock  模拟应急解锁
quit              退出模拟器
```

`duplicate-open` 场景会演示：

```text
提醒启动
→ 合法开盒
→ 停止提醒
→ 进入安全保护期并发出锁定命令
→ 再次开盒
→ 生成重复开盒风险
→ 保持锁定
→ 创建照护者通知
```

## 启动 API

默认数据库文件为项目运行目录下的 `dose_aware.db`。可通过环境变量指定其他位置：

```bash
DOSE_AWARE_DATABASE_PATH=./data/dose_aware.db uvicorn dose_aware.api:app --app-dir src --reload
```

Windows PowerShell：

```powershell
$env:DOSE_AWARE_DATABASE_PATH = ".\data\dose_aware.db"
uvicorn dose_aware.api:app --app-dir src --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

患者端与照护者端：`http://127.0.0.1:8000/`

API 文档：`http://127.0.0.1:8000/docs`

Web 页面支持直接运行：正常夜间取药、重复开盒风险、长时间无响应和小睡后补提醒。演示状态全部由真实后端状态机产生，不在浏览器中伪造。

当前主要接口：

```text
GET  /
GET  /health
POST /demo/scenarios/{name}
POST /sessions
GET  /sessions
GET  /sessions/{session_id}
POST /sessions/{session_id}/events
GET  /sessions/{session_id}/audit
GET  /notifications
GET  /notifications?session_id={session_id}
```

## 核心目录

```text
src/dose_aware/
├── api.py             # FastAPI 入口
├── protocol.py        # 设备事件和命令协议
├── repository.py      # SQLite 会话、审计和通知仓储
├── service.py         # 应用服务与场景模拟
└── state_machine.py   # 确定性安全状态机
simulator/
├── __main__.py          # CLI 场景入口
└── device.py            # 交互式虚拟药盒
web/
├── index.html           # 患者端与照护者端
├── styles.css           # 响应式浅色界面
└── app.js               # 同源 API 交互
tests/
├── test_api.py
├── test_fault_scenarios.py
├── test_persistence.py
├── test_simulator_device.py
└── test_state_machine.py
```

## 安全边界

AI 不参与以下决策：

- 药物剂量；
- 是否补服；
- 安全间隔；
- 是否解除锁定；
- 是否修改处方；
- 是否已经实际服药。

当前代码中的安全间隔仅用于软件测试，不构成医学建议。真实设备和真实患者使用前，必须经过患者、照护者和专业人员验证。

## 项目资料

- `docs/知醒DoseAware项目计划书V1.0.md`
- `docs/00-资料与开发输入清单.md`
- `docs/01-明日开工检查清单.md`
- `docs/02-需求覆盖矩阵.md`

## 为什么做这个项目

这个项目来自一次面向发作性睡病场景的黑客松实践。原本想做一个智能药盒，后来把问题收敛成一个更值得复用的工程命题：当患者刚醒、意识模糊或小睡后醒来时，系统如何记录设备观察、阻止短时间内重复取药，并在异常时把问题交给照护者，而不是假装软件已经证明患者服了药。

即使最终没有实体硬件，这个仓库仍然保留了需求分析、状态机、设备协议、持久化、模拟器、Web 演示和测试，作为一次面向真实患者问题的开源实验记录。

## 你可以借鉴什么

- 用确定性状态机承载安全关键规则，把 AI 放在摘要、问答和趋势分析等辅助位置；
- 用统一 `DeviceEvent` 协议隔离软件逻辑与 ESP32、T5-core 或其他硬件；
- 把“开盒”“患者响应”和“实际服药”分成不同事实，避免过度承诺；
- 用幂等事件、审计日志和照护者通知构成可追溯的异常闭环；
- 先用 Python 模拟器验证故障场景，再决定是否投入实体硬件。

## 明确不做什么

- 不根据 AI 输出决定剂量、补服、安全间隔或物理解锁；
- 不把开盒事件包装成服药证明；
- 不把模拟器结果包装成真实唤醒能力或医疗器械验证；
- 不鼓励任何人直接把当前原型用于真实处方、真实患者或急救场景。

## 开源状态

当前版本为 **v0.1 核心闭环原型**。代码、测试、模拟器、Web 演示、设计资料和安全边界说明已提交到本地 git 仓库，适合阅读、复现、讨论和二次开发。

仍待后续验证的内容包括：患者与照护者实测、实体硬件、真实远程通知、断电与网络异常下的设备行为、隐私与权限模型，以及医疗和监管场景的专业审查。

如果这个项目对你有帮助，欢迎优先贡献：真实需求反馈、故障场景、测试、硬件适配和文档。请先阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md) 与 [`SECURITY.md`](SECURITY.md)。
