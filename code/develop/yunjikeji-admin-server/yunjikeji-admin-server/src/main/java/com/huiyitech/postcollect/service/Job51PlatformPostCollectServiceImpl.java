package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Slf4j
public class Job51PlatformPostCollectServiceImpl extends AbstractRecruitWebsitePostCollectService {

    private static final Pattern CARD_PATTERN = Pattern.compile(
            "(?:joblist-item|j_joblist|job-card|job_item|e\\s+eck)[\\s\\S]*?</(?:li|div)>");
    private static final Pattern TITLE_PATTERN = Pattern.compile(
            "class=\"[^\"]*(?:jname|job-name|job-title|title)[^\"]*\"[^>]*>\\s*(.*?)\\s*</|title=\"([^\"]+)\"");
    private static final Pattern AREA_PATTERN = Pattern.compile(
            "class=\"[^\"]*(?:area|workarea|job-area|location)[^\"]*\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern SALARY_PATTERN = Pattern.compile(
            "class=\"[^\"]*(?:sal|salary|providesalary)[^\"]*\"[^>]*>\\s*(.*?)\\s*</");
    private static final Pattern COMPANY_PATTERN = Pattern.compile(
            "class=\"[^\"]*(?:cname|company-name|company)[^\"]*\"[^>]*>\\s*(?:<a[^>]*>)?\\s*(.*?)\\s*</");
    private static final Pattern JOB_ID_PATTERN = Pattern.compile(
            "jobid=([^&\"']+)|jobId=([^&\"']+)|/job/([^/?\"']+)|\"jobid\"\\s*:\\s*\"?([^,\"'}]+)");
    private static final Pattern JSON_BLOCK_PATTERN = Pattern.compile(
            "\\{[^{}]*(?:\"jobName\"|\"job_name\"|\"jobTitle\"|\"job_title\"|\"jobid\"|\"job_href\")[^{}]*}");

    @Override
    public String getPlatformSource() {
        return "51job";
    }

    @Override
    protected String platformName() {
        return "前程无忧";
    }

    @Override
    protected String searchUrlTemplate() {
        return "https://we.51job.com/pc/search?keyword=%s&searchType=2&sortType=0";
    }

    @Override
    protected String referer() {
        return "https://we.51job.com/";
    }

    @Override
    protected List<PostCollectDO> fetchKeyword(PostCollectTaskDO task, String keyword, int limit) {
        try {
            return super.fetchKeyword(task, keyword, limit);
        } catch (RuntimeException ex) {
            log.warn("前程无忧采集访问失败，返回空结果: taskId={}, keyword={}, message={}",
                    task == null ? null : task.getId(), keyword, ex.getMessage());
            return new ArrayList<>();
        }
    }

    @Override
    protected List<PostCollectDO> parseHtml(PostCollectTaskDO task, String html, int limit) {
        List<PostCollectDO> posts = parseCards(task, html, limit, CARD_PATTERN, TITLE_PATTERN, COMPANY_PATTERN,
                SALARY_PATTERN, AREA_PATTERN, JOB_ID_PATTERN);
        if (!posts.isEmpty()) {
            log.info("前程无忧采集解析命中页面卡片: taskId={}, count={}", task.getId(), posts.size());
            return posts;
        }

        posts = parseJsonLike(task, html, limit);
        if (!posts.isEmpty()) {
            log.info("前程无忧采集解析命中JSON片段: taskId={}, count={}", task.getId(), posts.size());
            return posts;
        }

        log.warn("前程无忧采集解析为0: taskId={}, htmlLength={}, hasJobList={}, hasJobName={}, hasVerify={}, hasLogin={}",
                task.getId(), html == null ? 0 : html.length(), contains(html, "joblist"),
                contains(html, "jobName"), contains(html, "verify"), contains(html, "login"));
        return posts;
    }

    private List<PostCollectDO> parseJsonLike(PostCollectTaskDO task, String html, int limit) {
        List<PostCollectDO> posts = new ArrayList<>();
        Matcher matcher = JSON_BLOCK_PATTERN.matcher(html == null ? "" : html);
        while (matcher.find() && posts.size() < limit) {
            String block = matcher.group();
            String title = firstJsonValue(block, "jobName", "job_name", "jobTitle", "job_title", "job_name_text");
            if (!StringUtils.hasText(title)) {
                continue;
            }
            String externalId = firstJsonValue(block, "jobid", "jobId", "job_id");
            String detailUrl = firstJsonValue(block, "job_href", "jobHref", "jobUrl", "job_url");
            posts.add(buildPost(task, externalId, title,
                    firstJsonValue(block, "companyName", "company_name", "cname", "company"),
                    firstJsonValue(block, "provideSalaryString", "providesalary_text", "salary", "salaryDesc"),
                    firstJsonValue(block, "workAreaString", "workarea_text", "area", "jobArea"),
                    StringUtils.hasText(detailUrl) ? detailUrl : detailUrl(externalId)));
        }
        return posts;
    }

    private String firstJsonValue(String block, String... names) {
        for (String name : names) {
            String value = jsonValue(block, name);
            if (StringUtils.hasText(value)) {
                return value;
            }
        }
        return "";
    }

    private boolean contains(String text, String keyword) {
        return text != null && text.contains(keyword);
    }

    @Override
    protected String detailUrl(String externalId) {
        return StringUtils.hasText(externalId) ? "https://jobs.51job.com/all/" + externalId + ".html" : "";
    }
}
