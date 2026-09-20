/**
 * IPO Devta - instant Telegram webhook (Cloudflare Worker).
 *
 * Handles fixed replies immediately: Start, Help, Settings, Channel, filter taps.
 * Preview GMP acknowledges instantly, then triggers GitHub Actions for the heavy fetch.
 *
 * Bindings / secrets:
 *   KV namespace binding: PREFS
 *   Secrets: TELEGRAM_TOKEN, CHANNEL_ID, GITHUB_TOKEN, GITHUB_REPO (owner/name)
 */

const DEFAULTS = {
  min_gmp_pct: 24.0,
  min_total_sub: 1.0,
  include_sme: false,
};

const PREVIEW_COOLDOWN_SEC = 60;
const PREVIEW_CACHE_TTL_SEC = 45 * 60; // serve saved preview for 45 minutes
const RULE = "────────────";

const BTN = {
  PREVIEW: "Preview GMP",
  SETTINGS: "Settings",
  HELP: "Help",
  CHANNEL: "Channel",
  FEEDBACK: "Feedback",
};

const SHORT_DESCRIPTION =
  "IPO fills without the clutter. Clear 👍 / 👎 with GMP and subscription.";

const BOT_DESCRIPTION =
  "IPODevta removes the clutter from IPO fill decisions.\n\n" +
  "You get a simple 👍 or 👎 with GMP and subscription numbers, using filters you set.\n\n" +
  "Tap Feedback anytime to send a note to the team.\n\n" +
  "Information only - not investment advice. Read the RHP.";

function channelUrl(channelId) {
  const cid = (channelId || "@ipodevta").trim();
  if (cid.startsWith("@")) return `https://t.me/${cid.slice(1)}`;
  if (cid.startsWith("-")) return "https://t.me/ipodevta";
  return `https://t.me/${cid}`;
}

function prefsSummary(p) {
  const board = p.include_sme ? "MAIN + SME" : "MAIN only";
  return `GMP min     ${p.min_gmp_pct}%\nSub min     ${p.min_total_sub}x\nBoard       ${board}`;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function prefsBlock(p) {
  return `<b>Your filters</b>\n<code>${esc(prefsSummary(p))}</code>`;
}

function welcomeText(p, channelId) {
  const channel = channelUrl(channelId);
  return [
    "<b>IPODevta</b>",
    "<i>IPO fills without the clutter.</i>",
    "",
    "On closing days you get:",
    "• A clear 👍 or 👎 for each issue",
    "• GMP and subscription in one place",
    "• Filters you control",
    "",
    prefsBlock(p),
    "",
    RULE,
    "",
    "Use the buttons below. No typing needed.",
    "",
    `Prefer a shared list? <a href="${channel}">Join the channel</a>`,
    "",
    "Something off? Tap <b>Feedback</b>.",
    "",
    "<i>No selling. No promotions.</i>",
  ].join("\n");
}

function helpText(channelId) {
  const channel = channelUrl(channelId);
  return [
    "<b>What you get</b>",
    "",
    "<b>Preview GMP</b>",
    "Recent issues with your filters applied.",
    "",
    "<b>Settings</b>",
    "Your GMP %, subscription floor, and board.",
    "",
    "<b>Channel</b>",
    "Shared closing-day list without personal filters.",
    "",
    "<b>Feedback</b>",
    "Send a short note to the team.",
    "",
    RULE,
    "",
    `<a href="${channel}">Open channel</a>`,
    "",
    "<i>Grey-market premium is unofficial and can move quickly.\nInformation only - not investment advice. Read the RHP.</i>",
  ].join("\n");
}

function settingsText(p) {
  return [
    "<b>Settings</b>",
    "",
    prefsBlock(p),
    "",
    "Tap a value below to change it.",
    "Your next Preview and closing-day notes use the new values.",
  ].join("\n");
}

function channelText(channelId) {
  const url = channelUrl(channelId);
  return [
    "<b>Public channel</b>",
    "",
    "Shared closing-day list.",
    "No personal filters.",
    "",
    RULE,
    "",
    `<a href="${url}">Join ${url.replace("https://t.me/", "@")}</a>`,
  ].join("\n");
}

function feedbackPrompt() {
  return [
    "<b>Feedback</b>",
    "",
    "Send your note in one message.",
    "We will forward it to the team.",
    "",
    "Type <code>cancel</code> to stop.",
  ].join("\n");
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
        { text: "Preview GMP", callback_data: "preview" },
        { text: "Settings", callback_data: "settings" },
      ],
      [
        { text: "Help", callback_data: "help" },
        { text: "Join channel", url: channelUrl(channelId) },
      ],
      [{ text: "Feedback", callback_data: "feedback" }],
    ],
  };
}

