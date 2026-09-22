# Story-052 手工初始化工具

仅人工显式执行，默认 `dry-run`，不被业务代码、启动、构建、迁移或定时任务引用。

## 分类14题库

```bash
python career_question_import.py ^
  --source-dir "D:\飞机\-APP--main (4)\-APP--main\skills\career-planning-coach" ^
  --db-host "<当前应用数据库 host>" ^
  --db-port <当前应用数据库 port> ^
  --db-name "<当前应用数据库名>" ^
  --db-user "<数据库用户>" ^
  --db-password-env STORY052_DB_PASSWORD
```

显式执行写入时额外追加 `--apply`。

## Agent 3

```bash
python career_agent_init.py ^
  --source-file "D:\飞机\-APP--main (4)\-APP--main\skills\career-planning-coach\scripts\career-core.mjs" ^
  --id 3 ^
  --apply
```

数据库账号通过环境变量传入，具体变量名以 `career_agent_init.py` 参数说明为准。

## 回执模板

```text
执行日期：
执行人：
工具名称：
运行模式：dry-run / apply
源目录：
应用配置：
目标库：
源哈希：
回读结果：
备份产物：
结论：
```
