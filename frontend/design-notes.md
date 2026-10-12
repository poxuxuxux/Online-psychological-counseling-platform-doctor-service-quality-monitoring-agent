# 心衡 · 玉石绿与自然光

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
