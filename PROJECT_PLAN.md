# FastAPI 社区答疑 Agent：完整项目计划

> 本文件是项目的"唯一事实来源"。换 AI、换窗口时，把这个文件和 `PROGRESS.md` 一起交给新的 AI。

---

## 0. 背景与原则

### 0.1 我是谁
- 计算机本科生，**Python 零基础**，没有实习经历，也没有项目经历
- 目标：用 10 天做出一个**真实、能演示、每一行都讲得清楚**的 AI Agent 项目，写进简历的"项目经历"，去投 AI 应用开发和后端方向的日常实习
- 同时要学会：Python 基础、数据结构与算法基础

### 0.2 三条铁律
1. **项目经历写成个人项目，不包装成假实习。** 背调能查出来，面试追问会露馅。真项目讲透，比假实习有用。
2. **核心代码我自己写。** AI 负责讲原理、搭骨架、出题、review，不替我写核心逻辑。面试官会让我讲代码，或者现场改代码。
3. **所有数据都是真测出来的。** 简历上的召回率、幻觉率、耗时都来自 `eval/` 的真实运行结果，不编数字。

### 0.3 对时间的现实预期
- 10 天能做到：能跑的 MVP + Python 基础 + 约 20 道算法题的理解
- 10 天做不到：算法达到面试水平。项目做完后，继续每天刷 2–3 道 LeetCode Hot100，刷 1–2 个月，边投简历边刷
- Redis、消息队列、限流、Docker 都是**加分项**，放到 D10 之后，有余力再做

---

## 1. 项目定位

### 1.1 一句话定位
**面向开源社区开发者的"可溯源"答疑 Agent：不只回答问题，还能主动去查资料，而且每句话都有出处。**

### 1.2 场景
- 知识源：FastAPI 官方文档（英文 Markdown）+ FastAPI 的 GitHub Issue / PR / Discussions
- 用户：学习和使用 FastAPI 的开发者（包括我自己）

### 1.3 要解决的问题
| 痛点 | 现状 |
|---|---|
| 信息分散 | 答案散在官方文档、Issue、Discussions 里，搜索效率低 |
| 通用大模型不可信 | 不了解最新版本的细节，会编 API、编参数 |
| 现成平台是黑盒 | Dify / FastGPT 能搭，但检索过程不透明，答错了没法排查 |
| 只会聊天不会查 | 普通 RAG 只能查本地文档，查不了实时的 Issue |

### 1.4 产品哲学（每一条都对应技术决策）
| 原则 | 技术落地 |
|---|---|
| **可信 > 能说会道**：宁可说不知道，也不胡编 | 回答必须带引用（文档名 + 段落）；检索相关度低于阈值时拒答；用评估集量化幻觉率 |
| **能办事，不只是聊天** | Function Calling：搜文档、搜 GitHub Issue；手写 Agent 推理循环，限制最大步数 |
| **过程透明、可调试** | 前端展示 Agent 每一步：想了什么、调了哪个工具、检索到了什么；记录耗时和 Token |
| **轻量、可理解** | 不用 LangChain，核心模块（分块、BM25、混合检索、LRU、Agent 循环）全部手写 |

### 1.5 明确不做什么
- 不做多用户、登录、多租户
- 不做可视化工作流编排
- 不做模型微调

### 1.6 "为什么做这个项目"的回答模板
> "我在学 FastAPI 的时候发现，很多问题文档里没写清楚，答案藏在 GitHub Issue 和 Discussions 里，很难搜。直接问 ChatGPT 又会编出不存在的参数。我试过 Dify，能搭，但检索过程是黑盒，答错了不知道原因。同时我也想真正搞懂 RAG 和 Agent 的底层，而不只是会调框架，所以没用 LangChain，从零实现了分块、BM25、混合检索和 Agent 推理循环。最后在自建的 50 条测试集上，混合检索的 Recall@5 比纯向量检索从 __% 提升到 __%，幻觉率从 __% 降到 __%。"

（空格处在 D9 跑完评估后填真实数据。故事里的触发点要和自己的真实经历一致：这 10 天我确实在学 FastAPI。）

---

## 2. 技术栈

