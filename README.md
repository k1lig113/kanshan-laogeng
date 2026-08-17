# 看山带你看老梗

「看山带你看老梗」是一个本地运行的网页小工具：输入一个老梗/网络热词，由知乎直答（zhihu-cli）实时解释并展示，配有刘看山吉祥物插画。

## 功能一览

### 看山 IP
- 官方素材驱动的“活物”：呼吸起伏、注视光标、戳一戳弹跳、拖拽回弹
- 40 秒没人理会犯困（冒 💤），动一下鼠标就醒
- 拖起看山松手会“转身”——循环切换官方四视图的 4 个姿势
- 把气泡拖到看山身上可“投喂”，它会回话并累积好感
- 点击头像 5 次解锁隐藏梗「刘看山其实是只哈士奇」

### 玩法
- **好感度养成**：看新梗 / 收藏 / 投喂 / 答对快问攒好感，等级从“路人”升到“轮子哥本哥”，头像下有等级徽章
- **今日挑战**：每天随机一个任务（戳新梗 / 收藏 / 连击 / 快问），完成 +5 好感
- **看山出题**：梗学快问默认接入独立大模型（OpenAI 兼容接口），把当前梗的知识喂给模型出四选一题；未配置 key 或出题失败时自动降级为本地年份题
- **梗编年史**：按年份排成时间轴，横滑浏览
- **梗宇宙星图**：可拖拽节点、空白处拖动平移、滚轮/双指缩放、悬停连线看关联、连线有粒子流
- **107 条梗库**：数据集中在 `memes-data.js`（29 条原始梗 + 78 条知乎原生梗，年份覆盖 2010-2026），全部梗均经 zhihu-cli 检索知乎官方十年盘点、知乎小管家官方说明及社区盘点整理；标签筛选替代了搜索框
- **详情扩写**：`memes-extra.js` 为全部 100 条补写了「来龙去脉」与「使用场景」（基于各梗原始资料由 DeepSeek 扩写），详情卡自动展示
- **弹幕回声**：详情页飘过知乎暗号弹幕
- **连击升级**：连戳显示得分，20 连触发“看山暴走”气泡加速
- **分享接力**：分享卡片上可以“接一句”，存入本地接龙链
- **键盘导航**：方向键移动、Home/End 跳转、Enter 打开
- **返回记忆**：返回列表时恢复滚动位置，已读梗带 ✓ 角标
- **深夜模式**：一键深色主题；23 点后自动切星空深夜，看山催你睡觉
- **匿名用户与全网统计**：每个浏览器生成匿名 ID（不采集个人信息），同一浏览器下次访问自动恢复该用户历史；页脚显示全网人数、总点击数、今日活跃（数据存服务器 SQLite，容器挂载 `data/` 卷，重建不丢）

### 体验
- 图片已转 WebP（立绘 190KB → 25KB）
- 无障碍：aria-live 播报、弹窗焦点还原、键盘可达
- 移动端保留浮动小看山，星图支持触摸拖拽

### 梗学快问 · 大模型配置（可选）

默认未配置时自动使用本地年份题库，零配置可跑。想用大模型出题，启动前设置三个环境变量：

```bash
export QUIZ_API_BASE=https://api.deepseek.com/v1   # 或任意 OpenAI 兼容接口
export QUIZ_API_KEY=你的_key
export QUIZ_MODEL=deepseek-chat                      # 模型名
python3 server.py
```

说明：
- 出题请求只发生在本地服务端，key 不会出现在浏览器里；
- 同一梗的题会缓存一天，不重复消耗额度；
- 接口返回格式不合法时前端自动降级本地题库，不影响浏览。

## 运行

依赖：Python 3、[zhihu-cli](https://github.com/zhihu/zhihu-cli)（已安装并配置好登录状态）。

```bash
python3 server.py
```

然后访问 <http://localhost:8931>。

> 说明：`GET /api/zhida?q=...` 会实时调用 `zhihu-cli answer` 流式输出，不缓存；本地服务会读取 `~/Library/Application Support/zhihu-cli/current/zhihu-cli`。

## 部署
项目只依赖 Python 标准库，基础镜像用 `python:3.12-slim`；`zhihu-cli` 用官方 Linux 预编译版，镜像里不需要装 Node。

```bash
# 把项目代码传到服务器后
docker compose up -d --build
```

访问 `http://服务器公网IP:8931`
部署前在服务器上的 `.env` 里补齐三样东西：

```bash
QUIZ_API_BASE=https://api.deepseek.com/v1
QUIZ_API_KEY=你的_deepseek_key
QUIZ_MODEL=deepseek-chat
ZHIHU_ACCESS_SECRET=你的_知乎_access_secret   # zhihu-cli 登录密钥，见下方说明
```

说明：
- `.env` 已被 `.dockerignore` 排除，密钥不会打进镜像层，只在容器运行时注入；
- 本地执行 `zhihu-cli auth status` 可确认/找回 Access Secret；
- 服务端默认监听 `HOST=0.0.0.0`（Dockerfile 已设），`PORT` 可通过环境变量覆盖；
- `ZHIHU_CLI` 环境变量可指定 zhihu-cli 路径，未设置时 macOS 本地路径优先。
- 换新 DeepSeek Key 后执行 `docker compose up -d` 即可生效（镜像没变时不会重建）。

## 目录结构

- `index.html` — 单页前端
- `server.py` — 本地静态托管 + 知乎直答 API 代理 + 梗学快问大模型出题
- `Dockerfile` / `docker-compose.yml` — 阿里云容器部署
- `assets/` — 刘看山插画与设计源文件
- `assets/poses/` — 从官方四视图切出的 4 个姿势（转身动画用）
