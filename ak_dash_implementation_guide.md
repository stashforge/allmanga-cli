# Ak/DASH `rawUrls` Implementation Guide

> **Purpose**: Hand this to Codex CLI to implement Ak server DASH support in `allmanga-cli`.
> **Status**: Manually tested and confirmed working on 2026-06-13.

---

## What We Discovered

The **Ak** server (encrypted `--hex` sourceUrls that go through the Clock endpoint) returns a `rawUrls` field containing **direct Bilibili/Akamai CDN segment URLs**. These are fully working 1080p streams that the CLI currently **ignores completely**.

The CLI only looks at the `link` field from clock items (which points to `sk.json` and returns 404). The actual playable URLs are in `rawUrls.vids[]` and `rawUrls.audios[]`.

## The Data Flow

```
sourceUrl starts with "--"
  → Substitution cipher decrypt (CIPHER table) → decoded path
  → Change "/clock" to "/clock.json"
  → GET https://allanime.day{decoded_path}
  → Response JSON has "links" array
  → Each link item has:
      - "link": "https://allanime.day/apiak/sk.json?sr=..."  ← RETURNS 404, USELESS
      - "dash": true
      - "rawUrls": { "vids": [...], "audios": [...], "duration": 1451.074 }  ← THE GOOD STUFF
      - "subtitles": [{ "lang": "en", "label": "English", "src": "https://..." }]
```

## Exact Clock Response Structure (relevant parts)

```json
{
  "links": [
    {
      "link": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
      "dash": true,
      "resolutionStr": "Dash 1",
      "src": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
      "subtitles": [
        {
          "lang": "en",
          "label": "English",
          "default": true,
          "type": "text/ass",
          "src": "https://allanime.day/apiak/sk.json?sub=dx-ep-srGrP23qJnjsHrRYD_8_sub_English"
        }
      ],
      "rawUrls": {
        "vids": [
          {
            "bandwidth": 1450146,
            "mime_type": "video/mp4",
            "height": 1080,
            "width": 1920,
            "codecs": "avc1.640032",
            "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/...m4s?...&deadline=1781322359&...",
            "segment_base": { "range": "0-926", "index_range": "927-4438" }
          },
          {
            "bandwidth": 993366,
            "height": 1080,
            "codecs": "avc1.640032",
            "url": "https://..."
          },
          {
            "bandwidth": 373479,
            "height": 720,
            "codecs": "avc1.640028",
            "url": "https://..."
          },
          {
            "bandwidth": 223193,
            "height": 480,
            "codecs": "avc1.64001F",
            "url": "https://..."
          }
        ],
        "audios": [
          {
            "bandwidth": 175739,
            "mime_type": "audio/mp4",
            "codecs": "mp4a.40.2",
            "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/...m4s?..."
          },
          { "bandwidth": 93890, "codecs": "mp4a.40.2", "url": "https://..." },
          { "bandwidth": 67170, "codecs": "mp4a.40.2", "url": "https://..." }
        ],
        "duration": 1451.074
      },
      "trusts": ["allanime", "apivtwo", "akamaized", "allanimenews"]
    }
  ]
}
```

### Key Details About the URLs

