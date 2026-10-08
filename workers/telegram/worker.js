/**
 * IPODevta - Telegram webhook + schedule trigger (Cloudflare Worker, free plan).
 *
 * - Webhook: Start, Check now, Settings, Channel, Help, Feedback (instant replies).
 * - Check now: filters the latest cards that GitHub Actions pushed to KV (POST /market).
 * - Cron: 9:30 IST dispatches the `channel` run, 14:30 IST dispatches the `bot` run.
 *
 * User-facing strings come from shared/copy.json (synced to ./copy.js).
 * KV binding: PREFS. Secrets: TELEGRAM_TOKEN, CHANNEL_ID, ADMIN_CHAT_ID,
 * WEBHOOK_SECRET, EXPORT_SECRET, GITHUB_TOKEN, GITHUB_REPO (owner/name).
 */

import COPY from "./copy.js";

const DEFAULTS = { board: "main", min_gmp_main: 34, min_gmp_sme: 48, min_total_sub: 1 };
const MAIN_PRESETS = [24, 30, 34, 40, 50];
const SME_PRESETS = [40, 45, 48, 55, 60];
const SUB_PRESETS = [1, 2, 5];
const MAX_CHECK_CARDS = 20;
const CRON_EVENTS = { "0 4 * * 1-5": "channel", "0 9 * * 1-5": "bot" };

// ---------------------------------------------------------------- copy

function t(path, vars) {
  let cur = COPY;
  for (const p of path.split(".")) {
    if (cur == null || typeof cur !== "object" || !(p in cur)) {
      throw new Error(`copy path not found: ${path}`);
    }
    cur = cur[p];
  }
  let text = String(cur);
  if (vars) {
    text = text.replace(/\{(\w+)\}/g, (m, key) => (vars[key] == null ? m : String(vars[key])));
  }
  return text;
}

const btn = (key) => t(`buttons.${key}`);

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function channelUrl(env) {
  if (env.CHANNEL_URL) return env.CHANNEL_URL.replace(/\/$/, "");
  const cid = (env.CHANNEL_ID || "@ipodevta").trim();
  return cid.startsWith("@") ? `https://t.me/${cid.slice(1)}` : "https://t.me/ipodevta";
}

function todayIst() {
  return new Date(Date.now() + 5.5 * 3600 * 1000).toISOString().slice(0, 10);
}

function dateLong(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getUTCDay()];
  const mo = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()];
  return `${wd} ${d.getUTCDate()} ${mo}`;
}

