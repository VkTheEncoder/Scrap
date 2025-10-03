import base64
from flask import Flask, render_template, request, Response
import requests
from bs4 import BeautifulSoup
import re, json
import m3u8
from urllib.parse import urljoin, unquote

app = Flask(__name__)

BASE_URL = "https://animexin.dev"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")

def b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("utf-8")).decode("utf-8")

@app.route("/", methods=["GET", "POST"])
def home():
    results = []
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if query:
            search_url = f"{BASE_URL}/?s={query}"
            r = requests.get(search_url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")

            # Each result card
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
                    "post_url": link,           # original page (kept for 'Original' button)
                    "post_token": b64e(link)    # safe token to pass in querystring
                })

    return render_template("index.html", results=results)

@app.route("/episodes")
def episodes():
    token = request.args.get("u", "")
    url = b64d(token) if token else ""
    episodes = []

    if url:
        r = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        for li in soup.select(".eplister ul li"):
            a = li.select_one("a")
            num = li.select_one(".epl-num")
            title = li.select_one(".epl-title")
            if a and a.has_attr("href"):
                href = a["href"]
                episodes.append({
                    "num": num.get_text(strip=True) if num else "?",
                    "title": title.get_text(strip=True) if title else "",
                    "episode_token": b64e(href)
                })

    return render_template("episodes.html", episodes=episodes)

import re

@app.route("/watch")
def watch():
    token = request.args.get("u", "")
    url = b64d(token) if token else ""
    video_options, subs = [], []

    if url:
        r = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        for option in soup.select("select.mirror option"):
            label = option.get_text(strip=True)
            encoded = option.get("value", "")
            if not encoded:
                continue
            try:
                decoded_html = base64.b64decode(encoded).decode("utf-8", errors="ignore")
                inner = BeautifulSoup(decoded_html, "html.parser")
                iframe = inner.find("iframe")
                src = iframe.get("src") if iframe else None

                if src:
                    video_options.append({"label": label, "src": src})

                    # 👉 if it's a dailymotion embed
                    if "dailymotion.com/embed/video/" in src:
                        vid_id = src.split("/embed/video/")[-1].split("?")[0]

                        # First get metadata (optional)
                        meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"
                        meta = requests.get(meta_url, headers=HEADERS, timeout=20).json()

                        # Get m3u8 link from metadata
                        if "qualities" in meta:
                            for q, streams in meta["qualities"].items():
                                for stream in streams:
                                    if stream.get("type") == "application/x-mpegURL":
                                        m3u8_url = stream["url"]
                                        subs.extend(extract_subs_from_m3u8(m3u8_url))
                                        break
            except Exception:
                continue

    return render_template("watch.html", video_options=video_options, subs=subs)


def extract_subs_from_m3u8(m3u8_url: str):
    """
    Extract real subtitle URLs from a master m3u8.
    - Handles #EXT-X-MEDIA TYPE=SUBTITLES (URI points to subtitle .m3u8)
    - Handles plain .vtt lines (Dailymotion case)
    """
    subs = []
    try:
        r = requests.get(m3u8_url, headers=HEADERS, timeout=20)
        text = r.text

        # structured subtitle entries
        for line in text.splitlines():
            if line.startswith("#EXT-X-MEDIA") and "TYPE=SUBTITLES" in line:
                attrs = dict(re.findall(r'([A-Z0-9\-]+)="(.*?)"', line))
                uri = attrs.get("URI")
                if uri:
                    sub_m3u8 = urljoin(m3u8_url, uri)
                    lang = attrs.get("LANGUAGE") or attrs.get("ASSOC-LANGUAGE") or attrs.get("NAME") or "unknown"
                    name = attrs.get("NAME") or lang
                    subs.append({"lang": lang, "name": name, "url": b64e(sub_m3u8)})

        # fallback: direct .vtt line
        for line in text.splitlines():
            if line and not line.startswith("#") and ".vtt" in line:
                vtt_url = urljoin(m3u8_url, line.strip())
                subs.append({"lang": "unknown", "name": vtt_url.rsplit("/", 1)[-1], "url": b64e(vtt_url)})

        # dedupe
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



def download_full_vtt(m3u8_url, output_file="subtitle.srt"):
    # Step 1: extract real .vtt link from .m3u8
    r = requests.get(m3u8_url, timeout=20)
    lines = r.text.splitlines()
    vtt_url = None
    for line in lines:
        if line.strip().endswith(".vtt") or "subtitle" in line:
            vtt_url = line.strip()
            break
    if not vtt_url:
        raise Exception("No VTT URL found in m3u8")

    # Step 2: download VTT file
    vtt_text = requests.get(vtt_url, timeout=20).text

    # Step 3: convert VTT → SRT
    srt_text = vtt_to_srt(vtt_text)

    # Step 4: save to file
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(srt_text)

    return output_file


def vtt_to_srt(vtt_text: str) -> str:
    lines = vtt_text.splitlines()
    out = []
    buf = []
    idx = 1

    def flush():
        nonlocal idx, buf, out
        if not buf:
            return
        # find time line
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
        # skip headers/notes/styles/regions
        if l.startswith("WEBVTT") or l.startswith("NOTE") or l.startswith("STYLE") or l.startswith("REGION") or l.startswith("Kind:") or l.startswith("Language:"):
            continue
        if not l.strip():
            flush()
        else:
            buf.append(l)
    flush()
    return "\n".join(out).strip() + ("\n" if out else "")

    

@app.route("/download_sub")
def download_sub():
    token = request.args.get("url", "").strip()
    if not token:
        return "No URL provided", 400

    # decode the base64 we set in extract_subs_from_m3u8
    try:
        url = b64d(token)
    except Exception:
        return "Invalid token", 400

    try:
        # Case A: subtitle .m3u8 → find .vtt inside
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

        # Case B: direct .vtt → download and convert
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



if __name__ == "__main__":
    # local run
    app.run(host="127.0.0.1", port=5000, debug=True)
