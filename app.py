
import base64
from flask import Flask, render_template, request, Response
import requests
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse, quote
import cloudscraper
import jsbeautifier
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import yt_dlp
from io import BytesIO
from flask import send_file, jsonify

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

@app.after_request
def disable_static_cache(response):
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Custom Adapter to fix SSL Handshake Failures
class CustomSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        # Create a context that permits legacy/older ciphers (SECLEVEL=1)
        ctx = create_urllib3_context(ciphers='DEFAULT@SECLEVEL=1')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super(CustomSSLAdapter, self).init_poolmanager(*args, **kwargs)

BASE_URL = "https://animexin.dev"
BASE_URL_TCA = "https://topchineseanime.xyz"

HEADERS = {"User-Agent": "Mozilla/5.0"}

ANIMEXIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://animexin.dev/",
}


def fetch_animexin_html(url: str) -> str:
    """
    Fetch AnimeXin using a browser-like TLS fingerprint.
    Also prints the real upstream response in Render logs.
    """
    response = curl_requests.get(
        url,
        headers=ANIMEXIN_HEADERS,
        impersonate="chrome",
        timeout=30,
        allow_redirects=True
    )

    html = response.text or ""
    first_part = html[:5000].lower()

    print("========== ANIMEXIN FETCH ==========")
    print("Requested URL:", url)
    print("Final URL:", response.url)
    print("Status:", response.status_code)
    print("HTML length:", len(html))
    print("Content-Type:", response.headers.get("content-type"))
    print("Server:", response.headers.get("server"))
    print("CF-Mitigated:", response.headers.get("cf-mitigated"))
    print("HTML beginning:", repr(html[:300]))
    print("====================================")

    if response.status_code != 200:
        raise RuntimeError(
            f"AnimeXin returned HTTP {response.status_code} for {url}"
        )

    challenge_detected = (
        response.headers.get("cf-mitigated") == "challenge"
        or "just a moment" in first_part
        or "challenge-platform" in first_part
        or "cf-chl-" in first_part
        or "attention required" in first_part
    )

    if challenge_detected:
        raise RuntimeError(
            "AnimeXin returned a Cloudflare challenge instead of the website."
        )

    if len(html.strip()) < 500:
        raise RuntimeError(
            f"AnimeXin returned unusually short HTML: {len(html)} characters."
        )

    return html

def recover_episode_context(token: str, title: str = "", episode: str = "", soup=None):
    """Recover anime title and episode number from the episode page/token.

    This is the server-side source of truth, so filename context still works
    even if an old browser JavaScript file sends no title/episode fields.
    """
    clean_title = (title or "").strip()
    clean_episode = (episode or "").strip()

    try:
        episode_url = b64d(token) if token else ""
    except Exception:
        episode_url = ""

    # Prefer the real page heading because it preserves the site's title casing.
    if (not clean_title or clean_title.lower() == "anime") and soup is not None:
        heading = soup.select_one("h1.entry-title")
        raw_heading = heading.get_text(" ", strip=True) if heading else ""
        if raw_heading:
            recovered = re.sub(
                r"\s+(?:episode|ep)\s*[-:]?\s*\d+(?:\.\d+)?\b.*$",
                "",
                raw_heading,
                flags=re.IGNORECASE,
            ).strip(" -")
            if recovered:
                clean_title = recovered

    # Recover episode number from the canonical episode URL.
    if not clean_episode and episode_url:
        match = re.search(
            r"-episode-(\d+(?:\.\d+)?)\b",
            episode_url,
            re.IGNORECASE,
        )
        if match:
            clean_episode = match.group(1)

    # URL fallback for title when the page heading is unavailable.
    if (not clean_title or clean_title.lower() == "anime") and episode_url:
        slug = urlparse(episode_url).path.strip("/")
        slug = re.sub(
            r"-episode-\d+(?:\.\d+)?.*$",
            "",
            slug,
            flags=re.IGNORECASE,
        )
        fallback = re.sub(r"[-_]+", " ", slug).strip()
        if fallback:
            clean_title = fallback.title()

    if not clean_title:
        clean_title = "Anime"

    return clean_title, clean_episode

def format_time(seconds):
    if not seconds:
        return ""
    try:
        seconds = int(seconds)
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        return f"{m}m {s}s"
    except:
        return ""

# -------------------------------
# RUMBLE SUBTITLE EXTRACTOR (UPDATED LOGIC)
# -------------------------------
def extract_rumble_subs(embed_url):
    # 1. Configuration to extract info without downloading the video
    ydl_opts = {
        'skip_download': True, 
        'quiet': True,
        'impersonate': False, # Anti-bot error roknene ke liye
        
        # UNCOMMENT THE LINE BELOW if the video is Premium/Private and you are running on Local PC Chrome:
        # Note: Render cloud par Chrome cookies nahi hoti, isliye wahan isko comment hi rehne dena.
        # 'cookiesfrombrowser': ('chrome',), 
    }
    
    subs = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Fetching subtitle info for: {embed_url}\nPlease wait...")
            info = ydl.extract_info(embed_url, download=False)
            
            # Extract manual and automatic subtitles from the video info
            subtitles = info.get('subtitles', {})
            auto_captions = info.get('automatic_captions', {})
            
            all_subs = {}
            
            # Manual Subtitles ko pehle priority
            for lang, tracks in subtitles.items():
                for t in tracks:
                    if t.get('ext') in ['vtt', 'srt']:
                        all_subs[lang] = {'url': t.get('url'), 'type': 'Manual Subtitle'}
                        break
            
            # Auto-Generated ko baad mein check karenge (Agar manual nahi mila)
            for lang, tracks in auto_captions.items():
                if lang not in all_subs: 
                    for t in tracks:
                        if t.get('ext') in ['vtt', 'srt']:
                            all_subs[lang] = {'url': t.get('url'), 'type': 'Auto-Generated'}
                            break
            
            # Frontend (HTML) dropdown ke liye format ready karna
            for lang, data in all_subs.items():
                subs.append({
                    "lang": lang, 
                    "name": f"{lang} ({data['type']})", # Example: "en (Manual Subtitle)"
                    "url": b64e(data['url']) # URL ko base64 encode kiya taaki tumhare existing downloader me fit ho jaye
                })
                
    except Exception as e:
        print(f"Rumble Sub Error: {e}")
        print("If this is a Premium video, make sure to uncomment the 'cookiesfrombrowser' line locally.")
        
    return subs

