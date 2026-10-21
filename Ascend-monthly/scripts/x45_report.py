# -*- coding: utf-8 -*-
# x45: 9社区纯comment流失者画像汇总
import json, re
from collections import Counter
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
def sem(t):
    s=(t or "").strip().lower()
    if not s: return "空/极短"
    if re.fullmatch(r"(\+1|👍\+?|great(!)?|nice(!)?|good(!)?|thanks?|thank you|ty|ok(ay)?|yes|same|following|follow|looking forward( to)?( this| it)?|支持|同问|顶|赞)[\s.!。~🎉👏🚀]*", s): return "+1/打call型"
    if re.search(r"same (issue|problem|thing|error)|encounter|我(也|刚)遇到|同问|having (the same|this)|facing (the same|this)", s): return "我也遇到这个问题"
    if re.search(r"(when|eta|plan(n)?ing|roadmap|schedule|still (not|no)|any update|进展|计划|什么时候|预计)", s): return "催进度/问排期"
    if re.search(r"(how (can|do|to|to do)|please (help|tell|explain)|question|what does|why (is|does|the)|unable to|can'?t (find|see|do)|如何|怎么|请问|求助)", s): return "求帮助/提问"
    if re.search(r"(error|fail(ed|ure)?|crash|not work(ing)?|doesn'?t work|broken|bug|issue #|wrong|异常|报错|失败)", s): return "反馈问题/报错"
    if re.search(r"(suggest|recommend|i think|in my opinion|consider|could (we|you)|should (we|be)|方案|建议)", s): return "技术建议/观点"
    if re.search(r"(support|add (support)?|please support|need|want|would like|feature request|希望|支持一下|想要)", s): return "功能请求(求支持)"
    if re.search(r"(lgtm|approved?|review|nit|typo|please fix|更新|rebase|merge)", s): return "review/协作类"
    return "一般讨论/陈述"
def person_cat(l):
    cs=[sem(c["body"]) for c in l]
    if not cs: return "无正文"
    if all(x=="+1/打call型" for x in cs): return "全程只打call"
    if any(x=="我也遇到这个问题" for x in cs) and all(x in ("我也遇到这个问题","+1/打call型","一般讨论/陈述","反馈问题/报错") for x in cs): return "只报到/附议"
    if any(x in ("催进度/问排期","求帮助/提问","反馈问题/报错","功能请求(求支持)") for x in cs): return "带诉求(问/催/报障/求功能)"
    return "参与讨论/陈述"
print(f'{"社区":12}{"纯评论流失":>6}{"评论条数":>6}{"人均":>5} | {"打call走":>7} {"带诉求":>6} {"报到附议":>6} {"讨论陈述":>6} | 诉求样例')
allv=[]
for c in COMMS:
    C=json.load(open(B+f'cmt_{c}.json'))
    items=[(u,cc) for u,l in C.items() for cc in l]
    pc=Counter(person_cat(l) for l in C.values())
    u_n=len(C)
    asks=[]
    for u,l in C.items():
        if person_cat(l)=="带诉求(问/催/报障/求功能)":
            for cc in l:
                k=sem(cc["body"])
                if k in ("催进度/问排期","求帮助/提问","功能请求(求支持)"):
                    asks.append(cc["body"].strip().replace("\n"," ")[:52])
                    break
            if len(asks)>=2: break
    c1=pc["全程只打call"]; c2=pc["带诉求(问/催/报障/求功能)"]; c3=pc["只报到/附议"]; c4=pc["参与讨论/陈述"]
    avg=(len(items)/u_n) if u_n else 0
    line="%-12s%8d%8d%6.1f | %7d %6d %6d %6d | %s" % (c,u_n,len(items),avg,c1,c2,c3,c4," / ".join(asks))
    print(line)
    allv.append((c,u_n,pc))
print("\n== 全局 ==")
tot=sum(u for _,u,_ in allv)
agg=Counter()
for _,_,pc in allv: agg.update(pc)
for k,v in agg.most_common(): print(f'  {k:20} {v:4} 人  {v/tot*100:5.1f}%')
