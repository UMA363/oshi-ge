import os
import urllib.request
import uvicorn
import base64
import uuid
import time
import io
from urllib.parse import urlparse
from collections import defaultdict
from typing import List
from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment
from markupsafe import Markup
from itsdangerous import URLSafeSerializer
import psycopg
from psycopg.rows import dict_row
from PIL import Image, ImageDraw, ImageFont

app = FastAPI()

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
serializer = URLSafeSerializer(SECRET_KEY)

FONT_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf"
FONT_PATH = "NotoSansCJKjp-Bold.otf"

def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            req = urllib.request.Request(FONT_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                with open(FONT_PATH, 'wb') as f:
                    f.write(response.read())
        except Exception:
            pass

download_font()

POST_COOLDOWN = 30
ip_last_post_time = defaultdict(float)

def check_rate_limit(request: Request) -> bool:
    # クラッシュ防止：request.clientがNoneの場合の安全対策
    client_ip = request.client.host if request.client else "127.0.0.1"
    client_ip = request.headers.get("X-Forwarded-For", client_ip).split(",")[0].strip()
    current_time = time.time()
    if current_time - ip_last_post_time[client_ip] < POST_COOLDOWN:
        return False
    ip_last_post_time[client_ip] = current_time
    return True

def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode="require")

def upload_image_to_supabase(base64_data: str) -> str:
    if not base64_data or not SUPABASE_URL or not SUPABASE_KEY: return ""
    try:
        header, encoded = base64_data.split(",", 1)
        file_ext = "webp" if "webp" in header else "jpg"
        file_data = base64.b64decode(encoded)
        filename = f"{uuid.uuid4()}.{file_ext}"
        
        url = f"{SUPABASE_URL}/storage/v1/object/games/{filename}"
        req = urllib.request.Request(url, data=file_data, method="POST")
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Content-Type", f"image/{file_ext}")
        
        with urllib.request.urlopen(req) as response:
            pass
        return f"{SUPABASE_URL}/storage/v1/object/public/games/{filename}"
    except Exception:
        return ""

def init_db():
    try:
        with get_db_connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS games (
                id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT,
                genre TEXT, platform TEXT, image_url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY, game_id INTEGER REFERENCES games(id), username TEXT NOT NULL,
                content TEXT NOT NULL, spoiler_level INTEGER DEFAULT 0, catchphrase TEXT,
                target_audience TEXT, play_time TEXT, likes INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id), 
                reason TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY, title TEXT NOT NULL, username TEXT NOT NULL, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            for col in ["platform TEXT", "image_url TEXT", "developer_x_id TEXT DEFAULT ''"]:
                conn.execute(f"ALTER TABLE games ADD COLUMN IF NOT EXISTS {col}")
            for col in ["catchphrase TEXT", "target_audience TEXT", "play_time TEXT", "likes INTEGER DEFAULT 0", "oshi_points TEXT DEFAULT ''", "wanna_play INTEGER DEFAULT 0", "agree INTEGER DEFAULT 0"]:
                conn.execute(f"ALTER TABLE posts ADD COLUMN IF NOT EXISTS {col}")
            conn.commit()
    except Exception as e:
        print(f"DB INIT ERROR: {e}")

init_db()

def get_secure_cookie_list(request: Request, key: str) -> List[int]:
    val = request.cookies.get(key)
    if not val: return []
    try:
        return serializer.loads(val)
    except:
        return []

def set_secure_cookie_list(res: Response, key: str, data: List[int]):
    res.set_cookie(key=key, value=serializer.dumps(data), max_age=60*60*24*365, httponly=True, samesite="lax")

@app.get("/robots.txt", response_class=Response)
def robots_txt(request: Request):
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    base_url = f"{scheme}://{host}" if host else ""
    content = f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml"
    return Response(content=content, media_type="text/plain")

@app.get("/sitemap.xml", response_class=Response)
def sitemap_xml(request: Request):
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    base_url = f"{scheme}://{host}" if host else ""
    
    with get_db_connection() as conn:
        games = conn.execute('SELECT id, created_at FROM games ORDER BY created_at DESC').fetchall()
        
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml.append(f'<url><loc>{base_url}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>')
    
    for g in games:
        lastmod = g['created_at'].strftime("%Y-%m-%d") if g['created_at'] else ""
        xml.append(f'<url><loc>{base_url}/games/{g["id"]}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>')
        
    xml.append('</urlset>')
    return Response(content="\n".join(xml), media_type="application/xml")

@app.get("/proxy-image")
def proxy_image(url: str):
    parsed = urlparse(url)
    allowed_host = urlparse(SUPABASE_URL).hostname if SUPABASE_URL else None
    if parsed.scheme != "https" or parsed.hostname != allowed_host:
        raise HTTPException(status_code=403, detail="Forbidden URL")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = response.read(5000000)
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            return Response(content=data, media_type=content_type)
    except Exception:
        raise HTTPException(status_code=404)

@app.get("/ogp.png")
def generate_top_ogp():
    W, H = 1200, 630
    img = Image.new('RGB', (W, H), color='#0f172a')
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype(FONT_PATH, 64)
        font_sub = ImageFont.truetype(FONT_PATH, 32)
    except:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.rectangle([(0, 0), (20, H)], fill="#f59e0b")
    draw.text((80, 160), "🎮 Oshi-Ge", font=font_title, fill="#f59e0b")
    draw.text((80, 260), "誰かの人生を変える1本を。", font=font_title, fill="#ffffff")
    draw.text((80, 360), "未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ", font=font_sub, fill="#94a3b8")

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return Response(content=img_byte_arr.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})

@app.get("/games/{game_id}/ogp.png")
def generate_ogp(game_id: int):
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
        if not game: raise HTTPException(status_code=404)
        post = conn.execute('SELECT catchphrase, username FROM posts WHERE game_id = %s ORDER BY (likes + wanna_play + agree) DESC, created_at DESC LIMIT 1', (game_id,)).fetchone()

    W, H = 1200, 630
    img = Image.new('RGB', (W, H), color='#0f172a')
    
    if game.get("image_url"):
        try:
            req = urllib.request.Request(game["image_url"], headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                bg_data = response.read(5000000)
                bg_img = Image.open(io.BytesIO(bg_data)).convert("RGBA")
                bg_ratio = bg_img.width / bg_img.height
                target_ratio = W / H
                if bg_ratio > target_ratio:
                    new_w = int(bg_img.height * target_ratio)
                    offset = (bg_img.width - new_w) // 2
                    bg_img = bg_img.crop((offset, 0, offset + new_w, bg_img.height))
                else:
                    new_h = int(bg_img.width / target_ratio)
                    offset = (bg_img.height - new_h) // 2
                    bg_img = bg_img.crop((0, offset, bg_img.width, offset + new_h))
                bg_img = bg_img.resize((W, H))
                overlay = Image.new('RGBA', (W, H), color=(15, 23, 42, 200))
                bg_img = Image.alpha_composite(bg_img, overlay)
                img.paste(bg_img.convert('RGB'), (0, 0))
        except:
            pass

    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype(FONT_PATH, 56)
        font_catch = ImageFont.truetype(FONT_PATH, 46)
        font_brand = ImageFont.truetype(FONT_PATH, 32)
    except:
        font_title = ImageFont.load_default()
        font_catch = ImageFont.load_default()
        font_brand = ImageFont.load_default()

    draw.rectangle([(0, 0), (16, H)], fill="#f59e0b")
    draw.text((60, 40), "🎮 Oshi-Ge", font=font_brand, fill="#f59e0b")
    
    title_text = game['title']
    draw.text((60, 130), title_text, font=font_title, fill="#ffffff")
    draw.line([(60, 210), (1140, 210)], fill="#334155", width=2)
    
    if post and post['catchphrase']:
        catch_text = f"「{post['catchphrase']}」"
        chars = list(catch_text)
        line = ""
        lines = []
        for ch in chars:
            if draw.textlength(line + ch, font=font_catch) > 1050:
                lines.append(line)
                line = ch
            else:
                line += ch
        if line: lines.append(line)
        
        y_text = 270
        for l in lines[:3]:
            draw.text((60, y_text), l, font=font_catch, fill="#fcd34d")
            y_text += 65
            
        author_text = f"布教者: {post['username']}"
        draw.text((60, H - 80), author_text, font=font_brand, fill="#94a3b8")
    else:
        draw.text((60, 270), "まだ布教コメントがありません。\n最初の布教者になりませんか？", font=font_catch, fill="#94a3b8")

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    return Response(content=img_byte_arr.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})

