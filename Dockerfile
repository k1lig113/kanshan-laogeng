# 看山老梗 · 阿里云部署镜像
#
# 基础镜像 python:3.12-slim：项目只用 Python 标准库，镜像最小。
# zhihu-cli 用知乎官方 CDN 发布的 Linux 预编译二进制（Go 静态链接，
# 无系统依赖），下载时校验官方 manifest 中的 SHA-256。
#
# 构建参数：
#   ZHIHU_ARCH     amd64（x86 服务器，默认）或 arm64（倚天 710）
#   ZHIHU_VERSION  zhihu-cli 版本，默认 0.3.0

ARG ZHIHU_ARCH=amd64
FROM python:3.12-slim

ARG ZHIHU_ARCH
ARG ZHIHU_VERSION=0.3.0

RUN set -eux; \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com/debian-security|g' \
        /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    case "$ZHIHU_ARCH" in \
      amd64) SHA="d7e89a2d5df20ab367d944c2a1f7694b6272705c18ebc8d7388129a7933e0e80" ;; \
      arm64) SHA="42296df3bc7f4678e050c6fb6e627f4ad87c6f3755e9f6b248a0813bea3dd2c7" ;; \
      *) echo "不支持的架构: $ZHIHU_ARCH"; exit 1 ;; \
    esac; \
    curl -fsSL "https://developer-cdn.zhihu.com/zhihu-cli/releases/stable/cli/${ZHIHU_VERSION}/zhihu-cli-${ZHIHU_VERSION}-linux-${ZHIHU_ARCH}.tar.gz" -o /tmp/zhihu-cli.tgz; \
    echo "$SHA  /tmp/zhihu-cli.tgz" | sha256sum -c -; \
    tar -xzf /tmp/zhihu-cli.tgz -C /usr/local/bin; \
    chmod +x /usr/local/bin/zhihu-cli; \
    rm /tmp/zhihu-cli.tgz; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*

ENV HOST=0.0.0.0 \
    PORT=8931 \
    ZHIHU_CLI=/usr/local/bin/zhihu-cli

WORKDIR /app
RUN mkdir -p /app/data
COPY index.html memes-data.js server.py README.md ./
COPY assets ./assets

EXPOSE 8931
CMD ["python3", "server.py"]
