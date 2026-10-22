"""Deterministic, content-driven B-roll renderer. No model/API calls.
Scene renderers accept (Canvas, scene, local_seconds). See references/extending.md.
"""
import math, re
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageColor

ROOT=Path(__file__).resolve().parent.parent
BUNDLED=ROOT/"assets/fonts/SmileySans-Oblique.ttf"
def clamp(v): return max(0.,min(1.,v))
def ease(v): v=clamp(v);return v*v*(3-2*v)
def rgb(c): return tuple(c) if isinstance(c,(tuple,list)) else ImageColor.getrgb(c)
def blend(a,b,p): return tuple(round(x*(1-p)+y*p) for x,y in zip(rgb(a),rgb(b)))
def progress(s,t,index=0,count=1):
 starts=s.get("cue_times")
 start=starts[index] if starts and index<len(starts) else .25+index*max(.2,(s["duration"]-1.7)/max(1,count))
 return ease((t-start)/min(.65,s["duration"]*.18))
@lru_cache(maxsize=256)
def load_font(path,size): return ImageFont.truetype(str(path),int(size))
@lru_cache(maxsize=8)
def glyphs(path):
 from fontTools.ttLib import TTFont
 f=TTFont(str(path),fontNumber=0);chars=set()
 for tab in f["cmap"].tables:
  if tab.isUnicode():chars.update(tab.cmap)
 f.close();return chars

