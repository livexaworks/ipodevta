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
const RULE = "────────────";

const BTN = {
  PREVIEW: "Preview GMP",
  SETTINGS: "Settings",
  HELP: "Help",
  CHANNEL: "Channel",
};

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
    "<b>IPO Devta</b>",
    "<i>Your IPO fill assistant</i>",
    "",
    "On closing days you get a clear 👍 / 👎 view from <b>your</b> filters - so you know what to consider filing.",
    "",
    prefsBlock(p),
    "",
    RULE,
    "",
    "Use the buttons below - no typing needed.",
    "",
    `Prefer a shared feed? <a href="${channel}">Join the channel</a>`,
    "",
    "<i>No selling. No promotions. Just fill reminders.</i>",
  ].join("\n");
}

function helpText(channelId) {
  const channel = channelUrl(channelId);
  return [
    "<b>How it works</b>",
    "",
    "<b>Preview GMP</b>",
    "Last five scored issues with your filters.",
    "",
    "<b>Settings</b>",
    "Tap to set GMP %, subscription, and board.",
    "",
    "<b>Channel</b>",
    "Public closing-day feed without personal filters.",
    "",
    RULE,
    "",
    "Weekday morning - personalized DM when issues close",
    "Weekday evening - book recorded for next day",
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
    "Tap a value below to update.",
    "Changes apply to Preview and closing-day DMs right away.",
  ].join("\n");
}

function channelText(channelId) {
  const url = channelUrl(channelId);
  return [
    "<b>Public channel</b>",
    "",
    "Daily closing-day GMP feed.",
    "No personal filters - useful if you want reminders without DMs.",
    "",
    RULE,
    "",
    `<a href="${url}">Join ${url.replace("https://t.me/", "@")}</a>`,
  ].join("\n");
}

function mainKeyboard() {
  return {
    keyboard: [
      [{ text: BTN.PREVIEW }, { text: BTN.SETTINGS }],
      [{ text: BTN.HELP }, { text: BTN.CHANNEL }],
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

async function sendPreviewAck(env, chatId, callbackQueryId) {
  await getPrefs(env, chatId);

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
      text: ok ? "Preview started" : "Preview unavailable",
    });
  }
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: ok
      ? [
          "<b>Preview GMP</b>",
          "",
          "Fetching scores with your filters…",
          "",
          RULE,
          "",
          "<i>Usually under 1 minute.</i>",
          "Please don’t tap Preview again until it arrives.",
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

  if (raw === BTN.PREVIEW) return sendPreviewAck(env, chatId);
  if (raw === BTN.SETTINGS) return sendSettings(env, chatId);
  if (raw === BTN.HELP) return sendHelp(env, chatId);
  if (raw === BTN.CHANNEL) return sendChannel(env, chatId);

  const cmd = raw.split(/\s+/)[0].toLowerCase().split("@")[0];
  if (["/start", "/menu", "start", "menu"].includes(cmd)) return sendHome(env, chatId);
  if (["/help", "help"].includes(cmd)) return sendHelp(env, chatId);
  if (["/settings", "/status", "settings", "status"].includes(cmd))
    return sendSettings(env, chatId);
  if (["/preview", "preview"].includes(cmd)) return sendPreviewAck(env, chatId);
  if (["/channel", "channel"].includes(cmd)) return sendChannel(env, chatId);

  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: "Use the buttons below.\nPreview GMP · Settings · Help · Channel",
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

  if (data.startsWith("gmp:")) {
    const val = Number(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.min_gmp_pct = val;
    await savePrefs(env, chatId, prefs);
    await answer(`Min GMP → ${val}%`);
    return sendSettings(env, chatId, messageId);
  }
  if (data.startsWith("sub:")) {
    const val = Number(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.min_total_sub = val;
    await savePrefs(env, chatId, prefs);
    await answer(`Min sub → ${val}x`);
    return sendSettings(env, chatId, messageId);
  }
  if (data.startsWith("board:")) {
    const include = ["all", "sme"].includes(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.include_sme = include;
    await savePrefs(env, chatId, prefs);
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
