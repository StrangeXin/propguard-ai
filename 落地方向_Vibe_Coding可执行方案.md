# Vibe Coding 可落地执行的 3 个方向

> 前提：券商 API 由合作方提供，我们聚焦产品层和 AI 层
> 原则：2-4 周可出 MVP，用户有真实付费意愿，Vibe Coding 能搞定技术复杂度

---

## 方向一：AI 智能信号聚合 + 风控仪表盘

### 为什么做这个

**用户痛点极其精准**（来自 X 上 @MojoAI_HQ 的真实列举）：
- "凌晨 3 点设了闹钟，睡过头了，醒来止损已经爆了"
- "看到聪明钱在买，手动跟进时价格已经涨了 20%"
- "想要 if A then B 的策略，没有工具支持，只能盯着屏幕"
- "四个标签页打开，信息到处都是，还是不知道该看什么"

**行业共识**：
- @0xaporia（703 likes）："我们已经掌握了展示海量市场数据的技术，但在辨别力上完全失败了。这些交易仪表盘像高科技驾驶舱…核心问题是缺少一个过滤器来判断某个数据点是否会真正改变你的下一步行动。"
- @RaybandzBBG："问题不是数据，是 UI/UX 设计太乱，一堆颜色和数字让人不知所措"
- 信号服务用户投诉最多的是："入场价不可实现"和"没有分析推理，只有警报"

**竞品空白**：
- 现有信号 Dashboard 要么信号太多不知选哪个（@SnehaSSR: "How to pick ONE stock from so many signals?"），要么只有信号没有风控
- @commutatioaii 的研究："56% 准确率 + 正确仓位管理 > 70% 准确率 + 固定仓位" — **风控比信号更重要，但没人把两者做到一起**

### 产品定义

**一句话**：不是又一个信号源，而是"信号过滤器 + AI 风控员"

**核心功能**：
1. **多源信号聚合** — 接入 Telegram 信号群、TradingView 警报、Discord 频道，统一展示
2. **AI 信号评分** — 每个信号自动评分（0-100），基于历史准确率、当前市场环境、风险回报比
3. **智能仓位计算** — 根据账户余额、当前持仓、波动率自动算出建议仓位（参考 lukra.ai 的动态仓位计算）
4. **一键执行 + 自动风控** — 设好参数后一键下单，AI 自动设置止损/止盈，监控最大回撤
5. **盘前 AI 简报** — 每天开盘前推送：今日关注信号 Top 3 + 整体市场情绪 + 你的持仓风险评估

**差异化**：不生产信号，而是帮你过滤和管理信号 — "信号的信号"

### 技术实现

```
前端: Next.js + TailwindCSS + TradingView Lightweight Charts
后端: Python FastAPI
AI:   Claude API（信号评分 + 盘前分析 + 风控建议）
数据: 券商 API（由合作方提供）+ Telegram Bot API + TradingView Webhook
实时: WebSocket 推送
部署: Vercel + Railway
```

### 变现模式

| 层级 | 价格 | 功能 |
|------|------|------|
| Free | $0 | 3 个信号源 + 基础仓位计算 |
| Pro | $29/月 | 无限信号源 + AI 评分 + 盘前简报 |
| Premium | $69/月 | 一键执行 + 自动风控 + 多账户管理 |

### 开发节奏

- 第 1 周：信号聚合 + 基础 UI（Telegram 接入 + 展示面板）
- 第 2 周：AI 评分 + 仓位计算器
- 第 3 周：券商 API 对接 + 一键执行
- 第 4 周：盘前简报 + 上线

### 来源链接