| 模块 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.13 | 本机已安装 |
| 对话模型 | DeepSeek API（`deepseek-chat`） | 便宜，兼容 OpenAI SDK，支持 Function Calling |
| 向量模型 | 硅基流动（SiliconFlow）的 `BAAI/bge-m3` | **DeepSeek 不提供 Embedding 接口**，硅基流动的 bge-m3 兼容 OpenAI SDK；备选方案：Chroma 自带的本地默认模型 |
| 向量库 | Chroma | `pip install chromadb` 就能用，不用另外部署 |
| 关键词检索 | **手写 BM25** | 练哈希表和倒排索引 |
| 混合检索 | **手写 RRF**（倒数排名融合） | 练排序和堆 |
| 缓存 | **手写 LRU** | 练哈希表 + 双向链表（LeetCode 146） |
| Agent | **手写 Function Calling 循环** | 不用 LangChain，搞懂底层 |
| 后端 | FastAPI + SSE 流式输出 | 简单，自带接口文档 |
| 前端 | Streamlit | 纯 Python |
| 外部工具 | GitHub REST API（搜索 Issue/PR）；进阶用 GraphQL 搜 Discussions | 注意：FastAPI 的大量问答在 Discussions 里 |
| 依赖管理 | `venv` + `requirements.txt` | 新手友好 |

需要准备的账号（Key 只存在 `.env` 里，**不发给任何 AI，不提交到 git**）：
- DeepSeek 开放平台 API Key
- 硅基流动 API Key
- GitHub Personal Access Token（只需要读 public repo 的权限）

---

## 3. 架构

### 3.1 数据流
```
【离线入库】 scripts/ingest.py
FastAPI 文档 .md ──> loader 读取 ──> chunker 分块（带重叠）──┬──> embedder 向量化 ──> Chroma
                                                          └──> BM25 建倒排索引 ──> 存到本地文件

【在线问答】
用户提问 ──> LRU 缓存命中？──是──> 直接返回
              │否
              v
         Agent 循环（最多 N 步）
           ├─ 工具1 search_docs：向量检索 + BM25 ──> RRF 融合 ──> 堆取 Top-K
           ├─ 工具2 search_github_issues：调 GitHub API
           └─ 最终回答：带引用；证据不足时拒答
              │
              v
         FastAPI（SSE 流式）──> Streamlit 界面（展示回答、引用、推理步骤）
```

### 3.2 目录结构
```
fastapi-helper-agent/
├── PROJECT_PLAN.md        # 本文件
├── AI_PROMPT.md           # 给 AI 的提示词
├── PROGRESS.md            # 进度日志，每次会话结束都要更新
├── README.md
├── .env                   # API Key（不提交）
├── .gitignore
├── requirements.txt
├── data/
│   ├── raw/               # FastAPI 文档原文
│   ├── chroma/            # 向量库文件
│   └── bm25_index.json    # BM25 索引
├── app/
│   ├── config.py          # 读取 .env 配置
│   ├── llm.py             # 封装大模型调用
│   ├── loader.py          # 读取文档
│   ├── chunker.py         # ★手写：分块
│   ├── embedder.py        # 向量化
│   ├── vector_store.py    # Chroma 封装
│   ├── bm25.py            # ★手写：BM25
│   ├── retriever.py       # ★手写：RRF 混合检索 + 堆取 Top-K
│   ├── cache.py           # ★手写：LRU 缓存
│   ├── memory.py          # ★手写：用 deque 实现对话窗口
│   ├── tools.py           # 工具定义：search_docs、search_github_issues
│   ├── agent.py           # ★手写：Agent 推理循环
│   └── api.py             # FastAPI 接口
├── ui/
│   └── streamlit_app.py
├── scripts/
│   └── ingest.py          # 入库脚本
├── eval/
│   ├── questions.jsonl    # 50 条测试题
│   ├── run_eval.py        # 评估脚本
│   └── results/           # 评估结果（简历数据的来源）
├── tests/                 # 单元测试（pytest）
└── leetcode/              # 每天刷的题，按日期存放
```
★ = 必须我自己写的核心模块

---

## 4. 项目模块 ↔ 数据结构与算法

