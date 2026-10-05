import os
import uvicorn
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Template
import psycopg
from psycopg.rows import dict_row

app = FastAPI()

# ============================================================
# Render / Supabase
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        sslmode="require"
    )


# ============================================================
# 1. データベース初期化
# ※ 既存データを削除する処理はありません
# ============================================================

def init_db():
    try:
        with get_db_connection() as conn:

            conn.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    genre TEXT,
                    platform TEXT,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER REFERENCES games(id),
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    spoiler_level INTEGER DEFAULT 0,
                    catchphrase TEXT,
                    target_audience TEXT,
                    play_time TEXT,
                    likes INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 不足カラムがあれば追加
            conn.execute(
                "ALTER TABLE games ADD COLUMN IF NOT EXISTS platform TEXT"
            )
            conn.execute(
                "ALTER TABLE games ADD COLUMN IF NOT EXISTS image_url TEXT"
            )

            conn.execute(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS catchphrase TEXT"
            )
            conn.execute(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS target_audience TEXT"
            )
            conn.execute(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS play_time TEXT"
            )
            conn.execute(
                "ALTER TABLE posts ADD COLUMN IF NOT EXISTS likes INTEGER DEFAULT 0"
            )

            conn.commit()

    except Exception as e:
        print("DB Init error:", e)


init_db()


# ============================================================
# 2. CSS
# ============================================================

CSS = """

:root {
    --bg-color: #0f172a;
    --card-bg: #1e293b;
    --text-main: #f8fafc;
    --text-sub: #94a3b8;
    --accent: #f59e0b;
    --accent-hover: #d97706;
    --border: #334155;
    --safe: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
}

* {
    box-sizing: border-box;
}

body {
    font-family: 'Helvetica Neue', Arial, 'Hiragino Sans', sans-serif;
    background-color: var(--bg-color);
    color: var(--text-main);
    margin: 0;
    padding: 0;
    line-height: 1.6;
}

.header-container {
    background-color: #0b1120;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
}

.header-container h1 {
    margin: 0;
    font-size: 1.8rem;
    font-weight: 900;
    letter-spacing: 0.05em;
    font-family: 'Arial Black', sans-serif;
}

.header-container h1 a {
    color: var(--accent);
    text-decoration: none;
    transition: color 0.2s;
}

.header-container h1 a:hover {
    color: var(--text-main);
}

main {
    max-width: 1100px;
    margin: 0 auto;
    padding: 2rem 1rem;
}

/* ============================================================
   Hero
   ============================================================ */

.hero {
    text-align: center;
    padding: 3rem 1rem 4rem;
    background: radial-gradient(
        circle at top,
        #1e293b 0%,
        #0f172a 100%
    );
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
}

.hero h2 {
    font-size: 2.5rem;
    margin: 0 0 1rem 0;
    color: var(--accent);
    font-weight: 900;
}

.hero p {
    color: var(--text-sub);
    font-size: 1.1rem;
    margin-bottom: 2rem;
}

/* ============================================================
   Search
   ============================================================ */

.search-bar-advanced {
    max-width: 800px;
    margin: 0 auto;
    background: rgba(15, 23, 42, 0.8);
    padding: 1rem;
    border-radius: 12px;
    border: 1px solid var(--border);
    margin-bottom: 1rem;
}

.search-inputs {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
}

.search-inputs input,
.search-inputs select {
    padding: 0.8rem;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: #0f172a;
    color: white;
    font-size: 1rem;
}

.search-inputs input {
    flex: 2;
    min-width: 200px;
}

.search-inputs select {
    flex: 1;
    min-width: 130px;
}

.search-inputs button {
    flex: 1;
    min-width: 120px;
    font-size: 1.1rem;
}

.search-inputs input:focus,
.search-inputs select:focus {
    outline: none;
    border-color: var(--accent);
}

/* ============================================================
   Layout
   ============================================================ */

.layout-wrapper {
    display: flex;
    gap: 2rem;
    align-items: flex-start;
}

.main-column {
    flex: 1;
    min-width: 0;
}

.sidebar-column {
    width: 320px;
    flex-shrink: 0;
}

@media (max-width: 850px) {

    .layout-wrapper {
        flex-direction: column;
    }

    .sidebar-column {
        width: 100%;
        order: -1;
        margin-bottom: 1.5rem;
    }
}

/* ============================================================
   Cards
   ============================================================ */

.card {
    background: var(--card-bg);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    border-radius: 12px;
    border: 1px solid var(--border);
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2);
}

h2,
h3 {
    margin-top: 0;
    color: var(--text-main);
}

/* ============================================================
   Buttons
   ============================================================ */

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    text-decoration: none;
    border: none;
    cursor: pointer;
    font-weight: bold;
    transition: all 0.2s;
    font-size: 1rem;
}

.btn-primary {
    background-color: var(--accent);
    color: #fff;
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.3);
}

.btn-primary:hover {
    background-color: var(--accent-hover);
    transform: translateY(-2px);
}

.btn-outline {
    background-color: transparent;
    border: 2px solid var(--border);
    color: var(--text-main);
}

.btn-outline:hover {
    border-color: var(--accent);
    color: var(--accent);
}

.btn-small {
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
}

.btn-x {
    background-color: #000;
    color: #fff;
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    border: 1px solid #333;
}

.btn-x:hover {
    background-color: #222;
}

.btn-line {
    background-color: #06C755;
    color: #fff;
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    border: 1px solid #05a546;
}

.btn-line:hover {
    background-color: #05a546;
}

.btn-bookmark {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-main);
    padding: 0.5rem 1rem;
    border-radius: 8px;
    cursor: pointer;
    font-weight: bold;
    font-size: 0.9rem;
    transition: 0.2s;
}

.btn-bookmark.bookmarked {
    background: rgba(16, 185, 129, 0.1);
    border-color: var(--safe);
    color: var(--safe);
}

/* ============================================================
   Forms
   ============================================================ */

.form-group {
    margin-bottom: 1.5rem;
}

.form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: bold;
    color: #cbd5e1;
}

.form-group input[type="text"],
.form-group textarea,
.form-group select {
    width: 100%;
    padding: 0.75rem;
    background: #0f172a;
    border: 1px solid var(--border);
    color: var(--text-main);
    border-radius: 8px;
    box-sizing: border-box;
    font-size: 1rem;
    font-family: inherit;
}

.form-group input[type="checkbox"] {
    width: auto;
    transform: scale(1.2);
    cursor: pointer;
    margin-right: 0.5rem;
}

/* ============================================================
   Spoiler
   ============================================================ */

.spoiler-radio-group {
    background: #0b1120;
    padding: 1.25rem;
    border-radius: 8px;
    border: 1px solid var(--border);
}

.radio-label {
    display: flex;
    flex-direction: column;
    margin-bottom: 1rem;
    cursor: pointer;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
}

.radio-label:last-child {
    margin-bottom: 0;
    padding-bottom: 0;
    border-bottom: none;
}

.radio-header {
    display: flex;
    align-items: center;
    font-weight: bold;
    font-size: 1.05rem;
}

/* ============================================================
   Tags
   ============================================================ */

.tag {
    display: inline-block;
    background: #334155;
    color: #e2e8f0;
    padding: 0.3rem 0.8rem;
    border-radius: 9999px;
    font-size: 0.85rem;
    font-weight: bold;
    margin-bottom: 0.5rem;
    margin-right: 0.5rem;
}

.tag.genre {
    background: rgba(245, 158, 11, 0.2);
    color: var(--accent);
    border: 1px solid rgba(245, 158, 11, 0.3);
}

/* ============================================================
   Game cards
   ============================================================ */

.game-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1.5rem;
}

.game-card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    transition: transform 0.2s;
    display: flex;
    flex-direction: column;
    cursor: pointer;
}

.game-card:hover {
    transform: translateY(-4px);
    border-color: var(--accent);
}

.game-thumbnail {
    width: 100%;
    height: 160px;
    object-fit: cover;
    background: #334155;
}

.game-thumbnail.empty {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-sub);
    font-weight: bold;
    background: linear-gradient(45deg, #1e293b, #0f172a);
}

.game-card-body {
    padding: 1.2rem;
    flex-grow: 1;
    display: flex;
    flex-direction: column;
}

.latest-catchphrase {
    margin-top: auto;
    padding: 0.8rem;
    background: rgba(245, 158, 11, 0.1);
    border-left: 3px solid var(--accent);
    border-radius: 4px;
    font-size: 0.9rem;
    font-weight: bold;
    color: #fcd34d;
}

.game-hero-image {
    width: 100%;
    max-height: 400px;
    object-fit: cover;
    border-radius: 8px;
    margin-bottom: 1.5rem;
    border: 1px solid var(--border);
}

/* ============================================================
   Posts
   ============================================================ */

.post-card {
    background: #0f172a;
    border: 1px solid var(--border);
}

.post-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.9rem;
    color: var(--text-sub);
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.75rem;
}

.catchphrase-text {
    margin: 0 0 0.75rem 0;
    color: var(--accent);
    font-size: 1.3rem;
    font-weight: 900;
    line-height: 1.4;
}

.meta-tag {
    background: transparent;
    color: #94a3b8;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    border: 1px solid #475569;
    font-size: 0.85rem;
}

.spoiler-badge.safe {
    color: var(--safe);
    font-weight: bold;
    font-size: 0.9rem;
    display: inline-flex;
    background: rgba(16, 185, 129, 0.1);
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
}

.post-content p {
    font-size: 1.05rem;
    margin-top: 0.75rem;
    white-space: pre-wrap;
}

.spoiler-toggle-btn {
    width: 100%;
    padding: 1rem;
    font-weight: bold;
    border: 2px dashed;
    border-radius: 8px;
    cursor: pointer;
    background: transparent;
    transition: all 0.2s;
    font-size: 1rem;
}

.spoiler-toggle-btn.warning {
    color: var(--warning);
    border-color: rgba(245, 158, 11, 0.5);
}

.spoiler-toggle-btn.danger {
    color: var(--danger);
    border-color: rgba(239, 68, 68, 0.5);
}

.spoiler-hidden-text {
    margin-top: 1rem;
    padding: 1.25rem;
    background: #1e293b;
    border-left: 4px solid var(--border);
    border-radius: 0 8px 8px 0;
}

/* ============================================================
   Like
   ============================================================ */

.btn-like {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-main);
    padding: 0.4rem 0.8rem;
    border-radius: 20px;
    cursor: pointer;
    font-weight: bold;
}

.btn-like.liked {
    background: rgba(245, 158, 11, 0.1);
    border-color: var(--accent);
    color: var(--accent);
}

/* ============================================================
   探し方
   ============================================================ */

.discover-panel {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
}

.discover-panel h3 {
    margin-bottom: 0.9rem;
    color: var(--accent);
}

.quick-filter-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 0.6rem;
}

.quick-filter {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 46px;
    padding: 0.6rem 0.8rem;
    background: #0f172a;
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text-main);
    text-decoration: none;
    font-weight: bold;
    text-align: center;
    transition: 0.2s;
}

.quick-filter:hover {
    border-color: var(--accent);
    color: var(--accent);
    transform: translateY(-2px);
}

/* ============================================================
   Promo Card
   ============================================================ */

.promo-modal {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.78);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    z-index: 9999;
}

.promo-modal-box {
    width: min(900px, 100%);
    max-height: 95vh;
    overflow-y: auto;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem;
    box-sizing: border-box;
}

.promo-modal-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.8rem;
}

.promo-modal-head h3 {
    margin: 0;
    color: var(--accent);
}

.promo-canvas-wrap {
    background: #0b1120;
    border-radius: 10px;
    padding: 0.75rem;
    border: 1px solid var(--border);
}

#promoCanvas {
    display: block;
    width: 100%;
    height: auto;
    border-radius: 8px;
    touch-action: manipulation;
}

.promo-modal-actions {
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
    margin-top: 0.8rem;
}

/* ============================================================
   Mobile
   ============================================================ */

@media (max-width: 600px) {

    .header-container {
        flex-direction: column;
        gap: 1rem;
        text-align: center;
        padding: 1rem;
    }

    .header-container h1 {
        font-size: 1.5rem;
    }

    .hero {
        padding: 2rem 1rem;
    }

    .hero h2 {
        font-size: 1.8rem;
    }

    .search-inputs {
        flex-direction: column;
    }

    .search-inputs input,
    .search-inputs select,
    .search-inputs button {
        width: 100%;
        box-sizing: border-box;
    }

    .game-grid {
        grid-template-columns: 1fr;
    }

    .card {
        padding: 1rem;
    }

    .promo-modal {
        padding: 0.4rem;
    }

    .promo-modal-box {
        padding: 0.6rem;
        max-height: 98vh;
    }

    .promo-modal-actions .btn {
        flex: 1;
        min-width: 130px;
    }
}

"""