| 证据 | 链接 |
|------|------|
| 交易者痛点清单 | https://x.com/MojoAI_HQ/status/2042173132555821510 |
| Dashboard 辨别力缺失（703 likes） | https://x.com/0xaporia/status/2036821425865081338 |
| UI/UX 设计问题 | https://x.com/RaybandzBBG/status/2043335977268113661 |
| "如何从众多信号中选一个" | https://x.com/SnehaSSR/status/2042986570815541503 |
| 风控比预测更重要 | https://x.com/commutatioaii/status/2041908932638384254 |
| Lukra AI 动态仓位计算 | https://www.tiktok.com/@lukra.ai/video/7626144760243178782 |
| 信号执行差距投诉 | https://signalproviderreviews.com/reviews/the-trading-analyst |
| PythVision 一周构建 Dashboard | https://x.com/JayBrass10/status/2035718079066304535 |
| AI 风控加密交易指南 | https://www.blockchain-council.org/cryptocurrency/risk-management-with-ai-in-crypto-trading-volatility-forecasting-position-sizing-stop-loss-automation/ |
| Telegram 信号群 Top 10 | https://margex.com/en/blog/top-10-crypto-signal-providers/ |
| Prop Firm 爆仓风控规则（25K views） | https://www.tiktok.com/@adiltrader369/video/7627318098483334421 |

---

## 方向二：AI 社交跟单平台（Strategy Marketplace）

### 为什么做这个

**社交跟单是 2026 年增长最快的赛道之一**：
- Cryptohopper："加入社交交易革命——订阅信号、讨论策略、从 marketplace 购买策略和 Bot 模板"
- Invezz 评出 2026 年 5 大跟单平台：Pepperstone（外汇低点差）、NinjaTrader（期货策略镜像）、Interactive Brokers（机构级投资组合复制）
- Nexwave 从"AI Agent 部署服务"转型为"Hyperliquid 上的社交交易平台，最佳信号交易员是 AI Agent"
- Poly_Follow：Polymarket 预测市场的 AI 跟单层，"多维度交易员评分 + 近实时执行"
- TradeVerse："5 步开始 AI 跟单——注册、连接 MT5、存款、一键跟单"

**核心洞察**：
- 跟单的关键不是"跟谁"，而是**"如何评估谁值得跟"**
- 现有平台的问题：只展示收益率，不展示风险调整后收益、最大回撤、策略风格
- **机会：做一个"交易员评分系统 + 智能匹配"**，而不只是简单复制交易

### 产品定义

**一句话**：交易策略的"大众点评" — AI 评分 + 一键跟单 + 风险匹配

**核心功能**：
1. **交易员排行榜** — 不只看收益率，AI 综合评分：夏普比率、最大回撤、交易频率、策略一致性
2. **策略标签系统** — 自动分类：日内/波段/趋势、外汇/加密/股票、激进/稳健
3. **AI 风险匹配** — 根据你的风险偏好和资金量，推荐最适合的交易员/策略
4. **智能跟单** — 不是盲目复制，AI 根据你的仓位自动调整比例，设置独立止损
5. **策略 Marketplace** — 交易员可以上架策略收费，平台抽成

**差异化**：不是另一个"复制交易"，而是"AI 帮你选对人 + 控制风险"

### 技术实现

```
前端: Next.js + shadcn/ui（排行榜 + 详情页 + 跟单设置）
后端: Python FastAPI + Celery（异步跟单执行）
AI:   Claude API（交易员评分 + 风险匹配 + 策略分类）
数据: 券商 API（交易记录拉取 + 下单执行）
DB:   Supabase（用户数据 + 交易记录 + 评分历史）
部署: Vercel + Railway + Redis（实时队列）
```

### 变现模式

| 收入来源 | 模式 |
|----------|------|
| 跟单者订阅 | $19-49/月 按跟单账户数收费 |
| 策略上架抽成 | 交易员收费的 20% 平台抽成 |
| Premium 分析 | $9/月 AI 深度分析报告（回撤概率、蒙特卡洛模拟） |

### 开发节奏

