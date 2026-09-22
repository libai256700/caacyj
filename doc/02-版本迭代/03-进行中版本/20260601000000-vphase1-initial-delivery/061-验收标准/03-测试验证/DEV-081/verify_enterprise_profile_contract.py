from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[7]
APP = ROOT / "code" / "develop" / "yunjikeji"
CUSTOMER_AUTH = APP / "src" / "services" / "customerAuth.ts"
PROFILE = APP / "src" / "pages" / "profile.vue"


def read_text(path: Path) -> str:
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def find_block(source: str, start_token: str) -> str:
    start = source.find(start_token)
    if start < 0:
        return ""
    brace_start = source.find("{", start)
    if brace_start < 0:
        return ""
    depth = 0
    for index in range(brace_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    return source[start:]


def main() -> int:
    customer_auth = read_text(CUSTOMER_AUTH)
    profile = read_text(PROFILE)
    enterprise_info_block = find_block(profile, "const enterpriseProfileInfo = computed(() =>")
    load_profile_block = find_block(profile, "async function loadCurrentCompanyProfile()")
    on_show_block = find_block(profile, "onShow(() =>")

    checks = {
        "company_profile_type": "export type CompanyProfile = {" in customer_auth,
        "company_profile_fields": all(
            token in customer_auth for token in ("nickname?: string", "deptName?: string")
        ),
        "fetch_current_company_export": "export const fetchCurrentCompany = ()" in customer_auth,
        "fetch_current_company_contract": bool(
            re.search(
                r"export const fetchCurrentCompany = \(\)\s*=>\s*[\s\S]*requestCompanyAuth<CompanyProfile>\(\{\s*path: '/me',\s*method: 'GET',\s*auth: true,",
                customer_auth,
            )
        ),
        "profile_imports_fetch_current_company": "fetchCurrentCompany," in profile,
        "enterprise_state_defined": "type EnterpriseProfileState = {" in profile and "const enterpriseProfileState = reactive<EnterpriseProfileState>" in profile,
        "enterprise_info_uses_state": "enterpriseProfileState.nickname" in enterprise_info_block
        and "enterpriseProfileState.deptName" in enterprise_info_block,
        "enterprise_info_does_not_use_profile_storage": "PROFILE_STORAGE_KEY" not in enterprise_info_block,
        "enterprise_phone_uses_session": "session?.phone || baseProfile.phone" in enterprise_info_block,
        "enterprise_onshow_refresh": "loadCurrentCompanyProfile()" in on_show_block,
        "load_profile_branching": "if (appState.loginIdentity !== 'enterprise')" in load_profile_block
        and "const profile = await fetchCurrentCompany()" in load_profile_block
        and "await fetchCurrentCustomer()" in load_profile_block,
        "no_enterprise_profile_storage_write": "uni.setStorageSync(PROFILE_STORAGE_KEY, { ...enterpriseProfileState })" not in profile,
    }

    passed = all(checks.values())
    for name, result in checks.items():
        print(f"{'PASS' if result else 'FAIL'} {name}")
    print(f"SUMMARY passed={sum(1 for result in checks.values() if result)} failed={sum(1 for result in checks.values() if not result)}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
