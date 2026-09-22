function normalizeGeneratedHtml(content, minimumLength = 600, maximumLength = 200000) {
  let html = String(content || "");
  html = html.replace(/^```(?:html)?\s*\n?/i, "").replace(/\n?```\s*$/i, "");
  html = html.replace(/<\/?(?:html|body|head|style|meta)[^>]*>/gi, "").trim();
  if (!html.startsWith("<")) {
    const firstTag = html.indexOf("<");
    if (firstTag <= 0 || firstTag >= 200) throw new Error("模型输出不是 HTML 片段");
    html = html.slice(firstTag);
  }
  if (html.length < minimumLength) throw new Error(`模型输出过短：${html.length} 字符`);
  if (html.length > maximumLength) throw new Error(`模型输出过长：${html.length} 字符`);
  return html;
}

function createOpenAICompatibleLlm(options) {
  const {
    endpoint,
    apiKey,
    model,
    fetchImpl = globalThis.fetch,
    headers = {},
    temperature = 0.6,
    maxTokens = 10000,
    timeoutMs = 120000,
    minimumLength = 600,
    maximumLength = 200000,
    includeErrorBody = false,
    channel = model
  } = options || {};

  if (!endpoint || !model) throw new TypeError("endpoint 和 model 为必填项");
  if (typeof fetchImpl !== "function") throw new TypeError("当前运行时没有 fetch，请注入 fetchImpl");

  return async function callLlm(systemPrompt, userPrompt) {
    const requestHeaders = { "Content-Type": "application/json", ...headers };
    if (apiKey) requestHeaders.Authorization = `Bearer ${apiKey}`;
    const response = await fetchImpl(endpoint, {
      method: "POST",
      headers: requestHeaders,
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userPrompt }
        ],
        temperature,
        max_tokens: maxTokens,
        stream: false
      }),
      signal: AbortSignal.timeout(timeoutMs)
    });
    if (!response.ok) {
      const detail = includeErrorBody ? (await response.text().catch(() => "")).slice(0, 200) : "";
      throw new Error(`LLM API ${response.status}${detail ? `: ${detail}` : ""}`);
    }
    const data = await response.json();
    const content = data?.choices?.[0]?.message?.content;
    return { content: normalizeGeneratedHtml(content, minimumLength, maximumLength), channel };
  };
}

export { createOpenAICompatibleLlm, normalizeGeneratedHtml };