def b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")

def b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("utf-8")).decode("utf-8")


def decode_server_payloads(server_value: str):
    payloads = []
    if not server_value:
        return payloads

    try:
        outer = b64d(server_value)
    except Exception:
        outer = server_value

    for candidate in [outer, outer.strip()]:
        if candidate and candidate not in payloads:
            payloads.append(candidate)

    normalized = outer.strip()
    if normalized:
        try:
            inner = base64.b64decode(normalized).decode("utf-8", errors="ignore")
            if inner and inner not in payloads:
                payloads.append(inner)
        except Exception:
            pass

    return payloads


def extract_dailymotion_video_id(payloads) -> str:
    if isinstance(payloads, str):
        payloads = [payloads]

    patterns = [
        r'dailymotion\.com/(?:embed/)?video/([A-Za-z0-9_-]+)',
        r'dailymotion\.com/player/metadata/video/([A-Za-z0-9_-]+)',
        r'[?&]video=([A-Za-z0-9_-]+)',
        r'["\']videoId["\']\s*[:=]\s*["\']([A-Za-z0-9_-]+)',
        r'["\']dm[_-]?id["\']\s*[:=]\s*["\']([A-Za-z0-9_-]+)',
    ]

    for payload in payloads or []:
        if not payload:
            continue
        for pattern in patterns:
            match = re.search(pattern, payload, re.IGNORECASE)
            if match:
                return match.group(1)

    return ""


def extract_matching_url(payloads, keyword: str) -> str:
    if isinstance(payloads, str):
        payloads = [payloads]

    patterns = [
        rf'https?://[^"\'>\s]*{re.escape(keyword)}[^"\'>\s]*',
        rf'//[^"\'>\s]*{re.escape(keyword)}[^"\'>\s]*',
    ]

    for payload in payloads or []:
        if not payload:
            continue
        for pattern in patterns:
            match = re.search(pattern, payload, re.IGNORECASE)
            if match:
                url = match.group(0).strip()
                return "https:" + url if url.startswith("//") else url

    return ""


