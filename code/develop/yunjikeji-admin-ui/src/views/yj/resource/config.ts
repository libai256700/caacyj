export type YjFieldType =
  | 'input'
  | 'textarea'
  | 'select'
  | 'switch'
  | 'number'
  | 'date'
  | 'datetime'
  | 'url'
  | 'editor'

export interface YjOption {
  label: string
  value: any
  type?: 'success' | 'info' | 'warning' | 'danger'
}

export interface YjField {
  prop: string
  label: string
  type?: YjFieldType
  options?: YjOption[]
  defaultValue?: any
  queryDefaultValue?: any
  switchLabels?: {
    active: string
    inactive: string
  }
  dictType?: string
  excludeValues?: any[]
  optionsResource?: string
  optionLabelProp?: string
  optionValueProp?: string
  width?: number
  minWidth?: number
  required?: boolean
  table?: boolean
  search?: boolean
  form?: boolean
  detail?: boolean
  readonly?: boolean
}

export interface YjRelatedConfig {
  title: string
  resource: string
  foreignKey: string
  parentKey?: string
  fields: YjField[]
  searchable?: boolean
  publishable?: boolean
}

export interface YjResourceConfig {
  title: string
  resource: string
  description: string
  keywordPlaceholder?: string
  searchCreateTime?: boolean
  fields: YjField[]
  readonly?: boolean
  editableFields?: string[]
  audit?: 'enterprise' | 'student'
  related?: YjRelatedConfig
  customerService?: boolean
}

export const commonStatusOptions: YjOption[] = [
  { label: '启用', value: true, type: 'success' },
  { label: '停用', value: false, type: 'info' },
  { label: '启用', value: 1, type: 'success' },
  { label: '停用', value: 0, type: 'info' }
]

export const enterpriseAuditOptions: YjOption[] = [
  { label: '待审核', value: 0, type: 'warning' },
  { label: '审核中', value: 1, type: 'info' },
  { label: '已通过', value: 2, type: 'success' },
  { label: '已驳回', value: 3, type: 'danger' }
]

export const studentAuditOptions: YjOption[] = [
  { label: '保存', value: 0, type: 'info' },
  { label: '审核中', value: 1, type: 'warning' },
  { label: '已通过', value: 2, type: 'success' },
  { label: '已驳回', value: 3, type: 'danger' }
]

export const YJ_PRACTICE_QUESTION_TYPE_DICT = 'yj_practice_question_type'
export const YJ_RECRUIT_COLLECTION_SOURCE_DICT = 'yj_recruit_collection_source'
export const YJ_AGREEMENT_TYPE_DICT = 'yj_agreement_type'

export const practiceCatalogTypeOptions: YjOption[] = [
  { label: '练习', value: 0, type: 'success' },
  { label: '自测', value: 1, type: 'info' }
]

export const publishStatusOptions: YjOption[] = [
  { label: '草稿', value: 0, type: 'info' },
  { label: '已发布', value: 1, type: 'success' },
  { label: '已撤回', value: 2, type: 'warning' }
]

export const collectionFrequencyOptions: YjOption[] = [
  { label: '每天一次', value: 1 },
  { label: '每周一次', value: 2 },
  { label: '每月一次', value: 3 }
]

export const collectionTaskInstanceStatusOptions: YjOption[] = [
  { label: '保存', value: 0, type: 'info' },
  { label: '进行中', value: 1, type: 'warning' },
  { label: '成功未合入', value: 2, type: 'success' },
  { label: '成功已合入', value: 3, type: 'success' },
  { label: '失败', value: 4, type: 'danger' }
]

const auditFields: YjField[] = [
  { prop: 'name', label: '企业名称', search: true, required: true, minWidth: 180 },
  { prop: 'legal_person', label: '法人', minWidth: 110 },
  { prop: 'contact_name', label: '联系人', search: true, required: true, minWidth: 120 },
  { prop: 'contact_mobile', label: '联系电话', search: true, required: true, minWidth: 140 },
  {
    prop: 'audit_status',
    label: '审核状态',
    type: 'select',
    options: enterpriseAuditOptions,
    search: true,
    required: true,
    minWidth: 110
  },
  { prop: 'audit_reason', label: '审核原因', type: 'textarea', table: false },
  { prop: 'create_time', label: '提交时间', type: 'datetime', form: false, width: 170 },
  { prop: 'audit_time', label: '审核时间', type: 'datetime', form: false, width: 170 }
]

