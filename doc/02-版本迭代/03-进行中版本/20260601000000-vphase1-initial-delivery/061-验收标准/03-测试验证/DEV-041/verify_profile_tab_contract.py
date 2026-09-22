from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[7]
APP = ROOT / "code" / "develop" / "yunjikeji"
HOME = APP / "src" / "pages" / "home.vue"
PROFILE = APP / "src" / "pages" / "profile.vue"
COMPONENT = APP / "src" / "components" / "HomeProfileTabBar.vue"

HOME_BASELINE_SHA256 = "a5a9caf2bdcf496693ba2d40e44164c830b7e9a7db397d86fb6ab4666794f990"
PROFILE_BASELINE_SHA256 = "38daa8dda8e6f42feda73e4cf38f2d4d8f2ecdc5fdf2753e7474c034a5de11df"
FORBIDDEN_DIFF_SHA256 = "3344a0b2a0b25004e240fb277664cfbaeccb4e68d8ba332f1f32f3056a80f95d"

OLD_HOME_NAV = """      <view class="bottom-nav">
        <view class="nav-item active">
          <uv-icon name="home-fill" color="#ff5d5f" size="22" />
          <text>首页</text>
        </view>
        <view class="nav-item nav-ai" @tap="openMainPage('/pages/center')">
          <view class="owl-ring"><image src="/static/brand/jixiangwu-logo.png" mode="aspectFill" /></view>
          <text>AI助手</text>
        </view>
        <view class="nav-item" @tap="openMainPage('/pages/profile')">
          <uv-icon name="account-fill" color="#aab4ca" size="22" />
          <text>我的</text>
        </view>
      </view>"""

OLD_HOME_CSS = """.bottom-nav { position: absolute; z-index: 10; left: 0; right: 0; bottom: 0; box-sizing: border-box; height: 67px; padding: 5px 8px max(3px, env(safe-area-inset-bottom)); display: grid; grid-template-columns: repeat(3,1fr); align-items: end; background: rgba(255,255,255,.98); box-shadow: 0 -5px 18px rgba(54,105,146,.08); }
.nav-item { position: relative; height: 54px; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 3px; color: #9ca8bc; font-size: 10px; font-weight: 600; }
.nav-item.active { color: #ff5d5f; }
.nav-ai { color: #7789a5; }
.owl-ring { position: absolute; top: -36px; box-sizing: border-box; width: 62px; height: 62px; padding: 2px; border-radius: 50%; background: #1279eb; border: 4px solid #fff; box-shadow: 0 5px 14px rgba(10,84,184,.38); overflow: hidden; }
.owl-ring image { width: 100%; height: 100%; border-radius: 50%; transform: scale(1.08); transform-origin: 50% 48%; }"""


def read_text(path: Path) -> str:
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reconstruct_home(home: str) -> str:
    if '<HomeProfileTabBar active="home" placement="absolute" />' not in home:
        return home
    restored = home.replace(
        '      <HomeProfileTabBar active="home" placement="absolute" />', OLD_HOME_NAV
    )
    restored = restored.replace(
        "import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'\n", ""
    )
    return restored.replace("\n\n@media (max-width: 370px)", f"\n\n{OLD_HOME_CSS}\n\n@media (max-width: 370px)")


def reconstruct_profile(profile: str) -> str:
    restored = profile.replace(
        '    <HomeProfileTabBar active="profile" placement="fixed" />',
        "    <AppDynamicTabBar />",
    )
    restored = restored.replace(
        "import HomeProfileTabBar from '@/components/HomeProfileTabBar.vue'",
        "import AppDynamicTabBar from '@/components/AppDynamicTabBar.vue'",
    )
    restored = restored.replace("  background: #F5F0EA;", "  background: #edf6ff;")
    restored = restored.replace(
        "linear-gradient(180deg, rgba(245, 240, 234, 0.2) 0%, rgba(245, 240, 234, 0.9) 32%, #F5F0EA 100%)",
        "linear-gradient(180deg, rgba(239, 247, 255, 0.2) 0%, rgba(243, 249, 255, 0.9) 32%, #f6fbff 100%)",
    )
    return restored.replace(
        "linear-gradient(180deg, rgba(245, 240, 234, 0.34) 0%, rgba(245, 240, 234, 0.14) 34%, rgba(245, 240, 234, 0.42) 100%)",
        "linear-gradient(180deg, rgba(236, 247, 255, 0.34) 0%, rgba(247, 251, 255, 0.14) 34%, rgba(239, 248, 255, 0.42) 100%)",
    )


def forbidden_diff_sha256() -> str:
    command = [
        "git", "diff", "--",
        "code/develop/yunjikeji",
        ":(exclude)code/develop/yunjikeji/src/pages/home.vue",
        ":(exclude)code/develop/yunjikeji/src/pages/profile.vue",
        ":(exclude)code/develop/yunjikeji/src/components/HomeProfileTabBar.vue",
    ]
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
    return hashlib.sha256(result.stdout.replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    home = read_text(HOME)
    profile = read_text(PROFILE)
    component = read_text(COMPONENT) if COMPONENT.exists() else ""
    actual_forbidden_sha = forbidden_diff_sha256()
    checks = {
        "component_exists": COMPONENT.exists(),
        "component_three_items": component.count('class="nav-item') == 3,
        "component_routes": all(route in component for route in ("/pages/home", "/pages/center", "/pages/profile")),
        "component_props": "active: 'home' | 'profile'" in component and "placement: 'absolute' | 'fixed'" in component,
        "component_active_guard": "if (props.active === target)" in component,
        "component_relaunch": "uni.reLaunch({ url })" in component,
        "component_visual_contract": all(token in component for token in ("height: 67px", "repeat(3,1fr)", "#ff5d5f", "width: 62px", "border: 4px solid #fff", "/static/brand/jixiangwu-logo.png", "AI助手")),
        "home_single_use": home.count("<HomeProfileTabBar") == 1 and home.count("class=\"bottom-nav\"") == 0,
        "profile_single_use": profile.count("<HomeProfileTabBar") == 1 and profile.count("AppDynamicTabBar") == 0,
        "profile_colors": all(token in profile for token in (
            "background: #F5F0EA;",
            "rgba(245, 240, 234, 0.2) 0%",
            "rgba(245, 240, 234, 0.9) 32%",
            "#F5F0EA 100%",
            "rgba(245, 240, 234, 0.34) 0%",
            "rgba(245, 240, 234, 0.14) 34%",
            "rgba(245, 240, 234, 0.42) 100%",
        )),
        "profile_old_colors_absent": not any(token in profile for token in ("#edf6ff", "rgba(239, 247, 255, 0.2)", "rgba(243, 249, 255, 0.9)", "#f6fbff", "rgba(236, 247, 255, 0.34)", "rgba(247, 251, 255, 0.14)", "rgba(239, 248, 255, 0.42)")),
        "gradient_structure": "linear-gradient(180deg" in profile and "center -30rpx / 100% auto no-repeat" in profile,
        "home_frozen": sha256_text(reconstruct_home(home)) == HOME_BASELINE_SHA256,
        "profile_business_frozen": sha256_text(reconstruct_profile(profile)) == PROFILE_BASELINE_SHA256,
        "forbidden_app_diff_frozen": actual_forbidden_sha == FORBIDDEN_DIFF_SHA256,
    }
    passed = all(checks.values())
    print(json.dumps({"passed": passed, "checks": checks, "actual_forbidden_diff_sha256": actual_forbidden_sha}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
