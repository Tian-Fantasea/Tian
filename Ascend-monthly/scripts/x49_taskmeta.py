# -*- coding: utf-8 -*-
# x49: 每社区D1流失者中 纯comment人数/任务型人数/高频词Top3 → task_meta.json
import json, re
from collections import Counter
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
X=json.load(open(B+"x40_data.json")); AD=json.load(open(B+"active_detail.json"))
TASK_PAT=re.compile(r"(任务(完成|已完|认领|领取|怎么领|认领了|申请)|认领(该|此|这个)?任务|已认领|claim(ed|ing)? (this |the )?(task|issue)|淬火|quenching|cann-outreach|社区任务|测试报告|测试(如下|完成)|结果如下|报告如下|task.*?(完成|done)|good[- ]first[- ]issue|标签(已|处理)|/label add|我认领|接下(来|受)|负责(该|此)?(模块|任务)|已完成.{0,6}(调研|方案|补充|测试))", re.I)
LEX={"任务":r"任务","认领":r"认领|claim","完成":r"完成|done|已完成","链接":r"http","测试报告":r"测试报告|报告如下|结果如下","模型":r"[Qq]wen|[Dd]eep[Ss]eep|[Ll]lama|[Cc]osmos|omni","报错":r"报错|error|失败|fail|异常"}
M={}
for c in COMMS:
    lost=set(X[c]['D1']['lost']); evt={}
    for u,ty,url in AD[c]['8-D1']: evt.setdefault(u,set()).add(ty)
    pure=[u for u in lost if evt.get(u)=={'comment'}]
    try: C=json.load(open(B+f'cmt_{c}.json'))
    except Exception: C={}
    tn=[u for u in pure if any(TASK_PAT.search(cc["body"]) for cc in C.get(u,[]))]
    df=Counter()
    for u in tn:
        t=" ".join(cc["body"] for cc in C.get(u,[]))
        for w,p in LEX.items():
            if re.search(p,t,re.I): df[w]+=1
    top=[w for w,_ in df.most_common(2)]
    M[c]={"pure_n":len(pure),"task_n":len(tn),"pct":round(len(tn)/len(pure)*100) if pure else 0,"words":top}
    print(c,M[c])
json.dump(M,open(B+"task_meta.json","w"),ensure_ascii=False)
print("saved task_meta.json")
