# ALCOEN QC 系统接口路由文档

> 本文档定义质量控制系统 (QC) 的所有后端路由接口规范，供前后端开发及后续维护参考。

---

## 1. 路由组织原则

QC 系统的 Flask Blueprint 统一注册为 `qc_bp`，URL 前缀为 `/qc`。认证相关的 QC 专属路由（如 QC 注册、QC 角色申请）放在 `auth_bp` 中。

---

## 2. 认证相关路由

### 2.1 系统选择门户页

| 属性 | 值 |
|------|-----|
| 路由 | `/` |
| 方法 | GET |
| Blueprint | `main_bp` |
| 模板 | `portal.html` |
| 说明 | 展示两个系统的大按钮入口 |

### 2.2 ERP 首页

| 属性 | 值 |
|------|-----|
| 路由 | `/erp/` |
| 方法 | GET |
| Blueprint | `main_bp` |
| 模板 | `index.html` |
| 说明 | 原 `main.index` 从 `/` 迁移至此 |

### 2.3 登录页（QC 入口）

| 属性 | 值 |
|------|-----|
| 路由 | `/auth/login` |
| 方法 | GET, POST |
| Blueprint | `auth_bp` |
| 模板 | `auth/login.html` |
| 查询参数 | `sub=qc`（标识从 QC 入口进入） |
| 说明 | 与 ERP 共用登录页，根据 `sub` 参数渲染不同标题和注册链接 |

### 2.4 QC 快捷登录入口

| 属性 | 值 |
|------|-----|
| 路由 | `/auth/login/qc` |
| 方法 | GET |
| Blueprint | `auth_bp` |
| 行为 | `redirect(url_for('auth.login', sub='qc'))` |

### 2.5 QC 注册页

| 属性 | 值 |
|------|-----|
| 路由 | `/auth/register/qc` |
| 方法 | GET, POST |
| Blueprint | `auth_bp` |
| 模板 | `auth/register_qc.html` |
| 说明 | QC 专属注册页面，角色下拉框仅显示 QC 相关角色 |

### 2.6 QC 角色申请页（ERP 老用户首次登录 QC）

| 属性 | 值 |
|------|-----|
| 路由 | `/auth/qc-role-apply` |
| 方法 | GET, POST |
| Blueprint | `auth_bp` |
| 模板 | `auth/qc_role_apply.html` |
| 装饰器 | `@login_required` |
| 说明 | 已登录 ERP 账号但未绑定 QC 角色的用户，在此选择 QC 角色并提交审核 |

---

## 3. QC 仪表盘路由

### 3.1 QC 首页

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/` |
| 方法 | GET |
| Blueprint | `qc_bp` |
| 模板 | `qc/dashboard.html` |
| 装饰器 | `@login_required` + 检查 QC 角色 |
| 说明 | 展示待质控、待质检、待验收、已验收统计卡片及最近订单 |

---

## 4. 质量控制模块路由

### 4.1 工件订单列表

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-control/` |
| 方法 | GET |
| Blueprint | `qc_bp` |
| 模板 | `qc/work_order_list.html` |
| 查询参数 | `page`, `status`, `keyword` |
| 装饰器 | `@login_required` + `qc_work_order_view` |
| 说明 | 按权限过滤列表；质控员只能看自己的订单；高管看全部 |

### 4.2 新增工件订单

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-control/new` |
| 方法 | GET, POST |
| Blueprint | `qc_bp` |
| 模板 | `qc/work_order_form.html` |
| 装饰器 | `@login_required` + `qc_work_order_create` |
| 说明 | GET 展示空白表单；POST 接收表单数据并创建订单和附件记录 |

### 4.3 编辑工件订单

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-control/<int:order_id>/edit` |
| 方法 | GET, POST |
| Blueprint | `qc_bp` |
| 模板 | `qc/work_order_form.html` |
| 装饰器 | `@login_required` + `qc_work_order_edit` |
| 说明 | 仅允许编辑 `status` 为 `qc_pending` 或 `rejected` 的订单；已推送的不允许编辑 |

