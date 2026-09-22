package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestTemplate;

import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.invalidParamException;

@Slf4j
public abstract class AbstractRecruitWebsitePostCollectService extends AbstractPostPlatformCollectService {

    private final RestTemplate restTemplate = new RestTemplate();

    @Override
    public List<PostCollectDO> collect(PostCollectTaskDO task) {
        String[] keywords = splitKeywords(task);
        if (keywords.length == 0) {
            throw invalidParamException(platformName() + "采集关键词不能为空");
        }
        int limit = limit(task, 20);
        List<PostCollectDO> posts = new ArrayList<>();
        log.info("岗位采集开始: platform={}, taskId={}, keywords={}, limit={}",
                getPlatformSource(), task == null ? null : task.getId(), String.join(",", keywords), limit);
        for (String keyword : keywords) {
            if (posts.size() >= limit) {
                break;
            }
            int remaining = limit - posts.size();
            log.info("岗位采集关键词开始: platform={}, taskId={}, keyword={}, remaining={}",
                    getPlatformSource(), task.getId(), keyword, remaining);
            List<PostCollectDO> keywordPosts = fetchKeyword(task, keyword, remaining);
            posts.addAll(keywordPosts);
            log.info("岗位采集关键词完成: platform={}, taskId={}, keyword={}, keywordCount={}, totalCount={}",
                    getPlatformSource(), task.getId(), keyword, keywordPosts.size(), posts.size());
        }
        log.info("岗位采集完成: platform={}, taskId={}, totalCount={}",
                getPlatformSource(), task.getId(), posts.size());
        return posts;
    }

    protected List<PostCollectDO> fetchKeyword(PostCollectTaskDO task, String keyword, int limit) {
        String url = String.format(searchUrlTemplate(), encode(keyword));
        log.info("岗位采集请求开始: platform={}, taskId={}, keyword={}, limit={}, url={}",
                getPlatformSource(), task.getId(), keyword, limit, url);
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.USER_AGENT, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                + "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36");
        headers.add(HttpHeaders.REFERER, referer());
        try {
            ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.GET, new HttpEntity<>(headers),
                    String.class);
            String html = response.getBody();
            MediaType contentType = response.getHeaders().getContentType();
            log.info("岗位采集请求完成: platform={}, taskId={}, keyword={}, status={}, contentType={}, bodyLength={}",
                    getPlatformSource(), task.getId(), keyword, response.getStatusCode(),
                    contentType, html == null ? 0 : html.length());
            if (!StringUtils.hasText(html)) {
                log.warn("岗位采集返回空内容: platform={}, taskId={}, keyword={}, status={}",
                        getPlatformSource(), task.getId(), keyword, response.getStatusCode());
                return new ArrayList<>();
            }
            List<PostCollectDO> posts = parseHtml(task, html, limit);
            log.info("岗位采集解析完成: platform={}, taskId={}, keyword={}, parsedCount={}",
                    getPlatformSource(), task.getId(), keyword, posts.size());
            return posts;
        } catch (RuntimeException ex) {
            log.error("岗位采集请求失败: platform={}, taskId={}, keyword={}, url={}",
                    getPlatformSource(), task.getId(), keyword, url, ex);
            throw ex;
        }
    }

    protected List<PostCollectDO> parseCards(PostCollectTaskDO task, String html, int limit, Pattern cardPattern,
                                             Pattern titlePattern, Pattern companyPattern, Pattern salaryPattern,
                                             Pattern areaPattern, Pattern idPattern) {
        List<PostCollectDO> posts = new ArrayList<>();
        Matcher cardMatcher = cardPattern.matcher(html);
        while (cardMatcher.find() && posts.size() < limit) {
            String card = cardMatcher.group();
            String title = firstMatch(card, titlePattern);
            if (!StringUtils.hasText(title)) {
                continue;
            }
            String externalId = firstMatch(card, idPattern);
            posts.add(buildPost(task, externalId, title, firstMatch(card, companyPattern),
                    firstMatch(card, salaryPattern), firstMatch(card, areaPattern), detailUrl(externalId)));
        }
        return posts;
    }

    protected String firstMatch(String text, Pattern pattern) {
        if (pattern == null || text == null) {
            return "";
        }
        Matcher matcher = pattern.matcher(text);
        if (!matcher.find()) {
            return "";
        }
        for (int i = 1; i <= matcher.groupCount(); i++) {
            if (StringUtils.hasText(matcher.group(i))) {
                return cleanText(matcher.group(i));
            }
        }
        return "";
    }

    protected String jsonValue(String block, String name) {
        Matcher matcher = Pattern.compile("\"" + name + "\"\\s*:\\s*\"([^\"]*)\"").matcher(block);
        return matcher.find() ? cleanText(matcher.group(1)) : "";
    }

    protected String detailUrl(String externalId) {
        return "";
    }

    protected String referer() {
        return "";
    }

    protected abstract String platformName();

    protected abstract String searchUrlTemplate();

    protected abstract List<PostCollectDO> parseHtml(PostCollectTaskDO task, String html, int limit);

    private String encode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (UnsupportedEncodingException ex) {
            throw new IllegalStateException("UTF-8 is not supported", ex);
        }
    }
}
