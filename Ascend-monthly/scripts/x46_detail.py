# -*- coding: utf-8 -*-
# x46: 每社区纯comment流失者 详细画像
import json, re
from collections import Counter
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
X=json.load(open(B+"x40_data.json"))
def sem(t):
    s=(t or "").strip().lower()
    if not s: return "空/极短"
    if re.fullmatch(r"(\+1|👍\+?|great(!)?|nice(!)?|good(!)?|thanks?|thank you|ty|ok(ay)?|yes|same|following|follow|looking forward( to)?( this| it)?|支持|同问|顶|赞|收到|ok了)[\s.!。~🎉👏🚀✨]*", s): return "+1/打call"
    if re.search(r"same (issue|problem|thing|error)|encounter|我(也|刚)遇到|同问|having (the same|this)|facing (the same|this)", s): return "我也遇到"
    if re.search(r"(when |eta|plan(n)?ing|roadmap|schedule|still (not|no)|any update|进展|计划|什么时候|预计|排期)", s): return "催进度/问排期"
    if re.search(r"(how (can|do|to|to do)|please (help|tell|explain)|question|what does|why (is|does|the)|unable to|can'?t (find|see|do)|如何|怎么|请问|求助|能不能|怎样)", s): return "求帮助/提问"
    if re.search(r"(error|fail(ed|ure)?|crash|not work(ing)?|doesn'?t work|broken|wrong|异常|报错|失败|复现|问题：)", s): return "反馈问题/报错"
    if re.search(r"(suggest|recommend|i think|in my opinion|consider|could (we|you)|should (we|be)|方案|建议|应该)", s): return "技术建议/观点"
    if re.search(r"(support|add (support)?|please support|need|want|would like|feature request|希望|支持一下|想要|能否支持)", s): return "功能请求"
    if re.search(r"(lgtm|approved?|review|nit|typo|please fix|rebase|merge|changed this line)", s): return "review/协作"
    if re.search(r"(测试报告|任务完成|淬火|quenching|report如下|结果如下|benchmark|复测)", s): return "测试报告/任务帖"
    return "一般讨论/陈述"
def person_cat(l):
    cs=[sem(c["body"]) for c in l if (c["body"] or "").strip()]
    if not cs: return "无正文(reaction类)"
    if all(x=="+1/打call" for x in cs): return "全程只打call"
    if any(x=="我也遇到" for x in cs) and all(x in ("我也遇到","+1/打call","一般讨论/陈述","反馈问题/报错") for x in cs): return "报到/附议"
    if any(x in ("催进度/问排期","求帮助/提问","反馈问题/报错","功能请求") for x in cs): return "带诉求"
    return "参与讨论/陈述"
for c in COMMS:
    C=json.load(open(B+f'cmt_{c}.json'))
    lost_n=len(X[c]['D1']['lost']); u_n=len(C)
    items=[(u,cc) for u,l in C.items() for cc in l]
    pc=Counter(person_cat(l) for l in C.values())
    dist=Counter("0条" if len(l)==0 else ("1条" if len(l)==1 else ("2-4条" if len(l)<=4 else ("5-9条" if len(l)<10 else "10条+"))) for l in C.values())
    order=["0条","1条","2-4条","5-9条","10条+"]
    print(f"\n{'='*76}\n【{c}】 D1流失{lost_n}人中纯评论 {u_n} 人（{u_n/lost_n*100:.0f}%）｜评论共{len(items)}条 人均{len(items)/u_n if u_n else 0:.1f}条")
    print(f"  评论量分布: "+"  ".join(f'{k}:{dist.get(k,0)}' for k in order))
    print(f"  行为分类:")
    for k in ["参与讨论/陈述","带诉求","全程只打call","报到/附议","无正文(reaction类)"]:
        if pc.get(k): print(f'    {k:18} {pc[k]:3} 人  {pc[k]/u_n*100:5.1f}%')
    # 诉求明细
    asks=[]
    for u,l in C.items():
        if person_cat(l)=="带诉求":
            for cc in l:
                k=sem(cc["body"])
                if k in ("催进度/问排期","求帮助/提问","功能请求","反馈问题/报错"):
                    asks.append((u,k,(cc["body"] or "").strip().replace("\n"," ")[:80])); break
    if asks:
        print(f"  带诉求者 {len(asks)} 人（可回访名录）:")
        for u,k,b in asks[:8]: print(f'    [{k}] @{u}: {b}')
        if len(asks)>8: print(f'    ...另{len(asks)-8}人')
    # 讨论/任务类高频者
    deep=sorted(((u,len(l)) for u,l in C.items() if len(l)>=5),key=lambda x:-x[1])[:5]
    if deep: print(f"  评论最多: "+"  ".join(f'@{u}({n}条)' for u,n in deep))
    if not items: print("  （该社区纯评论流失者均无正文，疑reaction为主）")
