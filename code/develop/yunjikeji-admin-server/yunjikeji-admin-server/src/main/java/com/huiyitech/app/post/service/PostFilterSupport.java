package com.huiyitech.app.post.service;

import com.huiyitech.postcollect.dal.dataobject.postcollect.PostCollectDO;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class PostFilterSupport {

    private static final String OTHER_KEYWORD_SENTINEL = "__other__";
    private static final List<String> OTHER_KEYWORD_EXCLUDES = Arrays.asList("飞手", "工程师", "教培");
    private static final Map<String, List<String>> PROVINCE_ALIAS_MAP = createProvinceAliasMap();

    private PostFilterSupport() {
    }

    static List<PostCollectDO> filterPosts(List<PostCollectDO> posts, String name, String workArea, String salaryRange) {
        List<PostCollectDO> filtered = new ArrayList<>();
        for (PostCollectDO post : posts) {
            if (!matchesName(post.getName(), name)) {
                continue;
            }
            if (!matchesWorkArea(post.getWorkArea(), workArea)) {
                continue;
            }
            if (!matchesSalaryRange(post.getSalaryRange(), salaryRange)) {
                continue;
            }
            filtered.add(post);
        }
        return filtered;
    }

    static boolean matchesName(String actualName, String expectedName) {
        if (!StringUtils.hasText(expectedName)) {
            return true;
        }
        if (isOtherKeywordFilter(expectedName)) {
            return matchesOtherKeyword(actualName);
        }
        return normalizeText(actualName).contains(normalizeText(expectedName));
    }

    private static boolean matchesOtherKeyword(String actualName) {
        if (!StringUtils.hasText(actualName)) {
            return true;
        }
        String normalizedName = normalizeText(actualName);
        for (String keyword : OTHER_KEYWORD_EXCLUDES) {
            if (normalizedName.contains(normalizeText(keyword))) {
                return false;
            }
        }
        return true;
    }

    private static boolean isOtherKeywordFilter(String expectedName) {
        return OTHER_KEYWORD_SENTINEL.equalsIgnoreCase(expectedName.trim());
    }

    static boolean matchesWorkArea(String actualWorkArea, String selectedProvince) {
        if (!StringUtils.hasText(selectedProvince)) {
            return true;
        }
        if (!StringUtils.hasText(actualWorkArea)) {
            return false;
        }
        String normalizedArea = normalizeText(actualWorkArea);
        for (String alias : aliasesForProvince(selectedProvince)) {
            if (normalizedArea.contains(normalizeText(alias))) {
                return true;
            }
        }
        return false;
    }

    static boolean matchesSalaryRange(String actualSalaryRange, String selectedSalaryRange) {
        if (!StringUtils.hasText(selectedSalaryRange)) {
            return true;
        }
        SalaryInterval selected = parseSelectedSalaryRange(selectedSalaryRange);
        if (selected == null) {
            return true;
        }
        SalaryInterval actual = parseSalaryRange(actualSalaryRange);
        if (actual == null) {
            return false;
        }
        return actual.min <= selected.max && actual.max >= selected.min;
    }

    private static List<String> aliasesForProvince(String selectedProvince) {
        List<String> aliases = PROVINCE_ALIAS_MAP.get(selectedProvince);
        if (aliases != null) {
            return aliases;
        }
        return Arrays.asList(selectedProvince, selectedProvince.replace("省", "").replace("市", ""));
    }

    private static SalaryInterval parseSelectedSalaryRange(String selectedSalaryRange) {
        String normalized = selectedSalaryRange == null ? "" : selectedSalaryRange.trim()
                .replace(" ", "")
                .replace("　", "")
                .replace("元", "");
        String[] parts = normalized.split("-");
        if (parts.length != 2) {
            return null;
        }
        try {
            int min = Integer.parseInt(parts[0]);
            int max = Integer.parseInt(parts[1]);
            return new SalaryInterval(Math.min(min, max), Math.max(min, max));
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private static SalaryInterval parseSalaryRange(String salaryRange) {
        if (!StringUtils.hasText(salaryRange)) {
            return null;
        }
        String normalized = normalizeSalaryText(salaryRange);
        if (!StringUtils.hasText(normalized) || normalized.contains("面议")
                || normalized.contains("/天") || normalized.contains("每天")
                || normalized.contains("/时") || normalized.contains("小时")
                || normalized.contains("/年") || normalized.contains("年薪")) {
            return null;
        }
        List<SalaryToken> tokens = extractSalaryTokens(normalized);
        if (tokens.isEmpty()) {
            return null;
        }
        if (tokens.size() == 1) {
            long value = resolveTokenValue(tokens.get(0), null, normalized);
            if (value <= 0) {
                return null;
            }
            if (normalized.contains("以上") || normalized.contains("+")) {
                return new SalaryInterval((int) value, Integer.MAX_VALUE);
            }
            if (normalized.contains("以下")) {
                return new SalaryInterval(0, (int) value);
            }
            return new SalaryInterval((int) value, (int) value);
        }

        SalaryToken first = tokens.get(0);
        SalaryToken second = tokens.get(1);
        long firstValue = resolveTokenValue(first, second, normalized);
        long secondValue = resolveTokenValue(second, first, normalized);
        if (firstValue <= 0 || secondValue <= 0) {
            return null;
        }
        long min = Math.min(firstValue, secondValue);
        long max = Math.max(firstValue, secondValue);
        return new SalaryInterval((int) min, max > Integer.MAX_VALUE ? Integer.MAX_VALUE : (int) max);
    }

    private static List<SalaryToken> extractSalaryTokens(String normalized) {
        List<SalaryToken> tokens = new ArrayList<>();
        java.util.regex.Matcher matcher = java.util.regex.Pattern
                .compile("(\\d+(?:\\.\\d+)?)\\s*([kKwW万千]?)")
                .matcher(normalized);
        while (matcher.find()) {
            String numberText = matcher.group(1);
            String unitText = matcher.group(2);
            if (!StringUtils.hasText(numberText)) {
                continue;
            }
            tokens.add(new SalaryToken(Double.parseDouble(numberText), unitText));
            if (tokens.size() == 2) {
                break;
            }
        }
        return tokens;
    }

    private static long resolveTokenValue(SalaryToken token, SalaryToken sibling, String normalized) {
        String unit = token.unit;
        if (!StringUtils.hasText(unit) && sibling != null && StringUtils.hasText(sibling.unit)) {
            unit = sibling.unit;
        }
        long multiplier = unitMultiplier(unit);
        if (multiplier == 1 && !StringUtils.hasText(unit) && normalized.contains("万")) {
            multiplier = 10_000L;
        }
        if (multiplier == 1 && !StringUtils.hasText(unit) && normalized.toLowerCase(Locale.ROOT).contains("k")) {
            multiplier = 1_000L;
        }
        return Math.round(token.value * multiplier);
    }

    private static long unitMultiplier(String unit) {
        if (!StringUtils.hasText(unit)) {
            return 1L;
        }
        String normalizedUnit = unit.toLowerCase(Locale.ROOT);
        if ("k".equals(normalizedUnit)) {
            return 1_000L;
        }
        if ("w".equals(normalizedUnit) || "万".equals(normalizedUnit)) {
            return 10_000L;
        }
        if ("千".equals(normalizedUnit)) {
            return 1_000L;
        }
        return 1L;
    }

    private static String normalizeText(String value) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        return value.trim()
                .replace(" ", "")
                .replace("　", "")
                .replace("-", "")
                .replace("－", "")
                .replace("—", "")
                .replace("_", "")
                .toLowerCase(Locale.ROOT);
    }

    private static String normalizeSalaryText(String value) {
        return value == null ? "" : value.trim()
                .replace(" ", "")
                .replace("　", "")
                .replace("·", "")
                .replace("／", "/")
                .replace("～", "-")
                .replace("~", "-")
                .replace("至", "-")
                .replace("—", "-")
                .replace("－", "-")
                .replace("元/月", "")
                .replace("元每月", "")
                .replace("月薪", "")
                .replace("每月", "")
                .replace("/月", "")
                .replace("人民币", "")
                .toLowerCase(Locale.ROOT);
    }

    private static Map<String, List<String>> createProvinceAliasMap() {
        Map<String, List<String>> aliases = new LinkedHashMap<>();
        putProvince(aliases, "北京市", "北京");
        putProvince(aliases, "天津市", "天津");
        putProvince(aliases, "上海市", "上海");
        putProvince(aliases, "重庆市", "重庆");
        putProvince(aliases, "河北省", "河北", "石家庄");
        putProvince(aliases, "山西省", "山西", "太原");
        putProvince(aliases, "辽宁省", "辽宁", "沈阳");
        putProvince(aliases, "吉林省", "吉林", "长春");
        putProvince(aliases, "黑龙江省", "黑龙江", "哈尔滨");
        putProvince(aliases, "江苏省", "江苏", "南京");
        putProvince(aliases, "浙江省", "浙江", "杭州");
        putProvince(aliases, "安徽省", "安徽", "合肥");
        putProvince(aliases, "福建省", "福建", "福州");
        putProvince(aliases, "江西省", "江西", "南昌");
        putProvince(aliases, "山东省", "山东", "济南");
        putProvince(aliases, "河南省", "河南", "郑州");
        putProvince(aliases, "湖北省", "湖北", "武汉");
        putProvince(aliases, "湖南省", "湖南", "长沙");
        putProvince(aliases, "广东省", "广东", "广州");
        putProvince(aliases, "海南省", "海南", "海口");
        putProvince(aliases, "四川省", "四川", "成都");
        putProvince(aliases, "贵州省", "贵州", "贵阳");
        putProvince(aliases, "云南省", "云南", "昆明");
        putProvince(aliases, "陕西省", "陕西", "西安");
        putProvince(aliases, "甘肃省", "甘肃", "兰州");
        putProvince(aliases, "青海省", "青海", "西宁");
        putProvince(aliases, "台湾省", "台湾", "台北");
        putProvince(aliases, "内蒙古自治区", "内蒙古", "呼和浩特");
        putProvince(aliases, "广西壮族自治区", "广西", "南宁");
        putProvince(aliases, "西藏自治区", "西藏", "拉萨");
        putProvince(aliases, "宁夏回族自治区", "宁夏", "银川");
        putProvince(aliases, "新疆维吾尔自治区", "新疆", "乌鲁木齐");
        putProvince(aliases, "香港特别行政区", "香港");
        putProvince(aliases, "澳门特别行政区", "澳门");
        return aliases;
    }

    private static void putProvince(Map<String, List<String>> aliases, String province, String... extraAliases) {
        List<String> values = new ArrayList<>();
        values.add(province);
        values.add(province.replace("省", "").replace("市", "").replace("壮族自治区", "")
                .replace("回族自治区", "").replace("维吾尔自治区", "").replace("自治区", "")
                .replace("特别行政区", ""));
        values.addAll(Arrays.asList(extraAliases));
        aliases.put(province, values);
    }

    private static final class SalaryToken {
        private final double value;
        private final String unit;

        private SalaryToken(double value, String unit) {
            this.value = value;
            this.unit = unit;
        }
    }

    private static final class SalaryInterval {
        private final int min;
        private final int max;

        private SalaryInterval(int min, int max) {
            this.min = min;
            this.max = max;
        }
    }
}
