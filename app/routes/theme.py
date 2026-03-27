#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
界面主题设置路由
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, session, g
from app import db
from app.utils.decorators import login_required
import os

theme_bp = Blueprint('theme', __name__, url_prefix='/theme')

# 背景类型选项
BACKGROUND_TYPE_OPTIONS = [
    {'value': 'video', 'name': '动态视频', 'description': '流畅的动态视频背景'},
    {'value': 'image', 'name': '图片背景', 'description': '精美的实验室风格图片'},
    {'value': 'solid', 'name': '纯色背景', 'description': '简洁的纯色渐变背景'},
]

# 可用的主题模式
THEME_OPTIONS = [
    {'value': 'light', 'name': '日间模式', 'description': '明亮的日间主题'},
    {'value': 'dark', 'name': '夜间模式', 'description': '护眼的暗色主题'},
]

# 可用的界面风格
STYLE_OPTIONS = [
    {'value': 'glass', 'name': '玻璃风格', 'description': '毛玻利和玻璃效果'},
    {'value': 'modern', 'name': '现代风格', 'description': '现代平面设计'},
    {'value': 'classic', 'name': '经典风格', 'description': '传统经典界面'},
]

# 获取可用的背景图片列表
def get_background_images():
    """获取static/img/backgrounds目录下的所有图片"""
    from flask import current_app
    images = []
    bg_dir = os.path.join(current_app.root_path, '..', 'static', 'img', 'backgrounds')
    if os.path.exists(bg_dir):
        for f in sorted(os.listdir(bg_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                images.append({
                    'filename': f,
                    'name': f.replace('.jpg', '').replace('.png', '').replace('-', ' ').title(),
                    'path': f'img/backgrounds/{f}'
                })
    return images


@theme_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """界面风格设置页面"""
    
    if request.method == 'POST':
        bg_type = request.form.get('bg_type', 'video')
        bg_image = request.form.get('bg_image', 'bg-main.jpg')
        theme = request.form.get('theme', 'light')
        style = request.form.get('style', 'glass')
        
        # 验证输入
        if bg_type not in [opt['value'] for opt in BACKGROUND_TYPE_OPTIONS]:
            bg_type = 'video'
        if theme not in [opt['value'] for opt in THEME_OPTIONS]:
            theme = 'light'
        if style not in [opt['value'] for opt in STYLE_OPTIONS]:
            style = 'glass'
        
        # 保存设置 - 使用bg_type代替background, 添加bg_image
        g.current_user.set_theme_preference(
            bg_type=bg_type,
            bg_image=bg_image,
            theme=theme,
            style=style
        )
        db.session.commit()
        
        flash('界面风格设置已保存', 'success')
        return redirect(url_for('theme.settings'))
    
    # 获取当前设置
    current_theme = g.current_user.get_theme_preference()
    
    # 获取可用背景图片
    background_images = get_background_images()
    
    return render_template('theme/settings.html',
                         background_type_options=BACKGROUND_TYPE_OPTIONS,
                         background_images=background_images,
                         theme_options=THEME_OPTIONS,
                         style_options=STYLE_OPTIONS,
                         current_theme=current_theme)
