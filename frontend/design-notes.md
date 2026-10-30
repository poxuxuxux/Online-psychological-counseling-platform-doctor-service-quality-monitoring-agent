# 心衡 · 青绿与纸面

## 2026-10-13 图表面板等宽等高

实施前计划与自审：沿用青绿主色与当前字号。双栏改为 1:1 等宽，使用网格拉伸使同一行的两个面板自然等高；不设置固定高度，展开每日数值时两栏一起延展。左侧维度表缩减单元格横向间距与辅助条长度，指标名称保持完整；右侧分布区贴合面板底部。手机仍单栏，不强行制造等高空白。

## 2026-10-13 图表并排调整

实施前计划与自审：保留青绿主色、现有字体与纸面样式。电脑端将“维度平均分”和“总分变化趋势”保持左右两栏，左侧雷达图与数值，右侧折线图与分布；删除 1280px 以下提前改为单栏的规则。760px 以下保留上下排列，图表和表格的局部滚动继续生效，避免挤压正文。

## 2026-10-13 视觉修订：阅读优先的质量工作台

实施前计划：保留主色 #087F73 与深色 #065E56。纸面 #FFFFFF，背景 #F4F6F5，正文 #243632，次级文字 #596963，边界 #DCE4E0。阅读正文 16px/1.8，操作与表格 14px，元信息 13–14px，区块标题 20px，页面标题 30px；数字使用等宽数字。主容器圆角 6px、按钮与输入 4px、表格与分区直角；圆形仅用于说话人和流程节点。去除面板浮动阴影、紫色均分图标、装饰叶片和多余渐变。

```text
固定白色侧栏 | 页面标题 / 来源 / 操作
青绿选中标记 | 咨询列表：白底、细线、明确选中行
             | 当前咨询信息 / 执行步骤
             | 原文记录                | 评价与证据

数据总览     | 轻照片横幅
             | 参评数 | 优质数 | 风险数 | 平均分（连续数据带）
             | 雷达图与维度数值        | 总分趋势

人工复核     | 全部 | 高 | 中 | 低（连续筛选带）
             | 优先级队列              | 原文、结论、复核意见
```

实施前自审：只是缩小圆角仍会保留模板化的重复卡片，所以将统计与优先级合并为连续区域，嵌套内容使用分隔线。主色保留，但避免大片彩色背景制造塑料感。中文阅读区放大到 16px，保持表格密度和手机局部横向滚动。高、中、低用明确文字、徽章和队列边线，保留证据状态与风险类别的区分。不改变评分、核验门槛、数据来源与接口行为。

