# Web Tool

A lightweight collection of web-based utility tools built with Flask. No registration required, all data stored locally.

## Tools

| Tool | Description |
|------|-------------|
| Online Clipboard | Username-based workspace for text & file sharing with password protection, QR codes, and collaborative editing |
| Encode/Decode | Base64 / URL / Hex / Unicode encoding and decoding |
| Image EXIF Cleaner | Strip all EXIF/metadata/AI watermarks from images |
| Todo List | Feature-rich task manager with priorities, categories, due dates, subtasks, search, and export |

## Quick Start

### Requirements

- Python 3.9+
- pip

### Installation

```bash
cd claude_code_test
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## Online Clipboard

### How It Works
1. Go to **/tool/netcut** → enter a **username** + optional password → creates your workspace
2. Your workspace lives at **/u/your-username** — this is your editing page AND share page
3. Share the link. Others can view and download. If you set a password, they enter it to gain access — including editing rights.
4. The same page handles everything: create text pastes, upload files, delete items, set/change password, generate QR codes.

### Features
- **Username-based workspace** — one link shares everything, not per-item codes
- **Password protection** — optional workspace password; anyone with the password can view AND edit
- **QR code generation** — every item and workspace has a QR code button for easy mobile sharing
- **Text sharing** — paste any text (code, Markdown, etc.) with optional burn-after-reading, expiry, and per-item password
- **File sharing** — upload files up to 50MB in 30+ formats, same protection options
- **Auto-login** — localStorage remembers your workspace; revisit /tool/netcut to jump straight back
- **Collaborative** — password holders can create, upload, and delete items too

### URL Structure

| URL | Purpose |
|-----|---------|
| `/tool/netcut` | Login / create workspace (auto-redirects if remembered) |
| `/u/<username>` | Workspace page — view + edit + share |
| `/u/<username>/p/<id>` | View a specific text paste |
| `/u/<username>/f/<id>/download` | Download a specific file |

## Encode/Decode Tool

| Mode | Encode | Decode |
|------|--------|--------|
| Base64 | Text to Base64 (UTF-8 safe, supports CJK) | Base64 to text |
| URL | Text to URL-encoded | URL-encoded to text |
| Hex | Text to hexadecimal | Hexadecimal to text |
| Unicode | Text to \uXXXX escapes | \uXXXX to text |

- `Ctrl + Enter` for quick encoding
- One-click copy result, swap input/output

## Image EXIF Cleaner

### What It Removes
- EXIF data: GPS location, capture time, device model, camera parameters
- IPTC/XMP metadata: author, copyright, description, keywords
- ICC color profile: embedded color space description
- AI watermarks: generation info embedded by DALL-E / Midjourney / SD / Gemini
- EXIF thumbnail: embedded JPEG thumbnail

### Supported Formats
JPG / PNG / GIF / BMP / WebP / TIFF

### How It Works
- Pixel data is fully preserved; only metadata is stripped
- For PNG: removes auxiliary chunks (tEXt / iTXt / zTXt)
- For JPEG: removes APP marker segments (EXIF/XMP/ICC) and Comment segments
- All processing happens server-side; uploaded images are not stored

## Todo List

### Core Features
- Full CRUD operations (create, view, edit, delete)
- Three priority levels (high/medium/low) with color labels
- Custom categories with autocomplete
- Due dates with overdue highlighting and animation
- Subtasks with progress bars
- Real-time search (300ms debounce)
- Stats dashboard (total/active/done/overdue), click to filter
- Flexible sorting (8 sort modes: by time, priority, due date, title)
- JSON export/import with merge support
- Bulk delete completed tasks

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + N` | New task |
| `Esc` | Close modal |
| `Enter` (in subtask input) | Add subtask |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/todos` | List tasks (`?status=active\|done&priority=&search=&sort=`) |
| POST | `/api/todos` | Create task |
| PUT | `/api/todos/<id>` | Update task |
| DELETE | `/api/todos/<id>` | Delete task |
| PATCH | `/api/todos/<id>/toggle` | Toggle completion |
| DELETE | `/api/todos/bulk/completed` | Clear all completed |
| GET | `/api/todos/stats` | Get statistics |
| GET | `/api/todos/export` | Export as JSON |
| POST | `/api/todos/import` | Import from JSON |
| POST | `/api/todos/<id>/subtasks` | Add subtask |
| PUT | `/api/subtasks/<id>` | Update subtask |
| DELETE | `/api/subtasks/<id>` | Delete subtask |
| PATCH | `/api/subtasks/<id>/toggle` | Toggle subtask |

## Clipboard API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/user` | Create or login to workspace (sets session) |
| POST | `/api/user/<u>/verify` | Verify workspace password (sets session) |
| POST | `/api/user/<u>/set-password` | Set or remove workspace password |
| GET | `/api/user/<u>/content` | List workspace content (pastes + files) |
| POST | `/api/paste` | Create text paste (requires `user_id`) |
| POST | `/api/file/upload` | Upload file (requires `user_id`) |
| DELETE | `/api/paste/by-id/<id>` | Delete paste by ID |
| DELETE | `/api/file/by-id/<id>` | Delete file by ID |

## Tech Stack

- **Backend**: Python 3 + Flask
- **Database**: SQLite (auto-created on first run)
- **Image Processing**: Pillow (PIL)
- **QR Codes**: api.qrserver.com (client-side, no extra dependency)
- **Frontend**: Vanilla HTML/CSS/JS, no framework dependencies
- **Theme**: Dark mode (Tailwind-inspired color palette)

## Project Structure

```
claude_code_test/
├── app.py                  # Flask main (routes + API + DB init)
├── data.db                 # SQLite database (auto-created, gitignored)
├── requirements.txt        # Python dependencies
├── README.md
├── .gitignore
├── templates/
│   ├── index.html          # Home page (tool cards)
│   ├── netcut.html         # Clipboard login page
│   ├── workspace.html      # Clipboard workspace (edit + share)
│   ├── encode.html         # Encode/decode tool
│   ├── exif.html           # Image EXIF cleaner
│   ├── todo.html           # Todo list
│   ├── view.html           # Legacy text view (backward compat)
│   └── view_file.html      # Legacy file view (backward compat)
├── files/                  # Uploaded file storage (gitignored)
└── uploads/                # Upload temp directory (gitignored)
```

## Notes

- This is a local development tool running with `debug=True`
- Use Gunicorn/uWSGI for production deployment
- `data.db` is auto-created on first run — do not commit to version control
- Uploaded files are stored locally in `files/`, clean up periodically

## License

MIT
