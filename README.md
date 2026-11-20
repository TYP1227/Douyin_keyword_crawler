# 社交媒体关键词爬虫 / Social Media Keyword Crawler

面向研究场景的抖音 / 快手关键词采集工具，可依据关键词爬取相关公开搜索结果数据。项目仅用于学术研究、论文写作与技术学习，严禁用于商业采集、批量营销、侵犯隐私或其他违法违规用途。

## 主要功能

- 平台：支持 `douyin` 和 `kuaishou` 两个平台。
- 登录态：通过 Chrome / Edge 的 CDP 远程调试端口复用浏览器登录态，不需要手动维护 `cookie.txt`。
- 关键词：支持直接传入 `--keywords`，也支持通过 `--keywords-file` 批量读取；可配合 `--locations` 自动拼接城市名。
- 过滤与去重：支持按发布时间、IP 属地过滤；已写入过的作品会通过 seen 状态跳过，减少重复采集。
- 输出：支持 `csv`、`xlsx`、`both`；采集过程中会增量写入 CSV，正常结束后可生成 XLSX。
- 风控处理：内置随机等待、随机滚动、连续空结果停止、连续 seen 提前停止；命中验证码、滑块、访问频繁等风险提示时会停下等待人工处理。
- 进度：终端会显示当前关键词、候选数、滚动轮次、已用时间和预计剩余时间。

## 安装

建议先创建一个独立 Python 环境，避免和系统环境或其他项目依赖混在一起。

项目代码兼容 Python 3.9 及以上版本。新建环境时建议用 Python 3.12。

Conda：

```bat
cd douyin_keyword_crawler
conda create -n your_env python=3.12
conda activate your_env
pip install -r requirements.txt
```

Python 自带 venv：

```bat
cd douyin_keyword_crawler
python -m venv your_env
your_env\Scripts\activate
pip install -r requirements.txt
```

说明：

- `requirements.txt` 里的 `playwright` 是 Python 控制库，必须安装；它负责连接 Chrome / Edge 的 CDP 调试端口。
- 当前推荐用法是连接本机已经安装好的 Chrome / Edge，因此默认不需要执行 `playwright install chromium`。
- `playwright install chromium` 的作用是额外下载 Playwright 自带的 Chromium 浏览器，通常会放在用户缓存目录，例如 `%LOCALAPPDATA%\ms-playwright`，不会下载到本项目目录，也不是 `data\chrome-profile`。
- `data\chrome-profile` / `data\edge-profile` 是本项目专用的浏览器用户数据目录，用来保存登录态、Cookie 和缓存；它们会变大，但这和 Playwright 下载浏览器不是一回事。

## 启动浏览器

先启动一个带远程调试端口的浏览器，并在这个浏览器里正常登录抖音/快手。

### 浏览器和登录态目录

本项目默认把专用浏览器登录态放在项目目录的 `data/` 下：

- Chrome：`data\chrome-profile`
- Edge：`data\edge-profile`

这里保存的是浏览器用户数据目录，包括登录态、Cookie、缓存、扩展数据等，不是浏览器安装包，也不是程序代码。第一次运行时如果没有这些目录，Chrome / Edge 会自动创建；你不需要手动下载或复制这个目录。

如果电脑没有安装 Chrome 或 Edge，请先安装任意一个：

- Chrome：https://www.google.com/chrome/
- Edge：https://www.microsoft.com/edge

安装浏览器后，先进入项目根目录，再用下面的命令启动。以下命令默认你当前在项目父目录；如果已经在 `douyin_keyword_crawler` 目录里，跳过 `cd` 这一步。

```bat
cd douyin_keyword_crawler
```

建议固定使用同一个 profile 目录，不要频繁删除或更换；否则需要重新登录抖音/快手。

Chrome：

```bat
start chrome.exe --remote-debugging-port=9222 --user-data-dir="%cd%\data\chrome-profile"
```

Edge：

```bat
start msedge.exe --remote-debugging-port=9222 --user-data-dir="%cd%\data\edge-profile"
```

注意：

- `data\chrome-profile` / `data\edge-profile` 体积变大是正常现象；里面主要是浏览器缓存和登录态。删除后可以自动重建，但需要重新登录平台。
- 不建议频繁换账号、换代理、换浏览器 profile。
- 出现验证码、滑块、扫码、登录确认时，必须在浏览器里手动完成，程序不会绕过验证。
- 代理不是默认必需；如果确实要用，优先让 Chrome/Edge 自己走稳定代理。

### 重建浏览器 profile

如果 `data\chrome-profile` 或 `data\edge-profile` 体积过大、登录态异常，或者你想重新登录一个干净环境，可以删除对应目录后再启动浏览器。删除前先关闭用这个 profile 启动的 Chrome / Edge。

下面的命令同样默认你当前在项目父目录；如果已经在 `douyin_keyword_crawler` 目录里，跳过 `cd` 这一步。

重建 Chrome profile：

```bat
cd douyin_keyword_crawler
rmdir /s /q data\chrome-profile
start chrome.exe --remote-debugging-port=9222 --user-data-dir="%cd%\data\chrome-profile"
```