CSS = """
:root { --bg-color: #0f172a; --card-bg: #1e293b; --text-main: #f8fafc; --text-sub: #94a3b8; --accent: #f59e0b; --accent-hover: #d97706; --border: #334155; --safe: #10b981; --warning: #f59e0b; --danger: #ef4444; }
html { font-size: 14px; }
body { font-family: 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif; background-color: var(--bg-color); color: var(--text-main); margin: 0; padding: 0; line-height: 1.6; }
.header-container { background-color: #0b1120; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
.header-container h1 { margin: 0; font-size: 1.8rem; font-weight: 900; letter-spacing: 0.05em; font-family: 'Arial Black', sans-serif;}
.header-container h1 a { color: var(--accent); text-decoration: none; transition: color 0.2s; }
.header-container h1 a:hover { color: var(--text-main); }
main { max-width: 1000px; margin: 0 auto; padding: 2rem 1rem; }
.hero { text-align: center; padding: 3rem 1rem 4rem; background: radial-gradient(circle at top, #1e293b 0%, #0f172a 100%); border-bottom: 1px solid var(--border); margin-bottom: 2rem; }
.hero h2 { font-size: 2.5rem; margin: 0 0 1rem 0; color: var(--accent); font-weight: 900; }
.hero p { color: var(--text-sub); font-size: 1.1rem; margin-bottom: 2rem; }
.search-bar-advanced { max-width: 800px; margin: 0 auto; background: rgba(15, 23, 42, 0.8); padding: 1rem; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 1rem;}
.search-inputs { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.search-inputs input, .search-inputs select { padding: 0.8rem; border-radius: 8px; border: 1px solid var(--border); background: #0f172a; color: white; font-size: 1rem; }
.search-inputs input { flex: 2; min-width: 200px; }
.search-inputs select { flex: 1; min-width: 130px; }
.search-inputs button { flex: 1; min-width: 120px; font-size: 1.1rem; }
.search-inputs input:focus, .search-inputs select:focus { outline: none; border-color: var(--accent); }
.layout-wrapper { display: flex; gap: 2rem; align-items: flex-start; }
.main-column { flex: 1; min-width: 0; }
.sidebar-column { width: 300px; flex-shrink: 0; }
@media (max-width: 850px) { 
    .layout-wrapper { flex-direction: column; } 
    .sidebar-column { width: 100%; order: -1; margin-bottom: 1.5rem; } 
}
.card { background: var(--card-bg); padding: 1.5rem; margin-bottom: 1.5rem; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); }
h2, h3 { margin-top: 0; color: var(--text-main); }
.btn { display: inline-flex; align-items: center; justify-content: center; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; border: none; cursor: pointer; font-weight: bold; transition: all 0.2s; font-size: 1rem; white-space: nowrap; }
.btn-primary { background-color: var(--accent); color: #fff; box-shadow: 0 2px 4px rgba(245, 158, 11, 0.3); }
.btn-primary:hover { background-color: var(--accent-hover); transform: translateY(-2px); }
.btn-outline { background-color: transparent; border: 2px solid var(--border); color: var(--text-main); }
.btn-outline:hover { border-color: var(--accent); color: var(--accent); }
.btn-small { padding: 0.4rem 0.8rem; font-size: 0.85rem; }
.btn-x { background-color: #000; color: #fff; padding: 0.5rem 1rem; font-size: 0.9rem; border: 1px solid #333; transition: all 0.2s; border-radius: 8px; cursor: pointer; }
.btn-x:hover { background-color: #222; }
.btn-line { background-color: #06C755; color: #fff; padding: 0.5rem 1rem; font-size: 0.9rem; border: 1px solid #05a546; transition: all 0.2s; border-radius: 8px; cursor: pointer; }
.btn-line:hover { background-color: #05a546; }
.btn-bookmark { background: transparent; border: 1px solid var(--border); color: var(--text-main); padding: 0.5rem 1rem; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 0.9rem; transition: 0.2s; white-space: nowrap; }
.btn-bookmark.bookmarked { background: rgba(16, 185, 129, 0.1); border-color: var(--safe); color: var(--safe); }
.form-group { margin-bottom: 1.5rem; }
.form-group label { display: block; margin-bottom: 0.5rem; font-weight: bold; color: #cbd5e1; }
.form-group input[type="text"], .form-group textarea, .form-group select { width: 100%; padding: 0.75rem; background: #0f172a; border: 1px solid var(--border); color: var(--text-main); border-radius: 8px; box-sizing: border-box; font-size: 1rem; font-family: inherit; }
.form-group input[type="file"] { width: 100%; color: var(--text-main); padding: 0.5rem 0; }
.form-group input[type="checkbox"] { width: auto; transform: scale(1.2); cursor: pointer; margin-right: 0.5rem; }
.spoiler-radio-group { background: #0b1120; padding: 1.25rem; border-radius: 8px; border: 1px solid var(--border); }
.radio-label { display: flex; flex-direction: column; margin-bottom: 1rem; cursor: pointer; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
.radio-label:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
.radio-header { display: flex; align-items: center; font-weight: bold; font-size: 1.05rem; }
.tag { display: inline-block; background: #334155; color: #e2e8f0; padding: 0.3rem 0.8rem; border-radius: 9999px; font-size: 0.85rem; font-weight: bold; margin-bottom: 0.5rem; margin-right: 0.5rem; }
.tag.genre { background: rgba(245, 158, 11, 0.2); color: var(--accent); border: 1px solid rgba(245, 158, 11, 0.3); }
.tag.oshi-point { background: rgba(236, 72, 153, 0.15); color: #f472b6; border: 1px solid rgba(236, 72, 153, 0.4); }
.game-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 1.5rem; }
.game-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; transition: transform 0.2s; display: flex; flex-direction: column; cursor: pointer; }
.game-card:hover { transform: translateY(-4px); border-color: var(--accent); }
.game-thumbnail { width: 100%; height: 150px; object-fit: cover; background: #334155; }
.game-thumbnail.empty { display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-weight: bold; background: linear-gradient(45deg, #1e293b, #0f172a); }
.game-card-body { padding: 1.2rem; flex-grow: 1; display: flex; flex-direction: column; }
.latest-catchphrase { margin-top: auto; padding: 0.8rem; background: rgba(245, 158, 11, 0.1); border-left: 3px solid var(--accent); border-radius: 4px; font-size: 0.9rem; font-weight: bold; color: #fcd34d; }
.game-hero-image { width: 100%; max-height: 400px; object-fit: cover; border-radius: 8px; margin-bottom: 1.5rem; border: 1px solid var(--border); }
.post-card { background: #0f172a; border: 1px solid var(--border); }
.post-header { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; color: var(--text-sub); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.75rem; }
.catchphrase-text { margin: 0 0 0.75rem 0; color: var(--accent); font-size: 1.3rem; font-weight: 900; line-height: 1.4; }
.meta-tag { background: transparent; color: #94a3b8; padding: 0.2rem 0.6rem; border-radius: 4px; border: 1px solid #475569; font-size: 0.85rem;}
.spoiler-badge.safe { color: var(--safe); font-weight: bold; font-size: 0.9rem; display: inline-flex; background: rgba(16, 185, 129, 0.1); padding: 0.3rem 0.6rem; border-radius: 6px; }
.post-content p { font-size: 1.05rem; margin-top: 0.75rem; white-space: pre-wrap; }
.spoiler-toggle-btn { width: 100%; padding: 1rem; font-weight: bold; border: 2px dashed; border-radius: 8px; cursor: pointer; background: transparent; transition: all 0.2s; font-size: 1rem; }
.spoiler-toggle-btn.warning { color: var(--warning); border-color: rgba(245, 158, 11, 0.5); }
.spoiler-toggle-btn.danger { color: var(--danger); border-color: rgba(239, 68, 68, 0.5); }
.spoiler-hidden-text { margin-top: 1rem; padding: 1.25rem; background: #1e293b; border-left: 4px solid var(--border); border-radius: 0 8px 8px 0; }
.btn-react { background: transparent; border: 1px solid var(--border); color: var(--text-sub); padding: 0.4rem 0.8rem; border-radius: 20px; cursor: pointer; font-weight: bold; transition: 0.2s; display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.9rem; white-space: nowrap; }
.btn-react:hover { transform: translateY(-2px); border-color: #94a3b8; color: var(--text-main); }
.btn-react span { background: rgba(255,255,255,0.05); padding: 0.1rem 0.5rem; border-radius: 12px; font-size: 0.8rem; }
.btn-react.reacted.btn-wanna-play { background: rgba(16, 185, 129, 0.1); border-color: var(--safe); color: var(--safe); }
.btn-react.reacted.btn-wanna-play span { background: rgba(16, 185, 129, 0.2); }
.btn-react.reacted.btn-agree { background: rgba(59, 130, 246, 0.1); border-color: #3b82f6; color: #3b82f6; }
.btn-react.reacted.btn-agree span { background: rgba(59, 130, 246, 0.2); }
.btn-react.reacted.btn-like { background: rgba(245, 158, 11, 0.1); border-color: var(--accent); color: var(--accent); }
.btn-react.reacted.btn-like span { background: rgba(245, 158, 11, 0.2); }
.discover-panel { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; }
.discover-panel h3 { margin-bottom: 0.9rem; color: var(--accent); }
.quick-filter-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.6rem; }
.quick-filter { display: flex; align-items: center; justify-content: center; min-height: 46px; padding: 0.6rem 0.8rem; background: #0f172a; border: 1px solid var(--border); border-radius: 10px; color: var(--text-main); text-decoration: none; font-weight: bold; text-align: center; transition: 0.2s; }
.quick-filter:hover { border-color: var(--accent); color: var(--accent); transform: translateY(-2px); }
.quick-filter.active { background-color: var(--accent); color: #fff; border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 4px 6px rgba(245,158,11,0.2); }

@media (max-width: 600px) { 
    html { font-size: 16px; }
    .header-container { flex-direction: column; gap: 1rem; text-align: center; padding: 1rem; }
    .header-container h1 { font-size: 1.5rem; }
    .hero { padding: 2rem 1rem; }
    .hero h2 { font-size: 1.8rem; }
    .search-inputs { flex-direction: column; }
    .search-inputs input, .search-inputs select, .search-inputs button { width: 100%; box-sizing: border-box; }
    .game-grid { grid-template-columns: 1fr; }
    .card { padding: 1rem; }
    .game-header-row { flex-direction: column; align-items: stretch !important; gap: 0.75rem !important; }
    .game-header-actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
    .game-header-actions .btn-bookmark, .game-header-actions .btn { font-size: 0.8rem !important; padding: 0.4rem 0.6rem !important; }
    .btn-react { flex: 1; justify-content: center; padding: 0.4rem 0.2rem; font-size: 0.75rem; gap: 0.2rem; }
    .btn-react span { font-size: 0.7rem; padding: 0.1rem 0.3rem; }
    .post-card > div:last-child { flex-direction: column; align-items: stretch !important; gap: 1rem !important; }
    .post-card > div:last-child > div { width: 100%; justify-content: space-between; }
}

.promo-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.78); display: flex; align-items: center; justify-content: center; padding: 1rem; z-index: 9999; }
.promo-modal-box { width: min(900px, 100%); max-height: 95vh; overflow-y: auto; background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; padding: 1rem; box-sizing: border-box; }
.promo-modal-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.8rem; }
.promo-modal-head h3 { margin: 0; color: var(--accent); }
.promo-canvas-wrap { background: #0b1120; border-radius: 10px; padding: 0.75rem; border: 1px solid var(--border); }
.promo-modal-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.8rem; }
.cropper-view-box, .cropper-face { border-radius: 4px; }
"""

