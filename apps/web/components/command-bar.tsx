"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

export interface CommandItem {
  id: string;
  label: string;
  category: "PAGES" | "ACTIONS" | "DECISIONS";
  icon: string;
  href?: string;
  action?: () => void;
  keywords: string[];
  langHints?: { en: string; ur: string; zh: string };
}

interface SpeechRecognitionResultItem {
  transcript: string;
}

interface SpeechRecognitionResultList {
  [index: number]: { [index: number]: SpeechRecognitionResultItem };
}

interface SpeechRecognitionResultEvent {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent {
  error: string;
}

interface BrowserSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
}

interface CommandBarProps {
  isOpen: boolean;
  onClose: () => void;
  onSwitchTenant?: (tenantId: string) => void;
  onToggleTheme?: () => void;
  currentTheme?: "light" | "dark";
}

export function CommandBar({
  isOpen,
  onClose,
  onSwitchTenant,
  onToggleTheme,
  currentTheme = "light",
}: CommandBarProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [voiceLang, setVoiceLang] = useState<"en-US" | "ur-PK" | "zh-CN">("en-US");
  const [isListening, setIsListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands: CommandItem[] = useMemo(
    () => [
      // Navigation
      {
        id: "nav-briefing",
        label: "Briefing",
        category: "PAGES",
        icon: "⌂",
        href: "/",
        keywords: ["briefing", "home", "dashboard", "خلاصہ", "صفحہ اول", "简报", "首页"],
        langHints: { en: "Morning financial briefing", ur: "صبح کا مالیاتی خلاصہ", zh: "每日财务晨报" },
      },
      {
        id: "nav-forecast",
        label: "Cash forecast",
        category: "PAGES",
        icon: "↗",
        href: "/forecast",
        keywords: ["cash", "forecast", "liquidity", "13-week", "کیش", "پیشگوئی", "نقد", "现金", "预测", "流动性"],
        langHints: { en: "13-week cash runway and dips", ur: "۱۳ ہفتوں کی نقد رقم کی پیشن گوئی", zh: "13周现金流预测与低谷预警" },
      },
      {
        id: "nav-launch-lab",
        label: "Launch Lab",
        category: "PAGES",
        icon: "✳",
        href: "/launch-lab",
        keywords: ["launch", "lab", "simulate", "product", "sku", "لانچ", "لیب", "نئی پروڈکٹ", "新品", "试验室", "模拟"],
        langHints: { en: "Simulate new SKU unit economics & break-even", ur: "نئے پروڈکٹ کے معاشی ماڈل کی سیمولیشن", zh: "新SKU单位经济与损益平衡模拟" },
      },
      {
        id: "nav-approvals",
        label: "Approvals & Inbox",
        category: "PAGES",
        icon: "▣",
        href: "/approvals",
        keywords: ["approvals", "inbox", "proposals", "mandate", "منظوریاں", "ان باکس", "审批", "收件箱"],
        langHints: { en: "Guardian-verified proposal queue", ur: "گارڈین سے تصدیق شدہ تجاویز", zh: "Guardian核验后的审批队列" },
      },
      {
        id: "nav-bills",
        label: "Bills & Invoices",
        category: "PAGES",
        icon: "▤",
        href: "/bills",
        keywords: ["bills", "invoices", "fapiao", "payable", "بلز", "انوائس", "بل", "发票", "应付账单"],
        langHints: { en: "Extracted bills, VAT & fapiao status", ur: "نکالے گئے بلز اور ٹیکس", zh: "发票抽取、税率与核销状态" },
      },
      {
        id: "nav-reconcile",
        label: "Reconcile",
        category: "PAGES",
        icon: "⇄",
        href: "/reconcile",
        keywords: ["reconcile", "pos", "bank", "matching", "مطابقت", "بینک", "پی او ایس", "对账", "POS对账", "银行对账"],
        langHints: { en: "Match bank lines and daily POS cash drawer", ur: "بینک اسٹیٹمنٹ اور پی او ایس مطابقت", zh: "流水撮合与每日POS款台对账" },
      },
      {
        id: "nav-inventory",
        label: "Inventory analytics",
        category: "PAGES",
        icon: "▤",
        href: "/inventory",
        keywords: ["inventory", "stock", "abc-xyz", "dead stock", "انوینٹری", "اسٹاک", "库存", "滞销", "品类分析"],
        langHints: { en: "ABC-XYZ classification and reorder safety", ur: "اسٹاک کی درجہ بندی اور دوبارہ آرڈر", zh: "ABC-XYZ周转分类与再订货点" },
      },
      {
        id: "nav-financing",
        label: "Financing matcher",
        category: "PAGES",
        icon: "◇",
        href: "/financing",
        keywords: ["financing", "loan", "debt", "matcher", "فنانسنگ", "قرضہ", "融资", "贷款", "授信方案"],
        langHints: { en: "Match working capital loan options", ur: "ورکنگ کیپیٹل کے قرضے کے آپشنز", zh: "匹配适宜的流动资金借贷方案" },
      },
      {
        id: "nav-council",
        label: "AI Council",
        category: "PAGES",
        icon: "◉",
        href: "/council",
        keywords: ["council", "debate", "agents", "cfo", "کونسل", "بحث", "مشاورت", "理事会", "辩论", "专家咨询"],
        langHints: { en: "Six-agent deliberation mode", ur: "چھ ایجنٹس کی مشترکہ مشاورت", zh: "六席AI决策委员会协同研讨" },
      },
      {
        id: "nav-audit",
        label: "Audit trail",
        category: "PAGES",
        icon: "⌁",
        href: "/audit",
        keywords: ["audit", "log", "hash", "sha256", "chain", "آڈٹ", "لاگ", "ریکارڈ", "审计", "哈希链", "全量记录"],
        langHints: { en: "Immutable SHA-256 hash-chained log", ur: "ناقابلِ تغیر ہیش چین آڈٹ لاگ", zh: "不可篡改的SHA-256哈希审计链" },
      },
      {
        id: "nav-mandates",
        label: "Mandates & Limits",
        category: "PAGES",
        icon: "⚙",
        href: "/settings/mandates",
        keywords: ["mandates", "limits", "caps", "autonomy", "مینڈیٹ", "حدود", "اختیارات", "授权", "额度", "自主权"],
        langHints: { en: "Agent payment caps & allow-lists", ur: "ایجنٹ کی ادائیگی کی حدود اور اجازتیں", zh: "智能体单笔限额与白名单设置" },
      },

      // Actions
      {
        id: "act-switch-shenzhen",
        label: "Switch to Shenzhen Persona (China / CAS)",
        category: "ACTIONS",
        icon: "🇨🇳",
        action: () => {
          if (onSwitchTenant) onSwitchTenant("ten_shenzhen_electronics");
          else {
            try {
              window.localStorage.setItem("fiona:tenant", "ten_shenzhen_electronics");
              window.location.reload();
            } catch { /* session */ }
          }
        },
        keywords: ["shenzhen", "china", "cny", "cas", "fapiao", "uscc", "شینزین", "چین", "深圳", "中国", "人民币", "发票", "统一社会信用代码"],
        langHints: { en: "Switch active tenant to Shenzhen Electronics", ur: "شینزین الیکٹرانکس پر سوئچ کریں", zh: "切换工作区至深圳市微芯科技有限公司" },
      },
      {
        id: "act-switch-karachi",
        label: "Switch to Karachi Persona (Pakistan / IFRS)",
        category: "ACTIONS",
        icon: "🇵🇰",
        action: () => {
          if (onSwitchTenant) onSwitchTenant("ten_karachi_apparel");
          else {
            try {
              window.localStorage.setItem("fiona:tenant", "ten_karachi_apparel");
              window.location.reload();
            } catch { /* session */ }
          }
        },
        keywords: ["karachi", "pakistan", "pkr", "ifrs", "ntn", "کراچی", "پاکستان", "روپیہ", "卡拉奇", "巴基斯坦"],
        langHints: { en: "Switch active tenant to Karachi Apparel", ur: "کراچی اپیرل پر سوئچ کریں", zh: "切换工作区至卡拉奇服装公司" },
      },
      {
        id: "act-toggle-theme",
        label: `Switch Theme to ${currentTheme === "dark" ? "Light" : "Dark"} Mode`,
        category: "ACTIONS",
        icon: currentTheme === "dark" ? "☼" : "☾",
        action: () => {
          if (onToggleTheme) onToggleTheme();
        },
        keywords: ["theme", "dark", "light", "mode", "رنگ", "ڈارک موڈ", "روشنی", "主题", "暗黑模式", "明亮模式"],
        langHints: { en: "Toggle visual contrast theme", ur: "تھیم تبدیل کریں", zh: "切换系统深色/浅色外观" },
      },
    ],
    [onSwitchTenant, onToggleTheme, currentTheme],
  );

  const filteredCommands = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => {
      const matchLabel = c.label.toLowerCase().includes(q);
      const matchKeywords = c.keywords.some((k) => k.toLowerCase().includes(q));
      const matchHints =
        c.langHints?.en.toLowerCase().includes(q) ||
        c.langHints?.ur.toLowerCase().includes(q) ||
        c.langHints?.zh.toLowerCase().includes(q);
      return matchLabel || matchKeywords || matchHints;
    });
  }, [commands, query]);

  useEffect(() => {
    if (isOpen) {
      const timer = window.setTimeout(() => {
        setQuery("");
        setSelectedIndex(0);
        setVoiceError(null);
        inputRef.current?.focus();
      }, 50);
      return () => window.clearTimeout(timer);
    } else {
      const timer = window.setTimeout(() => {
        setIsListening(false);
      }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [isOpen]);

  function handleVoiceInput() {
    if (typeof window === "undefined") return;
    const win = window as unknown as {
      SpeechRecognition?: new () => BrowserSpeechRecognition;
      webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
    };
    const SpeechRecognition = win.SpeechRecognition || win.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setVoiceError("Speech recognition not supported in this browser. You can type in English, Urdu or Chinese.");
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = voiceLang;
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onstart = () => {
        setIsListening(true);
        setVoiceError(null);
      };

      recognition.onresult = (event: SpeechRecognitionResultEvent) => {
        const transcript = event.results[0]?.[0]?.transcript;
        if (transcript) {
          setQuery(transcript);
          setSelectedIndex(0);
        }
      };

      recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
        setIsListening(false);
        if (event.error !== "no-speech") {
          setVoiceError(`Voice input error (${event.error}). Please type.`);
        }
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
    } catch (e: unknown) {
      setIsListening(false);
      const msg = e instanceof Error ? e.message : String(e);
      setVoiceError(`Speech error: ${msg}`);
    }
  }

  function executeItem(item: CommandItem) {
    if (item.action) {
      item.action();
      onClose();
    } else if (item.href) {
      router.push(item.href);
      onClose();
    }
  }

  if (!isOpen) return null;

  return (
    <div
      className="overlay-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Fiona Command Bar"
        style={{ width: "min(100%, 580px)" }}
      >
        <div className="palette-search" style={{ position: "relative" }}>
          <span aria-hidden="true">⌕</span>
          <input
            ref={inputRef}
            placeholder="Type or speak a command in English, اردو, or 中文…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSelectedIndex((i) =>
                  filteredCommands.length ? (i + 1) % filteredCommands.length : 0
                );
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setSelectedIndex((i) =>
                  filteredCommands.length
                    ? (i + filteredCommands.length - 1) % filteredCommands.length
                    : 0
                );
              }
              if (e.key === "Enter") {
                const selected = filteredCommands[selectedIndex];
                if (selected) executeItem(selected);
              }
            }}
          />

          {/* Voice input button & language selector */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <select
              value={voiceLang}
              onChange={(e) => setVoiceLang(e.target.value as "en-US" | "ur-PK" | "zh-CN")}
              style={{
                fontSize: "10px",
                padding: "2px 4px",
                border: "1px solid var(--border)",
                borderRadius: "4px",
                background: "var(--surface)",
                color: "var(--text-muted)",
              }}
              aria-label="Voice language"
            >
              <option value="en-US">EN</option>
              <option value="ur-PK">اردو</option>
              <option value="zh-CN">中文</option>
            </select>
            <button
              type="button"
              onClick={handleVoiceInput}
              aria-label={isListening ? "Listening voice input" : "Speak command"}
              style={{
                background: isListening ? "var(--accent)" : "var(--surface)",
                color: isListening ? "#fff" : "var(--text)",
                border: "1px solid var(--border)",
                borderRadius: "5px",
                cursor: "pointer",
                padding: "3px 7px",
                fontSize: "12px",
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
              }}
            >
              🎤 {isListening && <span style={{ fontSize: "9px" }}>●</span>}
            </button>
            <kbd>ESC</kbd>
          </div>
        </div>

        {voiceError && (
          <div style={{ padding: "6px 14px", fontSize: "11px", color: "var(--accent)", background: "var(--accent-soft)" }}>
            {voiceError}
          </div>
        )}

        <div style={{ maxHeight: "360px", overflowY: "auto" }}>
          {filteredCommands.length === 0 ? (
            <p className="palette-empty" style={{ margin: "14px 0" }}>
              No matching commands or pages for &ldquo;{query}&rdquo;
            </p>
          ) : (
            filteredCommands.map((item, index) => {
              const isSelected = selectedIndex === index;
              return (
                <div
                  key={item.id}
                  className={`palette-item ${isSelected ? "palette-item-selected" : ""}`}
                  onMouseEnter={() => setSelectedIndex(index)}
                  onClick={() => executeItem(item)}
                  style={{
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 14px",
                    background: isSelected ? "var(--surface-soft)" : "transparent",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span className="nav-icon" style={{ fontSize: "14px" }}>
                      {item.icon}
                    </span>
                    <div>
                      <div style={{ fontWeight: isSelected ? 600 : 500 }}>{item.label}</div>
                      {item.langHints && (
                        <div style={{ fontSize: "10px", color: "var(--text-subtle)", marginTop: "2px" }}>
                          {item.langHints.en} · {item.langHints.ur} · {item.langHints.zh}
                        </div>
                      )}
                    </div>
                  </div>
                  <kbd>↵</kbd>
                </div>
              );
            })
          )}
        </div>

        <div className="palette-footer">
          <span>
            Navigate with <kbd>↑</kbd> <kbd>↓</kbd> · Run with <kbd>↵</kbd>
          </span>
          <span>
            Multi-lingual bar: <kbd>Ctrl</kbd>+<kbd>K</kbd> / <kbd>⌘</kbd>+<kbd>K</kbd>
          </span>
        </div>
      </section>
    </div>
  );
}
