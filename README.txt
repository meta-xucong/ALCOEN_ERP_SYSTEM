ERP系统数据备份
====================
备份时间: 2026-03-29 23:25:53
备份文件名: erp_backup_20260329_232552.zip

备份内容说明:
-------------
data/           - 数据库文件 (SQLite)
  - erp.db      - 主数据库文件
  
static/uploads/ - 上传的文件
  - contracts/          - 合同相关图片
  - contract_documents/ - 合同文档 (PDF, Word等)
  - products/           - 产品图片
  
exports/        - 导出的Excel文件
  - 对账单导出
  - 发货单导出

恢复说明:
---------
1. 解压此备份文件到ERP系统根目录
2. 确保覆盖以下目录:
   - data/
   - static/uploads/
   - exports/
3. 重启ERP服务即可恢复所有数据

注意: 恢复数据前请先备份当前数据！
