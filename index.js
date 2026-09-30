const { NovaBot } = require("./bot/telegram");
const Logger = require("./bot/logger");
const db = require("./bot/db");

process.on("unhandledRejection", (e) => Logger.error("unhandledRejection: " + (e && e.stack || e)));
process.on("uncaughtException", (e) => Logger.error("uncaughtException: " + (e && e.stack || e)));

db.init();

const bot = new NovaBot();
bot.start().catch((e) => Logger.error("fatal: " + e.message));
