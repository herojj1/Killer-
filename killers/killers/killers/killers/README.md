# NOVA bot

telegram bot — killers, checkers, tools, credits, premium tiers, referrals.

## install

    npm install
    pip install requests

## configure `config.js`

- `telegramBotToken` — from @BotFather
- `adminUsers` — tg usernames/ids of admins
- `authorisedUsers` — who can use the bot (empty = open to all)
- `adminNames` — shown to unauthorised users
- `creditPerKill: 5`, `creditPerCheck: 1`, `creditPerTool: 0`
- `startingCredits: 10`
- `referral.referrerBonus: 5`
- gateway credentials under `gateways.*`

## run

    npm start

## first-time setup in telegram

1. DM the bot `/start`
2. upload your banner GIF, then **reply to it** with `/setmedia welcome_gif`
3. repeat for `main`, `killers`, `checkers`, `tools` if you want per-screen banners
4. `/listmedia` to confirm what's saved

## commands

### killers (cost 5 credits, premium)
    /ke   — Stripe auth
    /kill — Authorize.Net auth
    /kg   — Square auth
    /dd   — Braintree auth

### checkers (cost 1 credit)
    /chk  — Braintree auth (free)
    /bt   — Braintree auth (premium)
    /auth — Authorize.Net auth (premium)
    /mc   — Stripe $0 (premium)
    /b3   — Braintree $40 (premium)
    /fp   — PayPal FlexPay $40 (premium)

### tools (free)
    /vbv <bin>
    /bin <bin>

### user
    /start /help /ping /menu /credits /history /creditlog
    /referral /ref /refs /reftop /gift <@u|id> <n>

### gate usage

    /ke 4242424242424242|12|27|123 10001
    /chk 4242424242424242|12|27|123 10001 3

first arg = cc, second = zip, optional third = rounds (default 4, max 6).

### admin
    /addcredit <id|@user> <amount> [reason]
    /removecredit <id|@user> <amount> [reason]
    /setcredit <id|@user> <amount>
    /give <id|@user> <amount>
    /zapcredits <id|@user>
    /settier <id|@user> free|premium
    /finduser <id|@user>
    /users [page]
    /creditlog <id|@user>
    /top
    /reftop
    /stats
    /broadcast <message>
    /setmedia <key>     (reply to a GIF/photo)
    /listmedia
    /resetref <id|@user>
    /unrefer <id|@user>

## storage

sqlite at `data/nova.db`. auto-migrates columns on startup.
tables: users, kills, credit_log, media.
delete the file to reset.

## adding a gateway

1. drop `<name>.py` into `killers/`
2. accept `--cc --zip --rounds`
3. print one JSON line on stdout:
   `{"gateway":"x","status":"approved|declined|error|timeout","attempts":N,"duration":S,"raw":"..."}`
4. register it in `config.js` under `gateways`
5. register a command in `bot/commands.js` pointing at it
6. restart — dispatcher picks it up
