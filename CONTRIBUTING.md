# Contributing to DoseAware

知醒 DoseAware 欢迎围绕患者真实需求的代码、测试、文档和硬件协议贡献。

## 开发原则

1. 每个功能必须对应一个患者需求或明确的工程问题；
2. 安全关键逻辑使用确定性规则，不交给大模型；
3. 开盒只能记录为开盒或响应，不写成已经服药；
4. 新功能必须包含测试或可复现的场景；
5. 不提交真实患者数据、API Key或本地配置；
6. 未实测的硬件能力必须标记为模拟验证或设计预留。

## 本地验证

```bash
python -m pytest
python -m simulator night-dose
python -m simulator duplicate-open
```

## 提交说明

提交信息建议使用以下前缀：

- `feat:` 新功能
- `fix:` 缺陷修复
- `test:` 测试
- `docs:` 文档
- `refactor:` 重构

请在 Pull Request 中说明：需求编号、实现范围、测试结果和已知限制。
