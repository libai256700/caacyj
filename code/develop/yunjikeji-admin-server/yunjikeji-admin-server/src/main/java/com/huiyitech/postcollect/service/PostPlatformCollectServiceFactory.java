package com.huiyitech.postcollect.service;

import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
public class PostPlatformCollectServiceFactory {

    public static final String FEISHU_FOLDER_CHANNEL = "feishu_folder";
    public static final String FEISHU_FOLDER_V2_CHANNEL = "feishu_folder_v2";

    private final FeishuFolderPlatformPostCollectServiceImpl feishuFolderService;

    public PostPlatformCollectServiceFactory(FeishuFolderPlatformPostCollectServiceImpl feishuFolderService) {
        this.feishuFolderService = feishuFolderService;
    }

    public IPostPlatformCollectService getRequired(String channel) {
        String normalizedChannel = StringUtils.hasText(channel) ? channel.trim() : channel;
        if (isFeishuFolderChannel(normalizedChannel)) {
            return feishuFolderService;
        }
        return new UnsupportedPostPlatformCollectServiceImpl(normalizedChannel);
    }

    public static boolean isFeishuFolderChannel(String channel) {
        return FEISHU_FOLDER_CHANNEL.equals(channel) || FEISHU_FOLDER_V2_CHANNEL.equals(channel);
    }
}