JS = """
function toggleSpoiler(btn) {
    const txt = btn.nextElementSibling;
    if (txt.style.display === "none") { txt.style.display = "block"; btn.style.opacity = "0.7"; btn.innerText = "クリックして閉じる"; } 
    else {
        txt.style.display = "none"; btn.style.opacity = "1";
        if (btn.classList.contains('warning')) btn.innerText = "🔒 軽微なネタバレ【クリックして表示】";
        else btn.innerText = "⚠️ ネタバレあり【クリックして表示】";
    }
}

function shareGameToX(title, devId) { 
    const cleanTitleTag = '#' + title.replace(/[\\s /／・！!？?♪～描()（）[\]「」『』]/g, '');
    let mentions = "@horse_123123";
    if (devId && devId.trim()) {
        let cleanDevId = devId.trim();
        if (!cleanDevId.startsWith('@')) cleanDevId = '@' + cleanDevId;
        mentions += ' ' + cleanDevId;
    }
    const text = `次に遊ぶ神ゲーを探している方へ🎮\\n『${title}』のおすすめ布教ページです！👇\\n\\n${cleanTitleTag} #推しゲー #OshiGe ${mentions}\\n`;
    window.open(`https://x.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(window.location.href)}`, '_blank'); 
}

function shareGameToLine(title) { 
    window.open(`https://line.me/R/msg/text/?${encodeURIComponent(`次に遊ぶ神ゲーを探している方へ🎮\\n『${title}』のおすすめ布教ページです！👇\\n`)}${encodeURIComponent(window.location.href)}`, '_blank'); 
}

function sharePost(btn, platform) {
    const gameId = btn.dataset.id;
    const title = btn.dataset.title;
    const catchphrase = btn.dataset.catch;
    const content = btn.dataset.content;
    const spoilerLevel = Number(btn.dataset.spoiler || '0');
    const devId = btn.dataset.dev || '';
    const url = window.location.origin + '/games/' + gameId;
    
    const cleanTitleTag = '#' + title.replace(/[\\s /／・！!？?♪～描()（）[\]「」『』]/g, '');
    
    let text = `このゲーム、もっと知られてほしい。\\n\\n🎮 『${title}』`;
    if (catchphrase) text += `\\n\\n「${catchphrase}」`;
    if (spoilerLevel === 0 && content.trim()) {
        let impression = content.trim();
        if (Array.from(impression).length > 20) impression = Array.from(impression).slice(0, 20).join('') + '…';
        text += `\\n\\n💬「${impression}」`;
    } else if (spoilerLevel === 1) text += `\\n\\n🔒 軽微なネタバレを含みます`;
    else if (spoilerLevel === 2) text += `\\n\\n⚠️ ネタバレあり`;
    
    let mentions = "@horse_123123";
    if (devId.trim()) {
        let cleanDevId = devId.trim();
        if (!cleanDevId.startsWith('@')) cleanDevId = '@' + cleanDevId;
        mentions += ' ' + cleanDevId;
    }
    
    text += `\\n\\n布教内容はこちら👇\\n${url}\\n\\n${cleanTitleTag} #推しゲー #OshiGe ${mentions}`;

    if (platform === 'x') window.open(`https://x.com/intent/tweet?text=${encodeURIComponent(text)}`, '_blank');
    else if (platform === 'line') window.open(`https://line.me/R/msg/text/?${encodeURIComponent(text)}`, '_blank');
}

async function reactPost(gId, pId, type, btn) {
    if (btn.classList.contains('reacted')) return;
    try {
        const res = await fetch(`/games/${gId}/posts/${pId}/react/${type}`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            btn.querySelector('span').innerText = data.count;
            btn.classList.add('reacted'); 
            localStorage.setItem(`reacted_${type}_${pId}`, 'true');
        }
    } catch (e) {}
}

async function toggleBookmark(gId, btn) {
    try {
        const res = await fetch(`/games/${gId}/bookmark`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            if (data.bookmarked) { btn.innerText = "🔖 お気に入り解除"; btn.classList.add('bookmarked'); } 
            else { btn.innerText = "🔖 お気に入りに追加"; btn.classList.remove('bookmarked'); }
        }
    } catch(e) {}
}

function openReportModal(postId) {
    const modal = document.getElementById('report-modal');
    if(modal) { document.getElementById('report_post_id').value = postId; modal.style.display = 'flex'; }
}
function closeReportModal() {
    const modal = document.getElementById('report-modal');
    if(modal) modal.style.display = 'none';
}
async function submitReport(e) {
    e.preventDefault();
    const postId = document.getElementById('report_post_id').value;
    const reasonEl = document.querySelector('input[name="report_reason"]:checked');
    if (!reasonEl) return;
    try {
        const formData = new FormData();
        formData.append('reason', reasonEl.value);
        await fetch(`/posts/${postId}/report`, { method: 'POST', body: formData });
        alert("通報を受信しました。サイトの治安維持にご協力いただきありがとうございます。");
        closeReportModal();
    } catch(err) { alert("通信エラーが発生しました。"); }
}

function updatePlatform(f) { f.querySelector('.platform-hidden').value = Array.from(f.querySelectorAll('.platform-cb:checked')).map(cb => cb.value).join(','); }

let cropper = null;
function applyCrop() {
    if (!cropper) return;
    const canvas = cropper.getCroppedCanvas({ maxWidth: 800, maxHeight: 800 });
    const dataUrl = canvas.toDataURL('image/webp', 0.8);
    document.getElementById('image_base64').value = dataUrl;
    document.getElementById('preview_img').src = dataUrl;
    document.getElementById('image_preview').style.display = 'block';
    closeCropModal();
}
function closeCropModal() {
    document.getElementById('crop_modal').style.display = 'none';
    if (cropper) { cropper.destroy(); cropper = null; }
    document.getElementById('image_upload').value = ""; 
}

let allGamesList = [];
async function initGachaData() {
    try {
        const res = await fetch('/api/games-list');
        if (res.ok) { allGamesList = await res.json(); }
    } catch(e) {}
}

async function startGacha(event) {
    event.preventDefault();
    if (allGamesList.length === 0) { await initGachaData(); }
    if (allGamesList.length === 0) {
        alert("現在登録されているゲームがありません！");
        return;
    }

    const modal = document.getElementById('gacha-modal');
    const titleEl = document.getElementById('gacha-title-display');
    const btnEl = document.getElementById('gacha-action-btn');
    if (!modal) return;

    modal.style.display = 'flex';
    btnEl.style.display = 'none';
    titleEl.innerText = "🎲 ガチャ回転中...";

    let count = 0;
    const maxCount = 20;
    const interval = setInterval(() => {
        const randomGame = allGamesList[Math.floor(Math.random() * allGamesList.length)];
        titleEl.innerText = randomGame.title;
        count++;
        if (count >= maxCount) {
            clearInterval(interval);
            const selectedGame = allGamesList[Math.floor(Math.random() * allGamesList.length)];
            titleEl.innerHTML = `🎉 神ゲー発掘！<br><span style="color: var(--accent); font-size: 1.8rem;">『${selectedGame.title}』</span>`;
            btnEl.innerText = "✨ このゲームを見に行く";
            btnEl.onclick = () => { location.href = `/games/${selectedGame.id}`; };
            btnEl.style.display = 'inline-block';
        }
    }, 100);
}

function closeGachaModal() {
    const modal = document.getElementById('gacha-modal');
    if (modal) modal.style.display = 'none';
}

document.addEventListener("DOMContentLoaded", () => {
    initGachaData();
    document.querySelectorAll('.btn-react').forEach(b => { 
        if (localStorage.getItem(`reacted_${b.dataset.type}_${b.dataset.postId}`)) {
            b.classList.add('reacted'); 
        }
    });

    const imageUpload = document.getElementById('image_upload');
    if (imageUpload) {
        imageUpload.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(event) {
                const cropperImg = document.getElementById('cropper_img');
                cropperImg.src = event.target.result;
                document.getElementById('crop_modal').style.display = 'flex';
                if (cropper) cropper.destroy();
                cropper = new Cropper(cropperImg, { aspectRatio: 16 / 9, viewMode: 1, autoCropArea: 1, responsive: true, background: false });
            };
            reader.readAsDataURL(file);
        });
    }

    const urlParams = new URLSearchParams(window.location.search);
    const postedId = urlParams.get('posted');
    if (postedId) {
        const promoBtn = document.querySelector(`button[data-postid="${postedId}"]`);
        if (promoBtn) {
            setTimeout(() => {
                alert("🎉 布教の投稿が完了しました！\\n生成された「布教カード」をSNSでシェアして、あなたの推しゲーを広めましょう！");
                openPromoCard(promoBtn);
                window.history.replaceState({}, document.title, window.location.pathname);
            }, 300);
        }
    }
});

function isMobileDevice() { return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent); }

function openPromoCard(btn) {
    const modal = document.getElementById('promo-card-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    modal.dataset.title = btn.dataset.title || '';
    modal.dataset.catchphrase = btn.dataset.catch || 'このゲーム、ぜひ遊んでほしい！';
    modal.dataset.target = btn.dataset.target || '';
    modal.dataset.playTime = btn.dataset.play || '';
    modal.dataset.username = btn.dataset.user || '名無しの布教者';
    modal.dataset.genre = btn.dataset.genre || '';
    modal.dataset.platform = btn.dataset.platform || '';
    modal.dataset.spoiler = String(btn.dataset.spoiler || '0');
    modal.dataset.content = btn.dataset.content || '';
    modal.dataset.imageUrl = btn.dataset.img || ''; 
    modal.dataset.oshiPoints = btn.dataset.oshi || '';
    modal.dataset.dev = btn.dataset.dev || '';
    
    const dlBtn = document.getElementById('promo-dl-btn');
    const instruction = document.getElementById('promo-instruction');
    if (isMobileDevice()) {
        if(dlBtn) dlBtn.style.display = 'none';
        if(instruction) instruction.innerHTML = '📱 <strong>画像を長押しして保存してください！</strong><br>保存した画像はSNSでシェアして布教しましょう。';
    } else {
        if(dlBtn) dlBtn.style.display = 'inline-block';
        if(instruction) instruction.innerHTML = '「画像を保存する」ボタンでダウンロードし、SNSでシェアして布教しましょう！';
    }
    
    const resultImg = document.getElementById('promoResultImg');
    if(resultImg) resultImg.style.display = 'none';

    drawPromoCard();
}
function closePromoCard() {
    const modal = document.getElementById('promo-card-modal');
    if (modal) modal.style.display = 'none';
}

function wrapCanvasText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
    const chars = Array.from(text || '');
    let line = '';
    const lines = [];
    for (const ch of chars) {
        const test = line + ch;
        if (ctx.measureText(test).width > maxWidth && line) {
            lines.push(line);
            line = ch;
            if (lines.length >= maxLines) break;
        } else {
            line = test;
        }
    }
    if (lines.length < maxLines && line) lines.push(line);
    if (lines.length === maxLines && lines.join('').length < chars.length) {
        let last = lines[maxLines - 1] || '';
        while (ctx.measureText(last + '…').width > maxWidth && last.length > 0) last = last.slice(0, -1);
        lines[maxLines - 1] = last + '…';
    }
    lines.forEach((t, i) => ctx.fillText(t, x, y + i * lineHeight));
    return lines.length;
}

function drawRoundRect(ctx, x, y, w, h, r) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath(); ctx.moveTo(x + rr, y); ctx.arcTo(x + w, y, x + w, y + h, rr); ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr); ctx.arcTo(x, y, x + w, y, rr); ctx.closePath();
}

async function drawPromoCard() {
    const modal = document.getElementById('promo-card-modal');
    const canvas = document.getElementById('promoCanvas');
    if (!modal || !canvas) return;

    const ctx = canvas.getContext('2d');
    const W = 1080; 

    const title = modal.dataset.title;
    const catchphrase = modal.dataset.catchphrase;
    const target = modal.dataset.target;
    const playTime = modal.dataset.playTime;
    const genre = modal.dataset.genre;
    const platform = modal.dataset.platform;
    const spoiler = Number(modal.dataset.spoiler);
    const imageUrl = modal.dataset.imageUrl;
    const oshiPoints = modal.dataset.oshiPoints;
    let contentRaw = modal.dataset.content;

    if (spoiler > 0) contentRaw = '（※詳細な感想は、ネタバレ防止のためサイト上で確認してください）';

    function getLines(text, maxWidth, font, maxLines) {
        if(!text) return 0;
        ctx.font = font;
        const chars = Array.from(text);
        let line = ''; let lines = 0;
        for (const ch of chars) {
            if (ctx.measureText(line + ch).width > maxWidth && line) {
                lines++; line = ch;
                if(maxLines && lines >= maxLines) return maxLines;
            } else { line += ch; }
        }
        if (line) lines++;
        return maxLines ? Math.min(lines, maxLines) : lines;
    }

    let img = null;
    let drawH = 607;
    if (imageUrl) {
        try {
            img = new Image();
            img.crossOrigin = 'Anonymous'; 
            img.src = '/proxy-image?url=' + encodeURIComponent(imageUrl);
            await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; });
            drawH = img.height * (W / img.width);
        } catch(e) {}
    }

    let catchY = 650;
    if (drawH > 600 && drawH < 800) { catchY = drawH + 40; }
    else if (drawH >= 800) { catchY = 840; }

    const catchLines = getLines(catchphrase, 980, '900 65px "Noto Sans JP", sans-serif', 3);
    let panelY = catchY + (catchLines * 85) + 30;
    if(panelY < 600) panelY = 600;

    let simY = panelY + 70;
    const titleLines = getLines(title, 920, '900 45px "Noto Sans JP", sans-serif', 2);
    simY += titleLines * 55 + 30;

    if (contentRaw) {
        const contentLines = getLines('「' + contentRaw.trim() + '」', 920, '400 30px "Noto Sans JP", sans-serif', 4);
        simY += contentLines * 45 + 40;
    }

    if (target) {
        simY += 35 + 35 + 60;
    }

    const tags = [];
    if(playTime) tags.push(playTime);
    if(genre) tags.push(genre);
    if(platform) tags.push(...platform.split(',').map(s=>s.trim()).filter(Boolean));
    if(oshiPoints) tags.push(...oshiPoints.split(',').filter(Boolean));
    if(tags.length) { simY += 42 + 40; }

    const panelH = simY - panelY + 20;
    const H = Math.max(1350, panelY + panelH + 100);
    
    canvas.width = W; canvas.height = H;

    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#1e293b'); bg.addColorStop(1, '#020617');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

    if (img) {
        ctx.drawImage(img, 0, 0, W, drawH);
        const fadeStart = Math.max(0, drawH - 250);
        const fade = ctx.createLinearGradient(0, fadeStart, 0, drawH);
        fade.addColorStop(0, 'rgba(2, 6, 23, 0)'); fade.addColorStop(1, '#020617');
        ctx.fillStyle = fade; ctx.fillRect(0, fadeStart, W, drawH - fadeStart);
        if (drawH < H) {
            ctx.fillStyle = '#020617';
            ctx.fillRect(0, drawH, W, H - drawH);
        }
    } else {
        const glow = ctx.createRadialGradient(W/2, 300, 50, W/2, 300, 600);
        glow.addColorStop(0, 'rgba(245,158,11,0.2)'); glow.addColorStop(1, 'rgba(245,158,11,0)');
        ctx.fillStyle = glow; ctx.fillRect(0, 0, W, 900);
    }

    ctx.fillStyle = '#f59e0b'; ctx.fillRect(0, 40, 12, 50);
    ctx.font = '900 36px "Noto Sans JP", sans-serif'; ctx.fillText('OSHI-GE', 40, 78);

    let badgeText = '🟢 ネタバレなし'; let badgeColor = '#10b981'; let badgeBg = 'rgba(16, 185, 129, 0.2)';
    if (spoiler === 1) { badgeText = '🟡 軽微なネタバレあり'; badgeColor = '#f59e0b'; badgeBg = 'rgba(245, 158, 11, 0.2)'; }
    if (spoiler === 2) { badgeText = '🔴 ネタバレあり'; badgeColor = '#ef4444'; badgeBg = 'rgba(239, 68, 68, 0.2)'; }
    ctx.font = '900 24px "Noto Sans JP", sans-serif';
    const bw = ctx.measureText(badgeText).width + 40;
    drawRoundRect(ctx, W - bw - 40, 40, bw, 50, 25);
    ctx.fillStyle = badgeBg; ctx.fill();
    ctx.strokeStyle = badgeColor; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = badgeColor; ctx.fillText(badgeText, W - bw - 20, 73);

    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = 'rgba(0,0,0,0.9)'; ctx.shadowBlur = 15;
    ctx.font = '900 65px "Noto Sans JP", sans-serif';
    wrapCanvasText(ctx, catchphrase, 50, catchY, 980, 85, 3);
    ctx.shadowBlur = 0;

    drawRoundRect(ctx, 40, panelY, 1000, panelH, 20);
    ctx.fillStyle = 'rgba(15, 23, 42, 0.85)'; ctx.fill();
    ctx.strokeStyle = 'rgba(51, 65, 85, 0.8)'; ctx.lineWidth = 2; ctx.stroke();

    let currentY = panelY + 70;
    ctx.fillStyle = '#ffffff'; ctx.font = '900 45px "Noto Sans JP", sans-serif';
    const drawnTitleLines = wrapCanvasText(ctx, title, 80, currentY, 920, 55, 2);
    currentY += drawnTitleLines * 55 + 30;

    if (contentRaw) {
        ctx.fillStyle = '#cbd5e1'; ctx.font = '400 30px "Noto Sans JP", sans-serif';
        const drawnContentLines = wrapCanvasText(ctx, '「' + contentRaw.trim() + '」', 80, currentY, 920, 45, 4);
        currentY += drawnContentLines * 45 + 40;
    }

    if (target) {
        ctx.fillStyle = '#94a3b8'; ctx.font = '700 22px "Noto Sans JP", sans-serif';
        ctx.fillText('👤 こんな人におすすめ', 80, currentY);
        currentY += 35;
        ctx.fillStyle = '#f8fafc'; ctx.font = '900 28px "Noto Sans JP", sans-serif';
        wrapCanvasText(ctx, target, 100, currentY, 880, 35, 1);
        currentY += 60;
    }

    if(tags.length) {
        let tx = 80;
        ctx.font = '700 22px "Noto Sans JP", sans-serif';
        for(let i=0; i<Math.min(tags.length, 6); i++) {
            const tagStr = '#' + tags[i];
            const tw = ctx.measureText(tagStr).width + 30;
            if(tx + tw > 1000) break;
            drawRoundRect(ctx, tx, currentY, tw, 42, 21);
            ctx.fillStyle = 'rgba(245, 158, 11, 0.15)'; ctx.fill();
            ctx.fillStyle = '#fcd34d'; ctx.fillText(tagStr, tx + 15, currentY + 30);
            tx += tw + 15;
        }
    }

    ctx.fillStyle = '#64748b'; ctx.font = '22px "Noto Sans JP", sans-serif';
    ctx.fillText('あなたも、このゲームを布教しよう。', 50, H - 35);
    ctx.fillStyle = '#f59e0b'; ctx.font = '900 26px "Noto Sans JP", sans-serif';
    ctx.fillText('Oshi-Ge', 960, H - 35);

    const dataUrl = canvas.toDataURL('image/png');
    const resultImg = document.getElementById('promoResultImg');
    if (resultImg) {
        resultImg.src = dataUrl;
        resultImg.style.display = 'block';
    }
}

function downloadPromoCard() {
    const canvas = document.getElementById('promoCanvas');
    if (!canvas) return;
    const title = document.getElementById('promo-card-modal').dataset.title || 'oshi-ge';
    const a = document.createElement('a');
    a.download = `Oshi-Ge_${title.replace(/[\\\\/:*?"<>|]/g, '_')}.png`;
    a.href = canvas.toDataURL('image/png');
    a.click();
}

function sharePromoCardToX() {
    const modal = document.getElementById('promo-card-modal');
    const title = modal.dataset.title || '';
    const catchphrase = modal.dataset.catchphrase || '';
    const spoilerLevel = Number(modal.dataset.spoiler || '0');
    const content = modal.dataset.content || '';
    const devId = modal.dataset.dev || '';
    
    const url = window.location.href.split('?')[0]; 
    const cleanTitleTag = '#' + title.replace(/[\\s /／・！!？?♪～描()（）[\]「」『』]/g, '');
    
    let text = `このゲーム、もっと知られてほしい。\\n\\n🎮 『${title}』`;
    if (catchphrase) text += `\\n\\n「${catchphrase}」`;
    
    if (spoilerLevel === 0 && content.trim()) {
        let impression = content.trim();
        if (Array.from(impression).length > 20) impression = Array.from(impression).slice(0, 20).join('') + '…';
        text += `\\n\\n💬「${impression}」`;
    } else if (spoilerLevel === 1) text += `\\n\\n🔒 軽微なネタバレを含みます`;
    else if (spoilerLevel === 2) text += `\\n\\n⚠️ ネタバレあり`;
    
    let mentions = "@horse_123123";
    if (devId.trim()) {
        let cleanDevId = devId.trim();
        if (!cleanDevId.startsWith('@')) cleanDevId = '@' + cleanDevId;
        mentions += ' ' + cleanDevId;
    }
    
    text += `\\n\\n布教内容はこちら👇\\n${url}\\n\\n${cleanTitleTag} #推しゲー #OshiGe ${mentions}`;
    
    alert("この後開くXの投稿画面で、先ほど保存した「布教カード画像」を貼り付けてポストしてください！");
    window.open(`https://x.com/intent/tweet?text=${encodeURIComponent(text)}`, '_blank');
}

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePromoCard(); });
"""

