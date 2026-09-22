package com.huiyitech.aiconfig.dal.dataobject;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

/**
 * AI model configuration bound to a business scene.
 *
 * <p>The API key is intentionally kept server-side and is never returned by
 * ordinary admin list endpoints.</p>
 */
@TableName("yj_ai_model_config")
@Data
@EqualsAndHashCode(callSuper = true)
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AiModelConfigDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String sceneCode;

    private String sceneName;

    private String channel;

    private String baseUrl;

    private String apiKey;

    /** Provider-specific settings, such as knowledge-base signing parameters. */
    private String extraConfig;

    private String model;

    private String systemPrompt;

    private Double temperature;

    private Integer maxTokens;

    private Integer timeoutMillis;

    private Integer minReportLength;

    private Integer status;

    private Integer sort;

    private String remark;
}
