from flask import Flask, jsonify, send_from_directory, send_file, request
import sqlite3
import os
import threading
from datetime import datetime, timedelta
import json
import time

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "lost_and_found.db")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# 确保目录存在
os.makedirs(IMAGES_DIR, exist_ok=True)

# 读取配置文件
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)

FACE_DB_PATH = config.get('FACE_DB_PATH', 'face_db_v4.json')
if not os.path.isabs(FACE_DB_PATH):
    FACE_DB_PATH = os.path.join(BASE_DIR, FACE_DB_PATH)
MAX_FACE_IMAGE_BYTES = int(config.get('MAX_FACE_IMAGE_BYTES', 8388608))

_face_recognition_service = None
_face_recognition_lock = threading.Lock()


def get_face_recognition_service():
    """Create the model on the first request so other server APIs remain available."""
    global _face_recognition_service
    if _face_recognition_service is None:
        with _face_recognition_lock:
            if _face_recognition_service is None:
                from face_recognize import FaceRecognitionService

                _face_recognition_service = FaceRecognitionService(
                    FACE_DB_PATH,
                    similarity_threshold=config.get('FACE_SIMILARITY_THRESHOLD', 0.35),
                )
    return _face_recognition_service


# ---------- 数据库初始化（若没有则创建） ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS item_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_time TEXT NOT NULL,
            terminal_id TEXT NOT NULL,
            photo_name TEXT NOT NULL,
            locker_id INTEGER NOT NULL,
            take_time TEXT,
            taker_name TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS terminals (
            terminal_id TEXT UNIQUE NOT NULL,   -- 终端唯一标识（如设备序列号）
            location TEXT NOT NULL,             -- 终端位置描述
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------- 清理功能 ----------
def cleanup_old_records():
    """删除已取且超过清理天数的记录及照片"""
    days = config.get('CLEANUP_DAYS')
    threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    print(f"执行清理：删除取物时间早于 {threshold} 的记录")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. 获取待删除记录的 photo_name
    c.execute("SELECT photo_name FROM item_records WHERE take_time IS NOT NULL AND take_time < ?", (threshold,))
    photos = [row[0] for row in c.fetchall()]

    # 2. 删除记录
    c.execute("DELETE FROM item_records WHERE take_time IS NOT NULL AND take_time < ?", (threshold,))
    deleted_count = c.rowcount
    conn.commit()
    conn.close()

    # 3. 删除对应的照片文件
    for photo_name in photos:
        if photo_name:
            photo_path = os.path.join(IMAGES_DIR, photo_name)
            try:
                if os.path.exists(photo_path):
                    os.remove(photo_path)
            except Exception as e:
                print(f"删除照片失败 {photo_path}: {e}")

    print(f"清理完成，删除了 {deleted_count} 条记录和 {len(photos)} 张照片")

def cleanup_loop():
    """循环执行清理（每日一次）"""
    while True:
        cleanup_old_records()
        # 等待 24 小时
        time.sleep(24 * 3600)

def start_cleanup_thread():
    """启动清理后台线程"""
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    print("清理任务已启动（每天执行一次）")

# ---------- 网页路由（保持不变） ----------
@app.route('/')
def index():
    return send_file("webUI0.02.html")

@app.route('/get_data')
def get_data():
    """供网页前端获取所有记录（含已取）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM item_records ORDER BY id DESC")
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    data = [dict(zip(columns, row)) for row in rows]
    return jsonify(data)

@app.route('/images/<filename>')
def get_image(filename):
    """供网页和客户端下载照片"""
    return send_from_directory(IMAGES_DIR, filename)

# ---------- 新增：客户端 API 接口 ----------
@app.route('/api/lockers', methods=['GET'])
def api_get_lockers():
    terminal_id = request.args.get('terminal_id')
    if not terminal_id:
        return jsonify({'error': '缺少 terminal_id'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 查询每个柜子当前是否有未取记录
    cursor.execute('''
        SELECT locker_id, terminal_id, photo_name
        FROM item_records
        WHERE take_time IS NULL AND terminal_id=?
    ''', (terminal_id,))
    rows = cursor.fetchall()
    conn.close()

    # 构建返回数据：8个柜子，status 0=空闲，1=已用
    lockers = {i: {'status': 0, 'terminal_id': None, 'photo_name': None} for i in range(1, 9)}
    for locker_id, terminal_id, photo_name in rows:
        if locker_id in lockers:
            lockers[locker_id]['status'] = 1
            lockers[locker_id]['terminal_id'] = terminal_id
            lockers[locker_id]['photo_name'] = photo_name
    return jsonify(lockers)

@app.route('/api/store', methods=['POST'])
def api_store():
    """存物：接收照片和数据，保存到服务端，图片文件名=记录ID"""
    terminal_id = request.form.get('terminal_id')
    locker_id = request.form.get('locker_id')
    photo = request.files.get('photo')

    if not all([terminal_id, locker_id, photo]):
        return jsonify({'error': '缺少必要参数'}), 400

    # 1. 先保存照片到一个临时文件名（避免重复）
    temp_photo_name = f"temp_{locker_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
    temp_photo_path = os.path.join(IMAGES_DIR, temp_photo_name)
    photo.save(temp_photo_path)

    # 2. 插入数据库记录，photo_name 先用临时文件名占位
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO item_records (store_time, terminal_id, photo_name, locker_id) VALUES (datetime('now', 'localtime'), ?, ?, ?)",
        (terminal_id, temp_photo_name, locker_id)
    )
    record_id = c.lastrowid  # 获取自增ID
    conn.commit()
    conn.close()

    # 3. 用记录ID重命名照片文件
    final_photo_name = f"{record_id}.jpg"
    final_photo_path = os.path.join(IMAGES_DIR, final_photo_name)
    os.rename(temp_photo_path, final_photo_path)

    # 4. 更新数据库中的 photo_name 为最终文件名
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE item_records SET photo_name = ? WHERE id = ?",
        (final_photo_name, record_id)
    )
    conn.commit()
    conn.close()

    return jsonify({'message': '存放成功', 'photo_name': final_photo_name, 'id': record_id}), 200

@app.route('/api/take', methods=['POST'])
def api_take():
    """取物：更新记录，标记已取"""
    data = request.get_json()
    terminal_id = data.get('terminal_id')
    locker_id = data.get('locker_id')
    taker_name = data.get('taker_name')

    if not all([terminal_id, locker_id, taker_name]):
        return jsonify({'error': '缺少必要参数'}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 更新该柜子最近一条未取记录（假设同一柜子不会同时有两个未取物品）
    c.execute(
        "UPDATE item_records SET take_time = datetime('now', 'localtime'), taker_name = ? WHERE locker_id = ? AND take_time IS NULL AND terminal_id = ?",
        (taker_name, locker_id, terminal_id)
    )
    affected = c.rowcount
    conn.commit()
    conn.close()

    if affected == 0:
        return jsonify({'error': '该柜子没有可取的物品'}), 404
    return jsonify({'message': '取物成功'}), 200

@app.route('/api/register', methods=['POST'])
def api_register():
    """终端信息更新"""
    data = request.get_json()
    terminal_id = data.get('terminal_id')
    location = data.get('location')

    if not terminal_id:
        return jsonify({'error': '缺少 terminal_id'}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        INSERT INTO terminals (terminal_id, location, created_at) VALUES (?, ?, datetime('now', 'localtime'))
        ON CONFLICT(terminal_id) DO UPDATE SET location = excluded.location
    ''', (terminal_id, location))
    conn.commit()
    conn.close()

    return jsonify({
        'message': '终端同步成功',
        'terminal_id': terminal_id,
        'location': location
    }), 200


@app.route('/api/face-recognize', methods=['POST'])
def api_face_recognize():
    """Recognize a camera frame using the server's private face database."""
    image = request.files.get('image')
    if image is None or not image.filename:
        return jsonify({'error': '缺少图片参数 image'}), 400

    image_bytes = image.stream.read(MAX_FACE_IMAGE_BYTES + 1)
    if len(image_bytes) > MAX_FACE_IMAGE_BYTES:
        return jsonify({'error': '图片过大'}), 413

    try:
        service = get_face_recognition_service()
    except FileNotFoundError:
        return jsonify({'error': '服务器人脸库未配置'}), 503
    except Exception:
        app.logger.exception('无法初始化人脸识别服务')
        return jsonify({'error': '服务器人脸识别服务未就绪'}), 503

    try:
        name = service.recognize(image_bytes)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception:
        app.logger.exception('处理人脸图片失败')
        return jsonify({'error': '服务器处理人脸图片失败'}), 500

    return jsonify({'recognized': name is not None, 'name': name}), 200

# ---------- 启动服务 ----------
if __name__ == '__main__':
    # 启动清理后台线程
    start_cleanup_thread()
    # 启动 Flask 应用
    app.run(host=config.get('SERVER_HOST'), port=config.get('SERVER_PORT'), ssl_context=('cert.pem', 'key.pem'), debug=True)  # 生产环境建议关闭 debug