class LayoutError(ValueError): pass
class Canvas:
 def __init__(self,w,h,style,font_path,seed=17):
  self.w,self.h,self.u=w,h,min(w,h)/720
  self.style,self.font_path,self.seed=style,str(font_path),seed
  self.fg,self.ac,self.panel=style["fg"],style["accent"],style["panel"]
  self.image=Image.new("RGB",(w,h),style["bg"])
  self.boxes=[]
 @property
 def portrait(self): return self.h>self.w
 def line(self,points,color=None,width=2):
  ImageDraw.Draw(self.image).line(points,fill=color or self.ac,width=max(1,round(width*self.u)),joint="curve")
 def rect(self,box,fill=None,radius=14,outline=None):
  ImageDraw.Draw(self.image).rounded_rectangle(tuple(round(v) for v in box),radius*self.u,fill=fill or self.panel,outline=outline,width=max(1,round(2*self.u)))
 def circle(self,x,y,r,fill=None,outline=None,width=2):
  ImageDraw.Draw(self.image).ellipse((x-r,y-r,x+r,y+r),fill=fill,outline=outline,width=max(1,round(width*self.u)))
 def text(self,value,box,size=38,min_size=20,color=None,align="center",max_lines=6,fit_value=None):
  """Fit complete text, never truncate. Error if the smallest readable size won't fit."""
  if not value:return
  value=str(value);x,y,w,h=box
  if w<=0 or h<=0:raise LayoutError("Text box has no area")
  missing={c for c in value if not c.isspace() and ord(c) not in glyphs(self.font_path)}
  if missing:raise LayoutError("Font lacks glyphs: "+repr("".join(sorted(missing)))+"; choose --font with required coverage")
  def wrap(content,f):
   rows=[]
   for paragraph in content.split("\n"):
    row=""
    # Keep Latin words intact; CJK wraps by glyph. Very long words still wrap safely.
    for token in re.findall(r"[A-Za-z0-9_]+(?:['’.-][A-Za-z0-9_]+)*|\s+|.",paragraph):
     if f.getlength(row+token)>w and row:rows.append(row.rstrip());row=""
     if not row:token=token.lstrip()
     for ch in token:
      if f.getlength(row+ch)>w and row:rows.append(row.rstrip());row=""
      row+=ch
    rows.append(row.rstrip())
   return rows
  lines=None
  for px in range(max(1,round(size*self.u)),max(1,round(min_size*self.u))-1,-1):
   f=load_font(self.font_path,px);candidate=wrap(fit_value or value,f)
   lh=px*1.4
   if len(candidate)<=max_lines and len(candidate)*lh<=h and all(f.getlength(z)<=w for z in candidate):
    lines=wrap(value,f) if fit_value else candidate;break
  if lines is None:raise LayoutError(f"Text too long for layout ({len(value)} chars): {value[:60]!r}. Split scene or shorten the display copy; preserve full narration in source_text.")
  d=ImageDraw.Draw(self.image);yy=y+(h-len(lines)*lh)/2
  for row in lines:
   tw=f.getlength(row);xx=x if align=="left" else x+(w-tw)/2 if align=="center" else x+w-tw
   d.text((round(xx),round(yy)),row,font=f,fill=color or self.fg,anchor="lt")
   yy+=lh
  self.boxes.append((x,y,w,h))
 def path(self,points,p,color=None,width=3):
  if not points:return (0,0)
  pts=np.array(points,float);dist=np.linalg.norm(np.diff(pts,axis=0),axis=1);left=sum(dist)*clamp(p);out=[tuple(pts[0])]
  for a,b,d in zip(pts,pts[1:],dist):
   if left>=d:out.append(tuple(b));left-=d
   else:
    if d:out.append(tuple(a+(b-a)*left/d))
    break
  if len(out)>1:self.line(out,color,width)
  return out[-1]
 def panel_text(self,item,box,p,index=0):
  x,y,w,h=box;y+=(1-p)*35*self.u
  self.rect((x,y,x+w,y+h),self.panel,12,self.ac if self.style["texture"]=="paper" else None)
  self.text(f"{index+1:02d}",(x+12*self.u,y+8*self.u,w-24*self.u,h*.22),24,18,self.ac)
  self.text(item.get("label",""),(x+w*.08,y+h*.26,w*.84,h*.34),39,23)
  if item.get("detail"):self.text(item["detail"],(x+w*.08,y+h*.64,w*.84,h*.28),23,18,max_lines=3)
 def background(self,t):
  w,h=self.w,self.h;texture=self.style["texture"];d=ImageDraw.Draw(self.image)
  if texture in ("soft","social"):
   # Low-resolution deterministic field, upsampled once per frame.
   yy,xx=np.mgrid[0:90,0:160];g=np.exp(-((xx/160-.3)**2+(yy/90-.35)**2)*7)
   a=np.array(rgb(self.style["bg"]));b=np.array(rgb(self.ac))
   arr=a+(b-a)*g[:,:,None]*(.65 if texture=="social" else .15)
   self.image=Image.fromarray(arr.astype("uint8")).resize((w,h),Image.Resampling.BILINEAR);d=ImageDraw.Draw(self.image)
  if texture=="grid":
   c=blend(self.style["bg"],self.ac,.12);step=max(20,int(48*self.u))
   for x in range(0,w,step):d.line((x,0,x,h),fill=c)
   for y in range(0,h,step):d.line((0,y,w,y),fill=c)
  if texture in ("dust","dots","paper"):
   rng=np.random.default_rng(self.seed)
   for x,y,r in rng.uniform(0,1,(95,3)):
    yy=(y*h-t*(3+r*4)*self.u)%h;rr=(.6+r)*self.u
    self.circle(x*w,yy,rr,blend(self.style["bg"],self.ac,.12 if texture=="paper" else .32))
  if texture=="rays":
   for j in range(20):
    a=j*math.tau/20+.02*t;r=min(w,h)*.4
    self.line([(w/2+math.cos(a)*r,h/2+math.sin(a)*r),(w/2+math.cos(a)*r*2,h/2+math.sin(a)*r*2)],blend(self.style["bg"],self.ac,.16),1)
  if texture=="neon":
   horizon=h*.69
   for j in range(-8,17):
    self.line([(w/2,horizon),(j*w/8,h)],blend(self.style["bg"],self.ac,.5),1)
   for j in range(10):
    q=((j+t)%10)/10;yy=horizon+q*q*(h-horizon);self.line([(0,yy),(w,yy)],blend(self.style["bg"],self.ac,.55),1)
  if texture=="pixel":
   d.rectangle((0,h*.85,w,h),fill="#75a46d")
   for j in range(12):
    x=((j*w/9)-t*15*self.u)%(w+w/5)-w/10
    d.rectangle((x,h*.23,x+w*.07,h*.25),fill=blend(self.style["bg"],"#ffffff",.7))

