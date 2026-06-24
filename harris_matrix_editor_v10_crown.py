
import json, zipfile, re, xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from collections import defaultdict, deque, Counter

APP_TITLE = "Harris Matrix Editor V9 PRO"
BOX_W, BOX_H = 98, 40
LEFT, TOP = 260, 80
X_STEP, Y_STEP = 142, 88

TYPE_COLORS = {
    "Structural": "#A9CBE8",
    "Deposit": "#F6E3A1",
    "Cut": "#F2A6A6",
    "Fill": "#F5C77A",
    "Surface": "#BFE5B4",
    "Natural": "#D7D7D7",
    "Unexcavated": "#CFCFCF",
    "Same context": "#F3B6C4",
    "Unknown": "#EFEFEF"
}

def norm_id(cid):
    cid = str(cid).strip()
    if cid == "F!10":
        return "F110"
    return cid

def norm_type(t):
    if not t:
        return "Unknown"
    s = str(t).strip().lower()
    if "struct" in s or "wall" in s or "bygning" in s or "stone" in s:
        return "Structural"
    if "deposit" in s or s == "d" or "layer" in s or "lag" in s:
        return "Deposit"
    if "fill" in s:
        return "Fill"
    if "cut" in s:
        return "Cut"
    if "surface" in s or "interface" in s or "top" in s:
        return "Surface"
    if "natural" in s or "geology" in s:
        return "Natural"
    if "unexcavated" in s:
        return "Unexcavated"
    if "=" in str(t):
        return "Same context"
    return str(t) if str(t) in TYPE_COLORS else "Unknown"

def label_text(n):
    return str(n.get("label") or n.get("id") or "")

def clip_label(s, n=18):
    s = str(s)
    return s if len(s) <= n else s[:n-1] + "…"

