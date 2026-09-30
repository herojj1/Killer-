const moment = require("moment");

class Logger {
    static _log(c, t, color) {
        const ts = `\x1b[38;2;0;255;0m${moment().utcOffset("+05:30").format("DD.MM.YYYY HH:mm:ss")}\x1b[0m\t`;
        const tag = `\x1b[38;2;${color}m[${t.toUpperCase()}]\x1b[0m\t`;
        console.log(`${ts}${tag}${c}`);
    }
    static log(c)   { this._log(c, "log",   "255;255;255"); }
    static info(c)  { this._log(c, "info",  "0;200;255"); }
    static warn(c)  { this._log(c, "warn",  "255;160;0"); }
    static error(c) { this._log(c, "error", "255;0;0"); }
    static debug(c) { this._log(c, "debug", "255;80;105"); }
}

module.exports = Logger;
