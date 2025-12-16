import base64
from flask import Flask, render_template, request, Response
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import cloudscraper

app = Flask(__name__)

BASE_URL = "https://animexin.dev"
BASE_URL_TCA = "https://topchineseanime.xyz"

HEADERS = {"User-Agent": "Mozilla/5.0"}

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


def b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")

def b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("utf-8")).decode("utf-8")

# -------------------------------
# HELPER: BRUTE FORCE EXTRACTOR
# -------------------------------
def extract_tca_data(url):
    print(f"DEBUG: Scraper scanning: {url}")
    try:
        # Use a fake browser header with Referer
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://topchineseanime.xyz/"
        }
        
        r = requests.get(url, headers=headers, timeout=20)
        html = r.text
        
        # 1. BRUTE FORCE SEARCH FOR VIDEO (.m3u8)
        # Finds any string starting with http and ending with .m3u8
        stream_link = ""
        # Regex explanation: http(s):// [anything not quote/space] .m3u8 [optional params]
        m3u8_match = re.search(r'(https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', html)
        
        if m3u8_match:
            stream_link = m3u8_match.group(1)
            # Clean up escape slashes if any (like https:\/\/...)
            stream_link = stream_link.replace('\\/', '/')
            print(f"DEBUG: Found M3U8 -> {stream_link}")
        else:
            # Fallback: Look for .mp4
            mp4_match = re.search(r'(https?://[^\s"\'<>]+?\.mp4[^\s"\'<>]*)', html)
            if mp4_match:
                stream_link = mp4_match.group(1).replace('\\/', '/')
                print(f"DEBUG: Found MP4 -> {stream_link}")

        # 2. BRUTE FORCE SEARCH FOR SUBTITLE (.vtt or .srt)
        sub_url = ""
        # Look for English vtt/srt specifically first
        # Pattern: http...vtt or /path...vtt inside quotes
        
        # Strategy A: Look for explicit .vtt files
        vtt_matches = re.findall(r'(https?://[^\s"\'<>]+?\.vtt)', html)
        if not vtt_matches:
            # Try relative paths: "/something.vtt"
            vtt_matches = re.findall(r'["\'](/[^"\']+\.vtt)["\']', html)
        
        # If we found any VTTs, try to pick the "eng" one
        for vtt in vtt_matches:
            # If relative, make it absolute
            if not vtt.startswith("http"):
                vtt = urljoin(url, vtt)
            
            # If the URL itself contains 'eng' or 'English', verify it
            if 'eng' in vtt.lower() or 'english' in vtt.lower():
                sub_url = vtt
                break
        
        # Strategy B: If no explicit english file found, look for "kind: 'captions'" or "label: 'English'" near a file
        if not sub_url and "English" in html:
            # Try to grab the file property near the word "English"
            # This is risky but often works for JWPlayer/PlayerJS
            # We look for a 100-character window around the word "English"
            idx = html.find("English")
            if idx != -1:
                snippet = html[max(0, idx-200): min(len(html), idx+200)]
                # Find any URL inside this snippet
                link_match = re.search(r'["\'](https?://[^"\']+\.vtt)["\']', snippet)
                if link_match:
                    sub_url = link_match.group(1)

        if sub_url:
            print(f"DEBUG: Found Subtitle -> {sub_url}")
        
        return stream_link, sub_url

    except Exception as e:
        print(f"DEBUG: Extraction Error: {e}")
        return "", ""

