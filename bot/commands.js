const {
    creditPerKill, creditPerCheck, creditPerTool
} = require("../config");

const COMMANDS = {
    ke:   { name: "ke",   label: "Kill 1",  category: "killer",  gateway: "stripe",    cost: creditPerKill,  tier: "premium", takesInput: true,  desc: "Stripe auth" },
    kill: { name: "kill", label: "Kill 2",  category: "killer",  gateway: "authorize", cost: creditPerKill,  tier: "premium", takesInput: true,  desc: "Authorize.Net auth" },
    kg:   { name: "kg",   label: "Kill 3",  category: "killer",  gateway: "square",    cost: creditPerKill,  tier: "premium", takesInput: true,  desc: "Square auth" },
    dd:   { name: "dd",   label: "Kill 4",  category: "killer",  gateway: "braintree", cost: creditPerKill,  tier: "premium", takesInput: true,  desc: "Braintree auth" },

    chk:  { name: "chk",  label: "Braintree Auth 1", category: "checker", gateway: "braintree", cost: creditPerCheck, tier: "free",    takesInput: true,  desc: "Free Braintree auth check" },
    bt:   { name: "bt",   label: "Braintree Auth 2", category: "checker", gateway: "braintree", cost: creditPerCheck, tier: "premium", takesInput: true,  desc: "Braintree auth" },
    auth: { name: "auth", label: "Auth 3",           category: "checker", gateway: "authorize", cost: creditPerCheck, tier: "premium", takesInput: true,  desc: "Authorize.Net auth" },
    mc:   { name: "mc",   label: "Auth $0",          category: "checker", gateway: "stripe",    cost: creditPerCheck, tier: "premium", takesInput: true,  desc: "Stripe $0 auth" },
    b3:   { name: "b3",   label: "Braintree $40",    category: "checker", gateway: "braintree", cost: creditPerCheck, tier: "premium", takesInput: true,  desc: "Braintree $40 charge" },
    fp:   { name: "fp",   label: "FlexPay $40",      category: "checker", gateway: "paypal",    cost: creditPerCheck, tier: "premium", takesInput: true,  desc: "PayPal FlexPay $40" },

    vbv:  { name: "vbv",  label: "VBV Lookup",       category: "tool", gateway: null, cost: creditPerTool, tier: "free", takesInput: false, desc: "VBV lookup" },
    bin:  { name: "bin",  label: "BIN Lookup",       category: "tool", gateway: null, cost: creditPerTool, tier: "free", takesInput: true,  desc: "BIN lookup" }
};

function checkAccess(user, cmd) {
    if (!cmd) return { ok: false, reason: "unknown command" };
    if (cmd.tier === "premium" && user.tier !== "premium") {
        return { ok: false, reason: "premium_required", message: "this command is *PREMIUM* only. contact an admin to upgrade." };
    }
    return { ok: true };
}

module.exports = { COMMANDS, checkAccess };
