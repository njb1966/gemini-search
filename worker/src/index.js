const DARK_CSS = `
  :root { --bg: #1a1a2e; --fg: #e0e0e0; --link: #7eb8f7; --border: #333; }
`;
const LIGHT_CSS = `
  :root { --bg: #f5f5f5; --fg: #1a1a1a; --link: #0057b8; --border: #ccc; }
`;
const BASE_CSS = `
  body {
    background: var(--bg);
    color: var(--fg);
    font-family: monospace;
    max-width: 900px;
    margin: 2rem auto;
    padding: 0 1rem;
    line-height: 1.6;
  }
  a { color: var(--link); }
  pre {
    white-space: pre-wrap;
    word-break: break-word;
    border: 1px solid var(--border);
    padding: 1rem;
    border-radius: 4px;
  }
  .error { color: #e07070; border: 1px solid #e07070; padding: 1rem; border-radius: 4px; }
  nav { margin-bottom: 1rem; font-size: 0.85em; }
`;

function buildPage(content, theme, url, isError = false) {
  const themeCss = theme === "light" ? LIGHT_CSS : DARK_CSS;
  const bodyContent = isError
    ? `<div class="error">${content}</div>`
    : `<pre>${content}</pre>`;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gemini Proxy — ${url}</title>
  <style>${themeCss}${BASE_CSS}</style>
</head>
<body>
  <nav>
    <a href="https://gemsearch.njb1966.com">← Search</a> &nbsp;|&nbsp;
    Viewing: <code>${url}</code> &nbsp;|&nbsp;
    <a href="?url=${encodeURIComponent(url)}&theme=${theme === "light" ? "dark" : "light"}">
      Switch to ${theme === "light" ? "dark" : "light"} mode
    </a>
  </nav>
  ${bodyContent}
</body>
</html>`;
}

export default {
  async fetch(request, env) {
    const reqUrl = new URL(request.url);
    const rawUrl = reqUrl.searchParams.get("url") || "";
    const theme = reqUrl.searchParams.get("theme") === "light" ? "light" : "dark";

    let geminiUrl;
    try {
      geminiUrl = decodeURIComponent(rawUrl);
    } catch {
      geminiUrl = rawUrl;
    }

    if (!geminiUrl.startsWith("gemini://")) {
      return new Response(
        buildPage("Invalid or missing <code>url</code> parameter. Must start with <code>gemini://</code>.", theme, geminiUrl, true),
        { status: 400, headers: { "Content-Type": "text/html;charset=utf-8" } }
      );
    }

    const gateway = (env.GEMINI_GATEWAY || "https://gemsearch.njb1966.com/api").replace(/\/$/, "");
    const proxyUrl = `${gateway}/proxy?url=${encodeURIComponent(geminiUrl)}`;

    let upstreamText;
    try {
      const resp = await fetch(proxyUrl, {
        headers: { Accept: "text/plain", "User-Agent": "gemini-mini-search-worker/1.0" },
      });
      if (!resp.ok) {
        throw new Error(`Gateway returned HTTP ${resp.status}`);
      }
      upstreamText = await resp.text();
    } catch (err) {
      return new Response(
        buildPage(`Failed to fetch capsule: ${err.message}`, theme, geminiUrl, true),
        { status: 502, headers: { "Content-Type": "text/html;charset=utf-8" } }
      );
    }

    // Escape HTML entities in the raw Gemini text for safe display in <pre>
    const escaped = upstreamText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    return new Response(
      buildPage(escaped, theme, geminiUrl),
      { status: 200, headers: { "Content-Type": "text/html;charset=utf-8" } }
    );
  },
};
