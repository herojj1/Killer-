const { Markup } = require("telegraf");
const { COMMANDS } = require("./commands");
const { botName, botTagline, creditPerKill, creditPerCheck } = require("../config");

function welcomeText() {
    return [
        `*Welcome to ${botName}*`,
        "",
        botTagline,
        "",
        "To use in a GroupChat promote it as Admin ⏳",
        "",
        `*Credits system*`,
        `• Killer Commands [-${creditPerKill}]`,
        `• Checker Commands [-${creditPerCheck}]`,
        "",
        "👇 pick a category"
    ].join("\n");
}

function mainKeyboard() {
    return Markup.inlineKeyboard([
        [Markup.button.callback("Killers", "nav:killers"), Markup.button.callback("Other Tools", "nav:tools")],
        [Markup.button.callback("Checker", "nav:checkers"), Markup.button.callback("🎁 Referral", "nav:referral")],
        [Markup.button.callback("💳 Credits", "nav:credits"), Markup.button.callback("❓ Help", "nav:help")]
    ]);
}

function gateLine(cmd) {
    const tag = cmd.tier === "premium" ? "PREMIUM" : "FREE";
    return `/${cmd.name} ✅ Active | ${tag}`;
}

function sectionText(title, list) {
    const lines = [`*${title}*`, ""];
    for (const c of list) {
        lines.push(`*${c.label}*`);
        lines.push(gateLine(c));
        lines.push("");
    }
    lines.push("[+] Adding more...");
    return lines.join("\n");
}

const killersText = () => sectionText("Killer Gates", Object.values(COMMANDS).filter((c) => c.category === "killer"));
const checkersText = () => sectionText("Checker Gates", Object.values(COMMANDS).filter((c) => c.category === "checker"));
const toolsText = () => sectionText("Other tools", Object.values(COMMANDS).filter((c) => c.category === "tool"));

const backKeyboard = () => Markup.inlineKeyboard([[Markup.button.callback("🔙 Back", "nav:main")]]);

module.exports = {
    welcomeText, mainKeyboard,
    killersText, killersKeyboard: backKeyboard,
    checkersText, checkersKeyboard: backKeyboard,
    toolsText, toolsKeyboard: backKeyboard
};
