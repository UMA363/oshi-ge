import os
import urllib.request
import uvicorn
import base64
import uuid
from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Template
import psycopg
from psycopg.rows import dict_row

app = FastAPI()

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode="require")

def upload_image_to_supabase(base64_data: str) -> str:
    """Base64画像を受け取り、Supabase Storageにアップロードして公開URLを返す"""
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
    except Exception as e:
        print("Image upload error:", e)
        return ""

# --- 1. データベース初期化 ---
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
            
            conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS platform TEXT")
            conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS image_url TEXT")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS catchphrase TEXT")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS target_audience TEXT")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS play_time TEXT")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS likes INTEGER DEFAULT 0")
            conn.commit()
    except Exception as e:
        print("DB Init error:", e)

init_db()

# --- 1.5 画像中継プロキシ ---
@app.get("/proxy-image")
async def proxy_image(url: str):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = response.read()
            content_type = response.headers.get('Content-Type', 'image/jpeg')
            return Response(content=data, media_type=content_type)
    except Exception:
        raise HTTPException(status_code=404)

# --- 2. HTML・CSS・JSテンプレート ---
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
.btn-x { background-color: #000; color: #fff; padding: 0.5rem 1rem; font-size: 0.9rem; border: 1px solid #333; }
.btn-line { background-color: #06C755; color: #fff; padding: 0.5rem 1rem; font-size: 0.9rem; border: 1px solid #05a546;}
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
.btn-like { background: transparent; border: 1px solid var(--border); color: var(--text-main); padding: 0.4rem 0.8rem; border-radius: 20px; cursor: pointer; font-weight: bold; }
.btn-like.liked { background: rgba(245, 158, 11, 0.1); border-color: var(--accent); color: var(--accent); }

/* 検索ボタンのハイライト実装 */
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
}

.discover-panel { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; }
.discover-panel h3 { margin-bottom: 0.9rem; color: var(--accent); }
.quick-filter-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.6rem; }
.quick-filter { display: flex; align-items: center; justify-content: center; min-height: 46px; padding: 0.6rem 0.8rem; background: #0f172a; border: 1px solid var(--border); border-radius: 10px; color: var(--text-main); text-decoration: none; font-weight: bold; text-align: center; transition: 0.2s; }
.quick-filter:hover { border-color: var(--accent); color: var(--accent); transform: translateY(-2px); }
.promo-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.78); display: flex; align-items: center; justify-content: center; padding: 1rem; z-index: 9999; }
.promo-modal-box { width: min(900px, 100%); max-height: 95vh; overflow-y: auto; background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; padding: 1rem; box-sizing: border-box; }
.promo-modal-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.8rem; }
.promo-modal-head h3 { margin: 0; color: var(--accent); }
.promo-canvas-wrap { background: #0b1120; border-radius: 10px; padding: 0.75rem; border: 1px solid var(--border); }
#promoCanvas { display: block; width: 100%; height: auto; border-radius: 8px; }
.promo-modal-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 0.8rem; }
"""

JS = """
function toggleSpoiler(btn) {
    const txt = btn.nextElementSibling;
    if (txt.style.display === "none") { txt.style.display = "block"; btn.style.opacity = "0.7"; btn.innerText = "クリックして閉じる"; } 
    else {
        txt.style.display = "none"; btn.style.opacity = "1";
        if (btn.classList.contains('warning')) btn.innerText = "🔒 軽微なネタバレ【クリックして表示】";
        else if (btn.classList.contains('danger')) btn.innerText = "⚠️ ネタバレあり【クリックして表示】";
    }
}
function shareGameToX(title) { 
    const text = encodeURIComponent(`次に遊ぶ神ゲーを探している方へ🎮\\n『${title}』のおすすめ布教ページです！👇\\n#OshiGe\\n`);
    window.open(`https://x.com/intent/tweet?text=${text}&url=${encodeURIComponent(window.location.href)}`, '_blank'); 
}
function shareGameToLine(title) { 
    const text = encodeURIComponent(`次に遊ぶ神ゲーを探している方へ🎮\\n『${title}』のおすすめ布教ページです！👇\\n#OshiGe\\n`);
    window.open(`https://line.me/R/msg/text/?${text}${encodeURIComponent(window.location.href)}`, '_blank'); 
}
function sharePost(btn, platform) {
    const gameId = btn.getAttribute('data-id');
    const title = btn.getAttribute('data-title') || 'おすすめゲーム';
    const catchphrase = btn.getAttribute('data-catch') || '';
    const content = btn.getAttribute('data-content') || '';
    const spoilerLevel = Number(btn.getAttribute('data-spoiler') || '0');
    const url = window.location.origin + '/games/' + gameId;

    let text = `このゲーム、もっと知られてほしい。\\n\\n🎮 『${title}』`;
    if (catchphrase) text += `\\n\\n「${catchphrase}」`;

    if (spoilerLevel === 0 && content.trim()) {
        let impression = content.trim();
        if (Array.from(impression).length > 20) {
            impression = Array.from(impression).slice(0, 20).join('') + '…';
        }
        text += `\\n\\n💬「${impression}」`;
    } else if (spoilerLevel === 1) {
        text += `\\n\\n🔒 軽微なネタバレを含みます`;
    } else if (spoilerLevel === 2) {
        text += `\\n\\n⚠️ ネタバレあり`;
    }
    text += `\\n\\n布教内容はこちら👇\\n${url}\\n\\n#OshiGe`;

    if (platform === 'x') {
        window.open(`https://x.com/intent/tweet?text=${encodeURIComponent(text)}`, '_blank');
    } else if (platform === 'line') {
        window.open(`https://line.me/R/msg/text/?${encodeURIComponent(text)}`, '_blank');
    }
}
async function likePost(gId, pId, btn) {
    if (btn.classList.contains('liked')) return;
    try {
        const res = await fetch(`/games/${gId}/posts/${pId}/like`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            btn.querySelector('span').innerText = data.likes;
            btn.classList.add('liked'); localStorage.setItem(`liked_${pId}`, 'true');
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
function updatePlatform(f) { f.querySelector('.platform-hidden').value = Array.from(f.querySelectorAll('.platform-cb:checked')).map(cb => cb.value).join(','); }

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('.btn-like').forEach(b => { if (localStorage.getItem(`liked_${b.getAttribute('data-post-id')}`)) b.classList.add('liked'); });
    document.querySelectorAll('.platform-hidden').forEach(h => {
        if (!h.value) return;
        const p = h.value.split(',').map(s => s.trim());
        h.closest('form').querySelectorAll('.platform-cb').forEach(cb => { if (p.includes(cb.value)) cb.checked = true; });
    });

    // 画像の自動リサイズとBase64変換
    const imageUpload = document.getElementById('image_upload');
    if (imageUpload) {
        imageUpload.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(event) {
                const img = new Image();
                img.onload = function() {
                    const canvas = document.createElement('canvas');
                    let width = img.width;
                    let height = img.height;
                    const MAX_WIDTH = 800; // 最適なサイズに自動縮小
                    if (width > MAX_WIDTH) {
                        height = Math.round((height * MAX_WIDTH) / width);
                        width = MAX_WIDTH;
                    }
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    const dataUrl = canvas.toDataURL('image/webp', 0.8); // 80%の画質でWebPに圧縮
                    document.getElementById('image_base64').value = dataUrl;
                    document.getElementById('preview_img').src = dataUrl;
                    document.getElementById('image_preview').style.display = 'block';
                }
                img.src = event.target.result;
            }
            reader.readAsDataURL(file);
        });
    }
});

