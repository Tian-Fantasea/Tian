# -*- coding: utf-8 -*-
# x32: 从 /server/user/active/user 重拉 9社区 8/9月 D0/D1/D2 活跃(总量+内部) 当前值
import urllib.request, json, time, datetime, os
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
T='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJ1c2VyX3RhbnRpYW4iLCJzdWIiOiI2OWU2MzliNzFkODhkNDRiMDk4ZDI5ZTkiLCJpYXQiOjE3OTE3OTYwNTksImV4cCI6MTc5MzAwNTY1OSwianRpIjoidmJ5aTVpamk4N2hod3Zxb3hyY2hyZ2hyeTY5M2U0dHRzYWkifQ.PJBYm2z1zyjxbRFWXbU2Gb2VcxHtqpbeYLInIHSX4gU'
H={"Content-Type":"application/json","Accept":"application/json","Origin":"https://datastat.osinfra.cn","token":T}
def ms(y,m,d): return int(datetime.datetime(y,m,d).timestamp()*1000)
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
F=B+"active_latest.json"
R=json.load(open(F)) if os.path.exists(F) else {}
def q(comm,lv,st,en,internal=None):
    body={"community":comm,"levelList":[lv],"interval":"month","eventList":[""],"start":st,"end":en-1}
    if internal: body["internalList"]=[internal]
    for k in range(6):
        try:
            req=urllib.request.Request("https://datastat.osinfra.cn/server/user/active/user",data=json.dumps(body).encode(),headers=H,method="POST")
            with urllib.request.urlopen(req,timeout=60) as x: j=json.loads(x.read().decode())
            if j.get("code")==1:
                d=(j.get("data") or [])
                if d: return int(d[0].get("increase",0))
                return 0
        except Exception: pass
        time.sleep(3+2*k)
    return None
A=ms(2026,8,1); Bm=ms(2026,9,1); C=ms(2026,10,1)
for c in COMMS:
    R.setdefault(c,{})
    for mk,(s,e) in [("aug",(A,Bm)),("sep",(Bm,C))]:
        m=R[c].setdefault(mk,{})
        for lv in ("D0","D1","D2"):
            cur=m.get(lv)
            if cur is not None and cur.get("all") is not None and (lv=="D0" or cur.get("in") is not None): continue
            alln=q(c,lv,s,e)
            inn=q(c,lv,s,e,"内部") if lv in ("D1","D2") else None
            m[lv]={"all":alln,"in":inn}
            print(c,mk,lv,"all",alln,"in",inn,flush=True)
            time.sleep(1.4)
        json.dump(R,open(F,"w"),ensure_ascii=False)
print("DONE",flush=True)
