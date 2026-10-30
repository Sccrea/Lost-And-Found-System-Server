# Lost-And-Found-System-Server

失物招领系统服务端，使用Python语言编写。

## 运行与调试
使用 **Python 3.11 或更新版本**。服务端依赖 InsightFace 和 ONNX Runtime。

**运行server.py以启动**

安装依赖:

```bash
pip install -r requirements.txt
```

或使用国内清华大学镜像源安装:

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

[WinSCP与DB Browser for SQLite下载](https://wwbwa.lanzoue.com/ipOoc3mlazpc)

## 人脸识别部署

客户端把摄像头画面发送到本服务端，由服务端运行 InsightFace `buffalo_l` 模型并读取人脸库进行比对。摄像头仍连接在客户端终端上。InsightFace 提供的预训练模型仅限非商业研究用途；如用于商业场景，请先确认并取得所需授权。

1. 安装 `requirements.txt` 中的依赖。首次调用人脸识别接口时，InsightFace 可能会下载 `buffalo_l` 模型；请确保服务器能访问模型下载源，或提前配置好模型缓存。
2. 把客户端原有的 `face_db_v4.json` 安全地复制到服务端项目根目录。该文件包含姓名和人脸特征，已加入 `.gitignore`，不要将其提交到公开 Git 仓库。
3. 默认数据库文件名是 `face_db_v4.json`。如需改名或放到其他位置，可修改 `config.json` 的 `FACE_DB_PATH`。
4. 在客户端 `files/config.json` 设置 `AUTH_METHOD` 为 `1`，并把 `SERVER_URL` 改成这台服务器可访问的 HTTPS 地址。

人脸库格式需与旧客户端脚本兼容，例如每条记录包含 `name` 和 `features` 字段：

```json
{
    "用户记录编号": {
        "name": "用户姓名",
        "features": [0.1, 0.2]
    }
}
```

上面的特征数组仅用于说明文件结构，不能直接用于识别。服务器使用 CPU 执行推理；接口不会把上传的摄像头画面写入磁盘。缺少人脸库时，接口返回 `503`，不会自动开放注册。

## 函数意义解释
以下是失物招领管理系统客户端中所有函数的意义解释，按模块划分。(部分内容已过时，仅供参考)(更新时间: 2026年8月5日 3:30)

1. [server.py (服务端主程序)](#1-serverpy-服务端主程序)
2. [config.json (配置文件)](#2-configjson-配置文件) 

---

### 1. server.py (服务端主程序)

Flask Web 服务端，提供 REST API，管理数据库和照片存储。

#### 全局常量与初始化

| 变量名 | 意义 |
|--------|------|
| `BASE_DIR` | `server.py` 所在目录。 |
| `DB_PATH` | SQLite 数据库文件路径（`lost_and_found.db`）。 |
| `IMAGES_DIR` | 存储照片的目录。 |
| `CONFIG_PATH` | `config.json` 文件路径。 |
| `config` | 从 `config.json` 加载的配置字典。 |

服务启动时会调用 `init_db()` 创建数据表，并启动清理后台线程。

#### 数据库初始化函数

| 函数名 | 参数 | 返回值 | 意义 |
|--------|------|--------|------|
| `init_db()` | 无 | 无 | 创建 `item_records` 和 `terminals` 表（若不存在）。 |

#### 清理相关函数（后台线程）

| 函数名 | 参数 | 返回值 | 意义 |
|--------|------|--------|------|
| `cleanup_old_records()` | 无 | 无 | 删除 `take_time` 早于（当前时间 - `CLEANUP_DAYS` 天）的记录，并删除对应的照片文件。打印删除数量。 |
| `cleanup_loop()` | 无 | 无 | 无限循环，每隔 24 小时执行一次 `cleanup_old_records()`。 |
| `start_cleanup_thread()` | 无 | 无 | 以守护线程方式启动 `cleanup_loop()`。 |

#### Flask 路由（HTTP 端点）

| 路由 | 方法 | 参数（通过 request） | 返回值 | 意义 |
|------|------|----------------------|--------|------|
| `/` | GET | 无 | `webUI0.02.html` 页面 | 提供网页管理界面（旧版，可能用于调试）。 |
| `/get_data` | GET | 无 | JSON（所有记录列表） | 供前端获取全部存取记录。 |
| `/images/<filename>` | GET | `filename`：照片文件名 | 照片文件 | 供客户端下载照片。 |
| `/api/lockers` | GET | Query: `terminal_id` | JSON（柜子状态字典） | 根据 `terminal_id` 返回该终端下 1‑8 号柜的占用状态（`status`、`terminal_id`、`photo_name`）。 |
| `/api/store` | POST | Form: `terminal_id`, `locker_id`, `photo` (文件) | JSON（含 `message`, `photo_name`, `id`） | 接收照片和柜号，保存照片（以记录 ID 命名），插入数据库记录，返回成功信息。 |
| `/api/take` | POST | JSON: `terminal_id`, `locker_id`, `taker_name` | JSON（含 `message`） | 更新对应柜子最近一条未取记录，填入取物时间和取物人。 |
| `/api/register` | POST | JSON: `terminal_id`, `location` | JSON（含 `message`, `terminal_id`, `location`） | 插入或更新 `terminals` 表中的终端信息。 |
| `/api/face-recognize` | POST | Form: `image` (JPEG 文件) | JSON: `recognized`, `name` | 在服务端运行模型并与私有人脸库匹配，不保存上传的图片。 |

> **注意**：服务端以 HTTPS 运行（`ssl_context=('cert.pem', 'key.pem')`），且启用 `debug=True`（生产环境建议关闭）。

---

### 2. config.json (配置文件)

`config.json` 位于服务端根目录，用于控制服务端行为。

| 字段 | 类型 | 意义 |
|------|------|------|
| `CLEANUP_DAYS` | int | 自动清理天数：已取物品记录保留 `CLEANUP_DAYS` 天后将被删除（连同照片）。默认 127。 |
| `SERVER_HOST` | str | Flask 服务绑定的 IP 地址，`"0.0.0.0"` 表示监听所有网络接口。 |
| `SERVER_PORT` | int | Flask 服务监听的端口号，默认 5000。 |

---
