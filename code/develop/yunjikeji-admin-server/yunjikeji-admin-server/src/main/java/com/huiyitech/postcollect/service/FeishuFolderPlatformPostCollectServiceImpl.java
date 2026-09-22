package com.huiyitech.postcollect.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.aiconfig.AiSceneCodes;
import com.huiyitech.knowledge.dal.DeepSeekOpenAiClient;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentItemDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.FeishuPostDocumentDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Element;
import org.springframework.stereotype.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.util.StringUtils;

import javax.annotation.Resource;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.HashSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

/**
 * Reads publicly accessible Feishu docx pages and asks the active
 * database-backed OpenAI-compatible model to semantically extract the jobs
 * newly added in that report. The upstream report is responsible for
 * deduplication.
 *
 * <p>The folder listing endpoint is deliberately not authenticated. If Feishu
 * requires a login for the listing, the task fails with an audit record instead
 * of reusing a browser session or pretending that the folder was fully read.</p>
 */
@Service
public class FeishuFolderPlatformPostCollectServiceImpl extends AbstractPostPlatformCollectService {

    private static final Logger log = LoggerFactory.getLogger(FeishuFolderPlatformPostCollectServiceImpl.class);

    private static final String FOLDER_HOST = "https://zcn5jf36q4fv.feishu.cn";
    private static final String FOLDER_LIST_PATH = "/space/api/explorer/v3/children/list/";
    private static final String BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            + " (KHTML, like Gecko) Chrome/125 Safari/537.36";
    private static final Pattern DOC_LINK = Pattern.compile("/docx/([A-Za-z0-9]+)");
    private static final Pattern DOCUMENT_DATE = Pattern.compile(
            "(?<!\\d)(20\\d{2})[-/.年](0?[1-9]|1[0-2])[-/.月](0?[1-9]|[12]\\d|3[01])日?(?!\\d)");
    private static final String INITIAL_ATTRIBUTED_TEXTS = "\"initialAttributedTexts\"";
    private static final String TEXT_FIELD = "\"text\"";
    private static final String LINK_FIELD = "\"link\"";
    private static final String DETAIL_LINK_PREFIX = "[查看详情](";
    private static final String JOB_EXTRACTION_PROMPT = "你是招聘日报岗位信息结构化抽取器。输入是完整的飞书招聘日报正文，"
            + "请依靠文档语义和上下文识别本日报中代表‘今日新增’或‘今日首次出现’的岗位集合，再将这些岗位完整转换为 jobs 数组。"
            + "不要依赖固定标题、固定行号、正则规则或文档中声明的数量；不要把更新岗位、持续在招、历史岗位、汇总说明或其他章节中的岗位纳入结果。"
            + "不同日报的标题和排版可能不同，必须以实际语义判断；如果文档没有明确的今日新增岗位，返回空 jobs 数组。"
            + "不要遗漏、合并或重复岗位，不要补充输入之外的岗位。输出前请自行复核完整性。"
            + "只根据输入事实输出严格 JSON，不要 Markdown，不要解释。"
            + "顶层必须是 {\"jobs\":[],\"ignored\":[],\"warnings\":[]}。"
            + "jobs 每项必须包含 name,company_name,source_code,external_post_id,salary_range,work_area,"
            + "publish_date,detail_url,status,source_text。publish_date 无需推断，可传 null，后端会按日报文档日期统一填写；"
            + "其他缺失字段用 null；无法识别 source_code 时使用 feishu；"
            + "无法识别 external_post_id 时传 null。不得补写输入没有的事实。";

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Resource
    private DeepSeekOpenAiClient aiClient;
    @Resource
    private FeishuPostCollectionAuditService auditService;

    @Override
    public String getPlatformSource() {
        return "feishu_folder";
    }

