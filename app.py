import base64

import html as html_lib
import json
import cloudscraper
import requests
import re
from flask import Flask, render_template, request, Response
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote, unquote
from seekplayer import extract_seekplayer_data
import jsbeautifier
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import yt_dlp
from io import BytesIO
from flask import send_file, jsonify

app = Flask(__name__)
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
def extract_rumble_data(embed_url):
    subs = []
    duration_str = ""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        print(f"Fetching Rumble API for: {embed_url}")
        
        # Extract the video ID directly from the URL to bypass Cloudflare HTML blocks
        video_id = None
        match = re.search(r'rumble\.com/(?:embed/)?([a-zA-Z0-9_-]+)', embed_url)
        if match:
            video_id = match.group(1)
            
        if video_id:
            api_url = f'https://rumble.com/embedJS/u3/?request=video&v={video_id}'
                r2 = requests.get(api_url, headers=headers, timeout=20)
                
                if r2.status_code == 200:
                    api_data = r2.json()
                    
                    # Extract duration
                    duration = api_data.get('duration')
                    if duration:
                        duration_str = format_time(duration)
                        
                    # Extract subtitles
                    cc_data = api_data.get('cc', {})
                    if isinstance(cc_data, dict):
                        for lang_code, sub_info in cc_data.items():
                            sub_url = sub_info.get('path')
                            if sub_url:
                                subs.append({
                                    "lang": lang_code,
                                    "name": f"{lang_code} (Manual Subtitle)",
                                    "url": b64e(sub_url)
                                })
                else:
                    print(f"Rumble API returned status {r2.status_code}")
                    
    except Exception as e:
        print(f"Rumble Direct Sub Error: {e}")
        
    return subs, duration_str

def b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("utf-8")

def b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("utf-8")).decode("utf-8")


def encode_resource_token(url: str, referer: str = "") -> str:
    """
    Encode an external resource URL while optionally keeping the Referer that
    the host expects. Existing plain URL tokens remain fully compatible.
    """
    if not referer:
        return b64e(url)

    return b64e(json.dumps({
        "url": url,
        "referer": referer,
    }, separators=(",", ":")))


def decode_resource_token(token: str):
    """Return ``(url, referer)`` for both old and new subtitle tokens."""
    decoded = b64d(token)

    try:
        data = json.loads(decoded)
        if isinstance(data, dict) and data.get("url"):
            return str(data["url"]), str(data.get("referer") or "")
    except Exception:
        pass

    return decoded, ""


# StreamWish rotates through many official/mirror player domains.  Keep the
# check deliberately narrow enough that unrelated iframe servers are not sent
# through this integration.
STREAMWISH_DOMAINS = {
    "streamwish.com", "streamwish.to", "streamwish.site", "streamwish.fun",
    "wishembed.pro", "mwish.pro", "awish.pro", "dwish.pro",
    "embedwish.com", "wishfast.top", "wishonly.site", "playerwish.com",
    "sfastwish.com", "flaswish.com", "obeywish.com", "cdnwish.com",
    "strwish.com", "strwish.xyz", "hlswish.com", "swishsrv.com",
    "iplayerhls.com", "hlsflast.com", "strmwis.xyz", "jodwish.com",
    "swdyu.com", "playembed.online", "vidmoviesb.xyz", "uqloads.xyz",
    "guxhag.com", "dhcplay.com", "hglink.to", "kravaxxa.com",
    "davioad.com", "haxloppd.com", "tryzendm.com", "dumbalag.com",
    "aiavh.com", "uasopt.com", "ghbrisk.com", "hgbazooka.com",
}


def _clean_embedded_url(value: str, base_url: str = "") -> str:
    if not value:
        return ""

    cleaned = html_lib.unescape(value).strip().strip('"\'')
    cleaned = cleaned.replace("\\/", "/")

    # Some WordPress player values contain a percent-encoded iframe URL.
    if "%3a" in cleaned.lower() or "%2f" in cleaned.lower():
        try:
            cleaned = unquote(cleaned)
        except Exception:
            pass

    if cleaned.startswith("//"):
        cleaned = "https:" + cleaned
    elif base_url and not urlparse(cleaned).scheme:
        cleaned = urljoin(base_url, cleaned)

    return cleaned.rstrip(" );,]")


