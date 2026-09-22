# answer.vue 既有 dirty 保护记录

## 应用修改前

`git diff -- code/develop/yunjikeji/src/pages/practice/answer.vue` 显示三块既有未提交改动，本任务不归因、不回退：

1. `@/services/practice` import 新增 `fetchAnswerCard`。
2. `loadQuestion` 后新增 `loadInitialQuestion`，通过答题卡定位未完成题目。
3. `onLoad` 从 `loadQuestion(0)` 改为 `void loadInitialQuestion()`。

本任务预期只在 `submitAnswer` 新增第四个差异块：删除正确答案提交后自动调用 `goNext()` 的分支。

## 应用修改后

再次执行 `git diff -- code/develop/yunjikeji/src/pages/practice/answer.vue`，结果仍为四块：

1. import 中的 `fetchAnswerCard` 既有 hunk 保留。
2. `loadInitialQuestion` 既有 hunk 保留，内容未回退。
3. `submitAnswer` 新增 DEV-060 hunk，仅删除：

```ts
if (answerResult.value.correct) {
  await goNext()
  return
}
```

4. `onLoad` 使用 `void loadInitialQuestion()` 的既有 hunk 保留。

未执行 `git add`、`git commit` 或 `git push`；未修改 `uni_modules/**`。
