/**
 * IPO Devta - instant Telegram webhook (Cloudflare Worker).
 *
 * Handles fixed replies immediately: Start, Help, Settings, Channel, filter taps.
 * Preview acknowledges instantly, then triggers GitHub Actions for the heavy fetch.
 *
 * User-facing strings come from shared/copy.json (synced to ./copy.js).
 *
 * Bindings / secrets:
 *   KV namespace binding: PREFS
 *   Secrets: TELEGRAM_TOKEN, CHANNEL_ID, GITHUB_TOKEN, GITHUB_REPO (owner/name)
 */

import COPY from "./copy.js";

const DEFAULTS = {
  board: "main",
  min_gmp_main: 34.0,
  min_gmp_sme: 48.0,
  min_gmp_pct: 34.0,
  min_total_sub: 1.0,
  include_sme: false,
};

const MAIN_PRESETS = [24, 30, 34, 40, 50];
const SME_PRESETS = [40, 45, 48, 55, 60];
const SUB_PRESETS = [1, 2, 5];

const PREVIEW_COOLDOWN_SEC = 60;
const PREVIEW_CACHE_TTL_SEC = 45 * 60;

function t(path, vars) {
  const parts = path.split(".");
  let cur = COPY;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object" || !(p in cur)) {
      throw new Error(`copy path not found: ${path}`);
    }
    cur = cur[p];
  }
  let text = String(cur);
  if (vars) {
    text = text.replace(/\{(\w+)\}/g, (_, key) =>
      vars[key] == null ? `{${key}}` : String(vars[key])
    );
  }
  return text;
}

function btn(key) {
  return t(`buttons.${key}`);
}

const BTN = {
  PREVIEW: btn("preview"),
  SETTINGS: btn("settings"),
  HELP: btn("help"),
  CHANNEL: btn("channel"),
  FEEDBACK: btn("feedback"),
};

function channelUrl(channelId) {
  const cid = (channelId || "@ipodevta").trim();
  if (cid.startsWith("@")) return `https://t.me/${cid.slice(1)}`;
  if (cid.startsWith("-")) return "https://t.me/ipodevta";
  return `https://t.me/${cid}`;
}

function boardMode(p) {
  const raw = String((p && p.board) || "").trim().toLowerCase();
  if (raw === "main" || raw === "sme" || raw === "both") return raw;
  if (p && p.include_sme) return "both";
  return "main";
}

function gmpMain(p) {
  if (p && p.min_gmp_main != null && p.min_gmp_main !== "") return Number(p.min_gmp_main);
  if (p && p.min_gmp_pct != null && p.min_gmp_pct !== "") return Number(p.min_gmp_pct);
  return DEFAULTS.min_gmp_main;
}

function gmpSme(p) {
  if (p && p.min_gmp_sme != null && p.min_gmp_sme !== "") return Number(p.min_gmp_sme);
  const legacy = p && !("min_gmp_sme" in p) && !("board" in p) && p.min_gmp_pct != null;
  if (legacy) return Number(p.min_gmp_pct);
  return DEFAULTS.min_gmp_sme;
}

function nearly(a, b) {
  return Math.abs(Number(a) - Number(b)) < 0.05;
}

function fmtNum(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return t("na");
  return Number.isInteger(v) ? String(v) : String(v);
}

function parsePct(raw) {
  const text = String(raw || "").trim().replace(/%$/, "").trim();
  const n = Number(text);
  if (!Number.isFinite(n) || n < 0 || n > 300) return null;
  return n;
}

function applyBoard(prefs, mode) {
  prefs.board = mode;
  prefs.include_sme = mode !== "main";
  return prefs;
}

function applyGmp(prefs, which, val) {
  if (which === "sme") prefs.min_gmp_sme = val;
  else {
    prefs.min_gmp_main = val;
    prefs.min_gmp_pct = val;
  }
  return prefs;
}

