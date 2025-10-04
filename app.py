import base64
from flask import Flask, render_template, request, Response
import requests
from bs4 import BeautifulSoup
import re, json
from urllib.parse import urljoin

app = Flask(__name__)

BASE_URL = "https://animexin.dev"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")

def b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("utf-8")).decode("utf-8")


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


# -------------------------------
# STREAM LINK + SUBTITLES
# -------------------------------
@app.route("/stream", methods=["POST"])
def stream():
    # we now receive EPISODE TOKEN, not anime id
    token = request.form.get("episode_token", "").strip()
    subtitle_pref = (request.form.get("subtitle", "") or "").lower().strip()
    server_choice_raw = (request.form.get("server", "") or "").strip()

    def norm(s: str) -> str:
        # normalize for robust comparisons
        return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

    server_choice = norm(server_choice_raw)
    stream_link = ""
    subs_map = {}

    url = b64d(token) if token else ""
    if not url:
        return render_template("partials/stream.html", link="", sub=None)

    r = requests.get(url, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    mirrors = soup.select("select.mirror option")
    if not mirrors:
        # no <select class="mirror"> found on this episode page
        return render_template("partials/stream.html", link="", sub=None)

    picked_src = None
    picked_label = None

    # 1st pass: try to match user's chosen server (normalized)
    for opt in mirrors:
        label = opt.get_text(strip=True)
        encoded = opt.get("value", "")
        if not encoded:
            continue

        try:
            decoded_html = base64.b64decode(encoded).decode("utf-8", errors="ignore")
            inner = BeautifulSoup(decoded_html, "html.parser")
            iframe = inner.find("iframe")
            src = iframe.get("src") or iframe.get("data-src") if iframe else None
            if not src:
                continue

            if server_choice and server_choice not in norm(label):
                continue  # this mirror doesn't match the chosen server

            picked_src = src
            picked_label = label
            break
        except Exception as e:
            print("Mirror decode error:", e)
            continue

    # 2nd pass (fallback): first working mirror if none matched
    if not picked_src:
        for opt in mirrors:
            encoded = opt.get("value", "")
            if not encoded:
                continue
            try:
                decoded_html = base64.b64decode(encoded).decode("utf-8", errors="ignore")
                inner = BeautifulSoup(decoded_html, "html.parser")
                iframe = inner.find("iframe")
                src = iframe.get("src") or iframe.get("data-src") if iframe else None
                if src:
                    picked_src = src
                    picked_label = opt.get_text(strip=True)
                    break
            except Exception:
                continue

    if not picked_src:
        # still nothing
        return render_template("partials/stream.html", link="", sub=None)

    # If Dailymotion embed -> grab the real m3u8 (and subs) from metadata JSON
    try:
        if "dailymotion.com/embed/video/" in picked_src:
            vid_id = picked_src.split("/embed/video/")[-1].split("?")[0]
            meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"
            meta = requests.get(meta_url, headers=HEADERS, timeout=20).json()

            # find the x-mpegURL entry
            if "qualities" in meta:
                for q, streams in meta["qualities"].items():
                    for st in streams:
                        if st.get("type") == "application/x-mpegURL":
                            master_url = st["url"]
                            # Step 1: fetch the master .m3u8
                            m3u8_text = requests.get(master_url, headers=HEADERS, timeout=20).text
            
                            # Step 2: find the first child manifest (real vod*.dmcdn.net)
                            real_url = None
                            for line in m3u8_text.splitlines():
                                line = line.strip()
                                if line and not line.startswith("#") and "dmcdn.net" in line:
                                    real_url = urljoin(master_url, line)
                                    break
            
                            # fallback: keep the master if no child found
                            stream_link = real_url or master_url
            
                            # Step 3: collect subs from master
                            subs = extract_subs_from_m3u8(master_url)
                            subs_map = {s["lang"].lower(): s["url"] for s in subs}
                            break
                    if stream_link:
                        break
        else:
            # Non-Dailymotion: use the iframe URL directly
            stream_link = picked_src
    except Exception as e:
        print("Dailymotion metadata error:", e)

    # choose subtitle: exact match (e.g., 'it') or prefix of lang (e.g., 'it' matches 'it-IT')
    chosen_sub = None
    if subtitle_pref and subs_map:
        # exact
        if subtitle_pref in subs_map:
            chosen_sub = subs_map[subtitle_pref]
        else:
            # try prefix match like 'it' in 'it-IT'
            for lang, tok in subs_map.items():
                if lang.split("-")[0] == subtitle_pref.split("-")[0]:
                    chosen_sub = tok
                    break

    return render_template("partials/stream.html", link=stream_link, sub=chosen_sub)



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
# DOWNLOAD SUB AS .SRT
# -------------------------------
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
        if url.endswith(".m3u8"):
            r = requests.get(url, headers=HEADERS, timeout=20)
            text = r.text
            vtt_url = None
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and ".vtt" in line:
                    vtt_url = urljoin(url, line)
                    break
            if not vtt_url:
                return "No VTT URL found inside subtitle m3u8", 404
            url = vtt_url

        vtt_resp = requests.get(url, headers=HEADERS, timeout=20)
        vtt_resp.raise_for_status()
        srt_text = vtt_to_srt(vtt_resp.text)

        return Response(
            srt_text,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=subtitle.srt"}
        )
    except Exception as e:
        return f"Error: {e}", 500


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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
