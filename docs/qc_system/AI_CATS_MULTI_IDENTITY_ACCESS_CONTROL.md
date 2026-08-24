# AI CATS 多身份与权限收口开发文档

> 文档状态：已开发并通过本地全量验收
>
> 文档版本：v1.0
>
> 编制日期：2026-08-21
>
> 适用范围：AI CATS 配件生产、装配/出厂、研究/实验，以及 AI CATS 独立注册、身份审核和用户管理

---

## 1. 决策摘要

本次改造采用以下最终业务决策：

1. 一个用户可以同时拥有多个 AI CATS 身份。
2. 用户注册或已有 ERP 用户申请 AI CATS 权限时，可以一次选择多个身份。
3. 总经理、总经理助理和超级管理员可以在后台增加、启用、停用或撤销用户身份。
4. “配件生产”和“装配/出厂”默认由同一组身份操作，不为两个模块重复创建相同身份。
5. 对外及界面统一使用“供应商”这一名称，不使用“供应商/质量检测人员”“质检员”或“质检人”作为身份名称。
6. 总经理和总经理助理拥有全部 AI CATS 业务权限。
7. 超级管理员保留技术维护和紧急处置权限，但不作为普通业务身份参与权限分配。
8. 其他用户只能访问其已生效身份、已启用模块范围和本人参与记录共同允许的内容。
9. 多身份不能绕过双方确认、订单参与人和数据隔离规则。
10. 只有完成身份迁移和权限回归后，才能关闭测试期完全放开开关。

本文档是后续 AI CATS 身份和权限开发的权威依据。既有 `QC_PERMISSIONS.md` 中的单身份设计仅用于理解历史实现，不再作为目标设计。

---

## 2. 背景与现状

### 2.1 已具备的注册入口

AI CATS 当前已经具有独立认证入口，无需重新建设一套登录系统：

| 功能 | 当前路由 | 当前模板 |
| --- | --- | --- |
| AI CATS 登录 | `/auth/login/qc` | 共用 `templates/auth/login.html` |
| AI CATS 独立注册 | `/auth/register/qc` | `templates/auth/register_qc.html` |
| ERP 用户申请 AI CATS 身份 | `/auth/qc-role-apply` | `templates/auth/qc_role_apply.html` |
| AI CATS 待审核用户 | `/qc/admin/pending` | `templates/qc/admin_pending.html` |
| AI CATS 用户管理 | `/qc/admin/users` | `templates/qc/admin_users.html` |

现有页面、邮箱验证码、密码策略和 `users` 表均继续复用。本次只扩展多身份申请、审核、修改和权限解析能力。

### 2.2 当前实现的主要问题

1. 注册页和 ERP 用户申请页都只能选择一个角色。
2. `QCUserBinding` 虽然是独立表，但登录和权限逻辑普遍通过 `.first()` 获取单条绑定。
3. 用户一旦存在绑定记录，就不能继续申请其他身份。
4. AI CATS 业务权限仍有代码直接读取 `User.role`，没有统一读取已审批的 AI CATS 身份。
5. 测试期配置默认把普通已激活 ERP 用户映射为总经理助理，导致权限完全放开。
6. 现有 `qc_controller` 和 `qc_inspector` 同时承载多个模块语义，容易出现跨模块误授权。
7. 总经理助理虽然应有全部业务权限，但当前不能进入 AI CATS 用户审核后台。
8. 出厂模块仍保留测试期宽松权限和双角色确认逻辑。
9. 管理后台只能启停账号、重置密码或修改整个角色的权限，不能修改单个用户的身份组合。
10. 当前 AI CATS 管理后台直接切换 `User.is_active`，对 ERP 共享账号可能连带影响 ERP 登录。

### 2.3 测试开关关闭顺序

开发前不得直接把 `AI_CATS_TEST_OPEN_ACCESS` 改为关闭状态，因为旧绑定身份尚未完整参与权限解析。当前实现已完成统一身份解析、旧身份迁移和主要权限矩阵回归，因此代码默认值已关闭；生产配置会强制忽略旧的全开放环境变量，部署时仍须先备份、迁移并核对身份。

正确顺序是：先建设多身份解析，迁移现有身份，完成权限矩阵测试，最后关闭完全放开开关。

---

## 3. 目标与非目标

### 3.1 开发目标

