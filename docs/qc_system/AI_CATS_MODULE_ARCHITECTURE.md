# AI CATS 模块化入口开发文档

## 背景

AI CATS 当前进入系统后直接展示原质量控制仪表盘，导航中包含工件库、质量控制、质量检测、验收模块四个业务入口。后续 AI CATS 会继续扩展多个平级业务模块，因此需要先把现有四个业务入口提升为一个上层模块，并在 AI CATS 内新增模块选择层。

## 目标

1. 将现有工件库、质量控制、质量检测、验收模块归入上层模块：配件生产。
2. AI CATS 入口不再直接进入原仪表盘，而是进入模块选择页。
3. 模块选择页展示四个卡片：
   - 配件生产：可点击，进入现有 AI CATS 仪表盘和原四个业务入口。
   - 装配/出厂：可点击，进入新平级模块空壳页面。
   - 研究/实验：可点击，进入新平级模块空壳页面。
   - coming soon：外观一致，灰色禁用，不可点击。
4. 装配/出厂、研究/实验暂不接入配件生产页面和导航，作为独立平级模块框架保留。

## 路由设计

| 路由 | endpoint | 用途 |
| --- | --- | --- |
| `/qc/` | `qc.index` | AI CATS 模块选择页 |
| `/qc/production/` | `qc.production_home` | 配件生产首页，承接原 AI CATS 仪表盘 |
| `/qc/assembly/` | `qc.assembly_home` | 装配/出厂模块空壳 |
| `/qc/research/` | `qc.research_home` | 研究/实验模块空壳 |

原有业务路由保持不变，例如：

| 原路由 | 归属 |
| --- | --- |
| `/qc/workpieces/` | 配件生产 / 工件库 |
| `/qc/quality-control/` | 配件生产 / 质量控制 |
| `/qc/quality-inspection/` | 配件生产 / 质量检测 |
| `/qc/acceptance/` | 配件生产 / 验收模块 |

## 权限策略

模块选择页和三个可点击模块入口共用现有 AI CATS 访问校验：

1. 超级管理员、总经理、总经理助理默认可进入 AI CATS。
2. 质量控制人、供应商等 QC 用户需要存在已激活的 `QCUserBinding`。
3. 未获得 AI CATS 权限的用户继续跳转到 AI CATS 登录或角色申请流程。

装配/出厂、研究/实验暂时只做空壳，不新增独立权限模型；后续实现业务功能时再细化权限。

## 模板结构

| 模板 | 说明 |
| --- | --- |
| `templates/qc/base.html` | 保留原 AI CATS 应用壳，同时新增 `qc_shell='landing'` 的全屏入口页模式 |
| `templates/qc/module_select.html` | 模块选择页，使用与系统首页一致的玻璃卡片视觉 |
| `templates/qc/module_placeholder.html` | 装配/出厂、研究/实验的空壳页面 |
| `templates/qc/dashboard.html` | 原仪表盘模板，不改变业务内容，改由 `/qc/production/` 渲染 |

## 导航层级

进入配件生产后：

1. 顶部品牌 `AI CATS` 返回模块选择页。
2. 导航中的首页入口改为 `配件生产`，指向 `/qc/production/`。
3. 原工件库、质量控制、质量检测、验收模块继续显示在同一导航中，作为配件生产下的子功能。

装配/出厂、研究/实验空壳页不展示配件生产导航，只提供返回模块选择和返回系统首页的操作。

## 测试策略

1. 语法检查：`python -m py_compile app/routes/qc.py`
2. 模板检查：访问 `/qc/`、`/qc/production/`、`/qc/assembly/`、`/qc/research/` 均应返回 200。
3. 回归检查：原配件生产业务路由仍保持可访问。
4. 入口检查：`/auth/switch/qc` 仍跳转 `/qc/`，但 `/qc/` 渲染模块选择页。
5. 浏览器验收：本地刷新服务后打开 `http://localhost:8080/qc/`。