env = Environment(autoescape=True)

def render_page(request: Request, content_template_str, is_top=False, page_title=None, og_description=None, og_image=None, game_schema=None, **kwargs):
    safe_kwargs = {k: (v if v is not None else "") for k, v in kwargs.items()}
    content_html = env.from_string(content_template_str).render(request=request, **safe_kwargs)
    final_title = page_title if page_title else "Oshi-Ge | ネタバレなしゲーム布教サイト"
    final_desc = og_description if og_description else "未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。"
    
    return HTMLResponse(env.from_string(BASE_HTML).render(
        request=request, css=Markup(CSS), js=Markup(JS), content=Markup(content_html), is_top=is_top, 
        page_title=final_title, og_description=final_desc, og_image=og_image, game_schema=game_schema, **safe_kwargs
    ))

@app.get("/api/games-list")
def api_games_list():
    with get_db_connection() as conn:
        games = conn.execute("SELECT id, title FROM games").fetchall()
    return games

@app.get("/")
def read_root(request: Request, q: str = "", genre: str = "", platform: str = "", sort: str = "new"):
    order_clause = "g.created_at DESC"
    if sort == "posts": order_clause = "(SELECT COUNT(*) FROM posts p WHERE p.game_id = g.id) DESC, g.created_at DESC"
    query = f'''SELECT g.*, (SELECT catchphrase FROM posts p WHERE p.game_id = g.id ORDER BY p.created_at DESC LIMIT 1) as latest_catchphrase, (SELECT COUNT(*) FROM posts p WHERE p.game_id = g.id) as post_count FROM games g WHERE 1=1'''
    params = []
    
    if q:
        synonyms = {
            "ストーリー": ["ストーリー", "シナリオ", "物語"],
            "泣ける": ["泣ける", "泣いた", "涙", "感動", "号泣", "切ない"],
            "一人": ["一人", "1人", "ソロ", "シングル", "没入"],
            "短時間": ["短時間", "サクッと", "短い", "手軽", "テンポ", "休日"],
            "ホラー": ["ホラー", "怖い", "恐怖", "ホラゲー", "驚く"],
            "インディー": ["インディー", "同人", "個人制作"],
            "初心者": ["初心者", "初めて", "入門", "簡単", "やさしい", "優しい", "誰でも"]
        }
        
        search_words = synonyms.get(q, [q])
        word_conditions = []
        for word in search_words:
            search_pattern = '%' + word + '%'
            params.extend([search_pattern] * 6)
            word_conditions.append("""(
                g.title ILIKE %s OR COALESCE(g.description, '') ILIKE %s OR EXISTS (
                    SELECT 1 FROM posts sp WHERE sp.game_id = g.id AND (
                        COALESCE(sp.catchphrase, '') ILIKE %s OR COALESCE(sp.target_audience, '') ILIKE %s OR COALESCE(sp.play_time, '') ILIKE %s OR COALESCE(sp.content, '') ILIKE %s
                    )
                )
            )""")
        query += " AND (" + " OR ".join(word_conditions) + ")"

    if genre: query += " AND g.genre = %s"; params.append(genre)
    if platform: query += " AND g.platform ILIKE %s"; params.append('%' + platform + '%')
    
    with get_db_connection() as conn:
        games = conn.execute(query + f" ORDER BY {order_clause}", params).fetchall()
        weekly_ranking = conn.execute('''SELECT g.id, g.title, g.image_url, COALESCE(SUM(p.likes + p.wanna_play + p.agree), 0) as weekly_likes FROM games g JOIN posts p ON g.id = p.game_id WHERE p.created_at >= NOW() - INTERVAL '7 days' GROUP BY g.id ORDER BY weekly_likes DESC, g.created_at DESC LIMIT 5''').fetchall()
        requests = conn.execute('SELECT * FROM requests ORDER BY created_at DESC LIMIT 5').fetchall()
        
    return render_page(request, INDEX_HTML, is_top=True, games=games, q=q, genre=genre, platform=platform, sort=sort, weekly_ranking=weekly_ranking, requests=requests)

