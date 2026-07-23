import re
import json
import requests
from urllib.parse import urlparse, parse_qs
from Crypto.Cipher import AES

def b64e(text: str) -> str:
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")

def extract_seekplayer_data(url: str):
    """
    Extracts the direct stream link and subtitles from seekplayer.vip URLs.
    Example URL: https://animexinfansub.seekplayer.vip/v/hxh15
    """
    try:
        # Extract the video ID
        # URLs can be /v/ID or /e/ID
        match = re.search(r'/[ve]/([^/?&]+)', url)
        if not match:
            return None, [], ""
            
        video_id = match.group(1)
        
        # Parse the domain and construct API URL
        parsed = urlparse(url)
        domain = parsed.netloc
        api_url = f"https://{domain}/api/v1/video?id={video_id}&w=1440&h=900&r=animexin.dev"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://{domain}/"
        }
        
        r = requests.get(api_url, headers=headers, timeout=20)
        if r.status_code != 200:
            print("Seekplayer API failed with status:", r.status_code)
            return None, [], ""
            
        hex_data = r.text.strip()
        if not hex_data:
            return None, [], ""
            
        # AES-CBC decryption
        key = b"kiemtienmua911ca"
        try:
            enc = bytes.fromhex(hex_data)
        except ValueError:
            print("Seekplayer API returned invalid hex")
            return None, [], ""
            
        iv = bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        dec = cipher.decrypt(enc)
        
        pad = dec[-1]
        if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]):
            dec = dec[:-pad]
            
        text = dec.decode('utf-8', errors='replace')
        
        # The first 16 bytes are garbled due to an unknown/missing IV. 
        # But the JSON structure starts at byte 16 and is always valid JSON!
        valid_part = text[16:]
        fixed_json_str = '{"video":"https' + valid_part
        
        try:
            data = json.loads(fixed_json_str)
        except Exception as e:
            print("Seekplayer JSON Parse Error:", e)
            return None, [], ""
            
        # Extract stream link
        stream_link = data.get("hlsVideoTiktok") or data.get("cfNative") or data.get("cf") or data.get("video")
        
        if stream_link and stream_link.startswith("/"):
            stream_link = f"https://{domain}{stream_link}"
            
        # Extract subtitles
        subs = []
        subtitle_data = data.get("subtitle") or data.get("subtitles")
        if isinstance(subtitle_data, dict):
            for lang, url in subtitle_data.items():
                if url:
                    subs.append({
                        "lang": lang,
                        "name": lang,
                        "url": b64e(url)
                    })
        elif isinstance(subtitle_data, list):
            for sub in subtitle_data:
                url = sub.get("url") or sub.get("src")
                lang = sub.get("lang") or sub.get("name") or "Unknown"
                if url:
                    subs.append({
                        "lang": lang,
                        "name": lang,
                        "url": b64e(url)
                    })
                    
        return stream_link, subs, ""
        
    except Exception as e:
        print("Seekplayer extract error:", e)
        return None, [], ""
