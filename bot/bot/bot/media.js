const db = require("./db");

const KEYS = {
    main: "main_banner",
    killers: "killers_banner",
    checkers: "checkers_banner",
    tools: "tools_banner",
    welcome_gif: "welcome_gif"
};

function getFileId(key) {
    const row = db.getMedia(key);
    return row ? row.file_id : null;
}

function remember(key, fileId) {
    db.setMedia(key, fileId);
}

module.exports = { KEYS, getFileId, remember };
