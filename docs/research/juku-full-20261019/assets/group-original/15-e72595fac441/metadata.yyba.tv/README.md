# YYBA TMDB TV Scraper

[中文](#中文) · [English](#english)

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](../../LICENSE)
[![Kodi](https://img.shields.io/badge/Kodi-20%2B-17B2E7)](https://kodi.tv/)

**Local-first TMDB TV metadata scraper for Kodi.**

Caches raw TMDB JSON under a configurable `.tv` directory. TV show and episode metadata can be stored separately from your video library.

> This product uses the TMDB API but is **not endorsed or certified by TMDB**.

---

## English

### Overview

**YYBA TMDB TV Scraper** (`metadata.yyba.tv`) mirrors the architecture of [metadata.yyba.movie](../metadata.yyba.movie/). It stores **raw TMDB API responses** as JSON and uses a **local-first** scrape flow for TV shows and episodes.

### Features

- **Local-first** — read cached JSON before calling TMDB
- **Title-based keys** — uses Kodi's scan `title` (local folder/filename)
- **Separate meta root** — `.tv` path independent of video files
- **Show + episode cache** — show JSON + per-episode JSON files
- **Full metadata** — plot, genres, ratings, status, creators, cast
- **Artwork via TMDB CDN** — poster, fanart, episode stills
- **Cast thumbnails** — from `credits.cast[].profile_path`
- **Episode guide** — `getepisodelist` / `getepisodedetails` for Kodi TV library
- **Languages** — Chinese (zh-CN) / English (en-US)
- **Flexible TMDB endpoint** — same 3-mode setup as the movie scraper

### Cache layout

```
{meta_path}/.tv/
  权力的游戏.json          ← TV show (raw TMDB /tv/{id} JSON)
  权力的游戏/
    S01E01.json            ← Episode (raw TMDB episode JSON)
    S01E02.json
    ...
```

### Architecture

| Module | File | Role |
|--------|------|------|
| Settings | `lib/settings.py` | Addon settings & Kodi request params |
| TmdbApi | `lib/tmdb_api.py` | TMDB search / TV / season / episode API |
| MetaFiles | `lib/meta_files.py` | Read/write show & episode JSON |
| TVScraper | `scraper.py` | Kodi entry: find / getdetails / episodelist / episodedetails |
| ListItem | `lib/list_item.py` | TMDB JSON → Kodi ListItem |

### Installation

```bash
cd metadata.yyba.tv
python build_zip.py
# Install metadata.yyba.tv-install.zip in Kodi
```

Configure `.tv` storage path, TMDB API key, and Image CDN host (`media.themoviedb.org` by default, or `tmdb.img.yyba.cn` for devices that cannot reach TMDB CDN), then select this scraper for your TV library source.

### License

Apache-2.0 — see [LICENSE](../../LICENSE) and [addon.xml](addon.xml).

---

## 中文

### 产品简介

**YYBA TMDB TV Scraper**（`metadata.yyba.tv`）与 [电影刮削器](../metadata.yyba.movie/) 采用相同架构：以 **TMDB 原始 JSON** 本地缓存，**本地优先** 刮削电视剧与单集。

### 核心特性

- **本地优先** — 先读本地 JSON，命中则不走网络
- **以 title 为键** — 使用 Kodi 扫描传入的本地目录/文件名
- **元数据与视频分离** — `.tv` 路径可独立配置
- **剧集 + 单集缓存** — 整剧 JSON + 每集 JSON
- **完整元数据** — 简介、类型、评分、状态、主创、演员
- **海报 / 背景 / 单集剧照** — TMDB CDN URL
- **演员头像** — 从源数据 `profile_path` 映射
- **单集向导** — 支持 Kodi `getepisodelist` / `getepisodedetails`
- **多语言、API 域名与图片 CDN 域名** — 与电影版设置一致（图片 CDN 默认 `media.themoviedb.org`，部分设备无法访问 TMDB CDN 时可切换 `tmdb.img.yyba.cn`）

### 缓存结构

```
{meta_path}/.tv/
  权力的游戏.json          ← 剧集（TMDB /tv/{id} 原始 JSON）
  权力的游戏/
    S01E01.json            ← 单集（TMDB episode 原始 JSON）
    S01E02.json
    ...
```

### 架构

| 模块 | 文件 | 职责 |
|------|------|------|
| Settings | `lib/settings.py` | 插件设置与 Kodi 请求参数 |
| TmdbApi | `lib/tmdb_api.py` | TMDB 搜索 / 剧集 / 季 / 单集 API |
| MetaFiles | `lib/meta_files.py` | 读写剧集与单集 JSON |
| TVScraper | `scraper.py` | Kodi 入口 |
| ListItem | `lib/list_item.py` | TMDB JSON → Kodi ListItem |

### 安装

```bash
cd metadata.yyba.tv
python build_zip.py
```

在 Kodi 中安装 `metadata.yyba.tv-install.zip`，配置 `.tv` 路径与 API Key，并在电视剧库源中选择本刮削器。

### 开源协议

Apache-2.0 — 详见 [LICENSE](../../LICENSE) 与 [addon.xml](addon.xml)。

### 声明

本产品使用 TMDB API，**未经 TMDB 认可或认证**。