function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

function openPromoCard(title, catchphrase, targetAudience, playTime, username, genre, platform, spoilerLevel, content, imageUrl) {
    const modal = document.getElementById('promo-card-modal');
    if (!modal) return;
    modal.style.display = 'flex';
    modal.dataset.title = title || '';
    modal.dataset.catchphrase = catchphrase || 'このゲーム、ぜひ遊んでほしい！';
    modal.dataset.target = targetAudience || '';
    modal.dataset.playTime = playTime || '';
    modal.dataset.username = username || '名無しの布教者';
    modal.dataset.genre = genre || '';
    modal.dataset.platform = platform || '';
    modal.dataset.spoiler = String(spoilerLevel || 0);
    modal.dataset.content = content || '';
    modal.dataset.imageUrl = imageUrl || ''; 
    
    const dlBtn = document.getElementById('promo-dl-btn');
    const instruction = document.getElementById('promo-instruction');
    if (isMobileDevice()) {
        if(dlBtn) dlBtn.style.display = 'none';
        if(instruction) instruction.innerHTML = '📱 <strong>スマホの方は、このカードをスクリーンショットで保存してください！</strong><br>SNSへの共有は各共有ボタンからどうぞ。';
    } else {
        if(dlBtn) dlBtn.style.display = 'inline-block';
        if(instruction) instruction.innerHTML = 'このカードは「画像を保存」ボタンからダウンロードできます。SNSへの共有は各共有ボタンからどうぞ。';
    }
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
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
}

async function drawPromoCard() {
    const modal = document.getElementById('promo-card-modal');
    const canvas = document.getElementById('promoCanvas');
    if (!modal || !canvas) return;

    const ctx = canvas.getContext('2d');
    const W = 1200, H = 960; 
    canvas.width = W;
    canvas.height = H;

    const title = modal.dataset.title || 'おすすめゲーム';
    const catchphrase = modal.dataset.catchphrase || '';
    const target = modal.dataset.target || '';
    const playTime = modal.dataset.playTime || '';
    const genre = modal.dataset.genre || '';
    const platform = modal.dataset.platform || '';
    const username = modal.dataset.username || '名無しの布教者';
    const spoiler = Number(modal.dataset.spoiler || 0);
    const imageUrl = modal.dataset.imageUrl || '';
    let contentRaw = modal.dataset.content || '';

    if (spoiler > 0) contentRaw = '';

    const bg = ctx.createLinearGradient(0, 0, W, H);
    bg.addColorStop(0, '#111827');
    bg.addColorStop(0.55, '#0f172a');
    bg.addColorStop(1, '#020617');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    if (imageUrl) {
        try {
            const img = new Image();
            img.crossOrigin = 'Anonymous'; 
            img.src = '/proxy-image?url=' + encodeURIComponent(imageUrl);
            
            await new Promise((resolve, reject) => {
                img.onload = resolve;
                img.onerror = reject;
            });
            
            const imgRatio = img.width / img.height;
            const targetRatio = W / 550;
            let drawW, drawH, drawX, drawY;
            
            if (imgRatio > targetRatio) {
                drawH = 550; drawW = img.width * (550 / img.height);
                drawX = (W - drawW) / 2; drawY = 0;
            } else {
                drawW = W; drawH = img.height * (W / img.width);
                drawX = 0; drawY = (550 - drawH) / 2;
            }
            
            ctx.save();
            ctx.globalAlpha = 0.5;
            ctx.beginPath();
            ctx.rect(0, 0, W, 550);
            ctx.clip();
            ctx.drawImage(img, drawX, drawY, drawW, drawH);
            ctx.restore();
            
            const fade = ctx.createLinearGradient(0, 0, 0, 550);
            fade.addColorStop(0, 'rgba(15, 23, 42, 0)');
            fade.addColorStop(0.6, 'rgba(15, 23, 42, 0.6)');
            fade.addColorStop(1, '#0f172a');
            ctx.fillStyle = fade;
            ctx.fillRect(0, 0, W, 550);
            
        } catch(e) {
            console.error("Image load failed", e);
            drawFallbackGlow(ctx);
        }
    } else {
        drawFallbackGlow(ctx);
    }

    function drawFallbackGlow(ctx) {
        const glow = ctx.createRadialGradient(1030, 100, 20, 1030, 100, 430);
        glow.addColorStop(0, 'rgba(245,158,11,0.22)');
        glow.addColorStop(1, 'rgba(245,158,11,0)');
        ctx.fillStyle = glow;
        ctx.fillRect(650, 0, 550, 500);
    }

    ctx.fillStyle = '#f59e0b';
    ctx.fillRect(0, 0, 14, H);

    ctx.fillStyle = '#f59e0b';
    ctx.font = '900 28px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
    ctx.fillText('OSHI-GE', 58, 62);
    ctx.fillStyle = '#cbd5e1';
    ctx.font = '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
    ctx.fillText('GAME RECOMMENDATION CARD', 58, 91);

    ctx.fillStyle = '#ffffff';
    ctx.font = '900 58px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
    ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
    ctx.shadowBlur = 10;
    const titleLines = wrapCanvasText(ctx, title, 58, 158, 1080, 70, 2);
    ctx.shadowBlur = 0;

    const quoteY = 305 + Math.max(0, titleLines - 1) * 20;
    drawRoundRect(ctx, 58, quoteY, 1084, 158, 18);
    ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(245,158,11,0.65)';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = '#f59e0b';
    ctx.font = '900 20px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
    ctx.fillText('このゲームを一言で言うと', 88, quoteY + 38);

    ctx.fillStyle = '#fff7ed';
    ctx.font = '900 34px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
    wrapCanvasText(ctx, '「' + catchphrase + '」', 88, quoteY + 84, 1015, 46, 2);

    let y = quoteY + 200;

    const cleanContent = contentRaw.replace(/\s+/g, ' ').trim();
    if (cleanContent.length >= 15) {
        ctx.fillStyle = '#cbd5e1';
        ctx.font = '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
        ctx.fillText('💬 布教者の声', 60, y);
        y += 28;

        ctx.fillStyle = '#f8fafc';
        ctx.font = '400 24px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
        const linesDrawn = wrapCanvasText(ctx, cleanContent, 60, y + 6, 1080, 36, 3);
        y += (linesDrawn * 36) + 36;
    } else {
        y += 10;
    }

    if (target) {
        ctx.fillStyle = '#94a3b8';
        ctx.font = '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
        ctx.fillText('おすすめ対象', 60, y);
        y += 30;

        drawRoundRect(ctx, 58, y, 1084, 52, 10);
        ctx.fillStyle = '#1e293b';
        ctx.fill();
        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = '#f8fafc';
        ctx.font = '700 22px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
        wrapCanvasText(ctx, target, 78, y + 34, 1040, 28, 1);
        y += 82;
    }

    const chips = [];
    if (playTime) chips.push('PLAY ' + playTime);
    if (genre) chips.push(genre);
    if (platform) chips.push(platform);

    if (chips.length) {
        let x = 58;
        ctx.font = '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

        for (const chip of chips) {
            const width = Math.min(340, Math.max(105, ctx.measureText(chip).width + 38));
            if (x + width > 1142) {
                x = 58;
                y += 66;
            }

            drawRoundRect(ctx, x, y, width, 48, 24);
            ctx.fillStyle = '#172033';
            ctx.fill();
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 1;
            ctx.stroke();

            ctx.fillStyle = '#cbd5e1';
            ctx.fillText(chip, x + 19, y + 31);
            x += width + 12;
        }
        y += 72;
    }

    if (spoiler > 0) {
        const spoilerText = spoiler === 2 ? 'WARNING  ネタバレあり' : 'CAUTION  軽微なネタバレあり';
        ctx.font = '900 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
        const sw = ctx.measureText(spoilerText).width + 36;
        drawRoundRect(ctx, 58, Math.min(y, H - 150), sw, 44, 22);
        ctx.fillStyle = spoiler === 2 ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)';
        ctx.fill();
        ctx.strokeStyle = spoiler === 2 ? 'rgba(239,68,68,0.65)' : 'rgba(245,158,11,0.65)';
        ctx.stroke();
        ctx.fillStyle = spoiler === 2 ? '#fca5a5' : '#fde68a';
        ctx.fillText(spoilerText, 76, Math.min(y, H - 150) + 29);
        y += 72;
    }

    const footerY = Math.max(y + 20, H - 90);
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(58, footerY);
    ctx.lineTo(1142, footerY);
    ctx.stroke();

    ctx.fillStyle = '#64748b';
    ctx.font = '18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
    ctx.fillText('布教者：' + username, 58, footerY + 36);

    ctx.fillStyle = '#f59e0b';
    ctx.font = '900 20px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';
    const brand = 'Oshi-Ge';
    ctx.fillText(brand, 1142 - ctx.measureText(brand).width, footerY + 36);
}