def body(c,s):
 if s.get("title"):c.text(s["title"],(c.w*.075,c.h*.065,c.w*.85,c.h*.16),49,27,max_lines=3)
 if s.get("footer"):c.text(s["footer"],(c.w*.08,c.h*.89,c.w*.84,c.h*.065),23,18,max_lines=2)
 return (c.w*.08,c.h*.27,c.w*.84,c.h*.55)
def items(s):return s.get("items",[])

def kinetic(c,s,t):
 words=items(s) or [{"label":s["title"]}]
 interval=s["duration"]/len(words);index=min(len(words)-1,int(t/interval))
 p=ease((t-index*interval)/min(.45,interval*.35))
 box=(c.w*.08,c.h*.29+(1-p)*c.h*.08,c.w*.84,c.h*.35)
 if s.get("eyebrow"):c.text(s["eyebrow"],(c.w*.1,c.h*.13,c.w*.8,c.h*.1),24,18,c.ac)
 c.text(words[index]["label"],box,95-20*(1-p),32,max_lines=4)
 if words[index].get("detail"):c.text(words[index]["detail"],(c.w*.12,c.h*.68,c.w*.76,c.h*.12),28,20,c.ac)
 if s.get("footer"):c.text(s["footer"],(c.w*.1,c.h*.88,c.w*.8,c.h*.06),22,18)
 if c.style["texture"]=="neon" and int(t*10)%17==3:
  for j in range(3):
   y=int(c.h*(.38+j*.07));part=c.image.crop((0,y,c.w,y+max(2,int(c.h*.008))))
   c.image.paste(part,(int(9*c.u),y))
 if c.style["id"]=="BR-003":
  zoom=1+.7*(1-ease((t-index*interval)/.3))
  if zoom>1:
   big=c.image.resize((round(c.w*zoom),round(c.h*zoom)),Image.Resampling.BICUBIC)
   left=(big.width-c.w)//2;top=(big.height-c.h)//2
   c.image=big.crop((left,top,left+c.w,top+c.h))

