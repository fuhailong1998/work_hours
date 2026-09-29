# 非常规工时调整接口流程

用户授权：可读取 OA 工时、填写并保存草稿、返回链接；不得提交审批。可选择本人工时报表中的任一项目调出，也可调入公共项目；调入和调出项目不得相同。公共项目作为默认来源，在个人配置中维护。

入口流程 83592，运行流程 110092，表单 -1099，创建节点 111018。运行时从 `loadForm` 的 `tableInfo` 解析字段名和 ID，不固定项目 ID。

1. `/api/hrm/login/getAccountList`：验证当前 HTTP 会话员工。
2. `/ThunderSoft/proj/working/PrjWorkingReport2.jsp`：GET `resSDate/resEDate`，解析返回报表并验证逐日、逐列合计。
3. `/api/workflow/reqform/loadForm`：新建使用 `iscreate=1,workflowid=83592`；回读使用 `requestid`。
4. `/api/workflow/reqform/detailData`：读取默认行、已有行和动态表单参数。
5. `/api/public/browser/data/161`：按 OA 完整名称检索项目，唯一匹配且结果完整才使用。
6. `/api/workflow/linkage/reqDataInputResult`、`reqFieldSqlResult`：根据 `linkageCfg` 动态调用，补齐员工部门、项目经理等字段。
7. `/api/workflow/formula/assignValue`：处理汇总字段显示对象；保存规则计算见 `oa_rules.py`。
8. `/api/workflow/reqform/requestOperation`：仅 `src=save`、新建 requestid=-1。使用当前初始化得到的令牌及签名，不重用历史请求参数。
9. 收到 SUCCESS 和正整数 requestid 后先持久化编号，再通过 loadForm/detailData 回读核对。网络失败或保存结果不明不重试。

扫码认证通过公司 SSO 登录入口及飞书 `/accounts/qrlogin/init`、`/accounts/qrlogin/polling` HTTP 接口，二维码内容由接口令牌生成。扫码后的 v1 应用授权通过 `/open-apis/authen/v1/confirm` 完成，校验公司应用及回调地址，并传递当前会话的 CSRF 与授权 flow key。公司 SSO 返回 `Unknown RedirectUrl` 时保留扫码会话，重新获取 SSO 状态一次。中间会话与回调进度保存在权限为 0600 的本地文件中，恢复时不再轮询已消费的二维码。授权最终必须通过 OA 身份核验；未知额外认证步骤明确报错，不进行浏览器回退。

周期规则：月份 M 对应 M-1 月 25 日至 M 月 24 日。默认选择今天的自然月份，允许用户选择其他周期或日期。OA 保存时跨月审批路由保留 OA 自身的判断规则，不能用页面默认周期替换。

lark-cli 可用于发现外部审批入口；飞书原生审批创建 API 不适用于这条外部 OA 流程。旧浏览器调查文件仅在忽略的 `.local/` 目录，不参与项目运行。