@app.get("/games/random")
def random_game():
    with get_db_connection() as conn:
        game = conn.execute('SELECT id FROM games ORDER BY RANDOM() LIMIT 1').fetchone()
    if game: return RedirectResponse(url=f"/games/{game['id']}", status_code=303)
    return RedirectResponse(url="/", status_code=303)

@app.get("/games/new")
def new_game_form(request: Request, title: str = ""):
    return render_page(request, NEW_GAME_HTML, page_title="ゲームを追加する - Oshi-Ge", title=title)

@app.post("/games/new")
def create_game(
    request: Request,
    title: str = Form(...), description: str = Form(""), genre: str = Form(""), platform: str = Form(""), image_base64: str = Form(""),
    developer_x_id: str = Form(""), username: str = Form(...), catchphrase: str = Form(...), target_audience: str = Form(""), play_time: str = Form(""), content: str = Form(...), spoiler_level: int = Form(...),
    oshi_points: List[str] = Form(default=[])
):
    if not check_rate_limit(request):
        return HTMLResponse("<script>alert('連続投稿は制限されています。少し時間をおいてから再度お試しください。');history.back();</script>")
    if image_base64 and len(image_base64) > 6600000:
        return HTMLResponse("<script>alert('画像サイズが大きすぎます（5MB制限）。別の画像をご利用ください。');history.back();</script>")

    image_url = upload_image_to_supabase(image_base64)
    points_str = ",".join(oshi_points)
    
    with get_db_connection() as conn:
        if conn.execute('SELECT id FROM games WHERE LOWER(title) = LOWER(%s)', (title,)).fetchone():
            return render_page(request, NEW_GAME_HTML, error_msg=f"「{title}」は既に登録されています。", title=title, description=description, genre=genre, platform=platform, developer_x_id=developer_x_id, page_title="ゲームを追加する - Oshi-Ge")
        
        cursor_game = conn.execute('INSERT INTO games (title, description, genre, platform, image_url, developer_x_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id', (title, description, genre, platform, image_url, developer_x_id))
        game_id = cursor_game.fetchone()["id"]
        
        cursor_post = conn.execute('''INSERT INTO posts (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, oshi_points) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''', (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, points_str))
        post_id = cursor_post.fetchone()["id"]
        conn.commit()
    
    res = RedirectResponse(url=f"/games/{game_id}?posted={post_id}", status_code=303)
    my_posts = get_secure_cookie_list(request, "my_posts")
    my_posts.append(post_id)
    set_secure_cookie_list(res, "my_posts", my_posts)
    return res

