# -*- coding: utf-8 -*-
# x23: 补数据 —— 各社区 6/7/9月 D0/D1/D2 单月名册 + 社区贡献者公司映射
import urllib.request, json, time, datetime, os
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
T='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJ1c2VyX3RhbnRpYW4iLCJzdWIiOiI2OWU2MzliNzFkODhkNDRiMDk4ZDI5ZTkiLCJpYXQiOjE3OTE3OTYwNTksImV4cCI6MTc5MzAwNTY1OSwianRpIjoidmJ5aTVpamk4N2hod3Zxb3hyY2hyZ2hyeTY5M2U0dHRzYWkifQ.PJBYm2z1zyjxbRFWXbU2Gb2VcxHtqpbeYLInIHSX4gU'
H={"Content-Type":"application/json","Accept":"application/json","Origin":"https://datastat.osinfra.cn","token":T}
def ms(y,m,d): return int(datetime.datetime(y,m,d).timestamp()*1000)
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]

def call(path,body,maxtry=6):
    for k in range(maxtry):
        try:
            r=urllib.request.Request("https://datastat.osinfra.cn"+path,data=json.dumps(body).encode(),headers=H,method="POST")
            with urllib.request.urlopen(r,timeout=100) as x: j=json.loads(x.read().decode())
            if j.get("code")==1: return j
        except Exception as e:
            pass
        time.sleep(4+3*k)
    return None

def roster(comm,lv,y,m):
    users=set(); p=1
    st=ms(y,m,1); en=(ms(y,m+1,1) if m<12 else ms(y+1,1,1))-1
    while True:
        j=call("/server/user/level/detail",{"community":comm,"level":lv,"date":f"{y}-{m:02d}-01","start":st,"end":en,
              "chartStart":ms(2026,1,1),"operation":"increase","pageNum":p,"pageSize":250})
        if not j: break
        d=j.get("data") or []
        for x in d:
            u=(x.get("user_login") or "").strip()
            if u: users.add(u.lower())
        if len(d)<250: break
        p+=1; time.sleep(1.5)
    return users

# 1) 月名册
MR_FILE=B+"month_rosters.json"
MR=json.load(open(MR_FILE)) if os.path.exists(MR_FILE) else {}
tasks=[]
for c in COMMS:
    for m in (6,7,9):
        for lv in (("D0","D1","D2") if m in (6,7) else ("D1","D2")):
            if MR.get(c,{}).get(f"{m}-{lv}") is not None: continue
            tasks.append((c,m,lv))
print("roster tasks:",len(tasks),flush=True)
for c,m,lv in tasks:
    u=roster(c,lv,2026,m)
    MR.setdefault(c,{})[f"{m}-{lv}"]=sorted(u)
    json.dump(MR,open(MR_FILE,"w"),ensure_ascii=False)
    print(c,m,lv,len(u),flush=True)
    time.sleep(2.4)

# 2) 公司映射 + 1-7月历史活跃标记
CM_FILE=B+"compmap.json"
HJ_FILE=B+"hist_janjul.json"
CM=json.load(open(CM_FILE)) if os.path.exists(CM_FILE) else {}
HJ=json.load(open(HJ_FILE)) if os.path.exists(HJ_FILE) else {}
for c in COMMS:
    if CM.get(c) and HJ.get(c): continue
    m={}
    hj=set()
    for p in range(1,60):
        j=call("/server/query/contributes/page",{"community":c,"start":ms(2025,10,1),"end":ms(2026,10,1),"metric":"user","pageNum":p,"pageSize":500})
        if not j: break
        for u in j["data"]["list"]:
            m[u["user_login"].lower()]=u.get("company") or "个人贡献者"
        if p>=j["data"]["total_page"]: break
        time.sleep(1.2)
    if not CM.get(c): CM[c]=m
    # 1-7月窗口: 指标>0 即历史有贡献
    for p in range(1,60):
        j=call("/server/query/contributes/page",{"community":c,"start":ms(2026,1,1),"end":ms(2026,8,1)-1,
              "metric":"user","pageNum":p,"pageSize":500})
        if not j: break
        for u in j["data"]["list"]:
            if (u.get("pr_total",0)+u.get("issue_total",0)+u.get("comment_total",0)+u.get("addcode_total",0))>0:
                hj.add(u["user_login"].lower())
        if p>=j["data"]["total_page"]: break
        time.sleep(1.2)
    HJ[c]=sorted(hj)
    json.dump(CM,open(CM_FILE,"w"),ensure_ascii=False)
    json.dump(HJ,open(HJ_FILE,"w"),ensure_ascii=False)
    print("compmap",c,len(m),"| hist_janjul",len(hj),flush=True)
    time.sleep(2.4)
print("ALL DONE",flush=True)
