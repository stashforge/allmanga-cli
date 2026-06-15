"""Pure provider source-name, URL, and priority helpers."""

import re


CIPHER = {
    "79":"A","7a":"B","7b":"C","7c":"D","7d":"E","7e":"F","7f":"G","70":"H",
    "71":"I","72":"J","73":"K","74":"L","75":"M","76":"N","77":"O","68":"P",
    "69":"Q","6a":"R","6b":"S","6c":"T","6d":"U","6e":"V","6f":"W","60":"X",
    "61":"Y","62":"Z","59":"a","5a":"b","5b":"c","5c":"d","5d":"e","5e":"f",
    "5f":"g","50":"h","51":"i","52":"j","53":"k","54":"l","55":"m","56":"n",
    "57":"o","48":"p","49":"q","4a":"r","4b":"s","4c":"t","4d":"u","4e":"v",
    "4f":"w","40":"x","41":"y","42":"z","08":"0","09":"1","0a":"2","0b":"3",
    "0c":"4","0d":"5","0e":"6","0f":"7","00":"8","01":"9","15":"-","16":".",
    "67":"_","46":"~","02":":","17":"/","07":"?","1b":"#","63":"[","65":"]",
    "78":"@","19":"!","1c":"$","1e":"&","10":"(","11":")","12":"*","13":"+",
    "14":",","03":";","05":"=","1d":"%"
}


def _resolution_height(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def decrypt_url(hex_string):
    decoded = []
    for index in range(0, len(hex_string), 2):
        pair = hex_string[index:index + 2]
        decoded.append(CIPHER.get(pair, pair))
    return "".join(decoded).replace("/clock", "/clock.json")


def expand_wixmp(url):
    match = re.search(r"/,([^/]*),/mp4", url)
    if not match:
        return {"original": url}
    base = re.sub(
        r"\.urlset.*$",
        "",
        url.replace("repackager.wixmp.com/", ""),
    )
    resolutions = [
        resolution
        for resolution in match.group(1).split(",")
        if resolution
    ]
    resolutions.sort(key=_resolution_height, reverse=True)
    return {
        resolution: base.replace(match.group(0), f"/{resolution}/mp4")
        for resolution in resolutions
    }


def source_priority(source):
    name = source.get("sourceName", "").strip().casefold()
    url = source.get("sourceUrl", "")
    if "yt-mp4" in name or "fast4speed" in url or "wixstatic" in url:
        return 1
    if name == "default":
        return 2
    if name == "ak":
        return 3
    if name in {"mp4", "mp4upload"}:
        return 4
    if name == "ok":
        return 5
    if url.startswith("--"):
        return 6
    if any(value in name for value in ("fm-hls", "filemoon")):
        return 7
    return 8