重建 Edge profile：

```bat
cd douyin_keyword_crawler
rmdir /s /q data\edge-profile
start msedge.exe --remote-debugging-port=9222 --user-data-dir="%cd%\data\edge-profile"
```

删除 profile 只会删除本项目专用浏览器环境，不会删除你电脑上安装的 Chrome / Edge，也不会影响日常浏览器默认 profile。删除后目录会在下次启动时自动创建，但需要重新登录抖音/快手。

## 诊断

诊断不会访问平台，只检查本地参数和状态库。

```bat
python main.py ^
  --platform douyin ^
  --keywords-file keywords.txt ^
  --locations "深圳" ^
  --start-date 2025-04-01 ^
  --end-date 2025-09-30 ^
  --diagnose
```

## 运行示例

先用小参数试跑：

```bat
python main.py ^
  --platform douyin ^
  --keywords "内涝" ^
  --locations "深圳" ^
  --start-date 2025-04-01 ^
  --end-date 2025-09-30 ^
  --out-format both ^
  --max-pages 2 ^
  --max-items 30 ^
  --min-sleep 5 ^
  --max-sleep 12 ^
  --state-db data/state-try.sqlite3
```

跑关键词文件（douyin+默认chorme）：

```bat
python main.py ^
  --platform douyin ^
  --keywords-file "keywords copy.txt" ^
  --locations "东莞" ^
  --start-date 2017-01-01 ^
  --end-date 2026-09-30 ^
  --out-format csv ^
  --max-pages 30 ^
  --max-items 200 ^
  --min-sleep 5 ^
  --max-sleep 12 ^
  --state-db data/state.sqlite3
```

快手 + Edge：

```bat
python main.py ^
  --platform kuaishou ^
  --browser-channel msedge ^
  --keywords-file "keywords copy.txt" ^
  --locations "深圳" ^
  --start-date 2018-04-01 ^
  --end-date 2026-06-30 ^
  --out-format both ^
  --max-pages 30 ^
  --max-items 300 ^
  --min-sleep 5 ^
  --max-sleep 12 ^
  --state-db data/state-kuaishou.sqlite3
```

注意：需要启动对应的浏览器

单条抖音 URL 排查：

```bat
python main.py ^
  --platform douyin ^
  --keywords "此处放入单条视频链接" ^
  --location-mode none ^
  --start-date 2000-01-01 ^
  --out output\debug.csv ^
  --max-pages 1 ^
  --max-items 5 ^
  --no-resume
```

## 输出

默认输出到 `output/`。文件名会根据平台、地点、前两个关键词和日期生成。也可以用 `--out` 指定路径。

程序会在运行开始时先创建 CSV 表头，并在采集过程中逐条增量写入 CSV；每条结果写入成功后，会立刻把作品 ID 记录到 `data/state.sqlite3` 的 seen 状态里。这样即使运行中断，已经写入 CSV 的结果和 seen 去重状态也会保留。下次执行同样命令时，默认会重新搜索，但已写入过的作品会被 seen 去重跳过。

重复运行同一批关键词时，程序会把历史 seen 作品 ID 加载到内存里加速判断。如果当前关键词连续遇到很多条已 seen 作品，会提前停止当前关键词，避免在已经跑过的结果里反复滚动；阈值由 `--max-seen-items` 控制。

如果 `--out-format xlsx` 或 `--out-format both`，XLSX 文件会在任务正常结束时由 CSV 转换生成；如果运行中断，优先查看同名 CSV 临时结果。

字段：

| 字段                  | 说明                                             |
| --------------------- | ------------------------------------------------ |
| `user_id`           | 作者 ID                                          |
| `username`          | 作者昵称                                         |
| `ip_location`       | 平台返回的发布 IP 属地，常为空，不等于真实发生地 |
| `poi_name`          | 用户发布时挂载的 POI 名称，如`ICC武汉环贸中心` |
| `poi_address`       | POI 详细地址，如`武汉市江汉区青年路161号...`   |
| `location_lng`      | POI 经度，平台接口返回时填写                     |
| `location_lat`      | POI 纬度，平台接口返回时填写                     |
| `inferred_location` | 从标题/话题/关键词识别出的粗略城市，只作辅助参考 |
| `publish_time`      | 发布时间                                         |
| `content_text`      | 标题/描述/正文                                   |
| `post_url`          | 作品入口 URL                                     |
| `media_type`        | `video`、`images`、`mixed`、`unknown`    |
| `like_count`        | 点赞数                                           |
| `comment_count`     | 评论数                                           |

位置字段说明：

- `poi_name` / `poi_address` 是平台返回的 POI 语义名称和地址，通常更适合用于人工核验、地点归类和研究分析。
- `location_lng` / `location_lat` 是平台接口返回的原始坐标。目前无法确认抖音/快手返回的坐标系，也无法稳定区分它是高德、百度或其他坐标体系。
- 因坐标系未知、平台 POI 代表点差异、地图服务商数据差异等原因，经纬度坐标可能与 `poi_name` / `poi_address` 对应的语义地点存在明显偏差。
- 当前建议：涉及内涝地点识别时，优先采用 `poi_name` 或 `poi_address` 作为地点依据；经纬度只作为平台原始辅助字段，不要直接当作真实灾害发生点。

