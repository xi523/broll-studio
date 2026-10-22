#!/usr/bin/env python3
"""Validate a scene plan, render previews or MP4s, and preserve a timing map."""
import argparse, importlib.util, json, math, os, shutil, subprocess, sys
from pathlib import Path
import engine
from PIL import Image

ROOT=Path(__file__).resolve().parent.parent
STYLES=json.loads((ROOT/"assets/styles.json").read_text(encoding="utf-8"))
def fail(msg): raise ValueError(msg)
def number(value,name,low,high):
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:fail(f"{name}: expected finite number in [{low}, {high}]")
def string(v,name,required=False):
 if not isinstance(v,str) or (required and not v.strip()):fail(name+": expected "+("nonempty " if required else "")+"text")
 if len(v)>12000:fail(name+": too long; split the scene")
def read_plan(path):
 path=Path(path).resolve()
 data=json.loads(path.read_text(encoding="utf-8-sig"),parse_constant=lambda v:fail("JSON non-finite number: "+v))
 if not isinstance(data,dict):fail("Plan must be an object")
 return data,path.parent
def validate(plan,base):
 if plan.get("version")!=1:fail("version must be 1")
 for k in plan:
  if k not in {"version","width","height","fps","inset","style","scenes","audio","seed","title","style_overrides","font"}:fail("Unknown plan field: "+k)
 w,h,fps=plan.get("width",1280),plan.get("height",720),plan.get("fps",30)
 for k,v,lo,hi in [("width",w,320,3840),("height",h,320,3840),("fps",fps,12,60)]:
  number(v,k,lo,hi)
  if int(v)!=v:fail(k+" must be integer")
 if w%2 or h%2:fail("width/height must be even for yuv420p")
 if w*h>3840*2160:fail("Canvas exceeds supported pixel count")
 number(plan.get("inset",1),"inset",.65,1)
 number(plan.get("seed",17),"seed",0,2147483647)
 if int(plan.get("seed",17))!=plan.get("seed",17):fail("seed must be integer")
 if "font" in plan:
  string(plan["font"],"font",True)
  if not (base/plan["font"]).is_file():fail("font file not found")
 if plan.get("style","cream-paper") not in STYLES:fail("Unknown style")
 overrides=plan.get("style_overrides",{})
 if not isinstance(overrides,dict):fail("style_overrides must be an object")
 for k,v in overrides.items():
  if k not in {"bg","fg","accent","panel"}:fail("Only palette values can be overridden: "+k)
  engine.rgb(v)
 if "audio" in plan:
  a=plan["audio"]
  if not isinstance(a,dict) or set(a)-{"path","start","volume"}:fail("audio needs path/start/volume")
  string(a.get("path"),"audio.path",True)
  if not (base/a["path"]).is_file():fail("Audio file not found")
  number(a.get("start",0),"audio.start",0,86400);number(a.get("volume",1),"audio.volume",0,4)
 scenes=plan.get("scenes")
 if not isinstance(scenes,list) or not 1<=len(scenes)<=120:fail("scenes: provide 1–120 scenes")
 allowed={"id","style","layout","duration","title","eyebrow","footer","source_text","source_start","source_end","items","root","center","data_note","unit","decimals","max_value","rank","points","shape","fourier","terms","code","quote","callout","image","object","cue_times","inset","params","source","example_data"}
 ids=set()
 for index,s in enumerate(scenes):
  if not isinstance(s,dict):fail(f"Scene {index}: expected object")
  unknown=set(s)-allowed
  if unknown:fail(f"Scene {index}: unknown fields {sorted(unknown)}")
  sid=s.get("id",f"scene-{index+1:03d}")
  if not isinstance(sid,str) or not sid or len(sid)>64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in sid):fail("Scene id: use ASCII letters, numbers, '-' or '_'")
  if sid in ids:fail("Duplicate scene id: "+sid)
  ids.add(sid);s["id"]=sid
  style=s.get("style",plan.get("style","cream-paper"))
  if style not in STYLES:fail(sid+": unknown style "+str(style))
  s["style"]=style
  if "layout" not in s:fail(sid+": choose layout explicitly; style alone does not determine meaning")
  if s["layout"] not in engine.LAYOUTS:fail(sid+": unknown layout "+str(s["layout"]))
  number(s.get("duration"),sid+".duration",1,60)
  number(s.get("inset",plan.get("inset",1)),sid+".inset",.65,1)
  s["inset"]=s.get("inset",plan.get("inset",1))
  for k in ["title","eyebrow","footer","source_text","root","center","data_note","unit","quote","callout","source"]:
   if k in s:string(s[k],sid+"."+k)
  for k in ["rank","fourier","example_data"]:
   if k in s and not isinstance(s[k],bool):fail(sid+"."+k+" must be boolean")
  if ("source_start" in s)!=("source_end" in s):fail(sid+": source_start and source_end belong together")
  if "source_start" in s:
   number(s["source_start"],"source_start",0,86400);number(s["source_end"],"source_end",0,86400)
   if s["source_end"]<=s["source_start"]:fail("source_end must exceed source_start")
  a=s.get("items",[])
  if not isinstance(a,list) or len(a)>8:fail(sid+": items must be a list with at most 8 items; split dense content")
  for it in a:
   if not isinstance(it,dict) or set(it)-{"label","detail","value","from","highlight"}:fail(sid+": invalid item fields")
   string(it.get("label"),sid+".item.label",True)
   if "detail" in it:string(it["detail"],"item.detail")
   if "highlight" in it and not isinstance(it["highlight"],bool):fail("highlight must be boolean")
  layout=s["layout"]
  if layout in {"cards","process","timeline","branch","compare","bars","orbit","journey","phone"} and not a:fail(sid+": items required")
  if layout=="compare" and len(a)!=2:fail(sid+": compare requires exactly two items")
  if layout in {"cards","process","timeline","branch","orbit","journey","phone"} and len(a)>5:fail(sid+": at most five items per scene; split to preserve reading time")
  if layout=="kinetic" and not (a or s.get("title")):fail(sid+": title or items required")
  if layout=="branch":string(s.get("root"),sid+".root",True)
  if layout=="orbit":string(s.get("center"),sid+".center",True)
  if layout=="bars":
   if not s.get("source") and not s.get("example_data"):fail(sid+": bars requires source or example_data=true")
   if s.get("example_data") and not s.get("data_note"):fail(sid+": label example data visibly using data_note")
   for it in a:
    number(it.get("value"),"value",0,1e12);number(it.get("from",0),"from",0,1e12)
   if "max_value" in s:
    number(s["max_value"],"max_value",.00001,1e12)
    if max(max(it["value"],it.get("from",0)) for it in a)>s["max_value"]:fail("max_value is smaller than data")
   number(s.get("decimals",0),"decimals",0,4)
   if int(s.get("decimals",0))!=s.get("decimals",0):fail("decimals must be integer")
  if layout=="trace":
   if "points" in s:
    pp=s["points"]
    if not isinstance(pp,list) or not 4<=len(pp)<=4096:fail("points requires 4–4096 [x,y] samples")
    for pair in pp:
     if not isinstance(pair,list) or len(pair)!=2:fail("points must be [x,y]")
     for v in pair:number(v,"point coordinate",-1.1,1.1)
   elif s.get("shape") not in {"heart","lissajous","circle","sine"}:fail("trace needs points or named shape")
   number(s.get("terms",20),"terms",1,128)
   if int(s.get("terms",20))!=s.get("terms",20):fail("terms must be integer")
  if layout=="code":
   if not isinstance(s.get("code"),list) or not 1<=len(s["code"])<=8:fail("code: provide 1–8 lines")
   for v in s["code"]:string(v,"code line")
  if layout=="product":
   if "image" in s:
    string(s["image"],"image",True)
    if not (base/s["image"]).is_file():fail(sid+": product image not found")
   elif s.get("object") not in {"ring","knot"}:fail("product requires image or explicit object=ring/knot; do not invent a product")
  if "cue_times" in s:
   cues=s["cue_times"];count=len(s.get("code",a)) or 1
   if not isinstance(cues,list) or len(cues)!=count:fail(sid+": cue_times length must match elements")
   for q in cues:number(q,"cue time",0,s["duration"]-.1)
   if cues!=sorted(cues):fail("cue_times must increase")
  if "params" in s and not isinstance(s["params"],dict):fail(sid+": params must be an object")
 if sum(s["duration"] for s in scenes)>1800:fail("Split jobs longer than 30 minutes")
 return plan