    @Override
    public List<PostCollectDO> collect(PostCollectTaskDO task) {
        String source = task == null ? null : task.getCollectionKey();
        if (!StringUtils.hasText(source)) {
            throw invalidParamException("飞书岗位采集目标不能为空");
        }
        String folderToken = folderToken(source);
        FeishuHttpSession httpSession = new FeishuHttpSession();
        Long runId = auditService.startRun(task.getId(), folderToken, "system", 0);
        try {
            log.info("飞书目录采集开始: taskId={}, runId={}, folderToken={}", task.getId(), runId, folderToken);
            List<DocumentRef> documents = listDocuments(source, httpSession);
            auditService.updateDocumentsSeen(runId, documents.size(), "system");
            log.info("飞书目录清单读取完成: taskId={}, runId={}, documentsSeen={}",
                    task.getId(), runId, documents.size());
            List<PostCollectDO> result = new ArrayList<>();
            for (DocumentRef document : documents) {
                try {
                    result.addAll(collectDocument(task, runId, folderToken, document, httpSession));
                } catch (Throwable ex) {
                    String errorMessage = failureMessage(ex);
                    try {
                        Long documentDbId = auditService.upsertDocument(runId, folderToken, document.documentId,
                                document.documentId, document.url, null, null, "system", 0);
                        auditService.markDocumentFailed(runId, documentDbId, errorMessage, "system");
                    } catch (Throwable auditEx) {
                        log.error("飞书岗位文档失败状态写回异常: runId={}, documentId={}",
                                runId, document.documentId, auditEx);
                        ex.addSuppressed(auditEx);
                    }
                    log.error("飞书岗位文档处理失败: runId={}, documentId={}", runId, document.documentId, ex);
                    if (ex instanceof Error) {
                        throw (Error) ex;
                    }
                }
            }
            if (result.isEmpty() && documents.stream().allMatch(document -> {
                FeishuPostDocumentDO state = auditService.findDocument(folderToken, document.documentId);
                return state != null && "FAILED".equals(state.getStatus());
            })) {
                throw new IllegalStateException("飞书目录中的文档均处理失败，请查看采集审计明细");
            }
            log.info("飞书目录采集完成: taskId={}, runId={}, extractedPosts={}", task.getId(), runId, result.size());
            return result;
        } catch (Throwable ex) {
            String errorMessage = failureMessage(ex);
            try {
                auditService.fail(errorMessage, "system");
            } catch (Throwable auditEx) {
                log.error("飞书目录失败状态写回异常: taskId={}, runId={}", task.getId(), runId, auditEx);
                ex.addSuppressed(auditEx);
            }
            log.error("飞书目录采集异常: taskId={}, runId={}", task.getId(), runId, ex);
            rethrow(ex);
            return Collections.emptyList(); // unreachable; keeps the compiler aware that rethrow always exits.
        }
    }

    private List<DocumentRef> listDocuments(String source, FeishuHttpSession httpSession) {
        Matcher direct = DOC_LINK.matcher(source);
        if (source.contains("/docx/") && direct.find()) {
            return Collections.singletonList(new DocumentRef(direct.group(1), source));
        }
        String folderUrl = source.startsWith("http") ? source : FOLDER_HOST + "/drive/folder/" + source;
        // The folder HTML contains many embedded links from Feishu itself. Only the
        // public explorer response is an authoritative list of direct children.
        httpSession.get(folderUrl, true);
        List<DocumentRef> documents = new ArrayList<>();
        Set<String> documentIds = new HashSet<>();
        String lastLabel = null;
        boolean hasMore;
        int page = 0;
        do {
            page++;
            if (page > 100) {
                throw new IllegalStateException("飞书目录分页超过安全上限");
            }
            JsonNode root = readJson(httpSession.get(buildFolderListUrl(folderToken(folderUrl), lastLabel), false));
            if (root.path("code").asInt(-1) != 0) {
                String message = root.path("msg").asText("unknown error");
                throw new IllegalStateException("飞书目录接口不可读：" + message);
            }
            JsonNode data = root.path("data");
            JsonNode nodes = data.path("entities").path("nodes");
            if (nodes.isObject()) {
                java.util.Iterator<JsonNode> iterator = nodes.elements();
                while (iterator.hasNext()) {
                    JsonNode node = iterator.next();
                    if (node.path("type").asInt(-1) != 22 || node.path("delete_flag").asInt(0) != 0) {
                        continue;
                    }
                    String documentId = text(node, "obj_token");
                    String url = text(node, "url");
                    if (!StringUtils.hasText(documentId) || !documentIds.add(documentId)) {
                        continue;
                    }
                    documents.add(new DocumentRef(documentId,
                            StringUtils.hasText(url) ? url : FOLDER_HOST + "/docx/" + documentId));
                }
            }
            hasMore = data.path("has_more").asBoolean(false);
            String nextLabel = text(data, "last_label");
            if (hasMore && !StringUtils.hasText(nextLabel)) {
                throw new IllegalStateException("飞书目录接口缺少下一页游标");
            }
            if (hasMore && nextLabel.equals(lastLabel)) {
                throw new IllegalStateException("飞书目录接口返回重复分页游标");
            }
            lastLabel = nextLabel;
        } while (hasMore);
        if (documents.isEmpty()) {
            throw new IllegalStateException("飞书目录公开清单为空，或目录未公开文档内容");
        }
        return documents;
    }

