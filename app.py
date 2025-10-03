import base64
from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup
import re, json
import m3u8

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


def extract_subs_from_m3u8(m3u8_url):
    subs = []
    try:
        r = requests.get(m3u8_url, timeout=20)
        lines = r.text.splitlines()

        for line in lines:
            line = line.strip()
            if line.endswith(".vtt") or "subtitle" in line:
                subs.append({
                    "lang": "unknown",
                    "name": "Subtitle",
                    "url": line
                })
    except Exception as e:
        print("Error extracting subs from m3u8:", e)
    return subs


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
    srt_lines = []
    counter = 1

    for block in vtt_text.strip().split("\n\n"):
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith("WEBVTT"):
            continue

        # detect timestamp line
        if "-->" in lines[0]:
            time_line = lines[0].replace(".", ",")
            text_lines = lines[1:]
        else:
            time_line = lines[1].replace(".", ",")
            text_lines = lines[2:]

        srt_lines.append(f"{counter}\n{time_line}\n" + "\n".join(text_lines))
        counter += 1

    return "\n\n".join(srt_lines)

    

@app.route("/download_sub")
def download_sub():
    url = request.args.get("url")
    if not url:
        return "No URL provided", 400

    # 🔹 Step 1: If it's a whole EXT-X-MEDIA line, extract the URI inside quotes
    if url.startswith("#EXT"):
        match = re.search(r'URI="([^"]+)"', url)
        if match:
            url = match.group(1)

    try:
        # 🔹 Step 2: If it's a .m3u8 again, parse to get real .vtt file
        if url.endswith(".m3u8"):
            r = requests.get(url, timeout=20)
            lines = r.text.splitlines()
            for line in lines:
                if line.strip().endswith(".vtt"):
                    url = line.strip()
                    break

        # 🔹 Step 3: Download final VTT
        r = requests.get(url, timeout=20)
        vtt_text = r.text

        # 🔹 Step 4: Convert to SRT
        srt_text = vtt_to_srt(vtt_text)

        return Response(
            srt_text,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment;filename=subtitle.srt"}
        )
    except Exception as e:
        return f"Error: {e}", 500

if __name__ == "__main__":
    # local run
    app.run(host="127.0.0.1", port=5000, debug=True)
