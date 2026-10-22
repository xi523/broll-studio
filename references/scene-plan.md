# 场景协议 v1

写 UTF-8 JSON，不把用户文案拼进 shell。

```json
{
  "version": 1, "width": 1280, "height": 720, "fps": 30,
  "style": "whiteboard", "inset": 1,
  "scenes": [{
    "id": "cooking-steps", "layout": "process", "duration": 6,
    "title": "先备料，再下锅",
    "source_text": "把食材切好，锅热后下油，最后分批翻炒。",
    "source_start": 12.4, "source_end": 18.4,
    "cue_times": [0.2, 1.8, 3.5],
    "items": [{"label": "切好食材", "detail": "大小均匀"}, {"label": "热锅下油"}, {"label": "分批翻炒"}]
  }]
}
```

根字段：version=1；width/height（偶数，320–3840，最多3840×2160像素）；fps（12–60整数）；inset（0.65–1）；seed（非负整数）；style；scenes。可选 title（元信息）、font（路径）、style_overrides（仅 bg/fg/accent/panel）、audio（path/start/volume）。

场景公共字段：id（唯一ASCII字母数字或短横线/下划线，最多64字符）、style、layout（必须显式选）、duration（1–60秒）、title/footer/eyebrow、source_text、source_start/source_end、inset。

items 中每项有 label，可选 detail。常规最多5项，数据条最多8项。文字完整显示，放不下就报错并拆段。cue_times 为局部秒数，与 items（code布局为代码行）数量一致，用于 cards/process/timeline/branch/compare/code/phone；其他连续运动由 duration 控制。

| 布局 | 特有字段 |
| --- | --- |
| kinetic | title 或 items.label；多项按时长均分；eyebrow、item.detail可用 |
| cards/process/timeline | items；timeline日期放label，事件放detail |
| branch | root + items；只支持一层分支，深层关系写扩展 |
| compare | 恰好两项items，label方案，detail差异 |
| bars | items每项value、可选from/highlight；非负数。max_value、unit、decimals(0–4)、rank可选。需要source或example_data=true，示例必须有可见data_note |
| orbit | center + items；中心关系不自动代表天文模拟 |
| trace | shape=heart/lissajous/circle/sine 或 points=[[x,y],...]（4–4096点，坐标[-1.1,1.1]）；fourier和terms(1–128)可选 |
| journey | items阶段目标；跳跃是比喻，不是实际进度证据 |
| code | code为1–8行字符串；只绘制，不执行，不伪造运行结果 |
| phone | items；横屏可加callout。示意界面，不捏造用户评论背书 |
| landscape | title、可选quote/footer；意境不承担精确机制证明 |
| product | image本地素材或object=ring/knot；真实产品不能被任意几何体替代 |

source记录数据出处。自定义布局参数放params，见extending.md。

## 脚本适配

保留原文和时间证据。先写观众应该看懂什么，再选结构。标题通常20字以内、节点4–12字是阅读建议，不是截断规则；长句放source_text并拆段。没有数据不做数据图，没有因果不画因果箭头。替换所有示例人名、数字和主体。竖屏用纵向流程、单列卡片，改比例后重新预览。


## 动作设计与参数

先按directing.md写storyboard.md，再转成此协议。不能在根级/场景级添加不支持的字段；对象、状态和局部事件放自定义params，由组件显式读取。cue_times只控制上面列明的内置布局，不是通用动作系统。

例如“资料分类后装订成手册”需要实现纸页分组、书脊装订、翻到目标页的组件；把动词写进process的items并不会演出这些动作。新脚本重新安排duration和事件，不能沿用旧片的章节时间。
