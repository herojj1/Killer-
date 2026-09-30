const { Telegraf, Markup } = require("telegraf");
const prettyMs = require("pretty-ms");

const {
    telegramBotToken, authorisedUsers, adminNames,
    cooldownMs, maxRounds, defaultRounds,
    creditPerKill, creditPerCheck, adminFreeUsage,
    referral, botName
} = require("../config");

const { runKiller } = require("./dispatcher");
const { COMMANDS, checkAccess } = require("./commands");
const { isAdmin, registerAdminCommands, displayName } = require("./admin");
const media = require("./media");
const menus = require("./menus");
const db = require("./db");
const Logger = require("./logger");

const CC_RE = /^(\d{12,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})$/;

function normaliseCC(input) {
    if (!input) return null;
    let s = String(input).trim().replace(/\s+/g, "");
    const parts = s.split("|");
    if (parts.length === 3) {
        const [num, exp, cvv] = parts;
        const e = exp.split("/");
        if (e.length === 2) s = `${num}|${e[0]}|${e[1]}|${cvv}`;
    }
    const m = s.match(CC_RE);
    if (!m) return null;
    let [, num, mm, yy, cvv] = m;
    if (yy.length === 4) yy = yy.slice(2);
    mm = mm.padStart(2, "0");
    yy = yy.padStart(2, "0");
    return { number: num, mm, yy, cvv, raw: `${num}|${mm}|${yy}|${cvv}` };
}

const ICON = { approved: "🟢", declined: "🔴", timeout: "🟡", error: "⚫", missing: "⚪" };

class NovaBot extends Telegraf {
    constructor() {
        super(telegramBotToken);
        this.cooldowns = new Map();
        this.busy = new Set();
        this.botUsername = null;
    }

    isAllowed(ctx) {
        const id = ctx.from.id.toString();
        const uname = (ctx.from.username || "").toLowerCase();
        if (!authorisedUsers.length) return true;
        return authorisedUsers.includes(id) || authorisedUsers.map((u) => u.toLowerCase()).includes(uname);
    }

    cooldownCheck(ctx) {
        const id = ctx.from.id;
        const last = this.cooldowns.get(id) || 0;
        const diff = Date.now() - last;
        if (diff < cooldownMs) return prettyMs(cooldownMs - diff, { secondsDecimalDigits: 0 });
        this.cooldowns.set(id, Date.now());
        return null;
    }

    refLink(code) {
        return `https://t.me/${this.botUsername || "bot"}?start=ref_${code}`;
    }

    helpText(user) {
        const admin = isAdmin({ from: user });
        const lines = [
            `*${botName}* — commands`,
            "",
            "💠 *menu*",
            "/start — main menu",
            "/help — this message",
            "/ping — alive check",
            "/credits — balance + stats",
            "/history — last 10 kills",
            "/creditlog — last 10 credit movements",
            "/referral — your link (alias /ref)",
            "/refs — who you referred",
            "/reftop — referral leaderboard",
            "/gift <@user|id> <amount> — send credits",
            "",
            `*💀 killers* (cost ${creditPerKill}, premium)`,
            ...Object.values(COMMANDS).filter((c) => c.category === "killer")
                .map((c) => `/${c.name} <cc> <zip> — ${c.desc}`),
            "",
            `*🔍 checkers* (cost ${creditPerCheck})`,
            ...Object.values(COMMANDS).filter((c) => c.category === "checker")
                .map((c) => `/${c.name} <cc> <zip> — ${c.desc} [${c.tier.toUpperCase()}]`),
            "",
            "*🛠 tools*",
            ...Object.values(COMMANDS).filter((c) => c.category === "tool")
                .map((c) => `/${c.name}${c.takesInput ? " <bin>" : ""} — ${c.desc}`),
            "",
            "*cc format*: `num|mm|yy|cvv`  or  `num|mm/yy|cvv`"
        ];
        if (admin) {
            lines.push("");
            lines.push("🔧 *admin*");
            lines.push("/addcredit /removecredit /setcredit /give /zapcredits");
            lines.push("/finduser /users /creditlog /top /reftop /stats /broadcast");
            lines.push("/settier <id|@user> free|premium");
            lines.push("/setmedia <key> (reply to media)");
            lines.push("/listmedia");
            lines.push("/resetref /unrefer");
        }
        return lines.join("\n");
    }

