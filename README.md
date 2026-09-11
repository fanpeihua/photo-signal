# 取景 · Photo Signal

摄影资讯、开源实践、竞品评论和版本动态的免费情报工作台。零运行依赖：Python 标准库 + SQLite + 原生浏览器。

网站：https://fanpeihua.github.io/photo-signal/

## 使用

- 今日视野：首见趋势、主题分布、商店评论样本情绪。
- 信号资料库：按平台、主题、品牌、情绪和时间筛选，搜索、原文跳转、导出、录入观察。
- 方向与差距：公开产品基线、竞品声音、带来源的实践候选、验收方式；可编辑自己的能力基线。
- 实践评测室：浏览器内两图曝光/细节诊断，记录 Android / iOS 设备、版本、场景、重复次数、盲评与结论；导出、合并导入备份。
- 来源与覆盖：各来源最后尝试、最后成功、失败和待接通状态。

**不是全网实时流。** GitHub、Hacker News、arXiv、App Store 为自动采集来源；摄影 RSS 按实际可达性显示。小红书、X、抖音在没有授权数据源时保持「待接通」，可人工记录或接入自己的授权 RSS。不能用空白状态证明没有讨论。没有买 API、代理或云服务器。

## 本地运行

```sh
python3 check.py
node check-metrics.js
python3 radar.py serve
```

打开 http://127.0.0.1:8840 。运行期间启动即采集，默认每 7200 秒重复；也可点击刷新立即采集。进程停止或电脑休眠期间不能采集。服务器仅监听回环地址，写接口限制同源。若 GitHub 未认证额度不足，可仅对当前进程传入 `GITHUB_TOKEN`，不要写入配置或网页。

```sh
python3 radar.py collect --local
python3 radar.py export
```

`data/radar.sqlite` 保存本地历史，`dist/` 是公开站点输出。`data/local-baseline.json` 可保存内部能力基线，仅本地 API 返回；覆盖公开基线的 `capabilities`、`scope`、`checked_at`。内部代码、日志、密钥、基线不进入公开仓库或快照。

## 免费远端更新

GitHub Actions 每两小时第 17 分钟采集，使用公开仓库免费标准 runner；GitHub Pages 托管交互界面和最新快照。页面每 5 分钟检查新快照。采集历史提交到 `data/public-snapshot.json`，全新 runner 会恢复首见日期和星标历史，而非每天清空。源码 push 与手动 Run workflow 都会采集并部署。

GitHub Pages 不运行 Python：公网「刷新」读取最新已部署数据，启动远端采集在 [Actions](https://github.com/fanpeihua/photo-signal/actions/workflows/collect.yml) 的 Run workflow。本机「刷新」可直接启动采集。不是手写固定数据的展示页，但也不承诺逐秒流式采集。

[GitHub 定时任务可能延迟或丢弃](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。超过 26 小时未采集时页面警示；失败源保留历史并单独显示错误。公开仓库 60 天没有活动可能停用定时任务，正常运行会持续提交有时间戳的真实采集快照。工作流成功表示部署执行完成，具体来源健康必须看网站。

## 来源接入

编辑 `config.json` 管理公开来源和关键词，添加 `kind: rss` / `atom`、`url`、`platform`、唯一 `id` 与说明。自有的授权来源（尤其含令牌的 URL）应仅放到被忽略的 `data/local-sources.json`：

```json
[
  {
    "id": "my-authorized-xhs-feed",
    "name": "我的小红书摄影授权源",
    "kind": "rss",
    "platform": "小红书",
    "url": "https://your-feed-host.example/photography.xml",
    "note": "填写授权范围、更新频率与覆盖限制"
  }
]
```

该示例不是可用源。自定义源只在 `serve` 或 `collect --local` 加载，记录标为私有且不进入公开导出。不要把私有令牌放公开配置。[X 官方搜索按量收费](https://docs.x.com/x-api/fundamentals/post-cap)，默认不调用。[抖音关键词视频搜索需要特殊权限](https://open.douyin.com/platform/resource/docs/accession-guide/type-and-permission)。目前没有证明可用的小红书免费全站搜索接口；未采用绕过登录、验证码或反爬的采集方式。

## 数据口径

- 关键词规则只生成主题，不生成伪造的 AI 总结。广泛检索还会过滤无摄影关键词和监控摄像头等无关内容；规则在 `keywords` / `exclude_keywords` 中可调，旧归档在展示导出时也使用当前规则。论文只看标题与链接，不能据此声称可在移动端运行。
- App Store 评论只采中国区最近一页（最多约 50 条），非全量；1–2 星负向、3 星中性、4–5 星正向。标题与短摘录、发布时间、品牌和原文链接保留，评论删除和修改可能使历史与页面不同。
- GitHub 按最近推送查询公开仓库，不是全站热门排行榜。星标增量需至少两个不同日期的真实观察。
- 14 天趋势按首次发现去重计数；首轮入库会形成峰值，不能当成热度爆发。没有采集前的日期是未知。未知原帖发布时间按首见时间筛选，并标明日期未知。
- 每个源独立失败隔离；保留 180 天最近被观察到的历史，页面导出上限 6000 条。后续增大规模前需调整保留策略与数据库查询。
- 公开竞品能力仅据商店描述，检查日期显示在网页。内部 Android 基线只在本地，能力存在与质量达标分开记录。
- 两图长边缩至 512，同一算法计算亮度、近黑/近白占比、Laplacian 方差及红蓝差；没有审美总分，也没有把噪声当成质量。不是校准过的专业 IQA 模型；用同场景盲评和端内诊断交叉核验。

## 私人数据与备份

手工观察、基线编辑、实践记录只在当前浏览器 localStorage，远端和本地各自独立，不会自动跨设备同步。照片完全在浏览器内处理，记录仅保存指标和文件名。清理浏览器数据会丢失记录，应定期在实践室「导出备份」。导入按 ID 合并且保留现有记录。公共页面没有接收笔记或图片的服务端接口。

## 验证

`python3 check.py` 验证去重、首见保留、未知/未来日期、评分口径、私有数据隔离、导出/恢复历史和内网地址拒绝。`node check-metrics.js` 用全黑、全白和棋盘图验证指标；`node --check web/app.js` 验证语法。真实接口和网页交互还需运行核验，测试通过不代表所有平台已接通。