- 第 1 周：交易员数据拉取 + 排行榜 UI + AI 评分逻辑
- 第 2 周：跟单执行引擎 + 仓位自动调整
- 第 3 周：策略 Marketplace + 支付集成
- 第 4 周：风险匹配 + 上线

### 来源链接

| 证据 | 链接 |
|------|------|
| Cryptohopper 社交交易 Marketplace | https://www.cryptohopper.com/ |
| 2026 年 5 大跟单平台 | https://invezz.com/trading/best-copy-trading-platforms/ |
| Nexwave 转型社交交易（AI Agent 是信号源） | https://x.com/diopfode/status/2037623913115525584 |
| Poly_Follow AI 跟单 + 多维评分 | https://x.com/AiCapitalMarket/status/2041373944700350927 |
| TradeVerse 5 步 AI 跟单 | https://x.com/Tradeverse_WW/status/2042129313710170341 |
| Telegram Signal Copier 90,000+ 用户 | https://gist.github.com/wxss540/4aea44c0d18de2e6c9afe018aab8ad54 |
| StockHero AI Bot 评测 | https://www.stockbrokers.com/guides/ai-stock-trading-bots |
| Freqtrade 开源交易 Bot | https://github.com/freqtrade/freqtrade |
| HedgeVision 开源对冲基金 AI | https://x.com/MrAyush108/status/2041707044022186062 |
| 蒙特卡洛模拟回撤估算（9K views） | https://www.instagram.com/reel/DWi8rPGjBHh/ |

---

## 方向三：Prop Firm 通关助手（AI 风控管家）

### 为什么做这个

**Prop Firm（自营交易公司）是 2026 年交易行业最大的增量市场**：
- 佣金战白热化（$0.50 到 $1.90 / per @nuttybartrading）
- 平台多元化（GFT 同时支持 5 个交易平台 / per @GoatFunded 160 likes）
- 但 **大量交易者在挑战阶段就被淘汰** — 不是因为交易能力不行，而是因为风控规则违规

**用户痛点**（极度精准）：
- @fortunemmxm："因为不会用 TradeLocker 平台就挂掉了挑战账户"
- TikTok @adiltrader369（25,414 views, 1,059 likes）："Stop blowing funded accounts! 仓位管理、回撤限制和每日亏损规则决定了你的 funded 账户能活多久"
- 各 Prop Firm 规则不同：有的最大回撤 5%，有的 8%；有的有每日亏损限制，有的没有；有的允许隔夜持仓，有的不允许

**核心洞察**：
- 交易者的问题不是"怎么赚钱"，而是**"怎么不违规被淘汰"**
- 这是一个**纯工具需求**，不涉及投资建议，法律风险极低
- Prop Firm 生态有几十家公司，规则各不相同 — **做一个统一的规则引擎就是壁垒**

### 产品定义

**一句话**：Prop Firm 交易者的"AI 风控秘书" — 实时监控规则合规，防止你被淘汰

**核心功能**：
1. **Prop Firm 规则库** — 预置 20+ 家 Prop Firm 的考核规则（最大回撤、每日亏损、持仓时间、新闻交易限制等）
2. **实时合规监控** — 连接券商 API，实时计算当前账户状态 vs 考核规则的距离
3. **AI 预警系统** — "你距离每日最大亏损还剩 $127，建议今天不再开新仓" / "当前回撤已达 3.2%，最大允许 5%"
4. **智能仓位锁定** — 根据剩余风险额度自动计算最大允许仓位，防止过度交易
5. **通关路线图** — AI 分析你的交易记录，告诉你"按照当前节奏，预计 X 天通过挑战"，或"你需要调整 Y 才能通关"
6. **多账户管理** — 同时管理多家 Prop Firm 的挑战账户 / funded 账户

**差异化**：不帮你交易，只帮你不被淘汰 — 最安全的定位

### 技术实现