def build_animexin_series_candidate(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ""

    path = parsed.path.rstrip("/")
    cleaned_path = re.sub(r'-episode-\d+[^/]*$', '', path, flags=re.IGNORECASE)
    if cleaned_path and cleaned_path != path:
        return f"{parsed.scheme}://{parsed.netloc}{cleaned_path}/"
    return ""


def extract_animexin_series_url(page_url: str, soup: BeautifulSoup, title: str = "") -> str:
    candidates = []
    base_host = urlparse(page_url).netloc

    def add_candidate(href: str):
        if not href:
            return
        normalized = urljoin(page_url, href.strip())
        host = urlparse(normalized).netloc
        if base_host and host and host != base_host:
            return
        if normalized not in candidates:
            candidates.append(normalized)

    for link in soup.select("a[href]"):
        text = link.get_text(" ", strip=True).lower()
        if "all episodes" in text:
            add_candidate(link.get("href", ""))

    add_candidate(build_animexin_series_candidate(page_url))

    clean_title = re.sub(r'\bepisode\b.*$', '', title, flags=re.IGNORECASE).strip(" -")
    title_hint = clean_title[:12].lower() if clean_title else ""

    for link in soup.select("a[href]"):
        href = link.get("href", "")
        text = link.get_text(" ", strip=True)
        text_lower = text.lower()

        if "/anime/" in href:
            add_candidate(href)

        if title_hint and title_hint in text_lower:
            add_candidate(href)

    for candidate in candidates:
        if candidate.rstrip("/") == page_url.rstrip("/"):
            continue
        if re.search(r'-episode-\d+', urlparse(candidate).path, re.IGNORECASE):
            continue
        return candidate

    return ""


def load_animexin_episode_page(url: str):
    html = fetch_animexin_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h1.entry-title")
    title = title_el.get_text(" ", strip=True) if title_el else ""

    ep_elements = soup.select(
        ".eplister ul li, "
        ".episodelist ul li, "
        "ul.clstyle li"
    )

    if not ep_elements:
        series_url = extract_animexin_series_url(url, soup, title)

        if series_url:
            print(
                f"DEBUG: No episode list on {url}. "
                f"Retrying series page -> {series_url}"
            )

            html = fetch_animexin_html(series_url)
            soup = BeautifulSoup(html, "html.parser")

            title_el = soup.select_one("h1.entry-title")
            title = (
                title_el.get_text(" ", strip=True)
                if title_el
                else title
            )

            ep_elements = soup.select(
                ".eplister ul li, "
                ".episodelist ul li, "
                "ul.clstyle li"
            )

            url = series_url

    print("EPISODE COUNT:", len(ep_elements))

    return url, title, ep_elements

# -------------------------------
# HELPER: BRUTE FORCE EXTRACTOR
# -------------------------------
def extract_tca_data(url):
    print(f"DEBUG: Scraper scanning: {url}")
    try:
        domain = url.split("/")[2]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://{domain}/",
            "Origin": f"https://{domain}"
        }
        
        r = requests.get(url, headers=headers, timeout=20)
        html = r.text
        
        # Decrypt VidHide/Packed JS if present
        if "eval(function" in html:
            try:
                html = jsbeautifier.beautify(html)
            except: pass

        stream_link = ""
        sub_url = ""
        duration_str = ""

        # 1. Video Extraction
        file_matches = re.findall(r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html)
        if file_matches:
            stream_link = file_matches[0]
        else:
            m3u8_match = re.search(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html)
            if m3u8_match:
                stream_link = m3u8_match.group(1)

        if stream_link:
            stream_link = stream_link.replace('\\/', '/')
            print(f"DEBUG: Found Video -> {stream_link}")
            
            # --- DURATION CALCULATION (Updated for Master Playlists) ---
            try:
                # A. Fetch the M3U8 file
                m3u_resp = requests.get(stream_link, headers=headers, timeout=10)
                if m3u_resp.status_code == 200:
                    m3u_text = m3u_resp.text
                    
                    # B. Check if it's a Master Playlist (contains multiple qualities)
                    if "#EXT-X-STREAM-INF" in m3u_text:
                        # We need to fetch one of the sub-playlists to get duration
                        lines = m3u_text.splitlines()
                        for line in lines:
                            if line.strip() and not line.startswith("#"):
                                # Found a URL to a chunklist
                                sub_url_list = line
                                if not sub_url_list.startswith("http"):
                                    sub_url_list = urljoin(stream_link, sub_url_list)
                                
                                # Fetch the actual media playlist
                                sub_resp = requests.get(sub_url_list, headers=headers, timeout=10)
                                if sub_resp.status_code == 200:
                                    m3u_text = sub_resp.text # Replace text with the media list
                                break
                    
                    # C. Sum up the seconds
                    total_seconds = 0.0
                    for line in m3u_text.splitlines():
                        if line.startswith("#EXTINF:"):
                            try:
                                # Line format is like: #EXTINF:10.000,
                                sec = float(line.split(":")[1].split(",")[0])
                                total_seconds += sec
                            except: pass
                    
                    # D. Format Time
                    if total_seconds > 0:
                        m, s = divmod(int(total_seconds), 60)
                        h, m = divmod(m, 60)
                        if h > 0:
                            duration_str = f"{h}h {m}m {s}s"
                        else:
                            duration_str = f"{m}m {s}s"
                        print(f"DEBUG: Calculated Duration -> {duration_str}")
            except Exception as e:
                print(f"DEBUG: Duration Calc Failed: {e}")

        # 2. Subtitle Extraction
        vtt_matches = re.findall(r'["\']([^"\']+\.vtt)["\']', html)
        for vtt in vtt_matches:
            if not vtt.startswith("http"):
                vtt = urljoin(url, vtt)
            sub_url = vtt
            if 'eng' in vtt.lower() or 'english' in vtt.lower():
                break 

        return stream_link, sub_url, duration_str

    except Exception as e:
        print(f"DEBUG: Extraction Error: {e}")
        return "", "", ""
