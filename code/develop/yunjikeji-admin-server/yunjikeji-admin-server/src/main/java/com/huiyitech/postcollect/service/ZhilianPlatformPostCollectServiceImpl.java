package com.huiyitech.postcollect.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
public class ZhilianPlatformPostCollectServiceImpl extends AbstractRecruitWebsitePostCollectService {

    private static final Pattern INITIAL_STATE_PATTERN = Pattern.compile("__INITIAL_STATE__=(\\{[\\s\\S]*?\\})</script>");
    private static final Pattern CARD_PATTERN = Pattern.compile("joblist-box__item[\\s\\S]*?</div>\\s*</div>\\s*</div>");
    private static final Pattern TITLE_PATTERN = Pattern.compile("class=\"jobinfo__name\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern AREA_PATTERN = Pattern.compile("class=\"jobinfo__other-info-item\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern SALARY_PATTERN = Pattern.compile("class=\"jobinfo__salary\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern COMPANY_PATTERN = Pattern.compile("class=\"companyinfo__name\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern JOB_ID_PATTERN = Pattern.compile("/jobdetail/([^/?\"']+)|jobs\\.zhaopin\\.com/([^/?\"']+)");
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public String getPlatformSource() {
        return "zhilian";
    }

    @Override
    protected String platformName() {
        return "Zhaopin";
    }

    @Override
    protected String searchUrlTemplate() {
        return "https://www.zhaopin.com/sou/?key=%s&city=";
    }

    @Override
    protected String referer() {
        return "https://www.zhaopin.com/";
    }

    @Override
    protected List<PostCollectDO> parseHtml(PostCollectTaskDO task, String html, int limit) {
        List<PostCollectDO> posts = parseInitialState(task, html, limit);
        if (!posts.isEmpty()) {
            return posts;
        }
        return parseCards(task, html, limit, CARD_PATTERN, TITLE_PATTERN, COMPANY_PATTERN, SALARY_PATTERN,
                AREA_PATTERN, JOB_ID_PATTERN);
    }

    private List<PostCollectDO> parseInitialState(PostCollectTaskDO task, String html, int limit) {
        List<PostCollectDO> posts = new ArrayList<>();
        if (!StringUtils.hasText(html)) {
            return posts;
        }
        Matcher matcher = INITIAL_STATE_PATTERN.matcher(html);
        if (!matcher.find()) {
            log.warn("Zhaopin initial state not found: taskId={}", task.getId());
            return posts;
        }
        try {
            JsonNode list = objectMapper.readTree(matcher.group(1)).path("positionList");
            if (!list.isArray()) {
                log.warn("Zhaopin initial state has no positionList: taskId={}", task.getId());
                return posts;
            }
            for (JsonNode job : list) {
                if (posts.size() >= limit) {
                    break;
                }
                String title = firstText(job, "name");
                if (!StringUtils.hasText(title)) {
                    title = text(job.path("jobDetailData").path("position").path("base"), "positionName");
                }
                if (!StringUtils.hasText(title)) {
                    continue;
                }
                String externalId = firstText(job, "number", "jobId");
                String detailUrl = firstText(job, "positionURL", "positionUrl");
                posts.add(buildPost(task, externalId, title, text(job, "companyName"),
                        firstText(job, "salary60", "salaryReal"), workArea(job), detailUrl));
            }
            log.info("Zhaopin initial state parsed: taskId={}, parsedCount={}", task.getId(), posts.size());
        } catch (Exception ex) {
            log.warn("Zhaopin initial state parse failed: taskId={}", task.getId(), ex);
        }
        return posts;
    }

    private String workArea(JsonNode job) {
        String area = text(job, "cityDistrict");
        if (StringUtils.hasText(area)) {
            return area;
        }
        return text(job.path("jobDetailData").path("position").path("workLocation"), "address");
    }

    private String firstText(JsonNode node, String... names) {
        for (String name : names) {
            String value = text(node, name);
            if (StringUtils.hasText(value)) {
                return value;
            }
        }
        return "";
    }

    private String text(JsonNode node, String name) {
        if (node == null || !node.has(name) || node.get(name).isNull()) {
            return "";
        }
        return cleanText(node.get(name).asText());
    }
}