参考：国内 [Ant Design 字体](https://ant.design/docs/spec/font-cn/) 与 [布局](https://ant.design/docs/spec/layout-cn/)，国外 [IBM Carbon Productive typography](https://v10.carbondesignsystem.com/guidelines/typography/productive/) 与 [USWDS Typography](https://designsystem.digital.gov/components/typography/)。参考其层级、对齐和阅读原则，本文字号与青绿视觉是针对本项目作出的选择。

实施后核对：类型检查、生产构建与 72 项前端功能测试通过；自包含预览的咨询切换、原文定位与优先级筛选运行检查通过。DOM 样式计算确认正文 16px、对话与引用 16px、列表 14px，统计项无圆角及阴影、主面板 6px。1050px 以下工作区改为单栏，窄屏表格与趋势图在自身区域滚动。未完成真实浏览器截图与手机视觉验收；本次检查不冒充该类验收。更新仅在本地，未推送或部署。

## 2026-10-13 咨询列表与核查优先级

第一轮计划：保留 #087F73 青绿、#20373E 文字、#EEF4F6 背景、#FFFFFF 卡片；优先级高用 #B52B41，中用 #9B5A00，低用 #087F73。沿用本地中文系统字体，列表 ID 14px 加粗，表头 12px，页面标题保持既有层级。上方为左对齐的咨询表格，每页 5 条；下方保留记录与评价的双栏，选中 ID 用青绿细边和浅底强调。复核页用数量筛选、队列徽章和详情说明形成三级信息层次。

```text
咨询对话 [ID 查询] [刷新] [数据来源]
ID / 类型 / 消息数 / 更新时间 / 评价状态 / 查看
[选中咨询信息]
[咨询记录]                 [服务质量评价与原文证据]

人工复核 [全部] [高] [中] [低]
[按优先级排序的项目]       [优先级 + 理由 / 原评价 / 证据 / 复核意见]
```

第二轮自审：不添加无作用的头像、总分或假数据库记录；列表不能只列报告，要覆盖尚未评价的咨询；核查优先级与证据状态并列，不把“材料冲突”改成风险诊断。颜色配明确文字，键盘可点选，窄屏只让表格自身滚动。不同咨询在切换前清空旧报告，返回时核对 ID；旧版后端没有列表接口时只展示真实返回的演示记录，提示来源。

## 本次设计依据

用户提供的心理咨询平台参考图：冰蓝灰背景、白色悬浮侧栏、咨询室大图、独立数据卡片、清晰图表与辅助侧栏。沿用心衡的质量评价产品身份，提高玉石绿的饱和度。只调整已有功能及入口，不新增 Agent。

## 第一轮：视觉与布局计划

- 主色 #087F73；深色 #065E56；文字 #20373E；背景 #EEF4F6；纸面 #FFFFFF。辅色琥珀用于优质卡片、珊瑚用于风险、紫罗兰用于均分。风险分类仍指服务质量。
- 中文使用苹方/等线/微软雅黑的本地系统字体；数字使用 Segoe UI 等宽数字。标题 28–34px，正文 14px，次级文案 12–13px；适当提高行距，不使用细小浅色文案撑高级感。
- 大图负责氛围，真实 HTML 负责所有标题与操作。阴影轻而短，圆角 14–22px；强色集中在导航、操作和数据曲线。

```text
白色浮动侧栏 | 标题与来源模式
             | 咨询室主视觉 + 进入评估工作台       | 评价闭环
             | 范围选择与来源提示                 | 证据核验入口
             | [参评] [优质] [风险] [平均分]      | 规则速览
             | [六维雷达+均值表] [日均折线+分布] | 指标/复核入口
             | 统计口径（可展开）
```

## 第二轮：实现前自审

参考图里的咨询师头像、评价与预约不适用于本项目，不直接搬入。保留与任务有关的咨询室照片、留白和颜色关系。右侧展示已有的核验—讨论—修正流程与真实页面入口，不把流程说明冒充实时执行状态。统计卡不放假增长率或装饰性假趋势。缩窄屏幕后侧栏内容移到图表下，手机使用两列统计卡和一列图表；大图文字区保持不透明的浅底，保证对比度。

## 资产来源

咨询室配图由内置 imagegen 工具生成；不代表真实机构或真实诊室。原始 PNG 保留，项目副本为 src/assets/consultation-room.png。生成图只用于氛围，不含数据、文字、医生或患者。

完整生成提示词：
Create a photorealistic editorial interior photograph for the wide hero banner of a premium Chinese psychological counseling quality dashboard. Landscape composition approximately 3:1. A quiet, welcoming real consulting room with one cream linen armchair, a small round oak side table with a ceramic cup, and a leafy plant, all in the right half of the frame. Sunlight from a large window on the right, gently diffused, realistic soft shadows, tactile linen and wood grain, sophisticated calm atmosphere. Left half is generous clean negative space: a pale cool ivory wall with very subtle aqua daylight, suitable for dark HTML headline overlay. Color accents are saturated jade and turquoise green foliage, warm natural cream, pale ice blue. Camera at seated eye level, understated professional architectural photography, believable slight material imperfections. No people, no text, no letters, no logos, no screens, no graphic overlays. Image asset only, not a UI mockup.

## 可访问性与数据约束

模式和来源提示保留。未知数值显示 —，证据不足不补 0；百分制阈值保持 ≥85 与 <60。图表仍支持键盘点选和完整数值表。保留减少动画偏好、打印、局部表格滚动与移动导航。所有图片为本地资源，离线预览内嵌图片，不依赖第三方图片链接。