def primary_num(s):
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else 999999

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1540x940")
        self.nodes = {}
        self.edges = []
        self.groups = []
        self.selected = None
        self.selected_group = None
        self.drag = (0,0)
        self.resizing_group = False
        self.moving_group = False
        self.zoom = 1.0
        self._ui()
        self.new_project()

    def _ui(self):
        tb = tk.Frame(self); tb.pack(fill=tk.X)
        for t,c in [
            ("Ny", self.new_project), ("Åbn HMCX", self.open_hmcx), ("Gem HMCX", self.save_hmcx),
            ("Åbn JSON", self.open_json), ("Gem JSON", self.save_json),
            ("Tilføj context", self.add_context), ("Tilføj relation", self.add_relation),
            ("Tilføj konstruktions-/faseboks", self.add_group), ("Slet valgt", self.delete_selected),
            ("Auto-layout V9", self.auto_layout), ("Kontroller", self.validate_show),
            ("Eksport PDF", self.export_pdf), ("Eksport PNG", self.export_png), ("Eksport SVG", self.export_svg),
            ("Eksport Graph", self.export_graph), ("Zoom +", lambda:self.set_zoom(self.zoom*1.15)),
            ("Zoom -", lambda:self.set_zoom(self.zoom/1.15)), ("Fit", self.fit), ("Søg", self.search)
        ]:
            tk.Button(tb, text=t, command=c).pack(side=tk.LEFT, padx=1, pady=2)

        main = tk.PanedWindow(self, orient=tk.HORIZONTAL); main.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(main); main.add(left, stretch="always")
        self.canvas = tk.Canvas(left, bg="white", scrollregion=(0,0,5600,3800))
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ys = tk.Scrollbar(left, orient=tk.VERTICAL, command=self.canvas.yview); ys.pack(side=tk.RIGHT, fill=tk.Y)
        xs = tk.Scrollbar(left, orient=tk.HORIZONTAL, command=self.canvas.xview); xs.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)

        right = tk.Frame(main, width=350); main.add(right)
        tk.Label(right, text="Inspector", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=8, pady=6)
        self.info = tk.Text(right, height=12, width=42); self.info.pack(fill=tk.X, padx=8)
        tk.Button(right, text="Opdater valgt", command=self.update_selected).pack(fill=tk.X, padx=8, pady=3)
        tk.Label(right, text="Relationer", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=8, pady=6)
        self.rels = tk.Listbox(right, height=14); self.rels.pack(fill=tk.BOTH, expand=True, padx=8)
        tk.Button(right, text="Slet valgt relation", command=self.delete_relation).pack(fill=tk.X, padx=8, pady=3)
        tk.Label(right, text="Feature type farver", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=8, pady=6)
        self.legend = tk.Canvas(right, height=210, bg="#FAFAFA"); self.legend.pack(fill=tk.X, padx=8)
        self.draw_legend()
        self.status = tk.StringVar(value="Klar")
        tk.Label(self, textvariable=self.status, anchor="w").pack(fill=tk.X)

        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Double-Button-1>", self.double_click)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<ButtonPress-3>", self.pan_start)
        self.canvas.bind("<B3-Motion>", self.pan_move)

    def draw_legend(self):
        self.legend.delete("all")
        y=12
        for k,c in TYPE_COLORS.items():
            self.legend.create_rectangle(10,y,30,y+16,fill=c,outline="black")
            self.legend.create_text(38,y+8,text=k,anchor="w",font=("Segoe UI",9))
            y += 22

    def sx(self,x): return x*self.zoom
    def sy(self,y): return y*self.zoom
    def ux(self,x): return x/self.zoom
    def uy(self,y): return y/self.zoom

    def new_project(self):
        self.nodes = {
            "T": {"id":"T","label":"T","type":"Surface","x":LEFT+300,"y":TOP,"w":80,"h":BOX_H},
            "Unexcavated": {"id":"Unexcavated","label":"Unexcavated","type":"Unexcavated","x":LEFT+240,"y":TOP+320,"w":170,"h":BOX_H}
        }
        self.edges = [{"source":"T","target":"Unexcavated"}]
        self.groups = []
        self.selected = None
        self.selected_group = None
        self.draw()

    def top_anchor(self, nid):
        n = self.nodes.get(nid, {})
        txt = (nid + " " + label_text(n) + " " + str(n.get("name",""))).lower()
        return nid.upper() in ("T","TOP") or "topsoil" in txt or "top surface" in txt or "græstørv" in txt

    def bottom_anchor(self, nid):
        n = self.nodes.get(nid, {})
        txt = (nid + " " + label_text(n) + " " + str(n.get("name",""))).lower()
        typ = norm_type(n.get("type"))
        return typ in ("Unexcavated","Natural") or nid.upper() in ("U","G","NATURAL") or "unexcavated" in txt or "geology" in txt

    def draw(self):
        self.canvas.delete("all")
        for y in range(70, 3400, Y_STEP):
            self.canvas.create_line(self.sx(120), self.sy(y), self.sx(5300), self.sy(y), fill="#F1F1F1")
        for i,g in enumerate(self.groups):
            outline = "#D33" if i == self.selected_group else "#6F8FB5"
            self.canvas.create_rectangle(self.sx(g["x"]),self.sy(g["y"]),self.sx(g["x"]+g["w"]),self.sy(g["y"]+g["h"]),
                                         outline=outline,dash=(6,5),width=2,tags=("group",str(i)))
            self.canvas.create_text(self.sx(g["x"]+8),self.sy(g["y"]+18),text=g.get("name","Konstruktion"),anchor="w",
                                    fill=outline,font=("Segoe UI",10,"bold"),tags=("group",str(i)))
            self.canvas.create_rectangle(self.sx(g["x"]+g["w"]-10),self.sy(g["y"]+g["h"]-10),self.sx(g["x"]+g["w"]+2),self.sy(g["y"]+g["h"]+2),
                                         fill=outline,outline="",tags=("gresize",str(i)))
        for e in self.edges:
            if e["source"] in self.nodes and e["target"] in self.nodes:
                self.draw_edge(e)
        for n in self.nodes.values():
            self.draw_node(n)
        self.update_panel()

    def draw_edge(self,e):
        a,b=self.nodes[e["source"]],self.nodes[e["target"]]
        aw,ah=a.get("w",BOX_W),a.get("h",BOX_H); bw,bh=b.get("w",BOX_W),b.get("h",BOX_H)
        x1,y1=a["x"]+aw/2,a["y"]+ah
        x2,y2=b["x"]+bw/2,b["y"]
        mid=(y1+y2)/2
        self.canvas.create_line(self.sx(x1),self.sy(y1),self.sx(x1),self.sy(mid),self.sx(x2),self.sy(mid),self.sx(x2),self.sy(y2),
                                fill="#111",width=2)

    def draw_node(self,n):
        x,y,w,h=n["x"],n["y"],n.get("w",BOX_W),n.get("h",BOX_H)
        color=TYPE_COLORS.get(norm_type(n.get("type")),TYPE_COLORS["Unknown"])
        outline="#C22" if n["id"]==self.selected else "#222"
        self.canvas.create_rectangle(self.sx(x),self.sy(y),self.sx(x+w),self.sy(y+h),fill=color,outline=outline,width=2,tags=("node",n["id"]))
        self.canvas.create_text(self.sx(x+w/2),self.sy(y+h/2),text=clip_label(n.get("label",n["id"])),font=("Segoe UI",9,"bold"),tags=("node",n["id"]))

    def hit(self,event):
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        for item in reversed(self.canvas.find_overlapping(x,y,x,y)):
            tags=self.canvas.gettags(item)
            if "node" in tags:
                for t in tags:
                    if t in self.nodes: return ("node",t)
            if "gresize" in tags:
                for t in tags:
                    if t.isdigit(): return ("gresize",int(t))
            if "group" in tags:
                for t in tags:
                    if t.isdigit(): return ("group",int(t))
        return (None,None)

    def press(self,event):
        kind,val=self.hit(event)
        self.selected=None; self.selected_group=None; self.resizing_group=False; self.moving_group=False
        x,y=self.ux(self.canvas.canvasx(event.x)),self.uy(self.canvas.canvasy(event.y))
        if kind=="node":
            self.selected=val; n=self.nodes[val]; self.drag=(x-n["x"],y-n["y"])
        elif kind=="gresize":
            self.selected_group=val; self.resizing_group=True; g=self.groups[val]; self.drag=(x-(g["x"]+g["w"]),y-(g["y"]+g["h"]))
        elif kind=="group":
            self.selected_group=val; self.moving_group=True; g=self.groups[val]; self.drag=(x-g["x"],y-g["y"])
        self.draw()

    def drag_motion(self,event):
        x,y=self.ux(self.canvas.canvasx(event.x)),self.uy(self.canvas.canvasy(event.y))
        dx,dy=self.drag
        if self.selected:
            self.nodes[self.selected]["x"]=round(x-dx)
            self.nodes[self.selected]["y"]=round(y-dy)
        elif self.selected_group is not None:
            g=self.groups[self.selected_group]
            if self.resizing_group:
                g["w"]=max(80,round(x-dx-g["x"]))
                g["h"]=max(55,round(y-dy-g["y"]))
            elif self.moving_group:
                g["x"]=round(x-dx); g["y"]=round(y-dy)
        self.draw()

    def release(self,event): pass

    def double_click(self,event):
        kind,val=self.hit(event)
        if kind=="node":
            n=self.nodes[val]
            label=simpledialog.askstring("Label","Label:",initialvalue=n.get("label",val),parent=self)
            if label is None: return
            typ=simpledialog.askstring("Feature Type","Structural / Deposit / Cut / Fill / Surface / Natural / Unexcavated / Same context:",initialvalue=n.get("type","Deposit"),parent=self)
            n["label"]=label; n["type"]=norm_type(typ)
        elif kind=="group":
            g=self.groups[val]
            name=simpledialog.askstring("Boksnavn","Navn:",initialvalue=g.get("name",""),parent=self)
            if name is not None: g["name"]=name
        self.draw()

    def wheel(self,event): self.set_zoom(self.zoom*(1.08 if event.delta>0 else 1/1.08))
    def set_zoom(self,z): self.zoom=max(0.3,min(2.5,z)); self.draw()
    def pan_start(self,event): self.pan=(event.x,event.y)
    def pan_move(self,event):
        dx=event.x-self.pan[0]; dy=event.y-self.pan[1]
        self.canvas.xview_scroll(int(-dx/2),"units"); self.canvas.yview_scroll(int(-dy/2),"units")
        self.pan=(event.x,event.y)

    def fit(self):
        if not self.nodes: return
        minx,miny,maxx,maxy=self.bounds()
        self.zoom=max(0.35,min(1.5,min(1100/max(1,maxx-minx),740/max(1,maxy-miny))))
        self.draw()
        self.canvas.xview_moveto(max(0,self.sx(minx-160)/5600))
        self.canvas.yview_moveto(max(0,self.sy(miny-120)/3800))

    def update_panel(self):
        self.info.delete("1.0",tk.END)
        if self.selected and self.selected in self.nodes:
            n=self.nodes[self.selected]
            self.info.insert("1.0",f"id={n['id']}\nlabel={n.get('label','')}\ntype={n.get('type','')}\nx={n.get('x',0)}\ny={n.get('y',0)}\n")
        self.rels.delete(0,tk.END)
        if self.selected:
            for i,e in enumerate(self.edges):
                if e["source"]==self.selected or e["target"]==self.selected:
                    self.rels.insert(tk.END,f"{i}: {e['source']} over {e['target']}")

    def update_selected(self):
        if not self.selected: return
        d={}
        for line in self.info.get("1.0",tk.END).splitlines():
            if "=" in line:
                k,v=line.split("=",1); d[k]=v
        n=self.nodes[self.selected]
        old=n["id"]; new=norm_id(d.get("id",old))
        if new != old:
            if new in self.nodes: messagebox.showerror("Fejl","ID findes allerede"); return
            self.nodes[new]=self.nodes.pop(old); self.nodes[new]["id"]=new
            for e in self.edges:
                if e["source"]==old: e["source"]=new
                if e["target"]==old: e["target"]=new
            self.selected=new; n=self.nodes[new]
        for k in ("label","type"):
            if k in d: n[k]=norm_type(d[k]) if k=="type" else d[k]
        for k in ("x","y"):
            if k in d:
                try: n[k]=float(d[k])
                except: pass
        self.draw()

    def add_context(self):
        cid=norm_id(simpledialog.askstring("Ny context","Context id, fx F118:",parent=self) or "")
        if not cid: return
        if cid in self.nodes: messagebox.showerror("Fejl","Findes allerede"); return
        typ=simpledialog.askstring("Feature Type","Structural / Deposit / Cut / Fill:",initialvalue="Deposit",parent=self) or "Deposit"
        self.nodes[cid]={"id":cid,"label":cid,"type":norm_type(typ),"x":LEFT,"y":TOP,"w":BOX_W,"h":BOX_H}
        self.draw()

    def add_relation(self):
        a=norm_id(simpledialog.askstring("Relation","Yngre/over:",parent=self) or "")
        b=norm_id(simpledialog.askstring("Relation","Ældre/under:",parent=self) or "")
        if not a or not b: return
        self.ensure(a); self.ensure(b)
        if not any(e["source"]==a and e["target"]==b for e in self.edges):
            self.edges.append({"source":a,"target":b})
        self.draw()

    def add_group(self):
        name=simpledialog.askstring("Konstruktionsboks/fase","Navn:",initialvalue="Konstruktion",parent=self)
        if name:
            self.groups.append({"name":name,"x":LEFT+100,"y":TOP+100,"w":360,"h":180})
            self.draw()

    def delete_selected(self):
        if self.selected:
            nid=self.selected
            del self.nodes[nid]
            self.edges=[e for e in self.edges if e["source"]!=nid and e["target"]!=nid]
            self.selected=None
        elif self.selected_group is not None:
            del self.groups[self.selected_group]
            self.selected_group=None
        self.draw()

    def delete_relation(self):
        sel=self.rels.curselection()
        if not sel: return
        idx=int(self.rels.get(sel[0]).split(":",1)[0])
        if 0<=idx<len(self.edges): del self.edges[idx]
        self.draw()

    def ensure(self,cid):
        if cid not in self.nodes:
            self.nodes[cid]={"id":cid,"label":cid,"type":"Unknown","x":LEFT,"y":TOP,"w":BOX_W,"h":BOX_H}

    def open_hmcx(self):
        p=filedialog.askopenfilename(filetypes=[("HMCX","*.hmcx"),("All files","*.*")])
        if p: self.load_hmcx(p)

    def load_hmcx(self,path):
        try:
            with zipfile.ZipFile(path) as z:
                names=z.namelist()
                xmlname="matrix.xml" if "matrix.xml" in names else next((n for n in names if n.endswith(".xml")),None)
                xml=z.read(xmlname).decode("utf-8",errors="ignore")
        except Exception as e:
            messagebox.showerror("HMCX fejl",str(e)); return
        root=ET.fromstring(xml)
        self.nodes={}; self.edges=[]; graph_id_to_unit={}
        for el in root.iter():
            if el.tag.endswith("node"):
                gid=el.attrib.get("id","")
                hmc=None
                for sub in el.iter():
                    if sub.tag.endswith("hmcnode"):
                        hmc=sub; break
                if hmc is not None:
                    cid=norm_id(hmc.attrib.get("id") or gid)
                    graph_id_to_unit[gid]=cid
                    x=float(hmc.attrib.get("x","0") or 0); y=float(hmc.attrib.get("y","0") or 0)
                    typ=norm_type(hmc.attrib.get("type","Unknown"))
                    if cid in ("U","Unexcavated"): typ="Unexcavated"
                    self.nodes[cid]={"id":cid,"label":cid,"type":typ,"x":x,"y":y,"w":max(BOX_W, min(170, len(cid)*12+38)),"h":BOX_H}
            elif el.tag.endswith("edge"):
                s=el.attrib.get("source"); t=el.attrib.get("target")
                if s and t:
                    a=norm_id(graph_id_to_unit.get(s,s)); b=norm_id(graph_id_to_unit.get(t,t))
                    if a!=b and not any(e["source"]==a and e["target"]==b for e in self.edges):
                        self.edges.append({"source":a,"target":b})
        self.normalize_layout()
        self.draw(); self.fit()
        self.status.set(f"Åbnede {Path(path).name}: {len(self.nodes)} contexts, {len(self.edges)} relationer")

    def normalize_layout(self):
        if not self.nodes: return
        xs=[n["x"] for n in self.nodes.values()]; ys=[n["y"] for n in self.nodes.values()]
        minx,miny=min(xs),min(ys)
        for n in self.nodes.values():
            n["x"]=round(n["x"]-minx+LEFT,2)
            n["y"]=round(n["y"]-miny+TOP,2)

    def layout_edges(self):
        clean=[]
        for e in self.edges:
            a,b=e["source"],e["target"]
            if a not in self.nodes or b not in self.nodes or a==b:
                continue
            if self.bottom_anchor(a):
                continue
            if self.top_anchor(b):
                continue
            clean.append((a,b))
        indeg=Counter(b for a,b in clean)
        out=Counter(a for a,b in clean)
        tops=[n for n in self.nodes if self.top_anchor(n)]
        bottoms=[n for n in self.nodes if self.bottom_anchor(n)]
        top=tops[0] if tops else None
        bottom=bottoms[0] if bottoms else None
        for n in self.nodes:
            if top and n != top and not self.bottom_anchor(n) and indeg[n]==0:
                clean.append((top,n))
            if bottom and n != bottom and not self.top_anchor(n) and out[n]==0:
                clean.append((n,bottom))
        return list(dict.fromkeys(clean))

    def auto_layout(self):
        clean=self.layout_edges()
        children=defaultdict(list); indeg={n:0 for n in self.nodes}
        for a,b in clean:
            children[a].append(b); indeg[b]=indeg.get(b,0)+1; indeg.setdefault(a,0)
        q=deque([n for n,d in indeg.items() if d==0])
        level={n:0 for n in self.nodes}
        visited=set()
        while q:
            n=q.popleft(); visited.add(n)
            for m in children[n]:
                level[m]=max(level.get(m,0),level[n]+1)
                indeg[m]-=1
                if indeg[m]==0: q.append(m)
        mid_default=max(level.values())//2+1 if level else 1
        for n in self.nodes:
            if n not in visited and not self.top_anchor(n) and not self.bottom_anchor(n):
                level[n]=mid_default
        max_mid=max([level[n] for n in self.nodes if not self.bottom_anchor(n)] or [0])
        for nid in self.nodes:
            if self.top_anchor(nid):
                level[nid]=0
            elif self.bottom_anchor(nid):
                level[nid]=max_mid+2
            else:
                level[nid]=max(1, level.get(nid,1))
        buckets=defaultdict(list)
        for nid in self.nodes: buckets[level[nid]].append(nid)
        for lev in sorted(buckets):
            arr=sorted(buckets[lev],key=self.sort_key)
            for i,nid in enumerate(arr):
                self.nodes[nid]["x"]=LEFT+i*X_STEP
                self.nodes[nid]["y"]=TOP+lev*Y_STEP
        self.draw(); self.fit()
        self.status.set("Auto-layout V9: topsoil/top øverst, unexcavated/natural nederst, øvrige efter stratigrafiske relationer")

    def sort_key(self,nid):
        group=0
        if nid in ("F14","F21","F22"): group=1
        return (group, primary_num(nid), nid)

    def validate_show(self):
        problems=[]
        g=defaultdict(list)
        for a,b in self.layout_edges(): g[a].append(b)
        temp=set(); perm=set()
        def visit(n,path):
            if n in temp:
                problems.append("Cirkulær relation: " + " → ".join(path+[n])); return
            if n in perm: return
            temp.add(n)
            for m in g.get(n,[]): visit(m,path+[n])
            temp.remove(n); perm.add(n)
        for n in self.nodes: visit(n,[])
        if problems: messagebox.showwarning("Kontrol","\n".join(problems))
        else: messagebox.showinfo("Kontrol","✓ Ingen cykler fundet i layout-grafen")

    def search(self):
        q=simpledialog.askstring("Søg","Context:",parent=self)
        if not q: return
        q=q.lower()
        for nid,n in self.nodes.items():
            if q in nid.lower() or q in label_text(n).lower():
                self.selected=nid; self.draw()
                self.canvas.xview_moveto(max(0,self.sx(n["x"]-250)/5600))
                self.canvas.yview_moveto(max(0,self.sy(n["y"]-180)/3800))
                return

    def bounds(self):
        xs=[]; ys=[]
        for n in self.nodes.values():
            xs += [n["x"],n["x"]+n.get("w",BOX_W)]; ys += [n["y"],n["y"]+n.get("h",BOX_H)]
        for g in self.groups:
            xs += [g["x"],g["x"]+g["w"]]; ys += [g["y"],g["y"]+g["h"]]
        return (min(xs)-80,min(ys)-80,max(xs)+80,max(ys)+80) if xs else (0,0,1000,700)

    def export_svg(self):
        p=filedialog.asksaveasfilename(defaultextension=".svg",filetypes=[("SVG","*.svg")])
        if p:
            Path(p).write_text(self.to_svg(),encoding="utf-8")
            messagebox.showinfo("SVG",p)

    def to_svg(self):
        minx,miny,maxx,maxy=self.bounds(); w=maxx-minx; h=maxy-miny
        parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{minx} {miny} {w} {h}"><rect x="{minx}" y="{miny}" width="{w}" height="{h}" fill="white"/>']
        for g in self.groups:
            parts.append(f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" fill="none" stroke="#6F8FB5" stroke-width="2" stroke-dasharray="6 5"/>')
            parts.append(f'<text x="{g["x"]+8}" y="{g["y"]+18}" font-family="Segoe UI, Arial" font-size="13" font-weight="bold" fill="#6F8FB5">{g.get("name","")}</text>')
        for e in self.edges:
            if e["source"] in self.nodes and e["target"] in self.nodes:
                a,b=self.nodes[e["source"]],self.nodes[e["target"]]
                aw,ah=a.get("w",BOX_W),a.get("h",BOX_H); bw,bh=b.get("w",BOX_W),b.get("h",BOX_H)
                x1,y1=a["x"]+aw/2,a["y"]+ah; x2,y2=b["x"]+bw/2,b["y"]; mid=(y1+y2)/2
                parts.append(f'<polyline points="{x1},{y1} {x1},{mid} {x2},{mid} {x2},{y2}" fill="none" stroke="#111" stroke-width="2"/>')
        for n in self.nodes.values():
            x,y,w0,h0=n["x"],n["y"],n.get("w",BOX_W),n.get("h",BOX_H)
            c=TYPE_COLORS.get(norm_type(n.get("type")),TYPE_COLORS["Unknown"])
            label=str(n.get("label",n["id"])).replace("&","&amp;").replace("<","&lt;")
            parts.append(f'<rect x="{x}" y="{y}" width="{w0}" height="{h0}" fill="{c}" stroke="#222" stroke-width="1.5"/>')
            parts.append(f'<text x="{x+w0/2}" y="{y+h0/2+4}" text-anchor="middle" font-family="Segoe UI, Arial" font-size="12" font-weight="bold">{label}</text>')
        parts.append("</svg>")
        return "\n".join(parts)

    def export_pdf(self):
        p=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF","*.pdf")])
        if not p: return
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A3, landscape
            from reportlab.lib.colors import HexColor, black
            c=canvas.Canvas(p,pagesize=landscape(A3)); pw,ph=landscape(A3)
            minx,miny,maxx,maxy=self.bounds()
            scale=min((pw-60)/(maxx-minx),(ph-60)/(maxy-miny))
            def tx(x): return 30+(x-minx)*scale
            def ty(y): return ph-(30+(y-miny)*scale)
            for e in self.edges:
                if e["source"] in self.nodes and e["target"] in self.nodes:
                    a,b=self.nodes[e["source"]],self.nodes[e["target"]]
                    aw,ah=a.get("w",BOX_W),a.get("h",BOX_H); bw,bh=b.get("w",BOX_W),b.get("h",BOX_H)
                    x1,y1=a["x"]+aw/2,a["y"]+ah; x2,y2=b["x"]+bw/2,b["y"]; mid=(y1+y2)/2
                    for (xa,ya),(xb,yb) in zip([(x1,y1),(x1,mid),(x2,mid)],[(x1,mid),(x2,mid),(x2,y2)]):
                        c.line(tx(xa),ty(ya),tx(xb),ty(yb))
            for g in self.groups:
                c.setDash(5,4); c.setStrokeColor(HexColor("#6F8FB5"))
                c.rect(tx(g["x"]),ty(g["y"]+g["h"]),g["w"]*scale,g["h"]*scale,fill=0,stroke=1)
                c.setDash(); c.setFillColor(HexColor("#6F8FB5")); c.setFont("Helvetica-Bold",8)
                c.drawString(tx(g["x"]+8),ty(g["y"]+18),g.get("name",""))
            c.setDash(); c.setStrokeColor(black)
            for n in self.nodes.values():
                x,y,w0,h0=n["x"],n["y"],n.get("w",BOX_W),n.get("h",BOX_H)
                c.setFillColor(HexColor(TYPE_COLORS.get(norm_type(n.get("type")),TYPE_COLORS["Unknown"])))
                c.rect(tx(x),ty(y+h0),w0*scale,h0*scale,fill=1,stroke=1)
                label=str(n.get("label",n["id"]))
                fs=max(5,min(9,(w0*scale)/(max(1,len(label))*0.52)))
                c.setFillColor(black); c.setFont("Helvetica-Bold",fs)
                c.drawCentredString(tx(x+w0/2),ty(y+h0/2)-fs/3,label[:22])
            c.save(); messagebox.showinfo("PDF",p)
        except Exception as e:
            messagebox.showerror("PDF fejl",str(e))

    def export_png(self):
        p=filedialog.asksaveasfilename(defaultextension=".png",filetypes=[("PNG","*.png")])
        if not p: return
        try:
            import cairosvg
            cairosvg.svg2png(bytestring=self.to_svg().encode("utf-8"),write_to=p,output_width=2400)
            messagebox.showinfo("PNG",p)
        except Exception as e:
            messagebox.showerror("PNG fejl",f"PNG eksport kræver cairosvg.\n{e}")

    def export_graph(self):
        p=filedialog.asksaveasfilename(defaultextension=".dot",filetypes=[("Graphviz DOT","*.dot"),("Graph JSON","*.json")])
        if not p: return
        if p.lower().endswith(".json"):
            json.dump({"nodes":list(self.nodes.values()),"edges":self.edges,"groups":self.groups},open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        else:
            lines=["digraph HarrisMatrix {","  rankdir=TB;","  node [shape=box, style=filled, fontname=\"Arial\"];"]
            for nid,n in self.nodes.items():
                lines.append(f'  "{nid}" [label="{n.get("label",nid)}"];')
            for e in self.edges:
                lines.append(f'  "{e["source"]}" -> "{e["target"]}";')
            lines.append("}")
            Path(p).write_text("\n".join(lines),encoding="utf-8")
        messagebox.showinfo("Graph",p)

    def open_json(self):
        p=filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if p:
            d=json.load(open(p,encoding="utf-8"))
            self.nodes={n["id"]:n for n in d.get("nodes",[])}
            self.edges=d.get("edges",[])
            self.groups=d.get("groups",[])
            self.draw(); self.fit()

    def save_json(self):
        p=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON","*.json")])
        if p:
            json.dump({"nodes":list(self.nodes.values()),"edges":self.edges,"groups":self.groups},open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=2)

    def save_hmcx(self):
        p=filedialog.asksaveasfilename(defaultextension=".hmcx",filetypes=[("HMCX","*.hmcx")])
        if not p: return
        write_hmcx(p, self.nodes, self.edges)
        messagebox.showinfo("HMCX", p)

def write_hmcx(path, nodes, edges):
    graphml = ET.Element("graphml", {"xmlns":"http://graphml.graphdrawing.org/xmlns/graphml"})
    graph = ET.SubElement(graphml, "graph", {"id":"G", "edgedefault":"directed"})
    for nid,n in nodes.items():
        node=ET.SubElement(graph,"node",{"id":nid})
        data=ET.SubElement(node,"data",{"key":"d0"})
        ET.SubElement(data,"hmcnode",{
            "id":nid,
            "name":str(n.get("label",nid)),
            "description":"",
            "type":hmc_type(n.get("type")),
            "valid":"true",
            "x":str(n.get("x",0)),
            "y":str(n.get("y",0)),
            "layer":"0",
            "index":"0",
            "bookmarked":"false"
        })
    for i,e in enumerate(edges):
        edge=ET.SubElement(graph,"edge",{"id":f"e{i}","source":e["source"],"target":e["target"]})
        data=ET.SubElement(edge,"data",{"key":"d1"})
        ET.SubElement(data,"hmcedge",{"type":"ABOVE","valid":"true"})
    xml=ET.tostring(graphml,encoding="utf-8",xml_declaration=True)
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.xml",'<?xml version="1.0" ?><ProjectProperties Name="Harris Matrix Editor V9" Description="" ExcavationSite=""></ProjectProperties>')
        z.writestr("matrix.xml",xml)

def hmc_type(t):
    t=norm_type(t)
    if t=="Surface": return "SURFACE"
    if t=="Natural": return "GEOLOGY"
    if t=="Unexcavated": return "UNEXCAVATED"
    if t=="Cut": return "SURFACE"
    return "DEPOSIT"

if __name__ == "__main__":
    App().mainloop()
