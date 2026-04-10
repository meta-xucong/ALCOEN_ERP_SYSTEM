from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField, TextAreaField, SubmitField, SelectField, FileField, RadioField, HiddenField
from wtforms.validators import DataRequired, Optional, NumberRange, Length


class ProductForm(FlaskForm):
    """产品库表单 - 产品编码为核心"""
    
    product_code = StringField(
        '产品编码 *',
        validators=[
            DataRequired(message='请输入产品编码'),
            Length(max=50, message='产品编码不能超过50个字符')
        ],
        render_kw={'placeholder': '请输入产品编码（唯一标识）'}
    )
    
    product_name = StringField(
        '产品名称',
        validators=[Optional(), Length(max=100, message='产品名称不能超过100个字符')],
        render_kw={'placeholder': '请输入产品名称（可选）'}
    )
    
    product_model = StringField(
        '产品型号',
        validators=[Optional(), Length(max=100, message='产品型号不能超过100个字符')],
        render_kw={'placeholder': '请输入产品型号（可选）'}
    )
    
    product_type = StringField(
        '产品类型',
        validators=[Optional(), Length(max=50, message='产品类型不能超过50个字符')],
        render_kw={'placeholder': '请输入产品类型（可选）'}
    )
    
    default_price = FloatField(
        '默认单价',
        validators=[Optional(), NumberRange(min=0, message='单价必须大于0')],
        render_kw={'placeholder': '请输入默认单价（可选）', 'step': '0.01'}
    )
    
    remark = TextAreaField(
        '产品备注',
        validators=[Optional(), Length(max=500, message='备注不能超过500个字符')],
        render_kw={'placeholder': '请输入产品备注（可选）', 'rows': 3}
    )
    
    image = FileField(
        '产品图片',
        validators=[Optional()],
        render_kw={'accept': 'image/*'}
    )
    
    submit = SubmitField('保存')


# ==================== v1.2: 新增合同表单 ====================

class ContractForm(FlaskForm):
    """合同基础信息表单"""
    
    contract_no = StringField(
        '合同编号 *',
        validators=[
            DataRequired(message='请输入合同编号'),
            Length(max=100, message='合同编号不能超过100个字符')
        ],
        render_kw={'placeholder': '请输入合同编号'}
    )
    
    company_name = StringField(
        '公司名称 *',
        validators=[
            DataRequired(message='请输入公司名称'),
            Length(max=100, message='公司名称不能超过100个字符')
        ],
        render_kw={
            'placeholder': '请输入或选择公司名称',
            'list': 'company-list',
            'autocomplete': 'off'
        }
    )
    
    # [问题4] 归属人/负责人
    owner = StringField(
        '归属人',
        validators=[Optional(), Length(max=100, message='归属人不能超过100个字符')],
        render_kw={
            'placeholder': '请输入或选择归属人',
            'list': 'owner-list',
            'autocomplete': 'off'
        }
    )
    
    total_value = FloatField(
        '产品总价',
        validators=[Optional()],
        render_kw={'readonly': True, 'placeholder': '自动计算'}
    )
    
    remark = TextAreaField(
        '备注',
        validators=[Optional()],
        render_kw={'placeholder': '备注将自动记录修改日志', 'rows': 4, 'readonly': True}
    )
    
    submit = SubmitField('保存合同')


class ContractProductForm(FlaskForm):
    """合同产品计划表单（动态多条）"""
    
    # 产品选择方式
    product_select_mode = RadioField(
        '选择方式',
        choices=[('existing', '产品库'), ('manual', '手动')],
        default='existing'
    )
    
    # 从产品库选择
    product_id = SelectField('选择产品', coerce=int, validators=[Optional()])
    
    # 手动输入
    product_code = StringField(
        '产品编码 *',
        validators=[DataRequired(), Length(max=50)],
        render_kw={'placeholder': '产品编码'}
    )
    
    product_name = StringField(
        '产品名称',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': '自动填充或手动输入'}
    )
    
    product_model = StringField(
        '产品型号',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': '型号'}
    )
    
    product_type = StringField(
        '产品类型',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': '类型'}
    )
    
    quantity = FloatField(
        '数量 *',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={'placeholder': '数量', 'step': '0.01'}
    )
    
    unit = StringField(
        '单位 *',
        validators=[DataRequired(), Length(max=20)],
        render_kw={'placeholder': '个'}
    )
    
    price = FloatField(
        '含税单价 *',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={'placeholder': '单价', 'step': '0.01'}
    )
    
    total = FloatField(
        '总价',
        validators=[Optional()],
        render_kw={'readonly': True, 'placeholder': '自动计算'}
    )
    

