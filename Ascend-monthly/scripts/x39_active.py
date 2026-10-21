# -*- coding: utf-8 -*-
# x39: 拉 9社区×8/9月×D1/D2 operation=active 全明细 → active_detail.json
import urllib.request, json, time, datetime, os
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
T='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJ1c2VyX3RhbnRpYW4iLCJzdWIiOiI2OWU2MzliNzFkODhkNDRiMDk4ZDI5ZTkiLCJpYXQiOjE3OTE3OTYwNTksImV4cCI6MTc5MzAwNTY1OSwianRpIjoidmJ5aTVpamk4N2hod3Zxb3hyY2hyZ2hyeTY5M2U0dHRzYWkifQ.PJBYm2z1zyjxbRFWXbU2Gb2VcxHtqpbeYLInIHSX4gU'
H={"Content-Type":"application/json","Accept":"application/json","Origin":"https://datastat.osinfra.cn","Referer":"https://datastat.osinfra.cn/developers","token":T}
def ms(y,m,d): return int(datetime.datetime(y,m,d).timestamp()*1000)
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
def call(body,maxtry=7):
    for k in range(maxtry):
        try:
            r=urllib.request.Request("https://datastat.osinfra.cn/server/user/level/detail",data=json.dumps(body).encode(),headers=H,method="POST")
            with urllib.request.urlopen(r,timeout=120) as x: j=json.loads(x.read().decode())
            if j.get("code")==1: return j
        except Exception: pass
        time.sleep(4+3*k)
    return None
F=B+"active_detail.json"
R=json.load(open(F)) if os.path.exists(F) else {}
for c in COMMS:
    R.setdefault(c,{})
    for tag,(s,e) in [("8",(ms(2026,8,1),ms(2026,9,1))),("9",(ms(2026,9,1),ms(2026,10,1)))]:
        for lv in ("D1","D2"):
            k=f"{tag}-{lv}"
            if R[c].get(k): continue
            rows=[]; p=1
            while True:
                j=call({"community":c,"level":lv,"date":f"2026-0{tag}-01","start":s,"end":e-1,
                        "chartStart":ms(2026,1,1),"operation":"active","interval":"month","pageNum":p,"pageSize":4000})
                if not j: break
                d=j.get("data") or []
                for x in d:
                    rows.append([ (x.get("user_login") or "").strip().lower(), (x.get("contrib_type") or "").strip().lower(), (x.get("html_url") or "") ])
                if len(d)<4000: break
                p+=1; time.sleep(1.5)
            R[c][k]=rows
            json.dump(R,open(F,"w"))
            u=len({r0[0] for r0 in rows})
            print(c,k,"rows",len(rows),"users",u,flush=True)
            time.sleep(2.4)
print("ALL DONE",flush=True)