    async start() {
        this.use(async (ctx, next) => {
            if (ctx.from && !ctx.from.is_bot) {
                try { db.ensureUser(ctx.from); } catch (e) { Logger.error("ensureUser: " + e.message); }
            }
            return next();
        });

        this._registerNavCallbacks();
        this._registerUserCommands();
        this._registerToolCommands();
        this._registerGateCommands();
        registerAdminCommands(this);

        this.on("text", (ctx) => this._onText(ctx).catch((e) => Logger.error("onText: " + e.message)));

        await this.launch();
        const me = await this.telegram.getMe();
        this.botUsername = me.username;
        Logger.info(`nova online: @${me.username}`);
    }

    async _reply(ctx, text, extra = {}) {
        return ctx.reply(text, { parse_mode: "Markdown", ...extra }).catch(() => {});
    }

    async _editOrReply(ctx, text, keyboard, mediaKey = null) {
        const extra = keyboard ? { reply_markup: keyboard.reply_markup } : {};
        try {
            if (ctx.callbackQuery && ctx.callbackQuery.message && !mediaKey) {
                await ctx.editMessageText(text, { parse_mode: "Markdown", ...extra });
                return;
            }
        } catch (_) {}
        if (mediaKey) {
            const fileId = media.getFileId(mediaKey);
            if (fileId) {
                return ctx.replyWithAnimation(fileId, { caption: text, parse_mode: "Markdown", ...extra }).catch(() =>
                    ctx.reply(text, { parse_mode: "Markdown", ...extra }).catch(() => {})
                );
            }
        }
        return this._reply(ctx, text, extra);
    }

    _registerNavCallbacks() {
        this.action("nav:main", async (ctx) => { await ctx.answerCbQuery(); return this._showMain(ctx); });
        this.action("nav:killers", async (ctx) => { await ctx.answerCbQuery(); return this._editOrReply(ctx, menus.killersText(), menus.killersKeyboard(), media.KEYS.killers); });
        this.action("nav:checkers", async (ctx) => { await ctx.answerCbQuery(); return this._editOrReply(ctx, menus.checkersText(), menus.checkersKeyboard(), media.KEYS.checkers); });
        this.action("nav:tools", async (ctx) => { await ctx.answerCbQuery(); return this._editOrReply(ctx, menus.toolsText(), menus.toolsKeyboard(), media.KEYS.tools); });
        this.action("nav:credits", async (ctx) => { await ctx.answerCbQuery(); return this._cmdCredits(ctx); });
        this.action("nav:referral", async (ctx) => { await ctx.answerCbQuery(); return this._cmdReferral(ctx); });
        this.action("nav:help", async (ctx) => { await ctx.answerCbQuery(); return this._reply(ctx, this.helpText(ctx.from), menus.mainKeyboard()); });
    }

    async _showMain(ctx) {
        const text = menus.welcomeText();
        const kb = menus.mainKeyboard();
        const fileId = media.getFileId(media.KEYS.welcome_gif) || media.getFileId(media.KEYS.main);
        if (fileId) {
            return ctx.replyWithAnimation(fileId, { caption: text, parse_mode: "Markdown", reply_markup: kb.reply_markup })
                .catch(() => this._reply(ctx, text, { reply_markup: kb.reply_markup }));
        }
        return this._reply(ctx, text, { reply_markup: kb.reply_markup });
    }

    _registerUserCommands() {
        this.command("start", (ctx) => this._cmdStart(ctx));
        this.command("help", (ctx) => this._reply(ctx, this.helpText(ctx.from), menus.mainKeyboard()));
        this.command("ping", (ctx) => this._reply(ctx, "pong"));
        this.command("credits", (ctx) => this._cmdCredits(ctx));
        this.command("history", (ctx) => this._cmdHistory(ctx));
        this.command("creditlog", (ctx) => this._cmdCreditLog(ctx));
        this.command("gift", (ctx) => this._cmdGift(ctx));
        this.command("referral", (ctx) => this._cmdReferral(ctx));
        this.command("ref", (ctx) => this._cmdReferral(ctx));
        this.command("refs", (ctx) => this._cmdRefs(ctx));
        this.command("reftop", (ctx) => this._cmdRefTop(ctx));
        this.command("menu", (ctx) => this._showMain(ctx));
    }