### 4.4 删除工件订单

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-control/<int:order_id>/delete` |
| 方法 | POST |
| Blueprint | `qc_bp` |
| 装饰器 | `@login_required` + `qc_work_order_delete` |
| 说明 | 软删除/物理删除（根据项目惯例，此处采用物理删除，级联删除附件文件） |

### 4.5 质控完成推送

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-control/<int:order_id>/complete` |
| 方法 | POST |
| Blueprint | `qc_bp` |
| 装饰器 | `@login_required` + `qc_work_order_create`（质控员主导） |
| 表单参数 | `inspector_id`（目标质检员） |
| 说明 | 校验所有必填项已填，更新状态为 `qc_completed`，设置 `inspector_id` |

### 4.6 图纸/作业指导书上传（AJAX）

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-control/<int:order_id>/upload` |
| 方法 | POST |
| Blueprint | `qc_bp` |
| 说明 | 通用文件上传接口，支持图纸、作业指导书、检测点图片、备注图片 |
| 返回 | JSON `{"success": true, "attachment_id": 123, "url": "..."}` |

### 4.7 删除附件

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-control/attachments/<int:attachment_id>/delete` |
| 方法 | POST |
| Blueprint | `qc_bp` |
| 说明 | 删除指定附件记录及物理文件 |

---

## 5. 质量检测模块路由

### 5.1 待检测订单列表

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-inspection/` |
| 方法 | GET |
| Blueprint | `qc_bp` |
| 模板 | `qc/inspection_list.html` |
| 查询参数 | `page`, `keyword` |
| 装饰器 | `@login_required` + `qc_inspection_perform` 或 `qc_work_order_view` |
| 说明 | 仅展示 `status IN ('qc_completed', 'inspection_pending')` 的订单 |

### 5.2 质检详情页

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-inspection/<int:order_id>` |
| 方法 | GET |
| Blueprint | `qc_bp` |
| 模板 | `qc/work_order_detail_inspector.html` |
| 装饰器 | `@login_required` + 可见性检查 |
| 说明 | 展示订单全部内容 + 各栏目质检交互区 |

### 5.3 提交质检结果

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/quality-inspection/<int:order_id>/submit` |
| 方法 | POST |
| Blueprint | `qc_bp` |
| 装饰器 | `@login_required` + `qc_inspection_perform` |
| 表单参数 | 动态生成的各 `attachment_id` 对应的 `result` 和 `remark` |
| 说明 | 保存所有质检记录，根据结果决定状态流转：全部 `pass` → `inspection_completed`；存在 `fail` → `rejected` |

---

## 6. 验收模块路由

### 6.1 验收列表

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/acceptance/` |
| 方法 | GET |
| Blueprint | `qc_bp` |
| 模板 | `qc/acceptance_list.html` |
| 查询参数 | `page`, `keyword` |
| 装饰器 | `@login_required` + 可见性检查 |
| 说明 | 展示 `status IN ('inspection_completed', 'accepted')` 的订单 |

### 6.2 验收确认页

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/acceptance/<int:order_id>` |
| 方法 | GET |
| Blueprint | `qc_bp` |
| 模板 | `qc/acceptance_detail.html` |
| 装饰器 | `@login_required` + 可见性检查 |
| 说明 | 展示最终确认表格和双签按钮 |

### 6.3 验收签字

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/acceptance/<int:order_id>/sign` |
| 方法 | POST |
| Blueprint | `qc_bp` |
| 装饰器 | `@login_required` + 角色检查 |
| 说明 | 当前用户作为质控员或质检员签字；记录到 `qc_acceptance_signatures`；当两条记录都存在时，自动将订单状态更新为 `accepted` |

