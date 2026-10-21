# -*- coding: utf-8 -*-
# x47: 纯comment流失者中"社区任务认领/参与"识别
import json, re
from collections import Counter
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
# 任务认领/参与信号（评论正文）
TASK_PAT=re.compile(r"(任务(完成|已完|认领|领取|怎么领|认领了|申请)|认领(该|此|这个)?任务|已认领|claim(ed|ing)? (this |the )?(task|issue)|"
                    r"淬火|quenching|chenghuo|cann-outreach|社区任务|测试报告|测试(如下|完成)|结果如下|报告如下|task.*?(完成|done)|"
                    r"good[- ]first[- ]issue|标签(已|处理)|/label add|我认领|接下(来|受)|负责(该|此)?(模块|任务)|已完成.{0,6}(调研|方案|补充|测试))", re.I)
def is_task(b): return bool(TASK_PAT.search(b or ""))
print(f'{"社区":12}{"纯评论流失":>6}{"任务型":>6}{"占比":>6} | 典型账号(评论数)')
tot_p=tot_t=0
detail={}
for c in COMMS:
    C=json.load(open(B+f'cmt_{c}.json'))
    tn=[];  # 任务型人
    for u,l in C.items():
        bodies=[cc["body"] for cc in l]
        if any(is_task(b) for b in bodies): tn.append((u,len(l)))
    u_n=len(C); t=len(tn)
    tot_p+=u_n; tot_t+=t
    tn.sort(key=lambda x:-x[1])
    detail[c]=tn
    sample="  ".join(f'@{x}({n})' for x,n in tn[:6])
    print(f'{c:12}{u_n:8}{t:7}{(t/u_n*100 if u_n else 0):5.0f}% | {sample}')
print(f'\n合计: 纯评论流失 {tot_p} 人，其中任务认领/参与型 {tot_t} 人（{tot_t/tot_p*100:.0f}%）')
# 抽3条真实文本验证判定
print("\n判定样例(每社区取1条命中评论):")
for c in COMMS:
    if not detail[c]: continue
    u=detail[c][0][0]
    C=json.load(open(B+f'cmt_{c}.json'))
    for cc in C[u]:
        if is_task(cc["body"]):
            print(f'  [{c}] @{u}: '+(cc["body"] or "").strip().replace("\n"," ")[:78]); break
