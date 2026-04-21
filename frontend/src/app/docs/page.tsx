"use client";

import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { LocaleSwitcher } from "@/components/dashboard/LocaleSwitcher";

const docs: Record<string, Record<string, string>> = {
  en: {
    heroDesc: "AI-powered risk management for Prop Firm traders. Real-time compliance monitoring, intelligent signal filtering, helping you pass the challenge instead of getting eliminated.",
    tagReadonly: "Read-only Monitoring",
    tagAi: "AI Powered",
    tagLegal: "Zero Legal Risk",
    problemTitle: "Problem",
    problemP1: "Prop Firm challenges eliminate traders not because of poor trading skills, but because of risk rule violations — drawdown exceeded, daily loss exceeded, position time violations.",
    problemP2: "Meanwhile, traders are overwhelmed by signals. Four tabs open, information everywhere, not knowing which signal is worth acting on.",
    problemCallout: "56% accuracy + correct risk management > 70% accuracy + fixed position sizing. Risk management matters more than prediction, but nobody combines both.",
    solutionTitle: "Solution",
    riskTitle: "Prop Firm Risk Manager",
    riskDesc: "Connect to broker API, show how far you are from violations in real-time. Telegram alerts when approaching limits.",
    signalTitle: "Signal Intelligence",
    signalDesc: "Don't produce signals, filter them. Help you find the one worth acting on from the noise.",
    architectureTitle: "Architecture",
    firmsTitle: "Supported Prop Firms",
    rulesGuideTitle: "Understanding Your Compliance Cards",
    rulesGuideIntro: "Your compliance dashboard shows one card per active rule. Here is what each rule type means and why the distinction matters.",
    ruleDailyLossTitle: "Daily Loss",
    ruleDailyLossDesc: "A per-session loss cap. Breach it and you either (a) fail the challenge outright or (b) have your positions auto-liquidated until the next session. Reset time varies by firm — FTMO resets at 00:00 CET, TopStep at 17:00 CT. The dollar floor moves every day based on the previous day's closing balance.",
    ruleMaxDrawdownTitle: "Max Drawdown (static vs trailing)",
    ruleMaxDrawdownDesc: "A lifetime-of-account equity floor. Static drawdown locks the floor at a fixed dollar amount from initial balance (FTMO 2-Step: 10% below start, forever). Trailing drawdown moves the floor up as your equity grows — TopStep and Apex both use end-of-day trailing, meaning the floor shifts at session close, not intraday.",
    ruleBestDayTitle: "Consistency / Best-Day Rule",
    ruleBestDayDesc: "Your single best profit day cannot exceed 50% of total profits. Not a hard breach — you simply can't pass the challenge until the rule is satisfied. Prevents 'lucky single-day' accounts from graduating. FTMO, TopStep, Maven all enforce this.",
    ruleMinDaysTitle: "Minimum Trading Days",
    ruleMinDaysDesc: "At least N calendar days with at least one trade each. FTMO requires 4, FundedNext 5, Maven 3 profitable days per phase. Meant to prevent all-in-one-day gambling from passing.",
    ruleTimeLimitTitle: "Time Limit",
    ruleTimeLimitDesc: "Maximum days to hit profit target. FTMO removed time limits in 2024 — so did FundedNext, The5ers, Maven, FundingPips. TopStep and Apex never had them. Some legacy firms still enforce 30 days.",
    ruleLeverageTitle: "Leverage / Position Size",
    ruleLeverageDesc: "Per-firm caps on how much notional exposure you can carry. The5ers is strictest (1:30). FTMO sits at 1:100 for FX. Apex caps absolute contract count by account size instead.",
    freshnessBannerTitle: "Why You See a Yellow or Red Banner",
    freshnessBannerDesc: "Rules change. Firms tighten drawdowns, switch to trailing, add consistency rules, remove time limits. We stamp each rule set with the date it was last re-verified against the firm's official page. If the stamp is older than 90 days, we show an amber warning above your compliance grid. Older than 180 days, we show red.",
    apiTitle: "API Endpoints",
    pricingTitle: "Pricing",
    quickstartTitle: "Quick Start",
    roadmapTitle: "Roadmap",
    footerTagline: "Don't help you trade, just help you not get eliminated.",
  },
  zh: {
    heroDesc: "Prop Firm 交易者的 AI 风控管家。实时监控考核规则合规状态，智能过滤交易信号，帮你通过挑战而不是被淘汰。",
    tagReadonly: "只读监控",
    tagAi: "AI 驱动",
    tagLegal: "零法律风险",
    problemTitle: "问题",
    problemP1: "Prop Firm 挑战中，大量交易者被淘汰。不是因为交易能力不行，而是因为风控规则违规 —— 回撤超限、每日亏损超限、违反持仓规则。",
    problemP2: "同时，交易者被海量信号淹没。四个标签页打开，信息到处都是，不知道该看什么，不知道哪个信号值得行动。",
    problemCallout: "56% 准确率 + 正确风控 > 70% 准确率 + 固定仓位。风控比预测更重要，但没人把两者做到一起。",
    solutionTitle: "解决方案",
    riskTitle: "Prop Firm 风控管家",
    riskDesc: "连接券商 API，实时展示你离违规还有多远。接近限额时 Telegram 推送预警。",
    signalTitle: "信号智能过滤",
    signalDesc: "不生产信号，过滤信号。帮你从噪音中找到值得行动的那一个。",
    architectureTitle: "技术架构",
    firmsTitle: "支持的 Prop Firm",
    rulesGuideTitle: "看懂你的合规卡",
    rulesGuideIntro: "合规面板每条规则对应一张卡。下面解释每种规则的含义和关键区别。",
    ruleDailyLossTitle: "每日亏损 (Daily Loss)",
    ruleDailyLossDesc: "单日亏损上限。突破后要么直接挑战失败，要么强平所有持仓等下个 session。重置时间每家不同 —— FTMO 是 CET 00:00，TopStep 是 CT 17:00。每天的美元地板根据前一天收盘余额动态调整。",
    ruleMaxDrawdownTitle: "最大回撤 (static vs trailing)",
    ruleMaxDrawdownDesc: "账户生命周期的权益地板。Static 固定在初始余额下方某个固定美元数（FTMO 2-Step：10% 下方，永远不变）。Trailing 随着权益新高往上移 —— TopStep 和 Apex 用 EOD trailing，意思是地板在 session 收盘时才移动，盘中不动。",
    ruleBestDayTitle: "一致性 / 最佳日规则",
    ruleBestDayDesc: "单日最大盈利不能超过总利润的 50%。这不是硬违规 —— 只是规则满足之前你无法过关。目的是防止'运气好单日大赚'的账户毕业。FTMO、TopStep、Maven 都有此规则。",
    ruleMinDaysTitle: "最低交易天数",
    ruleMinDaysDesc: "至少 N 天自然日各有至少一笔交易。FTMO 要求 4，FundedNext 5，Maven 要求 3 个盈利日/phase（更严）。目的是防止「一天梭哈」式过关。",
    ruleTimeLimitTitle: "时间限制",
    ruleTimeLimitDesc: "达到利润目标的最长天数。FTMO 2024 年取消时间限制 —— FundedNext、The5ers、Maven、FundingPips 也都取消了。TopStep 和 Apex 从来没有。少数老牌 prop 还在用 30 天限制。",
    ruleLeverageTitle: "杠杆 / 仓位大小",
    ruleLeverageDesc: "每家对名义敞口的上限。The5ers 最严 (1:30)。FTMO 外汇 1:100。Apex 不按杠杆而按绝对合约数量限制。",
    freshnessBannerTitle: "为什么看到黄色或红色横幅",
    freshnessBannerDesc: "规则会变。公司会收紧回撤、改成 trailing、加一致性规则、取消时间限制。我们给每套规则打上「最后核对日期」。如果超过 90 天没核对，合规表格上方会显示琥珀色警告。超过 180 天，显示红色。",
    apiTitle: "API 端点",
    pricingTitle: "定价",
    quickstartTitle: "快速开始",
    roadmapTitle: "路线图",
    footerTagline: "不帮你交易，只帮你不被淘汰。",
  },
};