function prefsSummary(p) {
  const mode = boardMode(p);
  const sub = `${fmtNum(p.min_total_sub)}x`;
  if (mode === "sme") {
    return [
      t("labels.board_sme_line"),
      t("labels.gmp_line", { value: `${fmtNum(gmpSme(p))}%` }),
      t("labels.sub_line", { value: sub }),
    ].join("\n");
  }
  if (mode === "both") {
    return [
      t("labels.board_both_line"),
      t("labels.main_gmp_line", { value: `${fmtNum(gmpMain(p))}%` }),
      t("labels.sme_gmp_line", { value: `${fmtNum(gmpSme(p))}%` }),
      t("labels.sub_line", { value: sub }),
    ].join("\n");
  }
  return [
    t("labels.board_main_line"),
    t("labels.gmp_line", { value: `${fmtNum(gmpMain(p))}%` }),
    t("labels.sub_line", { value: sub }),
  ].join("\n");
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function prefsBlock(p) {
  return `<b>${t("labels.your_filters")}</b>\n<code>${esc(prefsSummary(p))}</code>`;
}

function welcomeText(p, channelId) {
  const channel = channelUrl(channelId);
  const w = COPY.welcome;
  return [
    w.title,
    w.tagline,
    "",
    w.lead,
    w.bullet_verdict,
    w.bullet_numbers,
    w.bullet_filters,
    "",
    prefsBlock(p),
    "",
    t("rule"),
    "",
    w.buttons_hint,
    "",
    t("welcome.channel_invite", { channel }),
    "",
    w.feedback_hint,
    "",
    w.closing,
  ].join("\n");
}

function helpText(channelId) {
  const channel = channelUrl(channelId);
  const h = COPY.help;
  return [
    h.title,
    h.sections,
    h.check,
    h.hidden,
    h.actions,
    h.feedback,
    t("help.open_channel", { channel }),
    `<blockquote expandable>${t("disclaimer.long")}</blockquote>`,
  ].join("\n");
}

function settingsText(p) {
  const mode = boardMode(p);
  const s = COPY.settings;
  const hint =
    mode === "sme" ? s.hint_sme : mode === "both" ? s.hint_both : s.hint_main;
  return [
    s.title,
    "",
    prefsBlock(p),
    "",
    hint,
    s.tap_hint,
    s.filters_use,
    s.channel_note,
  ].join("\n");
}

function gmpPrompt(which) {
  const sme = which === "sme";
  return [
    sme ? t("gmp_prompt.title_sme") : t("gmp_prompt.title_main"),
    "",
    t("gmp_prompt.body", { example: sme ? "48" : "34" }),
    t("gmp_prompt.cancel"),
  ].join("\n");
}

function channelText(channelId) {
  const url = channelUrl(channelId);
  const handle = url.replace("https://t.me/", "@");
  const c = COPY.channel_invite;
  return [
    c.title,
    "",
    c.no_filters,
    "",
    c.body,
    "",
    t("rule"),
    "",
    t("channel_invite.join", { channel: url, handle }),
    "",
    c.closing,
  ].join("\n");
}

function feedbackPrompt() {
  const f = COPY.feedback;
  return [f.title, "", f.body, f.forward, "", f.cancel].join("\n");
}

function mainKeyboard() {
  return {
    keyboard: [
      [{ text: BTN.PREVIEW }, { text: BTN.SETTINGS }],
      [{ text: BTN.HELP }, { text: BTN.CHANNEL }],
      [{ text: BTN.FEEDBACK }],
    ],
    resize_keyboard: true,
    is_persistent: true,
  };
}

function homeInline(channelId) {
  return {
    inline_keyboard: [
      [
        { text: BTN.PREVIEW, callback_data: "preview" },
        { text: BTN.SETTINGS, callback_data: "settings" },
      ],
      [
        { text: BTN.HELP, callback_data: "help" },
        { text: btn("join_channel"), url: channelUrl(channelId) },
      ],
      [{ text: BTN.FEEDBACK, callback_data: "feedback" }],
    ],
  };
}

function settingsInline(p) {
  const mode = boardMode(p);
  const sub = Number(p.min_total_sub);
  const mark = (on, label) => (on ? `✓ ${label}` : label);
  const pctRows = (current, presets, which, prefix) => {
    const buttons = presets.map((value) => ({
      text: mark(nearly(current, value), `${prefix}${value}%`),
      callback_data: `gmp:${which}:${value}`,
    }));
    const custom = !presets.some((value) => nearly(current, value));
    const typeLabel = prefix
      ? t("buttons.type_pct_prefixed", { prefix: prefix.trim() })
      : btn("type_pct");
    buttons.push({
      text: mark(custom, custom ? `${prefix}${fmtNum(current)}%` : typeLabel),
      callback_data: `gmp:ask:${which}`,
    });
    const rows = [];
    for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
    return rows;
  };
  const rows = [];
  const prefixMain = mode === "both" ? "M " : "";
  const prefixSme = mode === "both" ? "S " : "";
  if (mode === "main" || mode === "both") {
    rows.push(...pctRows(gmpMain(p), MAIN_PRESETS, "main", prefixMain));
  }
  if (mode === "sme" || mode === "both") {
    rows.push(...pctRows(gmpSme(p), SME_PRESETS, "sme", prefixSme));
  }
  rows.push(
    SUB_PRESETS.map((value) => ({
      text: mark(nearly(sub, value), t("buttons.sub_preset", { value: String(value) })),
      callback_data: `sub:${value}`,
    }))
  );
  rows.push([
    { text: mark(mode === "main", btn("board_main")), callback_data: "board:main" },
    { text: mark(mode === "sme", btn("board_sme")), callback_data: "board:sme" },
    { text: mark(mode === "both", btn("board_both")), callback_data: "board:both" },
  ]);
  rows.push([
    { text: BTN.PREVIEW, callback_data: "preview" },
    { text: btn("home"), callback_data: "home" },
  ]);
  return { inline_keyboard: rows };
}

async function tg(env, method, body) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${method}`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}

let profileSynced = false;

async function ensureBotProfile(env) {
  if (profileSynced) return;
  const c = COPY.commands;
  const commands = [
    { command: "start", description: c.start },
    { command: "preview", description: c.preview },
    { command: "settings", description: c.settings },
    { command: "help", description: c.help },
    { command: "feedback", description: c.feedback },
  ];
  await tg(env, "setMyCommands", { commands });
  await tg(env, "setMyShortDescription", {
    short_description: t("bot.short_description").slice(0, 120),
  });
  await tg(env, "setMyDescription", {
    description: t("bot.description").slice(0, 512),
  });
  try {
    await tg(env, "setMyName", { name: t("bot.name") });
  } catch (_) {
    // older bots may not support rename via API
  }
  profileSynced = true;
}

async function beginFeedback(env, chatId) {
  await env.PREFS.put(`feedback:await:${chatId}`, "1", { expirationTtl: 600 });
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: feedbackPrompt(),
    parse_mode: "HTML",
    reply_markup: mainKeyboard(),
  });
}

async function handleFeedbackMessage(env, chatId, text) {
  const awaiting = await env.PREFS.get(`feedback:await:${chatId}`);
  if (!awaiting) return false;

  const raw = (text || "").trim();
  if (!raw) return true;

  if (raw.toLowerCase() === "cancel") {
    await env.PREFS.delete(`feedback:await:${chatId}`);
    await tg(env, "sendMessage", {
      chat_id: chatId,
      text: t("feedback.cancelled"),
      reply_markup: mainKeyboard(),
    });
    return true;
  }

  await env.PREFS.delete(`feedback:await:${chatId}`);
  const admin = (env.ADMIN_CHAT_ID || "").trim();
  if (admin) {
    await tg(env, "sendMessage", {
      chat_id: admin,
      text:
        t("labels.feedback_admin", { chat_id: esc(String(chatId)) }) +
        `\n${t("rule")}\n` +
        esc(raw),
      parse_mode: "HTML",
    });
  }
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: t("feedback.thanks"),
    reply_markup: homeInline(env.CHANNEL_ID),
    parse_mode: "HTML",
  });
  return true;
}

async function getPrefs(env, chatId) {
  const key = `prefs:${chatId}`;
  const raw = await env.PREFS.get(key);
  if (!raw) {
    const prefs = { ...DEFAULTS, updated: new Date().toISOString() };
    await savePrefs(env, chatId, prefs);
    return prefs;
  }
  return JSON.parse(raw);
}

async function savePrefs(env, chatId, prefs) {
  prefs.updated = new Date().toISOString();
  await env.PREFS.put(`prefs:${chatId}`, JSON.stringify(prefs));
  const idxRaw = await env.PREFS.get("users:index");
  const idx = idxRaw ? JSON.parse(idxRaw) : [];
  const id = String(chatId);
  if (!idx.includes(id)) {
    idx.push(id);
    await env.PREFS.put("users:index", JSON.stringify(idx));
  }
}

async function githubDispatch(env, eventType, payload) {
  const repo = env.GITHUB_REPO;
  const token = env.GITHUB_TOKEN;
  if (!repo || !token) return false;
  const resp = await fetch(`https://api.github.com/repos/${repo}/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      accept: "application/vnd.github+json",
      "content-type": "application/json",
      "user-agent": "ipo-devta-worker",
    },
    body: JSON.stringify({
      event_type: eventType,
      client_payload: payload || {},
    }),
  });
  return resp.status === 204;
}