# ============================================================
# 3. JavaScript
# ============================================================

JS = r"""
function toggleSpoiler(btn) {

    const txt = btn.nextElementSibling;

    if (txt.style.display === "none") {

        txt.style.display = "block";
        btn.style.opacity = "0.7";
        btn.innerText = "クリックして閉じる";

    } else {

        txt.style.display = "none";
        btn.style.opacity = "1";

        if (btn.classList.contains('warning')) {
            btn.innerText = "🔒 軽微なネタバレ【クリックして表示】";
        }
        else if (btn.classList.contains('danger')) {
            btn.innerText = "⚠️ ネタバレあり【クリックして表示】";
        }
    }
}


function shareGameToX(title) {

    const text = encodeURIComponent(
        `次に遊ぶ神ゲーを探している方へ🎮\n『${title}』のおすすめ布教ページです！👇\n#OshiGe\n`
    );

    window.open(
        `https://x.com/intent/tweet?text=${text}&url=${encodeURIComponent(window.location.href)}`,
        '_blank'
    );
}


function shareGameToLine(title) {

    const text = encodeURIComponent(
        `次に遊ぶ神ゲーを探している方へ🎮\n『${title}』のおすすめ布教ページです！👇\n#OshiGe\n`
    );

    window.open(
        `https://line.me/R/msg/text/?${text}${encodeURIComponent(window.location.href)}`,
        '_blank'
    );
}


function sharePost(btn, platform) {

    const gameId = btn.getAttribute('data-id');
    const title = btn.getAttribute('data-title') || 'おすすめゲーム';
    const catchphrase = btn.getAttribute('data-catch') || '';
    const content = btn.getAttribute('data-content') || '';
    const spoilerLevel = Number(
        btn.getAttribute('data-spoiler') || '0'
    );

    const url =
        window.location.origin +
        '/games/' +
        gameId;

    let text =
        `このゲーム、もっと知られてほしい。\n\n🎮 『${title}』`;

    if (catchphrase) {
        text += `\n\n「${catchphrase}」`;
    }

    if (spoilerLevel === 0 && content.trim()) {

        let impression = content.trim();

        if (Array.from(impression).length > 30) {
            impression =
                Array.from(impression)
                .slice(0, 30)
                .join('') + '…';
        }

        text += `\n\n💬「${impression}」`;

    } else if (spoilerLevel === 1) {

        text += `\n\n🔒 軽微なネタバレを含みます`;

    } else if (spoilerLevel === 2) {

        text += `\n\n⚠️ ネタバレあり`;
    }

    text +=
        `\n\n布教内容はこちら👇\n${url}\n\n#OshiGe`;

    if (platform === 'x') {

        window.open(
            `https://x.com/intent/tweet?text=${encodeURIComponent(text)}`,
            '_blank'
        );

    } else if (platform === 'line') {

        window.open(
            `https://line.me/R/msg/text/?${encodeURIComponent(text)}`,
            '_blank'
        );
    }
}


async function likePost(gId, pId, btn) {

    if (btn.classList.contains('liked')) return;

    try {

        const res = await fetch(
            `/games/${gId}/posts/${pId}/like`,
            {
                method: 'POST'
            }
        );

        if (res.ok) {

            const data = await res.json();

            btn.querySelector('span').innerText =
                data.likes;

            btn.classList.add('liked');

            localStorage.setItem(
                `liked_${pId}`,
                'true'
            );
        }

    } catch (e) {
        console.log(e);
    }
}


async function toggleBookmark(gId, btn) {

    try {

        const res = await fetch(
            `/games/${gId}/bookmark`,
            {
                method: 'POST'
            }
        );

        if (res.ok) {

            const data = await res.json();

            if (data.bookmarked) {

                btn.innerText = "🔖 お気に入り解除";
                btn.classList.add('bookmarked');

            } else {

                btn.innerText = "🔖 お気に入りに追加";
                btn.classList.remove('bookmarked');
            }
        }

    } catch (e) {
        console.log(e);
    }
}


function updatePlatform(form) {

    form.querySelector('.platform-hidden').value =
        Array.from(
            form.querySelectorAll('.platform-cb:checked')
        )
        .map(cb => cb.value)
        .join(',');
}


document.addEventListener(
    "DOMContentLoaded",
    () => {

        document.querySelectorAll('.btn-like').forEach(
            b => {

                if (
                    localStorage.getItem(
                        `liked_${b.getAttribute('data-post-id')}`
                    )
                ) {
                    b.classList.add('liked');
                }
            }
        );


        document.querySelectorAll('.platform-hidden').forEach(
            h => {

                if (!h.value) return;

                const p =
                    h.value
                    .split(',')
                    .map(s => s.trim());

                h.closest('form')
                .querySelectorAll('.platform-cb')
                .forEach(cb => {

                    if (p.includes(cb.value)) {
                        cb.checked = true;
                    }
                });
            }
        );
    }
);


/* ============================================================
   布教カード
   ============================================================ */

function openPromoCard(
    title,
    catchphrase,
    targetAudience,
    playTime,
    username,
    genre,
    platform,
    spoilerLevel,
    content
) {

    const modal =
        document.getElementById('promo-card-modal');

    if (!modal) return;

    modal.style.display = 'flex';

    modal.dataset.title =
        title || '';

    modal.dataset.catchphrase =
        catchphrase ||
        'このゲーム、ぜひ遊んでほしい！';

    modal.dataset.target =
        targetAudience || '';

    modal.dataset.playTime =
        playTime || '';

    modal.dataset.username =
        username ||
        '名無しの布教者';

    modal.dataset.genre =
        genre || '';

    modal.dataset.platform =
        platform || '';

    modal.dataset.spoiler =
        String(spoilerLevel || 0);

    modal.dataset.content =
        content || '';

    drawPromoCard();
}


function closePromoCard() {

    const modal =
        document.getElementById(
            'promo-card-modal'
        );

    if (modal) {
        modal.style.display = 'none';
    }
}


/* ============================================================
   Canvas文字折り返し
   ============================================================ */

function wrapCanvasText(
    ctx,
    text,
    x,
    y,
    maxWidth,
    lineHeight,
    maxLines
) {

    const chars =
        Array.from(text || '');

    let line = '';
    const lines = [];

    for (const ch of chars) {

        const test =
            line + ch;

        if (
            ctx.measureText(test).width >
            maxWidth &&
            line
        ) {

            lines.push(line);
            line = ch;

            if (lines.length >= maxLines) {
                break;
            }

        } else {

            line = test;
        }
    }

    if (
        lines.length < maxLines &&
        line
    ) {
        lines.push(line);
    }

    if (
        lines.length === maxLines &&
        lines.join('').length <
        chars.length
    ) {

        let last =
            lines[maxLines - 1] || '';

        while (
            ctx.measureText(last + '…').width >
            maxWidth &&
            last.length > 0
        ) {
            last = last.slice(0, -1);
        }

        lines[maxLines - 1] =
            last + '…';
    }

    lines.forEach(
        (t, i) => {
            ctx.fillText(
                t,
                x,
                y + i * lineHeight
            );
        }
    );

    return lines.length;
}


function drawRoundRect(
    ctx,
    x,
    y,
    w,
    h,
    r
) {

    const rr =
        Math.min(
            r,
            w / 2,
            h / 2
        );

    ctx.beginPath();

    ctx.moveTo(
        x + rr,
        y
    );

    ctx.arcTo(
        x + w,
        y,
        x + w,
        y + h,
        rr
    );

    ctx.arcTo(
        x + w,
        y + h,
        x,
        y + h,
        rr
    );

    ctx.arcTo(
        x,
        y + h,
        x,
        y,
        rr
    );

    ctx.arcTo(
        x,
        y,
        x + w,
        y,
        rr
    );

    ctx.closePath();
}


/* ============================================================
   布教カード描画
   ============================================================ */

function drawPromoCard() {

    const modal =
        document.getElementById(
            'promo-card-modal'
        );

    const canvas =
        document.getElementById(
            'promoCanvas'
        );

    if (!modal || !canvas) return;

    const ctx =
        canvas.getContext('2d');

    const W = 1200;
    const H = 800;

    canvas.width = W;
    canvas.height = H;


    const title =
        modal.dataset.title ||
        'おすすめゲーム';

    const catchphrase =
        modal.dataset.catchphrase ||
        'このゲーム、ぜひ遊んでほしい！';

    const target =
        modal.dataset.target ||
        '';

    const playTime =
        modal.dataset.playTime ||
        '';

    const genre =
        modal.dataset.genre ||
        '';

    const platform =
        modal.dataset.platform ||
        '';

    const username =
        modal.dataset.username ||
        '名無しの布教者';

    const spoiler =
        Number(
            modal.dataset.spoiler || 0
        );

    const content =
        modal.dataset.content ||
        '';


    /* ========================================================
       背景
       ======================================================== */

    const bg =
        ctx.createLinearGradient(
            0,
            0,
            W,
            H
        );

    bg.addColorStop(
        0,
        '#111827'
    );

    bg.addColorStop(
        0.55,
        '#0f172a'
    );

    bg.addColorStop(
        1,
        '#020617'
    );

    ctx.fillStyle = bg;
    ctx.fillRect(
        0,
        0,
        W,
        H
    );


    /* 右上の光 */

    const glow =
        ctx.createRadialGradient(
            1030,
            100,
            20,
            1030,
            100,
            430
        );

    glow.addColorStop(
        0,
        'rgba(245,158,11,0.22)'
    );

    glow.addColorStop(
        1,
        'rgba(245,158,11,0)'
    );

    ctx.fillStyle = glow;

    ctx.fillRect(
        650,
        0,
        550,
        500
    );


    /* 左アクセント */

    ctx.fillStyle =
        '#f59e0b';

    ctx.fillRect(
        0,
        0,
        14,
        H
    );


    /* ========================================================
       ヘッダー
       ======================================================== */

    ctx.fillStyle =
        '#f59e0b';

    ctx.font =
        '900 28px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    ctx.fillText(
        'OSHI-GE',
        58,
        62
    );

    ctx.fillStyle =
        '#64748b';

    ctx.font =
        '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    ctx.fillText(
        'GAME RECOMMENDATION CARD',
        58,
        91
    );


    /* ========================================================
       タイトル
       ======================================================== */

    ctx.fillStyle =
        '#ffffff';

    ctx.font =
        '900 58px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    const titleLines =
        wrapCanvasText(
            ctx,
            title,
            58,
            158,
            1080,
            70,
            2
        );


    /* ========================================================
       キャッチコピー
       ======================================================== */

    const quoteY =
        300 +
        Math.max(
            0,
            titleLines - 1
        ) * 20;

    drawRoundRect(
        ctx,
        58,
        quoteY,
        1084,
        150,
        18
    );

    ctx.fillStyle =
        'rgba(245,158,11,0.10)';

    ctx.fill();

    ctx.strokeStyle =
        'rgba(245,158,11,0.65)';

    ctx.lineWidth = 2;

    ctx.stroke();


    ctx.fillStyle =
        '#f59e0b';

    ctx.font =
        '900 20px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    ctx.fillText(
        'このゲームを一言で言うと',
        88,
        quoteY + 38
    );


    ctx.fillStyle =
        '#fff7ed';

    ctx.font =
        '900 34px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    wrapCanvasText(
        ctx,
        '「' + catchphrase + '」',
        88,
        quoteY + 84,
        1015,
        46,
        2
    );


    /* ========================================================
       下段
       ======================================================== */

    const lowerY =
        quoteY + 180;

    const leftX = 58;
    const rightX = 620;

    const columnW = 500;


    /* ========================================================
       左：おすすめ情報
       ======================================================== */

    ctx.fillStyle =
        '#cbd5e1';

    ctx.font =
        '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    ctx.fillText(
        'こんな人におすすめ',
        leftX,
        lowerY
    );


    let leftY =
        lowerY + 25;


    drawRoundRect(
        ctx,
        leftX,
        leftY,
        columnW,
        76,
        12
    );

    ctx.fillStyle =
        '#1e293b';

    ctx.fill();

    ctx.strokeStyle =
        '#334155';

    ctx.lineWidth = 1;

    ctx.stroke();


    ctx.fillStyle =
        '#f8fafc';

    ctx.font =
        '700 21px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    if (target) {

        wrapCanvasText(
            ctx,
            target,
            leftX + 22,
            leftY + 32,
            columnW - 44,
            28,
            2
        );

    } else {

        ctx.fillStyle =
            '#64748b';

        ctx.font =
            '600 19px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

        ctx.fillText(
            'あなたに刺さるかもしれない一本',
            leftX + 22,
            leftY + 32
        );
    }


    leftY += 95;


    /* ========================================================
       情報チップ
       ======================================================== */

    const chips = [];

    if (playTime) {
        chips.push(
            'PLAY ' + playTime
        );
    }

    if (genre) {
        chips.push(genre);
    }

    if (platform) {

        platform
        .split(',')
        .map(x => x.trim())
        .filter(Boolean)
        .slice(0, 3)
        .forEach(
            p => chips.push(p)
        );
    }


    let chipX = leftX;
    let chipY = leftY;

    ctx.font =
        '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    for (const chip of chips) {

        const width =
            Math.min(
                240,
                Math.max(
                    105,
                    ctx.measureText(chip).width + 38
                )
            );

        if (
            chipX + width >
            leftX + columnW
        ) {

            chipX = leftX;
            chipY += 58;
        }

        drawRoundRect(
            ctx,
            chipX,
            chipY,
            width,
            46,
            23
        );

        ctx.fillStyle =
            '#172033';

        ctx.fill();

        ctx.strokeStyle =
            '#475569';

        ctx.lineWidth = 1;

        ctx.stroke();

        ctx.fillStyle =
            '#cbd5e1';

        ctx.fillText(
            chip,
            chipX + 19,
            chipY + 30
        );

        chipX +=
            width + 10;
    }


    /* ========================================================
       右：感想
       ======================================================== */

    ctx.fillStyle =
        '#cbd5e1';

    ctx.font =
        '700 18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    ctx.fillText(
        '布教者の感想',
        rightX,
        lowerY
    );


    drawRoundRect(
        ctx,
        rightX,
        lowerY + 25,
        columnW,
        170,
        14
    );

    ctx.fillStyle =
        '#0b1120';

    ctx.fill();

    ctx.strokeStyle =
        '#334155';

    ctx.lineWidth = 1;

    ctx.stroke();


    if (
        spoiler === 0 &&
        content.trim()
    ) {

        ctx.fillStyle =
            '#f8fafc';

        ctx.font =
            '700 22px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

        wrapCanvasText(
            ctx,
            '「' +
            content.trim() +
            '」',
            rightX + 24,
            lowerY + 65,
            columnW - 48,
            34,
            3
        );

    } else {

        ctx.fillStyle =
            spoiler === 2
            ? '#fca5a5'
            : '#fde68a';

        ctx.font =
            '900 21px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

        const spoilerText =
            spoiler === 2
            ? '⚠ ネタバレあり'
            : '🔒 軽微なネタバレあり';

        ctx.fillText(
            spoilerText,
            rightX + 24,
            lowerY + 68
        );

        ctx.fillStyle =
            '#64748b';

        ctx.font =
            '600 17px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

        ctx.fillText(
            '詳細な感想はOshi-Geでチェック',
            rightX + 24,
            lowerY + 105
        );
    }


    /* ========================================================
       フッター
       ======================================================== */

    ctx.strokeStyle =
        '#334155';

    ctx.lineWidth = 1;

    ctx.beginPath();

    ctx.moveTo(
        58,
        718
    );

    ctx.lineTo(
        1142,
        718
    );

    ctx.stroke();


    ctx.fillStyle =
        '#64748b';

    ctx.font =
        '18px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    ctx.fillText(
        '布教者：' + username,
        58,
        754
    );


    ctx.fillStyle =
        '#f59e0b';

    ctx.font =
        '900 20px "Noto Sans JP", "Yu Gothic", Arial, sans-serif';

    const brand =
        'Oshi-Ge';

    ctx.fillText(
        brand,
        1142 -
        ctx.measureText(brand).width,
        754
    );
}


/* ============================================================
   布教カード画像保存
   ============================================================ */

function downloadPromoCard() {

    const modal =
        document.getElementById(
            'promo-card-modal'
        );

    const canvas =
        document.getElementById(
            'promoCanvas'
        );

    if (!modal || !canvas) return;

    const title =
        modal.dataset.title ||
        'oshi-ge';

    const safeName =
        title.replace(
            /[\\/:*?"<>|]/g,
            '_'
        );


    canvas.toBlob(
        function(blob) {

            if (!blob) {

                openPromoImage();
                return;
            }

            const url =
                URL.createObjectURL(blob);

            const a =
                document.createElement('a');

            a.download =
                `Oshi-Ge_${safeName}.png`;

            a.href = url;

            document.body.appendChild(a);

            a.click();

            a.remove();

            setTimeout(
                () => URL.revokeObjectURL(url),
                1000
            );
        },
        'image/png'
    );
}


/* ============================================================
   スマホ用：画像を共有
   ============================================================ */

async function sharePromoCard() {

    const modal =
        document.getElementById(
            'promo-card-modal'
        );

    const canvas =
        document.getElementById(
            'promoCanvas'
        );

    if (!modal || !canvas) return;


    canvas.toBlob(
        async function(blob) {

            if (!blob) {
                openPromoImage();
                return;
            }

            const title =
                modal.dataset.title ||
                'Oshi-Ge';

            const safeName =
                title.replace(
                    /[\\/:*?"<>|]/g,
                    '_'
                );

            const file =
                new File(
                    [blob],
                    `Oshi-Ge_${safeName}.png`,
                    {
                        type: 'image/png'
                    }
                );


            try {

                if (
                    navigator.share &&
                    navigator.canShare &&
                    navigator.canShare({
                        files: [file]
                    })
                ) {

                    await navigator.share({
                        title: 'Oshi-Ge 布教カード',
                        text: `『${title}』を布教します！`,
                        files: [file]
                    });

                } else {

                    openPromoImage();
                }

            } catch (e) {

                console.log(e);
            }

        },
        'image/png'
    );
}


/* ============================================================
   保存できないスマホ用
   ============================================================ */

function openPromoImage() {

    const canvas =
        document.getElementById(
            'promoCanvas'
        );

    if (!canvas) return;

    const image =
        canvas.toDataURL(
            'image/png'
        );

    const newWindow =
        window.open(
            '',
            '_blank'
        );

    if (!newWindow) {

        alert(
            'ポップアップがブロックされています。カードをスクリーンショットして保存してください。'
        );

        return;
    }

    newWindow.document.write(`
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta name="viewport"
                  content="width=device-width, initial-scale=1.0">
            <title>Oshi-Ge 布教カード</title>
            <style>
                body {
                    margin: 0;
                    background: #000;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                }
                img {
                    max-width: 100%;
                    height: auto;
                }
            </style>
        </head>
        <body>
            <img src="${image}">
        </body>
        </html>
    `);

    newWindow.document.close();
}


/* ============================================================
   ESCで閉じる
   ============================================================ */

document.addEventListener(
    'keydown',
    (e) => {

        if (e.key === 'Escape') {
            closePromoCard();
        }
    }
);
"""