不保存 `video_urls` / `image_urls`。这些直链经常带临时签名，容易 403/430，长期保存意义不大。后续下载视频/图片应基于 `post_url` 单独做下载模块。

## 常用参数

| 参数                      |         默认值 | 说明                                                              |
| ------------------------- | -------------: | ----------------------------------------------------------------- |
| `--platform`            |     `douyin` | `douyin` 或 `kuaishou`                                        |
| `--browser-channel`     |     `chrome` | `chrome` 或 `msedge`                                          |
| `--out-format`          |        `csv` | `csv`、`xlsx`、`both`                                       |
| `--start-date`          | `2020-01-01` | 开始日期                                                          |
| `--end-date`            |             空 | 结束日期，空表示不过滤结束时间                                    |
| `--locations`           |             空 | 地点词，如`"深圳"`                                              |
| `--location-mode`       |    `prepend` | `prepend (地点在前)`、`append(地点在后)`、`none (不拼地点)` |
| `--max-pages`           |         `15` | 每个关键词最多向下滚动几轮                                        |
| `--max-items`           |        `300` | 每个关键词最多保存多少条                                          |
| `--max-empty-pages`     |          `2` | 连续几轮没有新结果就停止当前关键词                                |
| `--max-responses`       |        `120` | 每个关键词最多处理多少个平台响应；耗尽后停止当前关键词            |
| `--max-seen-items`      |         `50` | 当前关键词连续遇到多少条已 seen 作品后提前停止                    |
| `--verify-retries`      |          `3` | 当前关键词最多人工验证次数                                        |
| `--verify-wait-seconds` |         `45` | 每次人工验证提示后至少等待秒数，低于 45 会按 45 处理              |
| `--min-sleep`           |          `4` | 最短随机等待秒数                                                  |
| `--max-sleep`           |         `10` | 最长随机等待秒数                                                  |
| `--no-resume`           |           关闭 | 忽略 seen 去重，排查时使用                                        |
| `--reset-state`         |           关闭 | 清空当前平台和关键词状态，谨慎使用                                |

## 账号风险

不能保证账号绝对安全，也不能保证不触发搜索受限。程序只能尽量降低风险：

- 固定账号、固定浏览器 profile、固定网络出口。
- 小批量、低频率运行，优先减少 `--max-pages` 和关键词数量。
- 出现验证、访问频繁、搜索异常时马上停，不要连续重试。
- `--max-responses` 是本地响应预算保护，不等于平台验证码；预算耗尽只会停止当前关键词。真正命中验证码、滑块、图形验证、人机验证、登录确认、访问频繁、403/429 等平台风险信号时，程序才会输出醒目的人工验证提示。
- 人工验证提示出现后，请到已连接的 Chrome/Edge 页面完成验证。程序默认每次至少等待 45 秒，然后回到终端按 Enter 重试当前关键词；如果验证后仍失败，会提示第 2 次、第 3 次人工验证，默认最多 3 次后跳过当前关键词。
- 不建议批量换代理；代理只适合作为稳定出口。
- 如果同名旧 CSV 还是旧字段，请自己删除后重新跑。

## 免责声明（请务必阅读）

### 1. 项目目的与性质

本项目仅用于**学术研究、论文写作与技术学习**目的，服务于**城市暴雨内涝/洪涝灾害风险分析**相关研究。项目输出数据仅用于研究过程中的方法验证、统计分析与可复现实验，不作为任何商业用途或实际业务决策依据。

### 2. 合规与责任

- 使用者应在使用本项目前，充分理解并严格遵守中华人民共和国相关法律法规，以及目标网站/平台的服务条款、隐私政策、robots 协议（如适用）与相关规则。
- 使用者应自行承担使用本项目所产生的一切后果与法律责任。项目作者/维护者不对使用者的任何行为承担责任。

### 3. 使用限制（严禁事项）

- 严禁将本项目用于任何**商业用途**、黑灰产用途或任何违法违规用途。
- 严禁对目标平台进行大规模、高频率、影响其正常运营的抓取行为。
- 严禁采集、传播、滥用涉及个人隐私、敏感信息或受法律保护的数据；如在数据中不可避免出现相关内容，应进行脱敏与合规处理。

### 4. 风控与账号提示

- 目标平台可能存在风控策略（封号、限流、验证码等）。建议使用者使用**小号**、合理降低频率、配置代理并严格控制并发与请求间隔。
- 因账号异常、数据缺失、接口变更导致的抓取失败属于正常情况；使用者应自行评估并承担相应风险。

### 5. 数据使用声明（学术研究）

本项目通过获取网络平台的公开数据，为写论文、做研究等**非商业项目**提供所需数据与技术验证；使用者应确保数据使用全过程满足合规与伦理要求，并仅在必要范围内保存与分析数据。