async function triggerPreview(env, chatId) {
  return githubDispatch(env, "preview", { chat_id: String(chatId) });
}

async function triggerAlert(env) {
  return githubDispatch(env, "alert", { source: "worker-cron" });
}

async function sendHome(env, chatId) {
  const prefs = await getPrefs(env, chatId);
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: welcomeText(prefs, env.CHANNEL_ID),
    parse_mode: "HTML",
    disable_web_page_preview: true,
    reply_markup: mainKeyboard(),
  });
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: t("labels.quick_actions_html"),
    parse_mode: "HTML",
    reply_markup: homeInline(env.CHANNEL_ID),
  });
}

async function sendHelp(env, chatId) {
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: helpText(env.CHANNEL_ID),
    parse_mode: "HTML",
    disable_web_page_preview: true,
    reply_markup: homeInline(env.CHANNEL_ID),
  });
}

async function sendSettings(env, chatId, messageId) {
  const prefs = await getPrefs(env, chatId);
  const body = {
    chat_id: chatId,
    text: settingsText(prefs),
    parse_mode: "HTML",
    disable_web_page_preview: true,
    reply_markup: settingsInline(prefs),
  };
  if (messageId) {
    body.message_id = messageId;
    const edited = await tg(env, "editMessageText", body);
    if (edited && edited.ok) return;
  }
  await tg(env, "sendMessage", body);
}