- **Domain**: `upos-bstar1-mirrorakam.akamaized.net` (Bilibili's Akamai CDN)
- **Format**: MPEG-DASH segments (`.m4s` files with init segment ranges)
- **No special headers needed** — no Referer, no Origin, just a plain GET
- **Token validity**: `deadline` parameter gives ~3 days, `hdnts` has HMAC auth
- **Video codecs**: Both AVC (`avc1.*`) and HEVC (`hev1.*` / `hvc1.*`) variants available
- **Video resolutions**: 144p, 240p, 360p, 480p, 720p, 1080p (two bitrates for 1080p)
- **Audio**: AAC (`mp4a.40.2`) at 67k, 94k, and 176k bitrates
- **Subtitles**: ASS format, fetched from a separate URL

## How to Play with mpv

Video and audio are **separate streams** — mpv needs `--audio-file`:

```bash
mpv "VIDEO_URL" --audio-file="AUDIO_URL"
```

To add subtitles:

```bash
mpv "VIDEO_URL" --audio-file="AUDIO_URL" --sub-file="SUBTITLE_URL"
```

**Tested result**: 1920x1080 VAAPI hardware decode, perfect A/V sync, played 16+ minutes with no issues.

## Where to Change in the CLI

The function `resolve_source()` handles `--hex` sources. Currently it does this:

```python
# Current code flow for --hex sources:
if url.startswith("--"):
    dec_path = decrypt_url(url[2:])
    items = get_clock_links(dec_path)   # fetches clock JSON, returns links[]
    for item in items:
        link = item.get("link", "")     # ← gets "sk.json" URL
        # ... checks for wixmp repackager
        # ... tries to probe "link" with various referers
        # ... "link" returns 404, so nothing gets added
```

### What Needs to Be Added

Inside the `for item in items:` loop, **before** or **instead of** the existing link probing, check for `rawUrls`:

```python
for item in items:
    link = item.get("link", "")
    raw_urls = item.get("rawUrls")

    # NEW: Handle DASH rawUrls (Bilibili/Akamai CDN)
    if raw_urls and isinstance(raw_urls, dict):
        vids = raw_urls.get("vids", [])
        audios = raw_urls.get("audios", [])
        subtitles = item.get("subtitles", [])

        if vids:
            # Pick best AVC video (prefer avc1 over hevc for compatibility)
            avc_vids = [v for v in vids if "avc" in v.get("codecs", "").lower()]
            if not avc_vids:
                avc_vids = vids  # fallback to whatever is available

            # Sort by height descending, then bandwidth descending
            avc_vids.sort(key=lambda v: (v.get("height", 0), v.get("bandwidth", 0)), reverse=True)

            # Pick best audio
            best_audio = max(audios, key=lambda a: a.get("bandwidth", 0)) if audios else None

            # Pick subtitle if available
            best_sub = None
            for sub in subtitles:
                if sub.get("lang") == "en" or sub.get("default"):
                    best_sub = sub
                    break
            if not best_sub and subtitles:
                best_sub = subtitles[0]

            for vid in avc_vids:
                h = vid.get("height", 0)
                bw = vid.get("bandwidth", 0)
                result.append({
                    "source_name": f"{name} ({h}p)",
                    "link": vid["url"],
                    "type": "mp4",           # mpv plays .m4s as mp4
                    "resolution": f"{h}p",
                    "referer": "",            # no referer needed
                    "headers": {},            # no special headers needed
                    "source_priority": prio,
                    "android_safe": True,     # direct CDN, no headers needed
                    "audio_url": best_audio["url"] if best_audio else None,
                    "subtitle_url": best_sub.get("src") if best_sub else None,
                    "subtitle_type": best_sub.get("type") if best_sub else None,
                })
            continue  # skip the old link probing for this item

    # ... existing wixmp / link probing code continues here ...
```

### mpv Launch Changes

Wherever mpv is launched, check for the new `audio_url` field:

```python
cmd = ["mpv", stream["link"]]
if stream.get("audio_url"):
    cmd += [f"--audio-file={stream['audio_url']}"]
if stream.get("subtitle_url"):
    cmd += [f"--sub-file={stream['subtitle_url']}"]
```

## Important Notes

1. **Video + Audio are separate** — this is the key difference from other sources. The `.m4s` video file has no audio. You MUST use `--audio-file` with mpv.

2. **Prefer AVC over HEVC** — AVC (`avc1.*`) has wider hardware decode support. HEVC (`hev1.*`) is smaller but some systems can't decode it. Pick AVC by default.

3. **Multiple 1080p options** — there are typically TWO 1080p AVC streams at different bitrates (e.g., 1450kbps and 993kbps). The higher bitrate one is better quality.

4. **No referer or headers needed** — the Akamai URLs are self-authenticating via the `hdnts` HMAC parameter. Just GET them directly.

5. **Token expiry** — the `deadline` parameter is a Unix timestamp, typically ~3 days out. The clock JSON itself may be cached (the response had `Cache-Control: public, max-age=150`), but the URLs within it are long-lived.

6. **Android compatibility** — see the dedicated Android section below. The short version: mpv-android works with `--audio-file`, but VLC and Next Player need a generated DASH MPD manifest.

7. **The `segment_base` field** — contains `range` and `index_range` for DASH init segments. mpv/ffmpeg handles this automatically when playing the URL directly. **On Android, these values are needed to build the MPD manifest** (see below).

## Test Proof

```
$ python3 test_ak_dash.py

[3] Probing video streams...
  ✅ 1920x1080 avc1.640032 1450kbps: HTTP 206  content-range=bytes 0-0/263038178
  ✅ 1920x1080 avc1.640032 993kbps: HTTP 206   content-range=bytes 0-0/180185555
  ✅ 1280x720 avc1.640028 373kbps: HTTP 206    content-range=bytes 0-0/67747711
  ... (all 14 video streams ✅)

[4] Probing audio streams...
  ✅ audio mp4a.40.2 175kbps: HTTP 206
  ✅ audio mp4a.40.2 93kbps: HTTP 206
  ✅ audio mp4a.40.2 67kbps: HTTP 206

mpv playback: 1920x1080 VAAPI hardware decode, perfect A-V sync, played 16+ minutes.
```

---

## Android Playback (mpv-android, VLC, Next Player)

### The Problem

These are **separate video-only and audio-only `.m4s` files**. Desktop mpv handles this with `--audio-file`, but Android players differ:

| Player | Separate audio support | Raw `.m4s` URL |
|--------|----------------------|----------------|
| **mpv-android** | ✅ `--audio-file` via intent extras | Works |
| **VLC** | ❌ No separate audio via intent | Video only (silent) |
| **Next Player** | ❌ No separate audio via intent | Video only (silent) |

### Solution: Generate a DASH MPD Manifest

Create a DASH MPD (Media Presentation Description) XML on the fly and serve it through the CLI's local HTTP proxy. All three Android players support DASH playback via MPD.

The clock response already provides everything needed to build the MPD:
- `rawUrls.vids[].url`, `.bandwidth`, `.width`, `.height`, `.codecs`, `.segment_base`
- `rawUrls.audios[].url`, `.bandwidth`, `.codecs`, `.segment_base`
- `rawUrls.duration`

### MPD Template

```python
def generate_mpd(raw_urls, subtitles=None):
    """Generate a DASH MPD manifest from clock rawUrls data."""
    vids = raw_urls.get("vids", [])
    audios = raw_urls.get("audios", [])
    duration = raw_urls.get("duration", 0)

    # Convert duration to ISO 8601 (PT1451.074S)
    dur_iso = f"PT{duration}S"

    video_reps = []
    for v in vids:
        sb = v.get("segment_base", {})
        init_range = sb.get("range", "0-0")
        index_range = sb.get("index_range", "0-0")
        video_reps.append(
            f'        <Representation id="v{v.get("height","0")}_{v.get("codecs","")}" '
            f'bandwidth="{v.get("bandwidth",0)}" '
            f'width="{v.get("width",0)}" height="{v.get("height",0)}" '
            f'codecs="{v.get("codecs","")}" '
            f'frameRate="{v.get("frame_rate","")}" '
            f'sar="{v.get("sar","1:1")}">\n'
            f'          <BaseURL>{v["url"]}</BaseURL>\n'
            f'          <SegmentBase indexRange="{index_range}">\n'
            f'            <Initialization range="{init_range}"/>\n'
            f'          </SegmentBase>\n'
            f'        </Representation>'
        )

    audio_reps = []
    for a in audios:
        sb = a.get("segment_base", {})
        init_range = sb.get("range", "0-0")
        index_range = sb.get("index_range", "0-0")
        audio_reps.append(
            f'        <Representation id="a{a.get("bandwidth",0)}" '
            f'bandwidth="{a.get("bandwidth",0)}" '
            f'codecs="{a.get("codecs","")}">\n'
            f'          <BaseURL>{a["url"]}</BaseURL>\n'
            f'          <SegmentBase indexRange="{index_range}">\n'
            f'            <Initialization range="{init_range}"/>\n'
            f'          </SegmentBase>\n'
            f'        </Representation>'
        )

    # Build subtitle AdaptationSet if available
    sub_section = ""
    if subtitles:
        sub_reps = []
        for s in subtitles:
            sub_reps.append(
                f'        <Representation id="sub_{s.get("lang","und")}" bandwidth="0">\n'
                f'          <BaseURL>{s["src"]}</BaseURL>\n'
                f'        </Representation>'
            )
        sub_section = (
            f'\n      <AdaptationSet mimeType="text/ass" lang="{subtitles[0].get("lang","und")}">\n'
            + "\n".join(sub_reps)
            + "\n      </AdaptationSet>"
        )

    mpd = f'''<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     profiles="urn:mpeg:dash:profile:isoff-on-demand:2011"
     type="static"
     mediaPresentationDuration="{dur_iso}"
     minBufferTime="PT2S">
  <Period duration="{dur_iso}">
    <AdaptationSet mimeType="video/mp4" startWithSAP="1" segmentAlignment="true">
{chr(10).join(video_reps)}
    </AdaptationSet>
    <AdaptationSet mimeType="audio/mp4" startWithSAP="1" segmentAlignment="true">
{chr(10).join(audio_reps)}
    </AdaptationSet>{sub_section}
  </Period>
</MPD>'''
    return mpd
```

### Example Generated MPD

For a single 1080p AVC + one audio track, the output looks like:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
     profiles="urn:mpeg:dash:profile:isoff-on-demand:2011"
     type="static"
     mediaPresentationDuration="PT1451.074S"
     minBufferTime="PT2S">
  <Period duration="PT1451.074S">
    <AdaptationSet mimeType="video/mp4" startWithSAP="1" segmentAlignment="true">
      <Representation id="v1080_avc1.640032" bandwidth="1450146"
                      width="1920" height="1080" codecs="avc1.640032">
        <BaseURL>https://upos-bstar1-mirrorakam.akamaized.net/...m4s?...</BaseURL>
        <SegmentBase indexRange="927-4438">
          <Initialization range="0-926"/>
        </SegmentBase>
      </Representation>
    </AdaptationSet>
    <AdaptationSet mimeType="audio/mp4" startWithSAP="1" segmentAlignment="true">
      <Representation id="a175739" bandwidth="175739" codecs="mp4a.40.2">
        <BaseURL>https://upos-bstar1-mirrorakam.akamaized.net/...m4s?...</BaseURL>
        <SegmentBase indexRange="817-4340">
          <Initialization range="0-816"/>
        </SegmentBase>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
```

### Serving the MPD via Local Proxy

The CLI already has a local HTTP proxy for header injection. Add an endpoint to serve the generated MPD:

```python
# When an Ak DASH stream is selected on Android:
mpd_xml = generate_mpd(raw_urls, subtitles)

# Serve it at something like:
# http://127.0.0.1:{PROXY_PORT}/dash/{episode_hash}.mpd

# Then launch the Android player with:
# intent: VIEW http://127.0.0.1:{PROXY_PORT}/dash/{episode_hash}.mpd
# Content-Type: application/dash+xml
```

The proxy handler for `/dash/*.mpd` routes should:
1. Return the pre-generated MPD XML
2. Set `Content-Type: application/dash+xml`
3. The player then fetches the actual video/audio segments directly from the Akamai CDN (no proxying needed for the segments since they need no special headers)

### Integration Summary for Android

```python
if is_android:
    # Generate MPD from rawUrls
    mpd = generate_mpd(raw_urls, subtitles)
    # Serve via local proxy
    mpd_url = proxy.serve_mpd(mpd, episode_id)
    # Launch player with MPD URL
    launch_player(mpd_url, player="vlc")  # works with vlc, next, mpv-android
else:
    # Desktop: use --audio-file directly
    cmd = ["mpv", best_vid_url, f"--audio-file={best_audio_url}"]
```

### Player-Specific Notes

- **VLC for Android**: Handles DASH MPD natively. Will auto-select best quality based on network. Works great.
- **Next Player**: Uses ExoPlayer under the hood, which has excellent DASH support. Should just work.
- **mpv-android**: Also supports DASH MPD. Alternatively, you can skip the MPD and pass `--audio-file` directly via intent extras if the CLI supports that path.

### Adaptive vs Fixed Quality

The MPD can include **all** video representations (144p through 1080p). The player then does adaptive bitrate switching automatically. Or the CLI can filter to just the user's preferred resolution before generating the MPD — whichever matches the CLI's existing behavior for quality selection.
