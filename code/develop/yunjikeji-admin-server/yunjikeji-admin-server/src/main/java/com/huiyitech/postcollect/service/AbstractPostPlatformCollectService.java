package com.huiyitech.postcollect.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectTaskDO;
import org.springframework.util.StringUtils;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public abstract class AbstractPostPlatformCollectService implements IPostPlatformCollectService {

    private static final Pattern HTML_TAG = Pattern.compile("<[^>]+>");

    @Override
    public abstract List<PostCollectDO> collect(PostCollectTaskDO task);

    protected String[] splitKeywords(PostCollectTaskDO task) {
        if (task == null || !StringUtils.hasText(task.getCollectionKey())) {
            return new String[0];
        }
        String[] raw = task.getCollectionKey().split("[,，;；\\s]+");
        List<String> keywords = new ArrayList<>();
        for (String item : raw) {
            if (StringUtils.hasText(item)) {
                keywords.add(item.trim());
            }
        }
        return keywords.toArray(new String[0]);
    }

    protected int limit(PostCollectTaskDO task, int defaultLimit) {
        if (task == null || task.getCollectionNum() == null || task.getCollectionNum() <= 0) {
            return defaultLimit;
        }
        return Math.min(task.getCollectionNum(), 200);
    }

    protected PostCollectDO buildPost(PostCollectTaskDO task, String externalPostId, String name, String companyName,
                                      String salaryRange, String workArea, String detailUrl) {
        PostCollectDO post = PostCollectDO.builder()
                .name(cleanText(name))
                .companyName(cleanText(companyName))
                .sourceCode(getPlatformSource())
                .externalPostId(cleanText(externalPostId))
                .salaryRange(cleanText(salaryRange))
                .workArea(cleanText(workArea))
                .publishDate(LocalDate.now().toString())
                .detailUrl(cleanText(detailUrl))
                .status(Boolean.TRUE)
                .build();
        post.setDeleted(Boolean.FALSE);
        return post;
    }

    protected String cleanText(String value) {
        if (value == null) {
            return "";
        }
        String noTags = HTML_TAG.matcher(value).replaceAll("");
        return noTags.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .trim();
    }

}
