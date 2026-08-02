---
title: 8月2日第一期周报：AI Workflow Copilot阶段0技术验证
date: 2026-08-02 10:15:13 +0800
categories: [周报]
tags: []
---

这是 AI Workflow Copilot 开发的第一期周报。本周没有直接开始正式业务功能，而是先把风险最高的模型流、Agent/Tool、Embedding、pgvector 和 SSE 拆成四个独立实验，逐项确认当前技术组合能否真实跑通。

阶段 0 原计划安排在 8 月 3 日至 9 日，但主要实验、兼容性收口和可复现验收已经提前完成。因此，原定 8 月 8 日的代码收口和 8 月 9 日的阶段验收也一并结束，不再为了填满日期重复运行同样的流程。

## 本周完成

### 1. Eino 调用 DeepSeek 流式输出

建立了与正式业务隔离的 Go 实验，使用 Eino DeepSeek adapter 调用真实 `deepseek-v4-flash`。真实请求首段延迟为 550 ms，总耗时 1.72 s，最终正常收到 `finish_reason=stop` 和 Token 用量。

这次运行共收到 100 个消息 chunk，其中正文 chunk 和 logprob token 都是 99 个。多出的一个 chunk 只携带结束信息，说明 chunk 是一次消息或传输边界，不能直接等同于模型 Token。

离线测试还覆盖了正常流、超时、HTTP 429 和缺少密钥等情况，`go test` 与 `go vet` 均通过。

### 2. ChatModelAgent 调用 Tool

使用 Eino `ChatModelAgent` 接入了一个最小的 `add_numbers` Tool。真实 DeepSeek 请求中，模型选择调用 `add_numbers({"a":37,"b":5})`，Go Tool 返回 `{"sum":42}`，结果再交给模型生成最终回答。

实验同时验证了不需要 Tool、缺少字段、JSON 类型错误和数值越界等路径。这里确认了一个重要边界：JSON Schema 只是提供给模型的结构化契约，不能保证模型每次都生成合法参数，Go 代码仍然必须做字段、类型、范围和 `context` 校验。

### 3. 百炼 Embedding、pgvector 与相似 JD 检索

使用真实百炼 `text-embedding-v4` 将 6 份脱敏 JD 转成 1024 维向量，并写入 PostgreSQL 17.10 与 pgvector 0.8.6。真实查询返回的前三项依次为 AI 应用后端/Go/RAG、Go 后端和 Java 后端，完整链路已经跑通。

数据库使用 `vector(1024)`、余弦距离和 HNSW 索引。兼容性探针进一步确认：普通 `vector(2048)` 可以建列，但不能建立 HNSW 索引；`halfvec(2048)` 可以建立 HNSW。当前正式基线因此固定为 1024 维，不能在模型或维度变化后静默复用旧表和旧索引。

### 4. React → Gin → Eino Agent/Tool/DeepSeek → SSE

最小 React 页面已经能够通过 POST 将输入发送给 Gin。Gin 把请求 `context` 继续传给 Eino Agent，Agent 调用 DeepSeek 和 Tool，再通过同一个 HTTP 响应持续发送 SSE 事件。前端使用 `fetch + ReadableStream` 逐段解析。

真实链路中，页面依次收到 `connected → agent_started → tool_call → tool_result → done`，最终得到 37 加 5 等于 42 的模型回答。离线模式还验证了模型错误和用户主动取消：浏览器的 `AbortController` 会让 Gin 请求 `context` 取消，并继续传到下游模型或 Tool。

该实验最终有 10 项 Go 测试和 2 项前端 SSE 解析测试通过，Vite 生产构建通过，`npm audit` 为 0 个漏洞。

### 5. 固定阶段 0 兼容性基线

本周最后将四个实验收束成了一套可重复验证的组合：Go 1.26.4、Eino 0.7.13、DeepSeek adapter 0.1.7、sonic 1.15.2、DeepSeek `deepseek-v4-flash`、百炼 `text-embedding-v4` 1024 维、PostgreSQL 17.10 和 pgvector 0.8.6。

仓库新增统一验证脚本，可以自动执行四个 Go 模块的测试和静态检查、Agent/Tool 错误分支、前端测试与构建，以及 pgvector 写入、Top-K 查询和索引探针。离线回归不会消耗真实模型额度，也不会把离线替身的结果冒充真实 API 成功。

## 本周主要收获

### 流式链路有三种不同的“分片”

模型 Token、Eino 消息 chunk 和浏览器网络 chunk 不是一回事。Eino 内部还存在两层读取：外层取得 Agent 的下一步消息，内层读取这条消息的流式分片。到了浏览器一侧，网络的一次 `read()` 也不保证正好得到一个完整 SSE event，所以前端必须缓存残缺文本并按事件边界解析。