# -------------------------------
# STREAM ROUTE (UPDATED)
# -------------------------------
@app.route("/stream", methods=["POST"])
def stream():
    # 1. Get Params
    token = request.form.get("episode_token", "").strip()
    subtitle_pref = (request.form.get("subtitle", "") or "").lower().strip()
    server_value = request.form.get("server", "").strip()
    
    # 2. Filename context. The browser sends this through every step.
    raw_title = (request.form.get("title") or "").strip()
    raw_ep = (request.form.get("episode") or "").strip()

    # Server-side fallback: recover missing context from the episode URL.
    # This prevents a cached/old JavaScript file from ever producing "Anime .srt".
    try:
        episode_url = b64d(token) if token else ""
    except Exception:
        episode_url = ""

    if not raw_ep and episode_url:
        ep_match = re.search(
            r"-episode-(\d+(?:\.\d+)?)\b",
            episode_url,
            re.IGNORECASE
        )
        if ep_match:
            raw_ep = ep_match.group(1)

    if (not raw_title or raw_title.lower() == "anime") and episode_url:
        slug = urlparse(episode_url).path.strip("/")
        slug = re.sub(
            r"-episode-\d+(?:\.\d+)?.*$",
            "",
            slug,
            flags=re.IGNORECASE
        )
        fallback_title = re.sub(r"[-_]+", " ", slug).strip()
        if fallback_title:
            raw_title = fallback_title.title()

    if not raw_title:
        raw_title = "Anime"

    safe_title = re.sub(r'[\\/*?:"<>|]', "", raw_title).strip() or "Anime"
    safe_ep = re.sub(r'[\\/*?:"<>|]', "", raw_ep).strip()
    if safe_ep and not safe_ep.lower().startswith("ep"):
        safe_ep = f"Ep-{safe_ep}"

    custom_filename = f"{safe_title} {safe_ep}.srt".strip()
    print("STREAM TITLE RECEIVED:", repr(request.form.get("title")))
    print("STREAM EPISODE RECEIVED:", repr(request.form.get("episode")))
    print("FINAL SUBTITLE FILENAME:", custom_filename)

    # 3. Init Variables
    stream_link = ""
    subs = []
    subs_map = {}
    duration_str = ""
    chosen_sub = None
    is_animexin = False
    dm_id = ""
    server_payloads = decode_server_payloads(server_value)
    decoded_server = server_payloads[0] if server_payloads else ""
    has_dailymotion_payload = any("dailymotion" in payload.lower() for payload in server_payloads)

    # ==========================================
    # === 1. RUMBLE LOGIC (COMPLETELY SEPARATE) ===
    # ==========================================
    try:
        rumble_payload = extract_matching_url(server_payloads, "rumble.com")
        rumble_match = re.search(r'src=["\']([^"\']*rumble\.com/embed/[^"\']+)["\']', decoded_server, re.IGNORECASE)

        if rumble_match:
            rumble_payload = rumble_match.group(1)

        if rumble_payload:
            if rumble_payload.startswith("//"):
                rumble_payload = "https:" + rumble_payload

            stream_link = rumble_payload
            subs = extract_rumble_subs(rumble_payload)
            subs_map = {s["lang"].lower(): s["url"] for s in subs}
    except Exception as e:
        print("Rumble Error in /stream:", e)

    
    # === 1. ANIMEXIN LOGIC (Dailymotion) ===
    try:
        vid_id = extract_dailymotion_video_id(server_payloads)
        direct_dm_url = extract_matching_url(server_payloads, "dailymotion")

        if has_dailymotion_payload:
            is_animexin = True
        if vid_id:
            dm_id = vid_id

            meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"
            dm_headers = HEADERS.copy()
            dm_headers["Referer"] = f"https://www.dailymotion.com/embed/video/{vid_id}"

            meta = requests.get(meta_url, headers=dm_headers, timeout=20).json()

            if "duration" in meta:
                duration_str = format_time(meta["duration"])

            if "subtitles" in meta and "data" in meta["subtitles"]:
                for lang_code, info in meta["subtitles"]["data"].items():
                    label = info.get("label", lang_code)
                    urls = info.get("urls", [])

                    if urls:
                        subs.append({
                            "lang": lang_code,
                            "name": label,
                            "url": b64e(urls[0])
                        })

            if not subs and "qualities" in meta:
                master_url = ""
                if "auto" in meta["qualities"]:
                    for s in meta["qualities"]["auto"]:
                        if s.get("type") == "application/x-mpegURL":
                            master_url = s["url"]
                            break
                if not master_url:
                    for q, streams in meta["qualities"].items():
                        for st in streams:
                            if st.get("type") == "application/x-mpegURL":
                                master_url = st["url"]
                                break
                        if master_url:
                            break

                if master_url:
                    found = extract_subs_from_m3u8(master_url)
                    if found:
                        subs.extend(found)

            subs_map = {s["lang"].lower(): s["url"] for s in subs}
            stream_link = f"https://www.dailymotion.com/embed/video/{dm_id}?autoplay=1"
        elif direct_dm_url:
            stream_link = direct_dm_url

    except Exception as e:
        print("Animexin Error:", e)

    # === 2. TOP CHINESE ANIME LOGIC (VidHide) ===
    if not is_animexin:
        try:
            tca_url = ""
            raw_val = b64d(server_value)
            
            if raw_val.strip().startswith("PElG") or raw_val.strip().startswith("PGlm"):
                try:
                    raw_val = base64.b64decode(raw_val).decode("utf-8", errors="ignore")
                except: pass

            src_match = re.search(r'src=["\']([^"\']+)["\']', raw_val, re.IGNORECASE)
            if src_match:
                tca_url = src_match.group(1)
            elif "http" in raw_val or raw_val.strip().startswith("//"):
                tca_url = raw_val

            if tca_url and tca_url.startswith("//"):
                tca_url = "https:" + tca_url

            if tca_url:
                s_link, s_sub, s_dur = extract_tca_data(tca_url)
                if s_link: stream_link = s_link
                if s_dur: duration_str = s_dur
                if s_sub:
                    subs_map["english"] = b64e(s_sub)
                    chosen_sub = subs_map["english"]

        except Exception as e:
            print(f"DEBUG: TCA Logic Crashed: {e}")

    # === 3. SUBTITLE SELECTION ===
    if not chosen_sub and subtitle_pref and subs_map:
        if subtitle_pref in subs_map:
            chosen_sub = subs_map[subtitle_pref]
        else:
            for lang, tok in subs_map.items():
                if lang.split("-")[0] == subtitle_pref.split("-")[0]:
                    chosen_sub = tok
                    break

    return render_template("partials/stream.html", 
                           link=stream_link, 
                           sub=chosen_sub, 
                           duration=duration_str, 
                           dm_id=dm_id,
                           filename=custom_filename)
    