class ContractTransactionForm(FlaskForm):
    """合同交易记录表单（动态多条）"""
    
    # 从合同产品中选择
    contract_product_id = SelectField(
        '选择产品 *',
        coerce=int,
        validators=[DataRequired(message='请选择产品')]
    )
    
    # 产品信息（只读显示）
    product_code_display = StringField('产品编码', render_kw={'readonly': True})
    product_name_display = StringField('产品名称', render_kw={'readonly': True})
    
    quantity = FloatField(
        '发货数量 *',
        validators=[DataRequired(), NumberRange(min=0)],
        render_kw={'placeholder': '发货数量', 'step': '0.01'}
    )
    
    unit = StringField(
        '单位',
        validators=[Optional(), Length(max=20)],
        render_kw={'placeholder': '自动填充'}
    )
    
    price_with_tax = FloatField(
        '含税单价',
        validators=[Optional(), NumberRange(min=0)],
        render_kw={'placeholder': '自动填充', 'step': '0.01'}
    )
    
    total_price = FloatField(
        '小计',
        validators=[Optional()],
        render_kw={'readonly': True, 'placeholder': '自动计算'}
    )
    
    payment_amount = FloatField(
        '回款金额',
        validators=[Optional(), NumberRange(min=0)],
        render_kw={'placeholder': '数量×单价', 'step': '0.01'}
    )
    
    delivery_date = DateField(
        '发货日期 *',
        validators=[DataRequired()],
        format='%Y-%m-%d',
        render_kw={'type': 'date'}
    )
    
    invoice_date = DateField(
        '开票日期',
        validators=[Optional()],
        format='%Y-%m-%d',
        render_kw={'type': 'date'}
    )
    
    payment_date = DateField(
        '回款日期',
        validators=[Optional()],
        format='%Y-%m-%d',
        render_kw={'type': 'date'}
    )
    
    remark = StringField(
        '备注',
        validators=[Optional(), Length(max=200)],
        render_kw={'placeholder': '备注'}
    )


# ==================== 保留旧表单用于兼容 ====================

class TransactionForm(FlaskForm):
    """交易记录表单 - v1.1 兼容版"""
    
    company_name = StringField(
        '公司名称 *',
        validators=[DataRequired(), Length(max=100)],
        render_kw={'placeholder': '请输入或选择公司名称', 'list': 'company-list'}
    )
    
    product_select_mode = RadioField(
        '产品选择方式',
        choices=[('existing', '从产品库选择'), ('manual', '手动输入')],
        default='existing'
    )
    
    product_id = SelectField('产品编码 *', coerce=int, validators=[Optional()])
    
    product_code = StringField('产品编码 *', validators=[DataRequired(), Length(max=50)])
    
    product_name = StringField('产品名称', validators=[Optional(), Length(max=100)])
    product_model = StringField('产品型号', validators=[Optional(), Length(max=100)])
    product_type = StringField('产品类型', validators=[Optional(), Length(max=50)])
    
    quantity = FloatField('数量 *', validators=[DataRequired(), NumberRange(min=0)], render_kw={'step': '0.01'})
    unit = StringField('单位 *', validators=[DataRequired(), Length(max=20)])
    price_with_tax = FloatField('含税单价 *', validators=[DataRequired(), NumberRange(min=0)], render_kw={'step': '0.01'})
    
    delivery_date = DateField('发货日期 *', validators=[DataRequired()], format='%Y-%m-%d', render_kw={'type': 'date'})
    invoice_date = DateField('开票日期', validators=[Optional()], format='%Y-%m-%d', render_kw={'type': 'date'})
    payment_date = DateField('回款日期', validators=[Optional()], format='%Y-%m-%d', render_kw={'type': 'date'})
    
    contract_no = StringField('合同编号', validators=[Optional(), Length(max=100)])
    remark = TextAreaField('备注', validators=[Optional(), Length(max=500)], render_kw={'rows': 3})
    
    submit = SubmitField('保存')


class StatementGeneratorForm(FlaskForm):
    """[LOGIC-8] 对账单生成器表单 - 支持多维度筛选"""
    
    # 公司筛选（可选，如果不选则匹配所有公司）
    company_name = StringField(
        '公司名称',
        validators=[Optional()],
        render_kw={'placeholder': '选择或输入公司名称（可选）', 'list': 'company-list'}
    )
    
    # 合同号筛选
    contract_no = StringField(
        '合同编号',
        validators=[Optional()],
        render_kw={'placeholder': '输入合同编号（可选，模糊匹配）'}
    )
    
    # 产品编码筛选（模糊匹配，多个逗号分隔）
    product_code_filter = StringField(
        '产品编码',
        validators=[Optional()],
        render_kw={'placeholder': '输入产品编码，多个用逗号分隔（可选，模糊匹配）'}
    )
    
    # 产品名称筛选（模糊匹配）
    product_filter = StringField(
        '产品名称',
        validators=[Optional()],
        render_kw={'placeholder': '输入产品名称，多个用逗号分隔（可选，模糊匹配）'}
    )
    
    # [v1.3] 部门和负责人筛选（替换原来的归属人）
    department = StringField(
        '部门',
        validators=[Optional()],
        render_kw={'placeholder': '选择或输入部门（可选）', 'list': 'department-list'}
    )
    manager = StringField(
        '负责人',
        validators=[Optional()],
        render_kw={'placeholder': '选择或输入负责人（可选）', 'list': 'manager-list'}
    )
    
    # 日期范围（可选）
    start_date = DateField('起始日期', validators=[Optional()], format='%Y-%m-%d', render_kw={'type': 'date'})
    end_date = DateField('结束日期', validators=[Optional()], format='%Y-%m-%d', render_kw={'type': 'date'})
    
    submit = SubmitField('生成对账单')