1. 建立与 ERP 主角色解耦的 AI CATS 多身份体系。
2. 复用现有 AI CATS 独立注册页，并改造成多选身份申请。
3. 支持 ERP 用户增量申请新的 AI CATS 身份。
4. 支持管理员对单个用户的身份和模块范围进行维护。
5. 配件生产和装配/出厂默认共用“质量控制人”和“供应商”两种身份。
6. 研究/实验继续使用独立的“研究人员”和“指导/验收人员”身份。
7. 统一菜单、列表、详情、附件、打印、下载和写操作的后端权限校验。
8. 保证现有订单、库存、签名、附件和历史记录不被迁移修改。
9. 收回普通 ERP 用户的临时完全权限。

### 3.2 非目标

1. 本次不重做登录、密码或邮箱验证码系统。
2. 本次不修改配件生产、装配、研究和出厂的业务状态机。
3. 本次不允许管理员为单个用户自由勾选底层权限码。
4. 本次不删除历史 `QCUserBinding` 表和旧角色代码。
5. 本次不修改现有业务订单中的参与人、签名人和历史记录。

管理员只维护“身份”和“模块范围”，具体权限由固定权限矩阵决定，避免人工拼接权限造成越权。

---

## 4. 术语与命名规范

### 4.1 系统名称

所有新增页面、提示、日志和测试统一使用 `AI CATS`，不再新增 `QC 系统` 作为用户可见名称。

数据库历史表名、旧路由变量和迁移兼容代码可以暂时保留 `qc` 前缀，避免破坏旧数据。

### 4.2 身份名称

| 身份代码 | 唯一用户可见名称 | 禁止使用的身份名称 |
| --- | --- | --- |
| `controller` | 质量控制人 | 质控员、装配负责人 |
| `supplier` | 供应商 | 供应商/质量检测人员、质量检测人员、质检员、质检人 |
| `researcher` | 研究人员 | 研发客户、A 客户 |
| `research_reviewer` | 指导/验收人员 | 指导客户、B 客户 |

“质量检测”可以继续作为业务流程或页面名称，但执行该流程的身份统一显示为“供应商”。例如：

- 正确：`供应商确认`
- 正确：`请指派供应商`
- 正确：`该订单等待供应商完成质量检测`
- 错误：`请指派供应商/质量检测人员`
- 错误：`质检员确认`

### 4.3 模块代码

| 模块代码 | 用户可见名称 | 说明 |
| --- | --- | --- |
| `production` | 配件生产 | 工件库、质量控制、质量检测、验收 |
| `assembly` | 装配/出厂 | 产品/工件库、发起装配、质量检测、验收、出厂 |
| `research` | 研究/实验 | 研究项目、研究批次、指导审批、共同验收 |

出厂是装配/出厂模块的子能力，不再单独设置“出厂人员”身份。

---

## 5. 身份目录与默认模块范围

### 5.1 普通业务身份

| 身份 | 默认模块范围 | 注册可选 | 主要职责 |
| --- | --- | --- | --- |
| 质量控制人 | 配件生产、装配/出厂 | 是 | 工件和产品维护、发起生产、发起装配、质控方验收、出厂操作 |
| 供应商 | 配件生产、装配/出厂 | 是 | 被指派订单的质量检测、材料上传、供应商确认、供应商方验收 |
| 研究人员 | 研究/实验 | 是 | 研究项目维护、发起研究批次、研究方验收 |
| 指导/验收人员 | 研究/实验 | 是 | 被指派批次的指导审批和指导方验收 |

质量控制人和供应商在注册时只选择一次，系统默认同时创建 `production` 和 `assembly` 两个模块范围。管理员审核或后续编辑时，可以关闭其中一个范围。

### 5.2 管理身份

| ERP 身份 | AI CATS 权限 |
| --- | --- |
| 总经理 | 自动拥有全部模块、全部数据和全部业务操作权限 |
| 总经理助理 | 自动拥有全部模块、全部数据和全部业务操作权限 |
| 超级管理员 | 拥有技术维护、身份管理和紧急业务处置权限 |

总经理、总经理助理和超级管理员不需要创建普通身份分配记录，也不能从公开注册页申请。

### 5.3 普通 ERP 用户

普通 ERP 用户没有生效的 AI CATS 身份时：

1. 不能切换到 AI CATS。
2. 不能直接访问 AI CATS 模块路由。
3. 不能调用附件、打印、下载、搜索和写操作接口。
4. 可以通过身份申请页提交一个或多个普通业务身份申请。

---

## 6. 权限判定模型

### 6.1 三层判定

普通用户执行任何 AI CATS 操作时，必须同时满足三层条件：

```text
生效身份
    AND 已启用模块范围
    AND 当前记录参与关系或数据范围
```

示例：用户拥有“供应商”身份且启用了装配/出厂模块，也只能查看 `inspector_id` 为自己的装配订单，不能查看其他供应商订单。

### 6.2 管理层判定