# -------------------------------
# HOME PAGE
# -------------------------------
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# -------------------------------
# SEARCH RESULTS
# -------------------------------
@app.route("/search", methods=["POST"])
def search():
    query = request.form.get("query", "").strip()
    results = []

    if query:
        search_url = f"{BASE_URL}/?s={query}"
        try:
            html = fetch_animexin_html(search_url)
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            print("SEARCH ANIMEXIN ERROR:", e)
            return render_template("partials/results.html", results=[])

        for post in soup.select("article.bs"):
            a = post.select_one("a")
            link = a["href"] if a and a.has_attr("href") else ""
            title_el = post.select_one(".eggtitle")
            ep_el = post.select_one(".eggepisode")
            img_el = post.select_one("img")

            title = title_el.get_text(strip=True) if title_el else "No Title"
            episode = f" {ep_el.get_text(strip=True)}" if ep_el else ""
            img = ""

            if img_el:
                img = (
                    img_el.get("src")
                    or img_el.get("data-src")
                    or img_el.get("data-lazy-src")
                    or img_el.get("data-original")
                    or ""
                )

                img = urljoin(BASE_URL, img)

            results.append({
                "title": (title + episode).strip(),
                "img": img,
                "post_token": b64e(link)
            })

    return render_template("partials/results.html", results=results)


# -------------------------------
# LATEST RELEASE (home cards)
# -------------------------------
@app.route("/latest", methods=["GET"])
def latest():
    page = int((request.args.get("page") or 1))
    url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"

    try:
        html = fetch_animexin_html(url)
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        print("LATEST ANIMEXIN ERROR:", e)
        return render_template(
            "partials/latest.html",
            results=[],
            next_page=None,
            error=str(e)
        )

    results = []

    cards = soup.select("div.listupd.normal div.excstf article.bs")

    if not cards:
        cards = soup.select("div.listupd article.bs")

    if not cards:
        cards = soup.select("div.excstf article.bs")

    if not cards:
        cards = soup.select("article.bs")

    print("LATEST CARD COUNT:", len(cards))

    for art in cards:
        a = art.select_one("a[href]")
        if not a:
            continue

        link = urljoin(BASE_URL, a.get("href", ""))

        img_el = a.select_one("img")
        title_el = a.select_one(".eggtitle")
        ep_el = a.select_one(".eggepisode")
        h2_el = art.select_one(".tt h2")

        title = ""

        if title_el:
            title = title_el.get_text(" ", strip=True)

        if ep_el:
            title = (
                title + " " + ep_el.get_text(" ", strip=True)
            ).strip()

        if not title and h2_el:
            title = h2_el.get_text(" ", strip=True)

        img = ""

        if img_el:
            img = (
                img_el.get("src")
                or img_el.get("data-src")
                or img_el.get("data-lazy-src")
                or img_el.get("data-original")
                or ""
            )

            img = urljoin(BASE_URL, img)

        if link and title:
            results.append({
                "title": title,
                "img": img,
                "post_token": b64e(link)
            })

    next_page = None
    nxt = soup.select_one(
        "div.hpage a.r[href], "
        "a.next.page-numbers[href], "
        ".pagination a.next[href]"
    )

    if nxt and nxt.get("href"):
        match = re.search(r"/page/(\d+)/", nxt["href"])

        if match:
            next_page = int(match.group(1))
        else:
            next_page = page + 1

    print("LATEST RESULT COUNT:", len(results))
    print("LATEST NEXT PAGE:", next_page)

    return render_template(
        "partials/latest.html",
        results=results,
        next_page=next_page,
        error=None
    )

# -------------------------------
# EPISODES LIST (FIXED: Targeted Redirect)
# -------------------------------
@app.route("/episodes", methods=["POST"])
def episodes():
    token = request.form.get("anime_id", "")
    url = b64d(token) if token else ""

    episodes = []
    ep_elements = []
    title = "Anime"

    if not url:
        return render_template(
            "partials/episodes.html",
            eps=[],
            anime_id=token,
            title=title
        )

    try:
        # This line must remain here.
        # It creates raw_title and ep_elements.
        resolved_url, raw_title, ep_elements = (
            load_animexin_episode_page(url)
        )

        print("RESOLVED ANIME URL:", resolved_url)
        print("RAW ANIME TITLE:", raw_title)
        print("EPISODE ELEMENT COUNT:", len(ep_elements))

        # Remove episode number and subtitle-language text.
        # Example:
        # Walking the Way all alone Episode 16 Indonesia, English Sub
        # becomes:
        # Walking the Way all alone
        title = re.sub(
            r"\s+(?:episode|ep)\s*[-:]?\s*"
            r"\d+(?:\.\d+)?\b.*$",
            "",
            raw_title or "",
            flags=re.IGNORECASE
        ).strip(" -")

        # Fallback: create the anime title from its URL.
        if not title:
            title_url = resolved_url or url
            slug = urlparse(title_url).path.strip("/")

            slug = re.sub(
                r"-episode-\d+(?:\.\d+)?.*$",
                "",
                slug,
                flags=re.IGNORECASE
            )

            title = re.sub(r"[-_]+", " ", slug).strip().title()

        if not title:
            title = "Anime"

        print("CLEAN ANIME TITLE:", title)

        for li in ep_elements:
            a = li.select_one("a[href]")

            if not a:
                continue

            href = urljoin(
                BASE_URL,
                a.get("href", "")
            )

            full_text = li.get_text(" ", strip=True)
            num_text = ""

            # First try number-related HTML elements.
            num_element = li.select_one(
                ".epl-num, "
                ".ep-num, "
                ".episode-number"
            )

            if num_element:
                number_match = re.search(
                    r"\d+(?:\.\d+)?",
                    num_element.get_text(" ", strip=True)
                )

                if number_match:
                    num_text = number_match.group(0)

            # Most reliable method: extract number from episode URL.
            if not num_text:
                number_match = re.search(
                    r"-episode-(\d+(?:\.\d+)?)\b",
                    href,
                    re.IGNORECASE
                )

                if number_match:
                    num_text = number_match.group(1)

            # Fallback: Episode 16, Ep 16 or Eps 16.
            if not num_text:
                number_match = re.search(
                    r"\b(?:episode|eps?)\s*[-:#]?\s*"
                    r"(\d+(?:\.\d+)?)\b",
                    full_text,
                    re.IGNORECASE
                )

                if number_match:
                    num_text = number_match.group(1)

            # Final fallback: number at beginning of text.
            if not num_text:
                number_match = re.match(
                    r"\s*(\d+(?:\.\d+)?)\b",
                    full_text
                )

                if number_match:
                    num_text = number_match.group(1)

            if not num_text:
                print(
                    "EPISODE NUMBER NOT FOUND:",
                    full_text[:200],
                    href
                )
                continue

            ep_title_element = li.select_one(
                ".epl-title, "
                ".ep-title, "
                ".episode-title"
            )

            ep_title_text = (
                ep_title_element.get_text(" ", strip=True)
                if ep_title_element
                else ""
            )

            episodes.append({
                "num": num_text,

                # Complete anime name received from the backend
                "anime_title": title,

                # Button text:
                # Walking the Way all alone Ep-16
                "button_name": f"{title} Ep-{num_text}",

                "episode_token": b64e(href)
            })

            print(
                "PARSED EPISODE:",
                num_text,
                "| TITLE:",
                title
            )

    except Exception as e:
        print("Error loading episodes:", repr(e))

    return render_template(
        "partials/episodes.html",
        eps=episodes,
        anime_id=token,
        title=title
    )

