# -*- coding: utf-8 -*-
"""机票优惠雷达 v0.1  —— 抢券提醒 + 券包管理 + 券后价计算
纯 Python 标准库(tkinter)，无第三方依赖。数据保存在 %APPDATA%/CouponRadar/data.json
"""
import json, os, sys, uuid, webbrowser, calendar
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta, date

APP = "机票优惠雷达 v0.1"
PLATFORMS = ["美团", "携程", "飞猪", "同程", "去哪儿", "航司官方", "其他"]
KINDS = {"daily": "每天", "monthly": "每月", "once": "单次"}
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CouponRadar")
DATA_FILE = os.path.join(DATA_DIR, "data.json")

# ---------- 预置线索（来自公开文章，未经验证，需要你在App里实测） ----------
def _ev(name, plat, kind, time_, day=None, code="", note=""):
    return {"id": uuid.uuid4().hex, "name": name, "platform": plat, "kind": kind,
            "time": time_, "day": day, "date": "", "code": code, "url": "",
            "note": note, "enabled": True, "verified": False}

def default_data():
    ev = [
        _ev("美团 机票通用券", "美团", "daily", "10:00", code="机票100", note="美团App首页搜索口令"),
        _ev("美团 出行100 每日大额券", "美团", "daily", "10:00", code="出行100", note="限量，开抢时间待实测"),
        _ev("美团 燃油补贴", "美团", "daily", "10:00", code="燃油补贴100"),
        _ev("美团 长途满减券", "美团", "daily", "10:00", code="机票888"),
        _ev("同程 通用券", "同程", "daily", "10:00", code="福利100", note="微信小程序搜索口令"),
    ]
    for d, n in [(8, "海航系"), (9, "厦航"), (12, "深航"), (18, "东航"),
                 (19, "川航"), (25, "吉祥"), (27, "春秋"), (28, "南航")]:
        ev.append(_ev(f"{n} 会员日", "航司官方", "monthly", "00:00", day=d,
                      note="航司App/小程序会员日特价，开放时间待实测"))
    return {"events": ev, "coupons": [], "settings": {"lead_seconds": 120}}

def load():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("events", []); d.setdefault("coupons", [])
        d.setdefault("settings", {"lead_seconds": 120})
        return d
    except Exception:
        return default_data()

def save(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

# ---------- 时间计算 ----------
def parse_hm(s):
    h, m = s.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60): raise ValueError
    return h, m

def next_occurrence(e, now):
    h, m = parse_hm(e["time"])
    if e["kind"] == "daily":
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return t if t > now - timedelta(seconds=5) else t + timedelta(days=1)
    if e["kind"] == "monthly":
        y, mo = now.year, now.month
        for _ in range(3):
            day = min(int(e["day"]), calendar.monthrange(y, mo)[1])
            t = datetime(y, mo, day, h, m)
            if t > now - timedelta(seconds=5): return t
            mo += 1
            if mo > 12: y, mo = y + 1, 1
        return None
    try:
        t = datetime.strptime(e["date"], "%Y-%m-%d").replace(hour=h, minute=m)
    except Exception:
        return None
    return t if t > now - timedelta(seconds=5) else None

def fmt_left(sec):
    sec = int(sec)
    if sec <= 0: return "进行中"
    d, r = divmod(sec, 86400); h, r = divmod(r, 3600); m, s = divmod(r, 60)
    return f"{d}天{h:02d}:{m:02d}:{s:02d}" if d else f"{h:02d}:{m:02d}:{s:02d}"

# ---------- 券后价计算 ----------
def coupon_valid(c, today=None):
    today = today or date.today()
    if c.get("used"): return False
    if c.get("expiry"):
        try:
            if datetime.strptime(c["expiry"], "%Y-%m-%d").date() < today: return False
        except Exception: pass
    return True

def best_coupon(coupons, platform, price):
    best = None
    for c in coupons:
        if c["platform"] != platform or not coupon_valid(c): continue
        if price >= float(c.get("threshold") or 0):
            if best is None or float(c["discount"]) > float(best["discount"]):
                best = c
    return best

# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP); self.geometry("980x620"); self.minsize(820, 520)
        self.data = load(); save(self.data)
        self.fired = set()
        st = ttk.Style(self)
        try: st.theme_use("vista" if sys.platform == "win32" else "clam")
        except Exception: pass
        st.configure("Treeview", rowheight=28, font=("Microsoft YaHei UI", 10))
        st.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        st.configure("TNotebook.Tab", padding=(16, 6), font=("Microsoft YaHei UI", 10))
        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.build_events(); self.build_coupons(); self.build_calc()
        self.status = ttk.Label(self, anchor="w", foreground="#666")
        self.status.pack(fill="x", padx=12, pady=(0, 8))
        self.refresh_events(); self.refresh_coupons()
        self.tick()

    # ===== 抢券日程 =====
    def build_events(self):
        f = ttk.Frame(self.nb, padding=8); self.nb.add(f, text="⏰ 抢券日程")
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        for t, cmd in [("新增", self.add_event), ("编辑", self.edit_event), ("删除", self.del_event),
                       ("启用/暂停", self.toggle_event), ("标记已验证", self.verify_event),
                       ("复制口令", self.copy_code), ("打开链接", self.open_url)]:
            ttk.Button(bar, text=t, command=cmd).pack(side="left", padx=2)
        ttk.Label(bar, text="  提前提醒(秒)").pack(side="left")
        self.lead = tk.StringVar(value=str(self.data["settings"].get("lead_seconds", 120)))
        sp = ttk.Spinbox(bar, from_=10, to=3600, width=6, textvariable=self.lead, command=self.save_lead)
        sp.pack(side="left"); sp.bind("<FocusOut>", lambda e: self.save_lead())
        cols = ("state", "name", "platform", "rule", "code", "next", "left", "note")
        heads = ("状态", "活动", "平台", "规则", "口令", "下次开抢", "倒计时", "备注")
        widths = (60, 200, 70, 110, 100, 130, 100, 240)
        self.ev_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.ev_tree.heading(c, text=h); self.ev_tree.column(c, width=w, anchor="w")
        self.ev_tree.tag_configure("soon", background="#fff3e0")
        self.ev_tree.tag_configure("off", foreground="#aaa")
        self.ev_tree.pack(fill="both", expand=True)
        self.ev_tree.bind("<Double-1>", lambda e: self.edit_event())

    def save_lead(self):
        try: v = max(10, min(3600, int(self.lead.get())))
        except ValueError: v = 120
        self.lead.set(str(v)); self.data["settings"]["lead_seconds"] = v; save(self.data)

    def sel_event(self):
        s = self.ev_tree.selection()
        if not s: messagebox.showinfo(APP, "先选中一个活动"); return None
        return next((e for e in self.data["events"] if e["id"] == s[0]), None)

    def refresh_events(self):
        now = datetime.now(); lead = self.data["settings"].get("lead_seconds", 120)
        sel = self.ev_tree.selection()
        rows = []
        for e in self.data["events"]:
            try: nxt = next_occurrence(e, now)
            except Exception: nxt = None
            rows.append((nxt or datetime.max, e, nxt))
        rows.sort(key=lambda r: (not r[1]["enabled"], r[0]))
        self.ev_tree.delete(*self.ev_tree.get_children())
        for _, e, nxt in rows:
            rule = KINDS[e["kind"]] + (f" {e['day']}日" if e["kind"] == "monthly" else
                                       f" {e['date']}" if e["kind"] == "once" else "") + f" {e['time']}"
            left = (nxt - now).total_seconds() if nxt else None
            state = ("暂停" if not e["enabled"] else "✅" if e["verified"] else "待验证")
            tag = "off" if not e["enabled"] else ("soon" if left is not None and left <= 3600 else "")
            self.ev_tree.insert("", "end", iid=e["id"], tags=(tag,), values=(
                state, e["name"], e["platform"], rule, e["code"],
                nxt.strftime("%m-%d %H:%M") if nxt else "已过期",
                fmt_left(left) if left is not None else "-", e["note"]))
        if sel and self.ev_tree.exists(sel[0]): self.ev_tree.selection_set(sel[0])

    def event_dialog(self, e=None):
        d = tk.Toplevel(self); d.title("活动"); d.transient(self); d.grab_set(); d.resizable(False, False)
        e = e or {"name": "", "platform": "美团", "kind": "daily", "time": "10:00", "day": 1,
                  "date": date.today().isoformat(), "code": "", "url": "", "note": ""}
        v = {k: tk.StringVar(value=str(e.get(k) or "")) for k in
             ("name", "platform", "time", "day", "date", "code", "url", "note")}
        kind = tk.StringVar(value=KINDS[e["kind"]])
        fields = [("活动名称", ttk.Entry(d, textvariable=v["name"], width=36)),
                  ("平台", ttk.Combobox(d, textvariable=v["platform"], values=PLATFORMS, state="readonly")),
                  ("重复", ttk.Combobox(d, textvariable=kind, values=list(KINDS.values()), state="readonly")),
                  ("时间 HH:MM", ttk.Entry(d, textvariable=v["time"])),
                  ("每月几号(每月)", ttk.Entry(d, textvariable=v["day"])),
                  ("日期(单次) YYYY-MM-DD", ttk.Entry(d, textvariable=v["date"])),
                  ("口令", ttk.Entry(d, textvariable=v["code"], width=36)),
                  ("链接(可选)", ttk.Entry(d, textvariable=v["url"], width=36)),
                  ("备注", ttk.Entry(d, textvariable=v["note"], width=36))]
        for i, (lab, w) in enumerate(fields):
            ttk.Label(d, text=lab).grid(row=i, column=0, sticky="e", padx=8, pady=4)
            w.grid(row=i, column=1, sticky="we", padx=8, pady=4)
        out = {}
        def ok():
            k = {vv: kk for kk, vv in KINDS.items()}[kind.get()]
            try:
                parse_hm(v["time"].get())
                day = int(v["day"].get() or 1)
                if k == "monthly" and not 1 <= day <= 31: raise ValueError
                if k == "once": datetime.strptime(v["date"].get(), "%Y-%m-%d")
            except Exception:
                messagebox.showerror(APP, "时间/日期格式不对", parent=d); return
            if not v["name"].get().strip():
                messagebox.showerror(APP, "请填写活动名称", parent=d); return
            out.update({kk: v[kk].get().strip() for kk in ("name", "platform", "time", "date", "code", "url", "note")})
            out.update(kind=k, day=day); d.destroy()
        b = ttk.Frame(d); b.grid(row=len(fields), column=0, columnspan=2, pady=8)
        ttk.Button(b, text="保存", command=ok).pack(side="left", padx=6)
        ttk.Button(b, text="取消", command=d.destroy).pack(side="left", padx=6)
        self.wait_window(d); return out or None

    def add_event(self):
        r = self.event_dialog()
        if r:
            r.update(id=uuid.uuid4().hex, enabled=True, verified=False)
            self.data["events"].append(r); save(self.data); self.refresh_events()
    def edit_event(self):
        e = self.sel_event()
        if e and (r := self.event_dialog(dict(e))):
            e.update(r); save(self.data); self.refresh_events()
    def del_event(self):
        e = self.sel_event()
        if e and messagebox.askyesno(APP, f"删除「{e['name']}」？"):
            self.data["events"].remove(e); save(self.data); self.refresh_events()
    def toggle_event(self):
        e = self.sel_event()
        if e: e["enabled"] = not e["enabled"]; save(self.data); self.refresh_events()
    def verify_event(self):
        e = self.sel_event()
        if e: e["verified"] = not e["verified"]; save(self.data); self.refresh_events()
    def copy_code(self, e=None):
        e = e or self.sel_event()
        if e and e["code"]:
            self.clipboard_clear(); self.clipboard_append(e["code"]); self.update()
            self.status.config(text=f"已复制口令：{e['code']}")
    def open_url(self, e=None):
        e = e or self.sel_event()
        if e and e["url"]: webbrowser.open(e["url"])
        elif e: self.status.config(text="该活动没有链接（手机App活动请用口令）")

    # ===== 提醒 =====
    def tick(self):
        now = datetime.now(); lead = self.data["settings"].get("lead_seconds", 120)
        for e in self.data["events"]:
            if not e["enabled"]: continue
            try: nxt = next_occurrence(e, now)
            except Exception: continue
            if not nxt: continue
            left = (nxt - now).total_seconds(); key = f"{e['id']}|{nxt.isoformat()}"
            if 0 < left <= lead and key + "|pre" not in self.fired:
                self.fired.add(key + "|pre")
                self.popup(f"⏰ {int(left)} 秒后开抢", e, pre=True)
            if -5 <= left <= 0 and key + "|go" not in self.fired:
                self.fired.add(key + "|go"); self.fired.add(key + "|pre")
                self.copy_code(e); self.open_url(e) if e["url"] else None
                self.popup("🔥 现在开抢！", e, pre=False)
        self.refresh_events() if self.nb.index("current") == 0 else None
        self.check_expiry_status()
        self.after(1000, self.tick)

    def popup(self, title, e, pre):
        try:
            import winsound; winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception: self.bell()
        w = tk.Toplevel(self); w.title(title); w.attributes("-topmost", True); w.resizable(False, False)
        fr = ttk.Frame(w, padding=16); fr.pack()
        ttk.Label(fr, text=title, font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        ttk.Label(fr, text=f"{e['platform']} · {e['name']}", font=("Microsoft YaHei UI", 11)).pack(anchor="w", pady=4)
        if e["code"]:
            ttk.Label(fr, text=f"口令：{e['code']}" + ("（已复制到剪贴板）" if not pre else ""),
                      foreground="#d84315", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
            ttk.Label(fr, text=f"打开手机「{e['platform']}」App → 首页搜索口令 → 领取").pack(anchor="w", pady=4)
        if e["note"]: ttk.Label(fr, text=e["note"], foreground="#666").pack(anchor="w")
        b = ttk.Frame(fr); b.pack(pady=(10, 0))
        if e["code"]: ttk.Button(b, text="复制口令", command=lambda: self.copy_code(e)).pack(side="left", padx=4)
        if e["url"]: ttk.Button(b, text="打开链接", command=lambda: self.open_url(e)).pack(side="left", padx=4)
        ttk.Button(b, text="知道了", command=w.destroy).pack(side="left", padx=4)

    # ===== 券包 =====
    def build_coupons(self):
        f = ttk.Frame(self.nb, padding=8); self.nb.add(f, text="🎟 我的券包")
        bar = ttk.Frame(f); bar.pack(fill="x", pady=(0, 6))
        for t, cmd in [("新增券", self.add_coupon), ("编辑", self.edit_coupon),
                       ("标记已用/未用", self.use_coupon), ("删除", self.del_coupon)]:
            ttk.Button(bar, text=t, command=cmd).pack(side="left", padx=2)
        self.show_dead = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="显示已用/过期", variable=self.show_dead,
                        command=self.refresh_coupons).pack(side="left", padx=10)
        cols = ("platform", "title", "rule", "expiry", "left", "state", "note")
        heads = ("平台", "券名", "规则", "到期日", "剩余", "状态", "备注")
        widths = (70, 220, 120, 100, 70, 70, 260)
        self.cp_tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.cp_tree.heading(c, text=h); self.cp_tree.column(c, width=w, anchor="w")
        self.cp_tree.tag_configure("urgent", background="#ffebee")
        self.cp_tree.tag_configure("dead", foreground="#aaa")
        self.cp_tree.pack(fill="both", expand=True)
        self.cp_tree.bind("<Double-1>", lambda e: self.edit_coupon())

    def refresh_coupons(self):
        today = date.today(); self.cp_tree.delete(*self.cp_tree.get_children())
        def key(c):
            try: return datetime.strptime(c["expiry"], "%Y-%m-%d").date()
            except Exception: return date.max
        for c in sorted(self.data["coupons"], key=key):
            valid = coupon_valid(c, today)
            if not valid and not self.show_dead.get(): continue
            exp = key(c); days = (exp - today).days if exp != date.max else None
            th = float(c.get("threshold") or 0); dc = float(c["discount"])
            rule = f"满{th:g}减{dc:g}" if th else f"无门槛减{dc:g}"
            state = "已用" if c.get("used") else ("过期" if not valid else "可用")
            tag = "dead" if not valid else ("urgent" if days is not None and days <= 3 else "")
            self.cp_tree.insert("", "end", iid=c["id"], tags=(tag,), values=(
                c["platform"], c["title"], rule, c.get("expiry") or "长期",
                f"{days}天" if days is not None and valid else "-", state, c.get("note", "")))
        if hasattr(self, "calc_vars"): self.calc()

    def check_expiry_status(self):
        today = date.today(); n = 0
        for c in self.data["coupons"]:
            if coupon_valid(c, today) and c.get("expiry"):
                try:
                    if (datetime.strptime(c["expiry"], "%Y-%m-%d").date() - today).days <= 3: n += 1
                except Exception: pass
        if not self.status.cget("text").startswith("已复制"):
            self.status.config(text=f"数据：{DATA_FILE}    ·    {n} 张券 3 天内到期" if n else f"数据：{DATA_FILE}")

    def sel_coupon(self):
        s = self.cp_tree.selection()
        if not s: messagebox.showinfo(APP, "先选中一张券"); return None
        return next((c for c in self.data["coupons"] if c["id"] == s[0]), None)

    def coupon_dialog(self, c=None):
        d = tk.Toplevel(self); d.title("优惠券"); d.transient(self); d.grab_set(); d.resizable(False, False)
        c = c or {"platform": "美团", "title": "", "discount": "", "threshold": "0", "expiry": "", "note": ""}
        v = {k: tk.StringVar(value=str(c.get(k, ""))) for k in ("platform", "title", "discount", "threshold", "expiry", "note")}
        fields = [("平台", ttk.Combobox(d, textvariable=v["platform"], values=PLATFORMS, state="readonly")),
                  ("券名", ttk.Entry(d, textvariable=v["title"], width=34)),
                  ("减多少(元)", ttk.Entry(d, textvariable=v["discount"])),
                  ("满多少可用(0=无门槛)", ttk.Entry(d, textvariable=v["threshold"])),
                  ("到期日 YYYY-MM-DD(空=长期)", ttk.Entry(d, textvariable=v["expiry"])),
                  ("备注(适用航线/舱位等)", ttk.Entry(d, textvariable=v["note"], width=34))]
        for i, (lab, w) in enumerate(fields):
            ttk.Label(d, text=lab).grid(row=i, column=0, sticky="e", padx=8, pady=4)
            w.grid(row=i, column=1, sticky="we", padx=8, pady=4)
        out = {}
        def ok():
            try:
                dc = float(v["discount"].get()); th = float(v["threshold"].get() or 0)
                if dc <= 0 or th < 0: raise ValueError
                if v["expiry"].get().strip(): datetime.strptime(v["expiry"].get().strip(), "%Y-%m-%d")
            except Exception:
                messagebox.showerror(APP, "金额或日期格式不对", parent=d); return
            out.update(platform=v["platform"].get(), title=v["title"].get().strip() or f"{v['platform'].get()}券",
                       discount=dc, threshold=th, expiry=v["expiry"].get().strip(), note=v["note"].get().strip())
            d.destroy()
        b = ttk.Frame(d); b.grid(row=len(fields), column=0, columnspan=2, pady=8)
        ttk.Button(b, text="保存", command=ok).pack(side="left", padx=6)
        ttk.Button(b, text="取消", command=d.destroy).pack(side="left", padx=6)
        self.wait_window(d); return out or None

    def add_coupon(self):
        r = self.coupon_dialog()
        if r:
            r.update(id=uuid.uuid4().hex, used=False)
            self.data["coupons"].append(r); save(self.data); self.refresh_coupons()
    def edit_coupon(self):
        c = self.sel_coupon()
        if c and (r := self.coupon_dialog(dict(c))):
            c.update(r); save(self.data); self.refresh_coupons()
    def use_coupon(self):
        c = self.sel_coupon()
        if c: c["used"] = not c.get("used"); save(self.data); self.refresh_coupons()
    def del_coupon(self):
        c = self.sel_coupon()
        if c and messagebox.askyesno(APP, f"删除「{c['title']}」？"):
            self.data["coupons"].remove(c); save(self.data); self.refresh_coupons()

    # ===== 券后价 =====
    def build_calc(self):
        f = ttk.Frame(self.nb, padding=12); self.nb.add(f, text="💰 券后价")
        ttk.Label(f, text="同一航班，填各平台下单页的含税价（不含保险等附加项），自动套用券包里最优的一张可用券：",
                  foreground="#555").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        self.calc_vars = {}
        for i, p in enumerate(PLATFORMS[:-1]):
            ttk.Label(f, text=p, width=8).grid(row=i + 1, column=0, sticky="w", pady=3)
            v = tk.StringVar(); v.trace_add("write", lambda *a: self.calc())
            ttk.Entry(f, textvariable=v, width=12).grid(row=i + 1, column=1, sticky="w")
            self.calc_vars[p] = v
        self.calc_out = tk.Text(f, width=60, height=12, font=("Microsoft YaHei UI", 11),
                                relief="flat", background="#fafafa")
        self.calc_out.grid(row=1, column=2, rowspan=8, sticky="nsew", padx=(20, 0))
        f.columnconfigure(2, weight=1)

    def calc(self):
        res = []
        for p, v in self.calc_vars.items():
            try: price = float(v.get())
            except ValueError: continue
            if price <= 0: continue
            c = best_coupon(self.data["coupons"], p, price)
            pay = max(0.0, price - (float(c["discount"]) if c else 0))
            res.append((pay, p, price, c))
        res.sort(key=lambda r: r[0])
        self.calc_out.config(state="normal"); self.calc_out.delete("1.0", "end")
        if not res: self.calc_out.insert("end", "在左边输入价格…")
        for i, (pay, p, price, c) in enumerate(res):
            mark = "🏆 " if i == 0 else "    "
            cp = f"用「{c['title']}」-{float(c['discount']):g}" if c else "无可用券"
            self.calc_out.insert("end", f"{mark}{p}：实付 ¥{pay:g}   (原价 ¥{price:g}，{cp})\n")
        if len(res) > 1:
            self.calc_out.insert("end", f"\n最多可省 ¥{res[-1][0] - res[0][0]:g}（相对最贵的平台）")
        self.calc_out.config(state="disabled")

if __name__ == "__main__":
    App().mainloop()