总经理和总经理助理绕过普通身份及数据范围限制，拥有全部业务权限。超级管理员作为技术兜底也可以访问全部模块，但所有代办和身份管理操作必须写入审计日志。

### 6.3 统一访问上下文

新增统一服务，例如 `AICatsAccessService`，负责生成当前用户访问上下文：

```python
class AICatsAccessContext:
    user_id: int
    is_manager: bool
    is_technical_admin: bool
    active_identities: set[str]
    enabled_scopes: dict[str, set[str]]

    def has_identity(self, identity_code: str) -> bool: ...
    def has_scope(self, module_code: str) -> bool: ...
    def can(self, capability_code: str) -> bool: ...
```

以下代码不得再作为 AI CATS 业务授权依据：

```python
user.role.code == 'qc_controller'
user.role.code == 'qc_inspector'
QCUserBinding.query.filter_by(user_id=user.id).first()
```

旧角色代码只允许在数据迁移和兼容映射中读取。

---

## 7. 详细权限矩阵

### 7.1 模块入口

| 身份 | 模块选择页 | 配件生产 | 装配/出厂 | 研究/实验 |
| --- | --- | --- | --- | --- |
| 总经理、总经理助理 | 全部 | 全部 | 全部 | 全部 |
| 超级管理员 | 全部 | 全部 | 全部 | 全部 |
| 质量控制人 | 可进入 | 按范围 | 按范围 | 不可见 |
| 供应商 | 可进入 | 按范围 | 按范围 | 不可见 |
| 研究人员 | 可进入 | 不可见 | 不可见 | 可进入 |
| 指导/验收人员 | 可进入 | 不可见 | 不可见 | 可进入 |
| 无身份用户 | 不可进入 | 不可访问 | 不可访问 | 不可访问 |

同时拥有多个身份时，模块入口取所有生效身份和模块范围的并集。

### 7.2 配件生产

| 功能 | 质量控制人 | 供应商 | 管理层 |
| --- | --- | --- | --- |
| 查看工件库 | 是 | 否 | 是 |
| 新增工件 | 是 | 否 | 是 |
| 编辑工件 | 本人创建且符合状态规则 | 否 | 是 |
| 删除工件 | 本人创建、未被引用且符合规则 | 否 | 是 |
| 发起质量控制订单 | 是 | 否 | 是 |
| 查看订单 | 本人发起 | 本人被指派 | 全部 |
| 编辑质量控制订单 | 本人发起且状态允许 | 否 | 是 |
| 执行质量检测 | 否 | 本人被指派 | 是 |
| 质控方验收 | 本人发起订单 | 否 | 可代办 |
| 供应商方验收 | 否 | 本人被指派订单 | 可代办 |
| 验收回退 | 本人发起且状态允许 | 否 | 是 |

供应商可以通过订单详情查看随订单快照保存的工件材料，但不能因此进入完整工件库。

### 7.3 装配/出厂

| 功能 | 质量控制人 | 供应商 | 管理层 |
| --- | --- | --- | --- |
| 查看产品/工件库 | 是 | 否 | 是 |
| 新增或编辑产品 | 按创建人和引用状态控制 | 否 | 是 |
| 发起装配 | 是 | 否 | 是 |
| 查看装配订单 | 本人发起 | 本人被指派 | 全部 |
| 执行装配质量检测 | 否 | 本人被指派 | 是 |
| 装配方验收 | 本人发起订单 | 否 | 可代办 |
| 供应商方验收 | 否 | 本人被指派订单 | 可代办 |
| 查看出厂模块 | 是 | 否 | 是 |
| 发起出厂 | 是 | 否 | 是 |
| 确认出厂 | 只能确认其他用户发起的订单 | 否 | 只能确认其他用户发起的订单 |
| 打印验收或 COA 报告 | 有权查看对应记录时 | 有权查看被指派记录时 | 是 |

出厂确认必须满足 `approver_id != initiator_id`。管理层也不得绕过这一条双人确认规则。

### 7.4 研究/实验

| 功能 | 研究人员 | 指导/验收人员 | 管理层 |
| --- | --- | --- | --- |
| 查看研究项目 | 本人创建 | 否 | 全部 |
| 新增或编辑研究项目 | 本人创建且状态允许 | 否 | 是 |
| 发起研究批次 | 是 | 否 | 是 |
| 查看研究批次 | 本人发起 | 本人被指派 | 全部 |
| 提交指导审批 | 本人发起 | 否 | 是 |
| 填写指导结果 | 否 | 本人被指派 | 是 |
| 研究方验收 | 本人发起批次 | 否 | 可代办 |
| 指导方验收 | 否 | 本人被指派批次 | 可代办 |
| 回退流程 | 按参与身份和状态控制 | 按参与身份和状态控制 | 是 |