def cards(c,s,t):
 x,y,w,h=body(c,s);a=items(s);n=len(a)
 cols=1 if c.portrait else min(3,n);rows=math.ceil(n/cols)
 gap=20*c.u;cw=(w-(cols-1)*gap)/cols;ch=(h-(rows-1)*gap)/rows
 for i,it in enumerate(a):
  p=progress(s,t,i,n)
  if p:c.panel_text(it,(x+i%cols*(cw+gap),y+i//cols*(ch+gap),cw,ch),p,i)

def process(c,s,t):
 x,y,w,h=body(c,s);a=items(s);n=len(a);vertical=c.portrait or n>4
 for i,it in enumerate(a):
  p=progress(s,t,i,n)
  if not p:continue
  if vertical:
   bh=h/n*.7;bw=w*.78;xx=x+w*.11;yy=y+i*h/n
  else:bh=h*.66;bw=w/n*.78;xx=x+i*w/n;yy=y+h*.12
  c.rect((xx,yy,xx+bw,yy+bh),c.panel,14)
  perimeter=[(xx,yy),(xx+bw,yy),(xx+bw,yy+bh),(xx,yy+bh),(xx,yy)]
  tip=c.path(perimeter,p,c.ac,2)
  if c.style["texture"]=="paper" and p<1:
   c.line([tip,(tip[0]+18*c.u,tip[1]-34*c.u)],c.fg,7)
  if p>.4:
   c.text(it["label"],(xx+bw*.08,yy+bh*.12,bw*.84,bh*.44),36,23)
   if it.get("detail"):c.text(it["detail"],(xx+bw*.08,yy+bh*.58,bw*.84,bh*.34),23,18)
  if i<n-1 and p>.95:
   if vertical:aa=(xx+bw/2,yy+bh+6*c.u);bb=(aa[0],y+(i+1)*h/n-7*c.u)
   else:aa=(xx+bw+7*c.u,yy+bh/2);bb=(x+(i+1)*w/n-7*c.u,aa[1])
   c.line([aa,bb],c.ac,2)
   if vertical:c.line([(bb[0]-5*c.u,bb[1]-7*c.u),bb,(bb[0]+5*c.u,bb[1]-7*c.u)],c.ac)
   else:c.line([(bb[0]-7*c.u,bb[1]-5*c.u),bb,(bb[0]-7*c.u,bb[1]+5*c.u)],c.ac)

def branch(c,s,t):
 x,y,w,h=body(c,s);a=items(s);n=len(a);root=(x+w/2,y+h*.15)
 c.text(s["root"],(x+w*.2,y-h*.08,w*.6,h*.15),38,22,c.ac)
 if c.portrait:
  root=(x+w*.12,y+h*.12)
  for i,it in enumerate(a):
   end=(x+w*.42,y+h*(.18+.75*i/max(1,n-1)));p=progress(s,t,i,n)
   pts=[root,(root[0],end[1]),end];c.path(pts,p,c.ac)
   if p>.9:c.circle(*end,4*c.u,c.ac);c.text(it["label"],(end[0]+12*c.u,end[1]-h*.075,w*.53,h*.15),29,21,align="left")
 else:
  for i,it in enumerate(a):
   end=(x+w*(i+.5)/n,y+h*.68);p=progress(s,t,i,n)
   pts=[root,(root[0],y+h*.35),end];c.path(pts,p,c.ac,2)
   if p>.9:c.circle(*end,4*c.u,c.ac);c.text(it["label"],(end[0]-w/n*.43,end[1]+h*.06,w/n*.86,h*.24),30,21)

def compare(c,s,t):
 x,y,w,h=body(c,s)
 for i,it in enumerate(items(s)):
  if c.portrait:box=(x,y+i*h*.53,w,h*.47)
  else:box=(x+i*w*.53,y,w*.47,h)
  p=progress(s,t,i,2)
  if p:c.panel_text(it,box,p,i)

def bars(c,s,t):
 x,y,w,h=body(c,s);a=items(s);n=len(a)
 end=[it["value"] for it in a];start=[it.get("from",0) for it in a]
 p=ease(t/max(.1,s["duration"]-.8));values=np.array(start)+(np.array(end)-start)*p
 maxv=s.get("max_value",max(max(end),max(start),1))
 positions=list(range(n))
 if s.get("rank"):
  # Interpolate ranks between neighboring discrete time samples; no fabricated values.
  def rank_at(q):
   v=np.array(start)+(np.array(end)-start)*q
   order=sorted(range(n),key=lambda i:(-v[i],i));return np.array([order.index(i) for i in range(n)],float)
  lo=math.floor(p*30)/30;hi=min(1,lo+1/30);f=ease((p-lo)*30)
  positions=rank_at(lo)*(1-f)+rank_at(hi)*f
 row=h/n
 for i,it in enumerate(a):
  yy=y+positions[i]*row;v=float(values[i]);col=c.ac if it.get("highlight") else blend(c.panel,c.ac,.35)
  c.text(it["label"],(x,yy,w*.24,row*.72),26,18,align="right",max_lines=2)
  bx=x+w*.28;bw=w*.57*max(0,v)/maxv
  if bw>0:c.rect((bx,yy+row*.15,bx+bw,yy+row*.65),col,4)
  value=f'{v:.{s.get("decimals",0)}f}'+s.get("unit","")
  c.text(value,(bx+bw+5*c.u,yy,w*.14,row*.72),23,17,col,align="left",max_lines=1)
 if s.get("data_note"):c.text(s["data_note"],(x,c.h*.825,w,c.h*.05),20,17)

def orbit(c,s,t):
 x,y,w,h=body(c,s);a=items(s);cx=x+w/2;cy=y+h*.49
 rx=w*.34;ry=h*.35
 c.circle(cx,cy,min(w,h)*.13,c.panel,outline=c.ac)
 c.text(s["center"],(cx-w*.16,cy-h*.12,w*.32,h*.24),31,21)
 for j in range(80):
  z=j*math.tau/80;c.circle(cx+rx*math.cos(z),cy+ry*math.sin(z),1.2*c.u,c.ac)
 for i,it in enumerate(a):
  z=i*math.tau/len(a)+t*.35;r=min(w,h)*.07;xx=cx+rx*math.cos(z);yy=cy+ry*math.sin(z)
  c.circle(xx,yy,r,c.ac)
  c.text(it["label"],(xx-w*.14,yy+r+7*c.u,w*.28,h*.14),25,18,max_lines=2)

def points_for(s):
 if "points" in s:return np.array(s["points"],float)
 a=np.linspace(0,math.tau,256,endpoint=False);shape=s["shape"]
 if shape=="heart":return np.array([16*np.sin(a)**3,-(13*np.cos(a)-5*np.cos(2*a)-2*np.cos(3*a)-np.cos(4*a))]).T/20
 if shape=="lissajous":return np.array([np.cos(2*a),np.sin(3*a)]).T
 if shape=="circle":return np.array([np.cos(a),np.sin(a)]).T
 return np.array([np.linspace(-1,1,256),np.sin(a)*.7]).T
def trace(c,s,t):
 x,y,w,h=body(c,s);pts=points_for(s);cx=x+w/2;cy=y+h/2;scale=min(w,h)*.42
 for yy in [cy]:c.line([(x,yy),(x+w,yy)],blend(c.style["bg"],c.ac,.3),1)
 c.line([(cx,y),(cx,y+h)],blend(c.style["bg"],c.ac,.3),1)
 p=clamp((t-.2)/(s["duration"]-.8))
 if s.get("fourier"):
  z=pts[:,0]+1j*pts[:,1];coef=np.fft.fft(z)/len(z);freq=np.fft.fftfreq(len(z))*len(z);order=np.argsort(-abs(coef))[:s.get("terms",20)]
  current=complex(cx,cy);reconstructed=np.zeros(len(z),complex);phase=np.arange(len(z))/len(z)*math.tau
  for k in order:
   rr=abs(coef[k])*scale;new=current+coef[k]*np.exp(1j*freq[k]*p*math.tau)*scale
   if rr>1:c.circle(current.real,current.imag,rr,outline=blend(c.style["bg"],c.ac,.35),width=1)
   c.line([(current.real,current.imag),(new.real,new.imag)],blend(c.style["bg"],c.ac,.65),1)
   current=new;reconstructed+=coef[k]*np.exp(1j*freq[k]*phase)
  pts=np.array([reconstructed.real,reconstructed.imag]).T
 pp=[(cx+a*scale,cy+b*scale) for a,b in pts]
 tip=c.path(pp,p,c.ac,3);c.circle(*tip,4*c.u,c.ac)

def journey(c,s,t):
 x,y,w,h=body(c,s);a=items(s);n=len(a);p=clamp(t/(s["duration"]-.5));stage=min(n-1,int(p*n));local=min(.999,p*n-stage)
 vertical=c.portrait;positions=[]
 for i,it in enumerate(a):
  xx=x+w*(.25 if vertical else (i+.5)/n);yy=y+h*((i+.5)/n if vertical else .58);positions.append((xx,yy))
  c.rect((xx-9*c.u,yy-10*c.u,xx+9*c.u,yy+10*c.u),c.ac,0)
  c.text(it["label"],(xx+30*c.u if vertical else xx-w/n*.45,yy-23*c.u if vertical else yy+38*c.u,w*.65 if vertical else w/n*.9,52*c.u),28,20,align="left" if vertical else "center")
 target=positions[stage];prev=positions[max(0,stage-1)]
 xx=prev[0]+(target[0]-prev[0])*local;yy=prev[1]+(target[1]-prev[1])*local-35*c.u*math.sin(local*math.pi)-42*c.u
 size=8*c.u;c.rect((xx-2*size,yy-2*size,xx+2*size,yy+2*size),c.fg,0)
 c.rect((xx-size,yy-size,xx+size,yy),c.ac,0)
 c.text(f"{min(n,int(p*n))} / {n}",(x,y-h*.12,w,h*.1),25,20,c.ac)

def code(c,s,t):
 x,y,w,h=body(c,s);lines=s["code"];c.rect((x,y,x+w,y+h),c.panel,12)
 available=h*.85;row=available/len(lines)
 for i,value in enumerate(lines):
  p=progress(s,t,i,len(lines));n=int(p*len(value))
  if p:
   # Fit against complete code first, so the font never jumps while typing.
   full=value;box=(x+w*.09,y+h*.07+i*row,w*.84,row*.9)
   c.text(value[:n],box,27,17,max_lines=2,align="left",color=c.ac if i%2 else c.fg,fit_value=full)
   c.text(str(i+1),(x+w*.015,box[1],w*.055,box[3]),19,17,color=c.ac,max_lines=1)

def phone(c,s,t):
 x,y,w,h=body(c,s);pw=min(w*.65 if c.portrait else w*.35,h*.6);ph=h
 px=x if not c.portrait else x+(w-pw)/2;py=y
 c.rect((px,py,px+pw,py+ph),c.panel,30,c.ac)
 c.rect((px+pw*.31,py+ph*.025,px+pw*.69,py+ph*.065),c.style["bg"],10)
 a=items(s);n=len(a)
 for i,it in enumerate(a):
  p=progress(s,t,i,n)
  if not p:continue
  yy=py+ph*.14+i*ph*.74/n
  c.rect((px+pw*.07,yy,px+pw*.93,yy+ph*.65/n),blend(c.panel,c.ac,.15),8)
  c.text(it["label"],(px+pw*.12,yy,pw*.76,ph*.65/n),28,20)
 if not c.portrait and s.get("callout"):c.text(s["callout"],(x+w*.48,y+h*.2,w*.49,h*.6),46,24)

def landscape(c,s,t):
 x,y,w,h=body(c,s);d=ImageDraw.Draw(c.image)
 c.circle(c.w*.77,c.h*.34,32*c.u,c.ac)
 for j in range(4):
  xx=np.linspace(0,c.w,220);base=c.h*(.55+j*.055)
  yy=base-(np.sin(xx/(120*c.u)+j+t*.02)+.35*np.cos(xx/(49*c.u)+j))*38*c.u
  col=blend(c.style["bg"],c.fg,.13+j*.055);d.polygon(list(zip(xx,yy))+[(c.w,c.h*.82),(0,c.h*.82)],fill=col)
  # Fine ink-like descending strokes, not source footage.
  for k in range(0,len(xx),3):d.line((xx[k],yy[k],xx[k]-5*c.u,yy[k]+36*c.u),fill=blend(col,c.fg,.12))
 bx=c.w*(.25+.012*t);by=c.h*.76
 d.polygon([(bx-33*c.u,by),(bx+34*c.u,by),(bx+20*c.u,by+9*c.u),(bx-22*c.u,by+9*c.u)],fill=c.fg)
 if s.get("quote"):c.text(s["quote"],(x,c.h*.39,w*.6,c.h*.13),35,23,align="left")

def mesh(c,s,t):
 """Projected parametric tube with depth sorting and diffuse/specular lighting."""
 x,y,w,h=body(c,s)
 if s.get("image"):
  asset=Path(s["_base"])/s["image"]
  with Image.open(asset) as src:
   src=src.convert("RGBA");src.thumbnail((round(w*.9),round(h*.92)),Image.Resampling.LANCZOS)
   # User image is presented as a flat product cutout, never described as a reconstructed 3D model.
   px=round(x+(w-src.width)/2);py=round(y+(h-src.height)/2+math.sin(t*.8)*5*c.u)
   c.image.paste(src,(px,py),src)
  return
 a=np.linspace(0,math.tau,90,endpoint=False);kind=s["object"]
 if kind=="ring":curve=np.array([np.cos(a),np.sin(a),np.zeros_like(a)]).T;rad=.16
 else:curve=np.array([(2+np.cos(3*a))*np.cos(2*a),(2+np.cos(3*a))*np.sin(2*a),np.sin(3*a)]).T/2.5;rad=.19
 tangent=np.roll(curve,-1,axis=0)-np.roll(curve,1,axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
 n=np.cross(tangent,np.tile([0,0,1.],(len(a),1)));n/=np.linalg.norm(n,axis=1)[:,None];b=np.cross(tangent,n)
 angles=np.linspace(0,math.tau,28,endpoint=False)
 v=curve[:,None,:]+rad*(n[:,None,:]*np.cos(angles)[None,:,None]+b[:,None,:]*np.sin(angles)[None,:,None])
 xx,yy,zz=v.reshape(-1,3).T;ry=t*.4;rx=.55
 xx,zz=xx*np.cos(ry)+zz*np.sin(ry),-xx*np.sin(ry)+zz*np.cos(ry)
 yy,zz=yy*np.cos(rx)-zz*np.sin(rx),yy*np.sin(rx)+zz*np.cos(rx)
 scale=min(w,h)*.32;v=np.array([x+w/2+xx*scale,y+h/2+yy*scale,zz*scale]).T.reshape(len(a),28,3)
 faces=[];color=np.array(rgb(c.ac))
 for i in range(len(a)):
  for j in range(28):
   q=np.array([v[i,j],v[(i+1)%len(a),j],v[(i+1)%len(a),(j+1)%28],v[i,(j+1)%28]])
   normal=np.cross(q[1]-q[0],q[3]-q[0]);normal/=max(np.linalg.norm(normal),1e-8)
   light=abs(np.dot(normal,[-.4,-.55,.73]));col=tuple(np.clip(color*(.25+.75*light)+light**30*100,0,255).astype(int))
   faces.append((q[:,2].mean(),[tuple(p[:2]) for p in q],col))
 d=ImageDraw.Draw(c.image)
 for _,p,col in sorted(faces,key=lambda f:f[0]):d.polygon(p,fill=col)

LAYOUTS={"kinetic":kinetic,"cards":cards,"process":process,"timeline":process,"branch":branch,
 "compare":compare,"bars":bars,"orbit":orbit,"trace":trace,"journey":journey,
 "code":code,"phone":phone,"landscape":landscape,"product":mesh}

def render_scene(scene,t,w,h,style,font_path,seed=17):
 if str(font_path)==str(BUNDLED) and style.get("type")=="serif":
  font_path=ROOT/"assets/fonts/NotoSerifCJKsc-Regular.otf"
 c=Canvas(w,h,style,font_path,seed);c.background(t)
 LAYOUTS[scene["layout"]](c,scene,t)
 inset=scene.get("inset",1.)
 if inset!=1:
  out=Image.new("RGB",(w,h),"black");iw,ih=round(w*inset),round(h*inset)
  out.paste(c.image.resize((iw,ih),Image.Resampling.LANCZOS),((w-iw)//2,(h-ih)//2));return out
 return c.image