    private List<PostCollectDO> collectDocument(PostCollectTaskDO task, Long runId, String folderToken,
                                                DocumentRef document, FeishuHttpSession httpSession) {
        FeishuPostDocumentDO previous = auditService.findDocumentIncludingDeleted(folderToken, document.documentId);
        if (hasSuccessfulReadRecord(previous)) {
            // Only a completed read suppresses another request. Failed/incomplete records must remain retryable.
            return Collections.emptyList();
        }
        log.info("飞书岗位新文档开始处理: runId={}, documentId={}", runId, document.documentId);
        String html = httpSession.get(document.url, true);
        log.info("飞书岗位新文档正文读取完成: runId={}, documentId={}, contentLength={}",
                runId, document.documentId, html.length());
        DocumentContent content = parseDocument(document.documentId, html);
        log.info("飞书岗位新文档正文解析完成: runId={}, documentId={}, title={}, lines={}",
                runId, document.documentId, content.title, content.lines.size());
        Long documentDbId = auditService.upsertDocument(runId, folderToken, document.documentId,
                content.title, document.url, content.revision, null, "system", 0);
        log.info("飞书岗位新文档 AI 提取开始: runId={}, documentId={}", runId, document.documentId);
        List<PostCollectDO> posts = extractJobsWithAi(document.documentId, content.title, content.lines,
                runId, documentDbId);
        log.info("飞书岗位新文档 AI 提取完成: runId={}, documentId={}, extractedPosts={}",
                runId, document.documentId, posts.size());
        auditService.updateDocumentExtractedCount(documentDbId, posts.size(), "system");
        if (posts.isEmpty()) {
            auditService.markDocumentCollectedEmpty(runId, documentDbId, "system");
        }
        return posts;
    }

    boolean hasSuccessfulReadRecord(FeishuPostDocumentDO document) {
        return document != null
                && !Boolean.TRUE.equals(document.getDeleted())
                && Boolean.TRUE.equals(document.getCollected());
    }

    private String failureMessage(Throwable throwable) {
        if (throwable == null) {
            return "unknown error";
        }
        String message = throwable.getMessage();
        return StringUtils.hasText(message) ? message : throwable.getClass().getName();
    }

    private void rethrow(Throwable throwable) {
        if (throwable instanceof Error) {
            throw (Error) throwable;
        }
        if (throwable instanceof RuntimeException) {
            throw (RuntimeException) throwable;
        }
        throw new IllegalStateException(throwable);
    }

