// Shared pricing config between the landing page and /pricing.

export type Plan = "free" | "pro" | "premium";

export type PlanConfig = {
  key: Plan;
  price: { en: string; zh: string };
  features: { en: string[]; zh: string[] };
  highlight?: boolean;
};

export const PLANS: PlanConfig[] = [
  {
    key: "free",
    price: { en: "$0", zh: "¥0" },
    features: {
      en: [
        "Sandbox trading ($100,000 simulation)",
        "20 AI scores / day",
        "100 AI auto-trade ticks / day",
        "3 saved strategies",
        "7-day history retention",
      ],
      zh: [
        "沙盒交易（$100,000 模拟）",
        "每日 20 次 AI 评分",
        "每日 100 次 AI 自动交易",
        "3 个策略保存",
        "历史保留 7 天",
      ],
    },
  },
  {
    key: "pro",
    price: { en: "$29/mo", zh: "¥199/月" },
    features: {
      en: [
        "Bind real MetaApi account",
        "500 AI scores / day",
        "2000 AI auto-trade ticks / day",
        "50 saved strategies",
        "24/7 backend auto-trader (works when browser is closed)",
        "Permanent history",
      ],
      zh: [
        "绑定真实 MetaApi 账户",
        "每日 500 次 AI 评分",
        "每日 2000 次 AI 自动交易",
        "50 个策略保存",
        "7x24 后台自动交易（关浏览器也跑）",
        "永久历史",
      ],
    },
    highlight: true,
  },
  {
    key: "premium",
    price: { en: "$49/mo", zh: "¥349/月" },
    features: {
      en: [
        "Everything in Pro",
        "Unlimited AI",
        "Multiple real accounts",
        "Telegram alerts",
        "Priority support",
      ],
      zh: [
        "包含 Pro 全部功能",
        "AI 无限额",
        "多个真实账户",
        "Telegram 告警",
        "优先支持",
      ],
    },
  },
];
