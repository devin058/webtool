#!/usr/bin/env python3
"""Web 小工具集合 - 在线剪切板、Base64/URL 编解码、图片EXIF清除"""

import sqlite3
import string
import random
import os
import io
import json
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, g, send_file, send_from_directory

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.db')
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'files')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)

# ── 数据库 ──────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''CREATE TABLE IF NOT EXISTS pastes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            syntax TEXT DEFAULT 'plain',
            password TEXT DEFAULT '',
            burn_after INTEGER DEFAULT 0,
            expire_hours INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0,
            password TEXT DEFAULT '',
            burn_after INTEGER DEFAULT 0,
            expire_hours INTEGER DEFAULT 0,
            download_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            category TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            completed INTEGER DEFAULT 0,
            completed_at TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            todo_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (todo_id) REFERENCES todos(id) ON DELETE CASCADE
        )''')
        db.commit()

# ── 工具函数 ────────────────────────────────────────────

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def generate_code(length=6):
    chars = string.ascii_letters + string.digits
    while True:
        code = ''.join(random.choices(chars, k=length))
        db = get_db()
        if not db.execute("SELECT 1 FROM pastes WHERE code=? UNION ALL SELECT 1 FROM files WHERE code=?", (code, code)).fetchone():
            return code

def clean_expired():
    db = get_db()
    now_str = utcnow().isoformat()
    db.execute("DELETE FROM pastes WHERE expire_hours > 0 AND datetime(created_at, '+' || expire_hours || ' hours') < ?", (now_str,))
    db.execute("DELETE FROM files WHERE expire_hours > 0 AND datetime(created_at, '+' || expire_hours || ' hours') < ?", (now_str,))
    db.commit()

# ── 页面路由 ────────────────────────────────────────────

@app.route('/')
def index():
    tools = [
        {
            'id': 'netcut',
            'name': '在线剪切板',
            'desc': '文本暂存与分享 + 文件上传分享，支持密码保护、阅后即焚、过期时间',
            'icon': '📋',
            'color': '#6366f1',
        },
        {
            'id': 'encode',
            'name': '编解码工具',
            'desc': 'Base64 / URL / Hex / Unicode 编解码，一键切换',
            'icon': '🔐',
            'color': '#10b981',
        },
        {
            'id': 'exif',
            'name': '图片 EXIF 清除',
            'desc': '去除图片全部 EXIF / 元数据 / AI 隐藏水印，保护隐私',
            'icon': '🖼️',
            'color': '#f59e0b',
        },
        {
            'id': 'todo',
            'name': '待办清单',
            'desc': '功能丰富的 Todolist · 优先级/分类/截止日期/子任务/搜索/导出',
            'icon': '📝',
            'color': '#8b5cf6',
        },
    ]
    return render_template('index.html', tools=tools)

@app.route('/tool/netcut')
def tool_netcut():
    return render_template('netcut.html')

@app.route('/tool/encode')
def tool_encode():
    return render_template('encode.html')

@app.route('/tool/exif')
def tool_exif():
    return render_template('exif.html')

@app.route('/tool/todo')
def tool_todo():
    return render_template('todo.html')

# ── 剪切板 API ──────────────────────────────────────────

@app.route('/api/paste', methods=['POST'])
def create_paste():
    data = request.get_json()
    if not data or not data.get('content', '').strip():
        return jsonify({'error': '内容不能为空'}), 400

    content = data['content'].strip()
    if len(content) > 50000:
        return jsonify({'error': '内容过长，最多 50000 字'}), 400

    code = generate_code()
    db = get_db()
    db.execute('''INSERT INTO pastes (code, content, syntax, password, burn_after, expire_hours)
                  VALUES (?, ?, ?, ?, ?, ?)''',
               (code, content,
                data.get('syntax', 'plain'),
                data.get('password', ''),
                data.get('burn_after', 0),
                data.get('expire_hours', 0)))
    db.commit()

    return jsonify({'code': code, 'url': f'/p/{code}'})

@app.route('/p/<code>')
def view_paste(code):
    clean_expired()
    db = get_db()
    paste = db.execute("SELECT * FROM pastes WHERE code=?", (code,)).fetchone()
    if not paste:
        return render_template('view.html', error='内容不存在或已过期'), 404

    paste = dict(paste)
    if paste['password']:
        return render_template('view.html', code=code, need_password=True)

    if paste['burn_after']:
        db.execute("DELETE FROM pastes WHERE code=?", (code,))
        db.commit()

    db.execute("UPDATE pastes SET view_count = view_count + 1 WHERE code=?", (code,))
    db.commit()

    return render_template('view.html', paste=paste)

@app.route('/api/paste/<code>', methods=['POST'])
def unlock_paste(code):
    db = get_db()
    paste = db.execute("SELECT * FROM pastes WHERE code=?", (code,)).fetchone()
    if not paste:
        return jsonify({'error': '内容不存在'}), 404

    paste = dict(paste)
    data = request.get_json()
    if data.get('password') != paste['password']:
        return jsonify({'error': '密码错误'}), 403

    if paste['burn_after']:
        db.execute("DELETE FROM pastes WHERE code=?", (code,))
        db.commit()

    db.execute("UPDATE pastes SET view_count = view_count + 1 WHERE code=?", (code,))
    db.commit()

    return jsonify({'content': paste['content'], 'syntax': paste['syntax']})

# ── 文件上传 API ────────────────────────────────────────

ALLOWED_EXTENSIONS = {
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg',
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'zip', 'rar', '7z', 'tar', 'gz',
    'mp3', 'mp4', 'avi', 'mov', 'mkv',
    'py', 'js', 'html', 'css', 'json', 'xml', 'yaml', 'yml',
    'csv', 'log', 'md', 'c', 'cpp', 'java', 'go', 'rs',
}

@app.route('/api/file/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '请选择文件'}), 400

    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': '请选择文件'}), 400

    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件类型: .{ext}'}), 400

    code = generate_code()
    save_name = f"{code}_{f.filename}"
    save_path = os.path.join(FILES_DIR, save_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)

    db = get_db()
    db.execute('''INSERT INTO files (code, filename, original_name, file_size, password, burn_after, expire_hours)
                  VALUES (?, ?, ?, ?, ?, ?, ?)''',
               (code, save_name, f.filename, file_size,
                request.form.get('password', ''),
                int(request.form.get('burn_after', 0)),
                int(request.form.get('expire_hours', 0))))
    db.commit()

    return jsonify({'code': code, 'url': f'/f/{code}', 'filename': f.filename, 'size': file_size})

@app.route('/f/<code>')
def view_file(code):
    clean_expired()
    db = get_db()
    f = db.execute("SELECT * FROM files WHERE code=?", (code,)).fetchone()
    if not f:
        return render_template('view_file.html', error='文件不存在或已过期'), 404

    f = dict(f)
    file_path = os.path.join(FILES_DIR, f['filename'])
    if not os.path.exists(file_path):
        return render_template('view_file.html', error='文件已被删除'), 404

    if f['password']:
        return render_template('view_file.html', code=code, need_password=True, file=f)

    if f['burn_after']:
        db.execute("DELETE FROM files WHERE code=?", (code,))
        db.commit()
        # 文件将在下载后删除

    db.execute("UPDATE files SET download_count = download_count + 1 WHERE code=?", (code,))
    db.commit()

    return send_from_directory(FILES_DIR, f['filename'], as_attachment=True, download_name=f['original_name'])

@app.route('/api/file/<code>', methods=['POST'])
def unlock_file(code):
    db = get_db()
    f = db.execute("SELECT * FROM files WHERE code=?", (code,)).fetchone()
    if not f:
        return jsonify({'error': '文件不存在'}), 404

    f = dict(f)
    data = request.get_json()
    if data.get('password') != f['password']:
        return jsonify({'error': '密码错误'}), 403

    if f['burn_after']:
        db.execute("DELETE FROM files WHERE code=?", (code,))
        db.commit()

    db.execute("UPDATE files SET download_count = download_count + 1 WHERE code=?", (code,))
    db.commit()

    return jsonify({'url': f'/f/{code}/download'})

@app.route('/f/<code>/download')
def download_file(code):
    db = get_db()
    f = db.execute("SELECT * FROM files WHERE code=?", (code,)).fetchone()
    if not f:
        return jsonify({'error': '文件不存在'}), 404

    f = dict(f)
    file_path = os.path.join(FILES_DIR, f['filename'])
    if not os.path.exists(file_path):
        return jsonify({'error': '文件已被删除'}), 404

    return send_from_directory(FILES_DIR, f['filename'], as_attachment=True, download_name=f['original_name'])

# ── EXIF 清除 API ───────────────────────────────────────

@app.route('/api/exif/clean', methods=['POST'])
def clean_exif():
    if 'image' not in request.files:
        return jsonify({'error': '请选择图片文件'}), 400

    f = request.files['image']
    if f.filename == '':
        return jsonify({'error': '请选择图片文件'}), 400

    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else 'png'
    if ext not in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 'tif'):
        return jsonify({'error': f'不支持的图片格式: .{ext}'}), 400

    try:
        from PIL import Image
        import struct

        img = Image.open(f.stream)
        original_format = img.format
        original_mode = img.mode

        # 提取纯像素数据（去掉所有元数据）
        if original_mode in ('RGBA', 'LA', 'P', 'PA'):
            # 保持透明度
            if original_mode == 'P':
                img = img.convert('RGBA')
            data = list(img.getdata())
            new_img = Image.new(img.mode, img.size)
            new_img.putdata(data)
        else:
            data = list(img.getdata())
            new_img = Image.new('RGB', img.size)
            new_img.putdata(data)

        # 保存到内存
        output = io.BytesIO()
        save_format = 'JPEG' if ext in ('jpg', 'jpeg') else ext.upper()
        if save_format == 'JPEG':
            new_img = new_img.convert('RGB')
            new_img.save(output, format='JPEG', quality=95, exif=b'', optimize=True)
        elif save_format == 'PNG':
            # PNG: 不保存任何元数据块
            new_img.save(output, format='PNG', optimize=True,
                        pnginfo=None)  # 不使用原图的 pnginfo
        elif save_format == 'WEBP':
            new_img.save(output, format='WEBP', quality=95, exif=b'')
        else:
            new_img.save(output, format=save_format, optimize=True)

        output.seek(0)

        # 二次处理: 用纯二进制方式清除 PNG 隐藏水印（AI 模型常嵌入在 tEXt/iTXt/zTXt 块中）
        if save_format == 'PNG':
            output = _strip_png_chunks(output)
        elif save_format == 'JPEG':
            output = _strip_jpeg_markers(output)

        output.seek(0)
        original_size = os.fstat(f.stream.fileno()).st_size if hasattr(f.stream, 'fileno') else 0
        cleaned_size = output.getbuffer().nbytes

        return send_file(
            output,
            mimetype=f'image/{("jpeg" if save_format == "JPEG" else save_format.lower())}',
            as_attachment=True,
            download_name=f"cleaned_{f.filename}"
        )

    except Exception as e:
        return jsonify({'error': f'处理失败: {str(e)}'}), 500


def _strip_png_chunks(buf):
    """从PNG文件中移除所有辅助chunk（tEXt, iTXt, zTXt, tIME等），只保留关键chunk。
    这会去掉 AI 模型（DALL-E, Midjourney, SD, Gemini）嵌入的隐藏水印。"""
    buf.seek(0)
    data = buf.read()

    # PNG 签名
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        buf.seek(0)
        return buf

    result = [data[:8]]  # 保留 PNG 签名
    pos = 8

    # 关键 chunk 白名单
    CRITICAL = {b'IHDR', b'PLTE', b'IDAT', b'IEND', b'cHRM', b'gAMA', b'iCCP',
                 b'sBIT', b'sRGB', b'bKGD', b'hIST', b'tRNS', b'pHYs', b'sPLT'}
    # 也保留 sRGB, gAMA, cHRM 等颜色相关 chunk 以保证正确显示

    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = int.from_bytes(data[pos:pos+4], 'big')
        chunk_type = data[pos+4:pos+8]
        chunk_end = pos + 12 + length

        if chunk_end > len(data):
            break

        if chunk_type in CRITICAL:
            result.append(data[pos:chunk_end])

        pos = chunk_end

    output = io.BytesIO()
    output.write(b''.join(result))
    output.seek(0)
    return output


def _strip_jpeg_markers(buf):
    """从JPEG中移除所有APP标记段（EXIF, IPTC, XMP, ICC等）以及Comment段。
    这也会去掉 AI 模型嵌入在 EXIF/Comment 中的水印信息。"""
    buf.seek(0)
    data = buf.read()

    if data[:2] != b'\xff\xd8':
        buf.seek(0)
        return buf

    result = [data[:2]]  # SOI
    pos = 2

    # 保留的标记
    KEEP = {0xDB, 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
            0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF,  # SOF/DHT
            0xDA, 0xD9,  # SOS, EOI
            0xDD,  # DRI
            0xFE,  # COM (comment) - 也移除
            }

    while pos < len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        if pos + 1 >= len(data):
            break
        marker = data[pos + 1]

        if marker == 0xD9:  # EOI
            result.append(data[pos:pos+2])
            break
        if marker == 0x00 or marker == 0xFF:  # 填充字节
            result.append(data[pos:pos+1])
            pos += 1
            continue
        if 0xD0 <= marker <= 0xD7:  # RST0-RST7 重启标记（无长度字段，仅2字节）
            result.append(data[pos:pos+2])
            pos += 2
            continue
        if marker == 0xDA:  # SOS - 扫描数据开始（包含实际压缩图像数据）
            sos_start = pos
            pos += 2
            # 跳过扫描数据直到下一个标记
            while pos < len(data):
                if data[pos] == 0xFF and pos + 1 < len(data) and data[pos+1] != 0x00:
                    break
                pos += 1
            # 保留 SOS 标记 + 扫描数据（压缩图像内容）到下一个标记之前
            result.append(data[sos_start:pos])
            continue

        # 读取段长度
        if pos + 4 > len(data):
            break
        seg_len = int.from_bytes(data[pos+2:pos+4], 'big')

        if marker in (0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF):
            # APP0-APP15: 跳过（包含 EXIF, XMP, ICC, Photoshop 等）
            pos += 2 + seg_len
        elif marker == 0xFE:  # COM (comment)
            pos += 2 + seg_len
        elif marker in KEEP and marker not in (0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xFE):
            result.append(data[pos:pos+2+seg_len])
            pos += 2 + seg_len
        else:
            pos += 2 + seg_len

    output = io.BytesIO()
    output.write(b''.join(result))
    output.seek(0)
    return output


# ── Todo API ─────────────────────────────────────────────

def _todo_row(todo):
    """将 sqlite Row 转为 dict，并附带子任务"""
    db = get_db()
    subs = db.execute(
        "SELECT * FROM subtasks WHERE todo_id=? ORDER BY sort_order, id",
        (todo['id'],)
    ).fetchall()
    t = dict(todo)
    t['subtasks'] = [dict(s) for s in subs]
    # 计算逾期
    t['overdue'] = False
    if t['due_date'] and not t['completed']:
        today = datetime.now().strftime('%Y-%m-%d')
        if t['due_date'] < today:
            t['overdue'] = True
    return t


@app.route('/api/todos', methods=['GET', 'POST'])
def api_todos():
    if request.method == 'GET':
        db = get_db()
        params = request.args

        where = []
        vals = []

        # 状态筛选
        status = params.get('status', 'all')
        if status == 'active':
            where.append("completed = 0")
        elif status == 'done':
            where.append("completed = 1")

        # 优先级筛选
        priority = params.get('priority', '')
        if priority and priority in ('high', 'medium', 'low'):
            where.append("priority = ?")
            vals.append(priority)

        # 分类筛选
        category = params.get('category', '')
        if category:
            where.append("category = ?")
            vals.append(category)

        # 搜索
        search = params.get('search', '')
        if search:
            where.append("(title LIKE ? OR description LIKE ?)")
            vals.extend([f'%{search}%', f'%{search}%'])

        where_clause = ('WHERE ' + ' AND '.join(where)) if where else ''

        # 排序
        sort = params.get('sort', 'created_desc')
        sort_map = {
            'created_desc': 'created_at DESC',
            'created_asc': 'created_at ASC',
            'priority_desc': "CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 END",
            'priority_asc': "CASE priority WHEN 'low' THEN 0 WHEN 'medium' THEN 1 WHEN 'high' THEN 2 END",
            'due_asc': "CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date ASC",
            'due_desc': "CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date DESC",
            'title_asc': 'title COLLATE NOCASE ASC',
            'title_desc': 'title COLLATE NOCASE DESC',
        }
        order = sort_map.get(sort, 'created_at DESC')

        sql = f"SELECT * FROM todos {where_clause} ORDER BY {order}"
        todos = db.execute(sql, vals).fetchall()
        return jsonify([_todo_row(t) for t in todos])

    elif request.method == 'POST':
        data = request.get_json()
        if not data or not data.get('title', '').strip():
            return jsonify({'error': '标题不能为空'}), 400

        title = data['title'].strip()
        if len(title) > 500:
            return jsonify({'error': '标题过长'}), 400

        db = get_db()
        # 获取最大 sort_order
        max_order = db.execute("SELECT COALESCE(MAX(sort_order), -1) FROM todos").fetchone()[0]
        cursor = db.execute(
            """INSERT INTO todos (title, description, priority, category, due_date, sort_order)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title,
             data.get('description', '').strip(),
             data.get('priority', 'medium'),
             data.get('category', '').strip(),
             data.get('due_date', ''),
             max_order + 1)
        )
        db.commit()
        todo = db.execute("SELECT * FROM todos WHERE id=?", (cursor.lastrowid,)).fetchone()
        return jsonify(_todo_row(todo)), 201


@app.route('/api/todos/<int:todo_id>', methods=['PUT', 'DELETE'])
def api_todo_single(todo_id):
    db = get_db()
    todo = db.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
    if not todo:
        return jsonify({'error': '任务不存在'}), 404

    if request.method == 'PUT':
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效数据'}), 400

        title = data.get('title', todo['title']).strip()
        if not title:
            return jsonify({'error': '标题不能为空'}), 400

        db.execute(
            """UPDATE todos SET title=?, description=?, priority=?, category=?,
               due_date=?, sort_order=?, updated_at=datetime('now')
               WHERE id=?""",
            (title,
             data.get('description', todo['description']).strip(),
             data.get('priority', todo['priority']),
             data.get('category', todo['category']).strip(),
             data.get('due_date', todo['due_date']),
             data.get('sort_order', todo['sort_order']),
             todo_id)
        )
        db.commit()
        todo = db.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
        return jsonify(_todo_row(todo))

    elif request.method == 'DELETE':
        db.execute("DELETE FROM subtasks WHERE todo_id=?", (todo_id,))
        db.execute("DELETE FROM todos WHERE id=?", (todo_id,))
        db.commit()
        return jsonify({'ok': True})


@app.route('/api/todos/<int:todo_id>/toggle', methods=['PATCH'])
def api_todo_toggle(todo_id):
    db = get_db()
    todo = db.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
    if not todo:
        return jsonify({'error': '任务不存在'}), 404

    new_val = 0 if todo['completed'] else 1
    completed_at = datetime.now().isoformat() if new_val else ''
    db.execute(
        "UPDATE todos SET completed=?, completed_at=?, updated_at=datetime('now') WHERE id=?",
        (new_val, completed_at, todo_id)
    )
    db.commit()
    todo = db.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
    return jsonify(_todo_row(todo))


@app.route('/api/todos/bulk/completed', methods=['DELETE'])
def api_todos_bulk_delete_completed():
    db = get_db()
    db.execute("DELETE FROM subtasks WHERE todo_id IN (SELECT id FROM todos WHERE completed=1)")
    db.execute("DELETE FROM todos WHERE completed=1")
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/todos/stats')
def api_todos_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM todos").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM todos WHERE completed=0").fetchone()[0]
    done = db.execute("SELECT COUNT(*) FROM todos WHERE completed=1").fetchone()[0]
    today = datetime.now().strftime('%Y-%m-%d')
    overdue = db.execute(
        "SELECT COUNT(*) FROM todos WHERE completed=0 AND due_date != '' AND due_date < ?",
        (today,)
    ).fetchone()[0]
    return jsonify({'total': total, 'active': active, 'done': done, 'overdue': overdue})


@app.route('/api/todos/export')
def api_todos_export():
    db = get_db()
    todos = db.execute("SELECT * FROM todos ORDER BY sort_order, id").fetchall()
    data = []
    for t in todos:
        subs = db.execute(
            "SELECT * FROM subtasks WHERE todo_id=? ORDER BY sort_order, id",
            (t['id'],)
        ).fetchall()
        item = dict(t)
        item['subtasks'] = [dict(s) for s in subs]
        data.append(item)
    return jsonify({'version': 1, 'exported_at': datetime.now().isoformat(), 'todos': data})


@app.route('/api/todos/import', methods=['POST'])
def api_todos_import():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': '请选择文件'}), 400

    try:
        content = file.read().decode('utf-8')
        import_data = json.loads(content)
        items = import_data.get('todos', [])
    except Exception:
        return jsonify({'error': 'JSON 格式无效'}), 400

    db = get_db()
    max_order = db.execute("SELECT COALESCE(MAX(sort_order), -1) FROM todos").fetchone()[0]
    imported = 0

    for item in items:
        title = item.get('title', '').strip()
        if not title:
            continue
        max_order += 1
        cursor = db.execute(
            """INSERT INTO todos (title, description, priority, category, due_date,
               completed, completed_at, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title,
             item.get('description', '').strip(),
             item.get('priority', 'medium'),
             item.get('category', '').strip(),
             item.get('due_date', ''),
             item.get('completed', 0),
             item.get('completed_at', ''),
             max_order)
        )
        todo_id = cursor.lastrowid
        for si, sub in enumerate(item.get('subtasks', [])):
            if sub.get('title', '').strip():
                db.execute(
                    "INSERT INTO subtasks (todo_id, title, completed, sort_order) VALUES (?, ?, ?, ?)",
                    (todo_id, sub['title'].strip(), sub.get('completed', 0), si)
                )
        imported += 1

    db.commit()
    return jsonify({'ok': True, 'imported': imported})


# ── 子任务 API ──────────────────────────────────────────

@app.route('/api/todos/<int:todo_id>/subtasks', methods=['POST'])
def api_subtask_create(todo_id):
    db = get_db()
    todo = db.execute("SELECT * FROM todos WHERE id=?", (todo_id,)).fetchone()
    if not todo:
        return jsonify({'error': '任务不存在'}), 404

    data = request.get_json()
    if not data or not data.get('title', '').strip():
        return jsonify({'error': '子任务标题不能为空'}), 400

    title = data['title'].strip()
    max_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM subtasks WHERE todo_id=?",
        (todo_id,)
    ).fetchone()[0]

    cursor = db.execute(
        "INSERT INTO subtasks (todo_id, title, sort_order) VALUES (?, ?, ?)",
        (todo_id, title, max_order + 1)
    )
    db.commit()
    sub = db.execute("SELECT * FROM subtasks WHERE id=?", (cursor.lastrowid,)).fetchone()
    return jsonify(dict(sub)), 201


@app.route('/api/subtasks/<int:sub_id>', methods=['PUT', 'DELETE'])
def api_subtask_single(sub_id):
    db = get_db()
    sub = db.execute("SELECT * FROM subtasks WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return jsonify({'error': '子任务不存在'}), 404

    if request.method == 'PUT':
        data = request.get_json()
        if not data or not data.get('title', '').strip():
            return jsonify({'error': '标题不能为空'}), 400
        db.execute("UPDATE subtasks SET title=? WHERE id=?", (data['title'].strip(), sub_id))
        db.commit()
        sub = db.execute("SELECT * FROM subtasks WHERE id=?", (sub_id,)).fetchone()
        return jsonify(dict(sub))

    elif request.method == 'DELETE':
        db.execute("DELETE FROM subtasks WHERE id=?", (sub_id,))
        db.commit()
        return jsonify({'ok': True})


@app.route('/api/subtasks/<int:sub_id>/toggle', methods=['PATCH'])
def api_subtask_toggle(sub_id):
    db = get_db()
    sub = db.execute("SELECT * FROM subtasks WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return jsonify({'error': '子任务不存在'}), 404

    new_val = 0 if sub['completed'] else 1
    db.execute("UPDATE subtasks SET completed=? WHERE id=?", (new_val, sub_id))
    db.commit()
    sub = db.execute("SELECT * FROM subtasks WHERE id=?", (sub_id,)).fetchone()
    return jsonify(dict(sub))


# ── 启动 ────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    init_db()
    print("=" * 50)
    print("  Web 小工具集合 已启动")
    print("  地址: http://0.0.0.0:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)