# ============================================================
# 4. Base HTML
# ============================================================

BASE_HTML = """

<!DOCTYPE html>

<html lang="ja">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>
        Oshi-Ge | ネタバレなしゲーム布教サイト
    </title>


    <!-- Google Analytics -->

    <script
        async
        src="https://www.googletagmanager.com/gtag/js?id=G-XRFBSR9HSR">
    </script>

    <script>

        window.dataLayer =
            window.dataLayer || [];

        function gtag(){
            dataLayer.push(arguments);
        }

        gtag(
            'js',
            new Date()
        );

        gtag(
            'config',
            'G-XRFBSR9HSR'
        );

    </script>


    <style>
        {{ css }}
    </style>

</head>


<body>

<header class="header-container">

    <h1>
        <a href="/">
            🎮 Oshi-Ge
        </a>
    </h1>

    <div
        style="
            display:flex;
            gap:1rem;
            flex-wrap:wrap;
            justify-content:center;
        "
    >

        <a
            href="/games/new"
            class="btn btn-primary btn-small"
            style="color:#ffffff;"
        >
            ＋ ゲームを布教する
        </a>

        <a
            href="/mypage"
            class="btn btn-outline btn-small"
            style="color:var(--text-main);"
        >
            👤 マイページ
        </a>

    </div>

</header>


{% if is_top %}

<div class="hero">

    <h2>
        誰かの人生を変える1本を。
    </h2>

    <p>
        未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。
    </p>


    <form
        action="/"
        method="get"
        class="search-bar-advanced"
    >

        <div class="search-inputs">

            <input
                type="text"
                name="q"
                placeholder="タイトル・感想・おすすめ対象などを検索..."
                value="{{ q }}"
            >


            <select name="genre">

                <option value="">
                    全ジャンル
                </option>

                {% set genres_list = [
                    "RPG",
                    "アクション",
                    "アドベンチャー",
                    "シミュレーション",
                    "FPS / TPS",
                    "パズル",
                    "ノベル",
                    "ホラー",
                    "インディー",
                    "その他 / 不明"
                ] %}

                {% for g in genres_list %}

                    <option
                        value="{{ g }}"
                        {% if genre == g %}
                            selected
                        {% endif %}
                    >
                        {{ g }}
                    </option>

                {% endfor %}

            </select>


            <select name="platform">

                <option value="">
                    全機種
                </option>

                {% set platforms_list = [
                    "PC",
                    "Switch",
                    "Switch2",
                    "PS5",
                    "Xbox",
                    "スマホ",
                    "その他"
                ] %}

                {% for p in platforms_list %}

                    <option
                        value="{{ p }}"
                        {% if platform == p %}
                            selected
                        {% endif %}
                    >
                        {{ p }}
                    </option>

                {% endfor %}

            </select>


            <button
                type="submit"
                class="btn btn-primary"
            >
                🔎 探す
            </button>

        </div>

    </form>


    <a
        href="/games/random"
        class="btn btn-outline"
        style="
            margin-top:1rem;
            border-style:dashed;
        "
    >
        🎲 ランダムにゲームを探す
    </a>

</div>

{% endif %}


<main>
    {{ content }}
</main>


<script>
    {{ js }}
</script>

</body>

</html>

"""