async function sendChannel(env, chatId) {
  const url = channelUrl(env.CHANNEL_ID);
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: channelText(env.CHANNEL_ID),
    parse_mode: "HTML",
    disable_web_page_preview: true,
    reply_markup: {
      inline_keyboard: [[{ text: btn("join_channel"), url }]],
    },
  });
}

function prefsFingerprint(p) {
  return {
    board: boardMode(p),
    min_gmp_main: gmpMain(p),
    min_gmp_sme: gmpSme(p),
    min_total_sub: Number(p.min_total_sub),
  };
}

function prefsEqual(a, b) {
  if (!a || !b) return false;
  return (
    a.board === b.board &&
    Number(a.min_gmp_main) === Number(b.min_gmp_main) &&
    Number(a.min_gmp_sme) === Number(b.min_gmp_sme) &&
    Number(a.min_total_sub) === Number(b.min_total_sub)
  );
}

async function getPreviewCache(env, chatId) {
  const raw = await env.PREFS.get(`preview:msg:${chatId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function savePreviewCache(env, chatId, payload) {
  await env.PREFS.put(`preview:msg:${chatId}`, JSON.stringify(payload), {
    expirationTtl: PREVIEW_CACHE_TTL_SEC,
  });
}

async function clearPreviewCache(env, chatId) {
  await env.PREFS.delete(`preview:msg:${chatId}`);
}

async function previewLocked(env, chatId) {
  const key = `cooldown:preview:${chatId}`;
  return Boolean(await env.PREFS.get(key));
}

async function lockPreview(env, chatId) {
  const key = `cooldown:preview:${chatId}`;
  await env.PREFS.put(key, String(Date.now()), {
    expirationTtl: PREVIEW_COOLDOWN_SEC,
  });
}

async function sendCachedPreview(env, chatId, cached) {
  const ageMin = Math.max(
    1,
    Math.round((Date.now() - Number(cached.ts || Date.now())) / 60000)
  );
  const header =
    `${t("preview.saved_title")}\n` +
    `${t("preview.saved_age", { age: String(ageMin) })}\n` +
    `${t("rule")}\n\n`;
  let body = cached.text || "";
  const text = header + body;
  const finalText =
    text.length > 4000
      ? text.slice(0, 3900) + "\n\n" + t("messages.truncated")
      : text;
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: finalText,
    parse_mode: "HTML",
    disable_web_page_preview: true,
    reply_markup: homeInline(env.CHANNEL_ID),
  });
}

async function sendPreviewAck(env, chatId, callbackQueryId) {
  const prefs = await getPrefs(env, chatId);
  const fp = prefsFingerprint(prefs);
  const cached = await getPreviewCache(env, chatId);

  if (cached && prefsEqual(cached.prefs, fp) && cached.text) {
    if (callbackQueryId) {
      await tg(env, "answerCallbackQuery", {
        callback_query_id: callbackQueryId,
        text: t("preview.toast_saved"),
      });
    }
    await sendCachedPreview(env, chatId, cached);
    return;
  }

  if (await previewLocked(env, chatId)) {
    const waitMsg =
      t("preview.in_progress_title") + "\n\n" + t("preview.in_progress_body");
    if (callbackQueryId) {
      await tg(env, "answerCallbackQuery", {
        callback_query_id: callbackQueryId,
        text: t("preview.toast_wait"),
        show_alert: true,
      });
    }
    await tg(env, "sendMessage", {
      chat_id: chatId,
      text: waitMsg,
      parse_mode: "HTML",
      reply_markup: homeInline(env.CHANNEL_ID),
    });
    return;
  }

  await lockPreview(env, chatId);
  const ok = await triggerPreview(env, chatId);
  if (callbackQueryId) {
    await tg(env, "answerCallbackQuery", {
      callback_query_id: callbackQueryId,
      text: ok ? t("preview.toast_fetching") : t("preview.toast_unavailable"),
    });
  }
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: ok
      ? [
          t("preview.fetching_title"),
          "",
          t("preview.fetching_body"),
          "",
          t("rule"),
          "",
          t("preview.fetching_eta"),
          t("preview.fetching_hint"),
        ].join("\n")
      : [
          t("preview.fetching_title"),
          "",
          t("preview.unavailable_body"),
        ].join("\n"),
    parse_mode: "HTML",
    reply_markup: homeInline(env.CHANNEL_ID),
  });
}

async function handleCustomGmp(env, chatId, raw) {
  const waiting = await env.PREFS.get(`gmp:await:${chatId}`);
  if (!waiting) return false;
  const first = raw.split(/\s+/)[0].toLowerCase().split("@")[0];
  const menu =
    Object.values(BTN).includes(raw) ||
    raw.startsWith("/") ||
    ["start", "menu", "help", "preview", "settings", "status", "channel", "feedback"].includes(first);
  if (menu) {
    await env.PREFS.delete(`gmp:await:${chatId}`);
    return false;
  }
  const which = waiting === "sme" ? "sme" : "main";
  if (raw.toLowerCase() === "cancel") {
    await env.PREFS.delete(`gmp:await:${chatId}`);
    await sendSettings(env, chatId);
    return true;
  }
  const val = parsePct(raw);
  if (val == null) {
    await tg(env, "sendMessage", {
      chat_id: chatId,
      text: `${gmpPrompt(which)}\n\n${t("gmp_prompt.retry")}`,
      parse_mode: "HTML",
      reply_markup: mainKeyboard(),
    });
    return true;
  }
  const prefs = await getPrefs(env, chatId);
  applyGmp(prefs, which, val);
  await savePrefs(env, chatId, prefs);
  await env.PREFS.delete(`gmp:await:${chatId}`);
  await clearPreviewCache(env, chatId);
  const label = which === "sme" ? t("labels.sme") : t("labels.mainboard");
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: t("messages.saved_gmp", {
      label,
      value: String(val),
      prefs: prefsBlock(prefs),
    }),
    parse_mode: "HTML",
    disable_web_page_preview: true,
    reply_markup: settingsInline(prefs),
  });
  return true;
}

async function handleText(env, chatId, text) {
  const raw = (text || "").trim();
  if (!raw) return;

  if (await handleCustomGmp(env, chatId, raw)) return;
  if (await handleFeedbackMessage(env, chatId, raw)) return;

  if (raw === BTN.PREVIEW) return sendPreviewAck(env, chatId);
  if (raw === BTN.SETTINGS) return sendSettings(env, chatId);
  if (raw === BTN.HELP) return sendHelp(env, chatId);
  if (raw === BTN.CHANNEL) return sendChannel(env, chatId);
  if (raw === BTN.FEEDBACK) return beginFeedback(env, chatId);

  const cmd = raw.split(/\s+/)[0].toLowerCase().split("@")[0];
  if (["/start", "/menu", "start", "menu"].includes(cmd)) return sendHome(env, chatId);
  if (["/help", "help"].includes(cmd)) return sendHelp(env, chatId);
  if (["/settings", "/status", "settings", "status"].includes(cmd))
    return sendSettings(env, chatId);
  if (["/preview", "preview"].includes(cmd)) return sendPreviewAck(env, chatId);
  if (["/channel", "channel"].includes(cmd)) return sendChannel(env, chatId);
  if (["/feedback", "feedback"].includes(cmd)) return beginFeedback(env, chatId);

  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: t("messages.use_buttons_worker"),
    reply_markup: mainKeyboard(),
  });
}

async function handleCallback(env, cb) {
  const chatId = cb.message?.chat?.id || cb.from?.id;
  const messageId = cb.message?.message_id;
  const data = (cb.data || "").trim();
  if (!chatId) return;

  const answer = async (text, showAlert = false) =>
    tg(env, "answerCallbackQuery", {
      callback_query_id: cb.id,
      text: text || undefined,
      show_alert: showAlert,
    });

  if (["home", "menu", "start"].includes(data)) {
    await answer(t("toasts.home"));
    return sendHome(env, chatId);
  }
  if (data === "help") {
    await answer(t("toasts.help"));
    return sendHelp(env, chatId);
  }
  if (data === "settings") {
    await answer(t("toasts.settings"));
    return sendSettings(env, chatId, messageId);
  }
  if (data === "channel") {
    await answer();
    return sendChannel(env, chatId);
  }
  if (data === "preview") {
    return sendPreviewAck(env, chatId, cb.id);
  }
  if (data === "feedback") {
    await answer(t("toasts.feedback"));
    return beginFeedback(env, chatId);
  }

  if (data.startsWith("gmp:")) {
    const parts = data.split(":");
    if (parts.length === 3 && parts[1] === "ask" && (parts[2] === "main" || parts[2] === "sme")) {
      const which = parts[2];
      await env.PREFS.put(`gmp:await:${chatId}`, which, { expirationTtl: 600 });
      await answer(which === "sme" ? t("toasts.send_sme_pct") : t("toasts.send_main_pct"));
      await tg(env, "sendMessage", {
        chat_id: chatId,
        text: gmpPrompt(which),
        parse_mode: "HTML",
        reply_markup: mainKeyboard(),
      });
      return;
    }
    let which = "main";
    if (parts.length === 3 && (parts[1] === "main" || parts[1] === "sme")) which = parts[1];
    const val = parsePct(parts[parts.length - 1]);
    if (val == null) {
      await answer(t("toasts.invalid_gmp"));
      return;
    }
    const prefs = await getPrefs(env, chatId);
    applyGmp(prefs, which, val);
    await savePrefs(env, chatId, prefs);
    await env.PREFS.delete(`gmp:await:${chatId}`);
    await clearPreviewCache(env, chatId);
    const label = which === "sme" ? t("labels.sme") : t("labels.mainboard");
    await answer(t("toasts.gmp_saved", { label, value: String(val) }));
    return sendSettings(env, chatId, messageId);
  }
  if (data.startsWith("sub:")) {
    const val = Number(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.min_total_sub = val;
    await savePrefs(env, chatId, prefs);
    await clearPreviewCache(env, chatId);
    await answer(t("toasts.sub_saved", { value: String(val) }));
    return sendSettings(env, chatId, messageId);
  }
  if (data.startsWith("board:")) {
    const token = data.split(":")[1];
    const mode = { all: "both", both: "both", sme: "sme", main: "main" }[token] || "main";
    const prefs = await getPrefs(env, chatId);
    applyBoard(prefs, mode);
    await savePrefs(env, chatId, prefs);
    await env.PREFS.delete(`gmp:await:${chatId}`);
    await clearPreviewCache(env, chatId);
    const toast = {
      main: t("toasts.board_main"),
      sme: t("toasts.board_sme"),
      both: t("toasts.board_both"),
    }[mode];
    await answer(toast);
    return sendSettings(env, chatId, messageId);
  }

  await answer(t("toasts.unknown"));
}

/** Export all prefs for Actions (Authorization: Bearer EXPORT_SECRET). */
async function exportUsers(env) {
  const idxRaw = await env.PREFS.get("users:index");
  const idx = idxRaw ? JSON.parse(idxRaw) : [];
  const users = {};
  for (const id of idx) {
    const raw = await env.PREFS.get(`prefs:${id}`);
    if (raw) users[id] = JSON.parse(raw);
  }
  return users;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return new Response("ok");
    }

    if (request.method === "GET" && url.pathname === "/export/users") {
      const auth = request.headers.get("authorization") || "";
      const expected = `Bearer ${env.EXPORT_SECRET || ""}`;
      if (!env.EXPORT_SECRET || auth !== expected) {
        return new Response("unauthorized", { status: 401 });
      }
      const users = await exportUsers(env);
      return Response.json(users);
    }

    if (request.method === "POST" && url.pathname === "/seed") {
      const auth = request.headers.get("authorization") || "";
      const expected = `Bearer ${env.EXPORT_SECRET || ""}`;
      if (!env.EXPORT_SECRET || auth !== expected) {
        return new Response("unauthorized", { status: 401 });
      }
      const body = await request.json();
      const idx = [];
      for (const [id, prefs] of Object.entries(body || {})) {
        await env.PREFS.put(`prefs:${id}`, JSON.stringify({ ...DEFAULTS, ...prefs }));
        idx.push(String(id));
      }
      await env.PREFS.put("users:index", JSON.stringify(idx));
      return Response.json({ ok: true, users: idx.length });
    }

    if (request.method === "POST" && url.pathname === "/cache/preview") {
      const auth = request.headers.get("authorization") || "";
      const expected = `Bearer ${env.EXPORT_SECRET || ""}`;
      if (!env.EXPORT_SECRET || auth !== expected) {
        return new Response("unauthorized", { status: 401 });
      }
      const body = await request.json();
      const chatId = String(body.chat_id || "");
      const text = body.text || "";
      if (!chatId || !text) {
        return new Response("chat_id and text required", { status: 400 });
      }
      await savePreviewCache(env, chatId, {
        text,
        prefs: body.prefs || {},
        source: body.source || "",
        saved_at: body.saved_at || new Date().toISOString(),
        ts: Date.now(),
      });
      return Response.json({ ok: true });
    }

    if (request.method !== "POST" || url.pathname !== "/telegram") {
      return new Response("not found", { status: 404 });
    }

    // Optional shared secret from Telegram secret_token
    const secret = request.headers.get("x-telegram-bot-api-secret-token");
    if (env.WEBHOOK_SECRET && secret !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("bad json", { status: 400 });
    }

    try {
      await ensureBotProfile(env);
      if (update.callback_query) {
        await handleCallback(env, update.callback_query);
      } else {
        const msg = update.message || update.edited_message;
        if (msg?.chat?.id != null) {
          await handleText(env, msg.chat.id, msg.text || "");
        }
      }
    } catch (err) {
      console.error("handler error", err);
    }

    return new Response("ok");
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(
      triggerAlert(env).then((ok) => {
        console.log("alert dispatch", ok ? "ok" : "failed");
      })
    );
  },
};