export default function DocsPage() {
  const { locale } = useI18n();
  const d = docs[locale] || docs.en;
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-300">
      {/* Nav */}
      <nav className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between max-w-5xl mx-auto">
        <Link href="/" className="text-white font-bold text-lg hover:text-zinc-300 transition-colors">
          PropGuard AI
        </Link>
        <div className="flex items-center gap-4">
          <LocaleSwitcher />
          <Link href="/" className="text-sm text-zinc-500 hover:text-white transition-colors">
            &larr; Back to Dashboard
          </Link>
        </div>
      </nav>

      <div className="max-w-3xl mx-auto px-6 py-12 space-y-16">
        {/* Hero */}
        <header className="space-y-4">
          <h1 className="text-4xl font-bold text-white tracking-tight">
            PropGuard AI
          </h1>
          <p className="text-xl text-zinc-400 leading-relaxed">
            {d.heroDesc}
          </p>
          <div className="flex gap-3 pt-2">
            <span className="px-3 py-1 bg-green-900/40 text-green-400 text-xs rounded-full">{d.tagReadonly}</span>
            <span className="px-3 py-1 bg-blue-900/40 text-blue-400 text-xs rounded-full">{d.tagAi}</span>
            <span className="px-3 py-1 bg-purple-900/40 text-purple-400 text-xs rounded-full">{d.tagLegal}</span>
          </div>
        </header>

        {/* Problem */}
        <Section title={d.problemTitle}>
          <p>
            {d.problemP1}
          </p>
          <p>
            {d.problemP2}
          </p>
          <Callout>
            {d.problemCallout}
          </Callout>
        </Section>

        {/* Solution */}
        <Section title={d.solutionTitle}>
          <p>{d.solutionTitle}</p>
          <div className="grid md:grid-cols-2 gap-6 mt-4">
            <FeatureBlock
              title={d.riskTitle}
              description={d.riskDesc}
              items={[
                "预置 FTMO、TopStep、CryptoFundTrader 等考核规则",
                "实时合规监控（账户状态 vs 规则距离）",
                "4 级告警：SAFE → WARNING → CRITICAL → DANGER",
                "AI 盘前简报（今日风险评估 + 建议）",
              ]}
            />
            <FeatureBlock
              title={d.signalTitle}
              description={d.signalDesc}
              items={[
                "多源信号聚合（Telegram 转发 + TradingView Webhook）",
                "AI 信号评分（0-100，基于历史胜率、风险回报比、市场环境）",
                "智能仓位计算（1% 风险规则 + Kelly 参考）",
                "盘前 Top 3 信号推荐",
              ]}
            />
          </div>
        </Section>

        {/* Key Design Decisions */}
        <Section title="关键设计决策">
          <Decision
            title="只读，不执行"
            description="MVP 阶段不做任何交易执行或拦截。95% 可靠的风控工具比没有工具更危险 —— 用户会因为信任它而加大仓位。只读定位确保即使有 bug，用户的损失不会因为我们的工具而放大。"
          />
          <Decision
            title="规则引擎，不是硬编码"
            description="每家 Prop Firm 的规则以 JSON 文件存储，含版本号和生效日期。规则更新时只改 JSON，不改代码。这让我们能快速扩展到 10+ 家 Prop Firm。"
          />
          <Decision
            title="AI 是增值层，不是核心依赖"
            description="Claude API 挂了，规则监控照常工作。信号评分自动回退到基于规则的评分算法。AI 让产品更好，但不是产品能不能用的前提。"
          />
          <Decision
            title="用户转发模式接入信号"
            description="不做 Telegram userbot 爬取（违反 ToS）。用户主动把信号群的消息转发给我们的 Bot。合规、安全、用户可控。"
          />
        </Section>

        {/* Architecture */}
        <Section title={d.architectureTitle}>
          <pre className="bg-zinc-900 rounded-lg p-6 text-sm overflow-x-auto text-zinc-400 leading-relaxed">{`┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│         Next.js + TypeScript + shadcn/ui         │
│                                                   │
│  Dashboard ─── Compliance Cards ─── Signal Panel │
│  Briefing ──── Position Calculator               │
│         ↕ WebSocket (exponential backoff)         │
├─────────────────────────────────────────────────┤
│                   Backend                         │
│              Python FastAPI                       │
│                                                   │
│  Rule Engine ← JSON Rules (8 firms, freshness-aware)     │
│  Signal Parser ← Telegram Bot / TradingView Hook │
│  AI Scorer ← Claude API (Haiku) + Rule Fallback  │
│  Alert Service → Telegram Bot API                │
│  Position Calculator (1% + Kelly)                │
│  Tier Enforcement (Free/Pro/Premium)             │
│         ↕ Broker API (partner)                    │
├─────────────────────────────────────────────────┤
│                   Data                            │
│  Supabase (users, signals, history)              │
│  JSON Rules (versioned, per-firm)                │
└─────────────────────────────────────────────────┘`}</pre>
        </Section>

        {/* Supported Firms */}
        <Section title={d.firmsTitle}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-zinc-500 uppercase tracking-wider border-b border-zinc-800">
                  <th className="pb-3 pr-4">Firm</th>
                  <th className="pb-3 pr-4">市场</th>
                  <th className="pb-3 pr-4">Daily Loss</th>
                  <th className="pb-3 pr-4">Max Drawdown</th>
                  <th className="pb-3">特点</th>
                </tr>
              </thead>
              <tbody className="text-zinc-300">
                <tr className="border-b border-zinc-900">
                  <td className="py-3 pr-4 font-medium text-white">FTMO</td>
                  <td className="py-3 pr-4">外汇 / 指数 / 商品 / 加密</td>
                  <td className="py-3 pr-4">5% (2-step) / 3% (1-step)</td>
                  <td className="py-3 pr-4">10% (static 2-step) / 10% trailing (1-step)</td>
                  <td className="py-3 text-zinc-400">新闻交易限制, 4 天最低, 无时间限制</td>
                </tr>
                <tr className="border-b border-zinc-900">
                  <td className="py-3 pr-4 font-medium text-white">TopStep</td>
                  <td className="py-3 pr-4">期货</td>
                  <td className="py-3 pr-4">$1K-3K (Classic) / 无 (TopstepX)</td>
                  <td className="py-3 pr-4">EOD 追踪</td>
                  <td className="py-3 text-zinc-400">合约数限制, 一致性规则</td>
                </tr>
                <tr className="border-b border-zinc-900">
                  <td className="py-3 pr-4 font-medium text-white">CryptoFundTrader</td>
                  <td className="py-3 pr-4">加密 / 外汇</td>
                  <td className="py-3 pr-4">4-5%</td>
                  <td className="py-3 pr-4">6% (Instant) / 10% (2-phase)</td>
                  <td className="py-3 text-zinc-400">Bybit 直连, MT5 / Match-Trader</td>
                </tr>
                <tr className="border-b border-zinc-900">
                  <td className="py-3 pr-4 font-medium text-white">FundedNext</td>
                  <td className="py-3 pr-4">外汇 / 指数 / 商品 / 加密</td>
                  <td className="py-3 pr-4">5%</td>
                  <td className="py-3 pr-4">10% (静态)</td>
                  <td className="py-3 text-zinc-400">无时间限制, 最高 95% 分成, MT5 / Match-Trader / cTrader</td>
                </tr>
                <tr className="border-b border-zinc-900">
                  <td className="py-3 pr-4 font-medium text-white">The5ers</td>
                  <td className="py-3 pr-4">外汇 / 指数 / 商品</td>
                  <td className="py-3 pr-4">3% (严格)</td>
                  <td className="py-3 pr-4">6% Stop Out (严格)</td>
                  <td className="py-3 text-zinc-400">1:30 杠杆上限, 无最低交易天数, cTrader / MT5</td>
                </tr>
                <tr className="border-b border-zinc-900">
                  <td className="py-3 pr-4 font-medium text-white">Apex</td>
                  <td className="py-3 pr-4">期货</td>
                  <td className="py-3 pr-4">无</td>
                  <td className="py-3 pr-4">Live trailing (按账户浮动)</td>
                  <td className="py-3 text-zinc-400">100% 首 $25K 分成, 8 天 payout, 新闻允许</td>
                </tr>
                <tr className="border-b border-zinc-900">
                  <td className="py-3 pr-4 font-medium text-white">Maven</td>
                  <td className="py-3 pr-4">外汇 / 指数 / 商品 / 加密</td>
                  <td className="py-3 pr-4">2% (极严) / 4% (1-step)</td>
                  <td className="py-3 pr-4">8% 静态</td>
                  <td className="py-3 text-zinc-400">3 次 payout 后费用退还, 低预算入门 ($13 起)</td>
                </tr>
                <tr>
                  <td className="py-3 pr-4 font-medium text-white">FundingPips</td>
                  <td className="py-3 pr-4">外汇 / 指数 / 商品 / 加密</td>
                  <td className="py-3 pr-4">5% (Standard) / 3% (Pro) / 4% (1-step) / 3% (Instant)</td>
                  <td className="py-3 pr-4">10% / 6% / 5% trailing (按产品)</td>
                  <td className="py-3 text-zinc-400">4 次 payout 后费用退还, MT5 / DxTrade / Match-Trader</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Section>

        {/* Rules Guide */}
        <Section title={d.rulesGuideTitle}>
          <p className="text-zinc-400 text-sm mb-4">{d.rulesGuideIntro}</p>
          <div className="grid gap-3">
            <RuleExplainer title={d.ruleDailyLossTitle} desc={d.ruleDailyLossDesc} />
            <RuleExplainer title={d.ruleMaxDrawdownTitle} desc={d.ruleMaxDrawdownDesc} />
            <RuleExplainer title={d.ruleBestDayTitle} desc={d.ruleBestDayDesc} />
            <RuleExplainer title={d.ruleMinDaysTitle} desc={d.ruleMinDaysDesc} />
            <RuleExplainer title={d.ruleTimeLimitTitle} desc={d.ruleTimeLimitDesc} />
            <RuleExplainer title={d.ruleLeverageTitle} desc={d.ruleLeverageDesc} />
            <div className="rounded-md border border-amber-900/40 bg-amber-950/20 px-4 py-3 text-sm">
              <div className="font-medium text-amber-200 mb-1">{d.freshnessBannerTitle}</div>
              <div className="text-amber-100/70 leading-relaxed">{d.freshnessBannerDesc}</div>
            </div>
          </div>
        </Section>

        {/* API */}
        <Section title={d.apiTitle}>
          <div className="space-y-2">
            <Endpoint method="GET" path="/api/firms" description="获取所有支持的 Prop Firm 列表" />
            <Endpoint method="GET" path="/api/firms/{name}/rules" description="获取某家 Prop Firm 的完整规则" />
            <Endpoint method="GET" path="/api/accounts/{id}/compliance" description="获取账户实时合规状态" />
            <Endpoint method="GET" path="/api/accounts/{id}/briefing" description="生成盘前 AI 简报" />
            <Endpoint method="WS" path="/ws/compliance/{id}" description="WebSocket 实时合规数据流" />
            <Endpoint method="POST" path="/api/signals/parse" description="解析并评分交易信号" />
            <Endpoint method="POST" path="/api/webhook/tradingview" description="TradingView Webhook 接收" />
            <Endpoint method="POST" path="/api/position/calculate" description="仓位大小计算" />
            <Endpoint method="GET" path="/api/signals/top" description="获取评分最高的信号" />
            <Endpoint method="GET" path="/api/tier/{user}/check/{feature}" description="检查功能权限" />
          </div>
        </Section>

        {/* Pricing */}
        <Section title={d.pricingTitle}>
          <div className="grid md:grid-cols-3 gap-4">
            <PricingCard
              tier="Free"
              price="$0"
              features={[
                "1 个 Prop Firm 账户监控",
                "3 个信号源（展示但不评分）",
                "基础规则合规检查",
                "Web 端告警",
              ]}
            />
            <PricingCard
              tier="Pro"
              price="$29/月"
              highlight
              features={[
                "3 个账户监控",
                "无限信号源",
                "AI 信号评分",
                "盘前 AI 简报",
                "Telegram + Email 告警",
              ]}
            />
            <PricingCard
              tier="Premium"
              price="$49/月"
              features={[
                "无限账户监控",
                "仓位计算器",
                "历史分析",
                "全渠道告警",
                "通关路线图 (V1.1)",
              ]}
            />
          </div>
        </Section>

        {/* Quick Start */}
        <Section title={d.quickstartTitle}>
          <div className="space-y-6">
            <Step number={1} title="启动后端">
              <Code>{`cd backend
cp .env.example .env
# 编辑 .env 填入 API keys
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8001`}</Code>
            </Step>
            <Step number={2} title="启动前端">
              <Code>{`cd frontend
npm install
npm run dev -- --port 3001`}</Code>
            </Step>
            <Step number={3} title="打开 Dashboard">
              <p>
                浏览器访问{" "}
                <code className="bg-zinc-800 px-2 py-0.5 rounded text-zinc-300">http://localhost:3001</code>
                ，选择 Prop Firm 和账户大小，开始监控。
              </p>
            </Step>
            <Step number={4} title="测试信号评分">
              <Code>{`curl -X POST http://localhost:8001/api/signals/parse \\
  -H "Content-Type: application/json" \\
  -d '{"text": "BUY BTCUSD @ 65000 SL: 63000 TP: 70000"}'`}</Code>
            </Step>
          </div>
        </Section>

        {/* Roadmap */}
        <Section title={d.roadmapTitle}>
          <div className="space-y-3">
            <RoadmapItem status="done" text="Prop Firm 规则引擎 (FTMO, TopStep, CryptoFundTrader)" />
            <RoadmapItem status="done" text="实时合规监控 Dashboard + WebSocket" />
            <RoadmapItem status="done" text="信号解析器 + AI 评分 (Claude API + 规则回退)" />
            <RoadmapItem status="done" text="盘前 AI 简报" />
            <RoadmapItem status="done" text="仓位计算器 (1% + Kelly)" />
            <RoadmapItem status="done" text="TradingView Webhook 接入" />
            <RoadmapItem status="done" text="Free / Pro / Premium 层级控制" />
            <RoadmapItem status="next" text="真实券商 API 对接（替换 mock 数据）" />
            <RoadmapItem status="next" text="Supabase 持久化（用户、信号历史）" />
            <RoadmapItem status="next" text="Telegram Bot 完整接入" />
            <RoadmapItem status="planned" text="通关路线图（AI 预测通关天数）" />
            <RoadmapItem status="planned" text="扩展至 10+ 家 Prop Firm" />
            <RoadmapItem status="planned" text="移动端适配" />
          </div>
        </Section>

        {/* Footer */}
        <footer className="border-t border-zinc-800 pt-8 text-center text-zinc-600 text-sm">
          <p>PropGuard AI v0.1.0</p>
          <p className="mt-1">{d.footerTagline}</p>
        </footer>
      </div>
    </main>
  );
}