---

## 8. 多身份与职责分离规则

### 8.1 同一用户可以拥有相对身份

系统允许同一用户同时拥有质量控制人和供应商身份，也允许同时拥有研究人员和指导/验收人员身份。这是账号层面的能力集合，不代表其可以在同一业务记录中担任双方。

### 8.2 订单参与人限制

1. 配件生产订单的 `controller_id` 和 `inspector_id` 不得相同。
2. 装配订单的 `controller_id` 和 `inspector_id` 不得相同。
3. 研究批次的 `researcher_id` 和 `reviewer_id` 不得相同。
4. 出厂订单的发起人和确认人不得相同。
5. 指派候选人下拉列表应排除当前记录另一方参与人。
6. 后端必须重复验证，不能只依赖前端过滤。

### 8.3 管理层代办

总经理、总经理助理和超级管理员可以在配件生产、装配和研究验收中选择代办任一方，但必须：

1. 明确提交本次代办的身份代码。
2. 每次点击只产生一方签名。
3. 不得一次操作同时写入双方确认。
4. 记录实际操作人、代办身份、时间和目标记录。

出厂流程不提供同一人双签代办，始终要求两名不同用户。

---

## 9. 独立注册页面改造

### 9.1 页面复用

继续使用 `/auth/register/qc` 和 `templates/auth/register_qc.html`，不新增重复注册入口。

原单选下拉框改为四个身份卡片复选框：

```text
[ ] 质量控制人
    默认负责配件生产和装配/出厂中的发起、管理与质控方确认

[ ] 供应商
    默认负责配件生产和装配/出厂中被指派的质量检测、材料上传与供应商确认

[ ] 研究人员
    负责研究项目、研究批次和研究方验收

[ ] 指导/验收人员
    负责被指派研究批次的指导审批和指导方验收
```

页面不展示总经理、总经理助理和超级管理员。

### 9.2 注册校验

1. 至少选择一个身份。
2. 身份代码必须来自服务端允许申请的固定集合。
3. 客户端提交重复身份时服务端自动去重。
4. 用户名、邮箱和手机号继续沿用现有校验。
5. 用户创建和全部身份申请必须在同一数据库事务中完成。
6. 任一步骤失败时不得留下半创建账号或孤立身份记录。
7. 新注册 AI CATS 用户默认不能进入 ERP。
8. 首次登录继续强制修改初始密码。

### 9.3 默认模块范围

| 申请身份 | 自动创建的模块范围 |
| --- | --- |
| 质量控制人 | `production`、`assembly` |
| 供应商 | `production`、`assembly` |
| 研究人员 | `research` |
| 指导/验收人员 | `research` |

注册用户不在前台调整模块范围。管理员审核时可以关闭质量控制人或供应商身份中的某一个模块范围。

### 9.4 审核结果

身份逐项审核，允许部分通过：

```text
质量控制人：已批准
供应商：已拒绝
研究人员：待审核
```

AI CATS 独立账号至少有一个生效身份后才能登录。全部身份均未通过时，账号保持不可用。

账号状态处理规则：

1. AI CATS 独立账号首次有身份获批时，启用 `User.is_active` 和 AI CATS Profile。
2. ERP 共享账号的身份审批不得修改其全局 `User.is_active`。
3. 撤销 ERP 共享账号的最后一个 AI CATS 身份，只会禁止其进入 AI CATS，不影响 ERP。
4. 停用 AI CATS 独立账号时，可以同步停用该用户；恢复时仍需至少有一个生效身份。
5. 全局 `User.is_active = False` 始终优先，已被 ERP 管理员停用的用户不能进入任何子系统。

---

## 10. ERP 用户增量申请

继续使用 `/auth/qc-role-apply`，但取消“存在任意绑定后不得再次申请”的限制。

新流程：

1. 页面展示用户当前生效、待审核、已拒绝和已撤销的身份。
2. 已生效或待审核身份不能重复申请。
3. 用户可以一次申请一个或多个缺少的身份。
4. 新申请不影响其原有生效身份。
5. ERP 用户的 ERP 主角色和部门关系保持不变。
6. ERP 用户只有在至少一个 AI CATS 身份生效后才能切换到 AI CATS。

---

## 11. 管理后台改造

### 11.1 管理员范围

以下用户可以管理 AI CATS 身份：

1. 总经理。
2. 总经理助理。
3. 超级管理员。

当前 `_is_qc_admin` 必须加入总经理助理，并最终改为统一访问服务判定。