def is_streamwish_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False

    if not host:
        return False

    if host in STREAMWISH_DOMAINS:
        return True

    if any(host.endswith("." + domain) for domain in STREAMWISH_DOMAINS):
        return True

    # Future StreamWish mirrors almost always retain a wish/swish hostname
    # marker even when the full domain rotates.
    return "wish" in host or "swish" in host


def extract_streamwish_embed_url(payloads) -> str:
    """
    Find the StreamWish iframe/page URL already supplied by AnimeXin.

    This integration intentionally uses the exposed embed URL and normally
    declared caption tracks. It does not unpack protected/obfuscated player
    code or attempt to bypass the host's delivery controls.
    """
    if isinstance(payloads, str):
        payloads = [payloads]

    candidates = []
    for payload in payloads or []:
        if not payload:
            continue

        text = html_lib.unescape(payload).replace("\\/", "/")

        for match in re.finditer(
            r'<iframe[^>]+(?:src|data-src)\s*=\s*["\']([^"\']+)["\']',
            text,
            re.IGNORECASE,
        ):
            candidates.append(match.group(1))

        for match in re.finditer(r'https?://[^"\'<>\s]+', text, re.IGNORECASE):
            candidates.append(match.group(0))

        for match in re.finditer(r'//[^"\'<>\s]+', text, re.IGNORECASE):
            candidates.append(match.group(0))

    for candidate in candidates:
        url = _clean_embedded_url(candidate)
        if not is_streamwish_url(url):
            continue

        parsed = urlparse(url)
        path = parsed.path or "/"

        # StreamWish accepts /e/<code> as the normal embeddable player path.
        path = re.sub(r'^/(?:f|d)/', '/e/', path, flags=re.IGNORECASE)
        return parsed._replace(path=path).geturl()

    return ""


def _streamwish_headers(page_url: str, referer: str = BASE_URL):
    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""

    headers = {
        "User-Agent": ANIMEXIN_HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": referer or BASE_URL,
    }

    if origin:
        headers["Origin"] = origin

    return headers


def fetch_streamwish_open_page(embed_url: str):
    """Fetch the public StreamWish embed page with normal browser headers."""
    headers = _streamwish_headers(embed_url)
    errors = []

    try:
        response = curl_requests.get(
            embed_url,
            headers=headers,
            impersonate="chrome",
            timeout=25,
            allow_redirects=True,
        )
        if response.status_code == 200 and (response.text or "").strip():
            return response.text, str(response.url)
        errors.append(f"curl_cffi HTTP {response.status_code}")
    except Exception as exc:
        errors.append(f"curl_cffi: {exc}")

    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(
            embed_url,
            headers=headers,
            timeout=25,
            allow_redirects=True,
        )
        if response.status_code == 200 and (response.text or "").strip():
            return response.text, str(response.url)
        errors.append(f"cloudscraper HTTP {response.status_code}")
    except Exception as exc:
        errors.append(f"cloudscraper: {exc}")

    raise RuntimeError("; ".join(errors) or "Unable to load StreamWish player")


def _subtitle_language_from_url(url: str) -> str:
    lower = url.lower()
    language_hints = {
        "english": ("english", "eng", "en"),
        "indonesian": ("indonesia", "indonesian", "indo", "id"),
        "portuguese": ("portuguese", "por", "pt"),
        "spanish": ("spanish", "spa", "es"),
        "turkish": ("turkish", "tur", "tr"),
        "arabic": ("arabic", "ara", "ar"),
        "german": ("german", "deu", "ger", "de"),
        "italian": ("italian", "ita", "it"),
        "polish": ("polish", "pol", "pl"),
        "thai": ("thai", "th"),
        "bangla": ("bangla", "bengali", "ben", "bn"),
    }

    path_tokens = set(re.split(r'[^a-z0-9]+', lower))
    for language, hints in language_hints.items():
        for hint in hints:
            if hint in path_tokens or (len(hint) > 3 and hint in lower):
                return language

    return "unknown"


