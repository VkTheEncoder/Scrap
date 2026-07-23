import requests, json
from Crypto.Cipher import AES

url = 'https://animexinfansub.seekplayer.vip/api/v1/video?id=hxh15&w=1440&h=900&r=animexin.dev'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://animexinfansub.seekplayer.vip/'
}
r = requests.get(url, headers=headers, timeout=20)
dec = AES.new(b'kiemtienmua911ca', AES.MODE_CBC, bytes(16)).decrypt(bytes.fromhex(r.text.strip()))
pad = dec[-1]
if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]):
    dec = dec[:-pad]
text = dec.decode('utf-8', errors='replace')
valid_part = text[16:]

prefix = '{"video":"https'
fixed_json = prefix + valid_part
try:
    json.loads(fixed_json)
    print('SUCCESS')
except Exception as e:
    print('ERROR:', e)
    print('PREFIX:', repr(fixed_json[:50]))
