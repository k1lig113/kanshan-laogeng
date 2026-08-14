# 看山带你看老梗

「看山带你看老梗」是一个本地运行的网页小工具：输入一个老梗/网络热词，由知乎直答（zhihu-cli）实时解释并展示，配有刘看山吉祥物插画。

## 运行

依赖：Python 3、[zhihu-cli](https://github.com/zhihu/zhihu-cli)（已安装并配置好登录状态）。

```bash
python3 server.py
```

然后访问 <http://localhost:8931>。

> 说明：`GET /api/zhida?q=...` 会实时调用 `zhihu-cli answer` 流式输出，不缓存；本地服务会读取 `~/Library/Application Support/zhihu-cli/current/zhihu-cli`。

## 目录结构

- `index.html` — 单页前端
- `server.py` — 本地静态托管 + 知乎直答 API 代理
- `assets/` — 刘看山插画与设计源文件