    async _cmdStart(ctx) {
        const payload = (ctx.message.text.split(/\s+/)[1] || "");
        if (payload.startsWith("ref_")) {
            const code = payload.slice(4).trim();
            const result = db.applyReferral(ctx.from.id, code);
            if (result.ok) {
                await this._reply(ctx,
                    `welcome ${displayName(ctx.from)}!\n` +
                    `you joined through *${displayName(result.referrer)}*'s referral.\n` +
                    (result.refereeBonus > 0 ? `you got *+${result.refereeBonus}* credits.\n` : "") +
                    `*${displayName(result.referrer)}* got *+${result.referrerBonus}* credits.`
                );
                try {
                    await this.telegram.sendMessage(result.referrer.id,
                        `🎉 *new referral!* ${displayName(ctx.from)} joined through your link. +${result.referrerBonus} credits.`,
                        { parse_mode: "Markdown" });
                } catch (_) {}
            } else {
                const reasons = {
                    already_referred: "you already used a referral link",
                    self_referral: "you can't refer yourself",
                    bad_code: "that referral code doesn't exist",
                    referrer_limit_reached: "referrer limit reached",
                    referrals_disabled: "referrals disabled"
                };
                await this._reply(ctx, `note: ${reasons[result.reason] || "referral not applied"}`);
            }
        }
        return this._showMain(ctx);
    }

    async _cmdCredits(ctx) {
        const u = db.getUser(ctx.from.id);
        if (!u) return this._reply(ctx, "no user record. try /start");
        const lines = [
            `*${botName} — your account*`,
            `id: \`${u.id}\``,
            `tier: *${u.tier.toUpperCase()}*`,
            `credits: *${u.credits}*`,
            `total kills: ${u.total_kills}`,
            `credits spent: ${u.total_credits_spent}`,
            `referrals: *${u.referral_count}* (earned ${u.referral_credits_earned})`,
            "",
            `cost: killers *-${creditPerKill}*, checkers *-${creditPerCheck}*, tools *free*`
        ];
        return this._reply(ctx, lines.join("\n"), menus.mainKeyboard());
    }

    async _cmdHistory(ctx) {
        const rows = db.userHistory(ctx.from.id, 10);
        if (!rows.length) return this._reply(ctx, "no history yet.");
        const lines = rows.map((r) => {
            const d = new Date(r.created_at).toISOString().slice(0, 19).replace("T", " ");
            return `${ICON[r.status] || "?"} \`/${r.command}\` \`${r.card}\` — ${d}`;
        });
        return this._reply(ctx, `*last ${rows.length} kills*\n\n${lines.join("\n")}`);
    }

    async _cmdCreditLog(ctx) {
        const rows = db.creditHistory(ctx.from.id, 10);
        if (!rows.length) return this._reply(ctx, "no credit activity.");
        const lines = rows.map((r) => {
            const d = new Date(r.created_at).toISOString().slice(0, 19).replace("T", " ");
            return `${r.delta >= 0 ? "+" : ""}${r.delta} — ${r.reason || "-"} — ${d}`;
        });
        return this._reply(ctx, `*credit log*\n\n${lines.join("\n")}`);
    }

    async _cmdGift(ctx) {
        const [, target, amountRaw] = ctx.message.text.trim().split(/\s+/);
        if (!target || !amountRaw) return this._reply(ctx, "usage: `/gift <@user|id> <amount>`");
        const amount = Math.abs(parseInt(amountRaw, 10));
        if (!Number.isFinite(amount) || amount <= 0) return this._reply(ctx, "amount must be positive");
        const recipient = /^\d+$/.test(target) ? db.getUser(parseInt(target, 10)) : db.getUserByUsername(target);
        if (!recipient) return this._reply(ctx, `recipient not found: ${target}`);
        if (recipient.id === ctx.from.id) return this._reply(ctx, "you can't gift yourself.");
        const sender = db.getUser(ctx.from.id);
        if (sender.credits < amount) return this._reply(ctx, `not enough credits. have *${sender.credits}*.`);
        db.spendCredit(sender.id, amount, `gift to ${recipient.id}`);
        db.addCredit(recipient.id, amount, `gift from ${sender.id}`, sender.id);
        await this._reply(ctx, `gifted *${amount}* to ${displayName(recipient)}. balance: *${db.getUser(sender.id).credits}*.`);
        try {
            await this.telegram.sendMessage(recipient.id,
                `you received *${amount}* credits from ${displayName(sender)}. balance: *${db.getUser(recipient.id).credits}*.`,
                { parse_mode: "Markdown" });
        } catch (_) {}
    }

