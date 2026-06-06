<div align="center">

# 📡 Notion RSS

**基于 Notion 的个人 RSS 阅读器，支持飞书通知推送**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Notion API](https://img.shields.io/badge/Notion-API-000000?logo=notion&logoColor=white)](https://developers.notion.com/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-自动运行-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![飞书](https://img.shields.io/badge/飞书-Webhook-00D09C?logo=bytedance&logoColor=white)](https://www.feishu.cn/)

自动抓取 RSS 订阅源，将文章内容写入 Notion 数据库，同时推送每日摘要到飞书群。

[English](README.md) | 中文

</div>

---

## ✨ 功能特性

- **📋 RSS 订阅管理** — 在 Notion 数据库中管理所有订阅源，通过勾选框一键启用/禁用
- **🔄 自动抓取与过滤** — 定时抓取 RSS Feed，仅获取时间窗口��的新文章（默认 24 小时）
- **📝 智能内容转换** — HTML → Markdown → Notion Blocks，完整保留标题、列表、链接等格式
- **📖 Notion 阅读器** — 文章自动写入 Notion Reader 数据库，随时随地阅读
- **🔔 飞书通知** — 每日新文章摘要推送到飞书群，不错过任何更新
- **🧹 自动清理** — 自动归档 30 天以上的未读文章，保持数据库整洁
- **⚙️ GitHub Actions** — 每日定时自动运行，零维护成本

---

## 🔄 工作流程

```mermaid
flowchart TD
    A["⏰ GitHub Actions 定时触发 / 手动触发"] --> B["📡 从 Notion Feeds 数据库获取已启用的订阅源"]
    B --> C["🔍 逐个解析 RSS Feed"]
    C --> D{"文章是否在时间窗口内?"}
    D -- "是" --> E["📦 收集新文章"]
    D -- "否" --> F["⏭️ 跳过"]
    E --> G["按发布时间排序"]
    G --> H["🔔 发送飞书每日摘要"]
    G --> I["📝 HTML → Markdown → Notion Blocks"]
    I --> J["📖 写入 Notion Reader 数据库"]
    J --> K["🧹 归档 30 天以上未读文章"]

    style A fill:#4A90D9,color:#fff
    style B fill:#000000,color:#fff
    style H fill:#00D09C,color:#fff
    style J fill:#000000,color:#fff
    style K fill:#E74C3C,color:#fff
```

---

## 📁 项目结构

```
notion-rss/
├── main.py              # 入口文件，编排整体流程
├── feed.py              # RSS 抓取与过滤逻辑
├── notion.py            # Notion API 交互（读取订阅源、写入文章、清理旧文章）
├── parser.py            # 内容转换（HTML → Markdown → Notion Blocks）
├── feishu.py            # 飞书 Webhook 消息推送
├── helpers.py           # 工具函数（时间差计算）
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量模板
└── .github/workflows/
    └── feed.yml         # GitHub Actions 工作流配置
```

---

## 🚀 快速开始

### 前置条件

- Python 3.12+
- Notion 账号 + [Integration Token](https://www.notion.so/my-integrations)
- 飞书群机器人 Webhook URL

### 1. 配置 Notion 数据库

你需要在 Notion 中创建两个数据库，并将它们与你的 Integration 关联。

**Feeds 数据库**（管理订阅源）：

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `Title` | Title | 订阅源名称 |
| `Link` | URL | RSS Feed 地址 |
| `Enabled` | Checkbox | 是否启用该订阅源 |

**Reader 数据库**（存储文章）：

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `Title` | Title | 文章标题 |
| `Link` | URL | 文章原文链接 |
| `Created At` | Created time | 创建时间（自动生成） |
| `Read` | Checkbox | 是否已读 |

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的配置：

```env
NOTION_API_TOKEN=your_notion_api_token_here
NOTION_READER_DATABASE_ID=your_reader_database_id_here
NOTION_FEEDS_DATABASE_ID=your_feeds_database_id_here
FEISHU_WEBHOOK_URL=https://www.feishu.cn/flow/api/trigger-webhook/xxxx
RUN_FREQUENCY=86400
```

### 3. 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

---

## 🤖 GitHub Actions 部署

本项目已配置 GitHub Actions，每天 UTC 5:12（北京时间 13:12）自动运行。

### 配置步骤

1. Fork 本仓库
2. 进入仓库 **Settings → Secrets and variables → Actions**
3. 添加以下 Secrets：

| Secret 名称 | 说明 |
|-------------|------|
| `NOTION_API_TOKEN` | Notion Integration Token |
| `NOTION_READER_DATABASE_ID` | Reader 数据库 ID |
| `NOTION_FEEDS_DATABASE_ID` | Feeds 数据库 ID |
| `FEISHU_WEBHOOK_URL` | 飞书 Webhook 地址 |

4. 工作流会自动按计划运行，也可以在 **Actions** 页面手动触发

---

## 📋 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|-----|--------|------|
| `NOTION_API_TOKEN` | ✅ | — | Notion API 认证令牌 |
| `NOTION_READER_DATABASE_ID` | ✅ | — | 存储文章的 Reader 数据库 ID |
| `NOTION_FEEDS_DATABASE_ID` | ✅ | — | 管理订阅源的 Feeds 数据库 ID |
| `FEISHU_WEBHOOK_URL` | ✅ | — | 飞书机器人 Webhook 地址 |
| `RUN_FREQUENCY` | ❌ | `86400` | 抓取时间窗口（秒），默认 24 小时 |
| `CI` | ❌ | — | CI 环境标识，影响日志级别 |

---

## 🛠️ 技术栈

| 依赖 | 用途 |
|------|------|
| [feedparser](https://feedparser.readthedocs.io/) | RSS/Atom Feed 解析 |
| [requests](https://requests.readthedocs.io/) | HTTP 请求（Notion API、飞书 Webhook） |
| [markdownify](https://github.com/matthewwithanm/python-markdownify) | HTML 转 Markdown |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 环境变量管理 |

---

## 📝 许可证

MIT

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
