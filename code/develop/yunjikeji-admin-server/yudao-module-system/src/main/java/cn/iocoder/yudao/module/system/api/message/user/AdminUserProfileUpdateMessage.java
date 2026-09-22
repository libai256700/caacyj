package cn.iocoder.yudao.module.system.api.message.user;

import lombok.Data;

import javax.validation.constraints.NotNull;

@Data
public class AdminUserProfileUpdateMessage {

    @NotNull(message = "用户编号不能为空")
    private Long userId;

    private String nickname;

    private String avatar;

}
