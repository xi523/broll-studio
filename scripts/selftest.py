"""Meaningful regression tests for scene plans, aspect adaptation and deterministic rendering."""
import argparse, copy, hashlib, json, tempfile
from pathlib import Path
import broll, engine

CASES=[
 ("warm-gold","branch",{"title":"职业发展不只有一条路","root":"已有经验","items":[{"label":"深入专业"},{"label":"跨领域合作"},{"label":"独立项目"}]}),
 ("cream-paper","cards",{"title":"一餐的准备清单","items":[{"label":"备齐食材","detail":"按食谱称量"},{"label":"分装调料","detail":"先准备再烹饪"},{"label":"整理台面","detail":"留下操作空间"}]}),
 ("black-gold","kinetic",{"eyebrow":"关于学习","items":[{"label":"先理解"},{"label":"再练习"},{"label":"最后，讲给别人听"}]}),
 ("lemon-tech","compare",{"title":"两种整理资料的方法","items":[{"label":"按来源收藏","detail":"方便回看出处"},{"label":"按问题归类","detail":"方便下次查找"}]}),
 ("flat-science","orbit",{"title":"一场活动，需要哪些协作？","center":"活动筹备","items":[{"label":"内容"},{"label":"场地"},{"label":"时间"},{"label":"参与者"}]}),
 ("dark-math","trace",{"title":"两个方向的周期运动","shape":"lissajous","fourier":True,"terms":12,"footer":"示意：水平与垂直运动叠加"}),
 ("minimal-launch","product",{"title":"观察曲面如何接住光","object":"ring","footer":"程序几何示意，并非真实商品"}),
 ("whiteboard","process",{"title":"给植物换盆的准备","items":[{"label":"备好新盆"},{"label":"整理根系"},{"label":"填土固定"}],"footer":"具体操作需按植物品种调整"}),
 ("neon-glitch","kinetic",{"eyebrow":"CREATIVE PRACTICE","items":[{"label":"Make a small start"},{"label":"Turn ideas into motion"}]}),
 ("ink-wash","landscape",{"title":"给自己一点空白","quote":"走慢一点，也是在向前。"}),
 ("data-news","bars",{"title":"阅读时长记录","items":[{"label":"周一","value":20},{"label":"周二","value":35},{"label":"周三","value":45,"highlight":True}],"unit":"分钟","example_data":True,"data_note":"示例数据，仅演示图表动画"}),
 ("pixel","journey",{"title":"把练习拆成小关卡","items":[{"label":"读懂例题"},{"label":"独立尝试"},{"label":"复盘错误"}]}),
 ("code-editor","code",{"title":"把列表里的数字翻倍","code":["values = [1, 2, 3]","result = [x * 2 for x in values]","print(result)"],"footer":"代码展示，不代表本工具执行了此代码"}),
 ("soft-3d","product",{"title":"把线条想象成空间","object":"knot","footer":"抽象几何与简化光照"}),
 ("social-gradient","phone",{"title":"把读书笔记整理成卡片","items":[{"label":"记录一个问题"},{"label":"摘出关键解释"},{"label":"写下自己的例子"}],"callout":"从收藏，走向理解"})
]
def plan(width=1280,height=720,duration=4):
 scenes=[]
 for i,(style,layout,payload) in enumerate(CASES):
  s=dict(copy.deepcopy(payload),id=f"style-{i+1:02d}",style=style,layout=layout,duration=duration)
  s["source_text"]=payload.get("title",payload.get("eyebrow",""))
  scenes.append(s)
 return {"version":1,"width":width,"height":height,"fps":24,"scenes":scenes}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--out",required=True);args=ap.parse_args();out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
 report={"aspect_cases":[],"negative_cases":[]}
 for w,h in [(1280,720),(720,1280),(960,960)]:
  p=plan(w,h);broll.validate(p,out);broll.preflight(p,out,engine.BUNDLED)
  for s in p["scenes"]:
   s=broll.prepare_scene(s,out);style=broll.style_for(s,p)
   a=engine.render_scene(s,2.1,w,h,style,engine.BUNDLED)
   b=engine.render_scene(s,2.1,w,h,style,engine.BUNDLED)
   assert a.tobytes()==b.tobytes(),"Non-deterministic rendering"
   a.thumbnail((640,640));a.save(out/f"{s['id']}-{w}x{h}.jpg",quality=88)
  report["aspect_cases"].append({"size":[w,h],"scenes":15,"preflight":"pass","deterministic":"pass"})
 p=plan()
 def reject(name,mutator,layout=False):
  q=copy.deepcopy(p);mutator(q)
  try:
   broll.validate(q,out)
   if layout:broll.preflight(q,out,engine.BUNDLED)
  except (ValueError,TypeError,KeyError):report["negative_cases"].append(name);return
  raise AssertionError("Should reject: "+name)
 reject("duplicate-id",lambda q:q["scenes"][1].update(id=q["scenes"][0]["id"]))
 reject("odd-dimension",lambda q:q.update(width=721))
 reject("nan-duration",lambda q:q["scenes"][0].update(duration=float("nan")))
 reject("negative-bars",lambda q:q["scenes"][10]["items"][0].update(value=-2))
 reject("unknown-style",lambda q:q.update(style="unknown"))
 reject("missing-branch-root",lambda q:q["scenes"][0].pop("root"))
 reject("unreadable-copy",lambda q:q["scenes"][0].update(title="很长的标题"*300),True)
 reject("missing-glyph",lambda q:q["scenes"][0].update(title="Missing glyph \U0001f984"),True)
 reject("unlabelled-demo-data",lambda q:q["scenes"][10].pop("data_note"))
 reject("backwards-source-time",lambda q:q["scenes"][0].update(source_start=10,source_end=3))
 reject("missing-product",lambda q:q["scenes"][6].pop("object"))
 reject("bad-cues",lambda q:q["scenes"][1].update(cue_times=[2,1,0]))
 reject("oversized-code",lambda q:q["scenes"][12].update(code=["line"]*9))
 (out/"all-styles.json").write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
 portrait=plan(720,1280);portrait["scenes"]=[portrait["scenes"][i] for i in [0,1,3,7,10]]
 (out/"portrait.json").write_text(json.dumps(portrait,ensure_ascii=False,indent=2),encoding="utf-8")
 (out/"selftest-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