| 项目模块 | 数据结构 / 算法 | 对应 LeetCode |
|---|---|---|
| chunker 分块（带重叠） | 字符串、滑动窗口 | 3. 无重复字符的最长子串、438. 找到字符串中所有字母异位词 |
| bm25 倒排索引 | 哈希表 | 1. 两数之和、49. 字母异位词分组、242. 有效的字母异位词 |
| retriever 取 Top-K | 堆（`heapq`） | 215. 数组中的第K个最大元素、347. 前 K 个高频元素 |
| retriever RRF 融合 | 排序、双指针 | 88. 合并两个有序数组、21. 合并两个有序链表 |
| cache LRU | 哈希表 + 双向链表 | **146. LRU 缓存** |
| memory 对话窗口 | 队列（`deque`） | 239. 滑动窗口最大值、933. 最近的请求次数 |
| agent 推理循环 | 循环、状态机、栈 | 20. 有效的括号、155. 最小栈 |
| 链表基础 | 链表 | 206. 反转链表、141. 环形链表 |

---

## 5. 10 天详细计划

每天大约 8 小时：**上午学 Python（2–3h）→ 下午做项目（4h）→ 晚上刷算法（1–2h）→ 结束前更新 PROGRESS.md**

### D1：环境 + 第一行 Python + 调通大模型
- **Python**：变量、数据类型、`list` / `dict`、`if` / `for`、函数
- **项目**
  - 创建虚拟环境：`python3 -m venv .venv && source .venv/bin/activate`
  - `git init`，写 `.gitignore`（必须包含 `.env`、`.venv/`、`data/chroma/`）
  - 申请三个 API Key，写进 `.env`
  - `app/config.py` 读取配置；`app/llm.py` 封装 `chat(messages) -> str`
- **自己写**：`llm.py` 里的 `chat` 函数
- **验收**：运行 `python -m app.llm`，能打印出大模型的回答
- **算法**：1. 两数之和（先写暴力解，再写哈希表解，说清两种解法的时间复杂度）
- **当天要能回答的面试题**：为什么要用虚拟环境？API Key 为什么不能写进代码？

### D2：读取文档
- **Python**：字符串方法、文件读写、`pathlib`、类（`class`、`__init__`）
- **项目**
  - 从 GitHub 下载 FastAPI 仓库，只要 `docs/en/docs/` 目录下的 `.md` 文件，放进 `data/raw/`
  - `loader.py`：遍历文件夹，返回 `list[Document]`，每个 Document 包含 `text`、`source`（文件路径）、`title`
- **自己写**：`Document` 类和遍历逻辑
- **验收**：打印出文档总数、总字数、最长的 5 篇文档
- **算法**：242. 有效的字母异位词、14. 最长公共前缀

### D3：手写分块
- **Python**：列表推导式、切片、异常处理、`dataclass`
- **项目**：`chunker.py`
  - 策略：先按 Markdown 标题切，太长的段落再按固定长度切，相邻块之间带重叠（例如块长 500 字符、重叠 100 字符）
  - 每个块保留元数据：`source`、所属标题、`chunk_id`
- **自己写**：整个 `chunker.py`
- **验收**：用 `pytest` 写 3 个测试（空文本、短文本、长文本）；随机打印 5 个块，人工检查有没有把代码块切断
- **算法**：3. 无重复字符的最长子串、438. 找到字符串中所有字母异位词
- **面试题**：为什么要分块？块大小怎么选？为什么要重叠？代码块被切断了怎么办？

### D4：向量化 + 最简 RAG 跑通
- **Python**：模块与包、`import`、`pip`、`requirements.txt`
- **项目**
  - `embedder.py`：调用 bge-m3 做向量化（注意分批调用）
  - `vector_store.py`：存入 Chroma、按问题检索
  - `scripts/ingest.py`：一键入库
  - 最简 RAG：问题 → 检索 Top-5 → 拼成 Prompt → 大模型回答
- **自己写**：拼 Prompt 的逻辑（要求模型只根据资料回答，并标注引用编号）
- **验收**：问"How to declare a path parameter?"，回答正确且带出处
- **算法**：49. 字母异位词分组、128. 最长连续序列
- **面试题**：Embedding 是什么？向量相似度怎么算（余弦相似度）？Prompt 是怎么设计的？

### D5：手写 BM25 + 混合检索
- **Python**：类进阶、类型注解、`collections.Counter` / `defaultdict`、`math`
- **项目**
  - `bm25.py`：分词 → 建倒排索引（`词 -> {文档id: 词频}`）→ 计算 BM25 分数，支持保存和加载
  - `retriever.py`：向量结果和 BM25 结果用 RRF 融合（`score = Σ 1/(k + rank)`，k=60），再用 `heapq.nlargest` 取 Top-K
