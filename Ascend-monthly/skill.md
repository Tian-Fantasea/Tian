# 社区活跃开发者「流失/新增」月度分析 — 复现手册

> 目标：每月用 datastat 最新数据，一键产出与 **V10** 同款的 PPT（9 社区 × D1/D2 逐人点名账 + 评论行为画像 + 附录全名单 + 人级恒等对账）。
> 版本产物：`9社区流失开发者分析_V{n}.pptx`，输出到本目录（`最新交付/`）。
> 脚本清单：见末尾「资产索引」。所有脚本在本目录 `scripts/` 下，数据中间产物缓存可复用。

---

## 0. 一次性准备

1. **取 datastat token**（会过期，一般 90 天）
   - 浏览器登录 `https://datastat.osinfra.cn` → F12 Network → 复制任意请求 Header 里的 `token:` 值。
   - 替换所有 `scripts/*.py` 顶部的 `T='eyJ...'`（或改成从环境变量读）。
2. **Python 依赖**：`pip install python-pptx xlsxwriter`（评论分词可选 `jieba`，无则自动降级）。
3. **改月份**（每月只动这一处）：把脚本里的窗口常量
   - `x39_active.py` / `x44_allcmt.py` 里 `ms(2026,8,1)/ms(2026,9,1)/ms(2026,10,1)` 三值 → 改为「上月1日 / 本月1日 / 次月1日」。
   - 记法：`PREV=8月, CUR=9月`，报告标题里的“8月→9月”同步替换。

---

## 1. 数据链路（关键概念，务必理解再跑）

| 概念 | 含义 | 接口 |
|---|---|---|
| **当月活跃池** | 该月有任一贡献记录的账号集合。**必须用 `operation:"active"`**（不是 increase，二者差数倍） | `POST /server/user/level/detail` `operation=active` |
| **D1** | 周期内有 提交PR / 提Issue / 评论 任一（=报表"活跃贡献者"宽口径，含评论） | 同上，`level:"D1"` |
| **D2** | 周期内有 PR 被 merged | 同上，`level:"D2"` |
| **D1池 vs D2池** | 报表分别给的"D1活跃数""D2活跃数"；D1⊃D2，做互斥分析要 `D1_excl = D1−D2` | `active/user` 或池计数 |
| **净变化 ≠ 纯进出** | 互斥池 `Δ = 新增 − 流失 ±层间流动(D1↔D2升级/降级)`，必须单列"层间"项才闭合 | x40 计算 |
| **流失/新增** | 逐人集合差：`流失=上月在池∩本月整个D1池无记录`；`新增=本月在该池∩上月完全不在池`（点名，非推导） | x40 |

**报表勾稽接口**（对数用）：
- 层级总人数：`POST /server/user/active/user` `{community,levelList:["D1"],interval:"month",eventList:[""],start,end}` → `increase`=该层级该月总人数（=报表页数值）。加 `internalList:["内部"]` 得内部拆分。
- D1池账号数应 = active/user 的 D1 数（本项目 vllm 已核对 754=754）。**若 x40 池人数对不上 active/user，说明 operation 用错**。

---

## 2. 标准执行顺序

```bash
cd 最新交付/scripts        # 全套自包含：数据读写都在 scripts/data/，不依赖任何临时目录/Google表

# ① 公司映射 + 1-7月历史活跃标记（首现/历史判定用；token换月时仅需重跑一次/季）
python3 -u x23_fetch.py            # → data/compmap.json, data/hist_janjul.json

# ② 报表级人数（总览D0列 & 勾稽基准；= datastat开发者页同一管道）
python3 -u x32_latest.py           # → data/active_latest.json

# ③ 逐人标题明细（上月/本月 PR+Issue，供类型分类）
python3 -u x37_refetch.py          # → data/titles_1021.json

# ④ 当月活跃池逐人明细（核心！operation=active）
python3 -u x39_active.py           # → data/active_detail.json

# ⑤ 人级点名账：池/流失/新增/留存/层间流动/分类/首现历史/名单
python3 -u x40_calc.py             # → data/x40_data.json   (逐社区打印恒等✓)

# ⑥ 评论行为画像（纯comment流失者正文）+ 任务型/高频词
python3 -u x44_allcmt.py           # → data/cmt_{社区}.json
python3 -u x49_taskmeta.py         # → data/task_meta.json

# ⑦ 出图（V10 版式）
python3 -u x50_v10.py              # → ../9社区流失开发者分析_V10.pptx  ★交付物
```
分析型脚本（按需）：x45 九社区画像汇总、x46 逐社区明细、x47 任务型识别、x48 高频词——读 data/ 直接出 stdout。

**跑完必看**：`x40_calc.py` 每行末尾 `✓` 表示 `8月池=留存+流失+升入D2` 且 `9月池=留存+新增+降级流入` 成立；有 `✗` 立即检查窗口/operation。

---

## 3. V10 版式规格（渲染层 x50_v10.py 已固化）

### 3.1 每社区 2 页（D1、D2）
- 标题：`{社区} — {层} 活跃开发者流失分析（上月→本月）`
- **红字三行（大字，逐人点名实数）**：
  1. `{层}活跃开发者总数：上月 A 人（内 a/外 b）→ 本月 C 人（内 c/外 d）`
  2. `{层}9月流失 −N 人（内/外）｜净变化 ±X 人（含升入D2/降级流入…，层间净流出/入 Y 人）`
  3. `{层}9月新增 M 人（内/外）`