    async _cmdReferral(ctx) {
        if (!referral.enabled) return this._reply(ctx, "referrals are disabled.");
        const u = db.getUser(ctx.from.id);
        const link = this.refLink(u.referral_code);
        await this._reply(ctx, [
            "*your referral*",
            "",
            `code: \`${u.referral_code}\``,
            `link: ${link}`,
            "",
            `people referred: *${u.referral_count}*`,
            `credits earned: *${u.referral_credits_earned}*`,
            "",
            `each new user who joins via your link = *+${referral.referrerBonus}* credits`
        ].join("\n"), menus.mainKeyboard());
    }

    async _cmdRefs(ctx) {
        const u = db.getUser(ctx.from.id);
        const rows = db.referralList(u.id, 20);
        if (!rows.length) return this._reply(ctx, "no referrals yet. use /referral to get your link.");
        const lines = rows.map((r, i) => {
            const d = new Date(r.created_at).toISOString().slice(0, 10);
            return `${i + 1}. ${displayName(r)} — ${d}`;
        });
        return this._reply(ctx, `*your referrals* (${u.referral_count})\n\n${lines.join("\n")}`);
    }

    async _cmdRefTop(ctx) {
        const rows = db.referralLeaderboard(10);
        if (!rows.length) return this._reply(ctx, "no referrals yet.");
        const lines = rows.map((u, i) => `${i + 1}. ${displayName(u)} — *${u.referral_count}* refs, *${u.referral_credits_earned}* credits`);
        return this._reply(ctx, `*referral leaderboard*\n\n${lines.join("\n")}`);
    }

    _registerToolCommands() {
        this.command("vbv", (ctx) => this._cmdVbv(ctx));
        this.command("bin", (ctx) => this._cmdBin(ctx));
    }

    async _cmdVbv(ctx) {
        const args = ctx.message.text.trim().split(/\s+/).slice(1);
        if (!args.length) return this._reply(ctx, "usage: `/vbv <first6|bin>`");
        const bin = args[0].replace(/\D/g, "").slice(0, 6);
        if (bin.length < 6) return this._reply(ctx, "give at least 6 digits");
        const vbv = guessVbvFromBin(bin);
        return this._reply(ctx, [
            `*VBV lookup*`,
            `bin: \`${bin}\``,
            `vbv: *${vbv.label}*`,
            `bank guess: \`${vbv.bank}\``,
            `country: \`${vbv.country}\``,
            "",
            "_local heuristic — swap for a real BIN API later_"
        ].join("\n"));
    }

    async _cmdBin(ctx) {
        const args = ctx.message.text.trim().split(/\s+/).slice(1);
        if (!args.length) return this._reply(ctx, "usage: `/bin <bin>`");
        const bin = args[0].replace(/\D/g, "").slice(0, 8);
        if (bin.length < 6) return this._reply(ctx, "give at least 6 digits");
        const vbv = guessVbvFromBin(bin);
        const brand = brandFromBin(bin);
        return this._reply(ctx, [
            `*bin lookup*`,
            `bin: \`${bin}\``,
            `brand: *${brand}*`,
            `type: ${typeFromBin(bin)}`,
            `bank: \`${vbv.bank}\``,
            `country: \`${vbv.country}\``,
            `vbv: *${vbv.label}*`
        ].join("\n"));
    }

    _registerGateCommands() {
        for (const cmd of Object.values(COMMANDS)) {
            if (cmd.category !== "killer" && cmd.category !== "checker") continue;
            this.command(cmd.name, (ctx) => this._runGate(ctx, cmd));
        }
    }