def extract_streamwish_public_tracks(page_html: str, page_url: str):
    """Extract only caption URLs plainly exposed by the player page."""
    tracks = []
    soup = BeautifulSoup(page_html or "", "html.parser")

    def add_track(raw_url: str, lang: str = "", name: str = ""):
        url = _clean_embedded_url(raw_url, page_url)
        if not url:
            return

        clean_path = urlparse(url).path.lower()
        if not clean_path.endswith((".vtt", ".webvtt", ".srt", ".m3u8")):
            return

        final_lang = (lang or _subtitle_language_from_url(url) or "unknown").strip()
        final_name = (name or final_lang or "Subtitle").strip()

        tracks.append({
            "lang": final_lang,
            "name": final_name,
            "url": encode_resource_token(url, page_url),
        })

    for track in soup.select("track[src]"):
        kind = (track.get("kind") or "").lower()
        if kind and kind not in {"captions", "subtitles"}:
            continue

        add_track(
            track.get("src", ""),
            track.get("srclang", ""),
            track.get("label", ""),
        )

    # Some StreamWish templates expose a normal, non-packed JWPlayer `tracks`
    # object. Read those literal values without evaluating JavaScript.
    for block in re.findall(r'\{[^{}]{0,1200}\}', page_html or "", re.DOTALL):
        lower = block.lower()
        if not any(word in lower for word in ("caption", "subtitle", ".vtt", ".srt", ".webvtt")):
            continue

        file_match = re.search(
            r'(?:file|src)\s*:\s*["\']([^"\']+)["\']',
            block,
            re.IGNORECASE,
        )
        if not file_match:
            continue

        label_match = re.search(r'label\s*:\s*["\']([^"\']+)["\']', block, re.IGNORECASE)
        lang_match = re.search(
            r'(?:srclang|language|lang)\s*:\s*["\']([^"\']+)["\']',
            block,
            re.IGNORECASE,
        )

        add_track(
            file_match.group(1),
            lang_match.group(1) if lang_match else "",
            label_match.group(1) if label_match else "",
        )

    seen = set()
    unique = []
    for track in tracks:
        if track["url"] in seen:
            continue
        seen.add(track["url"])
        unique.append(track)

    return unique


def extract_streamwish_public_data(embed_url: str):
    """Return the public embed URL, normal caption tracks, and duration."""
    page_html, final_url = fetch_streamwish_open_page(embed_url)
    subtitles = extract_streamwish_public_tracks(page_html, final_url)
    duration = ""

    duration_match = re.search(
        r'(?:duration|video_duration)\s*[:=]\s*["\']?(\d{1,6})',
        page_html,
        re.IGNORECASE,
    )
    if duration_match:
        duration = format_time(duration_match.group(1))

    return final_url or embed_url, subtitles, duration