@app.route("/process_all", methods=["POST"])
def process_all():
    token = request.form.get("anime_id", "")
    url = b64d(token) if token else ""
    if not url:
        return "Invalid anime ID"

    episodes = []
    _, _, ep_elements = load_animexin_episode_page(url)
    for li in ep_elements:
        a = li.select_one("a[href]")

        if not a:
            continue

        href = urljoin(BASE_URL, a.get("href", ""))
        full_text = li.get_text(" ", strip=True)

        number_match = re.search(
            r"-episode-(\d+(?:\.\d+)?)\b",
            href,
            re.IGNORECASE
        )

        if not number_match:
            number_match = re.search(
                r"\b(?:episode|eps?)\s*[-:#]?\s*(\d+(?:\.\d+)?)\b",
                full_text,
                re.IGNORECASE
            )

        if not number_match:
            number_match = re.match(
                r"\s*(\d+(?:\.\d+)?)\b",
                full_text
            )

        if not number_match:
            continue

        episodes.append({
            "num": number_match.group(1),
            "url": href
        })

    return render_template("partials/all_streams.html", eps=episodes)

# -------------------------------
# GET AVAILABLE SERVERS FOR EPISODE
# -------------------------------
@app.route("/get_servers", methods=["POST"])
def get_servers():
    token = request.form.get("episode_token", "").strip()
    posted_title = (request.form.get("title") or "").strip()
    posted_episode = (request.form.get("episode") or "").strip()
    servers = []
    soup = None

    try:
        url = b64d(token)
        html = fetch_animexin_html(url)
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        print("SERVER LIST ANIMEXIN ERROR:", e)
        anime_title, episode_num = recover_episode_context(
            token, posted_title, posted_episode
        )
        return render_template(
            "partials/servers.html",
            servers=[],
            episode_token=token,
            anime_title=anime_title,
            episode_num=episode_num
        )

    # Never depend only on browser globals. Recover context from the page/token.
    anime_title, episode_num = recover_episode_context(
        token, posted_title, posted_episode, soup
    )

    for option in soup.select(
        "select.mirror option, "
        "select[name='mirror'] option, "
        ".mirror option"
    ):
        label = option.get_text(strip=True)
        encoded = option.get("value", "")
        if encoded:
            servers.append({"label": label, "value": b64e(encoded)})

    print("GET_SERVERS FORM:", request.form.to_dict(flat=True))
    print("SERVER CONTEXT:", anime_title, "| EP:", episode_num)
    return render_template(
        "partials/servers.html",
        servers=servers,
        episode_token=token,
        anime_title=anime_title,
        episode_num=episode_num
    )