### Tool 调用不是模型直接执行代码

模型只负责选择 Tool 并生成参数；Eino 根据 `tool_call` 找到 Go Tool，Go 代码校验并执行，再把结果作为 Tool Message 交回模型。Tool schema、运行时校验和 `call_id` 分别解决“告诉模型格式”“阻止非法输入”和“关联调用与结果”的问题，不能互相替代。

### Embedding 与 pgvector 的职责不同

Embedding 模型负责把文字映射到语义空间，pgvector 负责保存向量并查找近邻。正式业务中，一份 JD 可以切成多个证据片段，每个片段分别生成向量，因此原文与向量通常不是简单的一对一关系。

HNSW 适合后续增量写入和近邻查询，但 6 条测试数据并不能证明索引更快。当前实验中的强制 `EXPLAIN` 只证明 SQL、距离操作符和索引定义能够配合，不代表已经完成大样本召回率和性能评估。

## 遇到的问题与处理

| 问题 | 处理结果 |
| --- | --- |
| adapter 间接依赖的 sonic 1.14.1 与 Go 1.26.4 编译不兼容 | 固定 sonic 1.15.2 和对应 loader，四个模块重新测试通过 |
| 百炼 Base URL 仍含 Workspace 占位符，真实请求返回 HTTP 400 | 改为实际华北 2 Workspace 端点后通过 |
| 本机 8080 端口被占用 | Gin 固定到 127.0.0.1:18080，Vite 代理同步调整 |
| Vite 旧版本被 npm 审计报告 Windows 开发服务器漏洞 | 升级并固定 Vite 8.2.0，复查为 0 个漏洞 |
| SSE 已经返回 HTTP 200 后模型才失败 | 统一在流内发送结构化 `error`，不再尝试修改 HTTP 状态码 |

## 本周力扣总结

本周共有 5 道题由滴答任务评论明确归入阶段 0。8 月 8 日和 9 日的提前收口任务没有另外记录新题，因此不重复计数。

| 题目 | 难度 | 核心结构 | 提交结果 |
| --- | --- | --- | --- |
| [239. 滑动窗口最大值](https://leetcode.cn/problems/sliding-window-maximum/) | 困难 | 单调队列，保存下标并维护队首为窗口最大值 | Go，53/53，13 ms，9.7 MB |
| [76. 最小覆盖子串](https://leetcode.cn/problems/minimum-window-substring/) | 困难 | 滑动窗口，`valid` 记录数量已经达标的字符种类 | Go，268/268，33 ms，4.9 MB |
| [25. K 个一组翻转链表](https://leetcode.cn/problems/reverse-nodes-in-k-group/) | 困难 | 分组原地翻转并重新连接前后链表 | Go，62/62，0 ms，5.2 MB |
| [138. 随机链表的复制](https://leetcode.cn/problems/copy-list-with-random-pointer/) | 中等 | 两遍遍历，建立旧节点到新节点的哈希映射 | Go，19/19，0 ms，5.2 MB |
| [148. 排序链表](https://leetcode.cn/problems/sort-list/) | 中等 | 快慢指针断链，自顶向下归并排序 | Go，30/30，21 ms，9.5 MB |

这些题的共同点是都需要维护一个清楚的不变量：单调队列中留下哪些下标、滑动窗口中的 `valid` 代表什么、链表翻转时各指针指向哪里，以及归并排序递归栈的真实复杂度。尤其需要保留的修正是：自顶向下归并排序的时间复杂度为 O(n log n)，递归栈为 O(log n)，不是 O(n log n) 的栈空间。

## 阶段 0 结论与下周计划

阶段 0 的结论是：目前选定的 Eino、DeepSeek、Tool Calling、SSE、百炼 Embedding 和 pgvector 组合可行，可以进入正式工程阶段。但这些目录仍然只是技术探针，不能把实验中的单 Tool、固定样本清表、无鉴权页面和简化错误处理整体复制进正式项目。

尚未验证的内容包括反向代理缓冲、弱网重连、长连接并发、多 Tool、非幂等 Tool、大样本向量召回率、鉴权、持久化、trace 和生产级重试。这些内容不会在阶段 0 继续扩展，而是在正式工程真正需要时逐步补齐。

下周只保留一个主目标：建立 AI Workflow Copilot 的正式工程骨架。具体包括 Go 与 React 项目结构、PostgreSQL/pgvector 与 Goose Migration、配置、健康检查、结构化日志、`trace_id`、Docker Compose、基础测试入口和 README。业务功能不提前展开，阶段 0 实验只提供已经验证过的协议、版本和错误边界。
