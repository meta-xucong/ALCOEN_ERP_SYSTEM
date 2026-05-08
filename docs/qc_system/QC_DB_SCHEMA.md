# ALCOEN QC 系统数据库变更文档

> 本文档详细描述为支持质量控制系统而在现有 SQLite 数据库 `data/erp.db` 中新增的表结构及字段说明。

---

## 1. 变更总览

本次升级共新增 **5 张数据表**，并在 `roles` 表中插入 **2 条新角色记录**。所有变更通过迁移脚本 `migrations/migrate_add_qc_system.py` 自动执行，支持幂等运行（多次执行不会重复创建）。

---

## 2. 新增表结构

### 2.1 qc_user_bindings — QC 用户角色绑定表

用于记录 ERP 主账号在 QC 子系统中的角色及审核状态。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| `user_id` | INTEGER | NOT NULL, FK → users(id) | 关联的 ERP 主账号 |
| `role_id` | INTEGER | NOT NULL, FK → roles(id) | QC 子系统中的角色 |
| `is_active` | BOOLEAN | DEFAULT 0 | 是否通过管理员审核 |
| `approved_by` | INTEGER | NULL, FK → users(id) | 审核人 |
| `approved_at` | DATETIME | NULL | 审核通过时间 |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 记录创建时间 |
| `updated_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 最后更新时间 |

**唯一约束：** `(user_id)` — 一个用户只能有一个 QC 角色绑定。

**SQL:**
```sql
CREATE TABLE IF NOT EXISTS qc_user_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT 0,
    approved_by INTEGER,
    approved_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (approved_by) REFERENCES users(id),
    UNIQUE (user_id)
);
CREATE INDEX IF NOT EXISTS idx_qc_user_bindings_user ON qc_user_bindings(user_id);
CREATE INDEX IF NOT EXISTS idx_qc_user_bindings_role ON qc_user_bindings(role_id);
CREATE INDEX IF NOT EXISTS idx_qc_user_bindings_active ON qc_user_bindings(is_active);
```

---

### 2.2 qc_work_orders — 工件订单主表

QC 系统的核心业务表，记录每一个工件批次的信息和当前状态。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| `batch_no` | VARCHAR(100) | UNIQUE, NOT NULL | 批次编号（唯一） |
| `workpiece_name` | VARCHAR(200) | NOT NULL | 工件名称 |
| `quantity` | FLOAT | NOT NULL | 生产数量 |
| `controller_id` | INTEGER | NOT NULL, FK → users(id) | 质量控制负责人 |
| `inspector_id` | INTEGER | NULL, FK → users(id) | 分配的质量检测员 |
| `status` | VARCHAR(50) | DEFAULT 'qc_pending' | 订单状态 |
| `qc_completed_at` | DATETIME | NULL | 质控完成时间 |
| `inspection_completed_at` | DATETIME | NULL | 质检完成时间 |
| `accepted_at` | DATETIME | NULL | 验收完成时间 |
| `rejected_at` | DATETIME | NULL | 质检不合格退回时间 |
| `rejection_reason` | TEXT | NULL | 质检不合格/回退原因 |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 最后更新时间 |

**状态枚举：**
- `qc_pending` — 质控未完成（初始）
- `qc_completed` — 待加工批次
- `inspection_pending` — 质检未完成
- `inspection_completed` — 质检已完成（全部通过）
- `accepted` — 验收已完成
- `rejected` — 质检不合格（退回）

**SQL:**
```sql
CREATE TABLE IF NOT EXISTS qc_work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no VARCHAR(100) UNIQUE NOT NULL,
    workpiece_name VARCHAR(200) NOT NULL,
    quantity FLOAT NOT NULL,
    controller_id INTEGER NOT NULL,
    inspector_id INTEGER,
    status VARCHAR(50) DEFAULT 'qc_pending',
    qc_completed_at DATETIME,
    inspection_completed_at DATETIME,
    accepted_at DATETIME,
    rejected_at DATETIME,
    rejection_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (controller_id) REFERENCES users(id),
    FOREIGN KEY (inspector_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_qcwo_status ON qc_work_orders(status);
CREATE INDEX IF NOT EXISTS idx_qcwo_controller ON qc_work_orders(controller_id);
CREATE INDEX IF NOT EXISTS idx_qcwo_inspector ON qc_work_orders(inspector_id);
CREATE INDEX IF NOT EXISTS idx_qcwo_created ON qc_work_orders(created_at);
```

---

### 2.3 qc_work_order_attachments — 工件订单附件表

统一存储工件订单相关的所有附件：图纸、作业指导书、检测点图片、备注图片。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| `work_order_id` | INTEGER | NOT NULL, FK → qc_work_orders(id) ON DELETE CASCADE | 关联工件订单 |
| `attach_type` | VARCHAR(50) | NOT NULL | 附件类型 |
| `title` | VARCHAR(255) | NULL | 标题（检测点名称/备注标题） |
| `content` | TEXT | NULL | 内容（检测点描述/备注文字） |
| `file_path` | VARCHAR(500) | NOT NULL | 文件存储相对路径 |
| `file_type` | VARCHAR(50) | NULL | 文件扩展名 |
| `is_required` | BOOLEAN | DEFAULT 1 | 是否必填 |
| `sort_order` | INTEGER | DEFAULT 0 | 排序序号 |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**attach_type 枚举：**
- `drawing` — 图纸
- `instruction` — 作业指导书
- `inspection_point` — 检测点
- `remark` — 备注

**SQL:**
```sql
CREATE TABLE IF NOT EXISTS qc_work_order_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    attach_type VARCHAR(50) NOT NULL,
    title VARCHAR(255),
    content TEXT,
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(50),
    is_required BOOLEAN DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_order_id) REFERENCES qc_work_orders(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_qcwoa_work_order ON qc_work_order_attachments(work_order_id);
CREATE INDEX IF NOT EXISTS idx_qcwoa_type ON qc_work_order_attachments(attach_type);
```

---

### 2.4 qc_inspection_records — 质检记录表

记录质量检测员对每个附件栏目的检测结果。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| `work_order_id` | INTEGER | NOT NULL, FK → qc_work_orders(id) ON DELETE CASCADE | 关联工件订单 |
| `inspector_id` | INTEGER | NOT NULL, FK → users(id) | 执行检测的质检员 |
| `attachment_id` | INTEGER | NOT NULL, FK → qc_work_order_attachments(id) | 被检测的附件 |
| `result` | VARCHAR(20) | NOT NULL | 检测结果 |
| `remark` | TEXT | NULL | 质检备注 |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 最后更新时间 |

**result 枚举：**
- `pass` — 通过（√）
- `fail` — 不通过（×）

**SQL:**
```sql
CREATE TABLE IF NOT EXISTS qc_inspection_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    inspector_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    result VARCHAR(20) NOT NULL,
    remark TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_order_id) REFERENCES qc_work_orders(id) ON DELETE CASCADE,
    FOREIGN KEY (inspector_id) REFERENCES users(id),
    FOREIGN KEY (attachment_id) REFERENCES qc_work_order_attachments(id)
);
CREATE INDEX IF NOT EXISTS idx_qcir_work_order ON qc_inspection_records(work_order_id);
CREATE INDEX IF NOT EXISTS idx_qcir_attachment ON qc_inspection_records(attachment_id);
CREATE INDEX IF NOT EXISTS idx_qcir_inspector ON qc_inspection_records(inspector_id);
```

---

### 2.5 qc_acceptance_signatures — 验收签字记录表

记录验收阶段质控员和质检员的双签确认。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| `work_order_id` | INTEGER | NOT NULL, FK → qc_work_orders(id) ON DELETE CASCADE | 关联工件订单 |
| `signer_id` | INTEGER | NOT NULL, FK → users(id) | 签字人 |
| `signer_role` | VARCHAR(50) | NOT NULL | 签字时的角色代码 |
| `signed_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 签字时间 |