### 11.2 待审核页面

待审核记录按用户分组展示：

| 用户 | 账号来源 | 申请身份 | 模块范围 | 操作 |
| --- | --- | --- | --- | --- |
| supplier_a | AI CATS 独立注册 | 供应商 | 配件生产、装配/出厂 | 批准/拒绝 |
| user_b | ERP 账号申请 | 质量控制人、研究人员 | 对应默认范围 | 分项批准/拒绝 |

管理员可以：

1. 全部批准。
2. 全部拒绝。
3. 分项批准或拒绝。
4. 在批准质量控制人或供应商时关闭其中一个模块范围。

### 11.3 用户身份详情页

AI CATS 用户管理增加独立详情页，展示：

1. 账号基本信息。
2. 账号来源：AI CATS 独立账号或 ERP 共享账号。
3. 当前生效身份。
4. 每个身份的模块范围。
5. 待审核、已拒绝和已撤销身份。
6. 未完成业务任务数量。
7. 身份变更历史。

管理员可以执行：

1. 直接新增并启用身份。
2. 启用或关闭某个模块范围。
3. 撤销身份。
4. 重新启用已撤销身份。
5. 停用或恢复该用户的 AI CATS 访问，不影响共享账号的 ERP 登录。
6. 重置密码。

### 11.4 撤销保护

如果待撤销身份仍关联未完成业务任务，系统不得静默撤销：

1. 显示未完成任务数量和链接。
2. 要求先将任务重新指派给其他合格用户。
3. 或由管理员停用账号后，通过专用重新指派流程完成交接。
4. 历史订单、签名和操作日志不得改写。

---

## 12. 数据模型设计

### 12.1 账号配置表

为避免修改现有 `users` 表，新增 AI CATS 账号配置表：

```python
class AICatsAccountProfile(db.Model):
    __tablename__ = 'ai_cats_account_profiles'

    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True,
    )
    access_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )
```

`access_mode` 取值：

| 值 | 说明 |
| --- | --- |
| `ai_cats_only` | AI CATS 独立注册账号，禁止进入 ERP |
| `shared` | 原 ERP 账号申请 AI CATS 身份，可在两个系统间切换 |

AI CATS 访问必须同时满足 `User.is_active = True` 和 `AICatsAccountProfile.is_enabled = True`。管理后台的“停用 AI CATS”只修改 Profile，不得直接停用共享 ERP 账号。

AI CATS 独立账号仍使用共享 `users` 表。由于 `users.role_id` 非空，新注册账号使用无 ERP 权限、无 AI CATS 业务权限的技术角色 `ai_cats_user`。实际业务权限全部来自下述多身份表。

历史 `qc_controller`、`qc_inspector` 专用账号迁移时不强制修改原 `role_id`，避免一次迁移同时改变过多认证状态；访问服务不得继续从这些旧主角色推导业务权限。

### 12.2 用户身份表