- **自己写**：整个 `bm25.py` 和 RRF
- **验收**：找一个向量检索查不准、BM25 查得准的例子（比如精确的函数名 `Depends`），对比两者结果
- **算法**：215. 数组中的第K个最大元素、347. 前 K 个高频元素
- **面试题**：BM25 公式里 k1、b 的作用？为什么需要混合检索？RRF 为什么不直接把两种分数相加？堆取 Top-K 的复杂度？

### D6：Agent 工具调用
- **Python**：装饰器、JSON、`requests`、字典嵌套
- **项目**
  - `tools.py`：定义两个工具和它们的 JSON Schema
    - `search_docs(query)`：调用 D5 的混合检索
    - `search_github_issues(query)`：调 GitHub 搜索接口 `GET /search/issues?q=repo:fastapi/fastapi+{query}`
  - `agent.py`：手写循环
    ```
    for step in range(MAX_STEPS):
        调用大模型（带 tools）
        如果模型要调工具 -> 执行工具 -> 把结果追加到 messages -> 继续
        如果模型给出最终回答 -> 返回
    超过最大步数 -> 返回兜底回答
    ```
  - 工具报错要捕获，并把错误信息告诉模型，不能让程序崩溃
- **自己写**：整个 Agent 循环
- **验收**：问一个文档里没有、Issue 里才有的问题，能看到 Agent 自己决定去搜 GitHub
- **算法**：20. 有效的括号、155. 最小栈
- **面试题**：Function Calling 的原理？Agent 和 RAG 的区别？怎么防止死循环？工具调用失败怎么办？GitHub API 限流怎么处理？

### D7：后端接口 + 流式输出
- **Python**：`async` / `await` 基础、生成器 `yield`
- **项目**
  - `api.py`：`POST /chat` 接口，用 SSE 流式返回，事件分几类：`step`（推理步骤）、`token`（回答片段）、`sources`（引用）
  - `memory.py`：用 `deque(maxlen=N)` 保存最近 N 轮对话
- **自己写**：`memory.py`、SSE 事件格式
- **验收**：打开 `http://127.0.0.1:8000/docs` 能调通接口，看到流式输出
- **算法**：239. 滑动窗口最大值、933. 最近的请求次数
- **面试题**：SSE 和 WebSocket 的区别？为什么要流式输出？同步和异步的区别？

### D8：界面 + LRU 缓存
- **Python**：复习面向对象，写一个双向链表
- **项目**
  - `ui/streamlit_app.py`：聊天界面；展示引用出处（可展开看原文）；展示 Agent 推理步骤；显示耗时
  - `cache.py`：手写 LRU 缓存（哈希表 + 双向链表，`get` / `put` 都是 O(1)），缓存问答结果
- **自己写**：整个 `cache.py`，**不准用 `OrderedDict` 或 `functools.lru_cache`**
- **验收**：同一个问题问两次，第二次明显更快；为 LRU 写测试（容量满了以后淘汰最久未使用的那条）
- **算法**：146. LRU 缓存、206. 反转链表、141. 环形链表
- **面试题**：LRU 为什么要用双向链表？缓存的 key 怎么设计（相似但不完全相同的问题怎么办）？缓存什么时候失效？

### D9：评估（简历数据的来源）
- **项目**
  - `eval/questions.jsonl`：**自己手写** 50 条问题，每条标注应该命中的文档 `source`；其中 10 条是文档里没有答案的问题（用来测拒答）
  - `eval/run_eval.py`：
    - 检索指标：分别跑 纯向量 / 纯 BM25 / 混合检索 三组，算 **Recall@5**、**MRR**
    - 拒答指标：无答案问题中，正确拒答的比例
    - 幻觉率：人工检查（或让大模型当裁判再人工抽查）回答里有没有资料中不存在的内容
    - 平均耗时、缓存命中后的耗时
  - 结果存进 `eval/results/`，带上日期
  - 发现问题就调参数（块大小、Top-K、拒答阈值），再跑一次，**前后两次的数据都保留**，这就是"优化"的证据
