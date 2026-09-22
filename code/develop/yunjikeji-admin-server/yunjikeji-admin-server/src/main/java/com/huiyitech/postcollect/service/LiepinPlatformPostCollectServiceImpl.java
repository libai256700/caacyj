package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestTemplate;

import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Slf4j
public class LiepinPlatformPostCollectServiceImpl extends AbstractRecruitWebsitePostCollectService {

    private static final String API_URL = "https://api-c.liepin.com/api/com.liepin.searchfront4c.pc-search-job";
    private static final int DEFAULT_CITY_CODE = 410;
    private static final int PAGE_SIZE = 40;
    private static final Pattern CARD_PATTERN = Pattern.compile("job-card[\\s\\S]*?</div>\\s*</div>\\s*</div>");
    private static final Pattern TITLE_PATTERN = Pattern.compile("class=\"job-card-title\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern AREA_PATTERN = Pattern.compile("class=\"job-dq\"[^>]*>\\s*(.*?)\\s*</|class=\"job-area\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern SALARY_PATTERN = Pattern.compile("class=\"job-salary\"[^>]*>\\s*(.*?)\\s*</|class=\"job-card-salary\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern COMPANY_PATTERN = Pattern.compile("class=\"company-name\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern JOB_ID_PATTERN = Pattern.compile("/job/([^?\"']+)|data-job-id=\"([^\"']+)\"");
    private final RestTemplate restTemplate = new RestTemplate();

    @Override
    public String getPlatformSource() {
        return "liepin";
    }

    @Override
    protected String platformName() {
        return "Liepin";
    }

    @Override
    protected String searchUrlTemplate() {
        return "https://www.liepin.com/zhaopin/?key=%s";
    }

    @Override
    protected String referer() {
        return "https://www.liepin.com/";
    }

    @Override
    public List<PostCollectDO> collect(PostCollectTaskDO task) {
        String[] keywords = splitKeywords(task);
        if (keywords.length == 0) {
            throw invalidParamException(platformName() + " collection keyword cannot be empty");
        }
        int limit = limit(task, 20);
        List<PostCollectDO> posts = new ArrayList<>();
        log.info("Liepin collection start: taskId={}, keywords={}, limit={}",
                task.getId(), String.join(",", keywords), limit);
        for (String keyword : keywords) {
            if (posts.size() >= limit) {
                break;
            }
            int remaining = limit - posts.size();
            log.info("Liepin keyword collection start: taskId={}, keyword={}, remaining={}",
                    task.getId(), keyword, remaining);
            List<PostCollectDO> keywordPosts = fetchApi(task, keyword, remaining);
            posts.addAll(keywordPosts);
            log.info("Liepin keyword collection done: taskId={}, keyword={}, keywordCount={}, totalCount={}",
                    task.getId(), keyword, keywordPosts.size(), posts.size());
        }
        log.info("Liepin collection done: taskId={}, totalCount={}", task.getId(), posts.size());
        return posts;
    }

    @Override
    protected List<PostCollectDO> parseHtml(PostCollectTaskDO task, String html, int limit) {
        return parseCards(task, html, limit, CARD_PATTERN, TITLE_PATTERN, COMPANY_PATTERN, SALARY_PATTERN,
                AREA_PATTERN, JOB_ID_PATTERN);
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private List<PostCollectDO> fetchApi(PostCollectTaskDO task, String keyword, int limit) {
        String pageUrl = String.format(searchUrlTemplate(), encode(keyword));
        LiepinSession session = initSession(task, keyword, pageUrl);
        List<PostCollectDO> posts = new ArrayList<>();
        for (int page = 0; posts.size() < limit; page++) {
            int pageSize = Math.min(PAGE_SIZE, limit - posts.size());
            HttpHeaders headers = apiHeaders(pageUrl, session);
            Map<String, Object> body = apiBody(keyword, page, pageSize);

            log.info("Liepin API request start: taskId={}, keyword={}, page={}, pageSize={}, url={}",
                    task.getId(), keyword, page, pageSize, API_URL);
            ResponseEntity<Map> response = restTemplate.postForEntity(API_URL, new HttpEntity<>(body, headers), Map.class);
            Map<String, Object> responseBody = response.getBody();
            log.info("Liepin API request done: taskId={}, keyword={}, page={}, status={}, hasBody={}",
                    task.getId(), keyword, page, response.getStatusCode(), responseBody != null);

            List<PostCollectDO> pagePosts = parseApiResponse(task, responseBody, pageSize);
            log.info("Liepin API parse done: taskId={}, keyword={}, page={}, parsedCount={}",
                    task.getId(), keyword, page, pagePosts.size());
            posts.addAll(pagePosts);
            if (pagePosts.size() < pageSize) {
                break;
            }
        }
        return posts;
    }

    private LiepinSession initSession(PostCollectTaskDO task, String keyword, String pageUrl) {
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.USER_AGENT, userAgent());
        headers.add(HttpHeaders.REFERER, referer());
        headers.add(HttpHeaders.ACCEPT, "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8");
        ResponseEntity<String> response = restTemplate.exchange(pageUrl, HttpMethod.GET, new HttpEntity<>(headers),
                String.class);
        LiepinSession session = LiepinSession.from(response.getHeaders().get(HttpHeaders.SET_COOKIE));
        log.info("Liepin session init done: taskId={}, keyword={}, status={}, hasCookie={}, hasXsrf={}",
                task.getId(), keyword, response.getStatusCode(), StringUtils.hasText(session.cookie),
                StringUtils.hasText(session.xsrfToken));
        return session;
    }

    private HttpHeaders apiHeaders(String pageUrl, LiepinSession session) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(new MediaType(MediaType.APPLICATION_JSON, StandardCharsets.UTF_8));
        headers.setAccept(Collections.singletonList(MediaType.APPLICATION_JSON));
        headers.add(HttpHeaders.USER_AGENT, userAgent());
        headers.add(HttpHeaders.REFERER, referer());
        headers.add(HttpHeaders.ORIGIN, "https://www.liepin.com");
        headers.add(HttpHeaders.ACCEPT_LANGUAGE, "zh-CN,zh;q=0.9");
        headers.add("x-client-type", "web");
        headers.add("x-requested-with", "XMLHttpRequest");
        headers.add("x-fscp-version", "1.1");
        headers.add("x-fscp-std-info", "{\"client_id\":\"40108\"}");
        headers.add("x-fscp-bi-stat", "{\"location\":\"" + pageUrl + "\"}");
        headers.add("x-fscp-trace-id", UUID.randomUUID().toString());
        if (StringUtils.hasText(session.xsrfToken)) {
            headers.add("x-xsrf-token", session.xsrfToken);
        }
        if (StringUtils.hasText(session.cookie)) {
            headers.add(HttpHeaders.COOKIE, session.cookie);
        }
        return headers;
    }

    private Map<String, Object> apiBody(String keyword, int page, int pageSize) {
        Map<String, Object> body = new LinkedHashMap<>();
        Map<String, Object> data = new LinkedHashMap<>();
        Map<String, Object> condition = new LinkedHashMap<>();
        condition.put("city", String.valueOf(DEFAULT_CITY_CODE));
        condition.put("dq", String.valueOf(DEFAULT_CITY_CODE));
        condition.put("pubTime", "");
        condition.put("currentPage", page);
        condition.put("pageSize", pageSize);
        condition.put("key", keyword);
        condition.put("suggestTag", "");
        condition.put("workYearCode", "");
        condition.put("compId", "");
        condition.put("compName", "");
        condition.put("compTag", "");
        condition.put("industry", "");
        condition.put("salaryCode", "");
        condition.put("jobKind", "");
        condition.put("compScale", "");
        condition.put("compKind", "");
        condition.put("compStage", "");
        condition.put("eduLevel", "");
        condition.put("salaryLow", "");
        condition.put("salaryHigh", "");
        data.put("mainSearchPcConditionForm", condition);

        Map<String, Object> passThrough = new LinkedHashMap<>();
        passThrough.put("scene", "init");
        passThrough.put("skId", "");
        passThrough.put("fkId", "");
        passThrough.put("ckId", "");
        passThrough.put("suggest", null);
        data.put("passThroughForm", passThrough);
        body.put("data", data);
        return body;
    }

    @SuppressWarnings("unchecked")
    private List<PostCollectDO> parseApiResponse(PostCollectTaskDO task, Map<String, Object> responseBody, int limit) {
        List<PostCollectDO> posts = new ArrayList<>();
        if (responseBody == null) {
            log.warn("Liepin API returned empty body: taskId={}", task.getId());
            return posts;
        }
        Object flag = responseBody.get("flag");
        Object dataValue = responseBody.get("data");
        if (!(dataValue instanceof Map)) {
            log.warn("Liepin API response has no data object: taskId={}, flag={}, code={}, msg={}",
                    task.getId(), flag, responseBody.get("code"), responseBody.get("msg"));
            return posts;
        }
        Object nestedDataValue = ((Map<String, Object>) dataValue).get("data");
        if (!(nestedDataValue instanceof Map)) {
            log.warn("Liepin API response has no nested data object: taskId={}, flag={}", task.getId(), flag);
            return posts;
        }
        Object listValue = ((Map<String, Object>) nestedDataValue).get("jobCardList");
        if (!(listValue instanceof List)) {
            log.warn("Liepin API response has no job list: taskId={}, flag={}", task.getId(), flag);
            return posts;
        }
        List<Object> list = (List<Object>) listValue;
        log.info("Liepin API returned job list: taskId={}, listSize={}", task.getId(), list.size());
        for (Object item : list) {
            if (!(item instanceof Map) || posts.size() >= limit) {
                continue;
            }
            Map<String, Object> card = (Map<String, Object>) item;
            Map<String, Object> job = childMap(card, "job");
            Map<String, Object> comp = childMap(card, "comp");
            String jobId = stringValue(job.get("jobId"));
            String title = stringValue(job.get("title"));
            if (!StringUtils.hasText(title)) {
                log.debug("Liepin skip empty title: taskId={}, jobId={}", task.getId(), jobId);
                continue;
            }
            posts.add(buildPost(task, jobId, title, stringValue(comp.get("compName")),
                    stringValue(job.get("salary")), stringValue(job.get("dq")), stringValue(job.get("link"))));
        }
        return posts;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> childMap(Map<String, Object> parent, String key) {
        Object value = parent.get(key);
        if (value instanceof Map) {
            return (Map<String, Object>) value;
        }
        return Collections.emptyMap();
    }

    private String stringValue(Object value) {
        return value == null ? "" : cleanText(String.valueOf(value));
    }

    @Override
    protected String detailUrl(String externalId) {
        return StringUtils.hasText(externalId)
                ? "https://www.liepin.com/job/" + externalId : "";
    }

    private String encode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (UnsupportedEncodingException ex) {
            throw new IllegalStateException("UTF-8 is not supported", ex);
        }
    }

    private String userAgent() {
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                + "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36";
    }

    private static class LiepinSession {

        private final String cookie;
        private final String xsrfToken;

        private LiepinSession(String cookie, String xsrfToken) {
            this.cookie = cookie;
            this.xsrfToken = xsrfToken;
        }

        private static LiepinSession from(List<String> setCookies) {
            if (setCookies == null || setCookies.isEmpty()) {
                return new LiepinSession("", "");
            }
            List<String> cookies = new ArrayList<>();
            String xsrfToken = "";
            for (String setCookie : setCookies) {
                if (!StringUtils.hasText(setCookie)) {
                    continue;
                }
                String cookiePair = setCookie.split(";", 2)[0];
                if (!StringUtils.hasText(cookiePair)) {
                    continue;
                }
                cookies.add(cookiePair);
                int splitIndex = cookiePair.indexOf('=');
                if (splitIndex > 0 && "XSRF-TOKEN".equals(cookiePair.substring(0, splitIndex))) {
                    xsrfToken = cookiePair.substring(splitIndex + 1);
                }
            }
            return new LiepinSession(String.join("; ", cookies), xsrfToken);
        }
    }
}
