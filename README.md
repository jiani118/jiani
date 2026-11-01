# 视频下载器

基于 Flask 和 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的网页视频下载工具。粘贴链接，解析后选择画质下载，支持进度条，可安装到手机桌面（PWA）。

## 功能
- 解析视频信息，选择画质，或仅下载音频
- 下载进度、速度、剩余时间
- 查看和搜索支持的网站（含常用网站中文名）
- 可添加到手机主屏幕（需要 HTTPS）

## 本地运行
```bash
pip install -r requirements.txt
python app.py
```
浏览器打开 http://localhost:8000 。要下载 1080p 以上，需要先安装 [ffmpeg](https://ffmpeg.org/)。

## Docker 部署
```bash
docker compose up -d --build
```
服务器上也可以直接运行一键脚本：
```bash
sudo bash deploy.sh                # 通过 IP:8000 访问
sudo bash deploy.sh 你的域名.com   # 自动配置 Caddy 和 HTTPS
```

## 更新 yt-dlp
网站改版会导致解析失败，更新 yt-dlp 即可：
```bash
docker compose build --no-cache && docker compose up -d
```

## 声明
请仅下载你拥有权利或获得授权的内容，并遵守各平台服务条款和当地法律。
