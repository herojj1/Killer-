const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const Database = require("better-sqlite3");
const { dataDir, startingCredits, referral } = require("../config");
const Logger = require("./logger");

let db = null;

function init() {
    if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
    const file = path.join(dataDir, "nova.db");
    db = new Database(file);
    db.pragma("journal_mode = WAL");

    db.exec(`
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            credits       INTEGER NOT NULL DEFAULT 0,
            tier          TEXT NOT NULL DEFAULT 'free',
            created_at    INTEGER NOT NULL,
            last_seen     INTEGER NOT NULL,
            total_kills   INTEGER NOT NULL DEFAULT 0,
            total_credits_spent INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS kills (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            command       TEXT NOT NULL,
            gateway       TEXT NOT NULL,
            card          TEXT NOT NULL,
            zip           TEXT NOT NULL,
            status        TEXT NOT NULL,
            attempts      INTEGER,
            duration      REAL,
            raw           TEXT,
            created_at    INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS credit_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            delta         INTEGER NOT NULL,
            reason        TEXT,
            actor_id      INTEGER,
            created_at    INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS media (
            key           TEXT PRIMARY KEY,
            file_id       TEXT NOT NULL,
            updated_at    INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_kills_user ON kills(user_id);
        CREATE INDEX IF NOT EXISTS idx_kills_created ON kills(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_credit_log_user ON credit_log(user_id);
    `);

    const cols = db.prepare("PRAGMA table_info(users)").all().map((c) => c.name);
    if (!cols.includes("referral_code"))           db.exec("ALTER TABLE users ADD COLUMN referral_code TEXT");
    if (!cols.includes("referred_by"))             db.exec("ALTER TABLE users ADD COLUMN referred_by INTEGER");
    if (!cols.includes("referral_count"))          db.exec("ALTER TABLE users ADD COLUMN referral_count INTEGER NOT NULL DEFAULT 0");
    if (!cols.includes("referral_credits_earned")) db.exec("ALTER TABLE users ADD COLUMN referral_credits_earned INTEGER NOT NULL DEFAULT 0");
    if (!cols.includes("tier"))                    db.exec("ALTER TABLE users ADD COLUMN tier TEXT NOT NULL DEFAULT 'free'");
    db.exec("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_refcode ON users(referral_code) WHERE referral_code IS NOT NULL");

    Logger.info(`db ready at ${file}`);
}

function ensureUser(tgUser) {
    const now = Date.now();
    let row = db.prepare("SELECT * FROM users WHERE id = ?").get(tgUser.id);
    if (!row) {
        const code = generateReferralCode(tgUser.id);
        db.prepare(`INSERT INTO users (id, username, first_name, credits, tier, created_at, last_seen, referral_code)
                    VALUES (?, ?, ?, ?, 'free', ?, ?, ?)`)
          .run(tgUser.id, tgUser.username || null, tgUser.first_name || null, startingCredits, now, now, code);
        addCredit(tgUser.id, 0, "welcome_bonus", null);
        row = db.prepare("SELECT * FROM users WHERE id = ?").get(tgUser.id);
    } else {
        db.prepare("UPDATE users SET username = ?, first_name = ?, last_seen = ? WHERE id = ?")
          .run(tgUser.username || null, tgUser.first_name || null, now, tgUser.id);
        if (!row.referral_code) {
            const code = generateReferralCode(tgUser.id);
            db.prepare("UPDATE users SET referral_code = ? WHERE id = ?").run(code, tgUser.id);
        }
    }
    return db.prepare("SELECT * FROM users WHERE id = ?").get(tgUser.id);
}

const getUser = (id) => db.prepare("SELECT * FROM users WHERE id = ?").get(id);
const getUserByUsername = (u) => {
    if (!u) return null;
    return db.prepare("SELECT * FROM users WHERE LOWER(username) = LOWER(?)").get(u.replace(/^@/, ""));
};
const getUserByReferralCode = (c) => db.prepare("SELECT * FROM users WHERE referral_code = ?").get(c);

function addCredit(userId, delta, reason, actorId) {
    if (delta !== 0) db.prepare("UPDATE users SET credits = credits + ? WHERE id = ?").run(delta, userId);
    db.prepare("INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?, ?, ?, ?, ?)")
      .run(userId, delta, reason || null, actorId || null, Date.now());
    return getUser(userId);
}

function spendCredit(userId, amount, reason) {
    const u = getUser(userId);
    if (!u) return { ok: false, error: "user not found" };
    if (u.credits < amount) return { ok: false, error: "insufficient" };
    db.prepare("UPDATE users SET credits = credits - ?, total_credits_spent = total_credits_spent + ? WHERE id = ?")
      .run(amount, amount, userId);
    db.prepare("INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?, ?, ?, ?, ?)")
      .run(userId, -amount, reason, null, Date.now());
    return { ok: true, user: getUser(userId) };
}

function setTier(userId, tier) {
    db.prepare("UPDATE users SET tier = ? WHERE id = ?").run(tier, userId);
    return getUser(userId);
}

function generateReferralCode(userId) {
    for (let i = 0; i < 12; i++) {
        const seed = `${userId}-${Date.now()}-${Math.random()}`;
        const code = crypto.createHash("sha1").update(seed).digest("hex").slice(0, 8);
        if (!db.prepare("SELECT 1 FROM users WHERE referral_code = ?").get(code)) return code;
    }
    return `u${userId.toString(36)}`.slice(0, 12);
}

