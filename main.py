import os
import io
import re
import time
import uuid
import base64
import logging
import urllib.request
import socket
import ipaddress
import json
import secrets
import hashlib
import threading
from collections import defaultdict
from functools import lru_cache
from typing import List, Optional
from urllib.parse import urlparse, urlencode
from xml.sax.saxutils import escape as xml_escape

import uvicorn
from fastapi import FastAPI, Request, Form, HTTPException, Response, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jinja2 import Environment
from markupsafe import Markup
from itsdangerous import URLSafeSerializer
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import psycopg
from psycopg import errors as pgerrors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oshige")

Image.MAX_IMAGE_PIXELS = 25_000_000

app = FastAPI()
security = HTTPBasic()

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "2"))

# --- 運営者情報（環境変数で設定。未設定でも動作します） ---
OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "Oshi-Ge運営")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")
CONTACT_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSd-T-pvp84tbmSImJpUi79bhk1AW6CgEIeZVeh4vVgmDsZFlw/viewform?usp=publish-editor"
ADSENSE_PUB_ID = "pub-6608111802250449"
# アフィリエイトリンクを表示するために必要な布教投稿数
AFFILIATE_MIN_POSTS = 3

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    logger.warning("SECRET_KEY is not set. Using a temporary random key. User sessions will be lost on restart.")
    SECRET_KEY = os.urandom(24).hex()
    
serializer = URLSafeSerializer(SECRET_KEY)

pool = None
if DATABASE_URL:
    try:
        pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row, "sslmode": "require", "prepare_threshold": None})
    except Exception as e:
        logger.error(f"Failed to initialize ConnectionPool: {e}")

def get_db_connection():
    if pool is None:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode="require")
    return pool.connection()

GENRES = ["RPG", "アクション", "アドベンチャー", "シミュレーション", "FPS / TPS", "パズル", "ノベル", "ホラー", "インディー", "その他 / 不明"]
PLATFORMS = ["PC", "Switch", "Switch2", "PS5", "Xbox", "スマホ", "その他"]
OSHI_POINTS = ["📖 ストーリーが最高", "👤 キャラが魅力的", "🎵 BGM・音楽が神", "⚔️ バトルが爽快", "🌍 世界観に浸れる", "⏳ やり込み要素あり", "🎬 演出がエモい", "👑 運営が神"]
REPORT_REASONS = ["ネタバレ", "誹謗中傷", "スパム", "その他"]
ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")

GENRE_SLUGS = {
    "rpg": "RPG",
    "action": "アクション",
    "adventure": "アドベンチャー",
    "simulation": "シミュレーション",
    "fps-tps": "FPS / TPS",
    "puzzle": "パズル",
    "novel": "ノベル",
    "horror": "ホラー",
    "indie": "インディー",
    "other": "その他 / 不明"
}

# ジャンルページ用の運営者オリジナル紹介文（各ジャンルページ冒頭に表示）
GENRE_INTROS = {
    "rpg": "RPGは、主人公の成長や長い物語をじっくり味わえるジャンルです。レベル上げや装備集めで少しずつ強くなる手応えがあり、世界観やキャラクターに愛着が湧きやすいのが魅力。ターン制、アクション寄り、オープンワールド型など遊び方の幅も広く、クリアまでに数十時間かかる作品も珍しくありません。ここでは、RPGが好きな人がネタバレを避けながら熱く語ったおすすめを集めています。「どんな人におすすめか」「プレイ時間の目安」を手がかりに、次の一本を探してみてください。",
    "action": "アクションは、操作そのものの気持ちよさと、上達したときの達成感が楽しいジャンルです。爽快なバトルを楽しむタイプ、シビアな難易度に挑戦するタイプ、探索や移動の楽しさを重視するタイプなど、作品ごとに個性があります。ストーリーを追うのが苦手でも、短い時間で遊びやすい作品が多いのも特徴です。このページでは、アクションゲームの魅力を実際にプレイした人の言葉で紹介しています。難易度やプレイ時間についての感想も、選ぶときの参考にしてください。",
    "adventure": "アドベンチャーは、物語や謎解き、探索を通じて世界に入り込むジャンルです。選択肢で展開が変わる作品、アイテムを集めて謎を解く作品、景色や雰囲気を味わう作品など、戦闘が少なくても没入感のある体験ができます。ストーリーが核になるため、ネタバレに特に配慮が必要なジャンルでもあります。ここでは、ネタバレレベルを明示した布教コメントを集めています。未プレイの人でも安心して読める紹介から、気になる一本を見つけてください。",
    "simulation": "シミュレーションは、街づくり、経営、育成、生活体験など、自分で状況をコントロールしていく楽しさがあるジャンルです。正解が一つではなく、プレイヤーごとに違う物語が生まれるのが魅力で、気づけば時間を忘れて遊んでいる、ということも多いです。じっくり考えるのが好きな人や、コツコツ積み上げるのが好きな人に向いています。このページでは、シミュレーションゲームのハマりポイントや、遊び始めのコツを語った布教を集めています。",
    "fps-tps": "FPS／TPSは、銃や武器を使って戦う一人称・三人称視点のシューティングです。対人戦で腕を競う作品、協力して敵に立ち向かう作品、物語を重視したシングルプレイ作品などがあり、同じジャンルでも体験が大きく変わります。反射神経だけでなく、立ち回りやチームワークも重要になります。ここでは、プレイスタイルや遊ぶ人数、操作の慣れやすさなど、選ぶときに役立つ視点を含んだ布教コメントを紹介しています。",
    "puzzle": "パズルは、ひらめきや論理的な思考を楽しむジャンルです。短い時間でも遊べるものが多く、スキマ時間に向いています。落ち物、謎解き、パズルアクションなど種類も多彩で、解けたときの気持ちよさは他のジャンルにはない魅力です。難しすぎず簡単すぎないバランスも作品選びの大事なポイント。このページでは、パズルゲームの難易度やプレイ時間の目安など、実際に遊んだ人のリアルな感想を集めています。",
    "novel": "ノベルは、文章と演出で物語を楽しむジャンルです。操作はシンプルで、読み進めることが中心のため、ゲームに慣れていない人でも入りやすいのが魅力です。恋愛、ミステリー、ホラー、群像劇など題材は幅広く、音楽やイラスト、声の演技が体験を大きく左右します。ネタバレが体験の価値に直結するジャンルなので、このページでは特にネタバレレベルを意識した布教コメントを集めています。",
    "horror": "ホラーは、恐怖や緊張感を楽しむジャンルです。驚かされるタイプ、じわじわと不安が増していくタイプ、謎を追うタイプなど、怖さの質は作品によってさまざまです。一人でじっくり遊ぶ人もいれば、友達と悲鳴をあげながら楽しむ人もいます。苦手な人は「怖さの度合い」を事前に知っておくと安心です。ここでは、怖さの種類やおすすめの遊び方に触れた、ネタバレ配慮の布教コメントを紹介しています。",
    "indie": "インディーゲームは、個人や小規模チームが作る、独創的なアイデアが光る作品群です。大作にはない尖った発想や、作り手の思いが伝わる手触りが魅力で、価格も手頃なものが多くあります。一方で知名度が低く、出会う機会が少ないのが難点です。Oshi-Geは、そんな隠れた良作をもっと知ってもらうための場所でもあります。このページでは、プレイした人だからこそ語れるインディーゲームの魅力を集めています。",
    "other": "ジャンルの枠に収まらない作品や、ジャンルがわからない作品もこのカテゴリにまとめています。複数のジャンルをまたぐ作品や、新しい遊び方を提案する作品など、思わぬ出会いがあるかもしれません。「どんな人におすすめか」「プレイ時間」などの布教コメントを手がかりに、気になる一本を探してみてください。ジャンルが分かる方は、ゲーム情報の編集から正しいジャンルに変更してもらえると助かります。",
}

# 運営者が書いたガイド記事
ARTICLES = [
    {
        "slug": "how-to-choose-game",
        "title": "次に遊ぶゲームの選び方｜失敗しないための5つの視点",
        "desc": "次の一本が決まらない人へ。遊べる時間、好みの体験、プラットフォーム、ネタバレ耐性、レビューの読み方の5つの視点から、自分に合うゲームを選ぶコツを解説します。",
        "body": """
<p>ゲームは数が多く、毎月のように新しい作品が発売されます。「何を遊べばいいかわからない」と悩むのは自然なことです。このガイドでは、自分に合う一本を見つけるための5つの視点を紹介します。</p>

<h3>1. 自由に使える時間を考える</h3>
<p>まず確認したいのは、ゲームに使える時間です。1日30分ほどしか遊べない人が、一度に何時間も遊ぶ前提の作品を選ぶと、途中で止まってしまいがちです。反対に、休日にまとまった時間がとれるなら、物語を一気に進められる長編も楽しめます。</p>
<p>プレイ時間の目安は、クリアまでの時間と、寄り道を含めた時間の2種類を意識するとよいでしょう。Oshi-Geの布教コメントには「プレイ時間」の欄があるので、実際に遊んだ人の体感を参考にできます。</p>

<h3>2. どんな体験を求めているか</h3>
<p>同じ「面白い」でも、求めているものは人によって違います。</p>
<ul>
<li>物語に浸りたい（ストーリー重視）</li>
<li>操作や戦闘の手応えを楽しみたい（アクション重視）</li>
<li>考えてひらめく快感がほしい（パズル・謎解き重視）</li>
<li>自分のペースでコツコツ積み上げたい（シミュレーション・育成重視）</li>
<li>怖さや緊張感を味わいたい（ホラー）</li>
</ul>
<p>最近遊んで「楽しかった」と感じた作品を思い出し、何が良かったのかを言葉にしてみると、次の選択がしやすくなります。</p>

<h3>3. 遊べる機種を確認する</h3>
<p>どれだけ魅力的でも、持っている機種で遊べなければ始められません。PC、Switch、PS5、Xbox、スマホなど、対応機種は作品によって異なります。同じタイトルでも機種ごとに価格や操作感が変わる場合があるので、購入前に確認しましょう。</p>

<h3>4. ネタバレにどこまで耐えられるか</h3>
<p>ストーリーの展開を知らずに遊びたい人もいれば、ある程度知っていても楽しめる人もいます。自分がどちらのタイプかを知っておくと、情報収集の仕方が変わります。未プレイの作品を調べるときは、ネタバレの有無が明記されている紹介を選ぶと安心です。Oshi-Geでは、すべての布教コメントにネタバレレベルを設定でき、内容が隠れた状態で表示されます。</p>

<h3>5. レビューは「誰に向けた意見か」を読む</h3>
<p>高評価か低評価かだけを見ると、自分に合うかどうかは判断しにくいものです。「どんな人におすすめか」「どこが良かったか」「どんな人には合わなさそうか」が書かれたレビューは、判断材料として役に立ちます。単純な点数よりも、理由が具体的に書かれているものを優先して読みましょう。</p>

<h3>気分で選びたいときは</h3>
<p>どうしても決められないときは、Oshi-Geのトップページにある「目的からゲームを探す」や、ジャンル別のページから、気になるキーワードで探してみてください。思いがけない一本との出会いがあるかもしれません。</p>
""",
    },
    {
        "slug": "how-to-write-oshi-post",
        "title": "ネタバレなしで魅力が伝わる布教文の書き方",
        "desc": "好きなゲームの魅力を、ネタバレなしで未プレイの人に伝えるための書き方を解説。一言キャッチ、おすすめの相手、具体的な体験、ネタバレレベルの考え方と例文テンプレートを紹介します。",
        "body": """
<p>好きなゲームについて語りたいけれど、何を書けばいいかわからない。ネタバレをしてしまいそうで不安。そんな人のために、布教文の基本の組み立て方をまとめました。</p>

<h3>ステップ1：まず「一言」で表現する</h3>
<p>最初に、そのゲームを一言で表してみましょう。ジャンル名や「面白い」だけでは伝わりません。「遊び終わったあと、しばらく余韻が抜けなかった作品」「5分で始められて、気づくと1時間たっているゲーム」のように、体験を言葉にするのがコツです。</p>

<h3>ステップ2：誰におすすめかを決める</h3>
<p>万人におすすめと書くよりも、「ストーリー重視の人」「短時間でサクッと遊びたい人」のように対象を絞るほうが、読む人は自分に合うか判断しやすくなります。反対に、「こういう人には合わないかも」を正直に書くと、紹介への信頼感も高まります。</p>

<h3>ステップ3：具体的な体験を書く</h3>
<p>「神ゲー」「最高」だけでは、魅力は伝わりません。次のような具体的なポイントを一つか二つ入れてみてください。</p>
<ul>
<li>どの場面で、どんな気持ちになったか（ネタバレにならない範囲で）</li>
<li>操作や仕組みのどこが気持ちよかったか</li>
<li>音楽や雰囲気、画面の印象</li>
<li>遊び始めてから面白くなるまでの時間</li>
</ul>

<h3>ステップ4：ネタバレレベルを正しく設定する</h3>
<p>Oshi-Geでは、コメントの内容に応じて3段階のレベルを選べます。</p>
<ul>
<li><strong>Lv.0（ネタバレなし）</strong>：未プレイの人が読んでも問題ない内容。序盤の雰囲気や遊び心地など。</li>
<li><strong>Lv.1（軽微なネタバレ）</strong>：序盤の設定など、体験に多少影響する内容。</li>
<li><strong>Lv.2（ネタバレあり）</strong>：物語の展開や結末など、体験を大きく左右する内容。</li>
</ul>
<p>迷ったときは、一段階高いレベルを選んでおくと安全です。</p>

<h3>避けたい書き方</h3>
<ul>
<li>結末や重要な展開を匂わせる書き方（「ラストは驚きの展開」も人によってはネタバレ）</li>
<li>他の作品を下げて、紹介する作品を持ち上げる書き方</li>
<li>特定の人やコミュニティへの攻撃的な表現</li>
</ul>

<h3>例文テンプレート</h3>
<p>一言：〇〇な人にこそ遊んでほしい、△△なゲーム。<br>
おすすめの人：□□が好きな人／短い時間で遊びたい人<br>
推しポイント：◇◇の場面で、思わず声が出ました。遊び始めて1時間ほどで、仕組みの面白さに気づきます。<br>
プレイ時間：クリアまで約〇時間</p>
<p>この形に自分の言葉を当てはめるだけで、読みやすく魅力が伝わる布教文になります。ぜひ、あなたの推しゲームを紹介してください。</p>
""",
    },
    {
        "slug": "beginner-game-guide",
        "title": "ゲーム初心者のための最初の一本の探し方",
        "desc": "ゲームをあまり遊んだことがない人向けに、難易度、プレイ時間、操作のわかりやすさ、ジャンル別の入口、機種の選び方から、最初の一本を探すコツを紹介します。",
        "body": """
<p>「ゲームを始めてみたいけれど、何から遊べばいいかわからない」という声はよく聞かれます。ここでは、ゲーム初心者の人が最初の一本を選ぶときのポイントを紹介します。</p>

<h3>難易度は「やさしめ」から</h3>
<p>最初から難しいゲームを選ぶと、操作に慣れる前に挫折してしまうことがあります。難易度を選べる作品や、失敗してもやり直しやすい作品が安心です。紹介文に「初心者でも遊べる」「ゆっくり進められる」と書かれているかを目安にしてみましょう。</p>

<h3>プレイ時間が短めの作品を選ぶ</h3>
<p>数十時間かかる大作よりも、数時間でクリアできる作品のほうが、「最後まで遊べた」という成功体験を得やすくなります。1回のプレイが短く区切れる作品なら、忙しい日でも続けられます。</p>

<h3>操作がシンプルかどうか</h3>
<p>ボタンが多い作品は、慣れるまで時間がかかります。ボタン操作が少ない作品や、タッチ操作で遊べる作品は、初心者でも入りやすい傾向があります。操作が複雑でも、チュートリアルが丁寧な作品なら問題なく始められます。</p>

<h3>ジャンル別の入口の考え方</h3>
<ul>
<li><strong>物語が好き</strong>：ノベルやアドベンチャー。操作が少なく、読み進めるだけで楽しめます。</li>
<li><strong>頭を使うのが好き</strong>：パズル。短い時間で区切れるものが多いです。</li>
<li><strong>のんびり遊びたい</strong>：シミュレーション。自分のペースで進められます。</li>
<li><strong>体を動かす感覚が好き</strong>：アクション。簡単なモードがある作品から始めるのがおすすめです。</li>
</ul>

<h3>機種の選び方</h3>
<p>すでにスマホやパソコンを持っているなら、まずは追加の機器を買わずに遊べる作品から始めるのが手軽です。据え置き機や携帯機を検討する場合は、遊びたい作品が対応しているかどうか、周りに一緒に遊べる人がいるかどうかを基準にしましょう。</p>

<h3>体験談を参考にする</h3>
<p>実際に遊んだ人の感想は、公式の紹介文よりも「初心者目線での遊びやすさ」が分かりやすいことがあります。Oshi-Geの布教コメントでは、「どんな人におすすめか」「プレイ時間」が書かれているので、最初の一本探しの参考にしてください。トップページの「初心者向け」ボタンからも探せます。</p>
""",
    },
]
ARTICLE_MAP = {a["slug"]: a for a in ARTICLES}