def resolve_font(args,plan,base):
 path=args.font or plan.get("font")
 if path:
  p=Path(path).expanduser()
  if not p.is_absolute():p=base/p
  if not p.is_file():fail("Font not found: "+str(p))
  return p.resolve()
 return engine.BUNDLED
def style_for(s,plan):
 st=dict(STYLES[s["style"]]);st.update(plan.get("style_overrides",{}));return st
def prepare_scene(s,base):s=dict(s);s["_base"]=str(base);return s
def preflight(plan,base,font):
 # Verify persistent and changing text states, including full code/items, before any MP4 is written.
 for original in plan["scenes"]:
  s=prepare_scene(original,base)
  times={0,s["duration"]-.001,s["duration"]*.25,s["duration"]*.5,s["duration"]*.75}
  n=len(s.get("items",[]))
  if s["layout"]=="kinetic" and n:times.update((i+.7)*s["duration"]/n for i in range(n))
  for t in sorted(times):engine.render_scene(s,t,plan.get("width",1280),plan.get("height",720),style_for(s,plan),font,plan.get("seed",17))
def ffmpeg():
 if os.environ.get("BROLL_FFMPEG"):
  p=Path(os.environ["BROLL_FFMPEG"]).expanduser()
  if not p.is_file():fail("BROLL_FFMPEG does not exist")
  return str(p)
 import imageio_ffmpeg
 return imageio_ffmpeg.get_ffmpeg_exe()
