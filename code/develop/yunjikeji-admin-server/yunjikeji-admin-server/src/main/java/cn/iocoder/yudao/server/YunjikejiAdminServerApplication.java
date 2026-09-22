package cn.iocoder.yudao.server;

import org.apache.ibatis.annotations.Mapper;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SuppressWarnings("SpringComponentScan")
@SpringBootApplication(scanBasePackages = {
        "${yudao.info.base-package}.server",
        "${yudao.info.base-package}.module",
        "com.huiyitech.app",
        "com.huiyitech.customer",
        "com.huiyitech.companyaudit",
        "com.huiyitech.practice",
        "com.huiyitech.knowledge",
        "com.huiyitech.aiconfig",
        "com.huiyitech.chart",
        "com.huiyitech.postcollect",
        "com.huiyitech.agreement",
        "com.huiyitech.message",
        "com.huiyitech.sms",
        "com.huiyitech.mcp",
        "com.huiyitech.univerify",
        "com.huiyitech.utils"
})
@MapperScan(value = {
        "com.huiyitech.customer.dal.mysql",
        "com.huiyitech.companyaudit.dal.mysql",
        "com.huiyitech.practice.dal.mysql",
        "com.huiyitech.chart.dal.mysql",
        "com.huiyitech.postcollect.dal.mysql",
        "com.huiyitech.agreement.dal.mysql",
        "com.huiyitech.aiconfig.dal.mysql",
        "com.huiyitech.app.knowledge.dal.mysql"
}, annotationClass = Mapper.class)
public class YunjikejiAdminServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(YunjikejiAdminServerApplication.class, args);
    }

}