# ============================================================
# 5. トップページ
# ============================================================

INDEX_HTML = """

<!-- ========================================================
     探し方
     ======================================================== -->

<div class="discover-panel">

    <h3>
        🔎 こんなゲームを探してる？
    </h3>

    <div
        style="
            color:var(--text-sub);
            margin-bottom:0.9rem;
        "
    >
        タイトルを知らなくても大丈夫。気分や好みから探せます。
    </div>


    <div class="quick-filter-grid">

        <a
            class="quick-filter"
            href="/?q=ストーリー"
        >
            📖 ストーリー重視
        </a>

        <a
            class="quick-filter"
            href="/?q=泣ける"
        >
            😭 泣ける
        </a>

        <a
            class="quick-filter"
            href="/?q=一人"
        >
            👤 一人で遊びたい
        </a>

        <a
            class="quick-filter"
            href="/?q=短時間"
        >
            ⏱ 短時間
        </a>

        <a
            class="quick-filter"
            href="/?q=ホラー"
        >
            😱 ホラー
        </a>

        <a
            class="quick-filter"
            href="/?q=インディー"
        >
            💎 インディー
        </a>

        <a
            class="quick-filter"
            href="/?q=初心者"
        >
            🌱 初心者向け
        </a>

        <a
            class="quick-filter"
            href="/?q=感想"
        >
            💬 感想から探す
        </a>

        <a
            class="quick-filter"
            href="/?sort=likes"
        >
            🔥 人気の布教
        </a>

        <a
            class="quick-filter"
            href="/games/random"
        >
            🎲 完全ランダム
        </a>

    </div>

</div>


<!-- ========================================================
     メイン
     ======================================================== -->

<div class="layout-wrapper">

    <div class="main-column">


        <!-- 一覧ヘッダー -->

        <div
            style="
                display:flex;
                justify-content:space-between;
                align-items:flex-end;
                border-bottom:2px solid var(--border);
                padding-bottom:0.5rem;
                margin-bottom:1.5rem;
                gap:1rem;
                flex-wrap:wrap;
            "
        >

            <div>

                <h3 style="margin:0;">
                    {% if q or genre or platform %}
                        🔎 検索結果
                    {% else %}
                        布教されているゲーム
                    {% endif %}
                </h3>

                {% if q or genre or platform %}

                    <div
                        style="
                            color:var(--text-sub);
                            font-size:0.85rem;
                            margin-top:0.3rem;
                        "
                    >
                        {% if q %}
                            「{{ q }}」
                        {% endif %}

                        {% if genre %}
                            {{ genre }}
                        {% endif %}

                        {% if platform %}
                            {{ platform }}
                        {% endif %}

                        の検索結果
                    </div>

                {% endif %}

            </div>


            <div
                style="
                    display:flex;
                    gap:0.5rem;
                    flex-wrap:wrap;
                "
            >

                <a
                    href="?sort=new{% if q %}&q={{ q }}{% endif %}{% if genre %}&genre={{ genre }}{% endif %}{% if platform %}&platform={{ platform }}{% endif %}"
                    class="btn btn-outline btn-small"
                    style="
                        {% if sort == 'new' or not sort %}
                            background:rgba(245,158,11,0.1);
                            border-color:var(--accent);
                            color:var(--accent);
                        {% endif %}
                    "
                >
                    🕒 最新
                </a>


                <a
                    href="?sort=posts{% if q %}&q={{ q }}{% endif %}{% if genre %}&genre={{ genre }}{% endif %}{% if platform %}&platform={{ platform }}{% endif %}"
                    class="btn btn-outline btn-small"
                    style="
                        {% if sort == 'posts' %}
                            background:rgba(245,158,11,0.1);
                            border-color:var(--accent);
                            color:var(--accent);
                        {% endif %}
                    "
                >
                    🔥 投稿数
                </a>


                <a
                    href="?sort=likes{% if q %}&q={{ q }}{% endif %}{% if genre %}&genre={{ genre }}{% endif %}{% if platform %}&platform={{ platform }}{% endif %}"
                    class="btn btn-outline btn-small"
                    style="
                        {% if sort == 'likes' %}
                            background:rgba(245,158,11,0.1);
                            border-color:var(--accent);
                            color:var(--accent);
                        {% endif %}
                    "
                >
                    👍 人気
                </a>

            </div>

        </div>


        <!-- ゲーム一覧 -->

        <div class="game-grid">

            {% for game in games %}

                <div
                    class="game-card"
                    onclick="location.href='/games/{{ game.id }}'"
                >

                    {% if game.image_url %}

                        <img
                            src="{{ game.image_url }}"
                            alt=""
                            class="game-thumbnail"
                            onerror="this.style.display='none'"
                        >

                    {% else %}

                        <div class="game-thumbnail empty">
                            NO IMAGE
                        </div>

                    {% endif %}


                    <div class="game-card-body">

                        <h3
                            style="
                                font-size:1.2rem;
                                margin:0 0 0.5rem 0;
                                color:var(--text-main);
                            "
                        >
                            {{ game.title }}
                        </h3>


                        <div style="margin-bottom:1rem;">

                            {% if game.genre %}

                                <span
                                    class="tag genre"
                                    style="margin:0;"
                                >
                                    🎮 {{ game.genre }}
                                </span>

                            {% endif %}


                            <span
                                class="tag"
                                style="
                                    margin:0;
                                    background:transparent;
                                    border:1px solid var(--border);
                                    color:var(--text-sub);
                                "
                            >
                                💬 {{ game.post_count }}件
                            </span>


                            {% if game.total_likes > 0 %}

                                <span
                                    class="tag"
                                    style="
                                        margin:0;
                                        background:rgba(245,158,11,0.1);
                                        color:var(--accent);
                                    "
                                >
                                    👍 {{ game.total_likes }}
                                </span>

                            {% endif %}


                            {% if game.platform %}

                                {% for p in game.platform.split(',') %}

                                    {% if p.strip() %}

                                        <span
                                            class="tag"
                                            style="
                                                margin:0;
                                                margin-top:0.3rem;
                                            "
                                        >
                                            💻 {{ p.strip() }}
                                        </span>

                                    {% endif %}

                                {% endfor %}

                            {% endif %}

                        </div>


                        {% if game.latest_catchphrase %}

                            <div class="latest-catchphrase">
                                「{{ game.latest_catchphrase }}」
                            </div>

                        {% endif %}

                    </div>

                </div>


            {% else %}

                <div
                    style="
                        grid-column:1 / -1;
                        text-align:center;
                        color:var(--text-sub);
                        padding:3rem;
                        background:var(--card-bg);
                        border-radius:12px;
                    "
                >

                    <p>
                        条件に合うゲームが見つかりませんでした。
                    </p>

                    <a
                        href="/"
                        class="btn btn-outline btn-small"
                    >
                        条件をリセット
                    </a>

                </div>

            {% endfor %}

        </div>

    </div>


    <!-- ====================================================
         人気ランキング
         ==================================================== -->

    <div class="sidebar-column">

        <div
            class="card"
            style="
                border-color:var(--accent);
                padding:1.2rem;
            "
        >

            <h3
                style="
                    margin-top:0;
                    color:var(--accent);
                    border-bottom:1px solid var(--border);
                    padding-bottom:0.5rem;
                "
            >
                👑 今週の人気ゲーム
            </h3>


            <div
                style="
                    display:flex;
                    flex-direction:column;
                    gap:1rem;
                    margin-top:1rem;
                "
            >

                {% for item in weekly_ranking %}

                    <div
                        style="
                            display:flex;
                            gap:1rem;
                            align-items:center;
                            cursor:pointer;
                        "
                        onclick="location.href='/games/{{ item.id }}'"
                    >

                        <div
                            style="
                                width:60px;
                                height:60px;
                                border-radius:8px;
                                overflow:hidden;
                                background:#334155;
                                flex-shrink:0;
                            "
                        >

                            {% if item.image_url %}

                                <img
                                    src="{{ item.image_url }}"
                                    style="
                                        width:100%;
                                        height:100%;
                                        object-fit:cover;
                                    "
                                    onerror="this.style.display='none'"
                                >

                            {% else %}

                                <div
                                    style="
                                        width:100%;
                                        height:100%;
                                        display:flex;
                                        align-items:center;
                                        justify-content:center;
                                        font-size:0.6rem;
                                        color:#94a3b8;
                                    "
                                >
                                    NO IMG
                                </div>

                            {% endif %}

                        </div>


                        <div>

                            <div
                                style="
                                    font-weight:bold;
                                    color:var(--text-main);
                                    font-size:0.95rem;
                                    margin-bottom:0.2rem;
                                "
                            >
                                {{ item.title }}
                            </div>

                            <div
                                style="
                                    font-size:0.8rem;
                                    color:var(--accent);
                                "
                            >
                                🔥 今週 {{ item.weekly_posts }} 件
                            </div>

                        </div>

                    </div>

                {% else %}

                    <div
                        style="
                            color:var(--text-sub);
                            font-size:0.9rem;
                        "
                    >
                        今週の布教はまだありません。
                    </div>

                {% endfor %}

            </div>

        </div>

    </div>

</div>

"""