FONT_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Japanese/NotoSansCJKjp-Bold.otf"
FONT_PATH = "/tmp/NotoSansCJKjp-Bold.otf"
_font_lock = threading.Lock()

def ensure_font() -> bool:
    if os.path.exists(FONT_PATH):
        return True
    with _font_lock:
        if os.path.exists(FONT_PATH):
            return True
        try:
            req = urllib.request.Request(FONT_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            with open(FONT_PATH + ".tmp", "wb") as f:
                f.write(data)
            os.replace(FONT_PATH + ".tmp", FONT_PATH)
            return True
        except Exception:
            logger.exception("font download failed")
            return False

def _wrap(draw, text, font, max_w, max_lines):
    lines, line = [], ""
    for ch in text or "":
        if draw.textlength(line + ch, font=font) > max_w and line:
            lines.append(line)
            line = ch
            if len(lines) >= max_lines:
                break
        else:
            line += ch
    if len(lines) < max_lines and line:
        lines.append(line)
    if lines and len("".join(lines)) < len(text or ""):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines

@lru_cache(maxsize=200)
def build_ogp(title: str, genre: str, catch: str, image_url: str) -> bytes:
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), "#0f172a")
    if image_url:
        data, _ = fetch_image_bytes(image_url)
        if data:
            try:
                bg = Image.open(io.BytesIO(data)).convert("RGB")
                scale = max(W / bg.width, H / bg.height)
                bg = bg.resize((int(bg.width * scale), int(bg.height * scale)))
                left, top = (bg.width - W) // 2, (bg.height - H) // 2
                bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(4))
                img = Image.blend(bg, Image.new("RGB", (W, H), "#020617"), 0.7)
            except Exception:
                pass
    d = ImageDraw.Draw(img)
    has_font = ensure_font()
    def F(size):
        return ImageFont.truetype(FONT_PATH, size) if has_font else ImageFont.load_default()

    d.rectangle((0, 60, 16, 130), fill="#f59e0b")
    d.text((50, 62), "OSHI-GE", font=F(56), fill="#f59e0b")
    if genre:
        d.text((50, 150), genre, font=F(30), fill="#fcd34d")
    y = 210
    for t in _wrap(d, title, F(72), 1100, 2):
        d.text((50, y), t, font=F(72), fill="#ffffff")
        y += 90
    y += 15
    if catch:
        for t in _wrap(d, f"「{catch}」", F(40), 1100, 3):
            d.text((50, y), t, font=F(40), fill="#fcd34d")
            y += 55
    d.text((50, H - 60), "ネタバレなしゲーム布教サイト", font=F(28), fill="#94a3b8")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

env = Environment(autoescape=True, finalize=lambda x: "" if x is None else x)
env.globals["GENRE_SLUGS"] = GENRE_SLUGS

@lru_cache(maxsize=500)
def get_template(source: str):
    return env.from_string(source)

POST_COOLDOWN = 30
ip_last_post_time = defaultdict(float)

def get_client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            idx = max(0, len(parts) - TRUSTED_PROXIES)
            return parts[idx]
    return request.client.host if request.client else "unknown"

def check_rate_limit(request: Request) -> bool:
    # 接続元IPの確認用ログ (確認できたら削除可能)
    logger.info(f"XFF={request.headers.get('X-Forwarded-For')} -> {get_client_ip(request)}")
    last = ip_last_post_time.get(get_client_ip(request), 0.0)
    return time.time() - last >= POST_COOLDOWN

def mark_posted(request: Request):
    now = time.time()
    ip_last_post_time[get_client_ip(request)] = now
    if len(ip_last_post_time) > 10000:
        for k in [k for k, v in list(ip_last_post_time.items()) if now - v > POST_COOLDOWN]:
            ip_last_post_time.pop(k, None)

RATE_LIMIT_HTML = "<script>alert('連続投稿は制限されています。少し時間をおいてから再度お試しください。');history.back();</script>"

def alert_back(msg: str) -> HTMLResponse:
    safe_msg = json.dumps(msg)
    return HTMLResponse(f"<script>alert({safe_msg});history.back();</script>")

def clip(s, n: int) -> str:
    return (s or "").strip()[:n]

def clean_genre(g: str) -> str:
    return g if g in GENRES else "その他 / 不明"

def clean_platform(p: str) -> str:
    items = [x.strip() for x in (p or "").split(",")]
    return ",".join([x for x in items if x in PLATFORMS])

def clean_points(points: List[str]) -> str:
    return ",".join([x for x in points if x in OSHI_POINTS])

def clean_x_id(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9_@]', '', s or '')[:20]

def clamp_spoiler(n: int) -> int:
    return max(0, min(2, n))

def get_base_url(request: Request) -> str:
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{scheme}://{host}" if host else ""

def parse_id_cookie(request: Request, name: str) -> List[int]:
    val = request.cookies.get(name)
    if not val: return []
    try:
        parsed = serializer.loads(val)
        if isinstance(parsed, list) and all(isinstance(x, int) for x in parsed):
            return parsed
        return []
    except Exception:
        return []