### 6.4 撤销验收

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/acceptance/<int:order_id>/rollback` |
| 方法 | POST |
| Blueprint | `qc_bp` |
| 装饰器 | `@login_required` + `qc_acceptance_rollback` |
| 表单参数 | `target` (`'qc'` 或 `'inspection'`), `reason` |
| 说明 | 删除签字记录，状态回退到 `qc_pending`（target=qc）或 `inspection_pending`（target=inspection），记录原因 |

### 6.5 打印验收清单

| 属性 | 值 |
|------|-----|
| 路由 | `/qc/acceptance/<int:order_id>/print` |
| 方法 | GET |
| Blueprint | `qc_bp` |
| 模板 | `qc/acceptance_print.html` |
| 装饰器 | `@login_required` + 可见性检查 |
| 说明 | 纯展示页面，无导航栏，优化打印样式 |

---

## 7. 共享管理路由的扩展

### 7.1 用户列表增加 QC 用户筛选

| 属性 | 值 |
|------|-----|
| 路由 | `/user/` |
| 方法 | GET |
| 说明 | 现有路由，需增加 `role` 筛选选项中的 `qc_controller` 和 `qc_inspector` |

### 7.2 待审核用户列表

| 属性 | 值 |
|------|-----|
| 路由 | `/user/pending` |
| 方法 | GET |
| 说明 | 现有路由，需同时展示 ERP 待审核用户和 QC 待审核用户（`qc_user_bindings.is_active = 0`） |

### 7.3 审核通过 QC 用户

| 属性 | 值 |
|------|-----|
| 路由 | `/user/<int:user_id>/approve-qc` |
| 方法 | POST |
| Blueprint | `user_bp` |
| 装饰器 | `@login_required` + `user_approve` |
| 说明 | 仅更新 `qc_user_bindings.is_active = 1`，不修改 ERP 账号状态 |

---

## 8. 静态文件服务

### 8.1 QC 附件访问

| 属性 | 值 |
|------|-----|
| 路由 | `/uploads/qc/<path:filename>` |
| 方法 | GET |
| 说明 | 通过 Flask `send_from_directory` 提供 `static/uploads/qc/` 目录下的文件访问 |

---

## 9. 返回规范

### 9.1 页面路由
- 成功：渲染模板或重定向
- 失败：`flash(message, category)` 后重定向回上一页

### 9.2 AJAX 路由（如上传）
```json
{
    "success": true,
    "attachment_id": 123,
    "url": "/uploads/qc/1/drawing_xxx.png",
    "message": "上传成功"
}
```

或

```json
{
    "success": false,
    "message": "文件格式不支持"
}
```

---

## 10. 路由汇总表

| 路由 | 方法 | 功能 | 主要角色 |
|------|------|------|---------|
| `/` | GET | 系统选择门户 | 所有访客 |
| `/erp/` | GET | ERP 首页 | ERP 用户 |
| `/auth/login` | GET/POST | 登录（ERP/QC） | 所有用户 |
| `/auth/login/qc` | GET | QC 快捷登录 | QC 用户 |
| `/auth/register/qc` | GET/POST | QC 注册 | QC 新用户 |
| `/auth/qc-role-apply` | GET/POST | QC 角色申请 | ERP 老用户 |
| `/qc/` | GET | QC 仪表盘 | QC 用户 |
| `/qc/quality-control/` | GET | 工件订单列表 | 质控员/高管 |
| `/qc/quality-control/new` | GET/POST | 新增工件订单 | 质控员 |
| `/qc/quality-control/<id>/edit` | GET/POST | 编辑工件订单 | 质控员 |
| `/qc/quality-control/<id>/delete` | POST | 删除工件订单 | 质控员/高管 |
| `/qc/quality-control/<id>/complete` | POST | 完成质控推送 | 质控员 |
| `/qc/quality-control/<id>/upload` | POST | 附件上传 | 质控员 |
| `/qc/quality-control/attachments/<id>/delete` | POST | 删除附件 | 质控员 |
| `/qc/quality-inspection/` | GET | 待检测列表 | 质检员/高管 |
| `/qc/quality-inspection/<id>` | GET | 质检详情页 | 质检员/高管 |
| `/qc/quality-inspection/<id>/submit` | POST | 提交质检结果 | 质检员 |
| `/qc/acceptance/` | GET | 验收列表 | 质控员/质检员/高管 |
| `/qc/acceptance/<id>` | GET | 验收确认页 | 质控员/质检员/高管 |
| `/qc/acceptance/<id>/sign` | POST | 验收签字 | 质控员/质检员 |
| `/qc/acceptance/<id>/rollback` | POST | 撤销验收 | 高管/质控员 |
| `/qc/acceptance/<id>/print` | GET | 打印验收清单 | 质控员/质检员/高管 |
| `/user/<id>/approve-qc` | POST | 审核 QC 绑定 | 管理员 |