# ============================================================
# 6. ゲームページ
# ============================================================

GAME_HTML = """

<div
    class="card"
    style="position:relative;"
>

    <div
        style="
            display:flex;
            justify-content:space-between;
            align-items:flex-start;
            margin-bottom:1rem;
            gap:1rem;
            flex-wrap:wrap;
        "
    >

        <h2
            style="
                font-size:2rem;
                margin:0;
                font-weight:900;
            "
        >
            {{ game.title }}
        </h2>


        <div
            style="
                display:flex;
                gap:0.5rem;
                flex-wrap:wrap;
            "
        >

            <button
                type="button"
                class="btn-bookmark {% if is_bookmarked %}bookmarked{% endif %}"
                onclick="toggleBookmark({{ game.id }}, this)"
            >

                {% if is_bookmarked %}
                    🔖 お気に入り解除
                {% else %}
                    🔖 お気に入りに追加
                {% endif %}

            </button>


            <a
                href="/games/{{ game.id }}/edit"
                class="btn btn-outline btn-small"
                style="padding:0.5rem 1rem;"
            >
                ⚙️ 編集
            </a>

        </div>

    </div>


    {% if game.image_url %}

        <div>

            <img
                src="{{ game.image_url }}"
                class="game-hero-image"
                onerror="this.style.display='none'"
            >

        </div>

    {% endif %}


    <div style="margin-bottom:1.5rem;">

        {% if game.genre %}

            <span class="tag genre">
                🎮 {{ game.genre }}
            </span>

        {% endif %}


        {% if game.platform %}

            {% for p in game.platform.split(',') %}

                {% if p.strip() %}

                    <span class="tag">
                        💻 {{ p.strip() }}
                    </span>

                {% endif %}

            {% endfor %}

        {% endif %}

    </div>


    <div
        style="
            background:#0f172a;
            padding:1.5rem;
            border-radius:8px;
            border:1px solid var(--border);
            margin-bottom:1.5rem;
        "
    >

        <p
            style="
                margin:0;
                white-space:pre-wrap;
                color:#cbd5e1;
            "
        >
            {{ game.description }}
        </p>

    </div>


    <div
        style="
            display:flex;
            gap:0.5rem;
            border-top:1px solid var(--border);
            padding-top:1.5rem;
            flex-wrap:wrap;
        "
    >

        <button
            type="button"
            class="btn btn-x"
            onclick="shareGameToX('{{ game.title }}')"
        >
            𝕏 でゲームを共有
        </button>

        <button
            type="button"
            class="btn btn-line"
            onclick="shareGameToLine('{{ game.title }}')"
        >
            LINE でゲームを共有
        </button>

    </div>

</div>


<!-- ========================================================
     布教フォーム
     ======================================================== -->

<div
    class="card"
    style="
        border-color:var(--accent);
        box-shadow:0 0 15px rgba(245,158,11,0.1);
    "
>

    <h3
        style="
            border-bottom:2px solid var(--border);
            padding-bottom:0.5rem;
            color:var(--accent);
        "
    >
        🔥 このゲームを布教する
    </h3>


    <form
        action="/games/{{ game.id }}/posts"
        method="post"
        style="margin-top:1.5rem;"
    >

        <div class="form-group">

            <label>
                布教ネーム（匿名可）:
            </label>

            <input
                type="text"
                name="username"
                value="名無しの布教者"
                required
            >

        </div>


        <div
            style="
                background:#0b1120;
                padding:1.5rem;
                border-radius:8px;
                border:1px solid var(--border);
                margin-bottom:1.5rem;
            "
        >

            <div class="form-group">

                <label
                    style="color:var(--accent);"
                >
                    一言で布教すると？（必須）:
                </label>

                <input
                    type="text"
                    name="catchphrase"
                    required
                    placeholder="例：最後まで遊んだときに、やってよかったと思える作品"
                    style="
                        border-color:
                        rgba(245,158,11,0.5);
                    "
                >

            </div>


            <div
                style="
                    display:flex;
                    gap:1rem;
                    margin-bottom:0;
                    flex-wrap:wrap;
                "
            >

                <div
                    class="form-group"
                    style="
                        flex:1;
                        min-width:200px;
                        margin-bottom:0;
                    "
                >

                    <label>
                        誰におすすめ？:
                    </label>

                    <input
                        type="text"
                        name="target_audience"
                        placeholder="例：ストーリー重視の人"
                    >

                </div>


                <div
                    class="form-group"
                    style="
                        flex:1;
                        min-width:200px;
                        margin-bottom:0;
                    "
                >

                    <label>
                        プレイ時間:
                    </label>

                    <input
                        type="text"
                        name="play_time"
                        placeholder="例：10～15時間"
                    >

                </div>

            </div>

        </div>


        <div class="form-group">

            <label>
                ネタバレレベル（詳細コメントの公開設定）:
            </label>


            <div class="spoiler-radio-group">

                <label class="radio-label">

                    <div class="radio-header">

                        <input
                            type="radio"
                            name="spoiler_level"
                            value="0"
                            checked
                        >

                        <span
                            style="color:var(--safe)"
                        >
                            Lv.0 ネタバレなし
                        </span>

                    </div>

                    <span class="radio-desc">
                        未プレイの人が読んでも問題ない内容
                    </span>

                </label>


                <label class="radio-label">

                    <div class="radio-header">

                        <input
                            type="radio"
                            name="spoiler_level"
                            value="1"
                        >

                        <span
                            style="color:var(--warning)"
                        >
                            Lv.1 軽微なネタバレ
                        </span>

                    </div>

                    <span class="radio-desc">
                        序盤の設定など、体験に多少影響する内容
                    </span>

                </label>


                <label class="radio-label">

                    <div class="radio-header">

                        <input
                            type="radio"
                            name="spoiler_level"
                            value="2"
                        >

                        <span
                            style="color:var(--danger)"
                        >
                            Lv.2 ネタバレあり
                        </span>

                    </div>

                    <span class="radio-desc">
                        ストーリー展開など、体験を大きく左右する内容
                    </span>

                </label>

            </div>

        </div>


        <div class="form-group">

            <label>
                布教コメントの詳細（必須）:
            </label>

            <textarea
                name="content"
                rows="4"
                required
                placeholder="熱い思いをぶつけてください。"
            ></textarea>

        </div>


        <button
            type="submit"
            class="btn btn-primary"
            style="
                width:100%;
                font-size:1.1rem;
                padding:1rem;
            "
        >
            布教を投稿する
        </button>

    </form>

</div>


<!-- ========================================================
     投稿一覧
     ======================================================== -->

<div>

    <div
        style="
            display:flex;
            justify-content:space-between;
            align-items:flex-end;
            margin-bottom:1rem;
            gap:1rem;
            flex-wrap:wrap;
        "
    >

        <h3 style="margin:0;">
            みんなの布教
        </h3>


        <div
            style="
                display:flex;
                gap:0.5rem;
            "
        >

            <a
                href="?sort=likes"
                class="btn btn-outline btn-small"
                style="
                    {% if sort == 'likes' or not sort %}
                        background:rgba(245,158,11,0.1);
                        border-color:var(--accent);
                        color:var(--accent);
                    {% endif %}
                "
            >
                👍 おすすめ順
            </a>


            <a
                href="?sort=new"
                class="btn btn-outline btn-small"
                style="
                    {% if sort == 'new' %}
                        background:rgba(245,158,11,0.1);
                        border-color:var(--accent);
                        color:var(--accent);
                    {% endif %}
                "
            >
                🕒 新着順
            </a>

        </div>

    </div>


    {% for post in posts %}

        <div class="card post-card">


            <div class="post-header">

                <span class="post-author">
                    👤 {{ post.username }}
                </span>


                <div
                    style="
                        display:flex;
                        align-items:center;
                        gap:1rem;
                    "
                >

                    <span>
                        {{
                            post.created_at.strftime('%Y-%m-%d %H:%M')
                            if post.created_at
                            else ''
                        }}
                    </span>


                    {% if post.id in my_posts %}

                        <a
                            href="/games/{{ game.id }}/posts/{{ post.id }}/edit"
                            class="btn btn-outline btn-small"
                            style="
                                padding:0.2rem 0.5rem;
                                font-size:0.8rem;
                            "
                        >
                            ⚙ 編集
                        </a>

                    {% endif %}

                </div>

            </div>


            {% if post.catchphrase %}

                <div style="margin-bottom:1.25rem;">

                    <h4 class="catchphrase-text">
                        「{{ post.catchphrase }}」
                    </h4>


                    <div
                        style="
                            display:flex;
                            flex-wrap:wrap;
                            gap:0.5rem;
                            font-size:0.85rem;
                        "
                    >

                        {% if post.target_audience %}

                            <span class="meta-tag">
                                🎯 {{ post.target_audience }}におすすめ
                            </span>

                        {% endif %}


                        {% if post.play_time %}

                            <span class="meta-tag">
                                ⏱ {{ post.play_time }}
                            </span>

                        {% endif %}

                    </div>

                </div>

            {% endif %}


            {% if post.spoiler_level == 0 %}

                <div>

                    <span class="spoiler-badge safe">
                        🔐 ネタバレなしの詳細
                    </span>


                    <div class="post-content">

                        <p>
                            {{ post.content }}
                        </p>

                    </div>

                </div>


            {% elif post.spoiler_level == 1 %}

                <div>

                    <button
                        type="button"
                        class="spoiler-toggle-btn warning"
                        onclick="toggleSpoiler(this)"
                    >
                        🔒 軽微なネタバレの詳細【クリックして表示】
                    </button>


                    <div
                        class="spoiler-hidden-text"
                        style="display:none;"
                    >

                        <div class="post-content">

                            <p>
                                {{ post.content }}
                            </p>

                        </div>

                    </div>

                </div>


            {% elif post.spoiler_level == 2 %}

                <div>

                    <button
                        type="button"
                        class="spoiler-toggle-btn danger"
                        onclick="toggleSpoiler(this)"
                    >
                        ⚠ ネタバレありの詳細【クリックして表示】
                    </button>


                    <div
                        class="spoiler-hidden-text"
                        style="display:none;"
                    >

                        <div class="post-content">

                            <p>
                                {{ post.content }}
                            </p>

                        </div>

                    </div>

                </div>

            {% endif %}


            <!-- 投稿アクション -->

            <div
                style="
                    display:flex;
                    justify-content:space-between;
                    align-items:center;
                    margin-top:1.5rem;
                    border-top:1px dashed var(--border);
                    padding-top:0.75rem;
                    gap:0.5rem;
                    flex-wrap:wrap;
                "
            >

                <div
                    style="
                        display:flex;
                        gap:0.5rem;
                        flex-wrap:wrap;
                    "
                >

                    <button
                        type="button"
                        class="btn btn-outline btn-small"
                        data-id="{{ game.id }}"
                        data-title="{{ game.title }}"
                        data-catch="{{ post.catchphrase }}"
                        data-content="{{ post.content }}"
                        data-spoiler="{{ post.spoiler_level }}"
                        onclick="sharePost(this, 'x')"
                    >
                        𝕏 で共有
                    </button>


                    <button
                        type="button"
                        class="btn btn-outline btn-small"
                        style="
                            color:#06C755;
                            border-color:rgba(6,199,85,0.5);
                        "
                        data-id="{{ game.id }}"
                        data-title="{{ game.title }}"
                        data-catch="{{ post.catchphrase }}"
                        data-content="{{ post.content }}"
                        data-spoiler="{{ post.spoiler_level }}"
                        onclick="sharePost(this, 'line')"
                    >
                        LINE で共有
                    </button>


                    <button
                        type="button"
                        class="btn btn-outline btn-small"
                        onclick='openPromoCard(
                            {{ game.title|tojson }},
                            {{ post.catchphrase|default('')|tojson }},
                            {{ post.target_audience|default('')|tojson }},
                            {{ post.play_time|default('')|tojson }},
                            {{ post.username|default('名無しの布教者')|tojson }},
                            {{ game.genre|default('')|tojson }},
                            {{ game.platform|default('')|tojson }},
                            {{ post.spoiler_level|default(0) }},
                            {{ post.content|default('')|tojson }}
                        )'
                    >
                        🎴 布教カード
                    </button>

                </div>


                <button
                    type="button"
                    class="btn-like"
                    data-post-id="{{ post.id }}"
                    onclick="likePost(
                        {{ game.id }},
                        {{ post.id }},
                        this
                    )"
                >
                    👍 いいね
                    <span>
                        {{ post.likes | default(0) }}
                    </span>
                </button>

            </div>

        </div>


    {% else %}

        <div
            class="card"
            style="
                text-align:center;
                color:var(--text-sub);
                padding:3rem 0;
                background:transparent;
                border:1px dashed var(--border);
            "
        >

            <p style="margin:0;">
                まだ布教コメントがありません。<br>
                最初の布教者になりませんか？
            </p>

        </div>

    {% endfor %}

</div>


<!-- ========================================================
     布教カードモーダル
     ======================================================== -->

<div
    id="promo-card-modal"
    class="promo-modal"
    style="display:none;"
    onclick="
        if(event.target===this)
        closePromoCard();
    "
>

    <div class="promo-modal-box">


        <div class="promo-modal-head">

            <h3>
                🎴 布教カード
            </h3>


            <button
                type="button"
                class="btn btn-outline btn-small"
                onclick="closePromoCard()"
            >
                ✕ 閉じる
            </button>

        </div>


        <div class="promo-canvas-wrap">

            <canvas
                id="promoCanvas"
                width="1200"
                height="800"
            ></canvas>

        </div>


        <div class="promo-modal-actions">

            <button
                type="button"
                class="btn btn-primary"
                onclick="downloadPromoCard()"
            >
                ⬇️ 画像を保存
            </button>


            <button
                type="button"
                class="btn btn-outline"
                onclick="sharePromoCard()"
            >
                📤 画像を共有
            </button>


            <button
                type="button"
                class="btn btn-outline"
                onclick="openPromoImage()"
            >
                🖼️ 画像を開く
            </button>

        </div>


        <div
            style="
                color:var(--text-sub);
                font-size:0.85rem;
                margin-top:0.7rem;
                line-height:1.6;
            "
        >
            PCでは「画像を保存」、スマホでは「画像を共有」が便利です。
            保存できない場合は「画像を開く」からスクリーンショットでも保存できます。
        </div>

    </div>

</div>

"""