def set_cookie_safe(res: Response, key: str, values: List[int]):
    values = values[-200:]
    signed_val = serializer.dumps(values)
    res.set_cookie(key=key, value=signed_val, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax", secure=True)

# ---------------------------------------------------------------------------
# Auth Helper Functions & Middleware
# ---------------------------------------------------------------------------
def set_auth_cookies(res: Response, access_token: str, refresh_token: str, expires_in: int = 3600):
    res.set_cookie("sb-access-token", access_token, max_age=int(expires_in), httponly=True, samesite="lax", secure=True)
    res.set_cookie("sb-refresh-token", refresh_token, max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax", secure=True)

def clear_auth_cookies(res: Response):
    res.delete_cookie("sb-access-token")
    res.delete_cookie("sb-refresh-token")

def get_user_id(request: Request) -> Optional[str]:
    if hasattr(request.state, "user_id"):
        return request.state.user_id

    access_token = request.cookies.get("sb-access-token")
    refresh_token = request.cookies.get("sb-refresh-token")
    
    if not access_token and not refresh_token:
        request.state.user_id = None
        return None
        
    if not supabase:
        request.state.user_id = None
        return None

    user_id = None
    try:
        if access_token:
            user_res = supabase.auth.get_user(access_token)
            if user_res and user_res.user:
                user_id = user_res.user.id
    except Exception:
        pass

    if not user_id and refresh_token:
        try:
            session_res = supabase.auth.refresh_session(refresh_token)
            if session_res and session_res.user:
                user_id = session_res.user.id
                request.state.new_session = session_res.session
        except Exception as e:
            logger.warning(f"Session refresh failed: {e}")

    request.state.user_id = user_id
    return user_id

@app.middleware("http")
async def persist_refreshed_session(request: Request, call_next):
    response = await call_next(request)
    s = getattr(request.state, "new_session", None)
    if s:
        set_auth_cookies(response, s.access_token, s.refresh_token, s.expires_in)
    return response

def is_owner(request: Request, post: dict, user_id: Optional[str]) -> bool:
    if user_id and post.get("user_id") is not None and str(post["user_id"]) == user_id:
        return True
    return post["id"] in parse_id_cookie(request, "my_posts")


def init_db():
    try:
        with get_db_connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS games (
                id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT,
                genre TEXT, platform TEXT, image_url TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY, game_id INTEGER REFERENCES games(id), username TEXT NOT NULL,
                content TEXT NOT NULL, spoiler_level INTEGER DEFAULT 0, catchphrase TEXT,
                target_audience TEXT, play_time TEXT, likes INTEGER DEFAULT 0, 
                user_id UUID,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id), 
                reason TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY, title TEXT NOT NULL, username TEXT NOT NULL, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS bookmarks (
                id SERIAL PRIMARY KEY, user_id UUID NOT NULL, game_id INTEGER REFERENCES games(id) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, game_id))''')
                
            conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS platform TEXT")
            conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS image_url TEXT")
            conn.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS developer_x_id TEXT DEFAULT ''")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS catchphrase TEXT")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS target_audience TEXT")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS play_time TEXT")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS likes INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS oshi_points TEXT DEFAULT ''")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS wanna_play INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS agree INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS user_id UUID")
            conn.commit()
    except Exception:
        logger.exception("init_db failed")

    try:
        with get_db_connection() as conn:
            conn.execute("CREATE INDEX IF NOT EXISTS posts_game_id_idx ON posts (game_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS posts_user_id_idx ON posts (user_id)")
            conn.commit()
    except Exception:
        pass

    try:
        with get_db_connection() as conn:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS games_title_lower_uq ON games (LOWER(title))")
            conn.commit()
    except Exception:
        pass

init_db()

def is_safe_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        hostname = p.hostname
        if not hostname:
            return False
        addr_info = socket.getaddrinfo(hostname, 80)
        for res in addr_info:
            ip_str = res[4][0]
            ip = ipaddress.ip_address(ip_str)
            if not ip.is_global:
                return False
        return True
    except Exception:
        return False

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def fetch_image_bytes(url: str, limit: int = 5_000_000):
    if not is_safe_url(url):
        logger.warning(f"SSRF Check failed for URL: {url}")
        return None, None
        
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        opener = urllib.request.build_opener(NoRedirectHandler())
        
        with opener.open(req, timeout=8) as r:
            ct = r.headers.get('Content-Type', '').split(';')[0].strip().lower()
            if ct not in ALLOWED_IMAGE_TYPES:
                logger.warning(f"Invalid Content-Type {ct} for URL: {url}")
                return None, None
                
            data = r.read(limit + 1)
            if len(data) > limit:
                logger.warning(f"Image too large: {url}")
                return None, None
            return data, ct
    except Exception as e:
        logger.warning(f"fetch_image_bytes failed: {url}, Error: {e}")
        return None, None

def process_image(base64_data: str):
    _, encoded = base64_data.split(",", 1)
    raw = base64.b64decode(encoded)
    img = Image.open(io.BytesIO(raw))
    if img.format not in ("JPEG", "PNG", "WEBP"):
        raise ValueError("unsupported image format")
    img.load()
    img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    try:
        img.save(buf, format="WEBP", quality=85)
        return buf.getvalue(), "webp", "image/webp"
    except Exception:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "jpg", "image/jpeg"

def upload_image_to_supabase(base64_data: str) -> str:
    if not base64_data or not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    try:
        file_data, file_ext, mime = process_image(base64_data)
        filename = f"{uuid.uuid4()}.{file_ext}"

        url = f"{SUPABASE_URL}/storage/v1/object/games/{filename}"
        req = urllib.request.Request(url, data=file_data, method="POST")
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Content-Type", mime)

        with urllib.request.urlopen(req, timeout=20):
            pass
        return f"{SUPABASE_URL}/storage/v1/object/public/games/{filename}"
    except Exception:
        return ""

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
.footer { text-align: center; padding: 2rem; border-top: 1px solid var(--border); margin-top: 3rem; color: var(--text-sub); font-size: 0.9rem; }
.footer a { color: var(--text-sub); text-decoration: none; margin: 0 1rem; }
.footer a:hover { color: var(--text-main); text-decoration: underline; }
.footer .footer-genres a { margin: 0 0.5rem; font-size: 0.85rem; display: inline-block; }
.prose { line-height: 1.9; color: #cbd5e1; font-size: 1.05rem; }
.prose h3 { color: var(--accent); margin: 2rem 0 0.75rem; font-size: 1.25rem; border-left: 4px solid var(--accent); padding-left: 0.75rem; }
.prose p { margin: 0 0 1rem; }
.prose ul { margin: 0 0 1rem; padding-left: 1.4rem; }
.prose li { margin-bottom: 0.4rem; }
.prose a { color: #3b82f6; }
.prose table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }
.prose th, .prose td { text-align: left; padding: 0.7rem; border-bottom: 1px solid var(--border); vertical-align: top; }
.prose th { width: 30%; color: var(--text-sub); font-weight: bold; }
.guide-link-card { display: block; text-decoration: none; background: #0f172a; border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem; margin-bottom: 1rem; transition: 0.2s; }
.guide-link-card:hover { border-color: var(--accent); transform: translateY(-2px); }
.guide-link-card .t { color: var(--text-main); font-weight: bold; font-size: 1.1rem; margin-bottom: 0.4rem; }
.guide-link-card .d { color: var(--text-sub); font-size: 0.9rem; }
.genre-chip-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.genre-chip { display: inline-block; padding: 0.4rem 0.9rem; border-radius: 9999px; border: 1px solid var(--border); color: var(--text-main); text-decoration: none; font-size: 0.9rem; font-weight: bold; background: #0f172a; transition: 0.2s; }
.genre-chip:hover { border-color: var(--accent); color: var(--accent); }

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

JS = r"""
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
    const cleanTitleTag = '#' + title.replace(/[\s /／・！!？?♪～描()（）[\]「」『』]/g, '');
    let mentions = "";
    if (devId && devId.trim()) {
        let cleanDevId = devId.trim();
        if (!cleanDevId.startsWith('@')) cleanDevId = '@' + cleanDevId;
        mentions += ' ' + cleanDevId;
    }
    const text = `次に遊ぶ神ゲーを探している方へ🎮\n『${title}』のおすすめ布教ページです！👇\n\n${cleanTitleTag} #推しゲー #OshiGe ${mentions}\n`;
    window.open(`https://x.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(window.location.href)}`, '_blank'); 
}

function shareGameToLine(title) { 
    window.open(`https://line.me/R/msg/text/?${encodeURIComponent(`次に遊ぶ神ゲーを探している方へ🎮\n『${title}』のおすすめ布教ページです！👇\n`)}${encodeURIComponent(window.location.href)}`, '_blank'); 
}

function sharePost(btn, platform) {
    const gameId = btn.dataset.id;
    const title = btn.dataset.title;
    const catchphrase = btn.dataset.catch;
    const content = btn.dataset.content;
    const spoilerLevel = Number(btn.dataset.spoiler || '0');
    const devId = btn.dataset.dev || '';
    const url = window.location.origin + '/games/' + gameId;
    
    const cleanTitleTag = '#' + title.replace(/[\s /／・！!？?♪～描()（）[\]「」『』]/g, '');
    
    let text = `このゲーム、もっと知られてほしい。\n\n🎮 『${title}』`;
    if (catchphrase) text += `\n\n「${catchphrase}」`;
    if (spoilerLevel === 0 && content.trim()) {
        let impression = content.trim();
        if (Array.from(impression).length > 20) impression = Array.from(impression).slice(0, 20).join('') + '…';
        text += `\n\n💬「${impression}」`;
    } else if (spoilerLevel === 1) text += `\n\n🔒 軽微なネタバレを含みます`;
    else if (spoilerLevel === 2) text += `\n\n⚠️ ネタバレあり`;
    
    let mentions = "";
    if (devId.trim()) {
        let cleanDevId = devId.trim();
        if (!cleanDevId.startsWith('@')) cleanDevId = '@' + cleanDevId;
        mentions += ' ' + cleanDevId;
    }
    
    text += `\n\n布教内容はこちら👇\n${url}\n\n${cleanTitleTag} #推しゲー #OshiGe ${mentions}`;

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
    titleEl.textContent = "🎲 ガチャ回転中...";

    let count = 0;
    const maxCount = 20;
    const interval = setInterval(() => {
        const randomGame = allGamesList[Math.floor(Math.random() * allGamesList.length)];
        titleEl.textContent = randomGame.title;
        count++;
        if (count >= maxCount) {
            clearInterval(interval);
            const selectedGame = allGamesList[Math.floor(Math.random() * allGamesList.length)];
            titleEl.textContent = '';
            titleEl.appendChild(document.createTextNode('🎉 神ゲー発掘！'));
            titleEl.appendChild(document.createElement('br'));
            const sp = document.createElement('span');
            sp.style.color = 'var(--accent)';
            sp.style.fontSize = '1.8rem';
            sp.textContent = '『' + selectedGame.title + '』';
            titleEl.appendChild(sp);
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
                alert("🎉 布教の投稿が完了しました！\n生成された「布教カード」をSNSでシェアして、あなたの推しゲーを広めましょう！");
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
        } catch(e) {
            img = null;
        }
    }

    let catchY = 650;
    if (drawH > 600 && drawH < 800) { catchY = drawH + 40; }
    else if (drawH >= 800) { catchY = 840; }

    const catchLines = getLines(catchphrase, 980, '900 65px "Noto Sans JP", sans-serif', 3);
    let panelY = catchY + (catchLines * 85) + 30;
    if(panelY < 600) panelY = 600;

    let currentY = panelY + 70;
    const titleLines = getLines(title, 920, '900 45px "Noto Sans JP", sans-serif', 2);
    currentY += titleLines * 55 + 30;

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

    const tags = [];
    if(playTime) tags.push(playTime);
    if(genre) tags.push(genre);
    if(platform) tags.push(...platform.split(',').map(s=>s.trim()).filter(Boolean));
    if(oshiPoints) tags.push(...oshiPoints.split(',').filter(Boolean));
    if(tags.length) { currentY += 42 + 40; }

    const panelH = currentY - panelY + 20;
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

    let drawTextY = panelY + 70;
    ctx.fillStyle = '#ffffff'; ctx.font = '900 45px "Noto Sans JP", sans-serif';
    const drawnTitleLines = wrapCanvasText(ctx, title, 80, drawTextY, 920, 55, 2);
    drawTextY += drawnTitleLines * 55 + 30;

    if (contentRaw) {
        ctx.fillStyle = '#cbd5e1'; ctx.font = '400 30px "Noto Sans JP", sans-serif';
        const drawnContentLines = wrapCanvasText(ctx, '「' + contentRaw.trim() + '」', 80, drawTextY, 920, 45, 4);
        drawTextY += drawnContentLines * 45 + 40;
    }

    if (target) {
        ctx.fillStyle = '#94a3b8'; ctx.font = '700 22px "Noto Sans JP", sans-serif';
        ctx.fillText('👤 こんな人におすすめ', 80, drawTextY);
        drawTextY += 35;
        ctx.fillStyle = '#f8fafc'; ctx.font = '900 28px "Noto Sans JP", sans-serif';
        wrapCanvasText(ctx, target, 100, drawTextY, 880, 35, 1);
        drawTextY += 60;
    }

    if(tags.length) {
        let tx = 80;
        ctx.font = '700 22px "Noto Sans JP", sans-serif';
        for(let i=0; i<Math.min(tags.length, 6); i++) {
            const tagStr = '#' + tags[i];
            const tw = ctx.measureText(tagStr).width + 30;
            if(tx + tw > 1000) break;
            drawRoundRect(ctx, tx, drawTextY, tw, 42, 21);
            ctx.fillStyle = 'rgba(245, 158, 11, 0.15)'; ctx.fill();
            ctx.fillStyle = '#fcd34d'; ctx.fillText(tagStr, tx + 15, drawTextY + 30);
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
    const cleanTitleTag = '#' + title.replace(/[\s /／・！!？?♪～描()（）[\]「」『』]/g, '');
    
    let text = `このゲーム、もっと知られてほしい。\n\n🎮 『${title}』`;
    if (catchphrase) text += `\n\n「${catchphrase}」`;
    
    if (spoilerLevel === 0 && content.trim()) {
        let impression = content.trim();
        if (Array.from(impression).length > 20) impression = Array.from(impression).slice(0, 20).join('') + '…';
        text += `\n\n💬「${impression}」`;
    } else if (spoilerLevel === 1) text += `\n\n🔒 軽微なネタバレを含みます`;
    else if (spoilerLevel === 2) text += `\n\n⚠️ ネタバレあり`;
    
    let mentions = "";
    if (devId.trim()) {
        let cleanDevId = devId.trim();
        if (!cleanDevId.startsWith('@')) cleanDevId = '@' + cleanDevId;
        mentions += ' ' + cleanDevId;
    }
    
    text += `\n\n布教内容はこちら👇\n${url}\n\n${cleanTitleTag} #推しゲー #OshiGe ${mentions}`;
    
    alert("この後開くXの投稿画面で、先ほど保存した「布教カード画像」を貼り付けてポストしてください！");
    window.open(`https://x.com/intent/tweet?text=${encodeURIComponent(text)}`, '_blank');
}

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePromoCard(); });
"""

BASE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ page_title }}</title>
    <meta name="description" content="{{ og_description }}">
    {% if noindex %}<meta name="robots" content="noindex,follow">{% endif %}
    <meta property="og:type" content="website">
    <meta property="og:title" content="{{ page_title }}">
    <meta property="og:description" content="{{ og_description }}">
    <meta property="og:image" content="{{ og_image if og_image else base_url + '/ogp.png' }}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{{ page_title }}">
    <meta name="twitter:description" content="{{ og_description }}">
    <meta name="twitter:image" content="{{ og_image if og_image else base_url + '/ogp.png' }}">
    
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text x=%2250%%22 y=%2250%%22 style=%22dominant-baseline:central;text-anchor:middle;font-size:90px;%22>🎮</text></svg>">
    
    {% if canonical_url %}
    <link rel="canonical" href="{{ canonical_url }}">
    {% endif %}
    
    {% if game_schema %}
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "VideoGame",
      "name": {{ (game_schema.title or '') | tojson }},
      "description": {{ (game_schema.description or '') | tojson }},
      "image": {{ (game_schema.image_url or '') | tojson }},
      "genre": {{ (game_schema.genre or '') | tojson }}
    }
    </script>
    {% endif %}

    <script async src="https://www.googletagmanager.com/gtag/js?id=G-XRFBSR9HSR"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-XRFBSR9HSR');
    </script>
    
    {% if not noindex %}
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6608111802250449" crossorigin="anonymous"></script>
    {% endif %}
    <link href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.css" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>

    <style>{{ css }}</style>
</head>
<body>
    <header class="header-container">
        <h1><a href="/">🎮 Oshi-Ge</a></h1>
        <div style="display:flex; gap: 1rem; flex-wrap: wrap; justify-content: center;">
            <a href="/guide" class="btn btn-outline btn-small" style="color:var(--text-main);">📖 ガイド</a>
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
    </div>
    {% endif %}
    <main>{{ content }}</main>

    <!-- ガチャ演出用モーダル -->
    <div id="gacha-modal" class="promo-modal" style="display:none; z-index: 10000;" onclick="if(event.target===this) closeGachaModal();">
        <div class="promo-modal-box" style="width: min(500px, 100%); background: radial-gradient(circle, #1e293b 0%, #0f172a 100%); border: 2px solid var(--accent); text-align: center; padding: 2.5rem 1.5rem;">
            <h3 style="color: var(--accent); font-size: 1.5rem; margin-bottom: 1.5rem;">🎰 神ゲー発掘ガチャ</h3>
            <div style="background: #0b1120; border: 2px solid #334155; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; min-height: 100px; display: flex; align-items: center; justify-content: center;">
                <div id="gacha-title-display" style="font-size: 1.4rem; font-weight: bold; color: #fff;">抽選中...</div>
            </div>
            <div>
                <button type="button" id="gacha-action-btn" class="btn btn-primary" style="display:none; font-size: 1.1rem; padding: 0.8rem 2rem; background: var(--accent);">✨ このゲームを見に行く</button>
                <button type="button" class="btn btn-outline" onclick="closeGachaModal()" style="margin-left: 0.5rem; color: #94a3b8; border-color: #475569;">✕ 閉じる</button>
            </div>
        </div>
    </div>

    <div id="crop_modal" class="promo-modal" style="display:none; z-index: 10000;">
        <div class="promo-modal-box" style="width: min(600px, 100%); background: var(--bg-color);">
            <div class="promo-modal-head">
                <h3 style="margin: 0; color: var(--accent);">✂️ 画像の切り抜き</h3>
                <button type="button" class="btn btn-outline btn-small" onclick="closeCropModal()">✕ キャンセル</button>
            </div>
            <p style="color: var(--text-sub); font-size: 0.9rem; margin-top: 0;">枠を動かして、見せたい範囲を指定してください。</p>
            <div style="max-height: 50vh; overflow: hidden; margin-bottom: 1.5rem; background: #000; border-radius: 8px;">
                <img id="cropper_img" src="" style="max-width: 100%; display: block;">
            </div>
            <button type="button" class="btn btn-primary" style="width: 100%; padding: 1rem; font-size: 1.1rem;" onclick="applyCrop()">✅ この範囲で切り抜く</button>
        </div>
    </div>

    <!-- 通報用モーダル -->
    <div id="report-modal" class="promo-modal" style="display:none; z-index: 10000;" onclick="if(event.target===this) closeReportModal();">
        <div class="promo-modal-box" style="width: min(500px, 100%); background: var(--card-bg);">
            <div class="promo-modal-head">
                <h3 style="margin: 0; color: var(--danger);">⚠ この投稿を通報する</h3>
                <button type="button" class="btn btn-outline btn-small" onclick="closeReportModal()">✕ 閉じる</button>
            </div>
            <p style="color: var(--text-sub); font-size: 0.9rem; margin-top: 0;">悪質な投稿（荒らし、スパム、悪質なネタバレ等）の理由を選んでください。</p>
            <form id="reportForm" onsubmit="submitReport(event)">
                <input type="hidden" id="report_post_id" name="post_id">
                <div class="spoiler-radio-group" style="margin-bottom: 1.5rem;">
                    <label class="radio-label"><div class="radio-header"><input type="radio" name="report_reason" value="ネタバレ" required> <span style="margin-left:0.5rem;">重大なネタバレが含まれる</span></div></label>
                    <label class="radio-label"><div class="radio-header"><input type="radio" name="report_reason" value="誹謗中傷" required> <span style="margin-left:0.5rem;">誹謗中傷・攻撃的な内容</span></div></label>
                    <label class="radio-label"><div class="radio-header"><input type="radio" name="report_reason" value="スパム" required> <span style="margin-left:0.5rem;">スパム・宣伝・荒らし</span></div></label>
                    <label class="radio-label" style="border:none;"><div class="radio-header"><input type="radio" name="report_reason" value="その他" required> <span style="margin-left:0.5rem;">その他不適切な内容</span></div></label>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%; background:var(--danger); border:none; padding:1rem; font-size:1.1rem; box-shadow:none;">通報を送信する</button>
            </form>
        </div>
    </div>

    <!-- 布教カード用モーダル -->
    <div id="promo-card-modal" class="promo-modal" style="display:none; z-index: 10000;" onclick="if(event.target===this) closePromoCard();">
        <div class="promo-modal-box" style="width: min(1080px, 100%); background: #0f172a; padding: 0; overflow: hidden; border: 1px solid var(--border);">
            <div class="promo-modal-head" style="padding: 1rem; margin: 0; background: #1e293b; border-bottom: 1px solid var(--border);">
                <h3 style="margin: 0; color: #f8fafc;">🎴 布教カード</h3>
                <button type="button" class="btn btn-outline btn-small" onclick="closePromoCard()" style="color: #fff; border-color: #475569;">✕ 閉じる</button>
            </div>
            <div style="padding: 1rem; max-height: 80vh; overflow-y: auto;">
                <p id="promo-instruction" style="color: var(--text-sub); font-size: 0.9rem; margin-top: 0; text-align:center;"></p>
                <div class="promo-canvas-wrap" style="background: transparent; border: none; padding: 0; display:flex; justify-content:center;">
                    <canvas id="promoCanvas" style="display:none;"></canvas>
                    <img id="promoResultImg" style="max-width: 100%; max-height: 60vh; object-fit: contain; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); display: none;">
                </div>
                <div class="promo-modal-actions" style="justify-content: center; margin-top: 1rem; gap: 1rem;">
                    <button type="button" id="promo-dl-btn" class="btn btn-primary" onclick="downloadPromoCard()" style="font-size: 1.1rem; padding: 0.8rem 1.5rem;">📥 画像を保存する</button>
                    <button type="button" class="btn btn-x" onclick="sharePromoCardToX()" style="font-size: 1.1rem; padding: 0.8rem 1.5rem;">🎴 保存した画像と一緒にXでシェア</button>
                </div>
            </div>
        </div>
    </div>
    
    <footer class="footer">
        <div class="footer-genres" style="margin-bottom: 1rem;">
            {% for slug, name in GENRE_SLUGS.items() %}<a href="/genres/{{ slug }}">{{ name }}</a>{% endfor %}
        </div>
        <div>
            <a href="/">トップページ</a> | 
            <a href="/guide">ガイド</a> | 
            <a href="/about">運営者情報</a> | 
            <a href="/terms">利用規約</a> | 
            <a href="/privacy">プライバシーポリシー・免責事項</a> | 
            <a href="/contact">お問い合わせ</a>
        </div>
        <div style="margin-top: 1rem;">&copy; 2026 Oshi-Ge</div>
    </footer>

    <script>{{ js }}</script>
</body>
</html>
"""

INDEX_HTML = """
{% if genre_intro %}
<div class="card" style="border-color: var(--accent);">
    <h2 style="color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem;">{{ genre }}のおすすめゲーム布教</h2>
    <p style="margin: 0; color: #cbd5e1; line-height: 1.9;">{{ genre_intro }}</p>
</div>
{% endif %}

{% if show_intro %}
<!-- お題バナー -->
<div style="background: linear-gradient(135deg, #f59e0b, #d97706); border-radius: 12px; padding: 1.5rem; margin-bottom: 2rem; text-align: center; box-shadow: 0 10px 25px rgba(245, 158, 11, 0.3); border: 2px solid #fbbf24; cursor: pointer; transition: transform 0.2s;" onclick="location.href='/games/new'" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='translateY(0)'">
    <div style="color: #fff; font-weight: bold; font-size: 0.95rem; margin-bottom: 0.5rem; letter-spacing: 0.1em;">🔥 今週のピックアップお題</div>
    <h2 style="color: #fff; margin: 0 0 1rem 0; font-size: 1.8rem; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">「100時間以上溶かした時間泥棒ゲーム」</h2>
    <div class="btn" style="background: #fff; color: #d97706; padding: 0.8rem 2.5rem; border-radius: 30px; font-weight: 900; box-shadow: 0 4px 10px rgba(0,0,0,0.2);">お題に沿って布教を書く ✍️</div>
</div>

<div class="card">
    <h2 style="color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem;">Oshi-Geとは</h2>
    <div class="prose">
        <p>Oshi-Geは、好きなゲームの魅力を「ネタバレなし」で伝え合うゲーム布教サイトです。投稿には3段階のネタバレレベルがあり、ストーリーに関わる内容は初期状態で隠れるため、未プレイの人も安心して読めます。</p>
        <p>気になるゲームのことを知りたいときは、ジャンル別のページや「目的からゲームを探す」から探せます。「誰におすすめか」「プレイ時間」「推しポイント」が書かれているので、自分に合うかどうかを判断する手がかりになります。遊んだことのあるゲームがあれば、ぜひあなたの言葉で布教してください。</p>
        <p>書き方や選び方のコツは、<a href="/guide">ガイド記事</a>にまとめています。サイトの方針は<a href="/about">運営者情報</a>をご覧ください。</p>
    </div>
</div>
{% endif %}

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
        <a class="quick-filter" href="#" onclick="startGacha(event)" style="background: linear-gradient(45deg, #ec4899, #8b5cf6); color: white; border: none; font-size: 1.05rem; box-shadow: 0 4px 15px rgba(236, 72, 153, 0.4);">🎰 神ゲー発掘ガチャ</a>
    </div>
    <div style="margin-top: 1.2rem; padding-top: 1rem; border-top: 1px dashed var(--border);">
        <div style="color: var(--text-sub); font-size: 0.85rem; margin-bottom: 0.6rem; font-weight: bold;">ジャンルから探す</div>
        <div class="genre-chip-row">
            {% for slug, name in GENRE_SLUGS.items() %}<a class="genre-chip" href="/genres/{{ slug }}">{{ name }}</a>{% endfor %}
        </div>
    </div>
</div>

<div class="layout-wrapper">
    <div class="main-column">
        <div style="display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">
            <h3 style="margin:0;">布教されているゲーム</h3>
            <div style="display: flex; gap: 0.5rem;">
                <a href="?sort=new{% if q %}&q={{ q | urlencode }}{% endif %}{% if genre %}&genre={{ genre | urlencode }}{% endif %}{% if platform %}&platform={{ platform | urlencode }}{% endif %}" class="btn btn-outline btn-small" style="{% if sort == 'new' or not sort %}background:rgba(245,158,11,0.1); border-color:var(--accent); color:var(--accent);{% endif %}">🕒 最新順</a>
                <a href="?sort=posts{% if q %}&q={{ q | urlencode }}{% endif %}{% if genre %}&genre={{ genre | urlencode }}{% endif %}{% if platform %}&platform={{ platform | urlencode }}{% endif %}" class="btn btn-outline btn-small" style="{% if sort == 'posts' %}background:rgba(245,158,11,0.1); border-color:var(--accent); color:var(--accent);{% endif %}">🔥 投稿数順</a>
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
        <!-- 布教リクエスト機能 -->
        <div class="card" style="border-color: #3b82f6; padding: 1.2rem; background: rgba(59, 130, 246, 0.05);">
            <h3 style="margin-top: 0; color: #3b82f6; border-bottom: 1px solid rgba(59, 130, 246, 0.3); padding-bottom: 0.5rem;">🙋 誰か布教して！</h3>
            <p style="font-size: 0.85rem; color: var(--text-sub); margin-bottom: 1rem;">気になっているゲームのプレゼンを誰かにリクエストしよう。</p>
            <form action="/requests" method="post" style="margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.5rem;">
                <input type="text" name="title" placeholder="ゲームタイトルを入力" required style="padding: 0.75rem; border-radius: 8px; border: 1px solid var(--border); background: #0f172a; color: white;">
                <input type="text" name="username" placeholder="あなたの名前 (匿名可)" value="名無しのゲーマー" required style="padding: 0.5rem; border-radius: 8px; border: 1px solid var(--border); background: #0f172a; color: white; font-size: 0.9rem;">
                <button type="submit" class="btn btn-primary btn-small" style="background: #3b82f6; border: none; font-size: 1rem; padding: 0.6rem;">リクエストを送信 ✈️</button>
            </form>
            
            <div style="display: flex; flex-direction: column; gap: 0.8rem;">
                <div style="font-size: 0.85rem; font-weight: bold; color: var(--text-sub);">現在募集中のリクエスト</div>
                {% for req in requests %}
                <div style="background: #0f172a; padding: 0.8rem; border-radius: 8px; border: 1px solid var(--border);">
                    <div style="font-weight: bold; color: var(--text-main); font-size: 0.95rem;">{{ req.title }}</div>
                    <div style="font-size: 0.75rem; color: var(--text-sub); margin-top: 0.3rem;">👤 リクエスター: {{ req.username }}</div>
                    <a href="/games/new?title={{ req.title | urlencode }}" style="display: inline-block; margin-top: 0.6rem; font-size: 0.85rem; color: #f59e0b; text-decoration: none; font-weight: bold; padding: 0.3rem 0.6rem; background: rgba(245, 158, 11, 0.1); border-radius: 4px; border: 1px solid rgba(245, 158, 11, 0.3);">👉 このゲームを布教する</a>
                </div>
                {% else %}
                <div style="color: var(--text-sub); font-size: 0.85rem; text-align: center;">現在リクエストはありません。</div>
                {% endfor %}
            </div>
        </div>

        <div class="card" style="border-color: var(--accent); padding: 1.2rem;">
            <h3 style="margin-top: 0; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">👑 今週の注目ゲーム</h3>
            <div style="display: flex; flex-direction: column; gap: 1rem; margin-top: 1rem;">
                {% for item in weekly_ranking %}
                <div style="display: flex; gap: 1rem; align-items: center; cursor: pointer;" onclick="location.href='/games/{{ item.id }}'">
                    <div style="width: 60px; height: 60px; border-radius: 8px; overflow: hidden; background: #334155; flex-shrink: 0;">
                        {% if item.image_url %}<img src="{{ item.image_url }}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'">
                        {% else %}<div style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 0.6rem; color: #94a3b8;">NO IMG</div>{% endif %}
                    </div>
                    <div>
                        <div style="font-weight: bold; color: var(--text-main); font-size: 0.95rem; margin-bottom: 0.2rem;">{{ item.title }}</div>
                        <div style="font-size: 0.8rem; color: var(--accent);">🔥 今週 {{ item.weekly_likes }} リアクション</div>
                    </div>
                </div>
                {% else %}<div style="color: var(--text-sub); font-size: 0.9rem;">今週の布教はまだありません。</div>{% endfor %}
            </div>
        </div>

        <div class="card" style="padding: 1.2rem;">
            <h3 style="margin-top: 0; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem;">📖 ガイド</h3>
            {% for a in articles %}
            <a href="/guide/{{ a.slug }}" style="display: block; color: var(--text-main); text-decoration: none; font-size: 0.9rem; font-weight: bold; padding: 0.5rem 0; border-bottom: 1px dashed var(--border);">{{ a.title }}</a>
            {% endfor %}
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
    
    {% if show_affiliate %}
    <div style="display: flex; gap: 0.5rem; margin-bottom: 0.5rem; flex-wrap: wrap;">
        <a href="https://www.amazon.co.jp/s?k={{ game.title | urlencode }}&i=videogames&tag=oshige06-22" target="_blank" rel="noopener sponsored" class="btn btn-outline btn-small" style="color: #f59e0b; border-color: rgba(245, 158, 11, 0.5);">🛒 Amazonで探す</a>
        <a href="https://search.rakuten.co.jp/search/mall/{{ game.title | urlencode }}/?tg=101240" target="_blank" rel="noopener sponsored" class="btn btn-outline btn-small" style="color: #ef4444; border-color: rgba(239, 68, 68, 0.5);">🛍 楽天市場で探す</a>
        <a href="https://store.steampowered.com/search/?term={{ game.title | urlencode }}" target="_blank" rel="noopener" class="btn btn-outline btn-small" style="color: #cbd5e1; border-color: rgba(203, 213, 225, 0.5);">🎮 Steamで探す</a>
    </div>
    <div style="font-size: 0.75rem; color: var(--text-sub); margin-bottom: 1.5rem;">当サイトはAmazonアソシエイト・楽天アフィリエイトのリンクを含みます。Amazonのアソシエイトとして、適格販売により収入を得ています。</div>
    {% endif %}

    <div style="display: flex; gap: 0.5rem; border-top: 1px solid var(--border); padding-top: 1.5rem;">
        <button type="button" class="btn btn-x" onclick='shareGameToX({{ (game.title or "") | tojson }}, {{ (game.developer_x_id or "") | tojson }})'>X でゲームを共有</button>
        <button type="button" class="btn btn-line" onclick='shareGameToLine({{ (game.title or "") | tojson }})'>LINE でゲームを共有</button>
    </div>
</div>

<details class="card" style="border-color: var(--accent); box-shadow: 0 0 15px rgba(245, 158, 11, 0.1);">
    <summary style="cursor: pointer; font-weight: bold; color: var(--accent); font-size: 1.1rem; user-select: none; outline: none;">
        🔥 このゲームを布教する（クリックして投稿フォームを開く）
    </summary>
    <form action="/games/{{ game.id }}/posts" method="post" style="margin-top: 1.5rem; border-top: 1px solid var(--border); padding-top: 1.5rem;">
        
        <!-- 布教のヒント -->
        <div style="background: rgba(245, 158, 11, 0.08); border: 1px dashed rgba(245, 158, 11, 0.4); border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; font-size: 0.9rem; color: #cbd5e1;">
            <div style="font-weight: bold; color: var(--accent); margin-bottom: 0.4rem;">💡 布教のヒント（こんなことを書くと魅力が伝わります！）</div>
            <ul style="margin: 0; padding-left: 1.2rem; color: var(--text-sub);">
                <li>どんなところが面白い？（バトル、世界観、キャラなど）</li>
                <li>どんな人におすすめ？</li>
                <li>遊んだあと、どんな気持ちになった？</li>
            </ul>
            <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 0.4rem;">※全部に答える必要はありません。ネタバレにはご注意ください！ 詳しくは<a href="/guide/how-to-write-oshi-post" style="color:#3b82f6;">布教文の書き方ガイド</a>をどうぞ。</div>
        </div>

        <div class="form-group"><label>布教ネーム（匿名可）:</label><input type="text" name="username" value="名無しの布教者" required></div>
        <div style="background: #0b1120; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;">
            <div class="form-group"><label style="color: var(--accent);">一言で布教すると？（必須）:</label><input type="text" name="catchphrase" required placeholder="例：最後まで遊んだときに、やってよかったと思える作品" style="border-color: rgba(245, 158, 11, 0.5);"></div>
            <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>誰におすすめ？ <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="target_audience" placeholder="例：ストーリー重視の人"></div>
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>プレイ時間 <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="play_time" placeholder="例：10～15時間"></div>
            </div>
            
            <div class="form-group checkbox-group" style="margin-bottom: 0;"><label>💡 このゲームの推しポイント（複数選択可）:</label>
                <div style="display: flex; flex-wrap: wrap; gap: 0.8rem; padding: 0.5rem 0;">
                    {% set points = ["📖 ストーリーが最高", "👤 キャラが魅力的", "🎵 BGM・音楽が神", "⚔️ バトルが爽快", "🌍 世界観に浸れる", "⏳ やり込み要素あり", "🎬 演出がエモい", "👑 運営が神"] %}
                    {% for pt in points %}
                    <label style="cursor: pointer; display: flex; align-items: center; background: #1e293b; padding: 0.4rem 0.8rem; border-radius: 8px; border: 1px solid var(--border);">
                        <input type="checkbox" name="oshi_points" value="{{ pt }}">
                        <span style="margin-left:0.5rem; font-size:0.9rem;">{{ pt }}</span>
                    </label>
                    {% endfor %}
                </div>
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
        <div style="font-size: 0.8rem; color: var(--text-sub); margin-bottom: 1rem;">投稿することで<a href="/terms" target="_blank" style="color:#3b82f6;">利用規約</a>に同意したものとみなします。</div>
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
                {% if post.id in my_posts or (user_id and post.user_id and post.user_id|string == user_id) %}<a href="/games/{{ game.id }}/posts/{{ post.id }}/edit" class="btn btn-outline btn-small" style="padding: 0.2rem 0.5rem; font-size: 0.8rem;">⚙ 編集</a>{% endif %}
            </div>
        </div>
        {% if post.catchphrase %}
        <div style="margin-bottom: 1rem;"><h4 class="catchphrase-text">「{{ post.catchphrase }}」</h4>
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; font-size: 0.85rem;">
                {% if post.target_audience %}<span class="meta-tag">🎯 {{ post.target_audience }}におすすめ</span>{% endif %}
                {% if post.play_time %}<span class="meta-tag">⏱ {{ post.play_time }}</span>{% endif %}
            </div>
        </div>
        {% endif %}
        
        {% if post.oshi_points %}
        <div style="margin-bottom: 1.25rem;">
            {% for pt in post.oshi_points.split(',') %}{% if pt %}<span class="tag oshi-point">{{ pt }}</span>{% endif %}{% endfor %}
        </div>
        {% endif %}

        {% if post.spoiler_level == 0 %}<div><span class="spoiler-badge safe">🔐 ネタバレなしの詳細</span><div class="post-content"><p>{{ post.content }}</p></div></div>
        {% elif post.spoiler_level == 1 %}<div><button type="button" class="spoiler-toggle-btn warning" onclick="toggleSpoiler(this)">🔒 軽微なネタバレの詳細【クリックして表示】</button><div class="spoiler-hidden-text" style="display: none;"><div class="post-content"><p>{{ post.content }}</p></div></div></div>
        {% else %}<div><button type="button" class="spoiler-toggle-btn danger" onclick="toggleSpoiler(this)">⚠ ネタバレありの詳細【クリックして表示】</button><div class="spoiler-hidden-text" style="display: none;"><div class="post-content"><p>{{ post.content }}</p></div></div></div>{% endif %}
        
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; border-top: 1px dashed var(--border); padding-top: 0.75rem; flex-wrap: wrap; gap: 1rem;">
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; flex: 1; min-width: 250px;">
                <button type="button" class="btn btn-outline btn-small" data-id="{{ game.id }}" data-title="{{ game.title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" data-dev="{{ game.developer_x_id }}" onclick="sharePost(this, 'x')">X で共有</button>
                <button type="button" class="btn btn-outline btn-small" style="color:#06C755; border-color:rgba(6,199,85,0.5);" data-id="{{ game.id }}" data-title="{{ game.title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" data-dev="{{ game.developer_x_id }}" onclick="sharePost(this, 'line')">LINE で共有</button>
                
                <button type="button" class="btn btn-outline btn-small" 
                    data-id="{{ game.id }}"
                    data-postid="{{ post.id }}"
                    data-title="{{ game.title }}" 
                    data-catch="{{ post.catchphrase }}" 
                    data-target="{{ post.target_audience }}" 
                    data-play="{{ post.play_time }}" 
                    data-user="{{ post.username or '名無しの布教者' }}" 
                    data-genre="{{ game.genre }}" 
                    data-platform="{{ game.platform }}" 
                    data-spoiler="{{ post.spoiler_level }}" 
                    data-content="{{ (post.content or '') | replace('\n', ' ') | replace('\r', '') }}" 
                    data-img="{{ game.image_url }}" 
                    data-oshi="{{ post.oshi_points }}" 
                    data-dev="{{ game.developer_x_id }}" 
                    onclick="openPromoCard(this)">🎴 布教カード</button>

                <button type="button" class="btn btn-outline btn-small" style="color:var(--text-sub); border:none; padding:0.4rem;" onclick="openReportModal({{ post.id }})">⚠ 通報</button>
            </div>
            
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; justify-content: flex-end; flex-shrink: 0;">
                <button type="button" class="btn-react btn-wanna-play" data-post-id="{{ post.id }}" data-type="wanna_play" onclick="reactPost({{ game.id }}, {{ post.id }}, 'wanna_play', this)">🎮 やってみる！ <span>{{ post.wanna_play or 0 }}</span></button>
                <button type="button" class="btn-react btn-agree" data-post-id="{{ post.id }}" data-type="agree" onclick="reactPost({{ game.id }}, {{ post.id }}, 'agree', this)">🤝 わかる <span>{{ post.agree or 0 }}</span></button>
                <button type="button" class="btn-react btn-like" data-post-id="{{ post.id }}" data-type="likes" onclick="reactPost({{ game.id }}, {{ post.id }}, 'likes', this)">👍 いいね <span>{{ post.likes or 0 }}</span></button>
            </div>
        </div>
    </div>
    {% else %}<div class="card" style="text-align: center; color: var(--text-sub); padding: 3rem 0; background: transparent; border: 1px dashed var(--border);"><p style="margin: 0;">まだ布教コメントがありません。<br>最初の布教者になりませんか？</p></div>{% endfor %}
</div>
"""

MYPAGE_HTML = """
<div class="card">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">👤 マイページ</h2>
    
    {% if not user_id %}
    <div style="background: rgba(59, 130, 246, 0.1); border: 1px solid #3b82f6; padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem;">
        <h3 style="color: #3b82f6; margin-top: 0;">🔄 データをアカウントに紐付ける（任意）</h3>
        <p style="font-size: 0.9rem; color: var(--text-sub); margin-bottom: 1rem;">
            ログインすると、現在の端末の「布教履歴（編集権限）」と「お気に入り」がアカウントに保存され、<br>
            ブラウザを変えたりスマホを買い替えてもデータを引き継げるようになります。<br>
            ※投稿時の名前は今まで通り「布教ネーム」が使われ、SNSアカウントが公開されることはありません。
        </p>
        <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
            <form action="/auth/login/google" method="post"><button type="submit" class="btn btn-outline" style="background: #fff; color: #444;">Googleでログイン</button></form>
            <form action="/auth/login/x" method="post"><button type="submit" class="btn btn-outline" style="background: #000; color: #fff; border-color: #333;">X (Twitter) でログイン</button></form>
        </div>
    </div>
    {% else %}
    <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(16, 185, 129, 0.1); border: 1px solid var(--safe); padding: 1rem; border-radius: 8px; margin-bottom: 2rem;">
        <div><span style="color: var(--safe); font-weight: bold;">✅ アカウント連携済み</span><br><span style="font-size: 0.85rem; color: var(--text-sub);">他の端末でもログインすれば履歴が同期されます。</span></div>
        <form action="/auth/logout" method="post"><button type="submit" class="btn btn-outline btn-small">ログアウト</button></form>
    </div>
    {% endif %}

    <div id="like-notification" style="display: none; background: rgba(16, 185, 129, 0.1); border: 1px solid var(--safe); color: var(--safe); padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; justify-content: space-between; align-items: center;">
        <div style="font-weight: bold;">🎉 あなたの布教に新しいリアクションがつきました！</div>
        <button onclick="document.getElementById('like-notification').style.display='none'" style="background: transparent; border: none; color: var(--safe); font-size: 1.2rem; cursor: pointer;">✕</button>
    </div>

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
            
            {% if post.oshi_points %}
            <div style="margin-bottom: 0.75rem;">
                {% for pt in post.oshi_points.split(',') %}{% if pt %}<span class="tag oshi-point">{{ pt }}</span>{% endif %}{% endfor %}
            </div>
            {% endif %}
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1.5rem; border-top: 1px dashed var(--border); padding-top: 0.75rem; flex-wrap: wrap; gap: 1rem;">
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; flex: 1; min-width: 250px;">
                    <button type="button" class="btn btn-outline btn-small" data-id="{{ post.game_id }}" data-title="{{ post.game_title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" data-dev="{{ post.game_developer_x_id }}" onclick="sharePost(this, 'x')">X で共有</button>
                    <button type="button" class="btn btn-outline btn-small" style="color:#06C755; border-color:rgba(6,199,85,0.5);" data-id="{{ post.game_id }}" data-title="{{ post.game_title }}" data-catch="{{ post.catchphrase }}" data-content="{{ post.content }}" data-spoiler="{{ post.spoiler_level }}" data-dev="{{ post.game_developer_x_id }}" onclick="sharePost(this, 'line')">LINE で共有</button>
                    
                    <button type="button" class="btn btn-outline btn-small" 
                        data-id="{{ post.game_id }}"
                        data-postid="{{ post.id }}"
                        data-title="{{ post.game_title }}" 
                        data-catch="{{ post.catchphrase }}" 
                        data-target="{{ post.target_audience }}" 
                        data-play="{{ post.play_time }}" 
                        data-user="{{ post.username or '名無しの布教者' }}" 
                        data-genre="{{ post.game_genre }}" 
                        data-platform="{{ post.game_platform }}" 
                        data-spoiler="{{ post.spoiler_level }}" 
                        data-content="{{ (post.content or '') | replace('\n', ' ') | replace('\r', '') }}" 
                        data-img="{{ post.game_image_url }}" 
                        data-oshi="{{ post.oshi_points }}" 
                        data-dev="{{ post.game_developer_x_id }}" 
                        onclick="openPromoCard(this)">🎴 布教カード</button>
                </div>
                <div style="display: flex; gap: 0.8rem; color: var(--text-sub); font-size: 0.9rem; font-weight: bold; flex-shrink: 0;">
                    <span style="color: var(--safe);">🎮 {{ post.wanna_play or 0 }}</span>
                    <span style="color: #3b82f6;">🤝 {{ post.agree or 0 }}</span>
                    <span style="color: var(--accent);">👍 {{ post.likes or 0 }}</span>
                </div>
            </div>
        </div>
        {% else %}
        <div style="color: var(--text-sub); padding: 1rem;">布教履歴はまだありません。</div>
        {% endfor %}
    </div>
</div>

<script>
document.addEventListener("DOMContentLoaded", () => {
    const currentLikes = {{ total_likes | int }};
    const savedLikes = localStorage.getItem("oshi_ge_last_likes");
    
    if (savedLikes !== null) {
        const lastSeenLikes = parseInt(savedLikes, 10);
        if (currentLikes > lastSeenLikes) {
            const notif = document.getElementById("like-notification");
            if (notif) notif.style.display = "flex";
        }
    }
    localStorage.setItem("oshi_ge_last_likes", currentLikes);
});
</script>
"""

NEW_GAME_HTML = """
<div class="card">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">ゲームを追加して布教する</h2>
    {% if error_msg %}<div style="background: rgba(239, 68, 68, 0.1); color: var(--danger); padding: 1rem; border-left: 4px solid var(--danger); margin-bottom: 1.5rem;">⚠️ {{ error_msg }}</div>{% endif %}
    <form action="/games/new" method="post" enctype="multipart/form-data">
        
        <h3 style="color: var(--accent);">🎮 ゲームの基本情報</h3>
        <div class="form-group"><label>タイトル（必須）:</label><input type="text" name="title" value="{{ title }}" required></div>
        <div class="form-group"><label>ジャンル:</label>
            <select name="genre">
                {% set genres = ["RPG", "アクション", "アドベンチャー", "シミュレーション", "FPS / TPS", "パズル", "ノベル", "ホラー", "インディー", "その他 / 不明"] %}
                {% for g in genres %}<option value="{{ g }}" {% if genre == g or (not genre and g == "その他 / 不明") %}selected{% endif %}>{{ g }}</option>{% endfor %}
            </select>
        </div>
        <div class="form-group checkbox-group"><label>プラットフォーム（複数選択可）:</label>
            {% set cur_platforms = (platform or '').split(',') %}
            <div style="display: flex; flex-wrap: wrap; gap: 1rem; padding: 0.5rem 0;">
                {% for p in ["PC", "Switch", "Switch2", "PS5", "Xbox", "スマホ", "その他"] %}
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="{{ p }}" onchange="updatePlatform(this.form)" {% if p in cur_platforms %}checked{% endif %}> {{ p }}</label>
                {% endfor %}
            </div>
            <input type="hidden" name="platform" class="platform-hidden" value="{{ platform }}">
        </div>
        <div class="form-group"><label>開発者・公式のX(Twitter)ID（任意）:</label><input type="text" name="developer_x_id" placeholder="例：@IndieDev （@は省略可）" value="{{ developer_x_id }}"></div>
        <div class="form-group"><label>ゲーム画像（任意・自動で最適なサイズに圧縮されます）:</label>
            <input type="file" id="image_upload" accept="image/*" style="background:transparent; border:none; padding:0;">
            <input type="hidden" name="image_base64" id="image_base64">
            <div style="font-size: 0.8rem; color: var(--text-sub); margin-top: 0.4rem;">※ご自身で撮影したスクリーンショットなど、掲載する権利のある画像のみアップロードしてください。公式の宣伝素材などを使う場合は、権利者のガイドラインの範囲内でお願いします。詳しくは<a href="/terms" target="_blank" style="color:#3b82f6;">利用規約</a>をご確認ください。</div>
            <div id="image_preview" style="margin-top: 1rem; display: none;"><img id="preview_img" src="" style="max-width: 100%; max-height: 200px; border-radius: 8px; border: 1px solid var(--border);"></div>
        </div>
        <div class="form-group"><label>ゲームの簡単な説明（ご自身の言葉で書いてください）:</label><textarea name="description" rows="4">{{ description }}</textarea></div>

        <h3 style="margin-top: 2rem; color: var(--accent); border-top: 1px dashed var(--border); padding-top: 1.5rem;">🔥 最初の布教コメント</h3>
        
        <!-- 布教のヒント -->
        <div style="background: rgba(245, 158, 11, 0.08); border: 1px dashed rgba(245, 158, 11, 0.4); border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; font-size: 0.9rem; color: #cbd5e1;">
            <div style="font-weight: bold; color: var(--accent); margin-bottom: 0.4rem;">💡 布教のヒント（こんなことを書くと魅力が伝わります！）</div>
            <ul style="margin: 0; padding-left: 1.2rem; color: var(--text-sub);">
                <li>どんなところが面白い？（バトル、世界観、キャラなど）</li>
                <li>どんな人におすすめ？</li>
                <li>遊んだあと、どんな気持ちになった？</li>
            </ul>
            <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 0.4rem;">※全部に答える必要はありません。ネタバレにはご注意ください！ 詳しくは<a href="/guide/how-to-write-oshi-post" target="_blank" style="color:#3b82f6;">布教文の書き方ガイド</a>をどうぞ。</div>
        </div>

        <div class="form-group"><label>布教ネーム（匿名可）:</label><input type="text" name="username" value="名無しの布教者" required></div>
        <div style="background: #0b1120; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;">
            <div class="form-group"><label style="color: var(--accent);">一言で布教すると？（必須）:</label><input type="text" name="catchphrase" required placeholder="例：最後まで遊んだときに、やってよかったと思える作品" style="border-color: rgba(245, 158, 11, 0.5);"></div>
            <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>誰におすすめ？ <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="target_audience" placeholder="例：ストーリー重視の人"></div>
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>プレイ時間 <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="play_time" placeholder="例：10～15時間"></div>
            </div>
            
            <div class="form-group checkbox-group" style="margin-bottom: 0;"><label>💡 このゲームの推しポイント（複数選択可）:</label>
                <div style="display: flex; flex-wrap: wrap; gap: 0.8rem; padding: 0.5rem 0;">
                    {% set points = ["📖 ストーリーが最高", "👤 キャラが魅力的", "🎵 BGM・音楽が神", "⚔️ バトルが爽快", "🌍 世界観に浸れる", "⏳ やり込み要素あり", "🎬 演出がエモい", "👑 運営が神"] %}
                    {% for pt in points %}
                    <label style="cursor: pointer; display: flex; align-items: center; background: #1e293b; padding: 0.4rem 0.8rem; border-radius: 8px; border: 1px solid var(--border);">
                        <input type="checkbox" name="oshi_points" value="{{ pt }}">
                        <span style="margin-left:0.5rem; font-size:0.9rem;">{{ pt }}</span>
                    </label>
                    {% endfor %}
                </div>
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
        <div style="font-size: 0.8rem; color: var(--text-sub); margin-bottom: 1rem;">登録することで<a href="/terms" target="_blank" style="color:#3b82f6;">利用規約</a>に同意したものとみなします。</div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%; font-size:1.1rem; padding: 1rem; margin-top: 1rem;">ゲームを登録して布教する</button>
    </form>
</div>
"""

EDIT_GAME_HTML = """
<div class="card">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">ゲーム情報を編集する</h2>
    <form action="/games/{{ game.id }}/edit" method="post" enctype="multipart/form-data">
        <div class="form-group"><label>タイトル（必須）:</label><input type="text" name="title" value="{{ game.title }}" required></div>
        <div class="form-group"><label>ジャンル:</label>
            <select name="genre">
                {% set genres = ["RPG", "アクション", "アドベンチャー", "シミュレーション", "FPS / TPS", "パズル", "ノベル", "ホラー", "インディー", "その他 / 不明"] %}
                {% for g in genres %}<option value="{{ g }}" {% if game.genre == g %}selected{% endif %}>{{ g }}</option>{% endfor %}
            </select>
        </div>
        <div class="form-group checkbox-group"><label>プラットフォーム（複数選択可）:</label>
            {% set cur_platforms = (game.platform or '').split(',') %}
            <div style="display: flex; flex-wrap: wrap; gap: 1rem; padding: 0.5rem 0;">
                {% for p in ["PC", "Switch", "Switch2", "PS5", "Xbox", "スマホ", "その他"] %}
                <label style="cursor: pointer; display: flex; align-items: center;"><input type="checkbox" class="platform-cb" value="{{ p }}" onchange="updatePlatform(this.form)" {% if p in cur_platforms %}checked{% endif %}> {{ p }}</label>
                {% endfor %}
            </div>
            <input type="hidden" name="platform" class="platform-hidden" value="{{ game.platform }}">
        </div>
        <div class="form-group"><label>開発者・公式のX(Twitter)ID（任意）:</label><input type="text" name="developer_x_id" placeholder="例：@IndieDev （@は省略可）" value="{{ game.developer_x_id }}"></div>
        <div class="form-group"><label>ゲーム画像（新しくアップロードして変更する場合のみ選択）:</label>
            <input type="file" id="image_upload" accept="image/*" style="background:transparent; border:none; padding:0;">
            <input type="hidden" name="image_base64" id="image_base64">
            <div style="font-size: 0.8rem; color: var(--text-sub); margin-top: 0.4rem;">※掲載する権利のある画像のみアップロードしてください。詳しくは<a href="/terms" target="_blank" style="color:#3b82f6;">利用規約</a>をご確認ください。</div>
            <div id="image_preview" style="margin-top: 1rem; display: {% if game.image_url %}block{% else %}none{% endif %};"><img id="preview_img" src="{{ game.image_url }}" style="max-width: 100%; max-height: 200px; border-radius: 8px; border: 1px solid var(--border);"></div>
        </div>
        <div class="form-group"><label>ゲームの簡単な説明:</label><textarea name="description" rows="4">{{ game.description }}</textarea></div>
        <div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
            <a href="/games/{{ game.id }}" class="btn btn-outline" style="flex: 1; text-align:center;">キャンセル</a>
            <button type="submit" class="btn btn-primary" style="flex: 2;">変更を保存する</button>
        </div>
    </form>
</div>
"""

EDIT_POST_HTML = """
<div class="card" style="border-color: var(--accent);">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem; color: var(--accent);">自分の布教を編集する</h2>
    <form action="/games/{{ game_id }}/posts/{{ post.id }}/edit" method="post">
        <div class="form-group"><label>布教ネーム（匿名可）:</label><input type="text" name="username" value="{{ post.username }}" required></div>
        <div style="background: #0b1120; padding: 1.5rem; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 1.5rem;">
            <div class="form-group"><label style="color: var(--accent);">一言で布教すると？（必須）:</label><input type="text" name="catchphrase" value="{{ post.catchphrase }}" required style="border-color: rgba(245, 158, 11, 0.5);"></div>
            <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>誰におすすめ？ <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="target_audience" value="{{ post.target_audience }}"></div>
                <div class="form-group" style="flex: 1; min-width: 200px; margin-bottom: 0;"><label>プレイ時間 <span style="color:var(--text-sub); font-weight:normal; font-size:0.85rem;">（任意）</span>:</label><input type="text" name="play_time" value="{{ post.play_time }}"></div>
            </div>
            <div class="form-group checkbox-group" style="margin-bottom: 0;"><label>💡 このゲームの推しポイント（複数選択可）:</label>
                {% set cur_points = (post.oshi_points or '').split(',') %}
                <div style="display: flex; flex-wrap: wrap; gap: 0.8rem; padding: 0.5rem 0;">
                    {% set points = ["📖 ストーリーが最高", "👤 キャラが魅力的", "🎵 BGM・音楽が神", "⚔️ バトルが爽快", "🌍 世界観に浸れる", "⏳ やり込み要素あり", "🎬 演出がエモい", "👑 運営が神"] %}
                    {% for pt in points %}
                    <label style="cursor: pointer; display: flex; align-items: center; background: #1e293b; padding: 0.4rem 0.8rem; border-radius: 8px; border: 1px solid var(--border);">
                        <input type="checkbox" name="oshi_points" value="{{ pt }}" {% if pt in cur_points %}checked{% endif %}>
                        <span style="margin-left:0.5rem; font-size:0.9rem;">{{ pt }}</span>
                    </label>
                    {% endfor %}
                </div>
            </div>
        </div>
        <div class="form-group"><label>ネタバレレベル:</label>
            <div class="spoiler-radio-group">
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="0" {% if post.spoiler_level == 0 %}checked{% endif %}> <span style="color:var(--safe)">Lv.0 ネタバレなし</span></div></label>
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="1" {% if post.spoiler_level == 1 %}checked{% endif %}> <span style="color:var(--warning)">Lv.1 軽微なネタバレ</span></div></label>
                <label class="radio-label"><div class="radio-header"><input type="radio" name="spoiler_level" value="2" {% if post.spoiler_level == 2 %}checked{% endif %}> <span style="color:var(--danger)">Lv.2 ネタバレあり</span></div></label>
            </div>
        </div>
        <div class="form-group"><label>布教コメントの詳細（必須）:</label><textarea name="content" rows="4" required>{{ post.content }}</textarea></div>
        <div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
            <a href="/games/{{ game_id }}" class="btn btn-outline" style="flex: 1; text-align: center;">キャンセル</a>
            <button type="submit" class="btn btn-primary" style="flex: 2;">変更を保存する</button>
        </div>
    </form>
</div>
"""

PRIVACY_HTML = """
<div class="card" style="max-width: 800px; margin: 0 auto;">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">プライバシーポリシー・免責事項</h2>
    
    <h3 style="color: var(--accent);">当サイトに掲載されている広告について</h3>
    <p>当サイトでは、第三者配信の広告サービス（Googleアドセンス、Amazonアソシエイト、楽天アフィリエイト）を利用しています。<br>
    このような広告配信事業者は、ユーザーの興味に応じた商品やサービスの広告を表示するため、当サイトや他サイトへのアクセスに関する情報 「Cookie」(氏名、住所、メール アドレス、電話番号は含まれません) を使用することがあります。<br>
    Googleアドセンスに関して、このプロセスの詳細やこのような情報が広告配信事業者に使用されないようにする方法については、<a href="https://policies.google.com/technologies/ads" target="_blank" style="color: #3b82f6;">こちら</a>をご覧ください。</p>
    
    <h3 style="color: var(--accent);">アクセス解析ツールについて</h3>
    <p>当サイトでは、Googleによるアクセス解析ツール「Googleアナリティクス」を利用しています。<br>
    このGoogleアナリティクスはトラフィックデータの収集のためにCookieを使用しています。このトラフィックデータは匿名で収集されており、個人を特定するものではありません。<br>
    この機能はCookieを無効にすることで収集を拒否することが出来ますので、お使いのブラウザの設定をご確認ください。</p>
    
    <h3 style="color: var(--accent);">免責事項</h3>
    <p>当サイトからリンクやバナーなどによって他のサイトに移動された場合、移動先サイトで提供される情報、サービス等について一切の責任を負いません。<br>
    当サイトのコンテンツ・情報につきまして、可能な限り正確な情報を掲載するよう努めておりますが、誤情報が入り込んだり、情報が古くなっていることもございます。<br>
    当サイトに掲載された内容によって生じた損害等の一切の責任を負いかねますのでご了承ください。</p>
    
    <h3 style="color: var(--accent);">ユーザー投稿データおよびアカウント情報の取り扱い</h3>
    <p>当サイトはユーザーが自由にゲームの布教（感想・レビュー等）を投稿できるサービスです。投稿された文章に関する責任は投稿者に帰属します。スパム、誹謗中傷、極端なネタバレなど、管理者が不適切と判断したコンテンツは予告なく削除・非表示にする場合があります。投稿ルールの詳細は<a href="/terms" style="color: #3b82f6;">利用規約</a>をご確認ください。<br>
    また、ログイン機能（Google連携やX連携等）を利用した場合、当サイトは認証に必要な最小限の識別子（UUID等）のみを保持し、ユーザーのSNSアカウント自体に勝手に投稿したり、パスワードを収集することはありません。</p>
    
    <h3 style="color: var(--accent);">アカウントの削除について</h3>
    <p>当サイトに紐付けたアカウントデータ（およびご自身の投稿履歴）の削除をご希望の場合は、<a href="/contact" style="color: #3b82f6;">お問い合わせページ</a>の窓口まで個別にご連絡いただくことで対応いたします。</p>

    <h3 style="color: var(--accent);">運営者について</h3>
    <p>運営者の情報は<a href="/about" style="color: #3b82f6;">運営者情報</a>のページに掲載しています。</p>
</div>
"""

ADMIN_HTML = """
<div class="card" style="max-width: 1000px; margin: 0 auto; border-color: var(--danger);">
    <h2 style="border-bottom: 2px solid var(--danger); padding-bottom: 0.5rem; margin-bottom: 1.5rem; color: var(--danger);">🛡 管理ダッシュボード</h2>
    
    <h3 style="color: var(--accent);">🚨 通報された投稿一覧</h3>
    <div style="overflow-x: auto;">
        <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem;">
            <thead>
                <tr style="background: #1e293b; border-bottom: 2px solid var(--border);">
                    <th style="padding: 0.75rem;">ID</th>
                    <th style="padding: 0.75rem;">ゲーム</th>
                    <th style="padding: 0.75rem;">投稿者</th>
                    <th style="padding: 0.75rem;">通報理由</th>
                    <th style="padding: 0.75rem;">通報日時</th>
                    <th style="padding: 0.75rem;">操作</th>
                </tr>
            </thead>
            <tbody>
                {% for r in reports %}
                <tr style="border-bottom: 1px solid var(--border);">
                    <td style="padding: 0.75rem;">{{ r.post_id }}</td>
                    <td style="padding: 0.75rem;"><a href="/games/{{ r.game_id }}" target="_blank" style="color: #3b82f6;">{{ r.game_title }}</a></td>
                    <td style="padding: 0.75rem;">{{ r.username }}</td>
                    <td style="padding: 0.75rem; color: var(--danger); font-weight: bold;">{{ r.reason }}</td>
                    <td style="padding: 0.75rem;">{{ r.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                    <td style="padding: 0.75rem;">
                        <form action="/admin/delete_post" method="post" onsubmit="return confirm('本当にこの投稿を削除しますか？（復元できません）');">
                            <input type="hidden" name="post_id" value="{{ r.post_id }}">
                            <button type="submit" class="btn btn-x btn-small" style="background: var(--danger); border-color: darkred;">🗑 削除</button>
                        </form>
                    </td>
                </tr>
                <tr>
                    <td colspan="6" style="padding: 0.5rem 1rem 1.5rem; background: #0b1120; color: #cbd5e1; white-space: pre-wrap; font-size: 0.85rem;">{{ r.content }}</td>
                </tr>
                {% else %}
                <tr><td colspan="6" style="padding: 1rem; text-align: center; color: var(--text-sub);">現在、通報されている投稿はありません。</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
"""

# ---------------------------------------------------------------------------
# 運営者作成コンテンツ用テンプレート（ガイド・運営者情報・利用規約・お問い合わせ）
# ---------------------------------------------------------------------------
GUIDE_INDEX_HTML = """
<div class="card" style="max-width: 800px; margin: 0 auto;">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem;">📖 ガイド</h2>
    <p style="color: var(--text-sub); margin-bottom: 1.5rem;">ゲーム選びのコツや、布教文の書き方など、Oshi-Geをより楽しむための記事をまとめています。</p>
    {% for a in articles %}
    <a class="guide-link-card" href="/guide/{{ a.slug }}">
        <div class="t">{{ a.title }}</div>
        <div class="d">{{ a.desc }}</div>
    </a>
    {% endfor %}
    <div style="margin-top: 2rem; padding-top: 1.5rem; border-top: 1px dashed var(--border);">
        <div style="color: var(--text-sub); font-size: 0.9rem; font-weight: bold; margin-bottom: 0.6rem;">ジャンルから探す</div>
        <div class="genre-chip-row">
            {% for slug, name in GENRE_SLUGS.items() %}<a class="genre-chip" href="/genres/{{ slug }}">{{ name }}</a>{% endfor %}
        </div>
    </div>
</div>
"""

ARTICLE_HTML = """
<div class="card" style="max-width: 800px; margin: 0 auto;">
    <div style="font-size: 0.85rem; color: var(--text-sub); margin-bottom: 0.5rem;"><a href="/guide" style="color: var(--text-sub);">ガイド</a> &gt; 記事</div>
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.75rem; margin-bottom: 1.5rem; font-size: 1.7rem; line-height: 1.4;">{{ article.title }}</h2>
    <div class="prose">{{ article.body | safe }}</div>

    <div style="margin-top: 2.5rem; padding-top: 1.5rem; border-top: 1px dashed var(--border);">
        <div style="color: var(--text-sub); font-size: 0.9rem; font-weight: bold; margin-bottom: 0.8rem;">あわせて読みたい</div>
        {% for a in articles %}{% if a.slug != article.slug %}
        <a class="guide-link-card" href="/guide/{{ a.slug }}"><div class="t">{{ a.title }}</div></a>
        {% endif %}{% endfor %}
    </div>
    <div style="margin-top: 1.5rem; text-align: center;">
        <a href="/" class="btn btn-primary">布教されているゲームを見る</a>
    </div>
</div>
"""

ABOUT_HTML = """
<div class="card" style="max-width: 800px; margin: 0 auto;">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">運営者情報</h2>
    <div class="prose">
        <h3>Oshi-Geについて</h3>
        <p>Oshi-Geは、好きなゲームの魅力をネタバレなしで伝え合うためのゲーム布教コミュニティです。「次に遊ぶゲームが見つからない」という人と、「好きなゲームをもっと知ってほしい」という人を結びつけることを目的としています。</p>

        <h3>サイトの特徴</h3>
        <ul>
            <li><strong>ネタバレレベルの明示</strong>：すべての布教コメントに3段階のレベルを設定でき、ストーリーに関わる内容は初期状態で隠れます。</li>
            <li><strong>選びやすい情報設計</strong>：「一言で布教すると？」「誰におすすめ？」「プレイ時間」「推しポイント」など、遊ぶかどうかを判断しやすい項目を用意しています。</li>
            <li><strong>布教カード</strong>：投稿内容から、SNSで共有できる画像を自動で作成できます。</li>
            <li><strong>布教リクエスト</strong>：気になるゲームの紹介を、他のユーザーにお願いできます。</li>
        </ul>

        <h3>運営方針</h3>
        <ul>
            <li>投稿はスパム・誹謗中傷・過度なネタバレがないか、通報とあわせて管理者が確認し、不適切なものは削除します。</li>
            <li>ゲームの画像は、権利を持つものだけを掲載する方針です。権利者の方からの削除依頼には速やかに対応します。</li>
            <li>当サイトはゲームの公式サイトではなく、各ゲームの開発元・販売元とは関係ありません。</li>
            <li>ガイド記事やジャンル紹介は運営者が執筆し、随時追加・更新します。</li>
        </ul>

        <h3>広告・アフィリエイトについて</h3>
        <p>当サイトは、Google AdSense、Amazonアソシエイト、楽天アフィリエイトを利用しています（利用開始前のものを含みます）。商品リンクは、投稿が一定数集まったゲームのページにのみ表示し、紹介内容の評価には影響させません。</p>

        <h3>運営者</h3>
        <table>
            <tr><th>サイト名</th><td>Oshi-Ge（推しゲー）</td></tr>
            <tr><th>運営者</th><td>{{ operator_name }}</td></tr>
            <tr><th>お問い合わせ</th><td><a href="/contact">お問い合わせページ</a></td></tr>
            <tr><th>開設</th><td>2026年</td></tr>
        </table>
    </div>
</div>
"""

TERMS_HTML = """
<div class="card" style="max-width: 800px; margin: 0 auto;">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">利用規約</h2>
    <div class="prose">
        <p>この利用規約（以下「本規約」）は、Oshi-Ge（以下「当サイト」）の利用条件を定めるものです。当サイトを利用した時点で、本規約に同意したものとみなします。</p>

        <h3>第1条（サービス内容）</h3>
        <p>当サイトは、ユーザーがゲームの魅力を紹介（以下「布教」）し、ゲーム情報を登録・閲覧できるサービスです。会員登録なしでも利用できますが、一部の機能（ゲーム情報の編集など）にはログインが必要です。</p>

        <h3>第2条（投稿のルール）</h3>
        <p>ユーザーは、次の内容を投稿してはいけません。</p>
        <ul>
            <li>設定したネタバレレベルに合わない内容（例：Lv.0に結末や重要な展開を書く）</li>
            <li>他者への誹謗中傷、差別的な表現、攻撃的な内容</li>
            <li>スパム、無関係な宣伝、同じ内容の繰り返し投稿</li>
            <li>個人情報の公開や、他者のプライバシーを侵害する内容</li>
            <li>法令や公序良俗に反する内容</li>
            <li>他の文章や作品を無断で転載したもの</li>
        </ul>

        <h3>第3条（画像の掲載について）</h3>
        <p>ゲーム画像をアップロードする場合は、次の点を守ってください。</p>
        <ul>
            <li>ご自身で撮影したスクリーンショットなど、掲載する権利のある画像、または権利者が許可している画像のみを使用してください。</li>
            <li>公式の宣伝素材を使用する場合は、権利者が定めるガイドラインの範囲内でご利用ください。</li>
            <li>第三者の著作権、肖像権、その他の権利を侵害する画像は掲載できません。</li>
        </ul>
        <p>権利者の方から削除の申し出があった場合や、権利侵害のおそれがあると判断した場合は、予告なく画像を削除することがあります。削除のご依頼は<a href="/contact">お問い合わせページ</a>からご連絡ください。</p>

        <h3>第4条（投稿内容の権利）</h3>
        <p>投稿された文章の著作権は、投稿者に帰属します。ただし、投稿者は当サイトに対し、当サイトの運営・改善・宣伝に必要な範囲で、投稿内容を無償で利用（表示、複製、加工、布教カードなどの形式への変換を含む）することを許諾するものとします。</p>

        <h3>第5条（投稿の削除・利用制限）</h3>
        <p>管理者は、本規約に違反する、または不適切と判断した投稿を、予告なく削除または非表示にできます。また、悪質な場合は、当該ユーザーの利用を制限することがあります。</p>

        <h3>第6条（広告・アフィリエイト）</h3>
        <p>当サイトには、広告およびアフィリエイトリンクが含まれます。リンク先の商品やサービスについて、当サイトは責任を負いません。</p>

        <h3>第7条（免責）</h3>
        <ul>
            <li>投稿内容の正確性や完全性について、当サイトは保証しません。</li>
            <li>当サイトの利用によって生じた損害について、当サイトに故意または重大な過失がある場合を除き、責任を負いません。</li>
            <li>システムの保守や障害などにより、予告なくサービスを中断・変更・終了することがあります。</li>
        </ul>

        <h3>第8条（規約の変更）</h3>
        <p>本規約は、必要に応じて変更することがあります。変更後の規約は、当サイトに掲載した時点から効力を持ちます。</p>

        <p style="margin-top: 2rem; color: var(--text-sub);">制定日：2026年</p>
    </div>
</div>
"""

CONTACT_HTML = """
<div class="card" style="max-width: 800px; margin: 0 auto;">
    <h2 style="border-bottom: 2px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1.5rem;">お問い合わせ</h2>
    <div class="prose">
        <p>Oshi-Geに関するご質問、ご意見、不具合のご報告は、下記の窓口までお寄せください。</p>
        <h3>お問い合わせフォーム</h3>
        <p><a href="{{ contact_form_url }}" target="_blank" rel="noopener" class="btn btn-primary" style="color:#fff; text-decoration:none;">お問い合わせフォームを開く</a></p>
        {% if contact_email %}
        <h3>メールでのお問い合わせ</h3>
        <p>{{ contact_email }}</p>
        {% endif %}
        <h3>こんなときにご利用ください</h3>
        <ul>
            <li>投稿やゲーム情報の削除依頼（権利者の方、投稿者ご本人を含みます）</li>
            <li>ゲーム画像に関する権利侵害のご連絡</li>
            <li>アカウントデータ（連携情報・投稿履歴）の削除依頼</li>
            <li>不具合や、使いにくい点のご報告</li>
            <li>その他、サイトについてのご意見</li>
        </ul>
        <p>内容を確認のうえ、順次対応します。お返事までにお時間をいただく場合があります。</p>
    </div>
</div>
"""

def render_page(request: Request, content_template_str, is_top=False, page_title=None, og_description=None, og_image=None, game_schema=None, noindex=False, **kwargs):
    content_html = get_template(content_template_str).render(user_id=get_user_id(request), **kwargs)
    final_title = page_title if page_title else "Oshi-Ge | ネタバレなしゲーム布教サイト"
    final_desc = og_description if og_description else "未プレイの人にこそ読んでほしい、熱量100%のゲーム布教コミュニティ。"

    canonical_url = f"{get_base_url(request)}{request.url.path}"

    html = get_template(BASE_HTML).render(
        request=request, css=Markup(CSS), js=Markup(JS), content=Markup(content_html), is_top=is_top,
        page_title=final_title, og_description=final_desc, og_image=og_image, game_schema=game_schema,
        base_url=get_base_url(request), canonical_url=canonical_url, noindex=noindex, **kwargs
    )
    return HTMLResponse(html)

# ---------------------------------------------------------------------------
# OGP Dynamic Image Routes
# ---------------------------------------------------------------------------
OGP_HEADERS = {"Cache-Control": "public, max-age=86400"}

@app.get("/ogp.png")
def ogp_default():
    png = build_ogp("誰かの人生を変える1本を。", "", "未プレイの人にこそ読んでほしい、ゲーム布教コミュニティ", "")
    return Response(content=png, media_type="image/png", headers=OGP_HEADERS)

@app.get("/games/{game_id}/ogp.png")
def ogp_game(game_id: int):
    with get_db_connection() as conn:
        game = conn.execute("SELECT title, genre, image_url FROM games WHERE id = %s", (game_id,)).fetchone()
        if not game:
            raise HTTPException(status_code=404)
        latest = conn.execute(
            "SELECT catchphrase FROM posts WHERE game_id = %s ORDER BY created_at DESC LIMIT 1", (game_id,)
        ).fetchone()
    png = build_ogp(game["title"] or "", game["genre"] or "", (latest or {}).get("catchphrase") or "", game["image_url"] or "")
    return Response(content=png, media_type="image/png", headers=OGP_HEADERS)


# ---------------------------------------------------------------------------
# SEO: robots.txt / sitemap.xml / ads.txt
# ---------------------------------------------------------------------------
@app.get("/robots.txt")
def robots_txt(request: Request):
    base = get_base_url(request)
    # AdSenseクローラー(Mediapartners-Google)は「User-agent: *」を無視するため、
    # 広告を出さないページは同じ禁止ルールを個別に指定する
    rules = (
        "Disallow: /mypage\n"
        "Disallow: /admin\n"
        "Disallow: /auth/\n"
        "Disallow: /api/\n"
        "Disallow: /proxy-image\n"
        "Disallow: /games/new\n"
        "Disallow: /games/random\n"
        "Disallow: /games/*/edit\n"
        "Disallow: /games/*/posts/\n"
        "Disallow: /posts/\n"
        "Disallow: /requests\n"
    )
    body = (
        "User-agent: Mediapartners-Google\n" + rules +
        "\n"
        "User-agent: *\n" + rules +
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(content=body, media_type="text/plain; charset=utf-8")

@app.get("/ads.txt")
def ads_txt():
    body = f"google.com, {ADSENSE_PUB_ID}, DIRECT, f08c47fec0942fa0\n"
    return Response(content=body, media_type="text/plain; charset=utf-8")

@app.get("/sitemap.xml")
def sitemap_xml(request: Request):
    base = get_base_url(request)
    urls = []  # (path, lastmod or None)

    for path in ["/", "/guide", "/about", "/terms", "/privacy", "/contact"]:
        urls.append((path, None))
    for a in ARTICLES:
        urls.append((f"/guide/{a['slug']}", None))

    try:
        with get_db_connection() as conn:
            genre_rows = conn.execute("SELECT genre, COUNT(*) AS c FROM games GROUP BY genre").fetchall()
            game_rows = conn.execute('''
                SELECT g.id, GREATEST(g.created_at, COALESCE(MAX(p.created_at), g.created_at)) AS lastmod
                FROM games g
                JOIN posts p ON p.game_id = g.id
                GROUP BY g.id
                HAVING COUNT(p.id) >= 1 AND (COALESCE(MAX(g.description), '') <> '' OR COUNT(p.id) >= 2)
                ORDER BY g.id
            ''').fetchall()
    except Exception:
        logger.exception("sitemap query failed")
        genre_rows, game_rows = [], []

    genre_counts = {r["genre"]: r["c"] for r in genre_rows}
    for slug, name in GENRE_SLUGS.items():
        if genre_counts.get(name, 0) > 0:
            urls.append((f"/genres/{slug}", None))
    for r in game_rows:
        lm = r["lastmod"].strftime("%Y-%m-%d") if r.get("lastmod") else None
        urls.append((f"/games/{r['id']}", lm))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lm in urls:
        parts.append("<url>")
        parts.append(f"<loc>{xml_escape(base + path)}</loc>")
        if lm:
            parts.append(f"<lastmod>{lm}</lastmod>")
        parts.append("</url>")
    parts.append("</urlset>")
    return Response(content="\n".join(parts), media_type="application/xml")


# ---------------------------------------------------------------------------
# Auth / Login Routing (Stateless PKCE)
# ---------------------------------------------------------------------------
def _pkce_pair():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge

@app.post("/auth/login/{provider}")
def login(request: Request, provider: str):
    if provider not in ["google", "x"]:
        raise HTTPException(status_code=400, detail="Invalid provider")
    if not SUPABASE_URL:
        return alert_back('Supabaseの設定が存在しないためログインできません。')
        
    verifier, challenge = _pkce_pair()
    qs = urlencode({
        "provider": provider,
        "redirect_to": f"{get_base_url(request)}/auth/callback",
        "code_challenge": challenge,
        "code_challenge_method": "s256",
    })
    res = RedirectResponse(url=f"{SUPABASE_URL}/auth/v1/authorize?{qs}", status_code=303)
    res.set_cookie("oshige-pkce", serializer.dumps(verifier), max_age=600, httponly=True, samesite="lax", secure=True)
    return res

def exchange_code(code: str, verifier: str) -> dict:
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=pkce",
        data=json.dumps({"auth_code": code, "code_verifier": verifier}).encode(),
        headers={"Content-Type": "application/json", "apikey": SUPABASE_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

@app.get("/auth/callback")
def auth_callback(request: Request, code: str = None):
    raw = request.cookies.get("oshige-pkce")
    if not code or not raw:
        return RedirectResponse(url="/mypage", status_code=303)
    try:
        verifier = serializer.loads(raw)
        data = exchange_code(code, verifier)
        res = RedirectResponse(url="/auth/merge", status_code=303)
        set_auth_cookies(res, data["access_token"], data["refresh_token"], data.get("expires_in", 3600))
        res.delete_cookie("oshige-pkce")
        return res
    except Exception as e:
        logger.error(f"Auth callback error: {e}")
        return RedirectResponse(url="/mypage", status_code=303)

@app.get("/auth/merge")
def auth_merge(request: Request):
    user_id = get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/mypage", status_code=303)

    my_posts = parse_id_cookie(request, "my_posts")
    bookmarks = parse_id_cookie(request, "bookmarks")
    
    with get_db_connection() as conn:
        if my_posts:
            conn.execute("UPDATE posts SET user_id = %s WHERE id = ANY(%s) AND user_id IS NULL", (user_id, my_posts))
        
        if bookmarks:
            conn.execute("""
                INSERT INTO bookmarks (user_id, game_id)
                SELECT %s::uuid, id FROM games WHERE id = ANY(%s)
                ON CONFLICT (user_id, game_id) DO NOTHING
            """, (user_id, bookmarks))
            
        conn.commit()
    
    res = RedirectResponse(url="/mypage", status_code=303)
    res.delete_cookie("my_posts")
    res.delete_cookie("bookmarks")
    return res

@app.post("/auth/logout")
def logout(request: Request):
    res = RedirectResponse(url="/mypage", status_code=303)
    clear_auth_cookies(res)
    return res


# ---------------------------------------------------------------------------
# Admin Routing
# ---------------------------------------------------------------------------
def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Admin disabled: ADMIN_PASSWORD is not set in environment.")
        
    is_correct_username = secrets.compare_digest(credentials.username, "admin")
    is_correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/admin")
def admin_dashboard(request: Request, admin: str = Depends(verify_admin)):
    with get_db_connection() as conn:
        reports = conn.execute('''
            SELECT p.id as post_id, p.content, p.username, g.id as game_id, g.title as game_title, r.reason, r.created_at
            FROM reports r
            JOIN posts p ON r.post_id = p.id
            JOIN games g ON p.game_id = g.id
            ORDER BY r.created_at DESC LIMIT 50
        ''').fetchall()
        
    return render_page(request, ADMIN_HTML, page_title="管理ダッシュボード - Oshi-Ge", noindex=True, reports=reports)

@app.post("/admin/delete_post")
def admin_delete_post(request: Request, post_id: int = Form(...), admin: str = Depends(verify_admin)):
    with get_db_connection() as conn:
        conn.execute('DELETE FROM reports WHERE post_id = %s', (post_id,))
        conn.execute('DELETE FROM posts WHERE id = %s', (post_id,))
        conn.commit()
    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------------------------------------------------------
# Static / Editorial Pages (ガイド・運営者情報・利用規約・お問い合わせ)
# ---------------------------------------------------------------------------
@app.get("/privacy")
def read_privacy(request: Request):
    return render_page(request, PRIVACY_HTML, page_title="プライバシーポリシー・免責事項 - Oshi-Ge")

@app.get("/about")
def read_about(request: Request):
    return render_page(
        request, ABOUT_HTML, page_title="運営者情報 - Oshi-Ge",
        og_description="Oshi-Geは、好きなゲームの魅力をネタバレなしで伝え合うゲーム布教コミュニティです。サイトの特徴や運営方針、運営者情報をご紹介します。",
        operator_name=OPERATOR_NAME,
    )

@app.get("/terms")
def read_terms(request: Request):
    return render_page(
        request, TERMS_HTML, page_title="利用規約 - Oshi-Ge",
        og_description="Oshi-Geの利用規約。投稿のルール、画像の掲載、権利の扱い、免責事項などを定めています。",
    )

@app.get("/contact")
def read_contact(request: Request):
    return render_page(
        request, CONTACT_HTML, page_title="お問い合わせ - Oshi-Ge",
        og_description="Oshi-Geへのお問い合わせ窓口です。ご意見、不具合のご報告、削除依頼などはこちらからどうぞ。",
        contact_form_url=CONTACT_FORM_URL, contact_email=CONTACT_EMAIL,
    )

@app.get("/guide")
def read_guide_index(request: Request):
    return render_page(
        request, GUIDE_INDEX_HTML, page_title="ガイド｜ゲーム選びと布教のコツ - Oshi-Ge",
        og_description="次に遊ぶゲームの選び方、ネタバレなしの布教文の書き方、初心者向けの最初の一本の探し方など、ゲームをもっと楽しむための記事をまとめています。",
        articles=ARTICLES,
    )

@app.get("/guide/{slug}")
def read_guide_article(request: Request, slug: str):
    article = ARTICLE_MAP.get(slug)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return render_page(
        request, ARTICLE_HTML, page_title=f"{article['title']} - Oshi-Ge",
        og_description=article["desc"], article=article, articles=ARTICLES,
    )


# ---------------------------------------------------------------------------
# Main Routing
# ---------------------------------------------------------------------------

@app.get("/proxy-image")
def proxy_image(url: str):
    data, content_type = fetch_image_bytes(url)
    if not data:
        raise HTTPException(status_code=404, detail="Image not found or invalid")
    return Response(content=data, media_type=content_type)

@app.get("/api/games-list")
def api_games_list():
    with get_db_connection() as conn:
        games = conn.execute("SELECT id, title FROM games").fetchall()
    return games

@app.get("/")
def read_root(request: Request, q: str = "", genre: str = "", platform: str = "", sort: str = "new"):
    q = clip(q, 100)
    order_clause = "COALESCE((SELECT MAX(created_at) FROM posts p WHERE p.game_id = g.id), g.created_at) DESC"
    if sort == "posts":
        order_clause = "(SELECT COUNT(*) FROM posts p WHERE p.game_id = g.id) DESC, g.created_at DESC"

    query = '''SELECT g.*, (SELECT catchphrase FROM posts p WHERE p.game_id = g.id ORDER BY p.created_at DESC LIMIT 1) as latest_catchphrase, (SELECT COUNT(*) FROM posts p WHERE p.game_id = g.id) as post_count FROM games g WHERE 1=1'''
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

    if genre:
        query += " AND g.genre = %s"
        params.append(genre)
    if platform:
        query += " AND g.platform ILIKE %s"
        params.append('%' + platform + '%')

    with get_db_connection() as conn:
        games = conn.execute(query + f" ORDER BY {order_clause}", params).fetchall()
        weekly_ranking = conn.execute('''SELECT g.id, g.title, g.image_url, COALESCE(SUM(COALESCE(p.likes,0) + COALESCE(p.wanna_play,0) + COALESCE(p.agree,0)), 0) as weekly_likes FROM games g JOIN posts p ON g.id = p.game_id WHERE p.created_at >= NOW() - INTERVAL '7 days' GROUP BY g.id ORDER BY weekly_likes DESC, g.created_at DESC LIMIT 5''').fetchall()
        requests = conn.execute('SELECT * FROM requests ORDER BY created_at DESC LIMIT 5').fetchall()

    # 検索・絞り込み・並び替え付きのURLは重複・低価値ページになるため noindex
    has_filters = bool(q or genre or platform or sort != "new")

    return render_page(
        request, INDEX_HTML, is_top=True, noindex=has_filters, show_intro=not has_filters,
        games=games, q=q, genre=genre, platform=platform, sort=sort,
        weekly_ranking=weekly_ranking, requests=requests, articles=ARTICLES
    )

# ---------------------------------------------------------------------------
# SEO対策: ジャンル別 静的URLルーティング (LP用)
# ---------------------------------------------------------------------------

@app.get("/genres/{genre_slug}")
def read_genre_page(request: Request, genre_slug: str, sort: str = "new"):
    genre_slug = genre_slug.lower()
    if genre_slug not in GENRE_SLUGS:
        raise HTTPException(status_code=404, detail="Genre not found")
        
    genre_name = GENRE_SLUGS[genre_slug]
    
    order_clause = "COALESCE((SELECT MAX(created_at) FROM posts p WHERE p.game_id = g.id), g.created_at) DESC"
    if sort == "posts":
        order_clause = "(SELECT COUNT(*) FROM posts p WHERE p.game_id = g.id) DESC, g.created_at DESC"
        
    query = '''SELECT g.*, 
              (SELECT catchphrase FROM posts p WHERE p.game_id = g.id ORDER BY p.created_at DESC LIMIT 1) as latest_catchphrase, 
              (SELECT COUNT(*) FROM posts p WHERE p.game_id = g.id) as post_count 
              FROM games g WHERE g.genre = %s ORDER BY ''' + order_clause
              
    with get_db_connection() as conn:
        games = conn.execute(query, (genre_name,)).fetchall()
        weekly_ranking = conn.execute('''SELECT g.id, g.title, g.image_url, COALESCE(SUM(COALESCE(p.likes,0) + COALESCE(p.wanna_play,0) + COALESCE(p.agree,0)), 0) as weekly_likes FROM games g JOIN posts p ON g.id = p.game_id WHERE p.created_at >= NOW() - INTERVAL '7 days' GROUP BY g.id ORDER BY weekly_likes DESC, g.created_at DESC LIMIT 5''').fetchall()
        requests = conn.execute('SELECT * FROM requests ORDER BY created_at DESC LIMIT 5').fetchall()

    page_title = f"{genre_name}のおすすめ神ゲー布教一覧 - Oshi-Ge"
    og_desc = f"次に遊ぶゲームを探している方へ。みんなが熱く語る、ネタバレなしの{genre_name}おすすめ布教一覧です。"

    # ゲームが0件、または並び替え付きURLの場合は noindex
    noindex = (len(games) == 0) or (sort != "new")

    return render_page(
        request, 
        INDEX_HTML, 
        is_top=False, 
        noindex=noindex,
        show_intro=False,
        games=games, 
        q="", 
        genre=genre_name, 
        genre_intro=GENRE_INTROS.get(genre_slug, ""),
        platform="", 
        sort=sort, 
        weekly_ranking=weekly_ranking, 
        requests=requests,
        articles=ARTICLES,
        page_title=page_title,
        og_description=og_desc
    )

@app.get("/games/random")
def random_game():
    with get_db_connection() as conn:
        game = conn.execute('SELECT id FROM games ORDER BY RANDOM() LIMIT 1').fetchone()
    if game:
        return RedirectResponse(url=f"/games/{game['id']}", status_code=303)
    return RedirectResponse(url="/", status_code=303)

@app.get("/games/new")
def new_game_form(request: Request, title: str = ""):
    return render_page(request, NEW_GAME_HTML, page_title="ゲームを追加する - Oshi-Ge", noindex=True, title=clip(title, 200))

@app.post("/games/new")
def create_game(
    request: Request,
    title: str = Form(...), description: str = Form(""), genre: str = Form(""), platform: str = Form(""), image_base64: str = Form(""),
    developer_x_id: str = Form(""), username: str = Form(...), catchphrase: str = Form(...), target_audience: str = Form(""), play_time: str = Form(""), content: str = Form(...), spoiler_level: int = Form(...),
    oshi_points: List[str] = Form(default=[])
):
    if not check_rate_limit(request):
        return HTMLResponse(RATE_LIMIT_HTML)
    if image_base64 and len(image_base64) > 6600000:
        return alert_back('画像サイズが大きすぎます（5MB制限）。別の画像をご利用ください。')

    title = clip(title, 200)
    description = clip(description, 2000)
    genre = clean_genre(genre)
    platform = clean_platform(platform)
    developer_x_id = clean_x_id(developer_x_id)
    username = clip(username, 50) or "名無しの布教者"
    catchphrase = clip(catchphrase, 100)
    target_audience = clip(target_audience, 100)
    play_time = clip(play_time, 50)
    content = clip(content, 3000)
    spoiler_level = clamp_spoiler(spoiler_level)
    points_str = clean_points(oshi_points)

    if not title or not catchphrase or not content:
        return alert_back('必須項目が入力されていません。')

    def dup_response():
        return render_page(request, NEW_GAME_HTML, noindex=True, error_msg=f"「{title}」は既に登録されています。", title=title, description=description, genre=genre, platform=platform, developer_x_id=developer_x_id, page_title="ゲームを追加する - Oshi-Ge")

    user_id = get_user_id(request)

    with get_db_connection() as conn:
        if conn.execute('SELECT id FROM games WHERE LOWER(title) = LOWER(%s)', (title,)).fetchone():
            return dup_response()

        image_url = upload_image_to_supabase(image_base64)

        try:
            cursor_game = conn.execute('INSERT INTO games (title, description, genre, platform, image_url, developer_x_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id', (title, description, genre, platform, image_url, developer_x_id))
        except pgerrors.UniqueViolation:
            conn.rollback()
            return dup_response()
        game_id = cursor_game.fetchone()["id"]

        cursor_post = conn.execute('''INSERT INTO posts (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, oshi_points, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''', (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, points_str, user_id))
        post_id = cursor_post.fetchone()["id"]
        conn.commit()

    mark_posted(request)
    res = RedirectResponse(url=f"/games/{game_id}?posted={post_id}", status_code=303)
    
    if not user_id:
        my_posts = parse_id_cookie(request, "my_posts")
        my_posts.append(post_id)
        set_cookie_safe(res, "my_posts", my_posts)
    return res

@app.get("/games/{game_id}/edit")
def edit_game_form(request: Request, game_id: int):
    user_id = get_user_id(request)
    if not user_id:
        return alert_back('ゲーム情報の編集にはログインが必要です。')
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return render_page(request, EDIT_GAME_HTML, game=game, noindex=True, page_title=f"{game['title']}の編集 - Oshi-Ge")

@app.post("/games/{game_id}/edit")
def update_game(request: Request, game_id: int, title: str = Form(...), description: str = Form(""), genre: str = Form(""), platform: str = Form(""), developer_x_id: str = Form(""), image_base64: str = Form("")):
    user_id = get_user_id(request)
    if not user_id:
        return alert_back('ゲーム情報の編集にはログインが必要です。')
    if image_base64 and len(image_base64) > 6600000:
        return alert_back('画像サイズが大きすぎます（5MB制限）。別の画像をご利用ください。')

    title = clip(title, 200)
    description = clip(description, 2000)
    genre = clean_genre(genre)
    platform = clean_platform(platform)
    developer_x_id = clean_x_id(developer_x_id)
    if not title:
        return alert_back('タイトルを入力してください。')

    with get_db_connection() as conn:
        cur = conn.execute('SELECT image_url FROM games WHERE id = %s', (game_id,)).fetchone()
        if not cur:
            raise HTTPException(status_code=404, detail="Game not found")

        image_url = cur["image_url"] or ""
        if image_base64:
            new_url = upload_image_to_supabase(image_base64)
            if new_url:
                image_url = new_url

        try:
            conn.execute('UPDATE games SET title = %s, description = %s, genre = %s, platform = %s, image_url = %s, developer_x_id = %s WHERE id = %s', (title, description, genre, platform, image_url, developer_x_id, game_id))
            conn.commit()
        except pgerrors.UniqueViolation:
            conn.rollback()
            return alert_back('同じタイトルのゲームが既に登録されています。')
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@app.get("/games/{game_id}")
def read_game(request: Request, game_id: int, sort: str = "likes"):
    with get_db_connection() as conn:
        game = conn.execute('SELECT * FROM games WHERE id = %s', (game_id,)).fetchone()
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        order_str = 'created_at DESC' if sort == 'new' else '(COALESCE(likes,0) + COALESCE(wanna_play,0) + COALESCE(agree,0)) DESC, created_at DESC'
        posts = conn.execute(f'SELECT * FROM posts WHERE game_id = %s ORDER BY {order_str}', (game_id,)).fetchall()

    user_id = get_user_id(request)
    my_posts = []
    bookmarks = []
    
    if user_id:
        with get_db_connection() as conn:
            bm_rows = conn.execute('SELECT game_id FROM bookmarks WHERE user_id = %s', (user_id,)).fetchall()
            bookmarks = [row["game_id"] for row in bm_rows]
    else:
        my_posts = parse_id_cookie(request, "my_posts")
        bookmarks = parse_id_cookie(request, "bookmarks")

    game_title_tag = f"{game['title']} の評価・感想・ネタバレなし布教 - Oshi-Ge"
    og_desc = game['description'] if game['description'] else f"『{game['title']}』のおすすめ布教ページです。ネタバレなしで魅力をお伝えします。"
    og_img = f"{get_base_url(request)}/games/{game_id}/ogp.png"

    # 内容が薄いゲームページ（投稿なし／説明も投稿も少ない）は検索エンジンにインデックスさせない
    post_count = len(posts)
    has_desc = bool((game["description"] or "").strip())
    indexable = post_count >= 1 and (has_desc or post_count >= 2) and sort in ("likes",)
    # 投稿が一定数集まったページにのみ商品リンクを表示
    show_affiliate = post_count >= AFFILIATE_MIN_POSTS

    return render_page(request, GAME_HTML, game=game, posts=posts, sort=sort, my_posts=my_posts, is_bookmarked=(game_id in bookmarks), page_title=game_title_tag, og_description=og_desc, og_image=og_img, game_schema=game, noindex=not indexable, show_affiliate=show_affiliate)

@app.post("/games/{game_id}/posts")
def create_post(request: Request, game_id: int, username: str = Form(...), catchphrase: str = Form(...), target_audience: str = Form(""), play_time: str = Form(""), content: str = Form(...), spoiler_level: int = Form(...), oshi_points: List[str] = Form(default=[])):
    if not check_rate_limit(request):
        return HTMLResponse(RATE_LIMIT_HTML)

    username = clip(username, 50) or "名無しの布教者"
    catchphrase = clip(catchphrase, 100)
    target_audience = clip(target_audience, 100)
    play_time = clip(play_time, 50)
    content = clip(content, 3000)
    spoiler_level = clamp_spoiler(spoiler_level)
    points_str = clean_points(oshi_points)
    if not catchphrase or not content:
        return alert_back('必須項目が入力されていません。')

    user_id = get_user_id(request)

    with get_db_connection() as conn:
        if not conn.execute('SELECT id FROM games WHERE id = %s', (game_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Game not found")
        cursor = conn.execute('''INSERT INTO posts (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, oshi_points, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''', (game_id, username, catchphrase, target_audience, play_time, content, spoiler_level, points_str, user_id))
        post_id = cursor.fetchone()["id"]
        conn.commit()

    mark_posted(request)
    res = RedirectResponse(url=f"/games/{game_id}?posted={post_id}", status_code=303)
    
    if not user_id:
        my_posts = parse_id_cookie(request, "my_posts")
        my_posts.append(post_id)
        set_cookie_safe(res, "my_posts", my_posts)
    return res

NO_EDIT_PERMISSION = "<script>alert('投稿の編集権限が確認できませんでした（Cookieが無効化されている、または別のアカウントで投稿された可能性があります）。');location.href='/games/{gid}';</script>"

@app.get("/games/{game_id}/posts/{post_id}/edit")
def edit_post_form(request: Request, game_id: int, post_id: int):
    user_id = get_user_id(request)
    with get_db_connection() as conn:
        post = conn.execute('SELECT id, user_id, username, catchphrase, target_audience, play_time, oshi_points, spoiler_level, content FROM posts WHERE id = %s AND game_id = %s', (post_id, game_id)).fetchone()
        
    if not post:
        raise HTTPException(status_code=404)
        
    if not is_owner(request, post, user_id):
        return HTMLResponse(NO_EDIT_PERMISSION.format(gid=game_id))

    return render_page(request, EDIT_POST_HTML, game_id=game_id, post=post, noindex=True, page_title="布教の編集 - Oshi-Ge")

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
    user_id = get_user_id(request)
    with get_db_connection() as conn:
        post = conn.execute('SELECT id, user_id FROM posts WHERE id = %s AND game_id = %s', (post_id, game_id)).fetchone()
        
    if not post:
        raise HTTPException(status_code=404)
        
    if not is_owner(request, post, user_id):
        return HTMLResponse(NO_EDIT_PERMISSION.format(gid=game_id))

    username = clip(username, 50) or "名無しの布教者"
    catchphrase = clip(catchphrase, 100)
    target_audience = clip(target_audience, 100)
    play_time = clip(play_time, 50)
    content = clip(content, 3000)
    spoiler_level = clamp_spoiler(spoiler_level)
    points_str = clean_points(oshi_points)
    if not catchphrase or not content:
        return alert_back('必須項目が入力されていません。')

    with get_db_connection() as conn:
        conn.execute('''UPDATE posts SET username = %s, catchphrase = %s, target_audience = %s, play_time = %s, content = %s, spoiler_level = %s, oshi_points = %s WHERE id = %s AND game_id = %s''', (username, catchphrase, target_audience, play_time, content, spoiler_level, points_str, post_id, game_id))
        conn.commit()
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@app.post("/posts/{post_id}/report")
def report_post(post_id: int, reason: str = Form(...)):
    reason = reason if reason in REPORT_REASONS else "その他"
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
        cursor = conn.execute(
            f'UPDATE posts SET {react_type} = COALESCE({react_type}, 0) + 1 WHERE id = %s AND game_id = %s RETURNING {react_type}',
            (post_id, game_id),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404)
        conn.commit()
    return {"count": row[react_type]}

@app.post("/games/{game_id}/bookmark")
def toggle_bookmark(request: Request, game_id: int):
    user_id = get_user_id(request)
    is_bookmarked = False
    
    with get_db_connection() as conn:
        if not conn.execute('SELECT id FROM games WHERE id = %s', (game_id,)).fetchone():
            raise HTTPException(status_code=404)
            
        if user_id:
            existing = conn.execute('SELECT id FROM bookmarks WHERE user_id = %s AND game_id = %s', (user_id, game_id)).fetchone()
            if existing:
                conn.execute('DELETE FROM bookmarks WHERE id = %s', (existing["id"],))
            else:
                conn.execute('INSERT INTO bookmarks (user_id, game_id) VALUES (%s, %s)', (user_id, game_id))
                is_bookmarked = True
            conn.commit()
            return JSONResponse(content={"bookmarked": is_bookmarked})
        else:
            bookmarks = parse_id_cookie(request, "bookmarks")
            if game_id in bookmarks:
                bookmarks.remove(game_id)
            else:
                bookmarks.append(game_id)
                is_bookmarked = True
            bookmarks = bookmarks[-200:]
            res = JSONResponse(content={"bookmarked": is_bookmarked})
            set_cookie_safe(res, "bookmarks", bookmarks)
            return res

@app.post("/requests")
def create_request(request: Request, title: str = Form(...), username: str = Form("名無しのゲーマー")):
    if not check_rate_limit(request):
        return HTMLResponse(RATE_LIMIT_HTML)
    title = clip(title, 200)
    username = clip(username, 50) or "名無しのゲーマー"
    if not title:
        return alert_back('タイトルを入力してください。')
    with get_db_connection() as conn:
        conn.execute('INSERT INTO requests (title, username) VALUES (%s, %s)', (title, username))
        conn.commit()
    mark_posted(request)
    return RedirectResponse(url="/", status_code=303)

@app.get("/mypage")
def mypage(request: Request):
    user_id = get_user_id(request)
    my_posts_list = []
    bookmarked_games = []
    
    with get_db_connection() as conn:
        if user_id:
            my_posts_list = conn.execute("SELECT p.*, g.title as game_title, g.image_url as game_image_url, g.genre as game_genre, g.platform as game_platform, g.developer_x_id as game_developer_x_id FROM posts p JOIN games g ON p.game_id = g.id WHERE p.user_id = %s ORDER BY p.created_at DESC", (user_id,)).fetchall()
            bookmarked_games = conn.execute("SELECT g.* FROM games g JOIN bookmarks b ON g.id = b.game_id WHERE b.user_id = %s ORDER BY b.created_at DESC", (user_id,)).fetchall()
        else:
            my_posts_ids = parse_id_cookie(request, "my_posts")
            bookmarks = parse_id_cookie(request, "bookmarks")
            if my_posts_ids:
                my_posts_list = conn.execute("SELECT p.*, g.title as game_title, g.image_url as game_image_url, g.genre as game_genre, g.platform as game_platform, g.developer_x_id as game_developer_x_id FROM posts p JOIN games g ON p.game_id = g.id WHERE p.id = ANY(%s) ORDER BY p.created_at DESC", (my_posts_ids,)).fetchall()
            if bookmarks:
                bookmarked_games = conn.execute("SELECT * FROM games WHERE id = ANY(%s) ORDER BY created_at DESC", (bookmarks,)).fetchall()

    total_likes = sum((p.get("likes") or 0) + (p.get("wanna_play") or 0) + (p.get("agree") or 0) for p in my_posts_list)

    return render_page(request, MYPAGE_HTML, my_posts_list=my_posts_list, bookmarked_games=bookmarked_games, total_likes=total_likes, noindex=True, page_title="マイページ - Oshi-Ge")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
