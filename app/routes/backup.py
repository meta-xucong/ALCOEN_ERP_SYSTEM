"""
数据备份路由 - 超级管理员专用
提供ERP系统完整数据备份下载功能
"""
import os
import shutil
import zipfile
from datetime import datetime
from flask import Blueprint, render_template, send_file, flash, redirect, url_for, current_app
from app.utils.decorators import admin_required

backup_bp = Blueprint('backup', __name__, url_prefix='/backup')


def get_backup_directory():
    """获取备份文件存放目录"""
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def get_data_directory():
    """获取数据目录"""
    return os.path.join(current_app.root_path, '..', 'data')


def get_uploads_directory():
    """获取上传文件目录"""
    return os.path.join(current_app.root_path, '..', 'static', 'uploads')


def get_exports_directory():
    """获取导出文件目录"""
    return os.path.join(current_app.root_path, '..', 'exports')


@backup_bp.route('/')
@admin_required
def backup_page():
    """数据备份页面"""
    # 获取各目录信息
    data_dir = get_data_directory()
    uploads_dir = get_uploads_directory()
    exports_dir = get_exports_directory()
    
    # 计算各目录大小
    data_size = get_directory_size(data_dir) if os.path.exists(data_dir) else 0
    uploads_size = get_directory_size(uploads_dir) if os.path.exists(uploads_dir) else 0
    exports_size = get_directory_size(exports_dir) if os.path.exists(exports_dir) else 0
    total_size = data_size + uploads_size + exports_size
    
    # 获取文件数量统计
    data_files = count_files(data_dir) if os.path.exists(data_dir) else 0
    uploads_files = count_files(uploads_dir) if os.path.exists(uploads_dir) else 0
    exports_files = count_files(exports_dir) if os.path.exists(exports_dir) else 0
    total_files = data_files + uploads_files + exports_files
    
    return render_template('backup/index.html',
                         data_size=format_size(data_size),
                         uploads_size=format_size(uploads_size),
                         exports_size=format_size(exports_size),
                         total_size=format_size(total_size),
                         data_files=data_files,
                         uploads_files=uploads_files,
                         exports_files=exports_files,
                         total_files=total_files)


@backup_bp.route('/download')
@admin_required
def download_backup():
    """下载完整数据备份"""
    try:
        # 创建备份文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'erp_backup_{timestamp}.zip'
        backup_dir = get_backup_directory()
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # 创建ZIP文件
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 1. 备份数据库文件
            data_dir = get_data_directory()
            if os.path.exists(data_dir):
                for root, dirs, files in os.walk(data_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join('data', os.path.relpath(file_path, data_dir))
                        zipf.write(file_path, arcname)
            
            # 2. 备份上传的文件（图片、PDF等）
            uploads_dir = get_uploads_directory()
            if os.path.exists(uploads_dir):
                for root, dirs, files in os.walk(uploads_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join('static', 'uploads', os.path.relpath(file_path, uploads_dir))
                        zipf.write(file_path, arcname)
            
            # 3. 备份导出文件
            exports_dir = get_exports_directory()
            if os.path.exists(exports_dir):
                for root, dirs, files in os.walk(exports_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join('exports', os.path.relpath(file_path, exports_dir))
                        zipf.write(file_path, arcname)
            
            # 4. 添加备份说明文件
            readme_content = f"""ERP系统数据备份
====================
备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
备份文件名: {backup_filename}

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
"""
            zipf.writestr('README.txt', readme_content)
        
        # 发送文件
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        flash(f'备份失败: {str(e)}', 'error')
        return redirect(url_for('backup.backup_page'))


@backup_bp.route('/cleanup', methods=['POST'])
@admin_required
def cleanup_backups():
    """清理旧的备份文件"""
    try:
        backup_dir = get_backup_directory()
        if os.path.exists(backup_dir):
            # 删除超过7天的备份文件
            now = datetime.now()
            deleted_count = 0
            
            for filename in os.listdir(backup_dir):
                if filename.startswith('erp_backup_') and filename.endswith('.zip'):
                    file_path = os.path.join(backup_dir, filename)
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    if (now - file_time).days > 7:
                        os.remove(file_path)
                        deleted_count += 1
            
            flash(f'已清理 {deleted_count} 个旧备份文件', 'success')
        else:
            flash('备份目录不存在', 'info')
            
    except Exception as e:
        flash(f'清理失败: {str(e)}', 'error')
    
    return redirect(url_for('backup.backup_page'))


def get_directory_size(path):
    """计算目录大小（字节）"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total += os.path.getsize(fp)
    return total


def count_files(path):
    """计算目录中的文件数量"""
    count = 0
    for dirpath, dirnames, filenames in os.walk(path):
        count += len(filenames)
    return count


def format_size(size_bytes):
    """格式化文件大小显示"""
    if size_bytes == 0:
        return '0 B'
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(size_bytes)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f'{int(size)} {units[unit_index]}'
    else:
        return f'{size:.2f} {units[unit_index]}'
