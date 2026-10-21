# -*- coding: utf-8 -*-
# x44: 9社区 D1纯comment流失者 评论明细批量拉取 (vllm已完成跳过)
import urllib.request, json, time, datetime, os
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
T='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJ1c2VyX3RhbnRpYW4iLCJzdWIiOiI2OWU2MzliNzFkODhkNDRiMDk4ZDI5ZTkiLCJpYXQiOjE3OTE3OTYwNTksImV4cCI6MTc5MzAwNTY1OSwianRpIjoidmJ5aTVpamk4N2hod3Zxb3hyY2hyZ2hyeTY5M2U0dHRzYWkifQ.PJBYm2z1zyjxbRFWXbU2Gb2VcxHtqpbeYLInIHSX4gU'
H={"Content-Type":"application/json","Accept":"application/json","Origin":"https://datastat.osinfra.cn","token":T}
def ms(y,m,d): return int(datetime.datetime(y,m,d).timestamp()*1000)
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
X=json.load(open(B+"x40_data.json")); AD=json.load(open(B+"active_detail.json"))
def pure_list(c):
    lost=set(X[c]['D1']['lost']); evt={}
    for u,ty,url in AD[c]['8-D1']: evt.setdefault(u,set()).add(ty)
    return [u for u in sorted(lost) if evt.get(u)=={'comment'}]
def call(b,maxtry=5):
    for k in range(maxtry):
        try:
            r=urllib.request.Request("https://datastat.osinfra.cn/server/query/comments/detail",data=json.dumps(b).encode(),headers=H,method="POST")
            with urllib.request.urlopen(r,timeout=60) as x: j=json.loads(x.read().decode())
            if j.get("code")==1: return j
        except Exception: pass
        time.sleep(3+2*k)
    return None
s,e=ms(2026,8,1),ms(2026,9,1)-1
for c in COMMS:
    F=B+f"cmt_{c}.json"
    done=json.load(open(F)) if os.path.exists(F) else {}
    lst=pure_list(c)
    todo=[u for u in lst if u not in done]
    print(f'== {c}: pure {len(lst)}, todo {len(todo)}',flush=True)
    for i,u in enumerate(todo):
        items=[]; p=1
        while True:
            j=call({"community":c,"user_login":u,"start":s,"end":e,"pageNum":p,"pageSize":100})
            if not j: break
            for x in (j.get("data") or {}).get("list",[]):
                items.append({"body":(x.get("body") or "")[:500],"url":x.get("html_url",""),"type":x.get("comment_type",""),"invalid":x.get("is_invalid_comment",0)})
            if p>=(j.get("data") or {}).get("total_page",1): break
            p+=1
        done[u]=items
        if i%20==19: json.dump(done,open(F,"w"),ensure_ascii=False); print(f'  {c} {i+1}/{len(todo)}',flush=True)
        time.sleep(0.6 if i%15 else 2.2)
    json.dump(done,open(F,"w"),ensure_ascii=False)
    print(f'  {c} DONE {len(done)} users',flush=True)
print("ALL DONE",flush=True)