```
前端: Next.js + shadcn/ui（仪表盘 + 规则监控面板）
后端: Python FastAPI
AI:   Claude API（规则解析 + 预警生成 + 通关预测）
数据: 券商 API（实时账户数据）+ Prop Firm 规则数据库（手动维护 + AI 辅助更新）
实时: WebSocket 推送预警
通知: Telegram Bot + Email + 浏览器推送
部署: Vercel + Railway
```

### 变现模式

| 层级 | 价格 | 功能 |
|------|------|------|
| Free | $0 | 1 个账户 + 基础规则监控 |
| Pro | $19/月 | 3 个账户 + AI 预警 + 仓位锁定 |
| Unlimited | $39/月 | 无限账户 + 通关路线图 + 历史分析 |

**额外收入**：与 Prop Firm 合作推广（CPA 分成），每家 Prop Firm 获客成本 $100-300

### 开发节奏

- 第 1 周：规则库搭建（Top 10 Prop Firm）+ 基础 UI
- 第 2 周：券商 API 对接 + 实时合规计算
- 第 3 周：AI 预警 + 仓位锁定 + 通知系统
- 第 4 周：通关路线图 + 上线

### 来源链接

| 证据 | 链接 |
|------|------|
| Prop Firm 佣金对比（8 家精确费率） | https://x.com/nuttybartrading/status/2042969525834883299 |
| GFT 支持 5 个平台（160 likes） | https://x.com/GoatFunded/status/2042623891302961436 |
| "不会用平台就挂了挑战账户" | https://x.com/fortunemmxm/status/2042863577971745162 |
| 风控规则是关键（25K views） | https://www.tiktok.com/@adiltrader369/video/7627318098483334421 |
| 24 家使用 TradeLocker 的 Prop Firm | https://www.aquafutures.io/blogs/prop-firms-that-use-tradelocker |
| 56% 准确率 + 正确风控 > 70% 准确率 | https://x.com/commutatioaii/status/2041908932638384254 |
| TradeLocker 自动百分比风控优势 | https://x.com/bobil2322/status/2041401255721923013 |
| Guardfolio 投资组合风控 | https://www.guardfolio.ai/portfolio-risk-management |
| Binance Bot 风控实现（GitHub） | https://github.com/victormonedero3-hue/DEMO/pull/3 |
| 蒙特卡洛回撤模拟 | https://www.instagram.com/reel/DWi8rPGjBHh/ |

---

## 三个方向对比总结

| 维度 | 方向一：信号聚合+风控 | 方向二：社交跟单 | 方向三：Prop Firm 通关助手 |
|------|----------------------|-----------------|--------------------------|
| **开发周期** | 3-4 周 | 4 周 | 3 周 |
| **技术难度** | 中 | 中高 | 低-中 |
| **市场验证** | 强（痛点明确） | 强（赛道热） | 极强（用户在 TikTok 上疯狂讨论） |
| **付费意愿** | 高 ($29-69/月) | 高 ($19-49/月) | 极高（交易者已在 Prop Firm 花了 $100-500） |
| **法律风险** | 低（工具定位） | 中（涉及跟单执行） | 极低（纯合规监控） |
| **竞争程度** | 中（有信号服务但无智能过滤） | 高（大平台已入场） | 低（几乎空白市场） |
| **壁垒** | AI 评分算法 | 交易员社区网络效应 | Prop Firm 规则库 |
| **扩展性** | 可升级为全功能交易终端 | 可升级为策略 Marketplace | 可扩展为 Prop Firm SaaS 服务 |

### 我的推荐排序

1. **方向三：Prop Firm 通关助手** — 法律风险最低、竞争最小、付费意愿最强、开发最快
2. **方向一：信号聚合+风控仪表盘** — 痛点最精准、差异化最明确
3. **方向二：社交跟单** — 市场最大但竞争也最大，适合作为第二阶段产品

**最优路径**：先做方向三快速验证 → 积累用户后加入方向一的信号聚合能力 → 最终演化为方向二的社交交易生态
