const DARK_CSS = `
  :root { --bg: #1a1a2e; --fg: #e0e0e0; --link: #7eb8f7; --border: #333; --pre-bg: #0d0d1a; --h: #a0c4ff; }
`;
const LIGHT_CSS = `
  :root { --bg: #f5f5f5; --fg: #1a1a1a; --link: #0057b8; --border: #ccc; --pre-bg: #e8e8e8; --h: #003a8c; }
`;
const BASE_CSS = `
  body {
    background: var(--bg);
    color: var(--fg);
    font-family: system-ui, sans-serif;
    max-width: 860px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    line-height: 1.7;
  }
  nav {
    font-size: 0.85em;
    margin-bottom: 2rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--border);
    font-family: monospace;
  }
  nav a { color: var(--link); }
  h1 { font-size: 1.6rem; color: var(--h); margin: 1.25rem 0 0.5rem; }
  h2 { font-size: 1.25rem; color: var(--h); margin: 1rem 0 0.4rem; }
  h3 { font-size: 1rem; color: var(--h); margin: 0.75rem 0 0.3rem; }
  p { margin: 0.4rem 0; }
  p.link { margin: 0.2rem 0; }
  p.link::before { content: "⇒ "; color: var(--link); font-family: monospace; }
  p.link a { color: var(--link); text-decoration: none; }
  p.link a:hover { text-decoration: underline; }
  ul { margin: 0.4rem 0 0.4rem 1.5rem; }
  li { margin: 0.15rem 0; }
  pre {
    background: var(--pre-bg);
    border: 1px solid var(--border);
    padding: 1rem;
    border-radius: 4px;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 0.9em;
  }
  .error { color: #e07070; border: 1px solid #e07070; padding: 1rem; border-radius: 4px; }
`;

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function gemtextToHtml(text, theme) {
  const lines = text.split("\n");
  const parts = [];
  let inPre = false;
  let inList = false;

  for (const line of lines) {
    // Preformatted toggle
    if (line.startsWith("```")) {
      if (inList) { parts.push("</ul>"); inList = false; }
      if (inPre) {
        parts.push("</pre>");
        inPre = false;
      } else {
        const alt = line.slice(3).trim();
        parts.push(alt ? `<pre aria-label="${escapeHtml(alt)}">` : "<pre>");
        inPre = true;
      }
      continue;
    }

    if (inPre) {
      parts.push(escapeHtml(line));
      continue;
    }

    // Headings
    if (line.startsWith("### ")) {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push(`<h3>${escapeHtml(line.slice(4).trim())}</h3>`);
    } else if (line.startsWith("## ")) {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push(`<h2>${escapeHtml(line.slice(3).trim())}</h2>`);
    } else if (line.startsWith("# ")) {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push(`<h1>${escapeHtml(line.slice(2).trim())}</h1>`);

    // Links
    } else if (line.startsWith("=>")) {
      if (inList) { parts.push("</ul>"); inList = false; }
      const rest = line.slice(2).trim();
      const match = rest.match(/^(\S+)(?:\s+(.*))?$/);
      if (!match) continue;
      const href = match[1];
      const label = (match[2] || href).trim();

      let finalHref;
      if (href.startsWith("gemini://")) {
        finalHref = `/?url=${encodeURIComponent(href)}&theme=${theme}`;
      } else if (href.startsWith("http://") || href.startsWith("https://")) {
        finalHref = href;
      } else {
        // Relative URL — skip for now
        finalHref = "#";
      }
      parts.push(`<p class="link"><a href="${escapeHtml(finalHref)}">${escapeHtml(label)}</a></p>`);

    // List items
    } else if (line.startsWith("* ")) {
      if (!inList) { parts.push("<ul>"); inList = true; }
      parts.push(`<li>${escapeHtml(line.slice(2))}</li>`);

    // Blank line
    } else if (line.trim() === "") {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push("<br>");

    // Paragraph
    } else {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push(`<p>${escapeHtml(line)}</p>`);
    }
  }

  if (inList) parts.push("</ul>");
  if (inPre) parts.push("</pre>");

  return parts.join("\n");
}

function buildPage(content, theme, url, isError = false) {
  const themeCss = theme === "light" ? LIGHT_CSS : DARK_CSS;
  const otherTheme = theme === "light" ? "dark" : "light";
  const bodyContent = isError
    ? `<div class="error">${content}</div>`
    : content;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gemini Proxy — ${escapeHtml(url)}</title>
  <style>${themeCss}${BASE_CSS}</style>
</head>
<body>
  <nav>
    <a href="https://gemsearch.njb1966.com">← Search</a> &nbsp;|&nbsp;
    Viewing: <code>${escapeHtml(url)}</code> &nbsp;|&nbsp;
    <a href="?url=${encodeURIComponent(url)}&theme=${otherTheme}">
      Switch to ${otherTheme} mode
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
        buildPage(`Failed to fetch capsule: ${escapeHtml(err.message)}`, theme, geminiUrl, true),
        { status: 502, headers: { "Content-Type": "text/html;charset=utf-8" } }
      );
    }

    return new Response(
      buildPage(gemtextToHtml(upstreamText, theme), theme, geminiUrl),
      { status: 200, headers: { "Content-Type": "text/html;charset=utf-8" } }
    );
  },
};
