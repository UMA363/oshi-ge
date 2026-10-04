import os
import uvicorn
from fastapi import FastAPI, Request, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Template
import psycopg
from psycopg.rows import dict_row

app = FastAPI()

# Renderの環境変数からSupabaseのURLを取得
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    # SSL通信を必須にしてSupabaseへ接続
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode="require")

# --- HTML・CSS・JSテンプレート ---
CSS = """
:root { --bg-color: #0f172a; --card-bg: #1e293b; --text-main: #f8fafc; --text-sub: #94a3b8; --accent: #f59e0b; --accent-hover: #d97706; --border: #334155; --safe: #10b981; --warning: #f59e0b; --danger: #ef4444; }
body { font-family: 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif; background-color: var(--bg-color); color: var(--text-main); margin: 0; padding: 0; line-height: 1.6; }
.header-container { background-color: #0b1120; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
.header-container h1 { margin: 0; font-size: 1.8rem; font-weight: 900; letter-spacing: 0.05em; font-family: 'Arial Black', sans-serif;}
.header-container h1 a { color: var(--accent); text-decoration: none; transition: color 0.2s; }
.header-container h1 a:hover { color: var(--text-main); }
main { max-width: 1100px; margin: 0 auto; padding: 2rem 1rem; }
.hero { text-align: center; padding: 3rem 1rem 4rem; background: radial-gradient(circle at top, #1e293b 0%, #0f172a 100%); border-bottom: 1px solid var(--border); margin-bottom: 2rem; }
.hero h2 { font-size: 2.5rem; margin: 0 0 1rem 0; color: var(--accent); font-weight: 900; }
.hero p { color: var(--text-sub); font-size: 1.1rem; margin-bottom: 2rem; }
.search-bar-advanced { max-width: 800px; margin: 0 auto; background: rgba(15, 23, 42, 0.8); padding: 1rem; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 1rem;}
.search-inputs { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.search-inputs input, .search-inputs select { padding: 0.8rem; border-radius: 8px; border: 1px solid var(--border); background: #0f172a; color: white; font-size: 1rem; }
.search-inputs input { flex: 2; min-width: 200px; }
.search-inputs select { flex: 1; min-width: 130px; }
.search-inputs button { flex: 1; min-width: 120px; font-size: 1.1rem; }
.layout-wrapper { display: flex; gap: 2rem; align-items: flex-start; }
.main-column { flex: 1; min-width: 0; }
.sidebar-column { width: 320px; flex-shrink: 0; }
@media (max-width: 850px) { .layout-wrapper { flex-direction: column; } .sidebar-column { width: 100%; } }
.card { background: var(--card-bg); padding: 1.5rem; margin-bottom: 1.5rem; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); }
h2, h3 { margin-top: 0; color: var(--text-main); }
.btn { display: inline-flex; align-items: center; justify-content: center; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; border: none; cursor: pointer; font-weight: bold; transition: all 0.2s; font-size: 1rem; }
.btn-primary { background-color: var(--accent); color: #fff; box-shadow: 0 2px 4px rgba(245, 158, 11, 0.3); }
.btn-outline { background-color: transparent; border: 2px solid var(--border); color: var(--text-main); }
.btn-small { padding: 0.4rem 0.8rem; font-size: 0.85rem; }
.tag { display: inline-block; background: #334155; color: #e2e8f0; padding: 0.3rem 0.8rem; border-radius: 9999px; font-size: 0.85rem; font-weight: bold; margin-bottom: 0.5rem; margin-right: 0.5rem; }
.tag.genre { background: rgba(245, 158, 11, 0.2); color: var(--accent); border: 1px solid rgba(245, 158, 11, 0.3); }
.game-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; }
.game-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; transition: transform 0.2s; display: flex; flex-direction: column; cursor: pointer; }
.game-thumbnail { width: 100%; height: 160px; object-fit: cover; background: #334155; }
.game-thumbnail.empty { display: flex; align-items: center; justify-content: center; color: var(--text-sub); font-weight: bold; background: linear-gradient(45deg, #1e293b, #0f172a); }
.game-card-body { padding: 1.2rem; flex-grow: 1; display: flex; flex-direction: column; }
.form-group { margin-bottom: 1.5rem; }
.form-group label { display: block; margin-bottom: 0.5rem; font-weight: bold; color: #cbd5e1; }
.form-group input[type="text"], .form-group textarea, .form-group select { width: 100%; padding: 0.75rem; background: #0f172a; border: 1px solid var(--border); color: var(--text-main); border-radius: 8px; box-sizing: border-box; font-size: 1rem; font-family: inherit; }
"""