    List<PostCollectDO> extractJobsWithAi(String documentId, String documentTitle, List<String> lines,
                                          Long runId, Long documentDbId) {
        String documentPublishDate = resolveDocumentPublishDate(documentTitle, lines);
        String userPrompt = "文档ID：" + documentId + "\n文档名称：" + documentTitle
                + "\n\n完整招聘日报正文：\n<document>\n" + String.join("\n", lines) + "\n</document>";
        RuntimeException lastError = null;
        AiExtraction extraction = null;
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                String raw = aiClient.completeRequired(AiSceneCodes.JOB_EXTRACTION, JOB_EXTRACTION_PROMPT, userPrompt);
                if (!StringUtils.hasText(raw)) {
                    throw new IllegalStateException("岗位提取模型返回空内容");
                }
                extraction = parseAiJobs(documentId, runId, documentDbId, documentPublishDate, raw);
                break;
            } catch (RuntimeException ex) {
                lastError = ex;
                log.warn("飞书岗位 AI 提取失败: documentId={}, attempt={}, error={}",
                        documentId, attempt, ex.getMessage());
            }
        }
        if (extraction == null) {
            throw new IllegalStateException("飞书岗位 AI 提取失败", lastError);
        }
        for (FeishuPostDocumentItemDO item : extraction.items) {
            auditService.saveItem(item, "system");
        }
        return extraction.posts;
    }

    String resolveDocumentPublishDate(String documentTitle) {
        if (!StringUtils.hasText(documentTitle)) {
            throw new IllegalStateException("飞书日报文档名称为空，无法确定岗位发布时间");
        }
        Matcher matcher = DOCUMENT_DATE.matcher(documentTitle);
        if (!matcher.find()) {
            throw new IllegalStateException("飞书日报文档名称缺少有效日期，无法确定岗位发布时间：" + documentTitle);
        }
        try {
            return LocalDate.of(Integer.parseInt(matcher.group(1)), Integer.parseInt(matcher.group(2)),
                    Integer.parseInt(matcher.group(3))).toString();
        } catch (DateTimeException ex) {
            throw new IllegalStateException("飞书日报文档名称包含无效日期，无法确定岗位发布时间：" + documentTitle,
                    ex);
        }
    }

    private String resolveDocumentPublishDate(String documentTitle, List<String> lines) {
        try {
            return resolveDocumentPublishDate(documentTitle);
        } catch (IllegalStateException titleError) {
            if (lines != null) {
                for (String line : lines) {
                    Matcher matcher = DOCUMENT_DATE.matcher(line == null ? "" : line);
                    if (!matcher.find()) {
                        continue;
                    }
                    try {
                        return LocalDate.of(Integer.parseInt(matcher.group(1)), Integer.parseInt(matcher.group(2)),
                                Integer.parseInt(matcher.group(3))).toString();
                    } catch (DateTimeException ignored) {
                        // Continue through the complete body. The original title error remains most useful otherwise.
                    }
                }
            }
            throw titleError;
        }
    }

    private AiExtraction parseAiJobs(String documentId, Long runId, Long documentDbId,
                                     String documentPublishDate, String raw) {
        JsonNode root = parseJson(raw);
        JsonNode jobs = root.path("jobs");
        if (!jobs.isArray()) {
            throw new IllegalStateException("岗位提取模型结果缺少 jobs 数组");
        }
        List<PostCollectDO> posts = new ArrayList<>();
        List<FeishuPostDocumentItemDO> items = new ArrayList<>();
        int index = 0;
        for (JsonNode node : jobs) {
            index++;
            String name = text(node, "name");
            if (!StringUtils.hasText(name)) {
                throw new IllegalStateException("岗位提取模型返回了缺少 name 的岗位项，序号：" + index);
            }
            String detailUrl = limitNullable(text(node, "detail_url"), 500);
            String externalId = text(node, "external_post_id");
            if (!StringUtils.hasText(externalId)) {
                externalId = "feishu:" + documentId + ":" + index;
            }
            PostCollectDO post = PostCollectDO.builder()
                    .name(limit(name, 100))
                    .companyName(limitNullable(text(node, "company_name"), 100))
                    .sourceCode(limit(resolveSourceCode(text(node, "source_code"), detailUrl), 20))
                    .externalPostId(limit(externalId, 100))
                    .salaryRange(limitNullable(text(node, "salary_range"), 100))
                    .workArea(limitNullable(text(node, "work_area"), 100))
                    .publishDate(documentPublishDate)
                    .detailUrl(detailUrl)
                    .status(Boolean.TRUE)
                    .build();
            post.setDeleted(Boolean.FALSE);
            posts.add(post);
            FeishuPostDocumentItemDO item = FeishuPostDocumentItemDO.builder()
                    .runId(runId)
                    .documentId(documentDbId)
                    .itemIndex(index)
                    .sourceText(limitNullable(text(node, "source_text"), 4000))
                    .aiRawJson(node.toString())
                    .name(post.getName())
                    .companyName(post.getCompanyName())
                    .sourceCode(post.getSourceCode())
                    .externalPostId(post.getExternalPostId())
                    .salaryRange(post.getSalaryRange())
                    .workArea(post.getWorkArea())
                    .publishDate(post.getPublishDate())
                    .detailUrl(post.getDetailUrl())
                    .status("EXTRACTED")
                    .build();
            items.add(item);
        }
        return new AiExtraction(posts, items);
    }

    private DocumentContent parseDocument(String documentId, String html) {
        List<String> lines = extractDocumentLines(html);
        if (lines.isEmpty()) {
            throw new IllegalStateException("飞书文档正文为空或仅支持浏览器端渲染：" + documentId);
        }
        return new DocumentContent(extractDocumentTitle(documentId, html), extractDocumentRevision(documentId, html),
                lines);
    }

    /**
     * Reads every SSR text object with JSON boundaries. It intentionally avoids regex and fixed windows because
     * either can silently lose a long Feishu block when the provider changes its rendered page size.
     */
    List<String> extractDocumentLines(String html) {
        if (!StringUtils.hasText(html)) {
            return Collections.emptyList();
        }
        List<String> lines = extractDirectDocumentLines(html);
        if (!lines.isEmpty()) {
            return lines;
        }
        lines = extractEscapedDocumentLines(html);
        return lines.isEmpty() ? extractRenderedDocumentLines(html) : lines;
    }

    private List<String> extractDirectDocumentLines(String html) {
        List<String> lines = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        int cursor = 0;
        while ((cursor = html.indexOf(INITIAL_ATTRIBUTED_TEXTS, cursor)) >= 0) {
            int nextMarker = html.indexOf(INITIAL_ATTRIBUTED_TEXTS, cursor + INITIAL_ATTRIBUTED_TEXTS.length());
            int segmentEnd = nextMarker < 0 ? html.length() : nextMarker;
            int textField = html.indexOf(TEXT_FIELD, cursor + INITIAL_ATTRIBUTED_TEXTS.length());
            if (textField < 0 || textField >= segmentEnd) {
                cursor += INITIAL_ATTRIBUTED_TEXTS.length();
                continue;
            }
            int textObjectStart = html.indexOf('{', textField + TEXT_FIELD.length());
            int textObjectEnd = balancedJsonEnd(html, textObjectStart);
            if (textObjectStart < 0 || textObjectEnd <= textObjectStart || textObjectEnd > segmentEnd) {
                cursor += INITIAL_ATTRIBUTED_TEXTS.length();
                continue;
            }
            try {
                JsonNode textObject = objectMapper.readTree(html.substring(textObjectStart, textObjectEnd));
                String text = joinTextFragments(textObject);
                List<String> links = extractBlockLinks(html, cursor, segmentEnd);
                String line = textWithLinks(text, links);
                if (StringUtils.hasText(line) && seen.add(line)) {
                    lines.add(line);
                }
            } catch (Exception ex) {
                log.debug("忽略不可解析的飞书 SSR 正文块: position={}", cursor, ex);
            }
            cursor = textObjectEnd;
        }
        return lines;
    }

    private List<String> extractEscapedDocumentLines(String html) {
        int cursor = 0;
        while (cursor < html.length()) {
            int stringStart = html.indexOf('"', cursor);
            if (stringStart < 0) {
                return Collections.emptyList();
            }
            int stringEnd = jsonStringEnd(html, stringStart);
            if (stringEnd < 0) {
                return Collections.emptyList();
            }
            String decoded = readJsonString(html, stringStart);
            if (StringUtils.hasText(decoded) && decoded.contains(INITIAL_ATTRIBUTED_TEXTS)) {
                List<String> lines = extractDirectDocumentLines(decoded);
                if (!lines.isEmpty()) {
                    return lines;
                }
            }
            cursor = stringEnd + 1;
        }
        return Collections.emptyList();
    }

    /**
     * Some Feishu edges stream the rendered SSR DOM before the embedded JSON is complete.
     * The document body remains available as ace-line nodes, so read that DOM rather than
     * treating a partial JSON payload as an empty document.
     */
    private List<String> extractRenderedDocumentLines(String html) {
        List<String> lines = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (Element lineElement : Jsoup.parse(html).select(".ace-line")) {
            String text = lineElement.text();
            List<String> links = new ArrayList<>();
            for (Element link : lineElement.select("a[href]")) {
                String href = link.attr("href");
                if (href.startsWith("https://") || href.startsWith("http://")) {
                    links.add(href);
                }
            }
            String line = textWithLinks(text, links);
            if (StringUtils.hasText(line) && seen.add(line)) {
                lines.add(line);
            }
        }
        return lines;
    }

    private String joinTextFragments(JsonNode textObject) {
        if (textObject == null || !textObject.isObject()) {
            return "";
        }
        StringBuilder text = new StringBuilder();
        java.util.Iterator<JsonNode> values = textObject.elements();
        while (values.hasNext()) {
            JsonNode value = values.next();
            if (value.isTextual()) {
                text.append(value.asText());
            }
        }
        return text.toString();
    }

    private List<String> extractBlockLinks(String html, int start, int end) {
        Set<String> links = new java.util.LinkedHashSet<>();
        int cursor = start;
        while ((cursor = html.indexOf(LINK_FIELD, cursor)) >= 0 && cursor < end) {
            int valueStart = html.indexOf('"', cursor + LINK_FIELD.length());
            if (valueStart < 0 || valueStart >= end) {
                break;
            }
            String value = readJsonString(html, valueStart);
            if (StringUtils.hasText(value) && (value.startsWith("https://") || value.startsWith("http://"))) {
                links.add(value);
            }
            cursor = valueStart + 1;
        }
        return new ArrayList<>(links);
    }

    private String textWithLinks(String text, List<String> links) {
        if (!StringUtils.hasText(text)) {
            return "";
        }
        StringBuilder result = new StringBuilder(text);
        for (String link : links) {
            result.append('\n').append(DETAIL_LINK_PREFIX).append(link).append(')');
        }
        return result.toString();
    }

    private int balancedJsonEnd(String value, int start) {
        if (start < 0 || start >= value.length() || value.charAt(start) != '{') {
            return -1;
        }
        int depth = 0;
        boolean inString = false;
        boolean escaped = false;
        for (int index = start; index < value.length(); index++) {
            char current = value.charAt(index);
            if (inString) {
                if (escaped) {
                    escaped = false;
                } else if (current == '\\') {
                    escaped = true;
                } else if (current == '"') {
                    inString = false;
                }
                continue;
            }
            if (current == '"') {
                inString = true;
            } else if (current == '{') {
                depth++;
            } else if (current == '}' && --depth == 0) {
                return index + 1;
            }
        }
        return -1;
    }

    private String readJsonString(String value, int start) {
        int end = jsonStringEnd(value, start);
        if (end < 0) {
            return null;
        }
        try {
            return objectMapper.readValue(value.substring(start, end + 1), String.class);
        } catch (Exception ignored) {
            return null;
        }
    }

    private int jsonStringEnd(String value, int start) {
        if (start < 0 || start >= value.length() || value.charAt(start) != '"') {
            return -1;
        }
        boolean escaped = false;
        for (int index = start + 1; index < value.length(); index++) {
            char current = value.charAt(index);
            if (escaped) {
                escaped = false;
            } else if (current == '\\') {
                escaped = true;
            } else if (current == '"') {
                return index;
            }
        }
        return -1;
    }

    private String extractDocumentTitle(String documentId, String html) {
        String fallback = null;
        int cursor = 0;
        while ((cursor = html.indexOf("\"title\"", cursor)) >= 0) {
            int colon = html.indexOf(':', cursor + "\"title\"".length());
            int valueStart = colon < 0 ? -1 : html.indexOf('"', colon + 1);
            String value = readJsonString(html, valueStart);
            if (StringUtils.hasText(value) && value.contains("招聘")) {
                if (DOCUMENT_DATE.matcher(value).find()) {
                    return value;
                }
                if (fallback == null) {
                    fallback = value;
                }
            }
            cursor += "\"title\"".length();
        }
        return fallback == null ? documentId : fallback;
    }

    private String extractDocumentRevision(String documentId, String html) {
        String pattern = "\"" + Pattern.quote(documentId) + "\":\\{\"id\":\""
                + Pattern.quote(documentId) + "\",\"version\":(\\d+)";
        Matcher matcher = Pattern.compile(pattern).matcher(html);
        return matcher.find() ? matcher.group(1) : null;
    }

    private JsonNode parseJson(String raw) {
        String value = raw.trim().replaceFirst("^```(?:json)?\\s*", "").replaceFirst("\\s*```$", "");
        int start = value.indexOf('{');
        int end = value.lastIndexOf('}');
        if (start < 0 || end <= start) {
            throw new IllegalStateException("GPT 返回内容不是 JSON");
        }
        try {
            return objectMapper.readTree(value.substring(start, end + 1));
        } catch (Exception ex) {
            throw new IllegalStateException("GPT 岗位 JSON 解析失败", ex);
        }
    }

    private String resolveSourceCode(String configuredSource, String detailUrl) {
        String source = configuredSource == null ? "" : configuredSource.trim().toLowerCase();
        if (source.contains("智联") || "zhaopin".equals(source) || "zhilian".equals(source)) return "zhilian";
        if (source.contains("猎聘") || "liepin".equals(source)) return "liepin";
        if (source.contains("国聘") || "guopin".equals(source) || "iguopin".equals(source)) return "guopin";
        if (source.contains("前程") || "51job".equals(source) || "051job".equals(source)) return "51job";
        if (source.contains("boss") || source.contains("直聘")) return "boss_zhipin";
        String url = detailUrl == null ? "" : detailUrl.toLowerCase();
        if (url.contains("zhaopin")) return "zhilian";
        if (url.contains("liepin")) return "liepin";
        if (url.contains("iguopin")) return "guopin";
        if (url.contains("51job") || url.contains("051job")) return "51job";
        if (url.contains("zhipin")) return "boss_zhipin";
        return "feishu";
    }

    private String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        return value == null || value.isNull() ? null : value.asText();
    }

    private String limitNullable(String value, int max) {
        return StringUtils.hasText(value) ? limit(value, max) : null;
    }

    private String limit(String value, int max) {
        if (value == null) return "";
        return value.length() <= max ? value : value.substring(0, max);
    }

    private String sha256(List<String> lines) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(String.join("\n", lines).getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder();
            for (byte value : digest) result.append(String.format("%02x", value));
            return result.toString();
        } catch (Exception ex) {
            throw new IllegalStateException("无法计算飞书文档摘要", ex);
        }
    }

    private String get(String url) {
        return new FeishuHttpSession().get(url, true);
    }

    private JsonNode readJson(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (Exception ex) {
            throw new IllegalStateException("飞书目录接口返回了不可识别的数据", ex);
        }
    }

    private String buildFolderListUrl(String token, String lastLabel) {
        StringBuilder url = new StringBuilder(FOLDER_HOST).append(FOLDER_LIST_PATH)
                .append("?thumbnail_width=1028")
                .append("&thumbnail_height=1028")
                .append("&thumbnail_policy=4")
                .append("&obj_type=0&obj_type=2&obj_type=22&obj_type=44&obj_type=3")
                .append("&obj_type=30&obj_type=8&obj_type=11&obj_type=12&obj_type=84")
                .append("&obj_type=123&obj_type=124")
                .append("&length=50&asc=1&rank=5")
                .append("&token=").append(encodeQueryParam(token))
                .append("&thumbnail_mode=0");
        if (StringUtils.hasText(lastLabel)) {
            url.append("&last_label=").append(encodeQueryParam(lastLabel));
        }
        return url.toString();
    }

    private String encodeQueryParam(String value) {
        try {
            return URLEncoder.encode(value, StandardCharsets.UTF_8.name());
        } catch (Exception ex) {
            throw new IllegalStateException("飞书目录分页参数编码失败", ex);
        }
    }

    private String folderToken(String source) {
        Matcher matcher = Pattern.compile("/folder/([^/?#]+)").matcher(source);
        if (matcher.find()) return matcher.group(1);
        return source.length() > 128 ? source.substring(0, 128) : source;
    }

    private static final class DocumentRef {
        private final String documentId;
        private final String url;

        private DocumentRef(String documentId, String url) {
            this.documentId = documentId;
            this.url = url;
        }
    }

    private static final class DocumentContent {
        private final String title;
        private final String revision;
        private final List<String> lines;

        private DocumentContent(String title, String revision, List<String> lines) {
            this.title = title;
            this.revision = revision;
            this.lines = lines;
        }
    }

    private static final class AiExtraction {
        private final List<PostCollectDO> posts;
        private final List<FeishuPostDocumentItemDO> items;

        private AiExtraction(List<PostCollectDO> posts, List<FeishuPostDocumentItemDO> items) {
            this.posts = posts;
            this.items = items;
        }
    }

    /**
     * Feishu creates a short-lived anonymous visitor session before allowing the
     * public explorer endpoint to be called. This session is local to one run;
     * no user login cookie is accepted or persisted.
     */
    private static final class FeishuHttpSession {
        private static final int MAX_REDIRECTS = 8;
        private final Map<String, String> cookies = new LinkedHashMap<>();

        private String get(String url, boolean html) {
            String currentUrl = url;
            for (int redirect = 0; redirect <= MAX_REDIRECTS; redirect++) {
                HttpURLConnection connection = null;
                try {
                    connection = (HttpURLConnection) new URL(currentUrl).openConnection();
                    connection.setInstanceFollowRedirects(false);
                    connection.setRequestMethod("GET");
                    connection.setConnectTimeout(20000);
                    connection.setReadTimeout(30000);
                    connection.setRequestProperty("User-Agent", BROWSER_USER_AGENT);
                    connection.setRequestProperty("Accept", html ? "text/html" : "application/json, text/plain, */*");
                    connection.setRequestProperty("Referer", currentUrl);
                    if (!cookies.isEmpty()) {
                        connection.setRequestProperty("Cookie", cookieHeader());
                    }
                    if (!html) {
                        connection.setRequestProperty("x-lsc-terminal", "web");
                        connection.setRequestProperty("x-lsc-version", "1");
                        connection.setRequestProperty("doc-platform", "web");
                        connection.setRequestProperty("doc-os", "windows");
                        connection.setRequestProperty("doc-biz", "Lark");
                    }
                    int status = connection.getResponseCode();
                    captureCookies(connection);
                    if (status >= 300 && status < 400) {
                        String location = connection.getHeaderField("Location");
                        if (!StringUtils.hasText(location)) {
                            throw new IllegalStateException("飞书公开页面跳转缺少目标地址");
                        }
                        currentUrl = new URL(new URL(currentUrl), location).toString();
                        continue;
                    }
                    if (status < 200 || status >= 300) {
                        throw new IllegalStateException("飞书公开页面请求失败：HTTP " + status);
                    }
                    return readBody(connection.getInputStream());
                } catch (Exception ex) {
                    if (ex instanceof IllegalStateException) {
                        throw (IllegalStateException) ex;
                    }
                    throw new IllegalStateException("飞书公开页面请求失败：" + ex.getMessage(), ex);
                } finally {
                    if (connection != null) {
                        connection.disconnect();
                    }
                }
            }
            throw new IllegalStateException("飞书公开页面跳转超过安全上限");
        }

        private void captureCookies(HttpURLConnection connection) {
            for (Map.Entry<String, List<String>> entry : connection.getHeaderFields().entrySet()) {
                if (entry.getKey() == null || !"Set-Cookie".equalsIgnoreCase(entry.getKey())) {
                    continue;
                }
                for (String header : entry.getValue()) {
                    int separator = header.indexOf(';');
                    String pair = separator >= 0 ? header.substring(0, separator) : header;
                    int equals = pair.indexOf('=');
                    if (equals <= 0) {
                        continue;
                    }
                    String name = pair.substring(0, equals).trim();
                    String value = pair.substring(equals + 1).trim();
                    if (value.isEmpty()) {
                        cookies.remove(name);
                    } else {
                        cookies.put(name, value);
                    }
                }
            }
        }

        private String cookieHeader() {
            StringBuilder value = new StringBuilder();
            for (Map.Entry<String, String> entry : cookies.entrySet()) {
                if (value.length() > 0) {
                    value.append("; ");
                }
                value.append(entry.getKey()).append('=').append(entry.getValue());
            }
            return value.toString();
        }

        private String readBody(InputStream inputStream) throws Exception {
            try (InputStream input = inputStream; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192];
                int length;
                while ((length = input.read(buffer)) >= 0) {
                    output.write(buffer, 0, length);
                }
                return new String(output.toByteArray(), StandardCharsets.UTF_8);
            }
        }
    }
}
