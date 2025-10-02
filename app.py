import base64
from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

BASE_URL = "https://animexin.dev"

@app.route("/", methods=["GET", "POST"])
def home():
    results = []
    if request.method == "POST":
        query = request.form.get("query")
        if query:
            search_url = f"{BASE_URL}/?s={query}"
            response = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(response.text, "html.parser")

            posts = soup.select("article.bs")
            for post in posts:
                link = post.select_one("a")["href"] if post.select_one("a") else "#"
                title = post.select_one(".eggtitle").get_text(strip=True) if post.select_one(".eggtitle") else "No Title"
                episode = post.select_one(".eggepisode").get_text(strip=True) if post.select_one(".eggepisode") else ""
                img = post.select_one("img")["src"] if post.select_one("img") else ""

                results.append({
                    "title": f"{title} {episode}".strip(),
                    "link": link,
                    "img": img
                })

    return render_template("index.html", results=results)


@app.route("/watch")
def watch():
    url = request.args.get("url")
    video_options = []

    if url:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")

        # Find all <option> under select.mirror
        for option in soup.select("select.mirror option"):
            label = option.get_text(strip=True)
            encoded_value = option["value"]

            try:
                # Decode base64
                decoded_html = base64.b64decode(encoded_value).decode("utf-8", errors="ignore")

                # Parse iframe src
                inner_soup = BeautifulSoup(decoded_html, "html.parser")
                iframe = inner_soup.find("iframe")
                src = iframe["src"] if iframe else None
                if src:
                    video_options.append({"label": label, "src": src})
            except Exception:
                pass

    return render_template("watch.html", video_options=video_options, url=url)


if __name__ == "__main__":
    app.run(debug=True)