```python
class AICatsUserIdentity(db.Model):
    __tablename__ = 'ai_cats_user_identities'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    identity_code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

约束：`user_id + identity_code` 唯一。重复申请通过更新原记录状态实现，不重复插入相同身份。

`status` 取值：

| 状态 | 说明 |
| --- | --- |
| `pending` | 待审核 |
| `active` | 已生效 |
| `rejected` | 已拒绝 |
| `revoked` | 已撤销 |

### 12.3 身份模块范围表

```python
class AICatsUserIdentityScope(db.Model):
    __tablename__ = 'ai_cats_user_identity_scopes'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_identity_id: Mapped[int] = mapped_column(
        ForeignKey('ai_cats_user_identities.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    module_code: Mapped[str] = mapped_column(String(30), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

约束：`user_identity_id + module_code` 唯一。

### 12.4 身份审计日志

```python
class AICatsIdentityAuditLog(db.Model):
    __tablename__ = 'ai_cats_identity_audit_logs'

    id: Mapped[int] = mapped_column(primary_key=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    identity_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
```

身份审批、管理员新增、范围变更、撤销、恢复和账号停用均必须写入审计日志。

---

## 13. 固定身份能力映射

身份能力由代码固定定义，不允许普通管理员逐项修改底层权限：

```python
AI_CATS_IDENTITY_DEFINITIONS = {
    'controller': {
        'name': '质量控制人',
        'default_scopes': ('production', 'assembly'),
    },
    'supplier': {
        'name': '供应商',
        'default_scopes': ('production', 'assembly'),
    },
    'researcher': {
        'name': '研究人员',
        'default_scopes': ('research',),
    },
    'research_reviewer': {
        'name': '指导/验收人员',
        'default_scopes': ('research',),
    },
}
```

具体能力代码按模块分组，避免继续复用含义模糊的 `qc_*` 权限码。建议至少包含：

```text
production.workpiece.view
production.workpiece.create
production.workpiece.edit
production.workpiece.delete
production.order.view
production.order.create
production.order.edit
production.inspection.perform
production.acceptance.controller_sign
production.acceptance.supplier_sign
production.acceptance.rollback

assembly.inventory.view
assembly.product.create
assembly.product.edit
assembly.order.view
assembly.order.create
assembly.order.edit
assembly.inspection.perform
assembly.acceptance.controller_sign
assembly.acceptance.supplier_sign
assembly.outbound.view
assembly.outbound.create
assembly.outbound.confirm

research.project.view
research.project.create
research.project.edit
research.batch.view
research.batch.create
research.review.perform
research.acceptance.researcher_sign
research.acceptance.reviewer_sign
research.rollback

ai_cats.admin.users
ai_cats.admin.identities
ai_cats.admin.audit
```

旧 `qc_*` 权限在过渡期保留兼容映射，所有路由迁移完成后再评估是否删除。

---

## 14. 查询与接口安全要求

### 14.1 前端隐藏不等于权限控制

导航和按钮根据访问上下文隐藏，但所有后端路由、服务方法和文件接口仍必须独立校验。

### 14.2 必须覆盖的接口类型

1. 模块首页和列表。
2. 详情、新增、编辑、删除。
3. 状态流转和验收签字。
4. 附件预览、下载和删除。
5. 打印页面和 DOC 下载。
6. 模糊搜索和快照接口。
7. 库存历史和操作历史。
8. 管理后台和身份审批接口。

### 14.3 查询范围

列表查询必须在数据库查询阶段过滤用户可见记录，不能先查询全部再在模板隐藏。

详情接口必须根据记录参与关系再次校验，防止用户修改 URL 中的 ID 查看其他用户订单。

### 14.4 错误响应

| 场景 | 推荐响应 |
| --- | --- |
| 未登录 | 跳转 AI CATS 登录页 |
| 无任何 AI CATS 身份 | 跳转身份申请页 |
| 无模块范围 | 返回 403 或跳转模块选择页并提示 |
| 无记录访问权限 | 返回 404 或统一的“记录不存在或无权限”提示 |
| 无写操作权限 | 返回 403，不执行任何数据库修改 |

---

## 15. 历史数据迁移方案

### 15.1 迁移原则

1. 迁移只新增账号配置、身份、模块范围和审计记录。
2. 不修改订单、库存、附件、签名和历史业务表。
3. 不删除 `qc_user_bindings`。
4. 迁移必须可重复执行且结果幂等。
5. 迁移前必须备份 VPS 数据库。

### 15.2 旧角色映射

| 旧角色或绑定 | 新身份 | 默认模块范围 |
| --- | --- | --- |
| `qc_controller` | 质量控制人、研究人员 | 配件生产、装配/出厂、研究/实验 |
| `qc_inspector` | 供应商、指导/验收人员 | 配件生产、装配/出厂、研究/实验 |
| `general_manager` | 自动管理权限 | 全部 |
| `gm_assistant` | 自动管理权限 | 全部 |
| `superadmin` | 技术管理员权限 | 全部 |

旧角色曾同时承担生产/装配和研究模块职责，因此迁移时各拆分为两个新身份，保证既有用户不会丢失研究模块权限。旧 `qc_inspector` 在生产和装配页面统一显示为“供应商”；研究模块独立显示为“指导/验收人员”。数据库旧代码只作为兼容别名保留。

账号配置迁移规则：

1. 主角色为旧 `qc_controller` 或 `qc_inspector` 的专用账号迁移为 `access_mode = ai_cats_only`。
2. ERP 主角色用户通过 `QCUserBinding` 获得权限的账号迁移为 `access_mode = shared`。
3. 总经理、总经理助理和超级管理员无需 Profile 也可通过管理身份进入，访问服务按其 ERP 主角色直接识别。
4. 仅通过测试期开关获得权限的普通 ERP 用户不创建 Profile 和身份。
5. 新增无业务权限的技术角色 `ai_cats_user`，仅供后续新注册 AI CATS 独立账号满足 `users.role_id` 非空约束。

### 15.3 绑定状态映射

| 旧状态 | 新状态 |
| --- | --- |
| `QCUserBinding.is_active = True` | `active` |
| `QCUserBinding.is_active = False` | `pending` |

如果同一用户存在重复旧绑定，迁移脚本按用户和身份合并，并保留最早申请时间和最新有效审批信息。

### 15.4 测试期用户

仅依靠 `AI_CATS_TEST_OPEN_ACCESS` 获得权限、但没有管理身份或有效绑定的 ERP 用户，不得自动迁移成任何 AI CATS 身份。

---

## 16. 测试计划

### 16.1 身份解析单元测试

覆盖以下用户：

1. 超级管理员。
2. 总经理。
3. 总经理助理。
4. 仅质量控制人。
5. 仅供应商。
6. 同时拥有质量控制人和供应商。
7. 仅研究人员。
8. 仅指导/验收人员。
9. 跨模块多身份用户。
10. 身份待审核用户。
11. 身份已撤销用户。
12. 普通 ERP 用户。
13. 停用用户。

### 16.2 注册与审核测试

1. AI CATS 独立注册选择一个身份。
2. AI CATS 独立注册选择多个身份。
3. 未选择身份时拒绝提交。
4. 伪造管理身份代码时拒绝提交。
5. 用户和身份在同一事务中创建。
6. 管理员全部批准。
7. 管理员部分批准。
8. 管理员全部拒绝。
9. 总经理助理可以审核。
10. 普通用户不能访问审核接口。
11. ERP 用户增量申请身份不影响已有身份。
12. 停用共享账号的 AI CATS 访问不影响其 ERP 登录。
13. AI CATS 独立账号不能切换到 ERP。
14. 新注册独立账号的技术主角色不授予任何业务权限。

### 16.3 权限矩阵测试

每个模块至少测试：

1. 导航是否显示。
2. 列表是否只返回允许数据。
3. 直接访问详情 URL 是否被拦截。
4. 直接提交 POST 是否被拦截。
5. 附件、打印、下载接口是否被拦截。
6. 被指派用户可以完成自己的操作。
7. 未被指派的同身份用户不能操作。
8. 模块范围关闭后不能进入对应模块。
9. 多身份用户可以看到权限并集，但不能看到无参与关系的数据。

### 16.4 双方确认测试

1. 普通多身份用户不能在同一订单担任双方。
2. 一次点击只写入一个签名角色。
3. 管理层代办时必须显式选择签名角色。
4. 管理层代办两方时必须分别点击。
5. 出厂发起人不能确认自己的出厂订单。
6. 双方完成前不得更新最终状态或库存。
7. 重复提交签名必须幂等，不得重复入库或扣库。

### 16.5 迁移测试

1. 空数据库迁移。
2. 仅旧专用 AI CATS 账号数据库迁移。
3. ERP 账号加旧绑定数据库迁移。
4. 重复旧绑定迁移。
5. 迁移脚本重复执行。
6. 迁移前后订单、库存、签名和附件数量一致。
7. 使用 `PRAGMA table_info` 和唯一索引检查结构。

### 16.6 全量回归

1. 执行修改文件的 `py_compile`。
2. 创建 Flask 应用并检查所有 Blueprint 注册成功。
3. 执行 AI CATS 全流程测试。
4. 执行 ERP 合同、发货、回款、开票和正式合同生成器回归。
5. 执行完整 pytest 测试集。
6. 本地以关闭测试权限的配置进行浏览器验收。

---

## 17. 分阶段实施计划

### 阶段一：数据结构和兼容层

1. 新增四张 AI CATS 身份相关表。
2. 新增固定身份定义和模块范围定义。
3. 建立 `AICatsAccessService`。
4. 保留旧权限读取作为临时兼容回退。
5. 编写幂等迁移脚本和迁移测试。

### 阶段二：注册和管理后台

1. 独立注册页改为多身份复选卡片。
2. ERP 身份申请页支持增量多选。
3. 待审核页支持按用户分组和部分审批。
4. 新增用户身份详情和编辑页面。
5. 总经理助理加入 AI CATS 管理员范围。
6. 增加身份审计日志。

### 阶段三：业务权限收口

1. 配件生产全部路由和服务改用统一访问上下文。
2. 装配/出厂全部路由和服务改用统一访问上下文。
3. 研究/实验全部路由和服务改用统一访问上下文。
4. 修正所有直接读取 `user.role` 的 AI CATS 代码。
5. 修正所有 `.first()` 单绑定逻辑。
6. 清理出厂测试期宽松权限。
7. 统一用户可见身份名称为“供应商”。

### 阶段四：迁移和关闭测试权限

1. 备份数据库。
2. 执行身份迁移。
3. 输出迁移前后用户身份对账报告。
4. 由管理员核对所有用户身份和模块范围。
5. 将配置默认值改为关闭，并由生产配置强制关闭测试期全开放。
6. 清理生产环境中遗留的 `AI_CATS_TEST_OPEN_ACCESS` 测试变量。
7. 重启服务并完成权限矩阵抽查。

---

## 18. 预计代码影响范围

| 文件或目录 | 预计改动 |
| --- | --- |
| `app/models.py` | 新增账号配置、身份、范围和审计模型；增加身份常量 |
| `app/services/auth_service.py` | 多身份注册、申请、审批和迁移兼容 |
| `app/services/ai_cats_access_service.py` | 新增统一权限解析服务 |
| `app/services/qc_service.py` | 配件生产数据范围和动作权限接入 |
| `app/services/assembly_service.py` | 装配、验收和出厂权限接入 |
| `app/services/research_service.py` | 研究项目、审批和验收权限接入 |
| `app/routes/auth.py` | 多身份注册和增量申请 |
| `app/routes/qc.py` | 模块、管理后台和直接接口权限收口 |
| `templates/auth/register_qc.html` | 独立注册多身份卡片 |
| `templates/auth/qc_role_apply.html` | ERP 用户增量多身份申请 |
| `templates/qc/admin_pending.html` | 分组和部分审批 |
| `templates/qc/admin_users.html` | 用户身份摘要和详情入口 |
| `templates/qc/base.html` | 导航按有效模块范围显示 |
| `templates/qc/*` | 按统一访问上下文显示按钮和提示 |
| `config.py` | 最终关闭测试期完全放开默认值 |
| `migrate_v2.2_ai_cats_multi_identity.py` | 幂等多身份迁移与结构验证脚本 |
| `tests/` | 新增身份、权限、迁移和回归测试 |

---

## 19. 部署与回滚

### 19.1 部署顺序

1. 备份 VPS 数据库和上传文件。
2. 部署兼容新旧权限读取的代码，暂不关闭测试开关。
3. 执行数据库迁移。
4. 生成用户身份迁移对账报告。
5. 管理员核对并修正身份。
6. 运行完整测试和生产只读抽查。
7. 关闭测试权限开关并重启服务。
8. 使用各身份测试账号完成浏览器验收。

### 19.2 回滚策略

1. 新表迁移不删除旧表和旧字段。
2. 首次上线保留短期兼容读取开关。
3. 如发生阻断，可临时恢复旧权限读取，不回滚业务数据。
4. 回滚不得删除迁移后产生的身份审计日志。
5. 恢复数据库备份只作为迁移本身破坏数据时的最后手段。

---

## 20. 验收标准

满足以下全部条件后才可交付：

1. AI CATS 独立注册页可以一次申请多个身份。
2. 页面和提示中的身份名称统一为“供应商”。
3. 质量控制人和供应商默认同时覆盖配件生产、装配/出厂。
4. 管理员可以按用户调整身份及模块范围。
5. 总经理和总经理助理拥有全部业务及身份管理权限。
6. 普通 ERP 用户无身份时不能进入 AI CATS。
7. 供应商只能查看和操作被指派记录。
8. 研究相关身份不能进入配件生产或装配/出厂。
9. 多身份用户不能在同一业务记录担任相对双方。
10. 管理层代办必须逐个身份分别确认。
11. 出厂始终由两个不同用户确认。
12. 直接 URL、POST、附件、打印和下载接口均通过权限测试。
13. 测试权限关闭后全部身份流程正常。
14. 迁移前后业务订单、库存、附件、签名和历史记录完全一致。
15. ERP 全量回归测试通过。

### 20.1 本地验收结果（2026-08-21）

1. Python 语法检查通过。
2. 85 个 HTML/Jinja 模板编译通过。
3. SQLite 新表、唯一约束和索引检查通过。
4. 旧角色迁移首次执行完成映射，第二次执行新增记录数为 0，业务订单快照不变。
5. 隔离浏览器完成管理员、多身份用户、供应商账号、模块隔离、管理后台和 ERP 切换实测，前端控制台无错误。
6. 全项目自动化测试结果：`209 passed`。

---

## 21. 开发停止条件

出现以下任一情况时不得关闭测试权限或部署到生产：

1. 任意生效绑定用户迁移后没有对应新身份。
2. 供应商能够查看未指派订单。
3. 普通 ERP 用户仍能通过直接 URL 进入 AI CATS。
4. 多身份用户可以一次操作完成双方确认。
5. 出厂发起人可以确认自己的出厂订单。
6. 管理后台身份修改没有审计记录。
7. 数据迁移改变业务表记录数量或库存值。
8. AI CATS 或 ERP 全量测试未通过。

---

*本文件记录目标设计。实际开发完成后，应同步更新 `QC_PERMISSIONS.md`、数据库结构文档和相关模块开发文档。*