function time12h(hhmm) {
  const [h, m] = String(hhmm || "00:00").split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

// ---------------------------------------------------------------- filters
// Mirrors bot/filters.py; keep both in sync.

function num(v, fallback) {
  const n = Number(v);
  return v == null || v === "" || !Number.isFinite(n) ? fallback : n;
}

function normalizePrefs(p) {
  p = p || {};
  let board = String(p.board || "").toLowerCase();
  if (!["main", "sme", "both"].includes(board)) board = p.include_sme ? "both" : DEFAULTS.board;
  const legacy = p.min_gmp_pct;
  const smeLegacy = !("board" in p) && !("min_gmp_sme" in p) ? legacy : undefined;
  return {
    board,
    min_gmp_main: num(p.min_gmp_main ?? legacy, DEFAULTS.min_gmp_main),
    min_gmp_sme: num(p.min_gmp_sme ?? smeLegacy, DEFAULTS.min_gmp_sme),
    min_total_sub: num(p.min_total_sub, DEFAULTS.min_total_sub),
  };
}

function passesFilter(ipo, prefs) {
  const p = normalizePrefs(prefs);
  let bar;
  if (ipo.board === "SME") {
    if (p.board === "main") return false;
    bar = p.min_gmp_sme;
  } else if (ipo.board === "MAIN") {
    if (p.board === "sme") return false;
    bar = p.min_gmp_main;
  } else {
    return false;
  }
  if (ipo.gmp_pct == null || ipo.sub_total == null) return false;
  return Number(ipo.gmp_pct) >= bar && Number(ipo.sub_total) >= p.min_total_sub;
}

function parsePct(raw) {
  const n = Number(String(raw || "").trim().replace(/%$/, "").trim());
  return Number.isFinite(n) && n >= 0 && n <= 300 ? n : null;
}

const nearly = (a, b) => Math.abs(Number(a) - Number(b)) < 0.05;
const fmtNum = (n) => String(Number(n));

// ---------------------------------------------------------------- text

function prefsSummary(p) {
  const sub = t("labels.sub_line", { value: `${fmtNum(p.min_total_sub)}x` });
  if (p.board === "sme") {
    return [t("labels.board_sme_line"), t("labels.gmp_line", { value: `${fmtNum(p.min_gmp_sme)}%` }), sub].join("\n");
  }
  if (p.board === "both") {
    return [
      t("labels.board_both_line"),
      t("labels.main_gmp_line", { value: `${fmtNum(p.min_gmp_main)}%` }),
      t("labels.sme_gmp_line", { value: `${fmtNum(p.min_gmp_sme)}%` }),
      sub,
    ].join("\n");
  }
  return [t("labels.board_main_line"), t("labels.gmp_line", { value: `${fmtNum(p.min_gmp_main)}%` }), sub].join("\n");
}

function prefsBlock(p) {
  return `<b>${t("labels.your_filters")}</b>\n<code>${esc(prefsSummary(p))}</code>`;
}

function welcomeText(p, env) {
  const w = COPY.welcome;
  return [
    w.title,
    w.tagline,
    "",
    w.daily,
    w.none,
    "",
    t("welcome.channel", { channel: channelUrl(env) }),
    "",
    prefsBlock(p),
    "",
    w.buttons_hint,
  ].join("\n");
}

function helpText(env) {
  const h = COPY.help;
  return [
    h.title,
    "",
    h.daily,
    h.closing,
    h.none,
    h.check,
    h.settings,
    t("help.channel", { channel: channelUrl(env) }),
    "",
    `<blockquote expandable>${esc(t("disclaimer"))}</blockquote>`,
  ].join("\n");
}

function settingsText(p) {
  const s = COPY.settings;
  const hint = p.board === "sme" ? s.hint_sme : p.board === "both" ? s.hint_both : s.hint_main;
  return [s.title, "", prefsBlock(p), "", hint, s.tap_hint, s.filters_use].join("\n");
}

function gmpPrompt(which) {
  return [
    which === "sme" ? t("gmp_prompt.title_sme") : t("gmp_prompt.title_main"),
    "",
    t("gmp_prompt.body", { example: which === "sme" ? "48" : "34" }),
    t("gmp_prompt.cancel"),
  ].join("\n");
}

// ---------------------------------------------------------------- keyboards

function mainKeyboard() {
  return {
    keyboard: [
      [{ text: btn("check") }, { text: btn("settings") }],
      [{ text: btn("channel") }, { text: btn("help") }],
      [{ text: btn("feedback") }],
    ],
    resize_keyboard: true,
    is_persistent: true,
  };
}

function cardKeyboard(todayUrl) {
  return {
    inline_keyboard: [
      [
        { text: btn("today_ipos"), url: todayUrl },
        { text: btn("filters"), callback_data: "settings" },
      ],
    ],
  };
}

function settingsInline(p) {
  const mark = (on, label) => (on ? `✓ ${label}` : label);
  const pctRows = (current, presets, which, prefix) => {
    const custom = !presets.some((v) => nearly(current, v));
    const buttons = presets.map((v) => ({
      text: mark(nearly(current, v), `${prefix}${v}%`),
      callback_data: `gmp:${which}:${v}`,
    }));
    const typeLabel = prefix ? t("buttons.type_pct_prefixed", { prefix: prefix.trim() }) : btn("type_pct");
    buttons.push({
      text: mark(custom, custom ? `${prefix}${fmtNum(current)}%` : typeLabel),
      callback_data: `gmp:ask:${which}`,
    });
    const rows = [];
    for (let i = 0; i < buttons.length; i += 3) rows.push(buttons.slice(i, i + 3));
    return rows;
  };

  const both = p.board === "both";
  const rows = [];
  if (p.board !== "sme") rows.push(...pctRows(p.min_gmp_main, MAIN_PRESETS, "main", both ? "M " : ""));
  if (p.board !== "main") rows.push(...pctRows(p.min_gmp_sme, SME_PRESETS, "sme", both ? "S " : ""));
  rows.push(
    SUB_PRESETS.map((v) => ({
      text: mark(nearly(p.min_total_sub, v), t("buttons.sub_preset", { value: String(v) })),
      callback_data: `sub:${v}`,
    }))
  );
  rows.push([
    { text: mark(p.board === "main", btn("board_main")), callback_data: "board:main" },
    { text: mark(p.board === "sme", btn("board_sme")), callback_data: "board:sme" },
    { text: mark(both, btn("board_both")), callback_data: "board:both" },
  ]);
  rows.push([{ text: btn("check"), callback_data: "check" }]);
  return { inline_keyboard: rows };
}

// ---------------------------------------------------------------- telegram + KV

async function tg(env, method, body) {
  const resp = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}

function send(env, chatId, text, extra) {
  return tg(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
    ...extra,
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getPrefs(env, chatId) {
  const raw = await env.PREFS.get(`prefs:${chatId}`);
  if (raw) return normalizePrefs(JSON.parse(raw));
  const prefs = { ...DEFAULTS };
  await savePrefs(env, chatId, prefs);
  return prefs;
}

async function savePrefs(env, chatId, prefs) {
  const clean = { ...normalizePrefs(prefs), updated: new Date().toISOString() };
  await env.PREFS.put(`prefs:${chatId}`, JSON.stringify(clean));
  const idx = JSON.parse((await env.PREFS.get("users:index")) || "[]");
  if (!idx.includes(String(chatId))) {
    idx.push(String(chatId));
    await env.PREFS.put("users:index", JSON.stringify(idx));
  }
}

async function exportUsers(env) {
  const idx = JSON.parse((await env.PREFS.get("users:index")) || "[]");
  const users = {};
  for (const id of idx) {
    const raw = await env.PREFS.get(`prefs:${id}`);
    if (raw) users[id] = normalizePrefs(JSON.parse(raw));
  }
  return users;
}

// ---------------------------------------------------------------- screens

async function sendHome(env, chatId) {
  const prefs = await getPrefs(env, chatId);
  await send(env, chatId, welcomeText(prefs, env), { reply_markup: mainKeyboard() });
}

async function sendHelp(env, chatId) {
  await send(env, chatId, helpText(env), { reply_markup: mainKeyboard() });
}

async function sendChannel(env, chatId) {
  await send(env, chatId, t("welcome.channel", { channel: channelUrl(env) }), {
    reply_markup: { inline_keyboard: [[{ text: btn("join_channel"), url: channelUrl(env) }]] },
  });
}

async function sendSettings(env, chatId, editMessageId) {
  const prefs = await getPrefs(env, chatId);
  const body = { text: settingsText(prefs), reply_markup: settingsInline(prefs) };
  if (editMessageId) {
    const edited = await tg(env, "editMessageText", {
      chat_id: chatId,
      message_id: editMessageId,
      parse_mode: "HTML",
      ...body,
    });
    if (edited && edited.ok) return;
  }
  await send(env, chatId, body.text, { reply_markup: body.reply_markup });
}

async function sendCheck(env, chatId) {
  const raw = await env.PREFS.get("market:latest");
  if (!raw) {
    await send(env, chatId, t("check.no_data"), { reply_markup: mainKeyboard() });
    return;
  }
  const market = JSON.parse(raw);
  const prefs = await getPrefs(env, chatId);
  const keyboard = cardKeyboard(market.today_url || channelUrl(env));
  if (market.date !== todayIst()) {
    await send(env, chatId, t("check.stale", { date: dateLong(market.date), time: time12h(market.as_of) }), {
      disable_notification: true,
    });
  }
  const passing = (market.ipos || []).filter((ipo) => passesFilter(ipo, prefs)).slice(0, MAX_CHECK_CARDS);
  if (!passing.length) {
    await send(env, chatId, t("no_match"), { reply_markup: keyboard });
    return;
  }
  for (let i = 0; i < passing.length; i++) {
    if (i) await sleep(350);
    await send(env, chatId, passing[i].card, { reply_markup: keyboard, disable_notification: i > 0 });
  }
}

async function beginFeedback(env, chatId) {
  await env.PREFS.put(`feedback:await:${chatId}`, "1", { expirationTtl: 600 });
  const f = COPY.feedback;
  await send(env, chatId, [f.title, "", f.body, f.cancel].join("\n"), { reply_markup: mainKeyboard() });
}

// ---------------------------------------------------------------- inputs

function isMenuInput(raw) {
  const first = raw.split(/\s+/)[0].toLowerCase().split("@")[0].replace(/^\//, "");
  const labels = ["check", "settings", "help", "channel", "feedback"].map(btn);
  return labels.includes(raw) || raw.startsWith("/") || ["start", "menu", "help", "check", "settings", "channel", "feedback"].includes(first);
}

async function handleFeedbackMessage(env, chatId, raw) {
  if (!(await env.PREFS.get(`feedback:await:${chatId}`))) return false;
  if (isMenuInput(raw)) {
    await env.PREFS.delete(`feedback:await:${chatId}`);
    return false;
  }
  await env.PREFS.delete(`feedback:await:${chatId}`);
  if (raw.toLowerCase() === "cancel") {
    await send(env, chatId, t("feedback.cancelled"), { reply_markup: mainKeyboard() });
    return true;
  }
  if (env.ADMIN_CHAT_ID) {
    await send(env, env.ADMIN_CHAT_ID, `${t("labels.feedback_admin", { chat_id: esc(String(chatId)) })}\n\n${esc(raw)}`);
  }
  await send(env, chatId, t("feedback.thanks"), { reply_markup: mainKeyboard() });
  return true;
}

async function handleCustomGmp(env, chatId, raw) {
  const waiting = await env.PREFS.get(`gmp:await:${chatId}`);
  if (!waiting) return false;
  if (isMenuInput(raw)) {
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
    await send(env, chatId, `${gmpPrompt(which)}\n\n${t("gmp_prompt.retry")}`, { reply_markup: mainKeyboard() });
    return true;
  }
  const prefs = await getPrefs(env, chatId);
  prefs[which === "sme" ? "min_gmp_sme" : "min_gmp_main"] = val;
  await savePrefs(env, chatId, prefs);
  await env.PREFS.delete(`gmp:await:${chatId}`);
  await send(
    env,
    chatId,
    t("messages.saved_gmp", {
      label: which === "sme" ? t("labels.sme") : t("labels.mainboard"),
      value: String(val),
      prefs: prefsBlock(normalizePrefs(prefs)),
    }),
    { reply_markup: settingsInline(normalizePrefs(prefs)) }
  );
  return true;
}

async function handleText(env, chatId, text) {
  const raw = (text || "").trim();
  if (!raw) return;
  if (await handleCustomGmp(env, chatId, raw)) return;
  if (await handleFeedbackMessage(env, chatId, raw)) return;

  if (raw === btn("check")) return sendCheck(env, chatId);
  if (raw === btn("settings")) return sendSettings(env, chatId);
  if (raw === btn("channel")) return sendChannel(env, chatId);
  if (raw === btn("help")) return sendHelp(env, chatId);
  if (raw === btn("feedback")) return beginFeedback(env, chatId);

  const cmd = raw.split(/\s+/)[0].toLowerCase().split("@")[0].replace(/^\//, "");
  if (["start", "menu"].includes(cmd)) return sendHome(env, chatId);
  if (["check", "preview"].includes(cmd)) return sendCheck(env, chatId);
  if (["settings", "filters", "status"].includes(cmd)) return sendSettings(env, chatId);
  if (cmd === "channel") return sendChannel(env, chatId);
  if (cmd === "help") return sendHelp(env, chatId);
  if (cmd === "feedback") return beginFeedback(env, chatId);

  await send(env, chatId, t("messages.use_buttons"), { reply_markup: mainKeyboard() });
}

async function handleCallback(env, cb) {
  const chatId = cb.message?.chat?.id ?? cb.from?.id;
  const messageId = cb.message?.message_id;
  const data = String(cb.data || "").trim();
  if (chatId == null) return;
  const answer = (text) =>
    tg(env, "answerCallbackQuery", { callback_query_id: cb.id, ...(text ? { text } : {}) });

  if (data === "settings") {
    // Opened from an IPO card: send a new message so the card stays intact.
    await answer(t("toasts.settings"));
    return sendSettings(env, chatId);
  }
  if (data === "check") {
    await answer(t("toasts.check"));
    return sendCheck(env, chatId);
  }
  if (data === "help") {
    await answer(t("toasts.help"));
    return sendHelp(env, chatId);
  }
  if (["home", "menu", "start"].includes(data)) {
    await answer(t("toasts.home"));
    return sendHome(env, chatId);
  }
  if (data === "feedback") {
    await answer(t("toasts.feedback"));
    return beginFeedback(env, chatId);
  }

  const [kind, a, b] = data.split(":");
  if (kind === "gmp" && a === "ask" && (b === "main" || b === "sme")) {
    await env.PREFS.put(`gmp:await:${chatId}`, b, { expirationTtl: 600 });
    await answer(b === "sme" ? t("toasts.send_sme_pct") : t("toasts.send_main_pct"));
    return send(env, chatId, gmpPrompt(b), { reply_markup: mainKeyboard() });
  }
  if (kind === "gmp" && (a === "main" || a === "sme")) {
    const val = parsePct(b);
    if (val == null) return answer(t("toasts.invalid_gmp"));
    const prefs = await getPrefs(env, chatId);
    prefs[a === "sme" ? "min_gmp_sme" : "min_gmp_main"] = val;
    await savePrefs(env, chatId, prefs);
    await env.PREFS.delete(`gmp:await:${chatId}`);
    await answer(t("toasts.gmp_saved", { label: a === "sme" ? t("labels.sme") : t("labels.mainboard"), value: String(val) }));
    return sendSettings(env, chatId, messageId);
  }
  if (kind === "sub") {
    const val = Number(a);
    if (!SUB_PRESETS.includes(val)) return answer(t("toasts.unknown"));
    const prefs = await getPrefs(env, chatId);
    prefs.min_total_sub = val;
    await savePrefs(env, chatId, prefs);
    await answer(t("toasts.sub_saved", { value: String(val) }));
    return sendSettings(env, chatId, messageId);
  }
  if (kind === "board" && ["main", "sme", "both"].includes(a)) {
    const prefs = await getPrefs(env, chatId);
    prefs.board = a;
    await savePrefs(env, chatId, prefs);
    await env.PREFS.delete(`gmp:await:${chatId}`);
    await answer(t(`toasts.board_${a}`));
    return sendSettings(env, chatId, messageId);
  }
  return answer(t("toasts.unknown"));
}

// ---------------------------------------------------------------- schedule

async function dispatch(env, eventType) {
  if (!env.GITHUB_REPO || !env.GITHUB_TOKEN) return 0;
  const resp = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "content-type": "application/json",
      "user-agent": "ipodevta-worker",
    },
    body: JSON.stringify({ event_type: eventType, client_payload: { source: "worker-cron" } }),
  });
  return resp.status;
}

async function runCron(env, cron) {
  const event = CRON_EVENTS[cron];
  if (!event) return;
  const status = await dispatch(env, event);
  console.log("dispatch", event, status);
  if (status !== 204 && env.ADMIN_CHAT_ID) {
    await tg(env, "sendMessage", {
      chat_id: env.ADMIN_CHAT_ID,
      text: t("admin.dispatch_failed", { event, status: String(status) }),
    });
  }
}

// ---------------------------------------------------------------- entry

function authorized(request, env) {
  return Boolean(env.EXPORT_SECRET) && request.headers.get("authorization") === `Bearer ${env.EXPORT_SECRET}`;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") return new Response("ok");

    if (url.pathname === "/export/users" && request.method === "GET") {
      if (!authorized(request, env)) return new Response("unauthorized", { status: 401 });
      return Response.json(await exportUsers(env));
    }

    if (url.pathname === "/market" && request.method === "POST") {
      if (!authorized(request, env)) return new Response("unauthorized", { status: 401 });
      const body = await request.json();
      if (!body || !body.date || !Array.isArray(body.ipos)) {
        return new Response("date and ipos required", { status: 400 });
      }
      await env.PREFS.put("market:latest", JSON.stringify(body));
      return Response.json({ ok: true, ipos: body.ipos.length });
    }

    if (request.method !== "POST" || url.pathname !== "/telegram") {
      return new Response("not found", { status: 404 });
    }
    if (env.WEBHOOK_SECRET && request.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("bad json", { status: 400 });
    }

    const work = (async () => {
      try {
        if (update.callback_query) {
          await handleCallback(env, update.callback_query);
        } else if (update.message?.chat?.id != null) {
          await handleText(env, update.message.chat.id, update.message.text || "");
        }
      } catch (err) {
        console.error("handler error", err);
      }
    })();
    ctx.waitUntil(work);
    return new Response("ok");
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(runCron(env, event.cron));
  },
};
