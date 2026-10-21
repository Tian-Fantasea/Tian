# -*- coding: utf-8 -*-
# x48: 每社区任务型纯comment者评论正文高频词Top3
import json, re
from collections import Counter
B=__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data")+__import__("os").sep
COMMS=["vllm","sgl","VeRL","triton","MindIE","MindSDK","MindStudio","MindCluster","MindSpeed"]
TASK_PAT=re.compile(r"(任务(完成|已完|认领|领取|怎么领|认领了|申请)|认领(该|此|这个)?任务|已认领|claim(ed|ing)? (this |the )?(task|issue)|"
                    r"淬火|quenching|chenghuo|cann-outreach|社区任务|测试报告|测试(如下|完成)|结果如下|报告如下|task.*?(完成|done)|"
                    r"good[- ]first[- ]issue|标签(已|处理)|/label add|我认领|接下(来|受)|负责(该|此)?(模块|任务)|已完成.{0,6}(调研|方案|补充|测试))", re.I)
try:
    import jieba; HAS_JIEBA=True
except Exception: HAS_JIEBA=False
STOP=set("的 了 我 你 他 是 在 有 和 就 不 也 都 一 这 那 个 上 到 说 们 为 与 及 或 等 着 被 把 从 将 can not for the and of to a is are in on it this that i you we 请 已 如下 一下 麻烦 谢谢 您好 可以 需要".split())
def words(t):
    t=re.sub(r'https?://\S+','',t or "")
    t=re.sub(r'[#*>`\[\]()!？?。，,、;:：""''"\|\-]+',' ',t)
    if HAS_JIEBA: ws=jieba.lcut(t)
    else:
        ws=[]
        for seg in re.findall(r'[\u4e00-\u9fff]+|[A-Za-z][A-Za-z0-9_\-\.]+',t):
            if re.match(r'[\u4e00-\u9fff]',seg):
                for n in (3,2):
                    ws+= [seg[i:i+n] for i in range(len(seg)-n+1)] if len(seg)>n else ([seg] if len(seg)>=2 else [])
            else: ws.append(seg.lower())
    return [w.strip() for w in ws if len(w.strip())>=2 and w.strip() not in STOP and not re.fullmatch(r'\d+',w)]
print(f'{"社区":12}{"任务型":>5} 高频词Top3(出现人数)')
for c in COMMS:
    C=json.load(open(B+f'cmt_{c}.json'))
    tu=[u for u,l in C.items() if any(TASK_PAT.search(cc["body"]) for cc in l)]
    df=Counter()   # 按人计（出现该词的人数）
    for u in tu:
        seen=set(words(" ".join(cc["body"] for cc in C[u])))
        for w in seen: df[w]+=1
    # 过滤纯英文长串路径类
    top=[(w,n) for w,n in df.most_common(12) if not re.search(r'gitcode|github|com|cn$',w,re.I)][:3]
    print(f'{c:12}{len(tu):6}   '+"  ".join(f'「{w}」({n}人)' for w,n in top))