def run(cmd):subprocess.run(cmd,check=True)
def preview(plan,base,font,out):
 out.mkdir(parents=True,exist_ok=True);frames=[]
 for s0 in plan["scenes"]:
  s=prepare_scene(s0,base);w,h=plan.get("width",1280),plan.get("height",720)
  for j,q in enumerate([.15,.5,.9]):
   im=engine.render_scene(s,s["duration"]*q,w,h,style_for(s,plan),font,plan.get("seed",17))
   path=out/f"{s['id']}-{j+1}.jpg";im.save(path,quality=92)
   frames.append(path.name)
 (out/"preview.json").write_text(json.dumps(frames,ensure_ascii=False,indent=2),encoding="utf-8")
def render(plan,base,font,out,overwrite):
 out.mkdir(parents=True,exist_ok=True);w,h,fps=plan.get("width",1280),plan.get("height",720),plan.get("fps",30)
 paths=[out/(s["id"]+".mp4") for s in plan["scenes"]]
 deliverables=paths+[out/"broll.mp4",out/"broll-silent.mp4"]
 if not overwrite and any(p.exists() for p in deliverables):fail("Output already exists; choose another folder or explicitly use --overwrite")
 ff=ffmpeg();timing=[];cursor=0
 for s0,path in zip(plan["scenes"],paths):
  s=prepare_scene(s0,base);frames=round(s["duration"]*fps);tmp=path.with_suffix(".partial.mp4")
  cmd=[ff,"-v","error","-y","-f","rawvideo","-pixel_format","rgb24","-video_size",f"{w}x{h}","-framerate",str(fps),"-i","pipe:0","-an","-c:v","libx264","-preset","fast","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart",str(tmp)]
  proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
  try:
   for f in range(frames):
    im=engine.render_scene(s,f/fps,w,h,style_for(s,plan),font,plan.get("seed",17))
    if im.mode!="RGB" or im.size!=(w,h):fail("Renderer must return RGB image at requested size")
    proc.stdin.write(im.tobytes())
   proc.stdin.close()
   if proc.wait()!=0:fail("FFmpeg failed for "+s["id"])
   tmp.replace(path)
  except BaseException:
   if proc.stdin and not proc.stdin.closed:proc.stdin.close()
   if proc.poll() is None:proc.terminate()
   proc.wait();raise
  duration=frames/fps
  timing.append({"id":s["id"],"style":s["style"],"layout":s["layout"],"file":path.name,"output_start":cursor,"output_end":cursor+duration,"source_start":s.get("source_start"),"source_end":s.get("source_end"),"source_text":s.get("source_text","")})
  cursor+=duration;print("Rendered",path.name,flush=True)
 # Simple generated ASCII filenames make concat quoting independent of user's folder name.
 concat=out/"concat.txt";concat.write_text("\n".join("file '"+p.name+"'" for p in paths),encoding="utf-8")
 silent=out/("broll-silent.mp4" if plan.get("audio") else "broll.mp4")
 run([ff,"-v","error","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy","-movflags","+faststart",str(silent)])
 if plan.get("audio"):
  a=plan["audio"]
  run([ff,"-v","error","-y","-i",str(silent),"-ss",str(a.get("start",0)),"-i",str(base/a["path"]),"-map","0:v:0","-map","1:a:0","-af",f"volume={a.get('volume',1)},apad","-t",str(cursor),"-c:v","copy","-c:a","aac","-movflags","+faststart",str(out/"broll.mp4")])
 run([ff,"-v","error","-i",str(out/"broll.mp4"),"-f","null","-"])
 (out/"timing.json").write_text(json.dumps(timing,ensure_ascii=False,indent=2),encoding="utf-8")
 (out/"plan.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
 (out/"render-report.json").write_text(json.dumps({"width":w,"height":h,"fps":fps,"duration":cursor,"scenes":len(paths),"decode_ok":True,"font":Path(font).name},ensure_ascii=False,indent=2),encoding="utf-8")
 print("Complete:",out/"broll.mp4",flush=True)

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("command",choices=["styles","validate","preview","render"])
 parser.add_argument("plan",nargs="?");parser.add_argument("--out");parser.add_argument("--font");parser.add_argument("--overwrite",action="store_true")
 parser.add_argument("--extension",help="Trusted, locally authored Python file exposing register(LAYOUTS)")
 args=parser.parse_args()
 if args.command=="styles":
  print(json.dumps(STYLES,ensure_ascii=False,indent=2));return
 if not args.plan:parser.error("plan.json is required")
 if args.extension:
  spec=importlib.util.spec_from_file_location("broll_extension",Path(args.extension).resolve());module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.register(engine.LAYOUTS)
 plan,base=read_plan(args.plan);validate(plan,base);font=resolve_font(args,plan,base)
 preflight(plan,base,font)
 if args.command=="validate":print("Valid: schema, required fields, glyphs and representative text layouts");return
 if not args.out:parser.error("--out is required")
 out=Path(args.out).expanduser().resolve()
 if args.command=="preview":preview(plan,base,font,out)
 else:render(plan,base,font,out,args.overwrite)
if __name__=="__main__":
 try:main()
 except (ValueError,FileNotFoundError) as exc:print("ERROR:",exc,file=sys.stderr);sys.exit(2)