function applyReferral(newUserId, code) {
    if (!referral.enabled) return { ok: false, reason: "referrals_disabled" };
    if (!code) return { ok: false, reason: "no_code" };
    const referee = getUser(newUserId);
    if (!referee) return { ok: false, reason: "referee_missing" };
    if (referee.referred_by) return { ok: false, reason: "already_referred" };
    const referrer = getUserByReferralCode(code);
    if (!referrer) return { ok: false, reason: "bad_code" };
    if (referrer.id === newUserId) return { ok: false, reason: "self_referral" };
    if (referral.maxReferralsPerUser > 0 && referrer.referral_count >= referral.maxReferralsPerUser)
        return { ok: false, reason: "referrer_limit_reached" };

    const now = Date.now();
    const tx = db.transaction(() => {
        db.prepare("UPDATE users SET referred_by = ? WHERE id = ?").run(referrer.id, newUserId);
        db.prepare("UPDATE users SET referral_count = referral_count + 1, referral_credits_earned = referral_credits_earned + ? WHERE id = ?")
          .run(referral.referrerBonus, referrer.id);
        if (referral.referrerBonus > 0) {
            db.prepare("UPDATE users SET credits = credits + ? WHERE id = ?").run(referral.referrerBonus, referrer.id);
            db.prepare("INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?, ?, ?, ?, ?)")
              .run(referrer.id, referral.referrerBonus, `referral_bonus:${newUserId}`, newUserId, now);
        }
        if (referral.refereeBonus > 0) {
            db.prepare("UPDATE users SET credits = credits + ? WHERE id = ?").run(referral.refereeBonus, newUserId);
            db.prepare("INSERT INTO credit_log (user_id, delta, reason, actor_id, created_at) VALUES (?, ?, ?, ?, ?)")
              .run(newUserId, referral.refereeBonus, `referee_bonus:${referrer.id}`, referrer.id, now);
        }
    });
    tx();

    return {
        ok: true,
        referrer: getUser(referrer.id),
        referee: getUser(newUserId),
        referrerBonus: referral.referrerBonus,
        refereeBonus: referral.refereeBonus
    };
}

const referralLeaderboard = (limit = 10) =>
    db.prepare("SELECT * FROM users WHERE referral_count > 0 ORDER BY referral_count DESC, referral_credits_earned DESC LIMIT ?").all(limit);
const referralList = (userId, limit = 20) =>
    db.prepare("SELECT * FROM users WHERE referred_by = ? ORDER BY created_at DESC LIMIT ?").all(userId, limit);
const referralTotals = () => ({
    totalReferrals: db.prepare("SELECT COUNT(*) AS c FROM users WHERE referred_by IS NOT NULL").get().c,
    creditsPaid: db.prepare("SELECT COALESCE(SUM(delta),0) AS s FROM credit_log WHERE reason LIKE 'referral_bonus:%'").get().s
});

function logKill(entry) {
    db.prepare(`INSERT INTO kills (user_id, command, gateway, card, zip, status, attempts, duration, raw, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(entry.user_id, entry.command, entry.gateway, entry.card, entry.zip, entry.status,
           entry.attempts || 0, entry.duration || 0, (entry.raw || "").slice(0, 400), Date.now());
    if (entry.status === "approved" || entry.status === "declined") {
        db.prepare("UPDATE users SET total_kills = total_kills + 1 WHERE id = ?").run(entry.user_id);
    }
}

const userHistory = (id, limit = 10) => db.prepare("SELECT * FROM kills WHERE user_id = ? ORDER BY id DESC LIMIT ?").all(id, limit);
const creditHistory = (id, limit = 10) => db.prepare("SELECT * FROM credit_log WHERE user_id = ? ORDER BY id DESC LIMIT ?").all(id, limit);
const topUsers = (limit = 10) => db.prepare("SELECT * FROM users ORDER BY total_kills DESC LIMIT ?").all(limit);
const allUsers = (limit = 50, offset = 0) => db.prepare("SELECT * FROM users ORDER BY last_seen DESC LIMIT ? OFFSET ?").all(limit, offset);

function globalStats() {
    return {
        users: db.prepare("SELECT COUNT(*) AS c FROM users").get().c,
        kills: db.prepare("SELECT COUNT(*) AS c FROM kills").get().c,
        approved: db.prepare("SELECT COUNT(*) AS c FROM kills WHERE status='approved'").get().c,
        declined: db.prepare("SELECT COUNT(*) AS c FROM kills WHERE status='declined'").get().c,
        spent: db.prepare("SELECT COALESCE(SUM(-delta),0) AS s FROM credit_log WHERE delta < 0").get().s,
        creditsOutstanding: db.prepare("SELECT COALESCE(SUM(credits),0) AS s FROM users").get().s,
        premium: db.prepare("SELECT COUNT(*) AS c FROM users WHERE tier='premium'").get().c
    };
}

const gatewayStats = () =>
    db.prepare(`SELECT gateway, COUNT(*) AS total,
                       SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) AS approved,
                       SUM(CASE WHEN status='declined' THEN 1 ELSE 0 END) AS declined
                FROM kills GROUP BY gateway ORDER BY total DESC`).all();

const getMedia = (key) => db.prepare("SELECT * FROM media WHERE key = ?").get(key);
const setMedia = (key, fileId) => db.prepare(`INSERT INTO media (key, file_id, updated_at) VALUES (?, ?, ?)
                                              ON CONFLICT(key) DO UPDATE SET file_id=excluded.file_id, updated_at=excluded.updated_at`)
    .run(key, fileId, Date.now());

module.exports = {
    init, ensureUser, getUser, getUserByUsername, getUserByReferralCode,
    addCredit, spendCredit, setTier,
    generateReferralCode, applyReferral, referralLeaderboard, referralList, referralTotals,
    logKill, userHistory, creditHistory, topUsers, allUsers, globalStats, gatewayStats,
    getMedia, setMedia,
    raw: () => db
};
