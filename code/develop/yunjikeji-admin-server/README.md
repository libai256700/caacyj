# 云技科技飞行学院后台管理平台后端

本目录基于既有后端模板落地为当前项目的后台管理端工程，目录名为 `code/develop/yunjikeji-admin-server`。

## 项目定位

- 面向云技科技飞行学院后台管理平台
- 与现有 APP 后端 `code/develop/yunjikeji-server` 并行存在
- 保留模板的多模块能力，作为后台管理端业务开发基础

## 当前工程结构

- `pom.xml`：父工程，统一依赖与构建版本
- `yunjikeji-admin-server`：启动工程
- `yudao-framework`：公共框架
- `yudao-module-*`：各业务模块

## 本地默认配置

- 应用名：`yunjikeji-admin-server`
- 本地端口：`48080`
- 本地数据库：`yunjikeji_admin`
- Swagger 地址：`http://127.0.0.1:48080/swagger-ui`

## 说明

- 本次处理目标是“将模板转换为云技科技后台项目”，不是简单克隆
- 当前阶段优先完成项目命名、启动入口、目录结构和本地配置落地
- 后续业务开发需按版本计划继续补充库表设计、建表脚本与模块实现
