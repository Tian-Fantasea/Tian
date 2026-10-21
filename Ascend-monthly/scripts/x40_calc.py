# -*- coding: utf-8 -*-
# x40: active池人级重算 → x40_data.json (流失/新增/构成/名单，全部点名)
import json, re
from collections import Counter
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
AD=json.load(open(B+"active_detail.json")); TI=json.load(open(B+"titles_1021.json"))
CM=json.load(open(B+"compmap.json")); HJ=json.load(open(B+"hist_janjul.json")); MRO=json.load(open(B+"month_rosters.json"))

CATS=["修复Bug","报告Bug","评论型","社区任务","新特性","文档","性能优化","CI/测试","重构","安装部署","其他"]
BUG_K=["[bug","bugfix","bug-fix","修复","缺陷","报错","崩溃","crash","error","失败","故障","异常","oom","segfault","挂死","hang","乱码","精度","broken","corrupt","wrong","incorrect","fail","死循环","重复输出","garbled","timeout","fix","resolve","hotfix","patch"]
FEAT_K=["[feature","[rfc","[new model","新增","support","添加特性","引入","feature-request","需求反馈","roadmap","请求"]
DOC_K=["[doc","documentation","文档","readme","tutorial"]
PERF_K=["[performance","[perf","性能","optimize","优化","regression","劣化","throughput","ttft","tpot"]
CI_K=["[ci","[test","测试","nightly","daily-ci","test case","e2e","ci门禁"]
RF_K=["[refactor","重构","refactor","retire","sunset"]
IN_K=["[installation","安装","部署","installation"]
TASK_K=["淬火行动","社区任务","任务完成","测试报告","昇腾开源社区任务","向我开炮"]
def _tag(t):
    m=re.match(r'^\[([^\]]+)\]',t); g=m.group(1).lower() if m else ""
    return g.startswith("bug") or "bug-report" in g
def classify_pr(title):
    if not title: return set()
    t=title.lower(); c=set()
    if any(k in t for k in BUG_K) or _tag(title): c.add("修复Bug")
    if any(k in t for k in FEAT_K) or _tag(title): c.add("新特性")
    if any(k in t for k in TASK_K): c.add("社区任务")
    if any(k in t for k in DOC_K): c.add("文档")
    if any(k in t for k in PERF_K): c.add("性能优化")
    if any(k in t for k in CI_K): c.add("CI/测试")
    if any(k in t for k in RF_K): c.add("重构")
    if any(k in t for k in IN_K): c.add("安装部署")
    if not c: c.add("其他")
    return c
def classify_iss(title):
    if not title: return set()
    t=title.lower(); c=set()
    if any(k in t for k in TASK_K): c.add("社区任务")
    elif any(k in t for k in BUG_K) or _tag(title): c.add("报告Bug")
    if any(k in t for k in FEAT_K): c.add("新特性")
    if any(k in t for k in DOC_K): c.add("文档")
    if any(k in t for k in PERF_K): c.add("性能优化")
    if any(k in t for k in CI_K): c.add("CI/测试")
    if any(k in t for k in IN_K): c.add("安装部署")
    if not c: c.add("其他")
    return c

D={}
for c in COMMS:
    cm=CM.get(c,{})
    inner=lambda u: "华为" in (cm.get(u) or "")
    def pool(tag,lv): return {x[0] for x in AD[c][f"{tag}-{lv}"]}
    P8d1,P8d2,P9d1,P9d2=pool("8","D1"),pool("8","D2"),pool("9","D1"),pool("9","D2")
    P8ex=P8d1-P8d2; P9ex=P9d1-P9d2
    # 8月记录索引
    rec8={}
    for u,ty,url in AD[c]["8-D1"]: rec8.setdefault(u,set()).add(ty)
    hj={x.lower() for x in HJ.get(c,[])} | {x.lower() for k in ("6-D0","6-D1","6-D2","7-D0","7-D1","7-D2") for x in MRO[c].get(k,[])}
    def cats_of(u):
        ct=set()
        for ti in TI[c]["aug"]["pr"].get(u,[]): ct|=classify_pr(ti)
        for ti in TI[c]["aug"]["iss"].get(u,[]): ct|=classify_iss(ti)
        if "pr" in rec8.get(u,()) or "issue" in rec8.get(u,()):
            if not ct: ct={"其他"}
        else:
            ct={"评论型"}
        if "comment" in rec8.get(u,()): ct.add("评论型")
        return sorted(ct,key=CATS.index)
    out={}
    for lv,px8,px9,allp9 in (("D1",P8ex,P9ex,P9d1),("D2",P8d2,P9d2,P9d1)):
        lost=sorted(px8-allp9)
        newu=sorted(px9-(P8d1))     # 9月出现在互斥池、8月完全不在D1大池(D2⊂D1) → 纯新增
        stay=len(px8&px9)
        per={}; cnt=Counter(); fix=0
        for u in lost:
            cl=cats_of(u)
            per[u]=cl
            for x in cl: cnt[x]+=1
            if "修复Bug" in cl: fix+=1
        # 首现/历史
        q1=[0,0]
        for u in lost:
            had = (u in hj)
            q1[1 if had else 0]+=1
        cl_all=Counter("内部" if inner(u) else "外部" for u in lost)
        cl_new=Counter("内部" if inner(u) else "外部" for u in newu)
        out[lv]={"p8":len(px8),"p9":len(px9),"p8_in":sum(1 for u in px8 if inner(u)),"p9_in":sum(1 for u in px9 if inner(u)),
            "lost":lost,"lost_n":len(lost),"lost_in":cl_all.get("内部",0),"lost_ext":cl_all.get("外部",0),
            "new":newu,"new_n":len(newu),"new_in":cl_new.get("内部",0),"new_ext":cl_new.get("外部",0),
            "cats":dict(cnt),"fixers":fix,"q1":q1,
            "lost_ext_list":[u for u in lost if not inner(u)],
            "new_list":[(u,"内部" if inner(u) else "外部",cm.get(u) or "无映射") for u in newu],
            "stay":stay}
        # 校验
        chk = len(px9)==stay+out[lv]["new_n"]+(len(px9&px8)-stay)
    D[c]=out
    v=out["D1"]; w=out["D2"]
    print(f'{c:12} D1池 {v["p8"]}→{v["p9"]} 流失{v["lost_n"]}(内{v["lost_in"]}/外{v["lost_ext"]}) 新增{v["new_n"]} | 评论型流失{v["cats"].get("评论型",0)} D2池 {w["p8"]}→{w["p9"]} 流失{w["lost_n"]} 新增{w["new_n"]}')
json.dump({"CATS":CATS,**D},open(B+"x40_data.json","w"),ensure_ascii=False)
print("saved x40_data.json")
