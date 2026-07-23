import requests, json, re
from Crypto.Cipher import AES

def b64e(text: str) -> str:
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")

def test_extract(url):
    print("Testing:", url)
    parsed_domain = "animexinfansub.seekplayer.vip"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'https://{parsed_domain}/'
    }
    r = requests.get(url, headers=headers, timeout=20)
    dec = AES.new(b'kiemtienmua911ca', AES.MODE_CBC, bytes(16)).decrypt(bytes.fromhex(r.text.strip()))
    pad = dec[-1]
    if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]):
        dec = dec[:-pad]
    text = dec.decode('utf-8', errors='replace')
    valid_part = text[16:]
    
    # Try multiple prefixes to fix the JSON
    prefixes = [
        '{"video":"https',
        '{"video":"http',
        '{"video":"',
        '{"dummy":"',
        '{',
        '{"',
        '{"dummy":'
    ]
    
    data = {}
    for pref in prefixes:
        try:
            data = json.loads(pref + valid_part)
            print("Successfully parsed JSON with prefix:", repr(pref))
            break
        except Exception:
            pass
            
    if not data:
        print("Fallback: slicing valid_part to nearest field")
        match = re.search(r'[,{]\s*"[a-zA-Z0-9_]+"\s*:', valid_part)
        if match:
            clean_json = "{" + valid_part[match.start()+1:]
            try:
                data = json.loads(clean_json)
                print("Successfully parsed JSON via slice!")
            except Exception as e:
                print("Slice JSON parse failed:", e)

    stream_link = data.get("hlsVideoTiktok") or data.get("cfNative") or data.get("cf") or data.get("video")
    
    if not stream_link:
        m = re.search(r'(?:https?:)?//[^"]+\.m3u8[^"]*', text)
        if m:
            stream_link = m.group(0)
            
    print("Stream Link:", stream_link)
    
    subtitle_data = data.get("subtitle") or data.get("subtitles")
    print("Subtitle count:", len(subtitle_data) if subtitle_data else 0)

if __name__ == "__main__":
    test_extract('https://animexinfansub.seekplayer.vip/api/v1/video?id=hxh15&w=1440&h=900&r=animexin.dev')
