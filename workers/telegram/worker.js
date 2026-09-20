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
  return `Min GMP: ${p.min_gmp_pct}%\nMin subscription: ${p.min_total_sub}x\nBoard: ${board}`;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function welcomeText(p, channelId) {
  const channel = channelUrl(channelId);
  return (
    `<b>IPO Devta</b>\n` +
    `Your IPO fill assistant.\n\n` +
    `On closing days you receive a clear 👍 / 👎 view based on ` +
    `<b>your</b> filters - GMP, subscription, and board - so you know ` +
    `what to consider filing.\n\n` +
    `Use the buttons below. No typing required.\n\n` +
    `<b>Your filters</b>\n${esc(prefsSummary(p))}\n\n` +
    `Prefer a quieter feed? Join the public channel for the daily closing ` +
    `list without personal filters:\n${esc(channel)}\n\n` +
    `No selling. No promotions. Just timely IPO fill reminders.`
  );
}

function helpText(channelId) {
  const channel = channelUrl(channelId);
  return (
    `<b>How IPO Devta works</b>\n\n` +
    `• <b>Preview GMP</b> - last five processed issues, scored with your filters.\n` +
    `• <b>Settings</b> - tap to set min GMP %, min subscription, and board.\n` +
    `• <b>Channel</b> - public closing-day feed if you prefer not to use DMs.\n\n` +
    `Weekday mornings: when issues close that day, you get a personalized DM.\n` +
    `Weekday evenings: we record the book for the next morning's decision.\n\n` +
    `Channel: ${esc(channel)}\n\n` +
    `Grey-market premium is unofficial and can move quickly.\n` +
    `This is information only - not investment advice. Read the RHP.`
  );
}

function settingsText(p) {
  return (
    `<b>Your filters</b>\n\n${esc(prefsSummary(p))}\n\n` +
    `Tap a button to update. Closing-day DMs use these values right away.`
  );
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
    text: "Quick actions:",
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
    text:
      `<b>Public channel</b>\n\n` +
      `Daily closing-day GMP feed - no personal filters.\n` +
      `Useful if you want reminders without DMs.\n\n` +
      `<a href="${url}">Join ${url.replace("https://t.me/", "@")}</a>`,
    parse_mode: "HTML",
    disable_web_page_preview: true,
    reply_markup: {
      inline_keyboard: [[{ text: "Join channel", url }]],
    },
  });
}

async function sendPreviewAck(env, chatId) {
  await getPrefs(env, chatId);
  const ok = await triggerPreview(env, chatId);
  await tg(env, "sendMessage", {
    chat_id: chatId,
    text: ok
      ? "<b>Preview GMP</b>\n\nFetching the latest scores with your filters. This usually takes under a minute."
      : "<b>Preview GMP</b>\n\nPreview is temporarily unavailable. Try again shortly, or wait for the next market scan.",
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
    text: "Use the buttons below - Preview GMP, Settings, Help, or Channel.",
    reply_markup: mainKeyboard(),
  });
}

async function handleCallback(env, cb) {
  const chatId = cb.message?.chat?.id || cb.from?.id;
  const messageId = cb.message?.message_id;
  const data = (cb.data || "").trim();
  if (!chatId) return;

  const answer = async (text) =>
    tg(env, "answerCallbackQuery", {
      callback_query_id: cb.id,
      text: text || undefined,
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
    await answer("Starting preview…");
    return sendPreviewAck(env, chatId);
  }

  if (data.startsWith("gmp:")) {
    const val = Number(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.min_gmp_pct = val;
    await savePrefs(env, chatId, prefs);
    await answer(`Min GMP set to ${val}%`);
    return sendSettings(env, chatId, messageId);
  }
  if (data.startsWith("sub:")) {
    const val = Number(data.split(":")[1]);
    const prefs = await getPrefs(env, chatId);
    prefs.min_total_sub = val;
    await savePrefs(env, chatId, prefs);
    await answer(`Min subscription set to ${val}x`);
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
