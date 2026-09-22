# AC-ORGBIND-201 学员基础信息落库

- 类型：技术-数据级
- 正式入口：`/app-api/yj/customer-info/save` 的 `AppCustomerInfoSaveReqVO`
- 支撑的业务结果：当前登录学员提交组织申请前，真实姓名、身份证号、性别先同步保存到 `yj_customer_info`。
- 技术边界：保存与更新都必须写入当前学员对应的 `customer_account_id` 记录，更新已有记录时保持主键与关联关系稳定；取消不产生任何数据变更。
- 通过条件：`CustomerServiceImpl.saveCustomerInfo` 将 `realName`、`idCard`、`sex` 同步到 `yj_customer_info`，并能被后续组织申请流程承接。
- 证据承接方式：以 `CustomerInfoDO`、`CustomerServiceImpl.java` 与后续正式测试/数据核对结果为准。
