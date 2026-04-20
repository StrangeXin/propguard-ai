export type Locale = "en" | "zh";

export const locales: Record<Locale, Record<string, string>> = {
  en: {
    // Header
    "app.title": "PropGuard AI",
    "app.challenge": "Challenge",
    "status.live": "Live",
    "status.connecting": "Connecting...",
    "status.reconnecting": "Connection interrupted, data may be delayed. Reconnecting...",
    "status.brokerConnecting": "Connecting to broker... Real-time data will appear shortly.",

    // Account header
    "account.equity": "Equity",
    "account.balance": "Balance",
    "account.dailyPnl": "Daily P&L",
    "account.totalPnl": "Total P&L",

    // Compliance
    "compliance.title": "Compliance Checks",
    "compliance.dailyLoss": "Daily Loss",
    "compliance.maxDrawdown": "Max Drawdown",
    "compliance.tradingDays": "Trading Days",
    "compliance.positionSize": "Position Size",
    "compliance.used": "Used",
    "compliance.remaining": "Remaining",
    "compliance.limit": "Limit",

    // Chart
    "chart.title": "Chart",
    "chart.loading": "Loading...",

    // Positions
    "positions.title": "Open Positions",
    "positions.empty": "No open positions",
    "positions.symbol": "Symbol",
    "positions.side": "Side",
    "positions.size": "Size",
    "positions.entry": "Entry",
    "positions.current": "Current",
    "positions.pnl": "P&L",
    "positions.by": "By",

    // Briefing
    "briefing.title": "AI Briefing",
    "briefing.generate": "Generate Briefing",
    "briefing.refresh": "Refresh",
    "briefing.generating": "Generating...",
    "briefing.placeholder": "Click \"Generate Briefing\" to get your pre-market AI analysis",
    "briefing.analyzing": "Analyzing your account...",
    "briefing.riskStatus": "Risk Status",
    "briefing.todaysFocus": "Today's Focus",
    "briefing.recommendation": "Recommendation",

    // Signals
    "signals.title": "Signal Intelligence",
    "signals.placeholder": "Paste a trading signal here... e.g. BUY BTCUSD @ 65000 SL: 63000 TP: 70000",
    "signals.hint": "Paste signals from Telegram, TradingView, or type manually",
    "signals.score": "Score Signal",
    "signals.scoring": "Scoring...",
    "signals.empty": "No signals yet. Paste a trading signal above to get started.",
    "signals.error.parse": "Could not parse signal",
    "signals.error.api": "Failed to connect to API",

    // Position Calculator
    "calc.title": "Position Calculator",
    "calc.entryPrice": "Entry Price",
    "calc.stopLoss": "Stop Loss",
    "calc.contractSize": "Contract Size",
    "calc.calculate": "Calculate",
    "calc.recommended": "Recommended Size",
    "calc.riskAmount": "Risk Amount",
    "calc.riskPct": "Risk %",
    "calc.maxAllowed": "Max Allowed",

    // Alerts
    "alerts.title": "Alert History",
    "alerts.empty": "No alerts yet. Alerts appear when compliance limits are approached.",
    "alerts.showAll": "Show all",
    "alerts.showLess": "Show less",

    // Accounts
    "accounts.title": "Accounts",
    "accounts.add": "+ Add Account",
    "accounts.cancel": "Cancel",
    "accounts.empty": "No accounts registered. Click \"+ Add Account\" to start monitoring.",
    "accounts.id": "Account ID",
    "accounts.label": "Label",
    "accounts.firm": "Prop Firm",
    "accounts.size": "Account Size",
    "accounts.broker": "Broker",
    "accounts.addBtn": "Add",

    // Auth / login gate
    "auth.login_required_title": "Login required",
    "auth.email": "Email",
    "auth.password": "Password",
    "auth.login": "Log in",
    "auth.logging_in": "Logging in…",
    "auth.cancel": "Cancel",
    "auth.no_account": "No account?",
    "auth.register_cta": "Register",
    "auth.login_to_place_order": "Log in to place an order on the shared account.",
    "auth.login_to_ai_trade": "Log in to start an AI auto-trade session.",
    "auth.login_to_view_briefing": "Log in to view today's AI briefing.",
    "auth.connect_your_account": "Connect my account",
    "auth.login_to_connect": "Log in to connect your account",
    "auth.connect_your_account_cta": "Log in to connect your own broker account.",

    // Footer
    "footer.lastUpdated": "Last updated",
    "footer.account": "Account",
    "footer.highWatermark": "High watermark",
    "footer.docs": "Product Documentation",
  },

  zh: {
    // Header
    "app.title": "PropGuard AI",
    "app.challenge": "挑战赛",
    "status.live": "实时",
    "status.connecting": "连接中...",
    "status.reconnecting": "连接中断，数据可能延迟。正在重连...",
    "status.brokerConnecting": "正在连接券商... 实时数据即将到来。",

    // Account header
    "account.equity": "净值",
    "account.balance": "余额",
    "account.dailyPnl": "当日盈亏",
    "account.totalPnl": "总盈亏",

    // Compliance
    "compliance.title": "合规检查",
    "compliance.dailyLoss": "每日亏损",
    "compliance.maxDrawdown": "最大回撤",
    "compliance.tradingDays": "交易天数",
    "compliance.positionSize": "仓位大小",
    "compliance.used": "已用",
    "compliance.remaining": "剩余",
    "compliance.limit": "限额",

    // Chart
    "chart.title": "行情图表",
    "chart.loading": "加载中...",

    // Positions
    "positions.title": "持仓列表",
    "positions.empty": "暂无持仓",
    "positions.symbol": "品种",
    "positions.side": "方向",
    "positions.size": "手数",
    "positions.entry": "入场价",
    "positions.current": "当前价",
    "positions.pnl": "盈亏",
    "positions.by": "下单人",

    // Briefing
    "briefing.title": "AI 盘前简报",
    "briefing.generate": "生成简报",
    "briefing.refresh": "刷新",
    "briefing.generating": "生成中...",
    "briefing.placeholder": "点击「生成简报」获取盘前 AI 分析",
    "briefing.analyzing": "正在分析你的账户...",
    "briefing.riskStatus": "风险状态",
    "briefing.todaysFocus": "今日关注",
    "briefing.recommendation": "操作建议",

    // Signals
    "signals.title": "信号智能",
    "signals.placeholder": "在此粘贴交易信号... 例如 BUY BTCUSD @ 65000 SL: 63000 TP: 70000",
    "signals.hint": "从 Telegram、TradingView 粘贴信号，或手动输入",
    "signals.score": "评分",
    "signals.scoring": "评分中...",
    "signals.empty": "暂无信号。在上方粘贴交易信号开始使用。",
    "signals.error.parse": "无法解析信号",
    "signals.error.api": "无法连接 API",

    // Position Calculator
    "calc.title": "仓位计算器",
    "calc.entryPrice": "入场价",
    "calc.stopLoss": "止损价",
    "calc.contractSize": "合约大小",
    "calc.calculate": "计算",
    "calc.recommended": "建议仓位",
    "calc.riskAmount": "风险金额",
    "calc.riskPct": "风险占比",
    "calc.maxAllowed": "最大允许",

    // Alerts
    "alerts.title": "告警历史",
    "alerts.empty": "暂无告警。当接近合规限额时将自动生成告警。",
    "alerts.showAll": "查看全部",
    "alerts.showLess": "收起",

    // Accounts
    "accounts.title": "账户管理",
    "accounts.add": "+ 添加账户",
    "accounts.cancel": "取消",
    "accounts.empty": "暂无监控账户。点击「+ 添加账户」开始。",
    "accounts.id": "账户 ID",
    "accounts.label": "备注名",
    "accounts.firm": "Prop Firm",
    "accounts.size": "账户金额",
    "accounts.broker": "券商",
    "accounts.addBtn": "添加",

    // Auth / login gate
    "auth.login_required_title": "需要登录",
    "auth.email": "邮箱",
    "auth.password": "密码",
    "auth.login": "登录",
    "auth.logging_in": "登录中…",
    "auth.cancel": "取消",
    "auth.no_account": "没有账号？",
    "auth.register_cta": "注册",
    "auth.login_to_place_order": "登录后即可在公用账号上下单。",
    "auth.login_to_ai_trade": "登录后可启动 AI 自动交易。",
    "auth.login_to_view_briefing": "登录后查看今日 AI 简报。",
    "auth.connect_your_account": "连接我的账户",
    "auth.login_to_connect": "登录以连接自己的账户",
    "auth.connect_your_account_cta": "登录后可连接自己的券商账户。",

    // Footer
    "footer.lastUpdated": "最后更新",
    "footer.account": "账户",
    "footer.highWatermark": "净值最高点",
    "footer.docs": "产品文档",
  },
};
