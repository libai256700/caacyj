package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestTemplate;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Slf4j
public class GuopinPlatformPostCollectServiceImpl extends AbstractRecruitWebsitePostCollectService {

    private static final String API_URL = "https://gp-api.iguopin.com/api/jobs/v1/recom-job";
    private static final Pattern CARD_PATTERN = Pattern.compile("job-item[\\s\\S]*?</div>\\s*</div>\\s*</div>");
    private static final Pattern TITLE_PATTERN = Pattern.compile("class=\"job-title\"[^>]*>\\s*(.*?)\\s*</|class=\"job-name\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern AREA_PATTERN = Pattern.compile("class=\"job-area\"[^>]*>\\s*(.*?)\\s*</|class=\"area\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern SALARY_PATTERN = Pattern.compile("class=\"salary\"[^>]*>\\s*(.*?)\\s*</|class=\"job-salary\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern COMPANY_PATTERN = Pattern.compile("class=\"company-name\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern JOB_ID_PATTERN = Pattern.compile("jobId=([^&\"']+)|/job/([^/?\"']+)");
    private final RestTemplate restTemplate = new RestTemplate();

    @Override
    public String getPlatformSource() {
        return "guopin";
    }

    @Override
    protected String platformName() {
        return "国聘";
    }

    @Override
    protected String searchUrlTemplate() {
        return "https://www.iguopin.com/job?keyword=%s";
    }

    @Override
    protected String referer() {
        return "https://www.iguopin.com/";
    }

    @Override
    public List<PostCollectDO> collect(PostCollectTaskDO task) {
        String[] keywords = splitKeywords(task);
        if (keywords.length == 0) {
            throw invalidParamException(platformName() + "采集关键词不能为空");
        }
        int limit = limit(task, 20);
        List<PostCollectDO> posts = new ArrayList<>();
        log.info("国聘采集开始: taskId={}, keywords={}, limit={}", task.getId(), String.join(",", keywords), limit);
        for (String keyword : keywords) {
            if (posts.size() >= limit) {
                break;
            }
            int remaining = limit - posts.size();
            log.info("国聘采集关键词开始: taskId={}, keyword={}, remaining={}", task.getId(), keyword, remaining);
            List<PostCollectDO> keywordPosts = fetchApi(task, keyword, remaining);
            posts.addAll(keywordPosts);
            log.info("国聘采集关键词完成: taskId={}, keyword={}, keywordCount={}, totalCount={}",
                    task.getId(), keyword, keywordPosts.size(), posts.size());
        }
        log.info("国聘采集完成: taskId={}, totalCount={}", task.getId(), posts.size());
        return posts;
    }

    @Override
    protected List<PostCollectDO> parseHtml(PostCollectTaskDO task, String html, int limit) {
        return parseCards(task, html, limit, CARD_PATTERN, TITLE_PATTERN, COMPANY_PATTERN, SALARY_PATTERN,
                AREA_PATTERN, JOB_ID_PATTERN);
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    private List<PostCollectDO> fetchApi(PostCollectTaskDO task, String keyword, int limit) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(new MediaType(MediaType.APPLICATION_JSON, StandardCharsets.UTF_8));
        headers.setAccept(java.util.Collections.singletonList(MediaType.APPLICATION_JSON));
        headers.add(HttpHeaders.USER_AGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                + "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36");
        headers.add(HttpHeaders.REFERER, referer());
        headers.add(HttpHeaders.ORIGIN, "https://www.iguopin.com");
        headers.add("device", "pc");
        headers.add("subsite", "iguopin");
        headers.add("version", "5.2.300");

        Map<String, Object> body = new LinkedHashMap<>();
        Map<String, Object> search = new LinkedHashMap<>();
        search.put("page", 1);
        search.put("page_size", limit);
        search.put("keyword", keyword);
        body.put("search", search);
        Map<String, Object> recom = new LinkedHashMap<>();
        recom.put("update_time", true);
        recom.put("company_nature", true);
        recom.put("hot_job", true);
        body.put("recom", recom);

        log.info("国聘采集接口请求开始: taskId={}, keyword={}, limit={}, url={}", task.getId(), keyword, limit, API_URL);
        ResponseEntity<Map> response = restTemplate.postForEntity(API_URL, new HttpEntity<>(body, headers), Map.class);
        Map<String, Object> responseBody = response.getBody();
        log.info("国聘采集接口请求完成: taskId={}, keyword={}, status={}, hasBody={}",
                task.getId(), keyword, response.getStatusCode(), responseBody != null);
        List<PostCollectDO> posts = parseApiResponse(task, responseBody, limit);
        log.info("国聘采集接口解析完成: taskId={}, keyword={}, parsedCount={}", task.getId(), keyword, posts.size());
        return posts;
    }

    @SuppressWarnings("unchecked")
    private List<PostCollectDO> parseApiResponse(PostCollectTaskDO task, Map<String, Object> responseBody, int limit) {
        List<PostCollectDO> posts = new ArrayList<>();
        if (responseBody == null) {
            log.warn("国聘采集接口返回空响应体: taskId={}", task.getId());
            return posts;
        }
        Object code = responseBody.get("code");
        Object dataValue = responseBody.get("data");
        if (!(dataValue instanceof Map)) {
            log.warn("国聘采集接口响应无data对象: taskId={}, code={}, keys={}",
                    task.getId(), code, responseBody.keySet());
            return posts;
        }
        Map<String, Object> data = (Map<String, Object>) dataValue;
        Object listValue = data.get("list");
        if (!(listValue instanceof List)) {
            log.warn("国聘采集接口响应无岗位列表: taskId={}, code={}, total={}",
                    task.getId(), code, data.get("total"));
            return posts;
        }
        List<Object> list = (List<Object>) listValue;
        log.info("国聘采集接口返回岗位列表: taskId={}, total={}, listSize={}",
                task.getId(), data.get("total"), list.size());
        for (Object item : list) {
            if (!(item instanceof Map) || posts.size() >= limit) {
                continue;
            }
            Map<String, Object> job = (Map<String, Object>) item;
            String jobId = stringValue(job.get("job_id"));
            String jobName = stringValue(job.get("job_name"));
            if (!StringUtils.hasText(jobName)) {
                log.debug("国聘采集跳过空岗位名: taskId={}, jobId={}", task.getId(), jobId);
                continue;
            }
            posts.add(buildPost(task, jobId, jobName, stringValue(job.get("company_name")),
                    salary(job), workArea(job), detailUrl(jobId)));
        }
        return posts;
    }

    @SuppressWarnings("unchecked")
    private String workArea(Map<String, Object> job) {
        Object districtValue = job.get("district_list");
        if (!(districtValue instanceof List)) {
            return "";
        }
        List<Object> districts = (List<Object>) districtValue;
        if (districts.isEmpty() || !(districts.get(0) instanceof Map)) {
            return "";
        }
        return stringValue(((Map<String, Object>) districts.get(0)).get("area_cn"));
    }

    private String salary(Map<String, Object> job) {
        if (Boolean.TRUE.equals(job.get("is_negotiable"))) {
            return "面议";
        }
        String min = stringValue(job.get("min_wage"));
        String max = stringValue(job.get("max_wage"));
        String unit = stringValue(job.get("wage_unit_cn"));
        if (StringUtils.hasText(min) && StringUtils.hasText(max)) {
            return min + "~" + max + unit;
        }
        return "";
    }

    private String stringValue(Object value) {
        return value == null ? "" : cleanText(String.valueOf(value));
    }

    @Override
    protected String detailUrl(String externalId) {
        return StringUtils.hasText(externalId) ? "https://www.iguopin.com/job/detail?id=" + externalId : "";
    }
}
