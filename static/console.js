function log(msg, isError = false) {
    const term = document.getElementById("terminal");
    if (!term) return;
    const time = new Date().toLocaleTimeString();
    const color = isError ? "var(--error-color)" : "#38bdf8";
    term.innerHTML += `<div style="color: ${color}">[${time}] ${msg}</div>`;
    term.scrollTop = term.scrollHeight;
}

function removeRow(btn) {
    btn.parentElement.remove();
}

function getApiUrl(path) {
    if (window.location.protocol === "file:") {
        return "http://127.0.0.1:8000" + path;
    }
    return path;
}

const originalFetch = window.fetch;
window.fetch = function (input, init) {
    if (typeof input === "string" && input.startsWith("/")) {
        input = getApiUrl(input);
    }
    return originalFetch(input, init);
};
