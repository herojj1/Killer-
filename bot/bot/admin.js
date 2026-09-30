const db = require("./db");
const media = require("./media");
const Logger = require("./logger");
const { adminUsers, broadcastDelayMs } = require("../config");

function isAdmin(ctx) {
    const id = ctx.from.id.toString();
    const uname = (ctx.from.username || "").toLowerCase();
    if (!adminUsers.length) return false;
    return adminUsers.includes(id) || adminUsers.map((u) => u.toLowerCase()).includes(uname);
}

function registerAdminCommands(bot) {
    const guard = (h) => async (ctx, ...rest) => {
        if (!isAdmin(ctx)) return ctx.reply("admin only.").catch(() => {});
        return h(ctx, ...rest);
    };

    bot.command("addcredit", guard(async (ctx) => {
        const [, target, amountRaw, ...reasonParts] = ctx.message.text.trim().split(/\s+/);
        if (!target || !amountRaw) return ctx.reply("usage: `/addcredit <id|@user> <amount> [reason]`", { parse_mode: "Markdown" });
        const amount = parseInt(amountRaw, 10);
        if (!Number.isFinite(amount) || amount === 0) return ctx.reply("bad amount");
        const user = resolveTarget(target);
        if (!user) return ctx.reply(`user not found: ${target}`);
        const reason = reasonParts.join(" ") || "admin grant";
        const updated = db.addCredit(user.id, amount, reason, ctx.from.id);
        await ctx.reply(`ok. ${displayName(user)} → *${updated.credits}* credits.`, { parse_mode: "Markdown" });
        try { await bot.telegram.sendMessage(user.id, `you received *${amount > 0 ? "+" : ""}${amount}* credits.\nreason: ${reason}\nbalance: ${updated.credits}`, { parse_mode: "Markdown" }); } catch (_) {}
    }));

    bot.command("removecredit", guard(async (ctx) => {
        const [, target, amountRaw, ...reasonParts] = ctx.message.text.trim().split(/\s+/);
        if (!target || !amountRaw) return ctx.reply("usage: `/removecredit <id|@user> <amount> [reason]`", { parse_mode: "Markdown" });
        const amount = Math.abs(parseInt(amountRaw, 10));
        if (!Number.isFinite(amount) || amount === 0) return ctx.reply("bad amount");
        const user = resolveTarget(target);
        if (!user) return ctx.reply(`user not found: ${target}`);
        const reason = reasonParts.join(" ") || "admin remove";
        const updated = db.addCredit(user.id, -amount, reason, ctx.from.id);
        await ctx.reply(`ok. ${displayName(user)} → *${updated.credits}* credits.`, { parse_mode: "Markdown" });
        try { await bot.telegram.sendMessage(user.id, `an admin removed *${amount}* credits.\nreason: ${reason}\nbalance: ${updated.credits}`, { parse_mode: "Markdown" }); } catch (_) {}
    }));

    bot.command("setcredit", guard(async (ctx) => {
        const [, target, amountRaw] = ctx.message.text.trim().split(/\s+/);
        if (!target || amountRaw === undefined) return ctx.reply("usage: `/setcredit <id|@user> <amount>`", { parse_mode: "Markdown" });
        const amount = parseInt(amountRaw, 10);
        if (!Number.isFinite(amount) || amount < 0) return ctx.reply("amount >= 0");
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        const delta = amount - user.credits;
        const updated = db.addCredit(user.id, delta, `admin set to ${amount}`, ctx.from.id);
        await ctx.reply(`ok. ${displayName(user)} → *${updated.credits}*.`, { parse_mode: "Markdown" });
    }));

    bot.command("give", guard(async (ctx) => {
        const [, target, amountRaw] = ctx.message.text.trim().split(/\s+/);
        if (!target || !amountRaw) return ctx.reply("usage: `/give <id|@user> <amount>`", { parse_mode: "Markdown" });
        const amount = Math.abs(parseInt(amountRaw, 10));
        if (!Number.isFinite(amount) || amount === 0) return ctx.reply("bad amount");
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        const updated = db.addCredit(user.id, amount, "admin gift", ctx.from.id);
        await ctx.reply(`gifted *${amount}* to ${displayName(user)}. balance: *${updated.credits}*.`, { parse_mode: "Markdown" });
    }));

    bot.command("zapcredits", guard(async (ctx) => {
        const target = ctx.message.text.trim().split(/\s+/)[1];
        if (!target) return ctx.reply("usage: `/zapcredits <id|@user>`");
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        const updated = db.addCredit(user.id, -user.credits, "admin zap", ctx.from.id);
        await ctx.reply(`zapped. ${displayName(user)} → *${updated.credits}*.`, { parse_mode: "Markdown" });
    }));

    bot.command("settier", guard(async (ctx) => {
        const [, target, tierRaw] = ctx.message.text.trim().split(/\s+/);
        const tier = (tierRaw || "").toLowerCase();
        if (!target || !["free", "premium"].includes(tier)) return ctx.reply("usage: `/settier <id|@user> free|premium`", { parse_mode: "Markdown" });
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        const updated = db.setTier(user.id, tier);
        await ctx.reply(`ok. ${displayName(user)} is now *${updated.tier.toUpperCase()}*.`, { parse_mode: "Markdown" });
        try { await bot.telegram.sendMessage(user.id, `your tier was updated to *${updated.tier.toUpperCase()}*.`, { parse_mode: "Markdown" }); } catch (_) {}
    }));

    bot.command("finduser", guard(async (ctx) => {
        const target = ctx.message.text.trim().split(/\s+/)[1];
        if (!target) return ctx.reply("usage: `/finduser <id|@user>`", { parse_mode: "Markdown" });
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        const referredBy = user.referred_by ? db.getUser(user.referred_by) : null;
        await ctx.reply([
            `*user*`,
            `id: \`${user.id}\``,
            `username: @${user.username || "-"}`,
            `name: ${user.first_name || "-"}`,
            `tier: *${user.tier.toUpperCase()}*`,
            `credits: *${user.credits}*`,
            `kills: ${user.total_kills}`,
            `spent: ${user.total_credits_spent}`,
            `ref code: \`${user.referral_code}\``,
            `refs: ${user.referral_count} (earned ${user.referral_credits_earned})`,
            `referred by: ${referredBy ? `${displayName(referredBy)} (${referredBy.id})` : "-"}`,
            `joined: ${new Date(user.created_at).toISOString()}`
        ].join("\n"), { parse_mode: "Markdown" });
    }));

    bot.command("users", guard(async (ctx) => {
        const page = Math.max(0, parseInt((ctx.message.text.split(/\s+/)[1] || "0"), 10) || 0);
        const limit = 20;
        const users = db.allUsers(limit, page * limit);
        if (!users.length) return ctx.reply("no users on this page.");
        const lines = users.map((u, i) =>
            `${page * limit + i + 1}. \`${u.id}\` ${displayName(u)} [${u.tier}] — *${u.credits}* cr, ${u.total_kills} kills, ${u.referral_count} refs`
        );
        await ctx.reply(`*users page ${page + 1}*\n\n${lines.join("\n")}`, { parse_mode: "Markdown" });
    }));

    bot.command("stats", guard(async (ctx) => {
        const g = db.globalStats();
        const byGw = db.gatewayStats();
        const ref = db.referralTotals();
        const gwLines = byGw.map((r) => `• \`${r.gateway}\` — ${r.total} total, ${r.approved} approved, ${r.declined} declined`);
        await ctx.reply([
            "*global stats*",
            `users: ${g.users} (premium: ${g.premium})`,
            `kills: ${g.kills} (approved ${g.approved} / declined ${g.declined})`,
            `credits spent: ${g.spent}`,
            `credits outstanding: ${g.creditsOutstanding}`,
            "",
            "*referrals*",
            `total: ${ref.totalReferrals}`,
            `credits paid: ${ref.creditsPaid}`,
            "",
            "*by gateway*",
            gwLines.length ? gwLines.join("\n") : "no kills yet"
        ].join("\n"), { parse_mode: "Markdown" });
    }));

    bot.command("top", guard(async (ctx) => {
        const top = db.topUsers(10);
        if (!top.length) return ctx.reply("no data yet.");
        const lines = top.map((u, i) => `${i + 1}. ${displayName(u)} [${u.tier}] — *${u.total_kills}* kills`);
        await ctx.reply(`*top users*\n\n${lines.join("\n")}`, { parse_mode: "Markdown" });
    }));

    bot.command("reftop", async (ctx) => {
        const rows = db.referralLeaderboard(10);
        if (!rows.length) return ctx.reply("no referrals yet.");
        const lines = rows.map((u, i) => `${i + 1}. ${displayName(u)} — *${u.referral_count}* refs, *${u.referral_credits_earned}* credits`);
        await ctx.reply(`*referral leaderboard*\n\n${lines.join("\n")}`, { parse_mode: "Markdown" });
    });

    bot.command("creditlog", guard(async (ctx) => {
        const target = ctx.message.text.trim().split(/\s+/)[1];
        if (!target) return ctx.reply("usage: `/creditlog <id|@user>`", { parse_mode: "Markdown" });
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        const rows = db.creditHistory(user.id, 15);
        if (!rows.length) return ctx.reply("no activity.");
        const lines = rows.map((r) =>
            `\`${new Date(r.created_at).toISOString().slice(0, 19)}\` ${r.delta >= 0 ? "+" : ""}${r.delta} — ${r.reason || "-"}`
        );
        await ctx.reply(`*credit log — ${displayName(user)}*\n\n${lines.join("\n")}`, { parse_mode: "Markdown" });
    }));

    bot.command("broadcast", guard(async (ctx) => {
        const msg = ctx.message.text.replace(/^\/broadcast\s*/i, "").trim();
        if (!msg) return ctx.reply("usage: `/broadcast <message>`", { parse_mode: "Markdown" });
        const users = db.raw().prepare("SELECT id FROM users").all();
        let sent = 0, failed = 0;
        await ctx.reply(`broadcasting to ${users.length}...`);
        for (const u of users) {
            try { await bot.telegram.sendMessage(u.id, msg); sent++; } catch (_) { failed++; }
            await new Promise((r) => setTimeout(r, broadcastDelayMs));
        }
        await ctx.reply(`done. sent ${sent}, failed ${failed}.`);
    }));

    bot.command("resetref", guard(async (ctx) => {
        const target = ctx.message.text.trim().split(/\s+/)[1];
        if (!target) return ctx.reply("usage: `/resetref <id|@user>`");
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        const newCode = db.generateReferralCode(user.id);
        db.raw().prepare("UPDATE users SET referral_code = ? WHERE id = ?").run(newCode, user.id);
        await ctx.reply(`new code for ${displayName(user)}: \`${newCode}\``, { parse_mode: "Markdown" });
    }));

    bot.command("unrefer", guard(async (ctx) => {
        const target = ctx.message.text.trim().split(/\s+/)[1];
        if (!target) return ctx.reply("usage: `/unrefer <id|@user>`");
        const user = resolveTarget(target);
        if (!user) return ctx.reply("not found.");
        db.raw().prepare("UPDATE users SET referred_by = NULL WHERE id = ?").run(user.id);
        await ctx.reply(`cleared referred_by for ${displayName(user)}.`);
    }));

    bot.command("setmedia", guard(async (ctx) => {
        const key = ctx.message.text.trim().split(/\s+/)[1];
        if (!key) return ctx.reply("usage: reply to a GIF/photo with `/setmedia <main|killers|checkers|tools|welcome_gif>`", { parse_mode: "Markdown" });
        const m = ctx.message.reply_to_message;
        if (!m) return ctx.reply("reply to a media message with this command.");
        const fileId = (m.animation && m.animation.file_id) ||
                       (m.document && m.document.file_id) ||
                       (m.photo && m.photo[m.photo.length - 1].file_id) ||
                       (m.video && m.video.file_id);
        if (!fileId) return ctx.reply("no media found in replied message.");
        media.remember(key, fileId);
        await ctx.reply(`saved media for *${key}*.`, { parse_mode: "Markdown" });
    }));

    bot.command("listmedia", guard(async (ctx) => {
        const keys = Object.keys(media.KEYS).map((k) => media.KEYS[k]);
        const lines = keys.map((k) => `${k}: ${media.getFileId(k) ? "✅ set" : "❌ empty"}`);
        await ctx.reply(`*media keys*\n\n${lines.join("\n")}`, { parse_mode: "Markdown" });
    }));
}

function resolveTarget(target) {
    if (/^\d+$/.test(target)) return db.getUser(parseInt(target, 10));
    return db.getUserByUsername(target);
}

function displayName(u) {
    if (!u) return "unknown";
    if (u.username) return `@${u.username}`;
    return u.first_name || `user ${u.id}`;
}

module.exports = { isAdmin, registerAdminCommands, displayName };