# ============================================================
# 7. マイページ
# ============================================================

MYPAGE_HTML = """

<div class="card">

    <h2
        style="
            border-bottom:2px solid var(--border);
            padding-bottom:0.5rem;
            margin-bottom:1.5rem;
        "
    >
        👤 マイページ
    </h2>


    <h3
        style="
            color:var(--accent);
            margin-top:2rem;
        "
    >
        🔖 お気に入りに追加したゲーム
    </h3>


    <div
        class="game-grid"
        style="margin-bottom:3rem;"
    >

        {% for game in bookmarked_games %}

            <div
                class="game-card"
                onclick="location.href='/games/{{ game.id }}'"
            >

                {% if game.image_url %}

                    <img
                        src="{{ game.image_url }}"
                        alt=""
                        class="game-thumbnail"
                        onerror="this.style.display='none'"
                    >

                {% else %}

                    <div class="game-thumbnail empty">
                        NO IMAGE
                    </div>

                {% endif %}


                <div class="game-card-body">

                    <h3
                        style="
                            font-size:1.2rem;
                            margin:0 0 0.5rem 0;
                            color:var(--text-main);
                        "
                    >
                        {{ game.title }}
                    </h3>


                    <div>

                        <span class="tag genre">
                            🎮 {{ game.genre }}
                        </span>

                    </div>

                </div>

            </div>

        {% else %}

            <div
                style="
                    grid-column:1 / -1;
                    color:var(--text-sub);
                    padding:1rem;
                "
            >
                お気に入りに登録したゲームはまだありません。
            </div>

        {% endfor %}

    </div>


    <h3 style="color:var(--accent);">
        ✍ 自分の布教履歴
    </h3>


    <div>

        {% for post in my_posts_list %}

            <div
                class="card post-card"
                style="margin-bottom:1rem;"
            >

                <div
                    style="
                        font-weight:bold;
                        margin-bottom:0.5rem;
                    "
                >

                    <a
                        href="/games/{{ post.game_id }}"
                        style="
                            color:var(--accent);
                            text-decoration:underline;
                        "
                    >
                        {{ post.game_title }}
                    </a>

                    への布教

                </div>


                <div
                    class="post-header"
                    style="margin-bottom:0.5rem;"
                >

                    <span class="post-author">
                        {{ post.username }}
                    </span>


                    <div
                        style="
                            display:flex;
                            gap:1rem;
                            align-items:center;
                        "
                    >

                        <span>
                            {{
                                post.created_at.strftime('%Y-%m-%d %H:%M')
                                if post.created_at
                                else ''
                            }}
                        </span>


                        <a
                            href="/games/{{ post.game_id }}/posts/{{ post.id }}/edit"
                            class="btn btn-outline btn-small"
                            style="padding:0.2rem 0.5rem;"
                        >
                            ⚙️ 編集
                        </a>

                    </div>

                </div>


                {% if post.catchphrase %}

                    <div
                        class="catchphrase-text"
                        style="
                            font-size:1.1rem;
                            margin-bottom:0.5rem;
                        "
                    >
                        「{{ post.catchphrase }}」
                    </div>

                {% endif %}


                <div
                    style="
                        color:var(--text-sub);
                        font-size:0.9rem;
                        margin-bottom:1rem;
                    "
                >
                    👍 いいね:
                    {{ post.likes | default(0) }}
                </div>


                <div
                    style="
                        display:flex;
                        gap:0.5rem;
                        border-top:1px dashed var(--border);
                        padding-top:0.75rem;
                        flex-wrap:wrap;
                    "
                >

                    <button
                        type="button"
                        class="btn btn-outline btn-small"
                        data-id="{{ post.game_id }}"
                        data-title="{{ post.game_title }}"
                        data-catch="{{ post.catchphrase }}"
                        data-content="{{ post.content }}"
                        data-spoiler="{{ post.spoiler_level }}"
                        onclick="sharePost(this, 'x')"
                    >
                        𝕏 で共有
                    </button>


                    <button
                        type="button"
                        class="btn btn-outline btn-small"
                        style="
                            color:#06C755;
                            border-color:rgba(6,199,85,0.5);
                        "
                        data-id="{{ post.game_id }}"
                        data-title="{{ post.game_title }}"
                        data-catch="{{ post.catchphrase }}"
                        data-content="{{ post.content }}"
                        data-spoiler="{{ post.spoiler_level }}"
                        onclick="sharePost(this, 'line')"
                    >
                        LINE で共有
                    </button>

                </div>

            </div>


        {% else %}

            <div
                style="
                    color:var(--text-sub);
                    padding:1rem;
                "
            >
                布教履歴はまだありません。
            </div>

        {% endfor %}

    </div>

</div>

"""


# ============================================================
# 8. ゲーム追加
# ============================================================

NEW_GAME_HTML = """

<div class="card">

    <h2
        style="
            border-bottom:2px solid var(--border);
            padding-bottom:0.5rem;
            margin-bottom:1.5rem;
        "
    >
        ゲームを追加する
    </h2>


    {% if error_msg %}

        <div
            style="
                background:rgba(239,68,68,0.1);
                color:var(--danger);
                padding:1rem;
                border-left:4px solid var(--danger);
                margin-bottom:1.5rem;
            "
        >
            ⚠️ {{ error_msg }}
        </div>

    {% endif %}


    <form
        action="/games/new"
        method="post"
    >

        <div class="form-group">

            <label>
                タイトル（必須）:
            </label>

            <input
                type="text"
                name="title"
                value="{{ title | default('') }}"
                required
            >

        </div>


        <div class="form-group">

            <label>
                ジャンル:
            </label>

            <select name="genre">

                {% set genres = [
                    "RPG",
                    "アクション",
                    "アドベンチャー",
                    "シミュレーション",
                    "FPS / TPS",
                    "パズル",
                    "ノベル",
                    "ホラー",
                    "インディー",
                    "その他 / 不明"
                ] %}

                {% for g in genres %}

                    <option
                        value="{{ g }}"
                        {% if genre == g or (not genre and g == "その他 / 不明") %}
                            selected
                        {% endif %}
                    >
                        {{ g }}
                    </option>

                {% endfor %}

            </select>

        </div>


        <div class="form-group checkbox-group">

            <label>
                プラットフォーム（複数選択可）:
            </label>


            <div
                style="
                    display:flex;
                    flex-wrap:wrap;
                    gap:1rem;
                    padding:0.5rem 0;
                "
            >

                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="PC"
                        onchange="updatePlatform(this.form)"
                    >
                    PC
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="Switch"
                        onchange="updatePlatform(this.form)"
                    >
                    Switch
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="Switch2"
                        onchange="updatePlatform(this.form)"
                    >
                    Switch2
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="PS5"
                        onchange="updatePlatform(this.form)"
                    >
                    PS5
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="Xbox"
                        onchange="updatePlatform(this.form)"
                    >
                    Xbox
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="スマホ"
                        onchange="updatePlatform(this.form)"
                    >
                    スマホ
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="その他"
                        onchange="updatePlatform(this.form)"
                    >
                    その他
                </label>

            </div>


            <input
                type="hidden"
                name="platform"
                class="platform-hidden"
                value="{{ platform | default('') }}"
            >

        </div>


        <div class="form-group">

            <label>
                画像URL（任意）:
            </label>

            <input
                type="text"
                name="image_url"
                value="{{ image_url | default('') }}"
            >

        </div>


        <div class="form-group">

            <label>
                ゲームの簡単な説明:
            </label>

            <textarea
                name="description"
                rows="4"
            >{{ description | default('') }}</textarea>

        </div>


        <button
            type="submit"
            class="btn btn-primary"
            style="
                width:100%;
                margin-top:1rem;
            "
        >
            ゲームを登録する
        </button>

    </form>

</div>

"""