function downloadPromoCard() {
    const canvas = document.getElementById('promoCanvas');
    if (!canvas) return;
    const title = document.getElementById('promo-card-modal').dataset.title || 'oshi-ge';
    const safeName = title.replace(/[\\\\/:*?"<>|]/g, '_');
    const a = document.createElement('a');
    a.download = `Oshi-Ge_${safeName}.png`;
    a.href = canvas.toDataURL('image/png');
    a.click();
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closePromoCard();
});
"""

BASE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ page_title | default("Oshi-Ge | ネタバレなしゲーム布教サイト") }}</title>
    <meta name="description" content="{{ og_description | default('未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。') }}">
    <meta property="og:type" content="website">
    <meta property="og:title" content="{{ page_title | default('Oshi-Ge | ネタバレなしゲーム布教サイト') }}">
    <meta property="og:description" content="{{ og_description | default('未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。') }}">
    {% if og_image %}
    <meta property="og:image" content="{{ og_image }}">
    <meta name="twitter:card" content="summary_large_image">
    {% else %}
    <meta name="twitter:card" content="summary">
    {% endif %}
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text x=%2250%%22 y=%2250%%22 style=%22dominant-baseline:central;text-anchor:middle;font-size:90px;%22>🎮</text></svg>">
    
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-XRFBSR9HSR"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-XRFBSR9HSR');
    </script>
    
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6608111802250449" crossorigin="anonymous"></script>
    
    <style>{{ css }}</style>
</head>
<body>
    <header class="header-container">
        <h1><a href="/">🎮 Oshi-Ge</a></h1>
        <div style="display:flex; gap: 1rem;">
            <a href="/games/new" class="btn btn-primary btn-small" style="color: #ffffff;">＋ ゲームを布教する</a>
            <a href="/mypage" class="btn btn-outline btn-small" style="color:var(--text-main);">👤 マイページ</a>
        </div>
    </header>
    {% if is_top %}
    <div class="hero">
        <h2>誰かの人生を変える1本を。</h2>
        <p>未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。</p>
        <form action="/" method="get" class="search-bar-advanced">
            <div class="search-inputs">
                <input type="text" name="q" placeholder="タイトル検索..." value="{{ q }}">
                <select name="genre">
                    <option value="">全ジャンル</option>
                    {% set genres_list = ["RPG", "アクション", "アドベンチャー", "シミュレーション", "FPS / TPS", "パズル", "ノベル", "ホラー", "インディー", "その他 / 不明"] %}
                    {% for g in genres_list %}<option value="{{ g }}" {% if genre == g %}selected{% endif %}>{{ g }}</option>{% endfor %}
                </select>
                <select name="platform">
                    <option value="">全機種</option>
                    {% set platforms_list = ["PC", "Switch", "Switch2", "PS5", "Xbox", "スマホ", "その他"] %}
                    {% for p in platforms_list %}<option value="{{ p }}" {% if platform == p %}selected{% endif %}>{{ p }}</option>{% endfor %}
                </select>
                <button type="submit" class="btn btn-primary">絞り込み</button>
            </div>
        </form>
        <a href="/games/random" class="btn btn-outline" style="margin-top: 1rem; border-style: dashed;">🎲 ランダムにゲームを探す</a>
    </div>
    {% endif %}
    <main>{{ content }}</main>
    <script>{{ js }}</script>
</body>
</html>
"""

INDEX_HTML = """
<div class="discover-panel">
    <h3>🔎 目的からゲームを探す</h3>
    <div style="color: var(--text-sub); margin-bottom: 0.9rem;">タイトルを知らなくても大丈夫。気分や好みから探せます。</div>
    <div class="quick-filter-grid">
        <a class="quick-filter {% if q == 'ストーリー' %}active{% endif %}" href="/?q=ストーリー">📖 ストーリー重視</a>
        <a class="quick-filter {% if q == '泣ける' %}active{% endif %}" href="/?q=泣ける">😭 泣ける</a>
        <a class="quick-filter {% if q == '一人' %}active{% endif %}" href="/?q=一人">👤 一人で遊びたい</a>
        <a class="quick-filter {% if q == '短時間' %}active{% endif %}" href="/?q=短時間">⏱ 短時間</a>
        <a class="quick-filter {% if q == 'ホラー' %}active{% endif %}" href="/?q=ホラー">😱 ホラー</a>
        <a class="quick-filter {% if q == 'インディー' %}active{% endif %}" href="/?q=インディー">💎 インディー</a>
        <a class="quick-filter {% if q == '初心者' %}active{% endif %}" href="/?q=初心者">🌱 初心者向け</a>
        <a class="quick-filter" href="/games/random">🎲 完全ランダム</a>
    </div>
</div>
<div class="layout-wrapper">
    <div class="main-column">
        <div style="display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">
            <h3 style="margin:0;">布教されているゲーム</h3>
            <div style="display: flex; gap: 0.5rem;">
                <a href="?sort=new{% if q %}&q={{ q }}{% endif %}{% if genre %}&genre={{ genre }}{% endif %}{% if platform %}&platform={{ platform }}{% endif %}" class="btn btn-outline btn-small" style="{% if sort == 'new' or not sort %}background:rgba(245,158,11,0.1); border-color:var(--accent); color:var(--accent);{% endif %}">🕒 最新順</a>
                <a href="?sort=posts{% if q %}&q={{ q }}{% endif %}{% if genre %}&genre={{ genre }}{% endif %}{% if platform %}&platform={{ platform }}{% endif %}" class="btn btn-outline btn-small" style="{% if sort == 'posts' %}background:rgba(245,158,11,0.1); border-color:var(--accent); color:var(--accent);{% endif %}">🔥 投稿数順</a>
            </div>
        </div>
        <div class="game-grid">
            {% for game in games %}
                <div class="game-card" onclick="location.href='/games/{{ game.id }}'">
                    {% if game.image_url %}<img src="{{ game.image_url }}" alt="" class="game-thumbnail" onerror="this.style.display='none'">
                    {% else %}<div class="game-thumbnail empty">NO IMAGE</div>{% endif %}
                    <div class="game-card-body">
                        <h3 style="font-size: 1.2rem; margin: 0 0 0.5rem 0; color: var(--text-main);">{{ game.title }}</h3>
                        <div style="margin-bottom: 1rem;">
                            <span class="tag genre" style="margin:0;">🎮 {{ game.genre }}</span>
                            <span class="tag" style="margin:0; background: transparent; border: 1px solid var(--border); color: var(--text-sub);">💬 布教 {{ game.post_count }}件</span>
                            {% if game.platform %}{% for p in game.platform.split(',') %}{% if p.strip() %}<span class="tag" style="margin:0; margin-top:0.3rem;">💻 {{ p.strip() }}</span>{% endif %}{% endfor %}{% endif %}
                        </div>
                        {% if game.latest_catchphrase %}<div class="latest-catchphrase">「{{ game.latest_catchphrase }}」</div>{% endif %}
                    </div>
                </div>
            {% else %}
                <div style="grid-column: 1 / -1; text-align: center; color: var(--text-sub); padding: 3rem; background: var(--card-bg); border-radius:12px;"><p>条件に合うゲームが見つかりませんでした。</p></div>
            {% endfor %}
        </div>
    </div>
    <div class="sidebar-column">
        <div class="card" style="border-color: var(--accent); padding: 1.2rem;">
            <h3 style="margin-top: 0; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">👑 今週の人気ゲーム</h3>
            <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;">
                {% for item in weekly_ranking %}
                <div style="display: flex; gap: 1rem; align-items: center; cursor: pointer;" onclick="location.href='/games/{{ item.id }}'">
                    <div style="width: 60px; height: 60px; border-radius: 8px; overflow: hidden; background: #334155; flex-shrink: 0;">
                        {% if item.image_url %}<img src="{{ item.image_url }}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'">
                        {% else %}<div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 0.6rem; color: #94a3b8;">NO IMG</div>{% endif %}
                    </div>
                    <div>
                        <div style="font-weight: bold; color: var(--text-main); font-size: 0.95rem; margin-bottom: 0.2rem;">{{ item.title }}</div>
                        <div style="font-size: 0.8rem; color: var(--accent);">🔥 今週 {{ item.weekly_posts }} 件の布教</div>
                    </div>
                </div>
                {% else %}<div style="color: var(--text-sub); font-size: 0.9rem;">今週の布教はまだありません。</div>{% endfor %}
            </div>
        </div>
    </div>
</div>
"""

GAME_HTML = """
<div class="card" style="position: relative;">
    <div class="game-header-row" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
        <h2 style="font-size: 2rem; margin: 0; font-weight: 900; word-break: break-all;">{{ game.title }}</h2>
        <div class="game-header-actions" style="display:flex; gap: 0.5rem; flex-shrink: 0;">
            <button type="button" class="btn-bookmark {% if is_bookmarked %}bookmarked{% endif %}" onclick="toggleBookmark({{ game.id }}, this)">
                {% if is_bookmarked %}🔖 お気に入り解除{% else %}🔖 お気に入りに追加{% endif %}
            </button>
            <a href="/games/{{ game.id }}/edit" class="btn btn-outline btn-small" style="padding: 0.5rem 1rem;">⚙️ 編集</a>
        </div>
    </div>
    {% if game.image_url %}<div><img src="{{ game.image_url }}" class="game-hero-image" onerror="this.style.display='none'"></div>{% endif %}
    <div style="margin-bottom: 1.5rem;">
        <span class="tag genre">🎮 {{ game.genre }}</span>
        {% if game.platform %}{% for p in game.platform.split(',') %}{% if p.strip() %}<span class="tag">💻 {{ p.strip() }}</span>{% endif %}{% endfor %}{% endif %}
    </div>
    <div style="background: #0f172a; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;">
        <p style="margin: 0; white-space: pre-wrap; color: #cbd5e1;">{{ game.description }}</p>
    </div>
    
    <div style="display: flex; gap: 0.5rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
        <a href="https://www.amazon.co.jp/s?k={{ game.title }}&i=videogames&tag=oshige06-22" target="_blank" class="btn btn-outline btn-small" style="color: #f59e0b; border-color: rgba(245, 158, 11, 0.5);">🛒 Amazonで探す</a>
        <a href="https://search.rakuten.co.jp/search/mall/{{ game.title }}/?tg=101240" target="_blank" class="btn btn-outline btn-small" style="color: #ef4444; border-color: rgba(239, 68, 68, 0.5);">🛍 楽天市場で探す</a>
        <a href="https://store.steampowered.com/search/?term={{ game.title }}" target="_blank" class="btn btn-outline btn-small" style="color: #cbd5e1; border-color: rgba(203, 213, 225, 0.5);">🎮 Steamで探す</a>
    </div>

    <div style="display: flex; gap: 0.5rem; border-top: 1px solid var(--border); padding-top: 1.5rem;">
        <button type="button" class="btn btn-x" onclick="shareGameToX('{{ game.title }}')">𝕏 でゲームを共有</button>
        <button type="button" class="btn btn-line" onclick="shareGameToLine('{{ game.title }}')">LINE でゲームを共有</button>
    </div>
</div>

<details class="card" style="border-color: var(--accent); box-shadow: 0 0 15px rgba(245, 158, 11, 0.1);">
    <summary style="cursor: pointer; font-weight: bold; color: var(--accent); font-size: 1.1rem; user-select: none; outline: none;">
        🔥 このゲームを布教する（クリックして投稿フォームを開く）
    </summary>
    <form action="/games/{{ game.id }}/posts" method="post" style="margin-top: 1.5rem; border-top: 1px solid var(--border); padding-top: 1.5rem;">
        <div class="form-group"><label>布教ネーム（匿名可）:</label><input type="text" name="username" value="名無しの布教者" required></div>
        <div style="background: #0b1120; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;">
            <div class="form-group"><label style="color: var(--accent);">一言で布教すると？（必須）:</label><input type="text" name="catchphrase" required placeholder="例：最後まで遊んだときに、やってよかったと思える作品" style="border-color: rgba(245, 158, 11, 0.5);"></div>
            <div style="display: flex; gap: 1rem; margin-bottom: 0; flex-wrap: wrap;">
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>誰におすすめ？ <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="target_audience" placeholder="例：ストーリー重視の人"></div>
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>プレイ時間 <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="play_time" placeholder="例：10～15時間"></div>
            </div>
        </div>
        <div class="form-group">
            <label>ネタバレレベル（詳細コメントの公開設定）:</label>
            <div class="spoiler-radio-group">
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="0" checked> <span style="color:var(--safe)">Lv.0 ネタバレなし</span></div><span class="radio-desc">未プレイの人が読んでも問題ない内容</span></label>
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="1"> <span style="color:var(--warning)">Lv.1 軽微なネタバレ</span></div><span class="radio-desc">序盤の設定など、体験に多少影響する内容</span></label>
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="2"> <span style="color:var(--danger)">Lv.2 ネタバレあり</span></div><span class="radio-desc">ストーリー展開など、体験を大きく左右する内容</span></label>
            </div>
        </div>
        <div class="form-group"><label>布教コメントの詳細（必須）:</label><textarea name="content" rows="4" required placeholder="熱い思いをぶつけてください。"></textarea></div>
        <button type="submit" class="btn btn-primary" style="width: 100%; font-size:1.1rem; padding: 1rem;">布教を投稿する</button>
    </form>
</details>

<div>
    <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 1rem;">
        <h3 style="margin: 0;">みんなの布教</h3>
        <div style="display: flex; gap: 0.5rem;">
            <a href="?sort=likes" class="btn btn-outline btn-small" style="{% if sort == 'likes' or not sort %}background:rgba(245,158,11,0.1); border-color:var(--accent); color:var(--accent);{% endif %}">👍 おすすめ順</a>
            <a href="?sort=new" class="btn btn-outline btn-small" style="{% if sort == 'new' %}background:rgba(245,158,11,0.1); border-color:var(--accent); color:var(--accent);{% endif %}">🕒 新着順</a>
        </div>
    </div>
    {% for post in posts %}
    <div class="card post-card">
        <div class="post-header">
            <span class="post-author">👤 {{ post.username }}</span>
            <div style="display: flex; align-items: center; gap: 1rem;">
                <span>{{ post.created_at.strftime('%Y-%m-%d %H:%M') if post.created_at else '' }}</span>
                {% if post.id in my_posts %}<a href="/games/{{ game.id }}/posts/{{ post.id }}/edit" class="btn btn-outline btn-small" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">⚙ 編集</a>{% endif %}
            </div>
        </div>
        {% if post.catchphrase %}
        <div style="margin-bottom: 1.25rem;"><h4 class="catchphrase-text">「{{ post.catchphrase }}」</h4>
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; font-size: 0.85rem;">
                {% if post.target_audience %}<span class="meta-tag">🎯 {{ post.target_audience }}におすすめ</span>{% endif %}
                {% if post.play_time %}<span class="meta-tag">⏱ {{ post.play_time }}</span>{% endif %}
            </div>
        </div>
        {% endif %}
        {% if post.spoiler_level == 0 %}<div><span class="spoiler-badge safe">🔐 ネタバレなしの詳細</span><div class="post-content"><p>{{ post.content }}</p></div></div>
        {% elif post.spoiler_level == 1 %}<div><button type="button" class="spoiler-toggle-btn warning" onclick="toggleSpoiler(this)">🔒 軽微なネタバレの詳細【クリックして表示】</button><div class="spoiler-hidden-text" style="display: none;"><div class="post-content"><p>{{ post.content }}</p></div></div></div>
        {% elif post.spoiler_level == 2 %}<div><button type="button" class="spoiler-toggle-btn danger" onclick="toggleSpoiler(this)">⚠ ネタバレありの詳細【クリックして表示】</button><div class="spoiler-hidden-text" style="display: none;"><div class="post-content"><p>{{ post.content }}</p></div></div></div>{% endif %}
        
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; border-top: 1px dashed var(--border); padding-top: 0.75rem;">
            <div style="display: flex; gap: 0.5rem;">
                <button type="button" class="btn btn-outline btn-small" data-id="{{ game.id }}" data-title="{{ game.title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" onclick="sharePost(this, 'x')">𝕏 で共有</button>
                <button type="button" class="btn btn-outline btn-small" style="color:#06C755; border-color:rgba(6,199,85,0.5);" data-id="{{ game.id }}" data-title="{{ game.title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" onclick="sharePost(this, 'line')">LINE で共有</button>
                <button type="button" class="btn btn-outline btn-small" onclick='openPromoCard({{ game.title|tojson }}, {{ post.catchphrase|default("")|tojson }}, {{ post.target_audience|default("")|tojson }}, {{ post.play_time|default("")|tojson }}, {{ post.username|default("名無しの布教者")|tojson }}, {{ game.genre|default("")|tojson }}, {{ game.platform|default("")|tojson }}, {{ post.spoiler_level|default(0) }}, {{ post.content|default("")|tojson }}, {{ game.image_url|default("")|tojson }})'>🎴 布教カード</button>
            </div>
            <button type="button" class="btn-like" data-post-id="{{ post.id }}" onclick="likePost({{ game.id }}, {{ post.id }}, this)">👍 いいね <span>{{ post.likes | default(0) }}</span></button>
        </div>
    </div>
    {% else %}<div class="card" style="text-align: center; color: var(--text-sub); padding: 3rem 0; background: transparent; border: 1px dashed var(--border);"><p style="margin: 0;">まだ布教コメントがありません。<br>最初の布教者になりませんか？</p></div>{% endfor %}
</div>

<div id="promo-card-modal" class="promo-modal" style="display:none;" onclick="if(event.target===this) closePromoCard();">
    <div class="promo-modal-box">
        <div class="promo-modal-head">
            <h3>🎴 布教カード</h3>
            <button type="button" class="btn btn-outline btn-small" onclick="closePromoCard()">✕ 閉じる</button>
        </div>
        <div class="promo-canvas-wrap"><canvas id="promoCanvas" width="1200" height="960"></canvas></div>
        <div class="promo-modal-actions">
            <button type="button" id="promo-dl-btn" class="btn btn-primary" onclick="downloadPromoCard()">⬇️ 画像を保存</button>
            <button type="button" class="btn btn-outline" onclick="closePromoCard()">閉じる</button>
        </div>
        <div id="promo-instruction" style="color:var(--text-sub); font-size:0.9rem; margin-top:0.7rem;">
            このカードは「画像を保存」ボタンからダウンロードできます。SNSへの共有は各共有ボタンからどうぞ。
        </div>
    </div>
</div>
"""

MYPAGE_HTML = """
<div class="card">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">👤 マイページ</h2>
    <h3 style="color: var(--accent); margin-top: 2rem;">🔖 お気に入りに追加したゲーム</h3>
    <div class="game-grid" style="margin-bottom: 3rem;">
        {% for game in bookmarked_games %}
        <div class="game-card" onclick="location.href='/games/{{ game.id }}'">
            {% if game.image_url %}<img src="{{ game.image_url }}" alt="" class="game-thumbnail" onerror="this.style.display='none'">
            {% else %}<div class="game-thumbnail empty">NO IMAGE</div>{% endif %}
            <div class="game-card-body">
                <h3 style="font-size: 1.2rem; margin: 0 0 0.5rem 0; color: var(--text-main);">{{ game.title }}</h3>
                <div><span class="tag genre">🎮 {{ game.genre }}</span></div>
            </div>
        </div>
        {% else %}
        <div style="grid-column: 1 / -1; color: var(--text-sub); padding: 1rem;">お気に入りに登録したゲームはまだありません。</div>
        {% endfor %}
    </div>
    <h3 style="color: var(--accent);">✍ 自分の布教履歴</h3>
    <div>
        {% for post in my_posts_list %}
        <div class="card post-card" style="margin-bottom: 1rem;">
            <div style="font-weight: bold; margin-bottom: 0.5rem;"><a href="/games/{{ post.game_id }}" style="color: var(--accent); text-decoration: underline;">{{ post.game_title }}</a> への布教</div>
            <div class="post-header" style="margin-bottom: 0.5rem;">
                <span class="post-author">{{ post.username }}</span>
                <div style="display: flex; gap: 1rem; align-items: center;">
                    <span>{{ post.created_at.strftime('%Y-%m-%d %H:%M') if post.created_at else '' }}</span>
                    <a href="/games/{{ post.game_id }}/posts/{{ post.id }}/edit" class="btn btn-outline btn-small" style="padding: 0.2rem 0.5rem;">⚙ 編集</a>
                </div>
            </div>
            {% if post.catchphrase %}<div class="catchphrase-text" style="font-size: 1.1rem; margin-bottom: 0.5rem;">「{{ post.catchphrase }}」</div>{% endif %}
            <div style="color: var(--text-sub); font-size: 0.9rem; margin-bottom: 1rem;">👍 いいね: {{ post.likes | default(0) }}</div>
            <div style="display: flex; gap: 0.5rem; border-top: 1px dashed var(--border); padding-top: 0.75rem;">
                <button type="button" class="btn btn-outline btn-small" data-id="{{ post.game_id }}" data-title="{{ post.game_title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" onclick="sharePost(this, 'x')">𝕏 で共有</button>
                <button type="button" class="btn btn-outline btn-small" style="color:#06C755; border-color:rgba(6,199,85,0.5);" data-id="{{ post.game_id }}" data-title="{{ post.game_title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" onclick="sharePost(this, 'line')">LINE で共有</button>
            </div>
        </div>
        {% else %}
        <div style="color: var(--text-sub); padding: 1rem;">布教履歴はまだありません。</div>
        {% endfor %}
    </div>
</div>
"""

NEW_GAME_HTML = """
<div class="card">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">ゲームを追加して布教する</h2>
    {% if error_msg %}<div style="background: rgba(239, 68, 68, 0.1); color: var(--danger); padding: 1rem; border-left: 4px solid var(--danger); margin-bottom: 1.5rem;">⚠️ {{ error_msg }}</div>{% endif %}
    <form action="/games/new" method="post">
        
        <h3 style="color: var(--accent);">🎮 ゲームの基本情報</h3>
        <div class="form-group"><label>タイトル（必須）:</label><input type="text" name="title" value="{{ title | default('') }}" required></div>
        <div class="form-group"><label>ジャンル:</label>
            <select name="genre">
                {% set genres = ["RPG", "アクション", "アドベンチャー", "シミュレーション", "FPS / TPS", "パズル", "ノベル", "ホラー", "インディー", "その他 / 不明"] %}
                {% for g in genres %}<option value="{{ g }}" {% if genre == g or (not genre and g == "その他 / 不明") %}selected{% endif %}>{{ g }}</option>{% endfor %}
            </select>
        </div>
        <div class="form-group checkbox-group"><label>プラットフォーム（複数選択可）:</label>
            <div style="display: flex; flex-wrap: wrap; gap: 1rem; padding: 0.5rem 0;">
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="PC" onchange="updatePlatform(this.form)"> PC</label>
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="Switch" onchange="updatePlatform(this.form)"> Switch</label>
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="Switch2" onchange="updatePlatform(this.form)"> Switch2</label>
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="PS5" onchange="updatePlatform(this.form)"> PS5</label>
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="Xbox" onchange="updatePlatform(this.form)"> Xbox</label>
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="スマホ" onchange="updatePlatform(this.form)"> スマホ</label>
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="その他" onchange="updatePlatform(this.form)"> その他</label>
            </div>
            <input type="hidden" name="platform" class="platform-hidden" value="{{ platform | default('') }}">
        </div>
        <div class="form-group"><label>ゲーム画像（任意・自動で最適なサイズに圧縮されます）:</label>
            <input type="file" id="image_upload" accept="image/*" style="background:transparent; border:none; padding:0;">
            <input type="hidden" name="image_base64" id="image_base64">
            <div id="image_preview" style="margin-top: 1rem; display: none;"><img id="preview_img" src="" style="max-width: 100%; max-height: 200px; border-radius: 8px; border: 1px solid var(--border);"></div>
        </div>
        <div class="form-group"><label>ゲームの簡単な説明:</label><textarea name="description" rows="4">{{ description | default('') }}</textarea></div>

        <h3 style="margin-top: 2rem; color: var(--accent); border-top: 1px dashed var(--border); padding-top: 1.5rem;">🔥 最初の布教コメント</h3>
        <div class="form-group"><label>布教ネーム（匿名可）:</label><input type="text" name="username" value="名無しの布教者" required></div>
        <div style="background: #0b1120; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;">
            <div class="form-group"><label style="color: var(--accent);">一言で布教すると？（必須）:</label><input type="text" name="catchphrase" required placeholder="例：最後まで遊んだときに、やってよかったと思える作品" style="border-color: rgba(245, 158, 11, 0.5);"></div>
            <div style="display: flex; gap: 1rem; margin-bottom: 0; flex-wrap: wrap;">
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>誰におすすめ？ <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="target_audience" placeholder="例：ストーリー重視の人"></div>
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>プレイ時間 <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="play_time" placeholder="例：10～15時間"></div>
            </div>
        </div>
        <div class="form-group">
            <label>ネタバレレベル（詳細コメントの公開設定）:</label>
            <div class="spoiler-radio-group">
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="0" checked> <span style="color:var(--safe)">Lv.0 ネタバレなし</span></div><span class="radio-desc">未プレイの人が読んでも問題ない内容</span></label>
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="1"> <span style="color:var(--warning)">Lv.1 軽微なネタバレ</span></div><span class="radio-desc">序盤の設定など、体験に多少影響する内容</span></label>
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="2"> <span style="color:var(--danger)">Lv.2 ネタバレあり</span></div><span class="radio-desc">ストーリー展開など、体験を大きく左右する内容</span></label>
            </div>
        </div>
        <div class="form-group"><label>布教コメントの詳細（必須）:</label><textarea name="content" rows="4" required placeholder="熱い思いをぶつけてください。"></textarea></div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%; font-size:1.1rem; padding: 1rem; margin-top: 1rem;">ゲームを登録して布教する</button>
    </form>
</div>
"""
EDIT_GAME_HTML = """<div class="card"><h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">ゲーム情報を編集する</h2><form action="/games/{{ game.id }}/edit" method="post"><div class="form-group"><label>タイトル（必須）:</label><input type="text" name="title" value="{{ game.title }}" required></div><div class="form-group"><label>ジャンル:</label><select name="genre">{% set genres = ["RPG", "アクション", "アドベンチャー", "シミュレーション", "FPS / TPS", "パズル", "ノベル", "ホラー", "インディー", "その他 / 不明"] %}{% for g in genres %}<option value="{{ g }}" {% if game.genre == g %}selected{% endif %}>{{ g }}</option>{% endfor %}</select></div><div class="form-group checkbox-group"><label>プラットフォーム（複数選択可）:</label><div style="display: flex; flex-wrap: wrap; gap: 1rem; padding: 0.5rem 0;"><label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="PC" onchange="updatePlatform(this.form)"> PC</label><label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="Switch" onchange="updatePlatform(this.form)"> Switch</label><label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="Switch2" onchange="updatePlatform(this.form)"> Switch2</label><label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="PS5" onchange="updatePlatform(this.form)"> PS5</label><label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="Xbox" onchange="updatePlatform(this.form)"> Xbox</label><label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="スマホ" onchange="updatePlatform(this.form)"> スマホ</label><label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="その他" onchange="updatePlatform(this.form)"> その他</label></div><input type="hidden" name="platform" class="platform-hidden" value="{{ game.platform | default('') }}"></div><div class="form-group"><label>ゲーム画像（新しくアップロードして変更する場合のみ選択）:</label><input type="file" id="image_upload" accept="image/*" style="background:transparent; border:none; padding:0;"><input type="hidden" name="image_base64" id="image_base64"><input type="hidden" name="existing_image_url" value="{{ game.image_url | default('') }}"><div id="image_preview" style="margin-top: 1rem; display: {% if game.image_url %}block{% else %}none{% endif %};"><img id="preview_img" src="{{ game.image_url | default('') }}" style="max-width: 100%; max-height: 200px; border-radius: 8px; border: 1px solid var(--border);"></div></div><div class="form-group"><label>ゲームの簡単な説明:</label><textarea name="description" rows="4">{{ game.description }}</textarea></div><div style="display: flex; gap: 1rem; margin-top: 1.5rem;"><a href="/games/{{ game.id }}" class="btn btn-outline" style="flex: 1; text-align:center;">キャンセル</a><button type="submit" class="btn btn-primary" style="flex: 2;">変更を保存する</button></div></form></div>"""
EDIT_POST_HTML = """<div class="card" style="border-color: var(--accent);"><h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem; color: var(--accent);">自分の布教を編集する</h2><form action="/games/{{ game_id }}/posts/{{ post.id }}/edit" method="post"><div class="form-group"><label>布教ネーム（匿名可）:</label><input type="text" name="username" value="{{ post.username }}" required></div><div style="background: #0b1120; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;"><div class="form-group"><label style="color: var(--accent);">一言で布教すると？（必須）:</label><input type="text" name="catchphrase" value="{{ post.catchphrase | default('') }}" required style="border-color: rgba(245, 158, 11, 0.5);"></div><div style="display: flex; gap: 1rem; margin-bottom: 0; flex-wrap: wrap;"><div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>誰におすすめ？ <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="target_audience" value="{{ post.target_audience | default('') }}"></div><div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>プレイ時間 <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="play_time" value="{{ post.play_time | default('') }}"></div></div></div><div class="form-group"><label>ネタバレレベル:</label><div class="spoiler-radio-group"><label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="0" {% if post.spoiler_level == 0 %}checked{% endif %}> <span style="color:var(--safe)">Lv.0 ネタバレなし</span></div></label><label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="1" {% if post.spoiler_level == 1 %}checked{% endif %}> <span style="color:var(--warning)">Lv.1 軽微なネタバレ</span></div></label><label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="2" {% if post.spoiler_level == 2 %}checked{% endif %}> <span style="color:var(--danger)">Lv.2 ネタバレあり</span></div></label></div></div><div class="form-group"><label>布教コメントの詳細（必須）:</label><textarea name="content" rows="4" required>{{ post.content }}</textarea></div><div style="display: flex; gap: 1rem; margin-top: 1.5rem;"><a href="/games/{{ game_id }}" class="btn btn-outline" style="flex: 1; text-align: center;">キャンセル</a><button type="submit" class="btn btn-primary" style="flex: 2;">変更を保存する</button></div></form></div>"""

def render_page(content_template_str, is_top=False, page_title=None, og_description=None, og_image=None, **kwargs):
    content_html = Template(content_template_str).render(**kwargs)
    final_title = page_title if page_title else "Oshi-Ge | ネタバレなしゲーム布教サイト"
    final_desc = og_description if og_description else "未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。"
    
    return HTMLResponse(Template(BASE_HTML).render(
        css=CSS, js=JS, content=content_html, is_top=is_top, 
        page_title=final_title, og_description=final_desc, og_image=og_image, **kwargs
    ))

@app.get("/")
async def read_root(q: str = "", genre: str = "", platform: str = "", sort: str = "new"):
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
        weekly_ranking = conn.execute('''SELECT g.id, g.title, g.image_url, COUNT(p.id) as weekly_posts FROM games g JOIN posts p ON g.id = p.game_id WHERE p.created_at >= NOW() - INTERVAL '7 days' GROUP BY g.id ORDER BY weekly_posts DESC, g.created_at DESC LIMIT 5''').fetchall()
    return render_page(INDEX_HTML, is_top=True, games=games, q=q, genre=genre, platform=platform, sort=sort, weekly_ranking=weekly_ranking)

@app.get("/games/random")
async def random_game():
    with get_db_connection() as conn:
        game = conn.execute('SELECT id FROM games ORDER BY RANDOM() LIMIT 1').fetchone()
    if game: return RedirectResponse(url=f"/games/{game['id']}", status_code=303)
    return RedirectResponse(url="/", status_code=303)

@app.get("/games/new")
async def new_game_form(): return render_page(NEW_GAME_HTML, page_title="ゲームを追加する - Oshi-Ge")

@app.post("/games/new")
async def create_game(
    request: Request,
    title: str = Form(...), description: str = Form(""), genre: str = Form(""), platform: str = Form(""), image_base64: str = Form(""),
    username: str = Form(...), catchphrase: str = Form(...), target_audience: str = Form(""), play_time: str = Form(""), content: str = Form(...), spoiler_level: int = Form(...)
):
    image_url = upload_image_to_supabase(image_base64)
    with get_db_connection() as conn:
        if conn.execute('SELECT id FROM games WHERE LOWER(title) = LOWER(%s)', (title,)).fetchone():
            return render_page(NEW_GAME_HTML, error_msg=f"「{title}」は既に登録されています。", title=title, description=description, genre=genre, platform=platform, page_title="ゲームを追加する - Oshi-Ge")
        
        # ゲーム情報の保存
        cursor_game = conn.execute('INSERT INTO games (title, description, genre, platform, image_url) VALUES (%s, %s, %s, %s, %s) RETURNING id', (title, description, genre, platform, image_url))
        game_id = cursor_game.fetchone()["id"]
        
        # 最初の布教コメントの保存
        cursor_post = conn.execute('''INSERT INTO posts (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id''', (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level))
        post_id = cursor_post.fetchone()["id"]
        
        conn.commit()
    
    # 布教情報をクッキーに保存してマイページへ反映
    res = RedirectResponse(url=f"/games/{game_id}", status_code=303)
    c = request.cookies.get("my_posts", "")
    res.set_cookie(key="my_posts", value=f"{c},{post_id}" if c else str(post_id), max_age=60*60*24*365)
    return res

@app.get("/games/{game_id}/edit")
async def edit_game_form(game_id: int):
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
    if not game: raise HTTPException(status_code=404, detail="Game not found")
    return render_page(EDIT_GAME_HTML, game=game, page_title=f"{game['title']}の編集 - Oshi-Ge")

@app.post("/games/{game_id}/edit")
async def update_game(game_id: int, title: str = Form(...), description: str = Form(""), genre: str = Form(""), platform: str = Form(""), image_base64: str = Form(""), existing_image_url: str = Form("")):
    image_url = existing_image_url
    if image_base64:
        new_url = upload_image_to_supabase(image_base64)
        if new_url: image_url = new_url

    with get_db_connection() as conn:
        conn.execute('UPDATE games SET title = %s, description = %s, genre = %s, platform = %s, image_url = %s WHERE id = %s', (title, description, genre, platform, image_url, game_id))
        conn.commit()
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@app.get("/games/{game_id}")
async def read_game(request: Request, game_id: int, sort: str = "likes"):
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
        if not game: raise HTTPException(status_code=404, detail="Game not found")
        posts = conn.execute('SELECT * FROM posts WHERE game_id = %s ORDER BY ' + ('created_at DESC' if sort == 'new' else 'likes DESC, created_at DESC'), (game_id,)).fetchall()
    
    my_posts = [int(x) for x in request.cookies.get("my_posts", "").split(",") if x.isdigit()]
    bookmarks = [int(x) for x in request.cookies.get("bookmarks", "").split(",") if x.isdigit()]
    
    game_title_tag = f"{game['title']} の評価・感想・ネタバレなし布教 - Oshi-Ge"
    og_desc = game['description'] if game['description'] else f"『{game['title']}』のおすすめ布教ページです。ネタバレなしで魅力をお伝えします。"
    og_img = game['image_url'] if game['image_url'] else None
    
    return render_page(GAME_HTML, game=game, posts=posts, sort=sort, my_posts=my_posts, is_bookmarked=(game_id in bookmarks), page_title=game_title_tag, og_description=og_desc, og_image=og_img)

@app.post("/games/{game_id}/posts")
async def create_post(request: Request, game_id: int, username: str = Form(...), catchphrase: str = Form(...), target_audience: str = Form(""), play_time: str = Form(""), content: str = Form(...), spoiler_level: int = Form(...)):
    with get_db_connection() as conn:
        cursor = conn.execute('''INSERT INTO posts (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id''', (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level))
        post_id = cursor.fetchone()["id"]
        conn.commit()
        
    res = RedirectResponse(url=f"/games/{game_id}", status_code=303)
    c = request.cookies.get("my_posts", "")
    res.set_cookie(key="my_posts", value=f"{c},{post_id}" if c else str(post_id), max_age=60*60*24*365)
    return res

@app.get("/games/{game_id}/posts/{post_id}/edit")
async def edit_post_form(request: Request, game_id: int, post_id: int):
    if post_id not in [int(x) for x in request.cookies.get("my_posts", "").split(",") if x.isdigit()]: raise HTTPException(status_code=403, detail="権限がありません。")
    with get_db_connection() as conn:
        post = conn.execute('SELECT * FROM posts WHERE id = %s AND game_id = %s', (post_id, game_id)).fetchone()
    if not post: raise HTTPException(status_code=404)
    return render_page(EDIT_POST_HTML, game_id=game_id, post=post, page_title="布教の編集 - Oshi-Ge")

@app.post("/games/{game_id}/posts/{post_id}/edit")
async def update_post(request: Request, game_id: int, post_id: int, username: str = Form(...), catchphrase: str = Form(...), target_audience: str = Form(""), play_time: str = Form(""), content: str = Form(...), spoiler_level: int = Form(...)):
    if post_id not in [int(x) for x in request.cookies.get("my_posts", "").split(",") if x.isdigit()]: raise HTTPException(status_code=403)
    with get_db_connection() as conn:
        conn.execute('''UPDATE posts SET username = %s, catchphrase = %s, target_audience = %s, play_time = %s, content = %s, spoiler_level = %s WHERE id = %s AND game_id = %s''', (username, catchphrase, target_audience, play_time, content, spoiler_level, post_id, game_id))
        conn.commit()
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@app.post("/games/{game_id}/posts/{post_id}/like")
async def like_post(game_id: int, post_id: int):
    with get_db_connection() as conn:
        cursor = conn.execute('UPDATE posts SET likes = likes + 1 WHERE id = %s RETURNING likes', (post_id,))
        likes = cursor.fetchone()["likes"]
        conn.commit()
    return {"likes": likes}

@app.post("/games/{game_id}/bookmark")
async def toggle_bookmark(request: Request, game_id: int):
    bookmarks = [int(x) for x in request.cookies.get("bookmarks", "").split(",") if x.isdigit()]
    is_bookmarked = False
    if game_id in bookmarks: bookmarks.remove(game_id)
    else: bookmarks.append(game_id); is_bookmarked = True
    res = JSONResponse(content={"bookmarked": is_bookmarked})
    res.set_cookie("bookmarks", ",".join(map(str, bookmarks)), max_age=60*60*24*365)
    return res

@app.get("/mypage")
async def mypage(request: Request):
    my_posts_ids = [int(x) for x in request.cookies.get("my_posts", "").split(",") if x.isdigit()]
    bookmarks = [int(x) for x in request.cookies.get("bookmarks", "").split(",") if x.isdigit()]
    
    my_posts_list = []
    bookmarked_games = []
    
    with get_db_connection() as conn:
        if my_posts_ids:
            my_posts_list = conn.execute("SELECT p.*, g.title as game_title FROM posts p JOIN games g ON p.game_id = g.id WHERE p.id = ANY(%s) ORDER BY p.created_at DESC", (my_posts_ids,)).fetchall()
        if bookmarks:
            bookmarked_games = conn.execute("SELECT * FROM games WHERE id = ANY(%s) ORDER BY created_at DESC", (bookmarks,)).fetchall()
            
    return render_page(MYPAGE_HTML, my_posts_list=my_posts_list, bookmarked_games=bookmarked_games, page_title="マイページ - Oshi-Ge")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