def extract_streamwish_api_data(embed_url: str):
    """
    Call the StreamWish /api/source/{code} JSON endpoint — the same request
    their own player JS makes — to get the real HLS stream URL and subtitle
    tracks without needing to execute JavaScript or pass a bot challenge.

    Falls back to the page-scraper (extract_streamwish_public_data) if the
    API call fails or returns no usable data.
    """
    try:
        parsed = urlparse(embed_url)
        # embed path is /e/<code> — grab the last non-empty segment
        path_parts = [p for p in parsed.path.split("/") if p]
        if not path_parts:
            raise ValueError("Cannot determine file code from embed URL")
        file_code = path_parts[-1]
        base = f"{parsed.scheme}://{parsed.netloc}"
        api_url = f"{base}/api/source/{file_code}"

        headers = {
            "User-Agent": ANIMEXIN_HEADERS["User-Agent"],
            "Referer": embed_url,
            "Origin": base,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        resp = requests.post(
            api_url,
            data={"r": BASE_URL, "d": parsed.netloc},
            headers=headers,
            timeout=20,
        )

        print("STREAMWISH API STATUS:", resp.status_code, api_url)
        data = resp.json()
        print("STREAMWISH API RESPONSE:", str(data)[:500])

        if not data.get("success"):
            raise RuntimeError(f"StreamWish API success=false: {data}")

        # --- Stream link (first HLS source) ---
        stream_link = ""
        for src in data.get("data", {}).get("sources", []) or []:
            if src.get("file"):
                stream_link = src["file"]
                break

        # --- Subtitle tracks ---
        subs = []
        for track in data.get("data", {}).get("tracks", []) or []:
            kind = (track.get("kind") or "").lower()
            # Skip chapter/thumbnail tracks
            if kind and kind not in {"captions", "subtitles"}:
                continue
            file_url = track.get("file") or track.get("src") or ""
            if not file_url:
                continue
            label = track.get("label") or track.get("language") or "unknown"
            lang  = track.get("language") or track.get("srclang") or label or "unknown"
            subs.append({
                "lang": lang,
                "name": label,
                "url": encode_resource_token(file_url, embed_url),
            })

        print("STREAMWISH API stream_link:", stream_link)
        print("STREAMWISH API subs count:", len(subs))

        # If the API gave us nothing useful, let the page scraper try.
        if not stream_link and not subs:
            raise RuntimeError("API returned no sources and no tracks")

        return stream_link, subs, ""

    except Exception as e:
        print("STREAMWISH API ERROR, falling back to page scraper:", e)
        return extract_streamwish_public_data(embed_url)


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


def filename_context_from_episode_token(token: str):
    """Return (anime title, episode number) from the encoded episode URL."""
    try:
        episode_url = b64d(token) if token else ""
    except Exception:
        return "Anime", ""

    path = urlparse(episode_url).path.strip("/")
    match = re.search(
        r"^(?P<title>.+?)-episode-(?P<episode>\d+(?:\.\d+)?)\b",
        path,
        flags=re.IGNORECASE,
    )

    if not match:
        return "Anime", ""

    title_slug = match.group("title")
    episode_num = match.group("episode")
    words = [word for word in re.split(r"[-_]+", title_slug) if word]

    # Readable title from the URL slug without depending on browser state.
    minor_words = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
    title_words = []
    for index, word in enumerate(words):
        lower = word.lower()
        if index > 0 and lower in minor_words:
            title_words.append(lower)
        else:
            title_words.append(lower.capitalize())

    title = " ".join(title_words).strip() or "Anime"
    return title, episode_num

# -------------------------------
# STREAM ROUTE (UPDATED)
# -------------------------------
@app.route("/stream", methods=["POST"])
def stream():
    # 1. Get Params
    token = request.form.get("episode_token", "").strip()
    subtitle_pref = (request.form.get("subtitle", "") or "").lower().strip()
    server_value = request.form.get("server", "").strip()
    
    # 2. Build the filename only from the episode token.
    # This keeps the original working button/request flow and does not depend
    # on JavaScript globals, data attributes, or cached browser state.
    token_title, token_episode = filename_context_from_episode_token(token)

    safe_title = re.sub(r'[\/*?:"<>|]', "", token_title).strip() or "Anime"
    safe_episode = re.sub(r'[\/*?:"<>|]', "", token_episode).strip()

    if safe_episode:
        custom_filename = f"{safe_title} Ep-{safe_episode}.srt"
    else:
        custom_filename = f"{safe_title}.srt"

    print("FILENAME CONTEXT FROM TOKEN:", safe_title, "| EP:", safe_episode)
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
            subs, rumble_duration = extract_rumble_data(rumble_payload)
            subs_map = {s["lang"].lower(): s["url"] for s in subs}
            if rumble_duration:
                duration_str = rumble_duration
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
            stream_link = f"https://www.dailymotion.com/embed/video/{dm_id}?autoplay=1"

            try:
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
            except Exception as e:
                print("Dailymotion Metadata Error:", e)
        elif direct_dm_url:
            stream_link = direct_dm_url

    except Exception as e:
        print("Animexin Error:", e)

    # === 1.5. SEEKPLAYER LOGIC ===
    if not is_animexin and not dm_id and not rumble_payload:
        seekplayer_url = extract_matching_url(server_payloads, "seekplayer.vip")
        if seekplayer_url:
            is_animexin = True
            sp_link, sp_subs, sp_dur = extract_seekplayer_data(seekplayer_url)
            if sp_link:
                stream_link = sp_link
                if sp_subs:
                    subs = sp_subs
                    subs_map = {s["lang"].lower(): s["url"] for s in subs}
                if sp_dur:
                    duration_str = sp_dur

    # === 2. ANIMEXIN LOGIC (StreamWish public embed + caption tracks) ===
    if not is_animexin and not dm_id and not rumble_payload:
        try:
            streamwish_url = extract_streamwish_embed_url(server_payloads)
            if streamwish_url:
                is_animexin = True
                sw_link, sw_subs, sw_duration = extract_streamwish_api_data(streamwish_url)
                stream_link = sw_link or streamwish_url

                if sw_duration:
                    duration_str = sw_duration

                if sw_subs:
                    subs = sw_subs
                    subs_map = {s["lang"].lower(): s["url"] for s in subs}

        except Exception as e:
            # Keep the exposed embed URL usable even if the host blocks the
            # server-side metadata request.
            print("StreamWish Error:", e)
            fallback_streamwish = extract_streamwish_embed_url(server_payloads)
            if fallback_streamwish:
                is_animexin = True
                stream_link = fallback_streamwish

    # === 3. TOP CHINESE ANIME LOGIC (VidHide) ===
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
    anime_title = (request.form.get("title") or "Anime").strip() or "Anime"
    episode_num = (request.form.get("episode") or "").strip()
    servers = []

    try:
        url = b64d(token)
        html = fetch_animexin_html(url)
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        print("SERVER LIST ANIMEXIN ERROR:", e)
        return render_template(
            "partials/servers.html",
            servers=[],
            episode_token=token,
            anime_title=anime_title,
            episode_num=episode_num
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
    anime_title = (request.form.get("title") or "Anime").strip() or "Anime"
    episode_num = (request.form.get("episode") or "").strip()
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
        if not subs:
            seekplayer_url = extract_matching_url(payloads, "seekplayer.vip")
            if seekplayer_url:
                _, sp_subs, _ = extract_seekplayer_data(seekplayer_url)
                if sp_subs:
                    subs = sp_subs

        if not subs:
            streamwish_url = extract_streamwish_embed_url(payloads)
            if streamwish_url:
                _, subs, _ = extract_streamwish_api_data(streamwish_url)

        if not subs:
            decoded_server = payloads[0] if payloads else ""
            rumble_payload = extract_matching_url(payloads, "rumble.com")
            rumble_match = re.search(r'src=["\']([^"\']*rumble\.com/embed/[^"\']+)["\']', decoded_server, re.IGNORECASE)
            if rumble_match:
                rumble_payload = rumble_match.group(1)
            if rumble_payload:
                if rumble_payload.startswith("//"):
                    rumble_payload = "https:" + rumble_payload
                r_subs, _ = extract_rumble_data(rumble_payload)
                if r_subs:
                    subs = r_subs

    except Exception as e:
        print(f"Error in get_subtitles: {e}")

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
        url, resource_referer = decode_resource_token(token)
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

        if resource_referer:
            headers["Referer"] = resource_referer
            parsed_referer = urlparse(resource_referer)
            if parsed_referer.scheme and parsed_referer.netloc:
                headers["Origin"] = f"{parsed_referer.scheme}://{parsed_referer.netloc}"


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

        # A few hosts expose a ready-made SRT track. Preserve it as-is rather
        # than forcing it through the VTT converter.
        if (
            "-->" in vtt_text
            and not vtt_text.lstrip().startswith("WEBVTT")
            and re.search(r"^\s*\d+\s*$", vtt_text, re.MULTILINE)
        ):
            return Response(
                vtt_text,
                mimetype="application/octet-stream",
                headers={"Content-Disposition": content_disposition}
            )

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