# ============================================================
# 9. ゲーム編集
# ============================================================

EDIT_GAME_HTML = """

<div class="card">

    <h2
        style="
            border-bottom:2px solid var(--border);
            padding-bottom:0.5rem;
            margin-bottom:1.5rem;
        "
    >
        ゲーム情報を編集する
    </h2>


    <form
        action="/games/{{ game.id }}/edit"
        method="post"
    >

        <div class="form-group">

            <label>
                タイトル（必須）:
            </label>

            <input
                type="text"
                name="title"
                value="{{ game.title }}"
                required
            >

        </div>


        <div class="form-group">

            <label>
                ジャンル:
            </label>

            <select name="genre">

                {% set genres = [
                    "RPG",
                    "アクション",
                    "アドベンチャー",
                    "シミュレーション",
                    "FPS / TPS",
                    "パズル",
                    "ノベル",
                    "ホラー",
                    "インディー",
                    "その他 / 不明"
                ] %}

                {% for g in genres %}

                    <option
                        value="{{ g }}"
                        {% if game.genre == g %}
                            selected
                        {% endif %}
                    >
                        {{ g }}
                    </option>

                {% endfor %}

            </select>

        </div>


        <div class="form-group checkbox-group">

            <label>
                プラットフォーム（複数選択可）:
            </label>


            <div
                style="
                    display:flex;
                    flex-wrap:wrap;
                    gap:1rem;
                    padding:0.5rem 0;
                "
            >

                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="PC"
                        onchange="updatePlatform(this.form)"
                    >
                    PC
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="Switch"
                        onchange="updatePlatform(this.form)"
                    >
                    Switch
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="Switch2"
                        onchange="updatePlatform(this.form)"
                    >
                    Switch2
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="PS5"
                        onchange="updatePlatform(this.form)"
                    >
                    PS5
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="Xbox"
                        onchange="updatePlatform(this.form)"
                    >
                    Xbox
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="スマホ"
                        onchange="updatePlatform(this.form)"
                    >
                    スマホ
                </label>


                <label>
                    <input
                        type="checkbox"
                        class="platform-cb"
                        value="その他"
                        onchange="updatePlatform(this.form)"
                    >
                    その他
                </label>

            </div>


            <input
                type="hidden"
                name="platform"
                class="platform-hidden"
                value="{{ game.platform | default('') }}"
            >

        </div>


        <div class="form-group">

            <label>
                画像URL（任意）:
            </label>

            <input
                type="text"
                name="image_url"
                value="{{ game.image_url | default('') }}"
            >

        </div>


        <div class="form-group">

            <label>
                ゲームの簡単な説明:
            </label>

            <textarea
                name="description"
                rows="4"
            >{{ game.description }}</textarea>

        </div>


        <div
            style="
                display:flex;
                gap:1rem;
                margin-top:1.5rem;
            "
        >

            <a
                href="/games/{{ game.id }}"
                class="btn btn-outline"
                style="
                    flex:1;
                    text-align:center;
                "
            >
                キャンセル
            </a>


            <button
                type="submit"
                class="btn btn-primary"
                style="flex:2;"
            >
                変更を保存する
            </button>

        </div>

    </form>

</div>

"""


# ============================================================
# 10. 投稿編集
# ============================================================

EDIT_POST_HTML = """

<div
    class="card"
    style="border-color:var(--accent);"
>

    <h2
        style="
            border-bottom:2px solid var(--border);
            padding-bottom:0.5rem;
            margin-bottom:1.5rem;
            color:var(--accent);
        "
    >
        自分の布教を編集する
    </h2>


    <form
        action="/games/{{ game_id }}/posts/{{ post.id }}/edit"
        method="post"
    >

        <div class="form-group">

            <label>
                布教ネーム（匿名可）:
            </label>

            <input
                type="text"
                name="username"
                value="{{ post.username }}"
                required
            >

        </div>


        <div
            style="
                background:#0b1120;
                padding:1.5rem;
                border-radius:8px;
                border:1px solid var(--border);
                margin-bottom:1.5rem;
            "
        >

            <div class="form-group">

                <label style="color:var(--accent);">
                    一言で布教すると？（必須）:
                </label>

                <input
                    type="text"
                    name="catchphrase"
                    value="{{ post.catchphrase | default('') }}"
                    required
                    style="
                        border-color:
                        rgba(245,158,11,0.5);
                    "
                >

            </div>


            <div
                style="
                    display:flex;
                    gap:1rem;
                    margin-bottom:0;
                    flex-wrap:wrap;
                "
            >

                <div
                    class="form-group"
                    style="
                        flex:1;
                        min-width:200px;
                        margin-bottom:0;
                    "
                >

                    <label>
                        誰におすすめ？:
                    </label>

                    <input
                        type="text"
                        name="target_audience"
                        value="{{ post.target_audience | default('') }}"
                    >

                </div>


                <div
                    class="form-group"
                    style="
                        flex:1;
                        min-width:200px;
                        margin-bottom:0;
                    "
                >

                    <label>
                        プレイ時間:
                    </label>

                    <input
                        type="text"
                        name="play_time"
                        value="{{ post.play_time | default('') }}"
                    >

                </div>

            </div>

        </div>


        <div class="form-group">

            <label>
                ネタバレレベル:
            </label>


            <div class="spoiler-radio-group">

                <label class="radio-label">

                    <div class="radio-header">

                        <input
                            type="radio"
                            name="spoiler_level"
                            value="0"
                            {% if post.spoiler_level == 0 %}
                                checked
                            {% endif %}
                        >

                        <span style="color:var(--safe)">
                            Lv.0 ネタバレなし
                        </span>

                    </div>

                </label>


                <label class="radio-label">

                    <div class="radio-header">

                        <input
                            type="radio"
                            name="spoiler_level"
                            value="1"
                            {% if post.spoiler_level == 1 %}
                                checked
                            {% endif %}
                        >

                        <span style="color:var(--warning)">
                            Lv.1 軽微なネタバレ
                        </span>

                    </div>

                </label>


                <label class="radio-label">

                    <div class="radio-header">

                        <input
                            type="radio"
                            name="spoiler_level"
                            value="2"
                            {% if post.spoiler_level == 2 %}
                                checked
                            {% endif %}
                        >

                        <span style="color:var(--danger)">
                            Lv.2 ネタバレあり
                        </span>

                    </div>

                </label>

            </div>

        </div>


        <div class="form-group">

            <label>
                布教コメントの詳細（必須）:
            </label>

            <textarea
                name="content"
                rows="4"
                required
            >{{ post.content }}</textarea>

        </div>


        <div
            style="
                display:flex;
                gap:1rem;
                margin-top:1.5rem;
            "
        >

            <a
                href="/games/{{ game_id }}"
                class="btn btn-outline"
                style="
                    flex:1;
                    text-align:center;
                "
            >
                キャンセル
            </a>


            <button
                type="submit"
                class="btn btn-primary"
                style="flex:2;"
            >
                変更を保存する
            </button>

        </div>

    </form>

</div>

"""


# ============================================================
# 11. ページ描画
# ============================================================

def render_page(
    content_template_str,
    is_top=False,
    **kwargs
):

    content_html =
        Template(
            content_template_str
        ).render(**kwargs)

    return HTMLResponse(
        Template(
            BASE_HTML
        ).render(
            css=CSS,
            js=JS,
            content=content_html,
            is_top=is_top,
            **kwargs
        )
    )


# ============================================================
# 12. トップページ
# ============================================================

@app.get("/")
async def read_root(
    q: str = "",
    genre: str = "",
    platform: str = "",
    sort: str = "new"
):

    order_clause = """
        g.created_at DESC
    """


    if sort == "posts":

        order_clause = """
            (SELECT COUNT(*)
             FROM posts p
             WHERE p.game_id = g.id) DESC,
            g.created_at DESC
        """


    elif sort == "likes":

        order_clause = """
            COALESCE(
                (
                    SELECT SUM(p.likes)
                    FROM posts p
                    WHERE p.game_id = g.id
                ),
                0
            ) DESC,
            g.created_at DESC
        """


    query = """
        SELECT
            g.*,

            (
                SELECT p.catchphrase
                FROM posts p
                WHERE p.game_id = g.id
                ORDER BY p.created_at DESC
                LIMIT 1
            ) AS latest_catchphrase,

            (
                SELECT COUNT(*)
                FROM posts p
                WHERE p.game_id = g.id
            ) AS post_count,

            (
                SELECT COALESCE(SUM(p.likes), 0)
                FROM posts p
                WHERE p.game_id = g.id
            ) AS total_likes

        FROM games g

        WHERE 1=1
    """


    params = []


    # --------------------------------------------------------
    # 検索
    # --------------------------------------------------------

    if q:

        search =
            '%' +
            q +
            '%'


        query += """
            AND (

                g.title ILIKE %s

                OR COALESCE(
                    g.description,
                    ''
                ) ILIKE %s

                OR COALESCE(
                    g.genre,
                    ''
                ) ILIKE %s

                OR COALESCE(
                    g.platform,
                    ''
                ) ILIKE %s

                OR EXISTS (

                    SELECT 1
                    FROM posts sp

                    WHERE sp.game_id = g.id

                    AND (

                        COALESCE(
                            sp.catchphrase,
                            ''
                        ) ILIKE %s

                        OR COALESCE(
                            sp.target_audience,
                            ''
                        ) ILIKE %s

                        OR COALESCE(
                            sp.play_time,
                            ''
                        ) ILIKE %s

                        OR COALESCE(
                            sp.content,
                            ''
                        ) ILIKE %s
                    )
                )
            )
        """


        params.extend(
            [search] * 8
        )


    # --------------------------------------------------------
    # ジャンル
    # --------------------------------------------------------

    if genre:

        query += """
            AND g.genre = %s
        """

        params.append(genre)


    # --------------------------------------------------------
    # プラットフォーム
    # --------------------------------------------------------

    if platform:

        query += """
            AND g.platform ILIKE %s
        """

        params.append(
            '%' +
            platform +
            '%'
        )


    with get_db_connection() as conn:

        games =
            conn.execute(
                query +
                f"""
                    ORDER BY
                    {order_clause}
                    LIMIT 100
                """,
                params
            ).fetchall()


        weekly_ranking =
            conn.execute(
                """
                SELECT
                    g.id,
                    g.title,
                    g.image_url,
                    COUNT(p.id) AS weekly_posts

                FROM games g

                JOIN posts p
                    ON g.id = p.game_id

                WHERE
                    p.created_at >=
                    NOW() - INTERVAL '7 days'

                GROUP BY
                    g.id

                ORDER BY
                    weekly_posts DESC,
                    g.created_at DESC

                LIMIT 5
                """
            ).fetchall()


    return render_page(
        INDEX_HTML,
        is_top=True,
        games=games,
        q=q,
        genre=genre,
        platform=platform,
        sort=sort,
        weekly_ranking=weekly_ranking
    )