@app.get("/games/{game_id}/edit")
def edit_game_form(request: Request, game_id: int):
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
    if not game: raise HTTPException(status_code=404, detail="Game not found")
    return render_page(request, EDIT_GAME_HTML, game=game, page_title=f"{game['title']}の編集 - Oshi-Ge")

@app.post("/games/{game_id}/edit")
def update_game(request: Request, game_id: int, title: str = Form(...), description: str = Form(""), genre: str = Form(""), platform: str = Form(""), developer_x_id: str = Form(""), image_base64: str = Form("")):
    if image_base64 and len(image_base64) > 6600000:
        return HTMLResponse("<script>alert('画像サイズが大きすぎます（5MB制限）。別の画像をご利用ください。');history.back();</script>")

    with get_db_connection() as conn:
        game = conn.execute('SELECT image_url FROM games WHERE id = %s', (game_id,)).fetchone()
        if not game: raise HTTPException(status_code=404)
        
        image_url = game['image_url']
        if image_base64:
            new_url = upload_image_to_supabase(image_base64)
            if new_url: image_url = new_url

        conn.execute('UPDATE games SET title = %s, description = %s, genre = %s, platform = %s, image_url = %s, developer_x_id = %s WHERE id = %s', (title, description, genre, platform, image_url, developer_x_id, game_id))
        conn.commit()
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@app.get("/games/{game_id}")
def read_game(request: Request, game_id: int, sort: str = "likes"):
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
        if not game: raise HTTPException(status_code=404, detail="Game not found")
        order_str = 'created_at DESC' if sort == 'new' else '(likes + wanna_play + agree) DESC, created_at DESC'
        posts = conn.execute(f'SELECT * FROM posts WHERE game_id = %s ORDER BY {order_str}', (game_id,)).fetchall()
    
    my_posts = get_secure_cookie_list(request, "my_posts")
    bookmarks = get_secure_cookie_list(request, "bookmarks")
    
    game_title_tag = f"{game['title']} の評価・感想・ネタバレなし布教 - Oshi-Ge"
    og_desc = game['description'] if game['description'] else f"『{game['title']}』のおすすめ布教ページです。ネタバレなしで魅力をお伝えします。"
    
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    base_url = f"{scheme}://{host}" if host else ""
    og_img = f"{base_url}/games/{game_id}/ogp.png"
    
    return render_page(request, GAME_HTML, game=game, posts=posts, sort=sort, my_posts=my_posts, is_bookmarked=(game_id in bookmarks), page_title=game_title_tag, og_description=og_desc, og_image=og_img, game_schema=game)