# -------------------------------
# GET SUBTITLES FOR SELECTED SERVER
# -------------------------------
@app.route("/get_subtitles", methods=["POST"])
def get_subtitles():
    ep_token = request.form.get("episode_token", "").strip()
    server_value = request.form.get("server", "").strip()
    posted_title = (request.form.get("title") or "").strip()
    posted_episode = (request.form.get("episode") or "").strip()
    anime_title, episode_num = recover_episode_context(
        ep_token, posted_title, posted_episode
    )
    subs = []

    try:
        payloads = decode_server_payloads(server_value)
        vid_id = extract_dailymotion_video_id(payloads)
        if vid_id:
            meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"

            dm_headers = HEADERS.copy()
            dm_headers["Referer"] = f"https://www.dailymotion.com/embed/video/{vid_id}"

            meta = requests.get(meta_url, headers=dm_headers, timeout=20).json()

            if "subtitles" in meta and "data" in meta["subtitles"]:
                for lang_code, info in meta["subtitles"]["data"].items():
                    label = info.get("label", lang_code)
                    urls = info.get("urls", [])
                    if urls:
                        subs.append({
                            "lang": lang_code,
                            "name": label,
                            "url": b64e(urls[0])
                        })

            if not subs and "qualities" in meta:
                target_streams = []
                if "auto" in meta["qualities"]:
                    target_streams.extend(meta["qualities"]["auto"])
                for quality, streams in meta["qualities"].items():
                    if quality != "auto":
                        target_streams.extend(streams)

                for stream_data in target_streams:
                    if stream_data.get("type") == "application/x-mpegURL":
                        found = extract_subs_from_m3u8(stream_data["url"])
                        if found:
                            subs = found
                            break

    except Exception as e:
        print(f"Error in get_subtitles: {e}")

    print("GET_SUBTITLES FORM:", request.form.to_dict(flat=True))
    print("SUBTITLE CONTEXT:", anime_title, "| EP:", episode_num)
    return render_template(
        "partials/subtitles.html",
        subtitles=subs,
        ep_token=ep_token,
        server_value=server_value,
        anime_title=anime_title,
        episode_num=episode_num
    )

# -------------------------------
# SUBTITLE EXTRACTOR
# -------------------------------
def extract_subs_from_m3u8(m3u8_url: str):
    subs = []
    try:
        r = requests.get(m3u8_url, headers=HEADERS, timeout=20)
        text = r.text

        for line in text.splitlines():
            if line.startswith("#EXT-X-MEDIA") and "TYPE=SUBTITLES" in line:
                attrs = dict(re.findall(r'([A-Z0-9\-]+)="(.*?)"', line))
                uri = attrs.get("URI")
                if uri:
                    sub_m3u8 = urljoin(m3u8_url, uri)
                    lang = attrs.get("LANGUAGE") or attrs.get("ASSOC-LANGUAGE") or attrs.get("NAME") or "unknown"
                    name = attrs.get("NAME") or lang
                    subs.append({"lang": lang, "name": name, "url": b64e(sub_m3u8)})

        for line in text.splitlines():
            if line and not line.startswith("#") and ".vtt" in line:
                vtt_url = urljoin(m3u8_url, line.strip())
                subs.append({"lang": "unknown", "name": vtt_url.rsplit("/", 1)[-1], "url": b64e(vtt_url)})

        seen = set()
        unique = []
        for s in subs:
            if s["url"] not in seen:
                unique.append(s)
                seen.add(s["url"])
        return unique

    except Exception as e:
        print("Error extracting subs:", e)
        return []

# -------------------------------
# DOWNLOAD SUB AS .SRT (FIXED)
# -------------------------------
def _fetch_text(scraper, url, headers, timeout=30):
    r = scraper.get(url, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {url}")
    txt = r.text or ""
    if not txt.strip():
        try:
            txt = r.content.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return txt

@app.route("/download_sub")
def download_sub():
    token = request.args.get("url", "").strip()
    fname = (request.args.get("filename") or "subtitle.srt").strip()

    if not token:
        return "No URL provided", 400

    # Keep the real Unicode filename while removing only unsafe header/path characters.
    fname = re.sub(r'[\r\n\x00-\x1f\x7f]', "", fname)
    fname = re.sub(r'[\\/:*?"<>|]', "", fname).strip() or "subtitle.srt"
    if not fname.lower().endswith((".srt", ".vtt")):
        fname += ".srt"

    ascii_fname = fname.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_fname:
        ascii_fname = "subtitle.srt"

    content_disposition = (
        f'attachment; filename="{ascii_fname}"; '
        f"filename*=UTF-8''{quote(fname)}"
    )

    try:
        url = b64d(token)
    except Exception:
        return "Invalid token", 400

    try:
        # SSL Adapter Setup
        session = cloudscraper.create_scraper()
        adapter = CustomSSLAdapter()
        session.mount("https://", adapter)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
        }

        if "dailymotion.com" in url:
            headers["Origin"] = "https://www.dailymotion.com"
            headers["Referer"] = "https://www.dailymotion.com/"

        def fetch_real_sub(target_url, depth=0):
            if depth > 3: return "" 
            resp = session.get(target_url, headers=headers, timeout=20, verify=False)
            if resp.status_code != 200:
                return ""
            text = resp.text.strip()
            if text.startswith("#EXTM3U"):
                lines = [urljoin(target_url, l.strip()) for l in text.splitlines() if l.strip() and not l.startswith("#")]
                for l in lines:
                    if l.lower().endswith(".vtt") or l.lower().endswith(".webvtt"):
                        return fetch_real_sub(l, depth + 1)
                if lines: return fetch_real_sub(lines[0], depth + 1)
            return text

        vtt_text = fetch_real_sub(url)

        if not vtt_text or len(vtt_text) < 20:
            return "No valid subtitle content found.", 502

        # Convert to SRT (using your fixed vtt_to_srt function)
        srt_text = vtt_to_srt(vtt_text)
        
        # Fallback to VTT if conversion fails
        if not srt_text.strip():
            if not fname.endswith(".vtt"): 
                fname = fname.rsplit('.', 1)[0] + ".vtt"
                
            return Response(
                vtt_text,
                mimetype="application/octet-stream",
                headers={"Content-Disposition": content_disposition}
            )

        # Return SRT with Safe Filename
        return Response(
            srt_text,
            mimetype="application/octet-stream",
            headers={"Content-Disposition": content_disposition}
        )

    except Exception as e:
        print("Subtitle download error:", e)
        return f"Error: {e}", 500