# ============================================================
# 13. ランダムゲーム
# ============================================================

@app.get("/games/random")
async def random_game():

    with get_db_connection() as conn:

        game =
            conn.execute(
                """
                SELECT id
                FROM games
                ORDER BY RANDOM()
                LIMIT 1
                """
            ).fetchone()


    if game:

        return RedirectResponse(
            url=f"/games/{game['id']}",
            status_code=303
        )


    return RedirectResponse(
        url="/",
        status_code=303
    )


# ============================================================
# 14. ゲーム追加画面
# ============================================================

@app.get("/games/new")
async def new_game_form():

    return render_page(
        NEW_GAME_HTML
    )


# ============================================================
# 15. ゲーム追加
# ============================================================

@app.post("/games/new")
async def create_game(
    title: str = Form(...),
    description: str = Form(""),
    genre: str = Form(""),
    platform: str = Form(""),
    image_url: str = Form("")
):

    with get_db_connection() as conn:

        existing =
            conn.execute(
                """
                SELECT id
                FROM games
                WHERE LOWER(title) =
                      LOWER(%s)
                """,
                (title,)
            ).fetchone()


        if existing:

            return render_page(
                NEW_GAME_HTML,
                error_msg=
                    f"「{title}」は既に登録されています。",
                title=title,
                description=description,
                genre=genre,
                platform=platform,
                image_url=image_url
            )


        cursor =
            conn.execute(
                """
                INSERT INTO games
                    (
                        title,
                        description,
                        genre,
                        platform,
                        image_url
                    )

                VALUES
                    (%s, %s, %s, %s, %s)

                RETURNING id
                """,
                (
                    title,
                    description,
                    genre,
                    platform,
                    image_url
                )
            )


        game_id =
            cursor.fetchone()["id"]


        conn.commit()


    return RedirectResponse(
        url=f"/games/{game_id}",
        status_code=303
    )


# ============================================================
# 16. ゲーム編集
# ============================================================

@app.get("/games/{game_id}/edit")
async def edit_game_form(
    game_id: int
):

    with get_db_connection() as conn:

        game =
            conn.execute(
                """
                SELECT *
                FROM games
                WHERE id = %s
                """,
                (game_id,)
            ).fetchone()


    if not game:

        raise HTTPException(
            status_code=404,
            detail="Game not found"
        )


    return render_page(
        EDIT_GAME_HTML,
        game=game
    )


# ============================================================
# 17. ゲーム更新
# ============================================================

@app.post("/games/{game_id}/edit")
async def update_game(
    game_id: int,
    title: str = Form(...),
    description: str = Form(""),
    genre: str = Form(""),
    platform: str = Form(""),
    image_url: str = Form("")
):

    with get_db_connection() as conn:

        conn.execute(
            """
            UPDATE games

            SET
                title = %s,
                description = %s,
                genre = %s,
                platform = %s,
                image_url = %s

            WHERE id = %s
            """,
            (
                title,
                description,
                genre,
                platform,
                image_url,
                game_id
            )
        )

        conn.commit()


    return RedirectResponse(
        url=f"/games/{game_id}",
        status_code=303
    )


# ============================================================
# 18. ゲーム詳細
# ============================================================

@app.get("/games/{game_id}")
async def read_game(
    request: Request,
    game_id: int,
    sort: str = "likes"
):

    with get_db_connection() as conn:

        game =
            conn.execute(
                """
                SELECT *
                FROM games
                WHERE id = %s
                """,
                (game_id,)
            ).fetchone()


        if not game:

            raise HTTPException(
                status_code=404,
                detail="Game not found"
            )


        if sort == "new":

            order_sql =
                """
                created_at DESC
                """

        else:

            order_sql =
                """
                likes DESC,
                created_at DESC
                """


        posts =
            conn.execute(
                f"""
                SELECT *
                FROM posts
                WHERE game_id = %s
                ORDER BY {order_sql}
                """,
                (game_id,)
            ).fetchall()


    my_posts = [
        int(x)
        for x in
        request.cookies
        .get("my_posts", "")
        .split(",")
        if x.isdigit()
    ]


    bookmarks = [
        int(x)
        for x in
        request.cookies
        .get("bookmarks", "")
        .split(",")
        if x.isdigit()
    ]


    return render_page(
        GAME_HTML,
        game=game,
        posts=posts,
        sort=sort,
        my_posts=my_posts,
        is_bookmarked=(
            game_id in bookmarks
        )
    )


# ============================================================
# 19. 布教投稿
# ============================================================

@app.post("/games/{game_id}/posts")
async def create_post(
    request: Request,
    game_id: int,
    username: str = Form(...),
    catchphrase: str = Form(...),
    target_audience: str = Form(""),
    play_time: str = Form(""),
    content: str = Form(...),
    spoiler_level: int = Form(...)
):

    with get_db_connection() as conn:

        cursor =
            conn.execute(
                """
                INSERT INTO posts
                    (
                        game_id,
                        username,
                        catchphrase,
                        target_audience,
                        play_time,
                        content,
                        spoiler_level
                    )

                VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )

                RETURNING id
                """,
                (
                    game_id,
                    username,
                    catchphrase,
                    target_audience,
                    play_time,
                    content,
                    spoiler_level
                )
            )


        post_id =
            cursor.fetchone()["id"]


        conn.commit()


    res =
        RedirectResponse(
            url=f"/games/{game_id}",
            status_code=303
        )


    c =
        request.cookies.get(
            "my_posts",
            ""
        )


    res.set_cookie(
        key="my_posts",
        value=(
            f"{c},{post_id}"
            if c
            else str(post_id)
        ),
        max_age=60 * 60 * 24 * 365
    )


    return res


# ============================================================
# 20. 投稿編集画面
# ============================================================

@app.get("/games/{game_id}/posts/{post_id}/edit")
async def edit_post_form(
    request: Request,
    game_id: int,
    post_id: int
):

    my_posts = [
        int(x)
        for x in
        request.cookies
        .get("my_posts", "")
        .split(",")
        if x.isdigit()
    ]


    if post_id not in my_posts:

        raise HTTPException(
            status_code=403,
            detail="権限がありません。"
        )


    with get_db_connection() as conn:

        post =
            conn.execute(
                """
                SELECT *
                FROM posts
                WHERE id = %s
                  AND game_id = %s
                """,
                (
                    post_id,
                    game_id
                )
            ).fetchone()


    if not post:

        raise HTTPException(
            status_code=404
        )


    return render_page(
        EDIT_POST_HTML,
        game_id=game_id,
        post=post
    )


# ============================================================
# 21. 投稿更新
# ============================================================

@app.post("/games/{game_id}/posts/{post_id}/edit")
async def update_post(
    request: Request,
    game_id: int,
    post_id: int,
    username: str = Form(...),
    catchphrase: str = Form(...),
    target_audience: str = Form(""),
    play_time: str = Form(""),
    content: str = Form(...),
    spoiler_level: int = Form(...)
):

    my_posts = [
        int(x)
        for x in
        request.cookies
        .get("my_posts", "")
        .split(",")
        if x.isdigit()
    ]


    if post_id not in my_posts:

        raise HTTPException(
            status_code=403
        )


    with get_db_connection() as conn:

        conn.execute(
            """
            UPDATE posts

            SET
                username = %s,
                catchphrase = %s,
                target_audience = %s,
                play_time = %s,
                content = %s,
                spoiler_level = %s

            WHERE
                id = %s
                AND game_id = %s
            """,
            (
                username,
                catchphrase,
                target_audience,
                play_time,
                content,
                spoiler_level,
                post_id,
                game_id
            )
        )

        conn.commit()


    return RedirectResponse(
        url=f"/games/{game_id}",
        status_code=303
    )


# ============================================================
# 22. いいね
# ============================================================

@app.post("/games/{game_id}/posts/{post_id}/like")
async def like_post(
    game_id: int,
    post_id: int
):

    with get_db_connection() as conn:

        cursor =
            conn.execute(
                """
                UPDATE posts

                SET likes =
                    COALESCE(likes, 0) + 1

                WHERE id = %s

                RETURNING likes
                """,
                (post_id,)
            )


        result =
            cursor.fetchone()


        if not result:

            raise HTTPException(
                status_code=404,
                detail="Post not found"
            )


        likes =
            result["likes"]


        conn.commit()


    return {
        "likes": likes
    }


# ============================================================
# 23. お気に入り
# ============================================================

@app.post("/games/{game_id}/bookmark")
async def toggle_bookmark(
    request: Request,
    game_id: int
):

    bookmarks = [
        int(x)
        for x in
        request.cookies
        .get("bookmarks", "")
        .split(",")
        if x.isdigit()
    ]


    is_bookmarked = False


    if game_id in bookmarks:

        bookmarks.remove(
            game_id
        )

    else:

        bookmarks.append(
            game_id
        )

        is_bookmarked = True


    res =
        JSONResponse(
            content={
                "bookmarked":
                    is_bookmarked
            }
        )


    res.set_cookie(
        "bookmarks",
        ",".join(
            map(
                str,
                bookmarks
            )
        ),
        max_age=60 * 60 * 24 * 365
    )


    return res


# ============================================================
# 24. マイページ
# ============================================================

@app.get("/mypage")
async def mypage(
    request: Request
):

    my_posts_ids = [
        int(x)
        for x in
        request.cookies
        .get("my_posts", "")
        .split(",")
        if x.isdigit()
    ]


    bookmarks = [
        int(x)
        for x in
        request.cookies
        .get("bookmarks", "")
        .split(",")
        if x.isdigit()
    ]


    my_posts_list = []
    bookmarked_games = []


    with get_db_connection() as conn:

        if my_posts_ids:

            my_posts_list =
                conn.execute(
                    """
                    SELECT
                        p.*,
                        g.title AS game_title

                    FROM posts p

                    JOIN games g
                        ON p.game_id = g.id

                    WHERE
                        p.id = ANY(%s)

                    ORDER BY
                        p.created_at DESC
                    """,
                    (my_posts_ids,)
                ).fetchall()


        if bookmarks:

            bookmarked_games =
                conn.execute(
                    """
                    SELECT *
                    FROM games

                    WHERE id = ANY(%s)

                    ORDER BY
                        created_at DESC
                    """,
                    (bookmarks,)
                ).fetchall()


    return render_page(
        MYPAGE_HTML,
        my_posts_list=my_posts_list,
        bookmarked_games=bookmarked_games
    )


# ============================================================
# 25. サーバー起動
# ============================================================

if __name__ == "__main__":

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000
    )
