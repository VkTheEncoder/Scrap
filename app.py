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
                title = post.select_one("h2 a").get_text(strip=True) if post.select_one("h2 a") else "No Title"
                link = post.select_one("h2 a")["href"] if post.select_one("h2 a") else "#"
                img = post.select_one("img")["src"] if post.select_one("img") else ""
                results.append({"title": title, "link": link, "img": img})

    return render_template("index.html", results=results)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