    async _runGate(ctx, cmd) {
        if (!this.isAllowed(ctx)) {
            const names = adminNames.map((n) => `@${n}`).join(", ");
            return this._reply(ctx, `not authorised. contact admin: ${names}`);
        }

        const args = ctx.message.text.trim().split(/\s+/).slice(1);
        if (!args.length) return this._reply(ctx, `usage: \`/${cmd.name} <cc> <zip> [rounds]\``);

        const cc = normaliseCC(args[0]);
        if (!cc) return this._reply(ctx, "bad cc format. use `num|mm|yy|cvv`");
        const zip = args[1] || "";
        if (!zip) return this._reply(ctx, `usage: \`/${cmd.name} ${cc.raw} <zip>\``);
        const rounds = Math.max(1, Math.min(maxRounds, parseInt(args[2] || String(defaultRounds), 10) || defaultRounds));

        const user = db.getUser(ctx.from.id);
        const admin = isAdmin(ctx);

        const access = checkAccess(user, cmd);
        if (!access.ok) return this._reply(ctx, access.message);

        const wait = this.cooldownCheck(ctx);
        if (wait) return this._reply(ctx, `cooldown — wait ${wait}`);

        if (this.busy.has(ctx.from.id)) return this._reply(ctx, "already running a job");

        if (!(admin && adminFreeUsage) && cmd.cost > 0) {
            if (user.credits < cmd.cost) {
                return this._reply(ctx, `insufficient credits. need *${cmd.cost}*, have *${user.credits}*.\ncontact: ${adminNames.map((n) => `@${n}`).join(", ")}`);
            }
            const spent = db.spendCredit(ctx.from.id, cmd.cost, `${cmd.category}:${cmd.name}`);
            if (!spent.ok) return this._reply(ctx, `credit error: ${spent.error}`);
        }

        const msg = await this._reply(ctx,
            `running */${cmd.name}* (${cmd.gateway}) on \`${cc.raw}\` (${rounds} rounds)...\n` +
            `balance after: *${db.getUser(ctx.from.id).credits}*`
        );

        this.busy.add(ctx.from.id);
        try {
            const res = await runKiller(cmd.gateway, cc.raw, zip, rounds);
            db.logKill({
                user_id: ctx.from.id,
                command: cmd.name,
                gateway: cmd.gateway,
                card: cc.raw,
                zip,
                status: res.status,
                attempts: res.attempts,
                duration: res.duration,
                raw: res.raw
            });
            await this._reply(ctx, this._formatGateResult(cmd, cc.raw, res, ctx.from.id), {
                reply_to_message_id: msg.message_id
            });
        } finally {
            this.busy.delete(ctx.from.id);
        }
    }

    _formatGateResult(cmd, cc, res, userId) {
        const u = db.getUser(userId);
        const lines = [
            `*command:* \`/${cmd.name}\` — ${cmd.label}`,
            `*gateway:* \`${cmd.gateway}\``,
            `*card:* \`${cc}\``,
            `*status:* ${ICON[res.status] || "?"} \`${res.status}\``,
            `*attempts:* ${res.attempts ?? "-"}`,
            `*duration:* ${res.duration ?? "-"}s`,
            `*balance:* ${u.credits}`
        ];
        if (res.raw) lines.push(`*raw:* \`${String(res.raw).slice(0, 180)}\``);
        return lines.join("\n");
    }

    async _onText(ctx) {
        const text = ctx.message.text || "";
        if (!text.startsWith(".")) return;
        const [cmd, ...rest] = text.slice(1).trim().split(/\s+/);
        const mapped = COMMANDS[cmd.toLowerCase()];
        if (!mapped) return this._reply(ctx, "unknown command. try /help");
        ctx.message.text = `/${cmd} ${rest.join(" ")}`;
        return this._runGate(ctx, mapped);
    }
}

function brandFromBin(bin) {
    const p = bin[0];
    if (p === "4") return "VISA";
    if (p === "5" || p === "2") return "MASTERCARD";
    if (p === "3") return "AMEX";
    if (p === "6") return "DISCOVER";
    return "UNKNOWN";
}

function typeFromBin(bin) {
    return bin[0] === "3" ? "credit" : "credit";
}

function guessVbvFromBin(bin) {
    const bank = `issuer-${bin.slice(0, 4)}`;
    const d = parseInt(bin[5] || "0", 10);
    if (d % 3 === 0) return { label: "VBV ✅ (guess)", bank, country: "unknown" };
    if (d % 3 === 1) return { label: "MSC ✅ (guess)", bank, country: "unknown" };
    return { label: "NON-VBV ❔", bank, country: "unknown" };
}

module.exports = { NovaBot, normaliseCC };
