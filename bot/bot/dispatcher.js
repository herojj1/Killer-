const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { killersDir, pythonBin, requestTimeoutMs, gateways } = require("../config");
const Logger = require("./logger");

const KNOWN = Object.keys(gateways);

function gatewayExists(name) {
    return KNOWN.includes(name) && fs.existsSync(path.join(killersDir, `${name}.py`));
}

function runKiller(gateway, cc, zip, rounds = 4) {
    return new Promise((resolve) => {
        if (!gatewayExists(gateway)) {
            return resolve({ status: "error", raw: `unknown gateway: ${gateway}`, attempts: 0, duration: 0 });
        }
        const script = path.join(killersDir, `${gateway}.py`);
        const proc = spawn(pythonBin, [script, "--cc", cc, "--zip", zip, "--rounds", String(rounds)], {
            cwd: killersDir,
            env: process.env
        });

        let out = "", err = "", done = false;
        const finish = (payload) => {
            if (done) return;
            done = true;
            try { proc.kill("SIGKILL"); } catch (_) {}
            resolve(payload);
        };

        proc.stdout.on("data", (d) => (out += d.toString()));
        proc.stderr.on("data", (d) => { err += d.toString(); Logger.debug(`[${gateway}] ${d.toString().trim()}`); });
        proc.on("error", (e) => finish({ status: "error", raw: `spawn: ${e.message}`, attempts: 0, duration: 0 }));
        proc.on("close", (code) => {
            const line = out.trim().split("\n").filter(Boolean).pop();
            if (!line) return finish({ status: "error", raw: err.slice(0, 400) || `exit ${code}`, attempts: 0, duration: 0 });
            try { finish(JSON.parse(line)); }
            catch (_) { finish({ status: "error", raw: `bad json: ${line.slice(0, 300)}`, attempts: 0, duration: 0 }); }
        });
        setTimeout(() => finish({ status: "timeout", raw: `timeout ${requestTimeoutMs}ms`, attempts: 0, duration: requestTimeoutMs / 1000 }), requestTimeoutMs);
    });
}

module.exports = { runKiller, gatewayExists, KNOWN };