- **验收**：一张对比表格，数据可复现
- **算法**：复习本周所有题，挑 5 道不看答案重写一遍
- **面试题**：你怎么评估 RAG 效果？Recall 和 MRR 是什么？测试集是怎么构建的？有什么局限？

### D10：包装与面试准备
- **项目**
  - `README.md`：项目介绍、架构图、快速启动、评估结果表格、演示截图或 GIF
  - 代码推到 GitHub 公开仓库，检查**没有提交 `.env`**
  - 录一段 2 分钟的演示视频
- **简历**：按第 7 节模板写，填入 D9 的真实数据
- **模拟面试**：让 AI 当面试官，按第 6 节的问题追问，每个问题至少追问 3 层
- **自测**：不看代码，在白纸上画出架构图，讲清楚一个问题从提出到回答经过了哪些模块

### D10 之后（加分项，按优先级排）
1. 用 Docker 打包部署到云服务器，做一个在线 Demo
2. 接入 GitHub Discussions（GraphQL API）
3. 用 Redis 替换手写 LRU，对比两者的优缺点
4. 加 Rerank 模型（例如 `BAAI/bge-reranker-v2-m3`），评估提升了多少
5. 给 FastAPI 或 Chroma 提一个文档 PR（真实的开源贡献）
6. 继续刷 LeetCode Hot100，每天 2–3 道

---

## 6. 面试深挖问题清单

**项目整体**
1. 为什么做这个项目？解决了什么问题？
2. 为什么不直接用 Dify / ChatGPT？
3. 画一下架构图，讲讲一次请求的完整流程
4. 最难的地方是什么？怎么解决的？
5. 如果再做一遍，你会怎么改？

**RAG**
6. 分块策略是怎么定的？块大小对效果有什么影响？
7. Embedding 模型为什么选 bge-m3？
8. 为什么做混合检索？RRF 的原理？
9. 怎么减少幻觉？拒答阈值怎么定的？
10. 怎么评估效果？测试集有什么局限？

**Agent**
11. Function Calling 的原理是什么？模型是怎么"决定"调用工具的？
12. 为什么不用 LangChain？
13. 怎么防止 Agent 死循环、乱调工具？
14. 工具调用失败、超时，怎么处理？
15. 多轮对话的上下文是怎么管理的？太长了怎么办？

**工程**
16. LRU 缓存是怎么实现的？复杂度是多少？
17. SSE 流式输出是怎么实现的？
18. 并发量大了，系统瓶颈在哪？怎么优化？
19. API Key 怎么管理？
20. 怎么测试？写了哪些单元测试？

**Python 基础**（项目里用到了，就会被问到）
21. list 和 tuple 的区别？dict 的底层是什么？
22. 生成器和迭代器的区别？`yield` 做了什么？
23. 装饰器的原理？
24. GIL 是什么？`async` 适合什么场景？
25. 深拷贝和浅拷贝的区别？

---

## 7. 简历模板

> 写在"项目经历"栏，**不写成实习**。数据全部来自 `eval/results/`。

**FastAPI 社区答疑 Agent**（个人项目） | Python, FastAPI, DeepSeek, Chroma | 2026.10 | GitHub: [链接]

面向开源社区开发者的可溯源答疑 Agent，能综合官方文档与 GitHub Issue 回答问题，每条回答都标注出处。

- 不依赖 LangChain，从零实现基于 Function Calling 的 Agent 推理循环，支持文档检索、GitHub Issue 搜索等工具的自主调用，并设计了最大步数限制和工具异常降级策略
- 手写 BM25 倒排索引，与向量检索通过 RRF 融合；在自建 50 条测试集上，Recall@5 从 __%（纯向量）提升到 __%
- 设计引用溯源与低相关度拒答机制，幻觉率从 __% 降到 __%，无答案问题的正确拒答率达到 __%
- 基于哈希表 + 双向链表实现 LRU 缓存，命中时响应耗时从 __s 降到 __ms；基于 FastAPI + SSE 实现流式输出，并可视化展示 Agent 推理过程

---

## 8. 学习资源
- Python：廖雪峰 Python 教程；Python 官方教程（中文版）
- FastAPI：官方文档的 Tutorial 部分（这也是本项目的知识库，一举两得）
- 算法：LeetCode Hot100；代码随想录（按专题刷）
- RAG / Agent：DeepSeek 官方文档里的 Function Calling 章节；OpenAI Cookbook