**唯一约束：** `(work_order_id, signer_role)` — 每个角色对同一订单只能签一次。

**SQL:**
```sql
CREATE TABLE IF NOT EXISTS qc_acceptance_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER NOT NULL,
    signer_id INTEGER NOT NULL,
    signer_role VARCHAR(50) NOT NULL,
    signed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_order_id) REFERENCES qc_work_orders(id) ON DELETE CASCADE,
    FOREIGN KEY (signer_id) REFERENCES users(id),
    UNIQUE (work_order_id, signer_role)
);
CREATE INDEX IF NOT EXISTS idx_qcas_work_order ON qc_acceptance_signatures(work_order_id);
```

---

## 3. roles 表新增记录

在现有 `roles` 表中插入以下两条记录：

```sql
INSERT INTO roles (name, code, description, permissions, level, created_at)
VALUES (
    '质量控制员',
    'qc_controller',
    '负责工件订单创建、质控流程发起及验收确认',
    '["qc_dashboard","qc_work_order_view","qc_work_order_create","qc_work_order_edit","qc_work_order_delete","qc_acceptance_perform","qc_acceptance_rollback"]',
    55,
    CURRENT_TIMESTAMP
);

INSERT INTO roles (name, code, description, permissions, level, created_at)
VALUES (
    '质量检测员',
    'qc_inspector',
    '负责工件订单各栏目质量检测',
    '["qc_dashboard","qc_work_order_view","qc_inspection_perform"]',
    45,
    CURRENT_TIMESTAMP
);
```