# -------------------------------
# STREAM ROUTE (UPDATED)
# -------------------------------
@app.route("/stream", methods=["POST"])
def stream():
    token = request.form.get("episode_token", "").strip()
    subtitle_pref = (request.form.get("subtitle", "") or "").lower().strip()
    server_value = request.form.get("server", "").strip()

    stream_link = ""
    subs_map = {}
    duration_str = ""
    chosen_sub = None
    is_animexin = False

    # === 1. ANIMEXIN LOGIC (Dailymotion Check) ===
    try:
        decoded = base64.b64decode(b64d(server_value)).decode("utf-8", errors="ignore")
        if "dailymotion.com/embed/video/" in decoded:
            is_animexin = True
            inner = BeautifulSoup(decoded, "html.parser")
            iframe = inner.find("iframe")
            src = iframe.get("src") if iframe else None

            if src:
                vid_id = src.split("/embed/video/")[-1].split("?")[0]
                meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"
                meta = requests.get(meta_url, headers=HEADERS, timeout=20).json()

                if "duration" in meta:
                    duration_str = format_time(meta["duration"])

                if "qualities" in meta:
                    for q, streams in meta["qualities"].items():
                        for st in streams:
                            if st.get("type") == "application/x-mpegURL":
                                master_url = st["url"]
                                stream_link = master_url
                                subs = extract_subs_from_m3u8(master_url)
                                subs_map = {s["lang"].lower(): s["url"] for s in subs}
                                break
                        if stream_link: break
    except:
        pass

    # === 2. TOP CHINESE ANIME LOGIC (Fixed) ===
    if not is_animexin:
        try:
            print("DEBUG: Attempting TCA Logic...")
            tca_url = ""
            raw_val = b64d(server_value)
            print(f"DEBUG: Raw Server Value: {raw_val}")

            # FIX: Convert to lowercase for checking, but keep raw_val for parsing
            raw_val_lower = raw_val.lower()

            # Handle Iframe HTML (Case Insensitive)
            if "<iframe" in raw_val_lower:
                soup = BeautifulSoup(raw_val, "html.parser")
                iframe = soup.find("iframe")
                if iframe:
                    tca_url = iframe.get("src")
            
            # Handle Direct URLs
            elif "http" in raw_val_lower or raw_val_lower.startswith("//"):
                tca_url = raw_val

            # Fix missing protocol
            if tca_url and tca_url.startswith("//"):
                tca_url = "https:" + tca_url

            if tca_url:
                stream_link, sub_url = extract_tca_data(tca_url)
                
                if sub_url:
                    subs_map["english"] = b64e(sub_url)
                    chosen_sub = subs_map["english"]
            else:
                print("DEBUG: No valid URL found (Check logic failed).")

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

    return render_template("partials/stream.html", link=stream_link, sub=chosen_sub, duration=duration_str)

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
        r = requests.get(search_url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        for post in soup.select("article.bs"):
            a = post.select_one("a")
            link = a["href"] if a and a.has_attr("href") else ""
            title_el = post.select_one(".eggtitle")
            ep_el = post.select_one(".eggepisode")
            img_el = post.select_one("img")

            title = title_el.get_text(strip=True) if title_el else "No Title"
            episode = f" {ep_el.get_text(strip=True)}" if ep_el else ""
            img = img_el["src"] if img_el and img_el.has_attr("src") else ""

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
    # /latest?page=1 → https://animexin.dev/
    # /latest?page=2 → https://animexin.dev/page/2/
    import re
    page = int((request.args.get("page") or 1))
    url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"

    r = requests.get(url, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    # Matches the exact structure you shared
    for art in soup.select("div.listupd.normal div.excstf article.bs"):
        a = art.select_one("a[href]")
        if not a:
            continue
        link = a["href"]

        img_el = a.select_one("img")
        title_el = a.select_one(".eggtitle")
        ep_el   = a.select_one(".eggepisode")
        h2_el   = art.select_one(".tt h2")

        # Build a clean card title
        title = ""
        if title_el:
            title = title_el.get_text(strip=True)
        if ep_el:
            title = (title + " " + ep_el.get_text(strip=True)).strip()
        if not title and h2_el:
            title = h2_el.get_text(strip=True)

        img = img_el["src"] if img_el and img_el.has_attr("src") else ""

        results.append({
            "title": title,
            "img": img,
            "post_token": b64e(link)
        })

    # Detect "Next" page
    next_page = None
    nxt = soup.select_one("div.hpage a.r[href]")
    if nxt and nxt["href"]:
        m = re.search(r"/page/(\d+)/", nxt["href"])
        next_page = int(m.group(1)) if m else (page + 1)

    return render_template("partials/latest.html",
                           results=results,
                           next_page=next_page)

# -------------------------------
# EPISODES LIST
# -------------------------------
@app.route("/episodes", methods=["POST"])
def episodes():
    token = request.form.get("anime_id", "")
    url = b64d(token) if token else ""
    episodes = []
    title = ""

    if url:
        r = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        h1 = soup.select_one("h1.entry-title")
        if h1:
            title = h1.get_text(strip=True)

        for li in soup.select(".eplister ul li"):
            a = li.select_one("a")
            num = li.select_one(".epl-num")
            ep_title = li.select_one(".epl-title")
            if a and a.has_attr("href"):
                href = a["href"]
                episodes.append({
                    "num": num.get_text(strip=True) if num else "?",
                    "title": ep_title.get_text(strip=True) if ep_title else "",
                    "episode_token": b64e(href)
                })

    return render_template("partials/episodes.html", eps=episodes, anime_id=token, title=title)


@app.route("/process_all", methods=["POST"])
def process_all():
    token = request.form.get("anime_id", "")
    url = b64d(token) if token else ""
    if not url:
        return "Invalid anime ID"

    r = requests.get(url, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    episodes = []
    for li in soup.select(".eplister ul li"):
        a = li.select_one("a")
        num = li.select_one(".epl-num")
        if a and a.has_attr("href"):
            episodes.append({"num": num.get_text(strip=True) if num else "?", "url": a["href"]})

    return render_template("partials/all_streams.html", eps=episodes)

# -------------------------------
# GET AVAILABLE SERVERS FOR EPISODE
# -------------------------------
@app.route("/get_servers", methods=["POST"])
def get_servers():
    token = request.form.get("episode_token", "")
    url = b64d(token)
    servers = []

    r = requests.get(url, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    for option in soup.select("select.mirror option"):
        label = option.get_text(strip=True)
        encoded = option.get("value", "")
        if encoded:
            servers.append({"label": label, "value": b64e(encoded)})

    return render_template("partials/servers.html", servers=servers, episode_token=token)

# -------------------------------
# GET SUBTITLES FOR SELECTED SERVER
# -------------------------------
@app.route("/get_subtitles", methods=["POST"])
def get_subtitles():
    ep_token = request.form.get("episode_token", "")
    server_value = request.form.get("server", "")

    decoded_html = base64.b64decode(b64d(server_value)).decode("utf-8", errors="ignore")
    inner = BeautifulSoup(decoded_html, "html.parser")
    iframe = inner.find("iframe")
    src = iframe.get("src") if iframe else None
    subs = []

    if src and "dailymotion.com/embed/video/" in src:
        vid_id = src.split("/embed/video/")[-1].split("?")[0]
        meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"
        meta = requests.get(meta_url, headers=HEADERS, timeout=20).json()

        if "qualities" in meta:
            for q, streams in meta["qualities"].items():
                for s in streams:
                    if s.get("type") == "application/x-mpegURL":
                        subs = extract_subs_from_m3u8(s["url"])
                        break

    return render_template("partials/subtitles.html", subtitles=subs, ep_token=ep_token, server_value=server_value)

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
    if not token:
        return "No URL provided", 400

    try:
        url = b64d(token)
    except Exception:
        return "Invalid token", 400

    try:
        scraper = cloudscraper.create_scraper()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.dailymotion.com",
            "Referer": "https://www.dailymotion.com/",
        }

        # Recursive subtitle fetcher
        def fetch_real_sub(vtt_url, depth=0):
            """Recursively follow playlists until we reach real subtitle text."""
            if depth > 3:
                return ""  # safety limit

            resp = scraper.get(vtt_url, headers=headers, timeout=20)
            text = resp.text.strip()

            # If file is an m3u8 playlist, go deeper
            if text.startswith("#EXTM3U"):
                lines = [
                    urljoin(vtt_url, l.strip())
                    for l in text.splitlines()
                    if l.strip() and not l.startswith("#")
                ]
                # pick the first .vtt inside or recursively fetch first line
                for l in lines:
                    if l.lower().endswith(".vtt") or l.lower().endswith(".webvtt"):
                        return fetch_real_sub(l, depth + 1)
                # no direct .vtt, maybe another playlist
                if lines:
                    return fetch_real_sub(lines[0], depth + 1)
                return ""
            return text

        # Fetch actual subtitle content (recursively)
        vtt_text = fetch_real_sub(url)

        if not vtt_text or len(vtt_text) < 20:
            return "No valid subtitle content found.", 502

        # Convert to SRT
        srt_text = vtt_to_srt(vtt_text)
        if not srt_text.strip():
            return Response(
                vtt_text,
                mimetype="text/vtt",
                headers={"Content-Disposition": "attachment; filename=subtitle.vtt"}
            )

        return Response(
            srt_text,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=subtitle.srt"}
        )

    except Exception as e:
        print("Subtitle download error:", e)
        return f"Error: {e}", 500

# -------------------------------
# VTT -> SRT CONVERTER
# -------------------------------
def vtt_to_srt(vtt_text: str) -> str:
    lines = vtt_text.splitlines()
    out, buf, idx = [], [], 1

    def flush():
        nonlocal idx, buf, out
        if not buf:
            return
        t_idx = -1
        for i, l in enumerate(buf):
            if "-->" in l:
                t_idx = i
                break
        if t_idx == -1:
            buf = []
            return
        time_line = buf[t_idx].replace(".", ",")
        text_lines = [l for i, l in enumerate(buf) if i != t_idx and l.strip()]
        out.append(f"{idx}\n{time_line}\n" + "\n".join(text_lines) + "\n")
        idx += 1
        buf = []

    for raw in lines:
        l = raw.rstrip("\n")
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
