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

                    # 👉 subtitle extraction for Dailymotion
                    if "dailymotion.com/embed/video/" in src:
                        vid_id = src.split("/embed/video/")[-1].split("?")[0]
                        meta_url = f"https://www.dailymotion.com/player/metadata/video/{vid_id}"
                        try:
                            meta = requests.get(meta_url, headers=HEADERS, timeout=20).json()
                            if "subtitles" in meta:
                                for lang, info in meta["subtitles"].items():
                                    subs.append({"lang": lang, "url": info["url"]})
                        except Exception as e:
                            print("Subtitle fetch failed:", e)

            except Exception:
                continue

    return render_template("watch.html", video_options=video_options, subs=subs)

def extract_subs_from_m3u8(m3u8_url):
    subs = []
    resp = requests.get(m3u8_url, timeout=20)
    playlist = m3u8.loads(resp.text)

    for media in playlist.media:
        if media.type == "SUBTITLES":
            subs.append({
                "lang": media.language or "unknown",
                "url": media.uri
            })
    return subs


if __name__ == "__main__":
    # local run
    app.run(host="127.0.0.1", port=5000, debug=True)