JS = """
function shareGameToX(title) { 
    const text = encodeURIComponent(`次に遊ぶ神ゲーを探している方へ🎮\\n『${title}』のおすすめ布教ページです！👇\\n#OshiGe\\n`);
    window.open(`https://x.com/intent/tweet?text=${text}&url=${encodeURIComponent(window.location.href)}`, '_blank'); 
}
"""

BASE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Oshi-Ge | ゲーム布教サイト</title>
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-XRFBSR9HSR"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-XRFBSR9HSR');
    </script>
    <style>{{ css }}</style>
</head>
<body>
    <header class="header-container">
        <h1><a href="/">🎮 Oshi-Ge</a></h1>
        <div style="display:flex; gap: 1rem;">
            <a href="/games/new" class="btn btn-primary btn-small" style="color: #ffffff;">＋ ゲームを布教する</a>
        </div>
    </header>
    {% if is_top %}
    <div class="hero">
        <h2>誰かの人生を変える1本を。</h2>
        <p>未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。</p>
    </div>
    {% endif %}
    <main>{{ content }}</main>
    <script>{{ js }}</script>
</body>
</html>
"""

INDEX_HTML = """
<div class="layout-wrapper">
    <div class="main-column">
        <h3 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">布教されているゲーム</h3>
        <div class="game-grid">
            {% for game in games %}
                <div class="game-card" onclick="location.href='/games/{{ game.id }}'">
                    {% if game.image_url %}<img src="{{ game.image_url }}" alt="" class="game-thumbnail" onerror="this.style.display='none'">
                    {% else %}<div class="game-thumbnail empty">NO IMAGE</div>{% endif %}
                    <div class="game-card-body">
                        <h3 style="font-size: 1.2rem; margin: 0 0 0.5rem 0; color: var(--text-main);">{{ game.title }}</h3>
                        <span class="tag genre">🎮 {{ game.genre }}</span>
                    </div>
                </div>
            {% else %}
                <div style="grid-column: 1 / -1; text-align: center; color: var(--text-sub); padding: 3rem; background: var(--card-bg); border-radius:12px;"><p>まだゲームがありません。</p></div>
            {% endfor %}
        </div>
    </div>
</div>
"""

GAME_HTML = """
<div class="card">
    <h2 style="font-size: 2rem; margin-bottom: 1rem; font-weight: 900;">{{ game.title }}</h2>
    <div style="margin-bottom: 1.5rem;"><span class="tag genre">🎮 {{ game.genre }}</span></div>
    <div style="background: #0f172a; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;">
        <p style="margin: 0; white-space: pre-wrap; color: #cbd5e1;">{{ game.description }}</p>
    </div>
</div>
"""

NEW_GAME_HTML = """
<div class="card">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">ゲームを追加する</h2>
    <form action="/games/new" method="post">
        <div class="form-group"><label>タイトル（必須）:</label><input type="text" name="title" required></div>
        <div class="form-group"><label>ジャンル:</label><select name="genre">
            <option value="RPG">RPG</option><option value="アクション">アクション</option><option value="その他">その他</option>
        </select></div>
        <div class="form-group"><label>画像URL（任意）:</label><input type="text" name="image_url"></div>
        <div class="form-group"><label>説明:</label><textarea name="description" rows="4"></textarea></div>
        <button type="submit" class="btn btn-primary" style="width: 100%; margin-top: 1rem;">ゲームを登録する</button>
    </form>
</div>
"""

def render_page(content_template_str, is_top=False, **kwargs):
    content_html = Template(content_template_str).render(**kwargs)
    return HTMLResponse(Template(BASE_HTML).render(css=CSS, js=JS, content=content_html, is_top=is_top, **kwargs))

# --- ルーティング ---
@app.get("/")
async def read_root():
    with get_db_connection() as conn:
        # Supabase用のSQL（プレースホルダーは %s ）
        games = conn.execute("SELECT * FROM games ORDER BY created_at DESC").fetchall()
    return render_page(INDEX_HTML, is_top=True, games=games)

@app.get("/games/new")
async def new_game_form(): 
    return render_page(NEW_GAME_HTML)

@app.post("/games/new")
async def create_game(title: str = Form(...), description: str = Form(""), genre: str = Form(""), image_url: str = Form("")):
    with get_db_connection() as conn:
        # PostgreSQLは %s を使用
        conn.execute('INSERT INTO games (title, description, genre, image_url) VALUES (%s, %s, %s, %s)', 
                     (title, description, genre, image_url))
        conn.commit()
        # 登録したIDを取得
        game_id = conn.execute('SELECT id FROM games ORDER BY id DESC LIMIT 1').fetchone()["id"]
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@app.get("/games/{game_id}")
async def read_game(game_id: int):
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
    if not game: raise HTTPException(status_code=404, detail="Game not found")
    return render_page(GAME_HTML, game=game)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
