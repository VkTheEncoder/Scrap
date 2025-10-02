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

            posts = soup.select("article")
            for post in posts:
                title = post.select_one(".eggtitle").get_text(strip=True) if post.select_one(".eggtitle") else "No Title"
                img = post.select_one("img")["src"] if post.select_one("img") else ""
                link = post.select_one("a")["href"] if post.select_one("a") else "#"
                results.append({"title": title, "link": link, "img": img})

    return render_template("index.html", results=results)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
