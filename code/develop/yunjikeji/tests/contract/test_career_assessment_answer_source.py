from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANSWER_PAGE = ROOT / "src/pages/practice/career-assessment-answer.vue"
REPORT_PAGE = ROOT / "src/pages/center/career-assessment-report.vue"


def assert_contains(text: str, needle: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing contract: {needle}")


def assert_not_contains(text: str, needle: str) -> None:
    if needle in text:
        raise AssertionError(f"unexpected contract: {needle}")


def main() -> None:
    answer_source = ANSWER_PAGE.read_text(encoding="utf-8")
    report_source = REPORT_PAGE.read_text(encoding="utf-8")

    assert_contains(answer_source, "import CoreScaleQuestionGroup from '@/components/practice/CoreScaleQuestionGroup.vue'")
    assert_contains(answer_source, ":group-start-index=\"interestGroupStartIndex\"")
    assert_contains(answer_source, "variant=\"supplement\"")
    assert_contains(answer_source, "section-title=\"兴趣倾向\"")
    assert_contains(answer_source, "const CAREER_INTEREST_STEP = '兴趣倾向'")
    assert_contains(answer_source, "const INTEREST_GROUP_START_INDEX = 13")
    assert_contains(answer_source, "const INTEREST_GROUP_END_INDEX = 24")
    assert_contains(answer_source, "const INTEREST_GROUP_ERROR = '职业规划兴趣倾向题目分组异常，请联系管理员检查题库配置'")
    assert_contains(answer_source, "const interestGroupReady = ref(false)")
    assert_contains(answer_source, "candidate.stepName?.trim() === CAREER_INTEREST_STEP")
    assert_contains(answer_source, "candidate.index === INTEREST_GROUP_START_INDEX + offset")
    assert_contains(answer_source, "&& interestGroupReady.value")
    assert_contains(answer_source, "const loadInterestGroup = async (seedQuestion: CareerAssessmentQuestion) => {")
    assert_contains(answer_source, "await loadInterestGroup(cached)")
    assert_contains(answer_source, "await loadInterestGroup(page.question)")
    assert_contains(answer_source, "await loadInterestGroup(firstPage.question)")
    assert_contains(answer_source, "currentIndex.value = INTEREST_GROUP_START_INDEX")
    assert_contains(answer_source, "interestGroupReady.value = true")
    assert_contains(answer_source, "currentIndex.value === INTEREST_GROUP_END_INDEX + 1")
    assert_contains(answer_source, "currentIndex.value = INTEREST_GROUP_START_INDEX")
    assert_contains(answer_source, ">上一组</button>")
    assert_contains(answer_source, "isLastQuestion ? '提交并生成报告' : '下一组'")
    assert_contains(answer_source, "SelfTestLoadingOverlay :show=\"status === 'loading'\"")
    assert_contains(answer_source, "submittedDialogVisible.value = true")
    assert_contains(answer_source, "const loadedQuestions = Object.values(questionCache.value).sort((left, right) => left.index - right.index)")

    assert_contains(report_source, "if (report.reportStatus === 'FAILED') {")
    assert_contains(report_source, "generating.value = false")
    assert_contains(report_source, "stopPolling()")
    assert_contains(report_source, ":show=\"!reportOverlayDismissed && !errorMessage && (loading || generating)\"")
    assert_contains(report_source, "@close=\"dismissReportOverlay\"")
    assert_contains(report_source, "const reportOverlayDismissed = ref(false)")
    assert_contains(report_source, "reportOverlayDismissed.value = true")
    assert_contains(report_source, "reportOverlayDismissed.value = false")
    assert_not_contains(report_source, "career-report__home")


if __name__ == "__main__":
    main()