/* ── Sub-components ────────────────────────────── */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="text-2xl font-bold text-white">{title}</h2>
      <div className="space-y-3 leading-relaxed">{children}</div>
    </section>
  );
}

function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-l-2 border-yellow-600 bg-yellow-950/20 pl-4 py-3 text-sm text-yellow-200">
      {children}
    </div>
  );
}

function FeatureBlock({ title, description, items }: { title: string; description: string; items: string[] }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-5 space-y-3">
      <h3 className="text-lg font-semibold text-white">{title}</h3>
      <p className="text-sm text-zinc-400">{description}</p>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-sm text-zinc-300 flex items-start gap-2">
            <span className="text-green-500 mt-0.5">+</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Decision({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-b border-zinc-900 pb-4">
      <h3 className="text-base font-semibold text-white mb-1">{title}</h3>
      <p className="text-sm text-zinc-400">{description}</p>
    </div>
  );
}

function RuleExplainer({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900/40 px-4 py-3">
      <div className="text-sm font-semibold text-white mb-1">{title}</div>
      <div className="text-sm text-zinc-400 leading-relaxed">{desc}</div>
    </div>
  );
}

function Endpoint({ method, path, description }: { method: string; path: string; description: string }) {
  const color = method === "GET" ? "text-green-400" : method === "POST" ? "text-blue-400" : "text-purple-400";
  return (
    <div className="flex items-start gap-3 bg-zinc-900 rounded px-4 py-2.5">
      <span className={`font-mono text-xs font-bold w-10 shrink-0 ${color}`}>{method}</span>
      <code className="font-mono text-xs text-zinc-300 shrink-0">{path}</code>
      <span className="text-xs text-zinc-500 ml-auto">{description}</span>
    </div>
  );
}

function PricingCard({ tier, price, features, highlight = false }: { tier: string; price: string; features: string[]; highlight?: boolean }) {
  return (
    <div className={`rounded-lg p-5 space-y-4 ${highlight ? "bg-zinc-800 ring-1 ring-green-800" : "bg-zinc-900"}`}>
      <div>
        <p className="text-sm text-zinc-400">{tier}</p>
        <p className="text-2xl font-bold text-white">{price}</p>
      </div>
      <ul className="space-y-2">
        {features.map((f, i) => (
          <li key={i} className="text-sm text-zinc-300 flex items-start gap-2">
            <span className="text-green-500">&#10003;</span>
            {f}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Step({ number, title, children }: { number: number; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4">
      <div className="w-8 h-8 rounded-full bg-zinc-800 text-white flex items-center justify-center text-sm font-bold shrink-0">
        {number}
      </div>
      <div className="space-y-2 flex-1">
        <h3 className="text-base font-semibold text-white">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre className="bg-zinc-900 rounded-lg p-4 text-sm text-zinc-400 overflow-x-auto">
      <code>{children}</code>
    </pre>
  );
}

function RoadmapItem({ status, text }: { status: "done" | "next" | "planned"; text: string }) {
  const icon = status === "done" ? "text-green-500" : status === "next" ? "text-yellow-500" : "text-zinc-600";
  const label = status === "done" ? "&#10003;" : status === "next" ? "&#9654;" : "&#9675;";
  return (
    <div className="flex items-center gap-3">
      <span className={`text-sm ${icon}`} dangerouslySetInnerHTML={{ __html: label }} />
      <span className={`text-sm ${status === "planned" ? "text-zinc-500" : "text-zinc-300"}`}>{text}</span>
    </div>
  );
}