**说明：**
- `permissions` 字段以 JSON 数组字符串形式存储。
- 超级管理员 (`superadmin`) 通过 `code == 'superadmin'` 判定拥有所有权限，无需在 JSON 中枚举 QC 权限。
- 总经理 (`general_manager`) 和总经理助理 (`gm_assistant`) 的权限在应用层做特殊处理或后续追加到其 `permissions` 字段。

---

## 4. 现有表变更说明

本次升级**不修改**任何现有表的结构（`users`、`roles`、`departments`、`contracts` 等）。

唯一需要说明的兼容处理：
- `users` 表继续以 `username` 为唯一键，密码、邮箱、电话等基础信息两子系统共享。
- `roles` 表的 `permissions` 字段兼容存储原有 ERP 权限和新增 QC 权限的混合列表。

---

## 5. ER 关系图

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│      users      │◄──────┤ qc_user_bindings│       │     roles       │
│   (主账号表)     │       │  (QC角色绑定)    │◄──────┤   (角色定义)     │
└─────────────────┘       └─────────────────┘       └─────────────────┘
         ▲
         │
         │ controller_id / inspector_id / approved_by / signer_id
         │
         │        ┌─────────────────────────┐
         │        │     qc_work_orders      │
         │        │      (工件订单主表)      │
         │        └───────────┬─────────────┘
         │                    │
         │    ┌───────────────┼───────────────┐
         │    ▼               ▼               ▼
         │ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
         │ │qc_work_order_   │ │ qc_inspection_  │ │qc_acceptance_   │
         │ │  attachments    │ │    records      │ │  signatures     │
         │ │  (附件表)        │ │   (质检记录)     │ │  (验收签字)      │
         │ └─────────────────┘ └─────────────────┘ └─────────────────┘
         │
```

---

## 6. 迁移脚本说明

迁移脚本 `migrations/migrate_add_qc_system.py` 执行以下操作：

1. 使用 `PRAGMA table_info(...)` 检查表是否已存在，避免重复创建。
2. 按顺序创建 5 张新表及索引。
3. 检查 `roles` 表中是否已有 `qc_controller` 和 `qc_inspector`，没有则插入。
4. 创建 `static/uploads/qc/` 目录用于文件存储。
5. 输出执行日志，便于排查问题。

**运行方式：**
```bash
python migrations/migrate_add_qc_system.py
```

---

## 7. 数据库备份建议

在执行迁移脚本前，请务必备份数据库：
```bash
copy data\erp.db data\erp.db.pre-qc-backup
```