const answerFields: YjField[] = [
  {
    prop: 'question_type',
    label: '题型',
    type: 'select',
    dictType: YJ_PRACTICE_QUESTION_TYPE_DICT,
    required: true,
    width: 110
  },
  { prop: 'answer_code', label: '选项标识', required: true, width: 110 },
  { prop: 'answer_content', label: '选项内容', type: 'textarea', required: true, minWidth: 220 },
  { prop: 'is_correct', label: '正确答案', type: 'switch', switchLabels: { active: '是', inactive: '否' }, width: 100 },
  { prop: 'sort_no', label: '排序', type: 'number', width: 90 }
]

export const yjResourceConfigs: Record<string, YjResourceConfig> = {
  'enterprise-audit': {
    title: '企业审核',
    resource: 'enterprise-audit',
    description: '企业注册审核列表，支持资质材料登记、审核通过和驳回原因维护。',
    fields: auditFields,
    audit: 'enterprise',
    related: {
      title: '资质材料',
      resource: 'enterprise-audit-attachment',
      foreignKey: 'company_id',
      fields: [
        { prop: 'file_name', label: '文件名', search: true, required: true, minWidth: 180 },
        { prop: 'file_type', label: '文件类型', search: true, minWidth: 120 },
        { prop: 'file_path', label: '存储路径', required: true, minWidth: 260 },
        { prop: 'create_time', label: '上传时间', type: 'datetime', form: false, width: 170 }
      ],
      searchable: true
    }
  },
  'student-audit': {
    title: '学员加入审核',
    resource: 'student-audit',
    description: '处理学员申请加入企业的待审核记录。',
    readonly: true,
    editableFields: ['student_name'],
    fields: [
      { prop: 'company_name', label: '企业名称', search: true, form: false, minWidth: 180 },
      { prop: 'student_name', label: '学员名称', search: true, form: false, minWidth: 160 },
      { prop: 'mobile_phone', label: '手机号码', search: true, form: false, minWidth: 140 },
      { prop: 'company_id', label: '企业编号', type: 'number', required: true, table: false, detail: false },
      { prop: 'user_id', label: '学员编号', type: 'number', required: true, table: false, detail: false },
      {
        prop: 'audit_status',
        label: '审核状态',
        type: 'select',
        options: studentAuditOptions,
        search: true,
        required: true,
        minWidth: 110
      },
      { prop: 'audit_reason', label: '审核原因', type: 'textarea', table: false },
      { prop: 'create_time', label: '申请时间', type: 'datetime', form: false, width: 170 },
      { prop: 'audit_time', label: '审核时间', type: 'datetime', form: false, width: 170 }
    ],
    audit: 'student'
  },
  'practice-category': {
    title: '练习分类管理',
    resource: 'practice-category',
    description: '维护练习题一级分类、所属领域、排序和启停状态。',
    searchCreateTime: false,
    fields: [
      { prop: 'category_name', label: '分类名称', search: true, required: true, minWidth: 180 },
      { prop: 'field_type', label: '所属领域', minWidth: 120 },
      {
        prop: 'catalog_type',
        label: '分类类型',
        type: 'select',
        options: practiceCatalogTypeOptions,
        required: true,
        width: 110
      },
      { prop: 'category_status', label: '状态', type: 'switch', search: true, width: 100 },
      { prop: 'sort_no', label: '排序', type: 'number', width: 90 },
      { prop: 'update_time', label: '更新时间', type: 'datetime', form: false, width: 170 }
    ]
  },
  'practice-exercise': {
    title: '练习题目管理',
    resource: 'practice-exercise',
    description: '维护题目题干、题型、分值、解析与可选项配置。',
    searchCreateTime: false,
    fields: [
      {
        prop: 'category_id',
        label: '分类名称',
        type: 'select',
        optionsResource: 'practice-category',
        optionLabelProp: 'category_name',
        optionValueProp: 'id',
        search: true,
        required: true,
        minWidth: 140
      },
      { prop: 'question_stem', label: '题干摘要', type: 'textarea', search: true, required: true, minWidth: 260 },
      {
        prop: 'question_type',
        label: '题型',
        type: 'select',
        dictType: YJ_PRACTICE_QUESTION_TYPE_DICT,
        search: true,
        required: true,
        width: 110
      },
      { prop: 'score', label: '分值', type: 'number', required: true, width: 90 },
      { prop: 'question_status', label: '状态', type: 'switch', search: true, width: 100 },
      { prop: 'sort_no', label: '排序', type: 'number', width: 90 },
      { prop: 'correct_memo', label: '正确解析', type: 'textarea', table: false },
      { prop: 'update_time', label: '更新时间', type: 'datetime', form: false, width: 170 }
    ],
    related: {
      title: '配置可选项',
      resource: 'practice-exercise-answer',
      foreignKey: 'exercises_id',
      fields: answerFields,
      searchable: true
    }
  },
  'practice-record': {
    title: '练习记录',
    resource: 'practice-record',
    description: '查看学员练习记录、得分、正确数与错误数。',
    readonly: true,
    fields: [
      { prop: 'student_name', label: '学员名称', search: true, minWidth: 160 },
      { prop: 'category_name', label: '分类名称', search: true, minWidth: 160 },
      { prop: 'total_score', label: '得分', type: 'number', width: 90 },
      { prop: 'correct_count', label: '正确数', type: 'number', width: 90 },
      { prop: 'wrong_count', label: '错误数', type: 'number', width: 90 },
      { prop: 'create_time', label: '练习时间', type: 'datetime', form: false, width: 170 }
    ],
    related: {
      title: '答题明细',
      resource: 'practice-record-detail',
      foreignKey: 'record_id',
      fields: [
        { prop: 'exercises_id', label: '题目编号', type: 'number', search: true, width: 110 },
        { prop: 'answer_code', label: '用户答案', minWidth: 120 },
        { prop: 'correct_answer_code', label: '正确答案', minWidth: 120 },
        { prop: 'is_correct', label: '是否正确', type: 'switch', switchLabels: { active: '是', inactive: '否' }, width: 100 },
        { prop: 'create_time', label: '答题时间', type: 'datetime', form: false, width: 170 }
      ],
      searchable: true
    }
  },
  'practice-record-detail': {
    title: '错题管理',
    resource: 'practice-record-detail',
    description: '按答题明细查看错题记录，可筛选题目、答案与正确性。',
    readonly: true,
    fields: [
      { prop: 'student_name', label: '所属学员', search: true, minWidth: 160 },
      { prop: 'practice_record_display', label: '练习时间+分类名称', minWidth: 260 },
      { prop: 'category_name', label: '分类名称', search: true, table: false, detail: false, minWidth: 160 },
      { prop: 'question_stem', label: '题目题干', minWidth: 260 },
      { prop: 'question_keyword', label: '题目', search: true, table: false, detail: false, minWidth: 160 },
      { prop: 'record_id', label: '练习记录编号', type: 'number', table: false, width: 110 },
      { prop: 'exercises_id', label: '题目编号', type: 'number', table: false, width: 110 },
      { prop: 'answer_code', label: '用户答案', search: true, minWidth: 140 },
      { prop: 'correct_answer_code', label: '正确答案', search: true, minWidth: 140 },
      {
        prop: 'is_correct',
        label: '是否正确',
        type: 'switch',
        switchLabels: { active: '是', inactive: '否' },
        options: [
          { label: '不限', value: '' },
          { label: '是', value: true, type: 'success' },
          { label: '否', value: false, type: 'info' }
        ],
        queryDefaultValue: false,
        search: true,
        width: 100
      },
      { prop: 'create_time', label: '最近答错时间', type: 'datetime', form: false, width: 170 }
    ]
  },
  post: {
    title: '岗位管理',
    resource: 'post',
    description: '维护招聘岗位、岗位平台、薪资范围、工作地点、发布时间与状态。',
    fields: [
      { prop: 'name', label: '岗位名称', search: true, required: true, minWidth: 180 },
      { prop: 'company_name', label: '企业名称', search: true, minWidth: 180 },
      {
        prop: 'collection_channel',
        label: '岗位平台',
        type: 'select',
        dictType: YJ_RECRUIT_COLLECTION_SOURCE_DICT,
        search: true,
        form: false,
        minWidth: 120
      },
      { prop: 'salary_range', label: '薪资范围', search: true, minWidth: 140 },
      { prop: 'work_area', label: '工作地点', search: true, minWidth: 140 },
      { prop: 'detail_url', label: '岗位链接', type: 'url', minWidth: 220 },
      { prop: 'publish_date', label: '发布时间', type: 'date', width: 130 },
      { prop: 'status', label: '状态', type: 'switch', search: true, width: 100 }
    ]
  },
  'collection-task': {
    title: '采集配置',
    resource: 'collection-task',
    description: '维护招聘信息自动采集任务，飞书目录任务可查看文档、AI 解析和入库审计。',
    fields: [
      { prop: 'name', label: '任务名称', search: true, required: true, minWidth: 180 },
      {
        prop: 'collection_channel',
        label: '采集来源',
        type: 'select',
        options: [
          { label: '飞书目录', value: 'feishu_folder_v2', type: 'success' },
          { label: '飞书目录（兼容）', value: 'feishu_folder', type: 'info' }
        ],
        search: true,
        required: true,
        minWidth: 120
      },
      {
        prop: 'collection_count_rule',
        label: '采集频次',
        type: 'select',
        options: collectionFrequencyOptions,
        required: true,
        width: 110
      },
      { prop: 'collection_time', label: '采集时间', type: 'datetime', required: true, width: 170 },
      { prop: 'collection_num', label: '每次条数', type: 'number', width: 100 },
      { prop: 'collection_key', label: '关键词/目录地址', search: true, minWidth: 220 },
      { prop: 'status', label: '状态', type: 'switch', search: true, width: 100 },
      { prop: 'last_execute_time', label: '最近执行时间', type: 'datetime', form: false, width: 170 }
    ],
      related: {
      title: '采集实例',
      resource: 'collection-task-instance',
      foreignKey: 'task_id',
      fields: [
        { prop: 'stauts', label: '状态', type: 'select', options: collectionTaskInstanceStatusOptions, width: 120 },
        { prop: 'collection_count', label: '采集条数', type: 'number', width: 100 },
        { prop: 'create_time', label: '创建时间', type: 'datetime', form: false, width: 170 },
        { prop: 'update_time', label: '更新时间', type: 'datetime', form: false, width: 170 }
      ],
      searchable: true
    }
  },
  'collection-task-instance': {
    title: '采集任务实例',
    resource: 'collection-task-instance',
    description: '查看每次招聘岗位采集任务的执行实例、采集数量和合入状态。',
    readonly: true,
    fields: [
      { prop: 'task_id', label: '采集任务', type: 'number', search: true, width: 110 },
      { prop: 'stauts', label: '状态', type: 'select', options: collectionTaskInstanceStatusOptions, search: true, width: 120 },
      { prop: 'collection_count', label: '采集条数', type: 'number', width: 100 },
      { prop: 'create_time', label: '创建时间', type: 'datetime', form: false, width: 170 },
      { prop: 'update_time', label: '更新时间', type: 'datetime', form: false, width: 170 }
    ],
    related: {
      title: '岗位实例',
      resource: 'post-instance',
      foreignKey: 'task_instance_id',
      fields: [
        { prop: 'name', label: '岗位名称', search: true, minWidth: 180 },
        { prop: 'company_name', label: '企业名称', search: true, minWidth: 180 },
        {
          prop: 'collection_channel',
          label: '岗位平台',
          type: 'select',
          dictType: YJ_RECRUIT_COLLECTION_SOURCE_DICT,
          search: true,
          form: false,
          minWidth: 120
        },
        { prop: 'salary_range', label: '薪资范围', search: true, minWidth: 140 },
        { prop: 'work_area', label: '工作区域', search: true, minWidth: 140 },
        { prop: 'publish_date', label: '发布时间', type: 'date', width: 130 },
        { prop: 'status', label: '状态', type: 'switch', width: 100 }
      ],
      searchable: true
    }
  },
  'post-instance': {
    title: '采集岗位实例',
    resource: 'post-instance',
    description: '查看采集任务实例落下的原始岗位明细。',
    readonly: true,
    fields: [
      { prop: 'task_instance_id', label: '任务实例', type: 'number', search: true, width: 110 },
      { prop: 'name', label: '岗位名称', search: true, minWidth: 180 },
      { prop: 'company_name', label: '企业名称', search: true, minWidth: 180 },
      {
        prop: 'collection_channel',
        label: '岗位平台',
        type: 'select',
        dictType: YJ_RECRUIT_COLLECTION_SOURCE_DICT,
        search: true,
        form: false,
        minWidth: 120
      },
      { prop: 'salary_range', label: '薪资范围', search: true, minWidth: 140 },
      { prop: 'work_area', label: '工作区域', search: true, minWidth: 140 },
      { prop: 'publish_date', label: '发布时间', type: 'date', width: 130 },
      { prop: 'detail_url', label: '岗位链接', type: 'url', minWidth: 220 },
      { prop: 'status', label: '状态', type: 'switch', search: true, width: 100 }
    ]
  },
  agreement: {
    title: '协议管理',
    resource: 'agreement',
    description: '维护用户协议、隐私协议等协议主数据及富文本版本。',
    fields: [
      { prop: 'name', label: '协议名称', search: true, required: true, minWidth: 180 },
      {
        prop: 'type',
        label: '协议类型',
        type: 'select',
        dictType: YJ_AGREEMENT_TYPE_DICT,
        search: true,
        required: true,
        minWidth: 120
      },
      { prop: 'status', label: '状态', type: 'switch', search: true, width: 100 },
      { prop: 'update_time', label: '更新时间', type: 'datetime', form: false, width: 170 }
    ],
    related: {
      title: '版本管理',
      resource: 'agreement-detail',
      foreignKey: 'agreement_info_id',
      fields: [
        { prop: 'version', label: '版本号', search: true, required: true, minWidth: 120 },
        {
          prop: 'publish_status',
          label: '发布状态',
          type: 'select',
          options: publishStatusOptions,
          required: true,
          width: 110
        },
        { prop: 'publish_time', label: '发布时间', type: 'datetime', form: false, width: 170 },
        { prop: 'content', label: '协议正文', type: 'editor', table: false, required: true }
      ],
      searchable: true,
      publishable: true
    }
  },
  'assessment-question': {
    title: '自测题库管理',
    resource: 'assessment-question',
    description: '维护自测题目、题型、题干内容与状态。',
    fields: [
      { prop: 'title', label: '题目标题', search: true, required: true, minWidth: 180 },
      {
        prop: 'question_type',
        label: '题型',
        type: 'select',
        dictType: YJ_PRACTICE_QUESTION_TYPE_DICT,
        search: true,
        required: true,
        width: 110
      },
      { prop: 'question_content', label: '题目内容', type: 'textarea', search: true, required: true, minWidth: 260 },
      { prop: 'step_name', label: '所属步骤名称', form: false, minWidth: 150 },
      {
        prop: 'is_required',
        label: '是否必填',
        type: 'select',
        options: [
          { label: '是', value: true, type: 'success' },
          { label: '否', value: false, type: 'info' }
        ],
        defaultValue: true,
        required: true,
        width: 100
      },
      { prop: 'status', label: '状态', type: 'switch', search: true, width: 100 },
      { prop: 'sort_no', label: '排序', type: 'number', width: 90 },
      { prop: 'update_time', label: '更新时间', type: 'datetime', form: false, width: 170 }
    ],
    related: {
      title: '自测答案',
      resource: 'assessment-answer',
      foreignKey: 'question_id',
      fields: [
        { prop: 'answer_code', label: '答案标识', search: true, required: true, width: 110 },
        { prop: 'answer_content', label: '答案内容', type: 'textarea', required: true, minWidth: 240 },
        { prop: 'is_correct', label: '推荐答案', type: 'switch', switchLabels: { active: '是', inactive: '否' }, width: 100 },
        { prop: 'sort_no', label: '排序', type: 'number', width: 90 }
      ],
      searchable: true
    }
  },
  'assessment-result': {
    title: '自测结果管理',
    resource: 'assessment-result',
    description: '查看用户自测结果、方向建议和 AI 报告内容。',
    readonly: true,
    fields: [
      { prop: 'user_id', label: '学员编号', type: 'number', search: true, width: 110 },
      { prop: 'assessment_time', label: '自测时间', type: 'datetime', width: 170 },
      { prop: 'report_content', label: '结果摘要', search: true, minWidth: 220 },
      { prop: 'recommend_direction', label: '推荐方向', search: true, minWidth: 160 },
      { prop: 'report_content', label: 'AI 报告', type: 'editor', table: false }
    ]
  },
  'knowledge-base': {
    title: '知识库管理',
    resource: 'knowledge-base',
    description: '维护知识库、条目数量和启停状态。',
    fields: [
      { prop: 'name', label: '知识库名称', search: true, required: true, minWidth: 180 },
      { prop: 'item_count', label: '条目数量', type: 'number', width: 100 },
      { prop: 'status', label: '状态', type: 'switch', search: true, width: 100 },
      { prop: 'update_time', label: '更新时间', type: 'datetime', form: false, width: 170 }
    ],
    related: {
      title: '知识条目',
      resource: 'knowledge-item',
      foreignKey: 'knowledge_base_id',
      fields: [
        { prop: 'title', label: '条目标题', search: true, required: true, minWidth: 180 },
        { prop: 'content_type', label: '内容类型', search: true, required: true, width: 120 },
        { prop: 'content_url', label: '内容地址', minWidth: 220 },
        { prop: 'content_text', label: '文本内容', type: 'textarea', search: true, minWidth: 260 },
        { prop: 'status', label: '状态', type: 'switch', width: 100 }
      ],
      searchable: true
    }
  },
  agent: {
    title: '智能体管理',
    resource: 'agent',
    description: '维护智能体、关联知识库、提示词配置和回复策略。',
    fields: [
      { prop: 'name', label: '名称', search: true, required: true, minWidth: 180 },
      { prop: 'prompt_config', label: '背景配置', type: 'textarea', minWidth: 260 },
      { prop: 'remark', label: '介绍', type: 'textarea', minWidth: 220 },
      { prop: 'status', label: '启用状态', type: 'switch', width: 100 }
    ]
  },
  'customer-session': {
    title: '客服会话',
    resource: 'customer-session',
    description: '参照桌面消息页处理用户和企业端客服会话。',
    customerService: true,
    readonly: true,
    fields: [
      { prop: 'student_name', label: '学员名称', minWidth: 140 },
      { prop: 'staff_name', label: '客服名称', minWidth: 140 },
      { prop: 'session_from', label: '发起人', type: 'number', search: true, width: 110 },
      { prop: 'session_to', label: '接收人', type: 'number', search: true, width: 110 },
      { prop: 'last_message_content', label: '最近消息', search: true, minWidth: 260 },
      { prop: 'last_message_time', label: '最近时间', type: 'datetime', width: 170 },
      { prop: 'unread_count', label: '未读数', type: 'number', width: 90 }
    ],
    related: {
      title: '会话消息',
      resource: 'customer-message',
      foreignKey: 'session_id',
      fields: [
        { prop: 'student_name', label: '学员名称', minWidth: 140 },
        { prop: 'staff_name', label: '客服名称', minWidth: 140 },
        { prop: 'session_from', label: '发送人', type: 'number', width: 110 },
        { prop: 'session_to', label: '接收人', type: 'number', width: 110 },
        { prop: 'message_type', label: '消息类型', width: 110 },
        { prop: 'content', label: '消息内容', type: 'textarea', minWidth: 260 },
        { prop: 'create_time', label: '发送时间', type: 'datetime', form: false, width: 170 }
      ]
    }
  }
}

export const fallbackConfig = yjResourceConfigs['enterprise-audit']
