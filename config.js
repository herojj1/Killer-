module.exports = {
    botName: "NOVA",
    botTagline: "#1 CC Burner on Telegram ✅",

    telegramBotToken: process.env.TG_TOKEN || "PUT_YOUR_BOT_TOKEN_HERE",
    authorisedUsers: (process.env.TG_USERS || "").split(",").filter(Boolean),
    adminUsers: (process.env.TG_ADMINS || "").split(",").filter(Boolean),
    adminNames: (process.env.TG_ADMIN_NAMES || "").split(",").filter(Boolean),

    startingCredits: 10,
    creditPerKill: 5,
    creditPerCheck: 1,
    creditPerTool: 0,
    adminFreeUsage: true,

    referral: {
        enabled: true,
        referrerBonus: 5,
        refereeBonus: 0,
        maxReferralsPerUser: 0
    },

    cooldownMs: 15 * 1000,
    broadcastDelayMs: 60,

    pythonBin: process.env.PY_BIN || (process.platform === "win32" ? "python" : "python3"),
    killersDir: __dirname + "/killers",
    dataDir: __dirname + "/data",
    requestTimeoutMs: 120 * 1000,
    maxRounds: 6,
    defaultRounds: 4,

    gateways: {
        stripe: { apiKey: "sk_test_yourKeyHere" },
        paypal: {
            clientId: "YOUR_PAYPAL_CLIENT_ID",
            secret: "YOUR_PAYPAL_SECRET",
            sandbox: true
        },
        square: {
            accessToken: "YOUR_SQUARE_TOKEN",
            locationId: "YOUR_LOCATION_ID",
            sandbox: true
        },
        braintree: {
            merchantId: "YOUR_MERCHANT_ID",
            publicKey: "YOUR_PUBLIC_KEY",
            privateKey: "YOUR_PRIVATE_KEY",
            sandbox: true
        },
        authorize: {
            apiLoginId: "YOUR_API_LOGIN_ID",
            transactionKey: "YOUR_TRANSACTION_KEY",
            sandbox: true
        },
        sslcommerz: {
            storeId: "YOUR_STORE_ID",
            storePasswd: "YOUR_STORE_PASSWORD",
            sandbox: true
        }
    }
};
