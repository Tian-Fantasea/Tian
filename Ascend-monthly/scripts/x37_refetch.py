# -*- coding: utf-8 -*-
# x37: 10/21全量重拉 —— 8/9月 prs(merged)+issues 标题明细(逐人) + 8/9月 D0/D1/D2 名册
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
            with urllib.request.urlopen(r,timeout=90) as x: j=json.loads(x.read().decode())
            if j.get("code")==1: return j
        except Exception: pass
        time.sleep(3+2*k)
    return None

# A) 标题明细
TF=B+"titles_1021.json"
TI=json.load(open(TF)) if os.path.exists(TF) else {}
A=ms(2026,8,1); Bm=ms(2026,9,1); C=ms(2026,10,1)
for c in COMMS:
    TI.setdefault(c,{})
    for tag,(s,e) in [("aug",(A,Bm)),("sep",(Bm,C))]:
        if TI[c].get(tag): continue
        data={"pr":{},"iss":{}}
        for path,key in [("/server/query/prs/detail","pr"),("/server/query/issues/detail","iss")]:
            p=1
            while True:
                body={"community":c,"start":s,"end":e-1,"pageNum":p,"pageSize":100}
                if key=="pr": body["state"]="merged"
                j=call(path,body)
                if not j: break
                for x in j["data"]["list"]:
                    u=(x.get("user_name") or "").strip().lower()
                    if u: data[key].setdefault(u,[]).append((x.get("title") or "")[:120])
                if p>=j["data"]["total_page"]: break
                p+=1; time.sleep(0.8)
        TI[c][tag]=data
        json.dump(TI,open(TF,"w"),ensure_ascii=False)
        n1=sum(len(v) for v in data["pr"].values()); n2=sum(len(v) for v in data["iss"].values())
        print("titles",c,tag,"pr",len(data["pr"]),n1,"iss",len(data["iss"]),n2,flush=True)
        time.sleep(2)

# B) 名册 8/9月 D0/D1/D2
RF=B+"dlevel_re1021.json"
RL=json.load(open(RF)) if os.path.exists(RF) else {}
for c in COMMS:
    RL.setdefault(c,{})
    for tag,(s,e) in [("8",(A,Bm)),("9",(Bm,C))]:
        for lv in ("D0","D1","D2"):
            k=f"{tag}-{lv}"
            if RL[c].get(k) is not None: continue
            users=set(); p=1
            while True:
                j=call("/server/user/level/detail",{"community":c,"level":lv,"date":f"2026-0{tag}-01","start":s,"end":e-1,
                      "chartStart":ms(2026,1,1),"operation":"increase","pageNum":p,"pageSize":250})
                if not j: break
                d=j.get("data") or []
                for x in d:
                    u=(x.get("user_login") or "").strip()
                    if u: users.add(u.lower())
                if len(d)<250: break
                p+=1; time.sleep(1.2)
            RL[c][k]=sorted(users)
            json.dump(RL,open(RF,"w"),ensure_ascii=False)
            print("roster",c,k,len(users),flush=True)
            time.sleep(2.2)
print("ALL DONE",flush=True)