- 灰色口径行：`留存 s 人(%)；账目 8月池=留存+流失+升入D2；9月池=留存+新增+自D2降级`
- 图表：**「本月流失开发者 · 上月贡献活动分布」**
  - 左类别轴=类型名，右柱外=数值（`show_category_name=False, show_value=True`）
  - 横向柱**类别倒序**传入，使视觉顺序与文字明细一致（否则上下颠倒看似错位）
  - 轴字体显式设 10pt（否则大字号导致类别抽稀，只显示一半）
- 右下文字：`类型明细：…（合计N人次，一人可命中多类）`、`流失者构成：首现/历史/修过Bug/纯评论型（社区任务型X人，占%，高频词「」「」）`
  - 纯评论型：**D1 用 task_meta.pure_n（无任何PR/Issue产出的严格数）**，括注任务型占比+Top2高频词；D2 保留评论参与数
  - sgl 特例：任务型0人时写「多为真实诉求而非任务党」

### 3.2 总览页（逐人点名账）
列：社区｜D0上/本月｜D1池上/本月｜D1流失(内/外)｜D1新增｜D1留存率｜D2同理。全部点名实数，非报表聚合。

### 3.3 附录 4 页（逐人全名单，含内部）
D1流失 / D2流失 / D1新增 / D2新增，每社区一行「人数｜内外｜账号名单」。

---

## 4. 贡献分类规则（x40_calc.py 内 classify_pr/iss）

- **多标签**：一人可命中多类，柱图加总=人次≥人数（页上标注"一人可命中多类"）。
- 修复Bug（PR标题命中bug词）≠ 报告Bug（Issue标题命中），V4 起拆分。
- **评论型**：active 明细只有 comment 记录者。
- **社区任务型**：评论正文命中 `x49` 的 `TASK_PAT`（认领/淬火/测试报告/交链接等）；高频词用 `LEX` 词表按"出现人数"计。
- 词表都在 x40_calc / x49_taskmeta 顶部，按社区实际情况增删关键词。

---

## 5. 常见坑（本项目踩过的，务必规避）

1. **operation 用 increase 会漏 4~5 倍的人**——报表754只取到384，误判"覆盖缺口"。一律 `active`。
2. **净变化 ≠ 新增−流失**：忘了 D1↔D2 层间流动就对不上账（本项目每社区差 6~13 人）。
3. **`level/detail` 大窗口会 IncompleteRead**（响应体大被掐断）→ `pageSize` 拆到 200~250。
4. **报表是滚动口径、且持续回填**（9月数据10月中旬比10月初多几十个）→ 出报告后若被质疑"数变了"，是回填，重跑即可。
5. **横向柱状图类别上下倒置**、**类别抽稀只显示一半**：见 3.1 图表两条修正。
6. 评论正文拉不到的账号=GitHub reaction/表情，非错误；单月活跃池留存率低(12~33%)是正常高换手，≠关系破裂（分析用D2留存率50~88%看核心粘性）。
7. 名单账号已 `.lower()` 归一，展示大小写与原站不同属正常。

---

## 6. 勾稽自检清单（交付前逐条过）

- [ ] x40 每社区每层 `8月池=留存+流失+升D2`、`9月池=留存+新增+降流入` 全 ✓
- [ ] D1池账号数 == active/user 的 D1 数（内外拆分==报表内外拆分）
- [ ] 红字/总览/附录 三处同一数字一致（人数、名单长度）
- [ ] 图表柱=左轴类型=明细文字 三处类型名一一对应
- [ ] 页顶"纯评论型"用严格 pure_n，括注任务型为其子集（勿混参与数275与纯193）
- [ ] 打开 PPT 无字体抽稀/截断（类别轴 10pt）

---

## 7. 资产索引

**脚本（`scripts/`）**
| 脚本 | 作用 | 产出 |
|---|---|---|
| x23_fetch.py | 公司映射+1-7月历史活跃 | compmap/hist_janjul.json |
| x32_latest.py | 报表级层级人数 | active_latest.json |
| x37_refetch.py | 逐人PR/Issue标题明细 | titles_1021.json |
| x39_active.py | 拉当月活跃池明细(active口径) | active_detail.json |
| x40_calc.py | 人级点名账+分类+流动+恒等校验 | x40_data.json |
| x44_allcmt.py | 纯comment流失者评论正文拉取 | cmt_{社区}.json |
| x45_report.py | 9社区评论画像汇总 | stdout |
| x46_detail.py | 每社区评论明细+诉求样例 | stdout |
| x47_task.py | 任务认领型识别+占比 | stdout |
| x48_words.py / x49_taskmeta.py | 高频词Top3/任务型元数据 | task_meta.json |
| x41_v9.py | V9渲染(点名账基线) | V9.pptx |
| **x50_v10.py** | **V10渲染(含评论画像括注)= 最终交付** | **V10.pptx** |

**数据文件（`scripts/data/`，缓存可复用/覆盖）**：active_detail、x40_data、task_meta、cmt_{社区}×9、active_latest、titles_1021、compmap、hist_janjul、month_rosters。当前目录已含 2026-08/09 全量快照，删临时目录不影响复跑；换月由 ①→⑦ 重新生成覆盖。

**接口速查（datastat）**
- `user/level/detail` — 逐人明细，`operation=active`
- `user/active/user` — 层级聚合人数(报表数)，`levelList/internalList`
- `query/prs/detail`(state=merged) / `query/issues/detail` / `query/comments/detail` — 标题/正文
- `query/contributes/page` — 人→company(内外判定)

**社区参数**：`community ∈ vllm, sgl, VeRL, triton, MindIE, MindSDK, MindStudio, MindCluster, MindSpeed`

---
*本手册随 V10 沉淀；下一版若版式再演进，更新第 3 节并另存 x5x 脚本，保留历史脚本以便回溯。*
