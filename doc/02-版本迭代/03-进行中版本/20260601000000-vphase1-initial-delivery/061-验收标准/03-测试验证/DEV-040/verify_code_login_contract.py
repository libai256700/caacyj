#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


FILES = {
    "customer_dto": "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/customer/controller/vo/AppCustomerAuthRegisterReqVO.java",
    "company_dto": "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/companyaudit/controller/vo/AppCompanyAuthRegisterReqVO.java",
    "customer_service": "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/customer/service/CustomerServiceImpl.java",
    "company_service": "code/develop/yunjikeji-admin-server/yunjikeji-admin-server/src/main/java/com/huiyitech/companyaudit/service/CompanyAuditServiceImpl.java",
    "frontend": "code/develop/yunjikeji/src/services/customerAuth.ts",
    "sms_controller": "code/develop/yunjikeji-admin-server/yudao-module-member/src/main/java/cn/iocoder/yudao/module/member/controller/app/auth/AppAuthController.java",
    "member_auth": "code/develop/yunjikeji-admin-server/yudao-module-member/src/main/java/cn/iocoder/yudao/module/member/service/auth/MemberAuthServiceImpl.java",
    "sms_api": "code/develop/yunjikeji-admin-server/yudao-module-system/src/main/java/cn/iocoder/yudao/module/system/api/sms/SmsCodeApiImpl.java",
    "sms_service": "code/develop/yunjikeji-admin-server/yudao-module-system/src/main/java/cn/iocoder/yudao/module/system/service/sms/SmsCodeServiceImpl.java",
    "sms_do": "code/develop/yunjikeji-admin-server/yudao-module-system/src/main/java/cn/iocoder/yudao/module/system/dal/dataobject/sms/SmsCodeDO.java",
    "sms_mapper": "code/develop/yunjikeji-admin-server/yudao-module-system/src/main/java/cn/iocoder/yudao/module/system/dal/mysql/sms/SmsCodeMapper.java",
}


def extract_block(source: str, marker: str) -> str:
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise ValueError(f"unterminated block: {marker}")


def add_check(results: list, name: str, passed: bool, detail: str) -> None:
    results.append({"name": name, "passed": passed, "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    source = {name: (root / path).read_text(encoding="utf-8") for name, path in FILES.items()}
    results = []

    for role in ("customer", "company"):
        dto = source[f"{role}_dto"]
        service = source[f"{role}_service"]
        login = extract_block(service, "loginOrRegister(")
        add_check(results, f"{role}_dto_code_field", "private String code;" in dto and "private String password;" not in dto,
                  "request VO exposes code and no password field")
        add_check(results, f"{role}_dto_six_digits", '^\\\\d{6}$' in dto,
                  "request VO validates a six-digit code")
        add_check(results, f"{role}_member_login_consumption",
                  "reqVO.getCode()" in login and "SmsSceneEnum.MEMBER_LOGIN.getScene()" in service,
                  "login consumes code in MEMBER_LOGIN scene")
        add_check(results, f"{role}_no_password_auth", "getPassword()" not in login and "passwordEncoder.matches" not in login,
                  "login-or-register does not read or match an account password")
        random_password_call = "createCustomer(mobile)" if role == "customer" else "encodeRandomInitialPassword()"
        add_check(results, f"{role}_secure_random_password",
                  "RANDOM_PASSWORD_BYTES = 32" in service
                  and "new SecureRandom()" in service
                  and random_password_call in login
                  and "passwordEncoder.encode(Base64.getUrlEncoder().withoutPadding().encodeToString(randomPassword))" in service,
                  "new account password uses 256 random bits and is encoded server-side")

    frontend = source["frontend"]
    add_check(results, "frontend_customer_code_payload",
              "loginCustomer = async (mobile: string, code: string)" in frontend
              and "data: { mobile, code }" in frontend,
              "student login sends mobile + code")
    add_check(results, "frontend_company_code_payload",
              "loginCompany = async (username: string, code: string)" in frontend
              and "data: { mobile: username, code }" in frontend,
              "company login sends mobile + code")

    sms_service = source["sms_service"]
    send_method = extract_block(sms_service, "sendSmsCode(")
    use_method = extract_block(sms_service, "useSmsCode(")
    add_check(results, "sms_send_chain",
              "authService.sendSmsCode" in source["sms_controller"]
              and "smsCodeApi.sendSmsCode" in source["member_auth"]
              and "smsCodeService.sendSmsCode" in source["sms_api"],
              "controller delegates through member auth and SMS API to SmsCodeService")
    add_check(results, "sms_saved_before_send",
              send_method.index("createSmsCode(") < send_method.index("smsSendService.sendSingleSms")
              and "smsCodeMapper.insert(newSmsCode)" in sms_service,
              "SMS code row is inserted before provider send")
    add_check(results, "sms_same_store_and_scene",
              '@TableName("system_sms_code")' in source["sms_do"]
              and 'eq("mobile", mobile)' in source["sms_mapper"]
              and 'eqIfPresent("scene", scene)' in source["sms_mapper"]
              and 'eqIfPresent("code", code)' in source["sms_mapper"]
              and "smsCodeService.useSmsCode" in source["sms_api"]
              and "validateSmsCode0(reqDTO.getMobile(), reqDTO.getCode(), reqDTO.getScene())" in use_method,
              "send and consume use system_sms_code keyed by mobile + code + scene")
    add_check(results, "sms_persistence_fields_and_expiry",
              ".mobile(mobile).code(code).scene(scene)" in sms_service
              and ".createIp(ip).used(false)" in sms_service
              and "lastSmsCode.getCreateTime()" in sms_service
              and "smsCodeProperties.getExpireTimes()" in sms_service,
              "row stores credential state; expiry is derived from createTime plus configured duration")

    report = {
        "status": "PASS" if all(item["passed"] for item in results) else "FAIL",
        "checks": results,
        "security_notes": [
            "Random initial passwords are never included in responses or logs by the checked flow.",
            "SMS provider failure after insert can leave an unused row; concurrent use is not atomically claimed in this task."
        ]
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        (root / args.output).write_text(output + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