# -------------------------------
# VTT -> SRT CONVERTER (ROBUST FIX)
# -------------------------------
# -------------------------------
# VTT -> SRT CONVERTER (FINAL FIX)
# -------------------------------
def vtt_to_srt(vtt_text: str) -> str:
    lines = vtt_text.splitlines()
    out, buf, idx = [], [], 1

    def normalize_timestamp(ts):
        ts = ts.replace('.', ',')
        ts = ts.split(" ")[0].strip()
        if ts.count(':') == 1:
            return "00:" + ts
        return ts

    def flush():
        nonlocal idx, buf, out
        if not buf:
            return
        t_idx = -1
        # Locate timestamp line
        for i, l in enumerate(buf):
            if "-->" in l:
                t_idx = i
                break
        if t_idx == -1:
            buf = []
            return
        
        # Normalize Timestamp
        raw_time_line = buf[t_idx]
        if "-->" in raw_time_line:
            start, end = raw_time_line.split("-->")
            start = normalize_timestamp(start.strip())
            end = normalize_timestamp(end.strip())
            time_line = f"{start} --> {end}"
        else:
            time_line = raw_time_line

        # === THE FIX IS HERE ===
        # Only take lines AFTER the timestamp (i > t_idx).
        # Previously (i != t_idx) included the ID line (i < t_idx) as text.
        text_lines = [l for i, l in enumerate(buf) if i > t_idx and l.strip()]
        
        cleaned_lines = []
        for txt in text_lines:
            txt = txt.strip()
            
            # Clean "Number + \N" artifacts (e.g. "145\N") just in case
            txt = re.sub(r'^\s*\d+\s*\\N', '', txt)
            
            # Convert \N to newlines (Standard SRT format)
            txt = txt.replace(r'\N', '\n')
            
            if txt:
                cleaned_lines.append(txt)

        if cleaned_lines:
            out.append(f"{idx}\n{time_line}\n" + "\n".join(cleaned_lines) + "\n")
            idx += 1
        
        buf = []

    for raw in lines:
        l = raw.rstrip("\n")
        # Filter headers
        if l.startswith(("WEBVTT", "NOTE", "STYLE", "REGION", "Kind:", "Language:")):
            continue
        if not l.strip():
            flush()
        else:
            buf.append(l)
    flush()
    return "\n".join(out).strip() + ("\n" if out else "")


# -------------------------------
# TOP CHINESE ANIME - LATEST
# -------------------------------
@app.route("/latest_tca", methods=["GET"])
def latest_tca():
    page = int((request.args.get("page") or 1))
    # URL structure might differ slightly, usually /page/2/
    url = BASE_URL_TCA if page == 1 else f"{BASE_URL_TCA}/page/{page}/"

    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        # Target the list container. 
        # Based on standard themes, it's often 'div.listupd article.bs' or similar.
        for art in soup.select("div.listupd article.bs"):
            a = art.select_one("a[href]")
            if not a: continue
            
            link = a["href"]
            img_el = art.select_one("img")
            title_el = art.select_one(".tt") or art.select_one(".eggtitle") 
            ep_el = art.select_one(".eggepisode") or art.select_one(".epx")

            title = title_el.get_text(strip=True) if title_el else "Unknown"
            ep = ep_el.get_text(strip=True) if ep_el else ""
            
            # Handle lazy loading images if present (data-src)
            img = ""
            if img_el:
                img = img_el.get("src") or img_el.get("data-src") or ""

            results.append({
                "title": f"{title} {ep}".strip(),
                "img": img,
                "post_token": b64e(link),
                "source": "tca" # Marker to know this is from TopChinese
            })

        return render_template("partials/latest.html", results=results, next_page=page+1, source="tca")
    except Exception as e:
        print("TCA Error:", e)
        return f"<p>Error loading TopChineseAnime: {e}</p>"

# -------------------------------
# TOP CHINESE ANIME - SEARCH
# -------------------------------
@app.route("/search_tca", methods=["POST"])
def search_tca():
    query = request.form.get("query", "").strip()
    results = []

    if query:
        # Search URL structure: /?s=query
        search_url = f"{BASE_URL_TCA}/?s={query}"
        try:
            r = requests.get(search_url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")

            for post in soup.select("article.bs"):
                a = post.select_one("a")
                link = a["href"] if a else ""
                
                title_el = post.select_one(".tt") or post.select_one(".eggtitle")
                ep_el = post.select_one(".eggepisode") or post.select_one(".epx")
                img_el = post.select_one("img")

                title = title_el.get_text(strip=True) if title_el else "No Title"
                ep = f" {ep_el.get_text(strip=True)}" if ep_el else ""
                img = img_el.get("src") or img_el.get("data-src") or "" if img_el else ""

                results.append({
                    "title": (title + ep).strip(),
                    "img": img,
                    "post_token": b64e(link),
                    "source": "tca"
                })
        except Exception as e:
            print("Search TCA Error:", e)

    return render_template("partials/results.html", results=results)

# -------------------------------
# RUN APP
# -------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