function settingsInline(p) {
  const gmp = Number(p.min_gmp_pct);
  const sub = Number(p.min_total_sub);
  const sme = !!p.include_sme;
  const mark = (on, label) => (on ? `✓ ${label}` : label);
  return {
    inline_keyboard: [
      [
        { text: mark(gmp === 20, "GMP 20%"), callback_data: "gmp:20" },
        { text: mark(gmp === 24, "GMP 24%"), callback_data: "gmp:24" },
        { text: mark(gmp === 30, "GMP 30%"), callback_data: "gmp:30" },
      ],
      [
        { text: mark(gmp === 40, "GMP 40%"), callback_data: "gmp:40" },
        { text: mark(gmp === 50, "GMP 50%"), callback_data: "gmp:50" },
      ],
      [
        { text: mark(sub === 1, "Sub 1x"), callback_data: "sub:1" },
        { text: mark(sub === 2, "Sub 2x"), callback_data: "sub:2" },
        { text: mark(sub === 5, "Sub 5x"), callback_data: "sub:5" },
      ],
      [
        { text: mark(!sme, "MAIN only"), callback_data: "board:main" },
        { text: mark(sme, "MAIN + SME"), callback_data: "board:all" },
      ],
      [
        { text: "Preview GMP", callback_data: "preview" },
        { text: "Home", callback_data: "home" },
      ],
    ],
  };
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
  const commands = [
    { command: "start", description: "Open IPODevta" },
    { command: "preview", description: "See issues with your filters" },
    { command: "settings", description: "Set GMP, subscription, board" },
    { command: "help", description: "What you get" },
    { command: "feedback", description: "Send a note to the team" },
  ];
  await tg(env, "setMyCommands", { commands });
  await tg(env, "setMyShortDescription", {
    short_description: SHORT_DESCRIPTION.slice(0, 120),
  });
  await tg(env, "setMyDescription", {
    description: BOT_DESCRIPTION.slice(0, 512),
  });
  try {
    await tg(env, "setMyName", { name: "IPODevta" });
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
      text: "Feedback cancelled.",
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
        `<b>Feedback</b> from <code>${esc(String(chatId))}</code>\n` +
        `${RULE}\n` +
        esc(raw),
      parse_mode: "HTML",
    });
  }
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: "Thanks. Your note was sent to the team.",
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

async function triggerPreview(env, chatId) {
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
      event_type: "preview",
      client_payload: { chat_id: String(chatId) },
    }),
  });
  return resp.status === 204;
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
    text: "<b>Quick actions</b>",
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
      inline_keyboard: [[{ text: "Join channel", url }]],
    },
  });
}

function prefsFingerprint(p) {
  return {
    min_gmp_pct: Number(p.min_gmp_pct),
    min_total_sub: Number(p.min_total_sub),
    include_sme: !!p.include_sme,
  };
}

function prefsEqual(a, b) {
  if (!a || !b) return false;
  return (
    Number(a.min_gmp_pct) === Number(b.min_gmp_pct) &&
    Number(a.min_total_sub) === Number(b.min_total_sub) &&
    !!a.include_sme === !!b.include_sme
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
    `<b>Saved preview</b>\n` +
    `<i>Retrieved from cache · about ${ageMin} min old</i>\n` +
    `${RULE}\n\n`;
  let body = cached.text || "";
  // Avoid duplicating if already a full message
  const text = header + body;
  const finalText = text.length > 4000 ? text.slice(0, 3900) + "\n\n…truncated." : text;
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
        text: "Showing saved preview",
      });
    }
    await sendCachedPreview(env, chatId, cached);
    return;
  }

  if (await previewLocked(env, chatId)) {
    const waitMsg =
      "<b>Preview in progress</b>\n\n" +
      "Your last request is still running.\n" +
      "Please wait about <b>1 minute</b> before tapping again.";
    if (callbackQueryId) {
      await tg(env, "answerCallbackQuery", {
        callback_query_id: callbackQueryId,
        text: "Please wait ~1 min - preview still running",
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
      text: ok ? "Fetching fresh preview…" : "Preview unavailable",
    });
  }
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: ok
      ? [
          "<b>Preview GMP</b>",
          "",
          "Fetching fresh scores with your filters…",
          "",
          RULE,
          "",
          "<i>Usually under 1 minute.</i>",
          "After it arrives, you can open it again instantly from the saved copy.",
        ].join("\n")
      : [
          "<b>Preview GMP</b>",
          "",
          "Temporarily unavailable.",
          "Try again in a minute, or wait for the next market scan.",
        ].join("\n"),
    parse_mode: "HTML",
    reply_markup: homeInline(env.CHANNEL_ID),
  });
}

async function handleText(env, chatId, text) {
  const raw = (text || "").trim();
  if (!raw) return;

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
    text: "Use the buttons below.\nPreview GMP · Settings · Help · Channel · Feedback",
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
    await answer("Home");
    return sendHome(env, chatId);
  }
  if (data === "help") {
    await answer("Help");
    return sendHelp(env, chatId);
  }
  if (data === "settings") {
    await answer("Settings");
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
    await answer("Feedback");
    return beginFeedback(env, chatId);
  }

  if (data.startsWith("gmp:")) {
    const val = Number(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.min_gmp_pct = val;
    await savePrefs(env, chatId, prefs);
    await clearPreviewCache(env, chatId);
    await answer(`Min GMP → ${val}%`);
    return sendSettings(env, chatId, messageId);
  }
  if (data.startsWith("sub:")) {
    const val = Number(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.min_total_sub = val;
    await savePrefs(env, chatId, prefs);
    await clearPreviewCache(env, chatId);
    await answer(`Min sub → ${val}x`);
    return sendSettings(env, chatId, messageId);
  }
  if (data.startsWith("board:")) {
    const include = ["all", "sme"].includes(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.include_sme = include;
    await savePrefs(env, chatId, prefs);
    await clearPreviewCache(env, chatId);
    await answer(include ? "MAIN + SME" : "MAIN only");
    return sendSettings(env, chatId, messageId);
  }

  await answer("Unknown action");
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
};