@app.post("/games/{game_id}/posts")
def create_post(request: Request, game_id: int, username: str = Form(...), catchphrase: str = Form(...), target_audience: str = Form(""), play_time: str = Form(""), content: str = Form(...), spoiler_level: int = Form(...), oshi_points: List[str] = Form(default=[])):
    if not check_rate_limit(request):
        return HTMLResponse("<script>alert('連続投稿は制限されています。少し時間をおいてから再度お試しください。');history.back();</script>")
    
    points_str = ",".join(oshi_points)
    with get_db_connection() as conn:
        if not conn.execute('SELECT id FROM games WHERE id = %s', (game_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Game not found")

        cursor = conn.execute('''INSERT INTO posts (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, oshi_points) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''', (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, points_str))
        post_id = cursor.fetchone()["id"]
        conn.commit()
        
    res = RedirectResponse(url=f"/games/{game_id}?posted={post_id}", status_code=303)
    my_posts = get_secure_cookie_list(request, "my_posts")
    my_posts.append(post_id)
    set_secure_cookie_list(res, "my_posts", my_posts)
    return res

@app.get("/games/{game_id}/posts/{post_id}/edit")
def edit_post_form(request: Request, game_id: int, post_id: int):
    my_posts = get_secure_cookie_list(request, "my_posts")
    if post_id not in my_posts: 
        return HTMLResponse(f"<script>alert('投稿の編集権限が確認できませんでした（Cookieが無効化されている可能性があります）。');location.href='/games/{game_id}';</script>")
    
    with get_db_connection() as conn:
        post = conn.execute('SELECT * FROM posts WHERE id = %s AND game_id = %s', (post_id, game_id)).fetchone()
    if not post: raise HTTPException(status_code=404)
    return render_page(request, EDIT_POST_HTML, game_id=game_id, post=post, page_title="布教の編集 - Oshi-Ge")

@app.post("/games/{game_id}/posts/{post_id}/edit")
def update_post(
    request: Request,
    game_id: int,
    post_id: int,
    username: str = Form(...),
    catchphrase: str = Form(...),
    target_audience: str = Form(""),
    play_time: str = Form(""),
    content: str = Form(...),
    spoiler_level: int = Form(...),
    oshi_points: List[str] = Form(default=[])
):
    my_posts = get_secure_cookie_list(request, "my_posts")
    if post_id not in my_posts:
        return HTMLResponse(f"<script>alert('投稿の編集権限が確認できませんでした（Cookieが無効化されている可能性があります）。');location.href='/games/{game_id}';</script>")
    
    points_str = ",".join(oshi_points) if oshi_points else ""
    with get_db_connection() as conn:
        conn.execute('''UPDATE posts SET username = %s, catchphrase = %s, target_audience = %s, play_time = %s, content = %s, spoiler_level = %s, oshi_points = %s WHERE id = %s AND game_id = %s''', (username, catchphrase, target_audience, play_time, content, spoiler_level, points_str, post_id, game_id))
        conn.commit()
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@app.post("/posts/{post_id}/report")
def report_post(post_id: int, reason: str = Form(...)):
    with get_db_connection() as conn:
        if not conn.execute('SELECT id FROM posts WHERE id = %s', (post_id,)).fetchone():
            raise HTTPException(status_code=404)
        conn.execute('INSERT INTO reports (post_id, reason) VALUES (%s, %s)', (post_id, reason))
        conn.commit()
    return JSONResponse({"status": "ok"})

@app.post("/games/{game_id}/posts/{post_id}/react/{react_type}")
def react_post(game_id: int, post_id: int, react_type: str):
    valid_types = ["likes", "wanna_play", "agree"]
    if react_type not in valid_types:
        raise HTTPException(status_code=400)
        
    with get_db_connection() as conn:
        if not conn.execute('SELECT id FROM posts WHERE id = %s AND game_id = %s', (post_id, game_id)).fetchone():
            raise HTTPException(status_code=404)
            
        cursor = conn.execute(f'UPDATE posts SET {react_type} = {react_type} + 1 WHERE id = %s RETURNING {react_type}', (post_id,))
        count = cursor.fetchone()[react_type]
        conn.commit()
    return {"count": count}

@app.post("/games/{game_id}/bookmark")
def toggle_bookmark(request: Request, game_id: int):
    bookmarks = get_secure_cookie_list(request, "bookmarks")
    is_bookmarked = False
    if game_id in bookmarks: bookmarks.remove(game_id)
    else: bookmarks.append(game_id); is_bookmarked = True
    
    res = JSONResponse(content={"bookmarked": is_bookmarked})
    set_secure_cookie_list(res, "bookmarks", bookmarks)
    return res

@app.post("/requests")
def create_request(request: Request, title: str = Form(...), username: str = Form("名無しのゲーマー")):
    if not check_rate_limit(request):
        return HTMLResponse("<script>alert('連続投稿は制限されています。少し時間をおいてから再度お試しください。');history.back();</script>")
    with get_db_connection() as conn:
        conn.execute('INSERT INTO requests (title, username) VALUES (%s, %s)', (title, username))
        conn.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/mypage")
def mypage(request: Request):
    my_posts_ids = get_secure_cookie_list(request, "my_posts")
    bookmarks = get_secure_cookie_list(request, "bookmarks")
    
    my_posts_list = []
    bookmarked_games = []
    
    with get_db_connection() as conn:
        if my_posts_ids:
            my_posts_list = conn.execute("SELECT p.*, g.title as game_title, g.image_url as game_image_url, g.genre as game_genre, g.platform as game_platform, g.developer_x_id as game_developer_x_id FROM posts p JOIN games g ON p.game_id = g.id WHERE p.id = ANY(%s) ORDER BY p.created_at DESC", (my_posts_ids,)).fetchall()
        if bookmarks:
            bookmarked_games = conn.execute("SELECT * FROM games WHERE id = ANY(%s) ORDER BY created_at DESC", (bookmarks,)).fetchall()
            
    total_likes = sum(post.get("likes", 0) + post.get("wanna_play", 0) + post.get("agree", 0) for post in my_posts_list) if my_posts_list else 0
            
    return render_page(request, MYPAGE_HTML, my_posts_list=my_posts_list, bookmarked_games=bookmarked_games, total_likes=total_likes, page_title="マイページ - Oshi-Ge")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
