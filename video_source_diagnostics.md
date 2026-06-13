# AllAnime Video Source Diagnostics

Generated: 2026-06-13T07:08:01.908855+05:30

> Sensitive: this file contains exact temporary/signed source URLs and tokens.

## Executive Notes

- The persisted GraphQL response contains one encrypted `tobeparsed` blob.
- AES-256-CTR decrypts that blob once, producing the complete episode object and all `sourceUrls`.
- Individual source URLs are not all AES-decrypted. Only values beginning with `--` use the separate substitution cipher and Clock endpoint.
- Direct CDN sources are probed by the CLI with User-Agent, Range, and sometimes Referer.
- Generic embed sources are handed to yt-dlp without CLI-supplied Referer/Origin headers.
- mpv accepts both HLS and MP4; extracted external streams are loaded by URL with yt-dlp-provided HTTP headers when available.

## Decryption Implementation

### Outer `tobeparsed` envelope

- Algorithm: AES-256-CTR through OpenSSL.
- Key input: SHA-256 hex digest of ASCII `Xot36i3lK3:v1`.
- Derived key hex: `a254aa27c410f297bd04ba33a0c0df7ff4e706bf3ae27271c6703f84e750f552`
- IV: bytes 1..12 of the base64-decoded envelope, hex-encoded, followed by `00000002`.
- Ciphertext: decoded bytes 13 through 16 bytes before the end.
- This decrypts the whole episode payload, therefore all server entries are inside the same decrypted object.

### Per-source `--...` decoding

- Algorithm: two-hex-character substitution using the CLI `CIPHER` table.
- Applied only when a decoded `sourceUrl` begins with `--`.
- The decoded `/clock` path is changed to `/clock.json` and fetched from `https://allanime.day`.

## Current Header Behavior

```json
{
  "GraphQL/API": {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://allmanga.to",
    "Referer": "https://allmanga.to/",
    "sec-ch-ua-platform": "\"Windows\"",
    "Origin override for episode request": "https://youtu-chan.com"
  },
  "Yt-mp4/direct probe": {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Range": "bytes=0-0",
    "Referer": "https://allmanga.to/ unless wixstatic"
  },
  "Clock link probes": {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Range": "bytes=0-0",
    "Referer attempts": [
      "",
      "https://allmanga.to/",
      "https://gogoanime.tel/",
      "https://anitaku.pe/",
      "https://yugenanime.tv/"
    ]
  },
  "Generic Ok/Uni/Mp4/Fm-Hls/Ss-Hls/Ak embed extraction": {
    "CLI command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "<sourceUrl>"
    ],
    "Explicit CLI Referer": null,
    "Explicit CLI Origin": null,
    "Explicit CLI User-Agent": null,
    "Note": "yt-dlp chooses its own request headers; extracted http_headers are later passed to mpv."
  }
}
```

## Test Episode: Slime Season 4 EP 8

### Exact persisted GraphQL request

```json
{
  "URL": "https://api.allanime.day/api?variables=%7B%22showId%22%3A%20%22srGrP23qJnjsHrRYD%22%2C%20%22translationType%22%3A%20%22sub%22%2C%20%22episodeString%22%3A%20%228%22%7D&extensions=%7B%22persistedQuery%22%3A%20%7B%22version%22%3A%201%2C%20%22sha256Hash%22%3A%20%22d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec%22%7D%7D",
  "headers": {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://youtu-chan.com",
    "Referer": "https://allmanga.to/",
    "sec-ch-ua-platform": "\"Windows\""
  },
  "variables": {
    "showId": "srGrP23qJnjsHrRYD",
    "translationType": "sub",
    "episodeString": "8"
  },
  "extensions": {
    "persistedQuery": {
      "version": 1,
      "sha256Hash": "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"
    }
  }
}
```

### Exact raw GraphQL response

```json
{
  "status": 200,
  "final_url": "https://api.allanime.day/api?variables=%7B%22showId%22%3A%20%22srGrP23qJnjsHrRYD%22%2C%20%22translationType%22%3A%20%22sub%22%2C%20%22episodeString%22%3A%20%228%22%7D&extensions=%7B%22persistedQuery%22%3A%20%7B%22version%22%3A%201%2C%20%22sha256Hash%22%3A%20%22d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec%22%7D%7D",
  "headers": {
    "Date": "Sat, 13 Jun 2026 01:37:15 GMT",
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": "9197",
    "Connection": "close",
    "Server": "cloudflare",
    "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
    "X-Powered-By": "Express",
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "public, max-age=120",
    "Etag": "W/\"23ed-l5J2pwV2+uo4/bIQPN6T6fmGWX0\"",
    "Accept-Ranges": "bytes",
    "Cf-Cache-Status": "EXPIRED",
    "Server-Timing": "cfEdge;dur=5,cfOrigin;dur=545",
    "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=x375pjVcvb7ZRRWBsSL18fNa7qODyLWIXPMfxkkgYdOY5DOQyQOVxakGYxDQ4XkzyaQkrOz7dwMkMBE1WSOEOThOOQO1eSBnvoZorKi9hYLDpJ%2FGln0AAiQ9j8EzB6A5OJIDedS7QFA3tpxKjVFK\"}]}",
    "CF-RAY": "a0ad5e72cecc8124-BOM",
    "alt-svc": "h3=\":443\"; ma=86400"
  },
  "body": {
    "data": {
      "_m": "b7",
      "tobeparsed": "AaGo5zfELIPNSOC/aCoMd04KObfwzJDeVg7HgXk17RQ1UglRlqn2sX7NSR5EsJNOasV52zXGCL/Bax9msuvcqzet1k3Qjd0C+RwHTsqkR5d7xZ11VVRDEGhuyhiVF8N6Wv4HygU/kiwI0qE3QzeJuDUfcp+WopTTaJ3PcaqJ2pwm9VeDgFH8BsiCdnxrLTDDmHTVKqebxvwnAW8EbzVzm920SYKnD2OCbQZziDGLb2KjRjmVq19Nr/7qc1ARUkLn1KsE6iICVhierne+vMdLreRKpI/+q1sJVbzsiE5HLMSRXjJEE8Wi5NLgg4y3T0t4ZEu8VH8QAoqSjgpIV1KyvjNRDVAzax9Ly9dxHZQTVaeCQjq4k/VTuJwz1SZ9o2zfft0R5tcFboPtjtJK68GBIyT+vdxg7+a6sbPh1xN4r4dbzWG9Q9V08+2ulvRRYZ+lVDZqZHqW+TYSkvDmcSY0td7XHglfeAYIbtZDHBX3MWxc8yrFRLCMuSOq1Dj4WpmSG4Aw/nQlIzQHY1DfUTJjHYs2Rr34Kd01X/EOizyt6Bsm7xdRg3k9mHOyZd3bnCFzlH6THHCkPl8O3tg1Aurx7nFSDBvCDQS1kP+5iUGurW8Xn3ZTYh6f7jDMXZrkumveBT8btccUz1PUvreJ/HMzorkpAALkQ+nrzmEvtXy12LhZcvseSDFoQmK5H7z8/2Gv9rHM4cTumSDrL1uvtuZyOe22DJfSnF36lcsch6PiwIxXN8/A1Mq0HAbiYqezxJl38tY7HamZUR3Ee1KyHbZUVSA9MThgR2WNPrzuNq7z4f72C8soawgWBsTDEYbeNuqLtyj6JEV5TN/qN/QRWrF6Jdhkant3Mqrq9l5HOR4G6SyyY+twaiWMWJ7gUPz2DGTQKb6n7XVjED+evN7kS6EKCjh5xMuQD1pY2pQQeb3E6Gj10Vm3OM9qbgYj1Y+p8ZaMWXRtYyxKj/AbGnw7ZBdFSBRCr+VNOmH826DAo4Uv70yqhPDOdEvyaJ283h0YKjkr0i5pp/COQYJ3vi15N1xub0jx+XofHoaQJ4J16waFp8l0zXGil+6qwaHT9edKm5AW3qRuaHAB+MsT3vsYNRqu/A7FsVWWrE/cSRZhiPIJ6HNFIP8nGwFITRNRGHWupNW8gMll1np4dgD27hTErt7zApw6PQs8iC/XAp5petisDXw6zD/qEA7WRgUQVTpyWKaY/BWEuvFYN4kBQdyib/+au0nExINIIp5/fQF/x41F5Hrxysj66t3HUuiOS6rF/fyG2eybq6csdibSkIn4ZTceByTeSOBELvE8lAaGANojUqXE+J4XeSP8tSUokLtNaeGu/zV5ZCp+ImiYUY0edsz9Rf+bMDUglUU3VGVKCz32qo0TcpmIhToKijueaVDpEiva+FzDq8J3n0pIYyB9tbM2bMBm3F4VUu7kP4bTQv+C/CFctK503/3fM+3IQ2g4cnA6ooe+NDKlgCfH7WwvI2aqkWaOBUpdZ54/Yo9HxVwTMnR0j6hhqq/OysS3smqDt0EZFdUbGbHpTOnc3c1dS6ShwNkuutYM/HBECkSFBBYERGJ09gEfnwQ7FkSxk3AXYX99KaCnlDlU5kCuMAJKdwT3OY3VJhBtVM6XK7j2nzNZp/pkvigN/Sir14dvTdcYfhmN+3Br3x5+5SkjUcOK39iWTU46tFtk29bWB5JCTykpeczgYBJuA/Q2tEYjr19JCAI3HD6sKy0YcC3gWJC/h46c8Nl1xRbkc7xD/uYWBY1ZKmBO3hxNNNHgyr2ZpBSxDGvEwDDx1TYLVkdGQ+hEd9Qm9roPNEN/eo6y7e09e0kD6eS3pDJgfWVNyY3RRM8Ml7sYn0hY9epFBAYpRZtOdZFnEfqUQjXNbK60REVpJa7cDxrae4IDDLokVJCYN8FnhM6WFeo3l0zJc3b3oZ/Rc3MjDes2DpI585bN3yMYLqjOmpn0Sbbo6WWKfFdsA5yI19DPYXS4QLblUJ0q1Jup6VGuOzCjpHtEyDLijQavuSsnccFD1yLYsbWyNpo3DC+DWdiPrSDXFicEZsz8RCk4So+ASlgc6GIxYyqT+ZUryXeqaAcB3hUZMH6Sm1IRyvHG6gsHHVgyQYLPxPg9NImDk6Ot7XLNgKs5hivkWysqQujf+qq0vsvoGs+FBJ/kV/I2A9UqF9+DGP7oMS1CQaSQzZoS2FC6EWD0I0fxC0uDH5v7SeYPmtnYRSxuqFUt3Qkm79PSGBSecC/2+xkDBypkhv4clccIDF890Jg0HogWqLcDn1BtroDC2AU2vv/d/t6qDEeX2JPT1pooLO40EZAevxxJW0nHzawSqGud6upLwEMKLdGjqJC36/xs6UIaCuO/OZSjopzXJNB3kub1n77kCxP4JSA+JllRczP6uQuKhXmvZebHq0o4fCMlua2bJ9+I0h5tIBVLFcnXj5U59WQkrI0mkx9JAkNKxxYM3NFCWAG6jCAbZ+ekZUvDoKhUqXLcX0AO72ikbOSSx235kVUoAjKWj82XlCY+ffkSwhF3RJ+8mfipDtK3Ke//um80W10a1kl/gjCewYD7dUo+VO+e2yjpGlH274s0ohWjo1PW2wbw7g4dM01Ob+4f/H+KtePvj8sk3U6fsHJUhjxuT6MnXg1q3XtNOoQHIZxQSBpcMrEXuAU3gkYUUblTaFqQ/NP6l2T3WkQAPxVGp+F7BUYD0JpWD1wwaoD34QFIBn7Wnts9JfoU+kSliDDMEH1lhd3rlR+CW9BtJ/9bDuxSiLKGWCEL8szl75p1G67/shWr5S7dvGIinpypAR4jJpFpe75ZCGqIyBDmyhvgFkBbR7N3awce3bxqN6u/ipxas43vS5QDvufjmrLtX1U5MaKeeA1hVC0IIa8cWxEPvXBjyT2seiYmvNOG5TkBbHN4nbhD1AdGio2m+h3PxPPFv0GDH/lTmkplIRBqfcCcwtk0TH3ImGYIuRXcZDWKtqpl2jwlV/2JfRQEelkP+zrgZcDHbVTPkkToSHJq8CyUWvfUtqIFPctKZnDDl9q16BLqLGKwiGS4ndNcXA1LN3jlgX6utZ96gL2m54RI4Z5Mzs+plByFIoxGZ/YSuQCHf5DfI8n8XtFbJfEFwy36t4UYRyYMXZFS8f98nqwVMDMpxjtbj+WlvG3sUt/Vx1jKBDXJD1PVeszrmQWX1HsxzdvsDapuETSIJ6Ro0KIxvuPfo3t/xTYO8HntDFUgP6NAtawmea3dsmjPo+ejxl+1pP9CN/rXowXQ5kC5wzTziY++4cE2Ib5UWhs5R2NTfNUBdzS49ZqWNCWturKQt30lryAx3IgzPuJZA64wHLMZpkhFRXfheGey7wb2xs3BZhexLTgUHlYJaJpBWoA9RP0m0+mWer5oMQMJVWovKKmA72dcn+Q69sYUa5k4c7FLN1K+gBpXEdySuAJZwPLMLrZKppc7LOppAYNdw/qVulynGQvntp0WoZL6aXnpILs2x+Szl9chYIXv2suqrib1Vl54bE7xhCYRQLBbTqehuq5iUoT/EDyhMU+MY6PL4CyFHLFdfp9ABM7TWyKtYOMdC4dKMlx5Z318aCsSSXcD5+NpBDLx/cKpDBOTH/2+Dw+n6mozlpLYcWJ4/42tfo2VlSAQF/xxj+0btPbim5AnDzocJL4vHzotNl8jvaXb0DSRPrTVYOGYFCa+9aBtcMvXaMD6arQ8X1HPZcKoQTugpem7hRbqwM2rFTA5tDlHFD0HVhQlhrZIxWuAvRsR+2VGbMef5AyGsR2OJywU+UiDHT3mdJEAWnbUahsKF2pNQcs18N8t5YusN5hfe9go7s1mkDxtRtKuybcq0/RdfKMhAHuFYJ8rBEZ3vbBSJz9S+XsvKMMpSiFTwZQR3rIFif2zTWNulkGLzP6kFv/QHobVRVawvdNYDENn3NJdzckDC7sxLmcxzjoQOcOFYck8cpB/0W+bj4Mw6eF9umjZSUaInFsM6V9tnWZ6J9B/h/VDaK2OBgBSo5CPkoOlbb3u/SA2IS1EXCVE+2oVw6+cns6bgqNAFbfIiPqqrprnRZFxKK/1bCmn/p6Ka9Ibv/OXf8o/avapm2wuplwo4b0yqDo2aYCLyRq4ApC7XGkOu/bzZ5UDpWD63OWZTpQ1JW4Hhg97WOk+eYXM5w0ZY/Je8Gy2mRWNMwXWPSSgTHw8WKdm1dDIDQ1ixbhIVbYA0iD0HQawa8Be3FBIbG1ltoKNSZgGOjQtCL3qOcmIPOrxV8H9Dsqod4v3VtPO4vp8gKL7mHzvJlMuL/QswZTNmOese/kJYaqsArS35wFwOyU+2e6C5bAhkTuJCqSbc6Lp/E7L2KSfAUfiTN77EoW8riv/yaMNN4fsz9+ZZaISbINZqFBm+pTV/IKdklppJZhhJ3rSNamTgLnwAE2V/kAIAlwqkNVyCJE35EBMD6y0+jqBaUM4aDVmav+njejSaVEIXLdbbKbcwAbAkM9c7Q/iWsPd5mfrQnRL5Oz3T90hNhI8MkZgSUelj0EudzZ/ac/rKFbSyCqXJ6E5RXvaItsPokIVeZ+mFK7nanRCx9B8ELPHcrQRun9OttLhveWEBkNZGmL98TEHF5Uy74GFAAqMtk33iCJYSE/R+MA19i2BHiYASPWlhdN5sklmgY5D/naK5M0KBBtV4OFza315Lf0V2290tUNTB7mHEgkRv49h7Hv3zMtzWB+g9QRnjA2ldAq0ip8en3W5Kim+OoJQSgLiZW0rH9OnJs74bNczRVyN5bRMxGXEMt33zGsrj16X0LqL25Ry9IZqm6R5IlLfonSq+6HdUbTZpIywq9v6H05ZYHGcjB4TXEedX341Kmi/t+WygVTDKvwTG6JRtR5hjnoxz0jJqPXOVvOnuxYHZEB+QZ/YPXfT5k6rLclxma85duLyKZ2QcOy2SaLl3gbfi+25px6fY3M/ZVkZhMH4leHqT1YYvxihdZlrX9eIYV7JN1jUzUDPk2DqDMVfpS8GJWNOP/GcYelxt41ySEyzmz9+TFxJ6BRBXBlhKtNoSjNpnSyYdq3AbGM0xlUEbZu6RHyT9PgaKT/fB4bRukp3ZF8tpTRR1N3JI7WZL1uQq/VigWMTyxGX3aSGijjGFhYGsqzlNtQxjdOrpOlE5bnneqNmEzNLuGLyYMxcS3BuFS4kkLGM/KbfO5OS1hVxyatGwWTWTHJ03LGnKXnvx8805sj+65F18v2T3bpIdWOqPGmo6OgwDGbx0SnQbBG0p5N1iloQdOgnwmWcT2UyZdMWbZDxGArKoc7NTd+hp5Mx/fmG42HnEp6jjK6scUem99GySTNndXbbvmgR7/D50tVDA5928lGgmdjhuR6vHdIxjUPKvKqyfHNQ0SPmQx/yBOXJWkupY/3/99CMD9w6CzS1oaniZlUEWwpVtlvnSCDhMw6qHa3nulYwIz6NgXT8a7YmBllzKSvxYkALK4VJbFexKEANox1TEw+E6wPiDcT7xZGe0/1r7hvnHTSR4A3OVJXEyS5aeNSN2ARIKKR0lItrWpG1sSIDyOBJAUI2X2X/c13JiULfXYOisVRDZxm2MzLsq5eoV7fGr4y7LEY91zMyhzFESoKd87YqHCU4FmcSpBresEps7sjulnd3qLOl/KiY3Lk8rC2YDQPLzuuPC2S0/DIJIi+UVFVWu2r38hRlK8SA1W8DlUnRZzTS4uSHmglml2wlWIevD7XuVb/ME18HfYVxEeuo7rGwo8Ae5ral3aJ3BPWzWFhv9acy5bym4kilJf/menJD6BS6UvdRB8y1xa3llrLLbszZL8R2P3ztUqnstSk4n+sZ56+EAup4AAJssNFCFo0OSJdjskKvIxTU6LUQYtNQYMYcPHc5tbStx3kEcTXLsu+v2DkymlCWpHP+u0OlHq3wdkB587FktUKZXkgyLUu02J+2bZ34MZ6g2JiOHroOsPMXLbjPh+t57TWrGjvipia7rpxUtlby2gk6fIvFr57pBlqsbXM3ndxrVV4W2Q34ZqHETNB0vi/mikyBlcagb9y8ecBRaGql/fHadBx1TpYFALimfZAIMxvmYTmH0SrWfuqDFxlzLyuqeecKRv105gkCpMjjMbnZT1agUx/mEzhkMpOp3pjZ47VG1RIkFUQsrxovfBke29ELo8we5A3sEalux+44rqBgnSWbWF6yaBwPPPacymmQjIKjpAaBfyTY5Tfg+Ea3G7CJAPdr06aXGcRPIxmM+b/DXqSri6qDvSnyShQwkWpvNEx2ty/DeO0QuS/tDi2Zb3w4BYXpNCZky6gkt+HMIqXybsCTt7eJBRTteVpTFuHvz2d2GgP9U8u+nDDIbjfjMF6r8Rt74i6hycinOE4RsWlr+O6ExXt4ECw+BNpj4JMUEWtfier33PVmArQXOHFY6gmfq5nW6wkPG98gxqM/nWQfwl8GcRHHxHy0CWeOrOEdl6QaJwB/qZ6E+Cs3TB3xNly5+DFH4Wo1Kd4KVBvw0mHFOiUPWG4DiGiPxwzdUe3xjiRjOYJsHWnh2n5I9csETEWun11coxlGmh7CsoTj8DYl3m3giLdVsMtyKF/Ke4LSWxdldQiuF1L7T/wQSO4mQJSib/57t/XSaAPwFSsTrnw/lFeIx2G9gTZZrswjQhDcwlVbIyDQt9X0ESjWqDsHch3U7NQ6WwuIwz0Yv75xFlNPGkpb4W8ERnz+tigtzLnskA7Mfxal1sqcNNZ+ICXFWq6rsXv5Vh09XuZ4ZKVj67ZHOfu4AL7YnxhMhZQv+rVFS/rIDw/So/rAMW0MzYpXs6XUJ7pqsVpWyGHIHp0dysk9MSNMdEMiZJCWHWkj8h5kqznS1no5nYVvOw3419XP2cau8rRxHGbNxsc1hJ2XnSwr4HJxSJ23R84jsoPh8JQe4uRk3O3o55LBgQf+se9kn7TH67pWXKzr8BgxEwyfoRAU7DJrCxeZlWueqr8UGG85rrFGtoOtT4B+eucMXSAyeHwH6iUqHcZJe8lj1WMPwTkSPD7uSAjqpKfhAywVesNZwY90bATXUzF/xXJMCn5lqkxE0AnuTjDFPk/wzmDSRcZ6AN63PiDezQQTSlCW3cSa8W0bL91rQP2zqyIQpztOac4b0BQ5P1QHucoDPaHXmo2EJJvRSVt6bY40PiypLkypA/L4/WVyYTpGXISTFIMw8B+cKm31guKwaF3Crigpwy0VV8evZ78MtcXaxFMRCIW4kZ0quHgAkMf4WQsEIJkRsHsyMDL3ULGt1xaJXMtJNE8/wJM+pg8EDesBfp6OY6MLWaXXFkkmOtZpZdFZMz+lOuO8GRIZw+ft2xVIRlfNOOsjlHROCvT+DU1skxdGegX7iEN5/R8i09MajwxZqvZnx4fjR7bvrKUg2e2E9W8yY7DklPrgCMp6Gjk8hAQAmNsO7oDVppQQnpzQK1a//1mqWODvO3AVr1KSMEHobxWPJp8A39O1iX7wtKBAf0uANBUtoGGmn7F8a0DJ8mdmq7QRgwSNz/+zGMktcD0lAGdfre1wKjptdgK0S/xoyqVuGZn3pq3KU40R4ug76fj0bzqO43EWgwSM5a+8RjOCFouFL0fIp1YlN96uC8bVzKziPNTqjNopqEEB55gGKzEzdOsMsGQaCMAS5ijE3ZG+keTQUhCiqYsVMrTPs9OYsmxHfE1GrdzKfWZ92cXupSexjOTKIEklKAYfYB9TgT11pm/sgl494PJTMWOoeDFezAdLZhdlHEQucFsPk+ppXj4P6slvvFJRdPy7zn2AoqOFSZA/ZYehre3BTt6X2fx7pACfJBr6Ujx8yGphSaQkN6qGPtmwc0Eoifgj8iOMiiL9t3PHCdWdzE0SmBXj5aVYVHmgSiCSed2KDK2rI5ZQWpT1BTBeLQriCmfDO8+NbzhVbZdG4+PihjIXR3bDgF/QdKFrpdObcHRrBcnSfYXRuarWnWklK2rjHd0MvnbSXWDKt+QD0Y4fBM1A9h+EoiKjfxFHyoUFMNFitj+td0xNZE61Ma4SXzbd/Ex+N3S5Jqm600jpmrtd2pyZLWzFxgP8gzwop12qwCIBN+zm7w+900+eEof2EFTx0Xi+trvJIsZ60/K7SWABJjDb35S7Qq0US6C+JtLk702m/G3B4mkGC57oGWWYkujK91VJsarfKA3oYLP3caGDDE+o8qemaFAowi9TH/m2gv0W51jz3auErBaulH4Q9ofnTv8h0mgPVoiKB4BHOJE/wOCZCEfxegRQSva2BDQc0qr8EqgoePIMcCeMJG5nO7aJWeivbqmDQSFuAkD2CF+Z+BwEuX4ihtaHY21yVQCb1DODmNLVXREzbAol7GjT9Dervba7ZnL46VQzyvUDDMrVZYh0F22nVsgzNyRm7sTTXs69UeEMIDh4wByQxDJqUu9ktbkxbgavDrLnQhygTeEfs1VvdwVwpfWso5dk0DMFyUVydrlnmIU788Jx0yzpWnVOW0VSiKIAaQj6gorKYoMD2ZUwwKiRndmOh6DieuMm2j/FJMsjNGlg5Ir62ugnwMJVxcrpVlE7WQPkp9SgBkge2bc0uyXIWIPlkRD1miQwNeFY1xUU9mPDVh40mIvPT+3N8UtIAQc5DadYBswigmpGfo2aXKDSJCpl56tAx7QGqSqWdtNMEcWb8jqsM4KiaXJ3zLjU2ZBgaAe/fMOgMUKALdK7P3pTcKAs3EBycIDwMyHUGdahRXRBfNi/oZbkVwR1lYdZGW8Avptmd9E6fBO4aGhQMQW7w6abhfdgDSUQ8mCPJFfuQMt2y3dYwcN7uHoaA+VM03awa8xxk89jf9jRVytXORQ9266P1N7Aw0LAWJtxOGPCcwtLrn6/yMIxY2Vz89zAUqXqhQ/9L9mY6Xzf9Cwb6RRbwbSVLoIXuIPvNaHhwxYV8krWQRwDnSX+ooXIujM7gigwNqd81mPbxsQo/QLlQxBRWHu1KEVAxtNIbU+U/jam3gt4g/uUYqqSyoWs2klYwM0PSksYqAQvVWKRQBtqIbo35WyaEE/M1xjFITzKa5W9POKGe7GG2rc9klBtMN5NM/FYtql3qQIK+nsFiHHF2ONZYfranQ3DIIb1JFnsrsWYFhDboeO8Ya0MZfIAbmD3vXHv0/jpfddFbYrFvE5xLmmGmts/t9Sbsv0cX3ZLMXQgLTW8dLovqob8ziG4ySEx1znN3GCT1hwVZEfLeH4="
    }
  }
}
```

### Encrypted `tobeparsed`

```text
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
```

### Decrypted episode JSON / raw sourceUrls

```json
{
  "episode": {
    "episodeString": "8",
    "uploadDate": {
      "hour": 15,
      "minute": 10,
      "year": 2026,
      "month": 4,
      "date": 29,
      "second": 56
    },
    "sourceUrls": [
      {
        "sourceUrl": "https://ok.ru/videoembed/14469506337426",
        "priority": 3.5,
        "sourceName": "Ok",
        "stype": "o",
        "type": "iframe",
        "sandbox": "allow-forms allow-scripts allow-same-origin",
        "className": "text-info",
        "streamerId": "allanime"
      },
      {
        "sourceUrl": "https://allanime.uns.bio/#kqmwae",
        "priority": 5.2,
        "sourceName": "Uni",
        "stype": "o",
        "type": "iframe",
        "className": "text-danger",
        "streamerId": "allanime",
        "downloads": {
          "sourceName": "Uns",
          "downloadUrl": "https://allanime.uns.bio/#kqmwae&dl=1"
        }
      },
      {
        "sourceUrl": "https://mp4upload.com/embed-xtx5nkudw78p.html",
        "priority": 4,
        "sourceName": "Mp4",
        "stype": "o",
        "type": "iframe",
        "sandbox": "allow-forms allow-scripts allow-same-origin",
        "className": "",
        "streamerId": "allanime"
      },
      {
        "sourceUrl": "https://bysekoze.com/e/7bo3puvfjgf8",
        "priority": 5.5,
        "sourceName": "Fm-Hls",
        "stype": "o",
        "type": "iframe",
        "className": "text-danger",
        "streamerId": "allanime",
        "downloads": {
          "sourceName": "Filemoon",
          "downloadUrl": "https://bysekoze.com/d/7bo3puvfjgf8"
        }
      },
      {
        "sourceUrl": "https://tools.fast4speed.rsvp/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs?Authorization=3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld",
        "priority": 7.9,
        "sourceName": "Yt-mp4",
        "stype": "t",
        "type": "player",
        "fallBack": "mp4",
        "fileExtenstion": "mp4",
        "className": "",
        "streamerId": "allanime"
      },
      {
        "sourceUrl": "--175948514e4c4f57175b54575b5307515c050f5c0a0c0f0b0f0c0e590a0c0b5b0a0c0b0c0b090b0d0b5d0b5d0b0e0b080b0e0a0c0a590a0c0f0d0f0a0f0c0e0b0e0f0e5a0e0b0f0c0c5e0e0a0a0c0b5b0a0c0c0c0e0c0a0c0a590a0c0e0a0e0f0f0a0e0b0a0c0b5b0a0c0b0c0b0e0b0c0b080a5a0b0e0b080a5a0b0f0b0d0d0a0b0e0b0f0b5b0b0d0b090b5b0b0e0b0e0a000b0e0b0e0b0e0d5b0a0c0a590a0c0f0a0f0c0e0f0e000f0d0e590e0f0f0a0e5e0e010e000d0a0f5e0f0e0e0b0a0c0b5b0a0c0f0d0f0b0e0c0a0c0a590a0c0e5c0e0b0f5e0a0c0b5b0a0c0e0b0f0e0a5a0f0d0f0c0c090f0c0d0e0b0c0b0d0f0f0c5b0e000e5b0f0d0c5d0f0c0d0c0d5e0c0a0d010b5d0d010f0d0f0b0e0c0a0c0f5a",
        "priority": 8.2,
        "sourceName": "Ak",
        "stype": "o",
        "type": "iframe",
        "className": "",
        "streamerId": "allanime"
      }
    ],
    "thumbnail": null,
    "notes": null,
    "show": {
      "_id": "srGrP23qJnjsHrRYD",
      "name": "Tensei shitara Slime Datta Ken Season 4",
      "englishName": "That Time I Got Reincarnated as a Slime Season 4",
      "nativeName": "転生したらスライムだった件 第4期",
      "slugTime": null,
      "thumbnail": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx182205-q2AeO1owuQbO.jpg",
      "lastEpisodeInfo": {
        "sub": {
          "episodeString": "10"
        },
        "dub": {
          "episodeString": "8"
        }
      },
      "lastEpisodeDate": {
        "sub": {
          "hour": 15,
          "minute": 26,
          "year": 2026,
          "month": 5,
          "date": 12
        },
        "dub": {
          "hour": 15,
          "minute": 13,
          "year": 2026,
          "month": 5,
          "date": 12
        },
        "raw": {}
      },
      "type": "TV",
      "season": {
        "quarter": "Spring",
        "year": 2026
      },
      "score": 8.12,
      "airedStart": {
        "year": 2026,
        "month": 3,
        "date": 3,
        "hour": 14,
        "minute": 0
      },
      "availableEpisodes": {
        "sub": 10,
        "dub": 8,
        "raw": 0
      },
      "episodeDuration": "1440000",
      "episodeCount": null,
      "lastUpdateEnd": "2026-06-13T00:46:48.585Z",
      "characterCount": "39",
      "description": "Demon Lord Rimuru&apos;s dream of creating an alliance between humans and monsters takes a step closer to being realized. As Tempest continues to prosper, Granville Rozzo and his granddaughter, Maribel Rozzo, clash with Demon Lord Rimuru over their plan to protect mankind by ruling over them. Meanwhile, in El Dorado, Demon Lord Leon works toward goals of his own. The awakening of a new Hero draws near!<br>\n<br>\n(Source: Crunchyroll)",
      "broadcastInterval": "604800000",
      "banner": "https://s4.anilist.co/file/anilistcdn/media/anime/banner/182205-fRUoKv6f2JAq.jpg",
      "characters": null,
      "availableEpisodesDetail": {
        "sub": [
          "10",
          "9",
          "8",
          "7",
          "6",
          "5",
          "4",
          "3",
          "2",
          "1"
        ],
        "dub": [
          "8",
          "7",
          "6",
          "5",
          "4",
          "3",
          "2",
          "1"
        ],
        "raw": []
      },
      "nameOnlyString": "tensei_shitara_slime_datta_ken_season_4",
      "isAdult": false,
      "relatedShows": [
        {
          "relation": "prequel",
          "showId": "KB5XDvwPdtLFEkoQZ"
        },
        {
          "relation": "sequel",
          "showId": "pJwn9L63YtH6yN9Y9"
        }
      ],
      "relatedMangas": [
        {
          "relation": "adaptation",
          "mangaId": "yTQqrp2LXwaFknp7j"
        }
      ],
      "altNames": [
        "Aquella vez que me convertí en slime - Temporada 4",
        "That Time I Got Reincarnated as a Slime Season 4",
        "เกิดใหม่ทั้งทีก็เป็นสไลม์ไปซะแล้ว ซีซั่น 4",
        "Tensei shitara Slime Datta Ken Season 4",
        "О моём перерождении в слизь 4",
        "転生したらスライムだった件 第4期",
        "Tensura 4",
        "転スラ 4"
      ],
      "disqusIds": {}
    },
    "pageStatus": {
      "_id": "6a19ac86877928643589fb4f",
      "notes": null,
      "pageId": "anime-srGrP23qJnjsHrRYD_sub_8",
      "showId": "srGrP23qJnjsHrRYD",
      "views": "32084",
      "likesCount": "40",
      "commentCount": "0",
      "dislikesCount": "0",
      "reviewCount": "5",
      "userScoreCount": "84",
      "userScoreTotalValue": 809.4,
      "userScoreAverValue": 9.64,
      "viewers": {
        "firstViewers": [
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-05-29T15:11:34.862Z",
            "user": {
              "_id": "AkX2SPBfBetSfffii",
              "displayName": "Hentainization",
              "picture": "https://i.ibb.co/v4KBcTx5/1000006618-upload.jpg",
              "hideMe": false,
              "brief": "gruni"
            }
          }
        ],
        "recViewers": [
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T22:57:00.726Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T23:08:03.774Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T23:18:38.600Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T23:20:57.208Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T23:22:08.620Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T23:58:09.112Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-13T00:07:03.134Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-13T00:23:06.270Z",
            "user": {
              "_id": "6438c82569c0ce23ec3fef11",
              "displayName": "Ledah",
              "picture": "https://lh3.googleusercontent.com/a/AGNmyxYkdqceRfP5A-Ip_RcPgYbJV7xep1QLA5QBR6K_=s96-c",
              "hideMe": false,
              "brief": null
            }
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-13T00:39:25.111Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-13T01:18:13.298Z",
            "user": {
              "_id": "65bec9f5aeb6131337a850ff",
              "displayName": "Bryan",
              "picture": "https://lh3.googleusercontent.com/a/ACg8ocJItILj_vzAOrnxNx3vlJLEVt-aQYwn4WfpZinSRHw=s96-c",
              "hideMe": false,
              "brief": null
            }
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-13T01:31:52.848Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-13T01:33:02.840Z",
            "user": null
          }
        ]
      }
    },
    "episodeInfo": {
      "notes": null,
      "thumbnails": [
        "/covers/mcovers/ep_tbs/srGrP23qJnjsHrRYD/8_sub.jpg",
        "/covers/mcovers/ep_tbs/srGrP23qJnjsHrRYD/8_dub.jpg"
      ],
      "vidInforssub": {
        "vidResolution": 1080,
        "vidPath": "/data2/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs.mp4",
        "vidSize": 215945493,
        "vidDuration": 1440.125
      },
      "uploadDates": {
        "sub": "2026-05-29T15:10:56.000Z",
        "dub": "2026-06-12T15:13:39.000Z"
      },
      "vidInforsdub": {
        "vidResolution": 1080,
        "vidPath": "/data2/media9/videos/srGrP23qJnjsHrRYD/dub/8_1781276898413-wrjo7vwa.mp4",
        "vidSize": 211721908,
        "vidDuration": 1440.51
      },
      "vidInforsraw": null,
      "description": null
    },
    "versionFix": null
  }
}
```

### Server: Ok

```json
{
  "source_name": "Ok",
  "raw_source_url": "https://ok.ru/videoembed/14469506337426",
  "raw_expiry_or_token_fields": {},
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://ok.ru/videoembed/14469506337426",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
  },
  "http_follow_redirect": {
    "url": "https://ok.ru/videoembed/14469506337426",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://ok.ru/videoembed/14469506337426"
    ],
    "returncode": 1,
    "stderr": "ERROR: [Odnoklassniki] 14469506337426: Unable to download webpage: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')) (caused by TransportError(\"('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))\"))\n",
    "stdout_bytes": 0
  }
}
```

### Server: Uni

```json
{
  "source_name": "Uni",
  "raw_source_url": "https://allanime.uns.bio/#kqmwae",
  "raw_expiry_or_token_fields": {},
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://allanime.uns.bio/#kqmwae",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "status": 200,
    "final_url": "https://allanime.uns.bio/#kqmwae",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:22 GMT",
      "Content-Type": "text/html; charset=UTF-8",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Server": "cloudflare",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "Last-Modified": "Sat, 09 May 2026 08:19:25 GMT",
      "Vary": "Accept-Encoding",
      "Server-Timing": "cfEdge;dur=16,cfOrigin;dur=425",
      "Cache-Control": "public, max-age=10",
      "Permissions-Policy": "browsing-topics=()",
      "Referrer-Policy": "origin",
      "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=ZAhMkQNE2uaBxmge7l0QTCQFQ5cmxYeb07Zw5m9jY5A2PkyBdZveIG8XCNDnXqzKf8ufqFfs%2FpDwy4zjUrsaAHNIqXRpCiTUHoBidsuigxlzeIgbGooSNVhmAc7EHCywp9eCLYQRivQDNG8tJYZw\"}]}",
      "Cf-Cache-Status": "REVALIDATED",
      "CF-RAY": "a0ad5e9e8b14ce09-SIN",
      "alt-svc": "h3=\":443\"; ma=86400"
    },
    "body_preview": "<!doctype html>\n<html lang=\"en\" player-version=\"16.5.3\">\n    <head>\n        <meta charset=\"UTF-8\" />\n        <link rel=\"icon\" type=\"image/svg+xml\" href=\"/favicon.png\" />\n        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n        <title>Loading...</title>\n      <script type=\"module\" crossorigin src=\"/assets/index-D1za30JL.js\"></script>\n      <link rel=\"stylesheet\" crossorigin href=\"/assets/index-DsSvO8OB.css\">\n    </head>\n    <body style=\"display: flex; justify-content: center; align-items: center\">\n    <script defer src=\"https://static.cloudflareinsights.com/beaco",
    "looks_hls": false
  },
  "http_follow_redirect": {
    "url": "https://allanime.uns.bio/#kqmwae",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "status": 200,
    "final_url": "https://allanime.uns.bio/#kqmwae",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:23 GMT",
      "Content-Type": "text/html; charset=UTF-8",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Server": "cloudflare",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "Last-Modified": "Sat, 09 May 2026 08:19:25 GMT",
      "Vary": "Accept-Encoding",
      "Server-Timing": "cfEdge;dur=93,cfOrigin;dur=0",
      "Cache-Control": "public, max-age=10",
      "Permissions-Policy": "browsing-topics=()",
      "Referrer-Policy": "origin",
      "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=GxQX0H1abV4MDf2HYj4xX70QNY5t8Ahag89udrcJNlm6vPlpYbaa8v7SmvfVQOQeSxjrpYl8aJij4r%2BIlB69m1fXBy%2BlaOJJSm23zJQdYUBHNrkrdG%2FOoZZ%2F2EVr1ZaxjjIDQJi5OYgc9rSM8pRi\"}]}",
      "Age": "0",
      "Cf-Cache-Status": "HIT",
      "CF-RAY": "a0ad5ea6dd5a49f3-SIN",
      "alt-svc": "h3=\":443\"; ma=86400"
    },
    "body_preview": "<!doctype html>\n<html lang=\"en\" player-version=\"16.5.3\">\n    <head>\n        <meta charset=\"UTF-8\" />\n        <link rel=\"icon\" type=\"image/svg+xml\" href=\"/favicon.png\" />\n        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n        <title>Loading...</title>\n      <script type=\"module\" crossorigin src=\"/assets/index-D1za30JL.js\"></script>\n      <link rel=\"stylesheet\" crossorigin href=\"/assets/index-DsSvO8OB.css\">\n    </head>\n    <body style=\"display: flex; justify-content: center; align-items: center\">\n    <script defer src=\"https://static.cloudflareinsights.com/beaco",
    "looks_hls": false
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://allanime.uns.bio/#kqmwae"
    ],
    "returncode": 1,
    "stderr": "ERROR: Unsupported URL: https://allanime.uns.bio/#kqmwae\n",
    "stdout_bytes": 0
  }
}
```

### Server: Mp4

```json
{
  "source_name": "Mp4",
  "raw_source_url": "https://mp4upload.com/embed-xtx5nkudw78p.html",
  "raw_expiry_or_token_fields": {},
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://mp4upload.com/embed-xtx5nkudw78p.html",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
  },
  "http_follow_redirect": {
    "url": "https://mp4upload.com/embed-xtx5nkudw78p.html",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://mp4upload.com/embed-xtx5nkudw78p.html"
    ],
    "returncode": 1,
    "stderr": "ERROR: [generic] Unable to download webpage: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')) (caused by TransportError(\"('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))\"))\n",
    "stdout_bytes": 0
  }
}
```

### Server: Fm-Hls

```json
{
  "source_name": "Fm-Hls",
  "raw_source_url": "https://bysekoze.com/e/7bo3puvfjgf8",
  "raw_expiry_or_token_fields": {},
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://bysekoze.com/e/7bo3puvfjgf8",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "status": 200,
    "final_url": "https://bysekoze.com/e/7bo3puvfjgf8",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:29 GMT",
      "Content-Type": "text/html",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Server": "cloudflare",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "Last-Modified": "Wed, 10 Jun 2026 15:44:22 GMT",
      "Vary": "Accept-Encoding",
      "Server-Timing": "cfEdge;dur=12,cfOrigin;dur=371",
      "Cache-Control": "no-cache, no-store, must-revalidate",
      "Pragma": "no-cache",
      "Expires": "0",
      "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=GERiEIekWmt1HiLv6vKPhz%2Fqz9qJt0v1mMu9P4Sqb8vT%2BrGEWrjPgNwecJyhLWUkVl%2BG5Uj%2BHD%2FLQEfpakmTyabgehGPZP%2Brcrc5UTTq3OTr%2Fgiwaj8JN7UCpjB1364%3D\"}]}",
      "Cf-Cache-Status": "DYNAMIC",
      "CF-RAY": "a0ad5ecb5c7e5f72-SIN",
      "alt-svc": "h3=\":443\"; ma=86400"
    },
    "body_preview": "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n    <link rel=\"icon\" type=\"image/svg+xml\" href=\"/assets/images/logo.svg\" />\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n    <title>Byse Frontend</title>\n    <script>\n      (function () {\n        try {\n          var path = '';\n          if (typeof window !== 'undefined' && window.location && typeof window.location.pathname === 'string') {\n            path = window.location.pathname;\n          }\n          if (path.indexOf('/e/') !== 0) {\n            return;\n          }\n          var root = docum",
    "looks_hls": false
  },
  "http_follow_redirect": {
    "url": "https://bysekoze.com/e/7bo3puvfjgf8",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "status": 200,
    "final_url": "https://bysekoze.com/e/7bo3puvfjgf8",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:30 GMT",
      "Content-Type": "text/html",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Server": "cloudflare",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "Last-Modified": "Wed, 10 Jun 2026 15:44:22 GMT",
      "Vary": "Accept-Encoding",
      "Server-Timing": "cfEdge;dur=6,cfOrigin;dur=204",
      "Cache-Control": "no-cache, no-store, must-revalidate",
      "Pragma": "no-cache",
      "Expires": "0",
      "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=P1PtdMbFlkQUnYkH51nH1JurimyckfRKGWWGZJ%2FoXcYQ0880iJTXyEFdfvJDGGSNI2WPvBzmZ%2BOuovao9b5h5CH7tz6IWH1pdSL%2F4n%2B47CrPxZ6VYwkbcU6KsRgcmn0%3D\"}]}",
      "Cf-Cache-Status": "DYNAMIC",
      "CF-RAY": "a0ad5ed15b0d25fd-SIN",
      "alt-svc": "h3=\":443\"; ma=86400"
    },
    "body_preview": "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n    <link rel=\"icon\" type=\"image/svg+xml\" href=\"/assets/images/logo.svg\" />\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n    <title>Byse Frontend</title>\n    <script>\n      (function () {\n        try {\n          var path = '';\n          if (typeof window !== 'undefined' && window.location && typeof window.location.pathname === 'string') {\n            path = window.location.pathname;\n          }\n          if (path.indexOf('/e/') !== 0) {\n            return;\n          }\n          var root = docum",
    "looks_hls": false
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://bysekoze.com/e/7bo3puvfjgf8"
    ],
    "returncode": 1,
    "stderr": "ERROR: Unsupported URL: https://bysekoze.com/e/7bo3puvfjgf8\n",
    "stdout_bytes": 0
  }
}
```

### Server: Yt-mp4

```json
{
  "source_name": "Yt-mp4",
  "raw_source_url": "https://tools.fast4speed.rsvp/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs?Authorization=3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld",
  "raw_expiry_or_token_fields": {
    "Authorization": [
      "3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld"
    ]
  },
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://tools.fast4speed.rsvp/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs?Authorization=3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "status": 404,
    "final_url": "https://tools.fast4speed.rsvp/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs?Authorization=3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:32 GMT",
      "Content-Type": "application/octet-stream",
      "Content-Length": "1",
      "Connection": "close",
      "Cache-Control": "private, max-age=0, no-store, no-cache, must-revalidate, post-check=0, pre-check=0",
      "Expires": "Thu, 01 Jan 1970 00:00:01 GMT",
      "Referrer-Policy": "same-origin",
      "X-Frame-Options": "SAMEORIGIN",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "xreop": "ace",
      "Server": "cloudflare",
      "CF-RAY": "a0ad5ee0a9813a29-BOM"
    },
    "body_preview": " ",
    "error": "HTTPError: HTTP Error 404: Not Found",
    "looks_hls": false
  },
  "http_follow_redirect": {
    "url": "https://tools.fast4speed.rsvp/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs?Authorization=3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "status": 404,
    "final_url": "https://tools.fast4speed.rsvp/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs?Authorization=3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:32 GMT",
      "Content-Type": "application/octet-stream",
      "Content-Length": "1",
      "Connection": "close",
      "Cache-Control": "private, max-age=0, no-store, no-cache, must-revalidate, post-check=0, pre-check=0",
      "Expires": "Thu, 01 Jan 1970 00:00:01 GMT",
      "Referrer-Policy": "same-origin",
      "X-Frame-Options": "SAMEORIGIN",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "xreop": "ace",
      "Server": "cloudflare",
      "CF-RAY": "a0ad5ee25a903b73-BOM"
    },
    "body_preview": " ",
    "error": "HTTPError: HTTP Error 404: Not Found",
    "looks_hls": false
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://tools.fast4speed.rsvp/media9/videos/srGrP23qJnjsHrRYD/sub/8_1780067298570-idnoamhs?Authorization=3_20260611032036_71d76a8eb1fd3dc5ae845a2e_fc3acf6078a3c8915ed7e1634d1004c5c9717890_000_20260614032036_0064_dnld"
    ],
    "returncode": 1,
    "stderr": "ERROR: [generic] Unable to download webpage: HTTP Error 404: Not Found (caused by <HTTPError 404: Not Found>)\n",
    "stdout_bytes": 0
  }
}
```

### Server: Ak

```json
{
  "source_name": "Ak",
  "raw_source_url": "--175948514e4c4f57175b54575b5307515c050f5c0a0c0f0b0f0c0e590a0c0b5b0a0c0b0c0b090b0d0b5d0b5d0b0e0b080b0e0a0c0a590a0c0f0d0f0a0f0c0e0b0e0f0e5a0e0b0f0c0c5e0e0a0a0c0b5b0a0c0c0c0e0c0a0c0a590a0c0e0a0e0f0f0a0e0b0a0c0b5b0a0c0b0c0b0e0b0c0b080a5a0b0e0b080a5a0b0f0b0d0d0a0b0e0b0f0b5b0b0d0b090b5b0b0e0b0e0a000b0e0b0e0b0e0d5b0a0c0a590a0c0f0a0f0c0e0f0e000f0d0e590e0f0f0a0e5e0e010e000d0a0f5e0f0e0e0b0a0c0b5b0a0c0f0d0f0b0e0c0a0c0a590a0c0e5c0e0b0f5e0a0c0b5b0a0c0e0b0f0e0a5a0f0d0f0c0c090f0c0d0e0b0c0b0d0f0f0c5b0e000e5b0f0d0c5d0f0c0d0c0d5e0c0a0d010b5d0d010f0d0f0b0e0c0a0c0f5a",
  "raw_expiry_or_token_fields": {},
  "decode_route": "Per-source substitution cipher -> Clock JSON",
  "clock": {
    "decoded_path": "/apivtwo/clock.json?id=7d2473746a243c243431353e3e363036242a2475727463676b63744f62243c244464242a2462677263243c24343634302b36302b37355236373c35313c3636283636365c242a2472746768756a67726f6968527f7663243c24757364242a246d637f243c2463762b75744174563435774c686c754e74545f42593e59757364247b",
    "clock_url": "https://allanime.day/apivtwo/clock.json?id=7d2473746a243c243431353e3e363036242a2475727463676b63744f62243c244464242a2462677263243c24343634302b36302b37355236373c35313c3636283636365c242a2472746768756a67726f6968527f7663243c24757364242a246d637f243c2463762b75744174563435774c686c754e74545f42593e59757364247b",
    "status": 200,
    "final_url": "https://allanime.day/apivtwo/clock.json?id=7d2473746a243c243431353e3e363036242a2475727463676b63744f62243c244464242a2462677263243c24343634302b36302b37355236373c35313c3636283636365c242a2472746768756a67726f6968527f7663243c24757364242a246d637f243c2463762b75744174563435774c686c754e74545f42593e59757364247b",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:34 GMT",
      "Content-Type": "application/json",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Server": "cloudflare",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "X-Powered-By": "Express",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=150",
      "Vary": "Accept-Encoding",
      "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=%2FysrtTtIeWhrCtTJM3t1ORR79tFk5reAUsk%2FHnO2Sdj3K3xQx6%2FG5D4pwwgGSnI4mQy8BKsy09r8BGZHqzXvxZUYPNP7NTC4SWjE0Crtb1DdCC3RdWx6D7qgKGWHlxVOcE%2FohbTpMQn25lI%3D\"}]}",
      "Last-Modified": "Sat, 13 Jun 2026 01:37:34 GMT",
      "Cf-Cache-Status": "MISS",
      "Server-Timing": "cfEdge;dur=7,cfOrigin;dur=566",
      "CF-RAY": "a0ad5eea6fb084d7-BOM",
      "alt-svc": "h3=\":443\"; ma=86400"
    },
    "body": {
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
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-261210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&gen=playurlv3&oi=2823883530&platform=pc&nbs=1&deadline=1781320997&os=akam&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&upsig=4406166c20c927246268dfca8f3cf102&uparams=e,uipk,gen,oi,platform,nbs,deadline,os,trid,mid&hdnts=exp=1781320997~hmac=cb2ee154c331ad955ab7cc4771673c46263f5ddf238ed8094febb0bd53f19b23&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "avc1.640032",
                "segment_base": {
                  "range": "0-926",
                  "index_range": "927-4438"
                }
              },
              {
                "bandwidth": 993366,
                "mime_type": "video/mp4",
                "height": 1080,
                "width": 1920,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-251210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&platform=pc&nbs=1&gen=playurlv3&os=akam&oi=2823883530&uipk=5&deadline=1781320997&upsig=e8b78057d197b8b54f6c8f1f905e3b8b&uparams=e,trid,mid,platform,nbs,gen,os,oi,uipk,deadline&hdnts=exp=1781320997~hmac=c67a9d0b5e4d9fe7ab214205494fd60a023ce539713da016f0aee6975a64102f&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "avc1.640032",
                "segment_base": {
                  "range": "0-926",
                  "index_range": "927-4438"
                }
              },
              {
                "bandwidth": 373479,
                "mime_type": "video/mp4",
                "height": 720,
                "width": 1280,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-241210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&nbs=1&deadline=1781320997&oi=2823883530&gen=playurlv3&os=akam&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&platform=pc&upsig=93ffab2fdf0ab0a9e227db9c73498d06&uparams=e,uipk,nbs,deadline,oi,gen,os,trid,mid,platform&hdnts=exp=1781320997~hmac=239de5a740ce695ac3e535229456a74d4cfe36993ce271a7d617e06f738b1c96&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "avc1.640028",
                "segment_base": {
                  "range": "0-926",
                  "index_range": "927-4438"
                }
              },
              {
                "bandwidth": 223193,
                "mime_type": "video/mp4",
                "height": 480,
                "width": 852,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-231210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&nbs=1&mid=1715226141&platform=pc&uipk=5&deadline=1781320997&gen=playurlv3&os=akam&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&upsig=b63d2b5b643d1d9d7a6be518a0e20977&uparams=e,nbs,mid,platform,uipk,deadline,gen,os,oi,trid&hdnts=exp=1781320997~hmac=c9206e0660eb9ceedfa3c4cbfc4fd1606dc41593690d4bdc93998a82ac81f39a&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "avc1.64001F",
                "segment_base": {
                  "range": "0-925",
                  "index_range": "926-4437"
                }
              },
              {
                "bandwidth": 152295,
                "mime_type": "video/mp4",
                "height": 360,
                "width": 640,
                "frame_rate": "216191/9018",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-211210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&nbs=1&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&uipk=5&deadline=1781320997&gen=playurlv3&os=akam&platform=pc&upsig=1193aec710113a1514cba3973989a079&uparams=e,nbs,oi,trid,mid,uipk,deadline,gen,os,platform&hdnts=exp=1781320997~hmac=70c546a93c48829eb0e3c8b9d2c9b6cfd975aa58fef2f6a92e332ab36c41ed01&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "avc1.64001E",
                "segment_base": {
                  "range": "0-933",
                  "index_range": "934-4445"
                }
              },
              {
                "bandwidth": 88189,
                "mime_type": "video/mp4",
                "height": 240,
                "width": 426,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2e1210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&deadline=1781320997&os=akam&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&uipk=5&nbs=1&gen=playurlv3&oi=2823883530&platform=pc&upsig=ab3e5579f749ee44825a9c24397cce00&uparams=e,deadline,os,trid,mid,uipk,nbs,gen,oi,platform&hdnts=exp=1781320997~hmac=8f53664cdfb4d5f84b3fae14117673fef936ebd9699c610e9816a7aa61fb8c76&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "avc1.64001E",
                "segment_base": {
                  "range": "0-926",
                  "index_range": "927-4438"
                }
              },
              {
                "bandwidth": 45061,
                "mime_type": "video/mp4",
                "height": 144,
                "width": 256,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2f1210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&deadline=1781320997&gen=playurlv3&os=akam&oi=2823883530&platform=pc&uipk=5&nbs=1&upsig=92448b06e3b4a6708101ce5dbb6dccac&uparams=e,trid,mid,deadline,gen,os,oi,platform,uipk,nbs&hdnts=exp=1781320997~hmac=35997c6e774dfd5238a1d4e8c148cc7be400a63fc22a893cfdaf5edb67d4c78c&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "avc1.64001E",
                "segment_base": {
                  "range": "0-925",
                  "index_range": "926-4437"
                }
              },
              {
                "bandwidth": 1402254,
                "mime_type": "video/mp4",
                "height": 1080,
                "width": 1920,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-261220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&uipk=5&oi=2823883530&gen=playurlv3&os=akam&nbs=1&deadline=1781320997&upsig=d51e70b3bd9ee60cfeef352e934b041f&uparams=e,trid,mid,platform,uipk,oi,gen,os,nbs,deadline&hdnts=exp=1781320997~hmac=64e81ea7b8bf7a66733622d9cf5402ca3c2af2f8f7aacdebd0d3af21bffdee92&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "hev1.1.6.L150.90",
                "segment_base": {
                  "range": "0-1088",
                  "index_range": "1089-4600"
                }
              },
              {
                "bandwidth": 983967,
                "mime_type": "video/mp4",
                "height": 1080,
                "width": 1920,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-251220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&oi=2823883530&trid=8913c3b4260a490c9b3f367a50b33bc7i&platform=pc&uipk=5&nbs=1&deadline=1781320997&gen=playurlv3&os=akam&mid=1715226141&upsig=c50ee4e8563ccb3c8b5a5c53dc27f972&uparams=e,oi,trid,platform,uipk,nbs,deadline,gen,os,mid&hdnts=exp=1781320997~hmac=f6cc87df0437700697a9ad4f106012ed05cd3caa9252a12bc0c52f97b33d9cc6&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "hev1.1.6.L150.90",
                "segment_base": {
                  "range": "0-1088",
                  "index_range": "1089-4600"
                }
              },
              {
                "bandwidth": 250579,
                "mime_type": "video/mp4",
                "height": 720,
                "width": 1280,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-241220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&deadline=1781320997&gen=playurlv3&trid=8913c3b4260a490c9b3f367a50b33bc7i&uipk=5&nbs=1&os=akam&oi=2823883530&mid=1715226141&platform=pc&upsig=9fc6f2f4c476ede7a5213d055b1d6b77&uparams=e,deadline,gen,trid,uipk,nbs,os,oi,mid,platform&hdnts=exp=1781320997~hmac=d54e6d8e75a1fc34575d2dc288ad7ed3b8637fbbdf0576576b4a7b0d0e0427f1&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "hev1.1.6.L120.90",
                "segment_base": {
                  "range": "0-1088",
                  "index_range": "1089-4600"
                }
              },
              {
                "bandwidth": 161929,
                "mime_type": "video/mp4",
                "height": 480,
                "width": 852,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-231220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&uipk=5&deadline=1781320997&os=akam&nbs=1&gen=playurlv3&oi=2823883530&upsig=137788e78430816fe7904802bdfa61a8&uparams=e,trid,mid,platform,uipk,deadline,os,nbs,gen,oi&hdnts=exp=1781320997~hmac=4fef3b53e7d6f451b144432e84749cb6b084b8d39dba42b354881eb29d1d63af&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "hev1.1.6.L120.90",
                "segment_base": {
                  "range": "0-1088",
                  "index_range": "1089-4600"
                }
              },
              {
                "bandwidth": 115192,
                "mime_type": "video/mp4",
                "height": 360,
                "width": 640,
                "frame_rate": "216191/9018",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-211220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&mid=1715226141&uipk=5&trid=8913c3b4260a490c9b3f367a50b33bc7i&gen=playurlv3&os=akam&oi=2823883530&platform=pc&nbs=1&deadline=1781320997&upsig=4dc21a9fd9349e5a704281ed057696da&uparams=e,mid,uipk,trid,gen,os,oi,platform,nbs,deadline&hdnts=exp=1781320997~hmac=c9906c7481991c20683d0be49c89af2397b2cb5753e9ef49deb03f4119173baa&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "hvc1.1.6.L120.90",
                "segment_base": {
                  "range": "0-1097",
                  "index_range": "1098-4609"
                }
              },
              {
                "bandwidth": 70595,
                "mime_type": "video/mp4",
                "height": 240,
                "width": 426,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2e1220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&nbs=1&deadline=1781320997&os=akam&oi=2823883530&gen=playurlv3&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&upsig=84a0c9e59cf6dcbcffbae111a6b4c42e&uparams=e,uipk,nbs,deadline,os,oi,gen,trid,mid,platform&hdnts=exp=1781320997~hmac=975f9378dffd6659d59e19c3ae21040c0a939e9d5c87a1818ae152084f0a509b&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "hev1.1.6.L120.90",
                "segment_base": {
                  "range": "0-1088",
                  "index_range": "1089-4600"
                }
              },
              {
                "bandwidth": 37812,
                "mime_type": "video/mp4",
                "height": 144,
                "width": 256,
                "frame_rate": "155203/6474",
                "start_with_sap": 1,
                "sar": "N/A",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2f1220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&nbs=1&deadline=1781320997&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&uipk=5&os=akam&oi=2823883530&gen=playurlv3&upsig=031504f4ad5eb1a8dd42ee3911f36f10&uparams=e,nbs,deadline,trid,mid,platform,uipk,os,oi,gen&hdnts=exp=1781320997~hmac=ee64a4b9ef9fe6b9c6925728e664bb5afb357cd7f90d992195653bb282ac693b&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "hev1.1.6.L120.90",
                "segment_base": {
                  "range": "0-1087",
                  "index_range": "1088-4599"
                }
              }
            ],
            "audios": [
              {
                "bandwidth": 175739,
                "mime_type": "audio/mp4",
                "height": 0,
                "width": 0,
                "frame_rate": "",
                "start_with_sap": 1,
                "sar": "",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2d1301000023.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&os=akam&mid=1715226141&uipk=5&deadline=1781320997&gen=playurlv3&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&platform=pc&nbs=1&upsig=da06b773e48c0f24bc6243a431182575&uparams=e,os,mid,uipk,deadline,gen,oi,trid,platform,nbs&hdnts=exp=1781320997~hmac=fe8bd6a07fde3b309bc19bc6551f371681ff2479dbcf740f93a7d62d39eeec5a&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "mp4a.40.2",
                "segment_base": {
                  "range": "0-816",
                  "index_range": "817-4340"
                }
              },
              {
                "bandwidth": 93890,
                "mime_type": "audio/mp4",
                "height": 0,
                "width": 0,
                "frame_rate": "",
                "start_with_sap": 1,
                "sar": "",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2c1301000023.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&platform=pc&uipk=5&os=akam&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&nbs=1&deadline=1781320997&gen=playurlv3&mid=1715226141&upsig=e28d91cf4f51f447747635f1cd235c96&uparams=e,platform,uipk,os,oi,trid,nbs,deadline,gen,mid&hdnts=exp=1781320997~hmac=f5d865b81b2e3b008c14678f025e5291a8c19f18257cb9878d6fa4ad21b92744&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "mp4a.40.2",
                "segment_base": {
                  "range": "0-816",
                  "index_range": "817-4340"
                }
              },
              {
                "bandwidth": 67170,
                "mime_type": "audio/mp4",
                "height": 0,
                "width": 0,
                "frame_rate": "",
                "start_with_sap": 1,
                "sar": "",
                "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2a1301000023.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&platform=pc&nbs=1&deadline=1781320997&gen=playurlv3&os=akam&oi=2823883530&upsig=8a6f61f8760e0e4c8d1ec37f69320f80&uparams=e,uipk,trid,mid,platform,nbs,deadline,gen,os,oi&hdnts=exp=1781320997~hmac=e399bd312893ec84c80f2b6e13d044453ee69d3f19a671d5a6b08f8a8537e5a3&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
                "codecs": "mp4a.40.2",
                "segment_base": {
                  "range": "0-824",
                  "index_range": "825-4348"
                }
              }
            ],
            "duration": 1451.074
          },
          "trusts": [
            "allanime",
            "apivtwo",
            "akamaized",
            "allanimenews"
          ],
          "fromCache": "2026-06-13T01:37:34.226Z"
        }
      ]
    }
  },
  "clock_link_probes": [
    {
      "item": {
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
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-261210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&gen=playurlv3&oi=2823883530&platform=pc&nbs=1&deadline=1781320997&os=akam&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&upsig=4406166c20c927246268dfca8f3cf102&uparams=e,uipk,gen,oi,platform,nbs,deadline,os,trid,mid&hdnts=exp=1781320997~hmac=cb2ee154c331ad955ab7cc4771673c46263f5ddf238ed8094febb0bd53f19b23&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "avc1.640032",
              "segment_base": {
                "range": "0-926",
                "index_range": "927-4438"
              }
            },
            {
              "bandwidth": 993366,
              "mime_type": "video/mp4",
              "height": 1080,
              "width": 1920,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-251210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&platform=pc&nbs=1&gen=playurlv3&os=akam&oi=2823883530&uipk=5&deadline=1781320997&upsig=e8b78057d197b8b54f6c8f1f905e3b8b&uparams=e,trid,mid,platform,nbs,gen,os,oi,uipk,deadline&hdnts=exp=1781320997~hmac=c67a9d0b5e4d9fe7ab214205494fd60a023ce539713da016f0aee6975a64102f&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "avc1.640032",
              "segment_base": {
                "range": "0-926",
                "index_range": "927-4438"
              }
            },
            {
              "bandwidth": 373479,
              "mime_type": "video/mp4",
              "height": 720,
              "width": 1280,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-241210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&nbs=1&deadline=1781320997&oi=2823883530&gen=playurlv3&os=akam&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&platform=pc&upsig=93ffab2fdf0ab0a9e227db9c73498d06&uparams=e,uipk,nbs,deadline,oi,gen,os,trid,mid,platform&hdnts=exp=1781320997~hmac=239de5a740ce695ac3e535229456a74d4cfe36993ce271a7d617e06f738b1c96&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "avc1.640028",
              "segment_base": {
                "range": "0-926",
                "index_range": "927-4438"
              }
            },
            {
              "bandwidth": 223193,
              "mime_type": "video/mp4",
              "height": 480,
              "width": 852,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-231210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&nbs=1&mid=1715226141&platform=pc&uipk=5&deadline=1781320997&gen=playurlv3&os=akam&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&upsig=b63d2b5b643d1d9d7a6be518a0e20977&uparams=e,nbs,mid,platform,uipk,deadline,gen,os,oi,trid&hdnts=exp=1781320997~hmac=c9206e0660eb9ceedfa3c4cbfc4fd1606dc41593690d4bdc93998a82ac81f39a&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "avc1.64001F",
              "segment_base": {
                "range": "0-925",
                "index_range": "926-4437"
              }
            },
            {
              "bandwidth": 152295,
              "mime_type": "video/mp4",
              "height": 360,
              "width": 640,
              "frame_rate": "216191/9018",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-211210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&nbs=1&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&uipk=5&deadline=1781320997&gen=playurlv3&os=akam&platform=pc&upsig=1193aec710113a1514cba3973989a079&uparams=e,nbs,oi,trid,mid,uipk,deadline,gen,os,platform&hdnts=exp=1781320997~hmac=70c546a93c48829eb0e3c8b9d2c9b6cfd975aa58fef2f6a92e332ab36c41ed01&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "avc1.64001E",
              "segment_base": {
                "range": "0-933",
                "index_range": "934-4445"
              }
            },
            {
              "bandwidth": 88189,
              "mime_type": "video/mp4",
              "height": 240,
              "width": 426,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2e1210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&deadline=1781320997&os=akam&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&uipk=5&nbs=1&gen=playurlv3&oi=2823883530&platform=pc&upsig=ab3e5579f749ee44825a9c24397cce00&uparams=e,deadline,os,trid,mid,uipk,nbs,gen,oi,platform&hdnts=exp=1781320997~hmac=8f53664cdfb4d5f84b3fae14117673fef936ebd9699c610e9816a7aa61fb8c76&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "avc1.64001E",
              "segment_base": {
                "range": "0-926",
                "index_range": "927-4438"
              }
            },
            {
              "bandwidth": 45061,
              "mime_type": "video/mp4",
              "height": 144,
              "width": 256,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2f1210110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&deadline=1781320997&gen=playurlv3&os=akam&oi=2823883530&platform=pc&uipk=5&nbs=1&upsig=92448b06e3b4a6708101ce5dbb6dccac&uparams=e,trid,mid,deadline,gen,os,oi,platform,uipk,nbs&hdnts=exp=1781320997~hmac=35997c6e774dfd5238a1d4e8c148cc7be400a63fc22a893cfdaf5edb67d4c78c&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "avc1.64001E",
              "segment_base": {
                "range": "0-925",
                "index_range": "926-4437"
              }
            },
            {
              "bandwidth": 1402254,
              "mime_type": "video/mp4",
              "height": 1080,
              "width": 1920,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-261220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&uipk=5&oi=2823883530&gen=playurlv3&os=akam&nbs=1&deadline=1781320997&upsig=d51e70b3bd9ee60cfeef352e934b041f&uparams=e,trid,mid,platform,uipk,oi,gen,os,nbs,deadline&hdnts=exp=1781320997~hmac=64e81ea7b8bf7a66733622d9cf5402ca3c2af2f8f7aacdebd0d3af21bffdee92&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "hev1.1.6.L150.90",
              "segment_base": {
                "range": "0-1088",
                "index_range": "1089-4600"
              }
            },
            {
              "bandwidth": 983967,
              "mime_type": "video/mp4",
              "height": 1080,
              "width": 1920,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-251220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&oi=2823883530&trid=8913c3b4260a490c9b3f367a50b33bc7i&platform=pc&uipk=5&nbs=1&deadline=1781320997&gen=playurlv3&os=akam&mid=1715226141&upsig=c50ee4e8563ccb3c8b5a5c53dc27f972&uparams=e,oi,trid,platform,uipk,nbs,deadline,gen,os,mid&hdnts=exp=1781320997~hmac=f6cc87df0437700697a9ad4f106012ed05cd3caa9252a12bc0c52f97b33d9cc6&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "hev1.1.6.L150.90",
              "segment_base": {
                "range": "0-1088",
                "index_range": "1089-4600"
              }
            },
            {
              "bandwidth": 250579,
              "mime_type": "video/mp4",
              "height": 720,
              "width": 1280,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-241220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&deadline=1781320997&gen=playurlv3&trid=8913c3b4260a490c9b3f367a50b33bc7i&uipk=5&nbs=1&os=akam&oi=2823883530&mid=1715226141&platform=pc&upsig=9fc6f2f4c476ede7a5213d055b1d6b77&uparams=e,deadline,gen,trid,uipk,nbs,os,oi,mid,platform&hdnts=exp=1781320997~hmac=d54e6d8e75a1fc34575d2dc288ad7ed3b8637fbbdf0576576b4a7b0d0e0427f1&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "hev1.1.6.L120.90",
              "segment_base": {
                "range": "0-1088",
                "index_range": "1089-4600"
              }
            },
            {
              "bandwidth": 161929,
              "mime_type": "video/mp4",
              "height": 480,
              "width": 852,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-231220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&uipk=5&deadline=1781320997&os=akam&nbs=1&gen=playurlv3&oi=2823883530&upsig=137788e78430816fe7904802bdfa61a8&uparams=e,trid,mid,platform,uipk,deadline,os,nbs,gen,oi&hdnts=exp=1781320997~hmac=4fef3b53e7d6f451b144432e84749cb6b084b8d39dba42b354881eb29d1d63af&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "hev1.1.6.L120.90",
              "segment_base": {
                "range": "0-1088",
                "index_range": "1089-4600"
              }
            },
            {
              "bandwidth": 115192,
              "mime_type": "video/mp4",
              "height": 360,
              "width": 640,
              "frame_rate": "216191/9018",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-211220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&mid=1715226141&uipk=5&trid=8913c3b4260a490c9b3f367a50b33bc7i&gen=playurlv3&os=akam&oi=2823883530&platform=pc&nbs=1&deadline=1781320997&upsig=4dc21a9fd9349e5a704281ed057696da&uparams=e,mid,uipk,trid,gen,os,oi,platform,nbs,deadline&hdnts=exp=1781320997~hmac=c9906c7481991c20683d0be49c89af2397b2cb5753e9ef49deb03f4119173baa&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "hvc1.1.6.L120.90",
              "segment_base": {
                "range": "0-1097",
                "index_range": "1098-4609"
              }
            },
            {
              "bandwidth": 70595,
              "mime_type": "video/mp4",
              "height": 240,
              "width": 426,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2e1220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&nbs=1&deadline=1781320997&os=akam&oi=2823883530&gen=playurlv3&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&upsig=84a0c9e59cf6dcbcffbae111a6b4c42e&uparams=e,uipk,nbs,deadline,os,oi,gen,trid,mid,platform&hdnts=exp=1781320997~hmac=975f9378dffd6659d59e19c3ae21040c0a939e9d5c87a1818ae152084f0a509b&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "hev1.1.6.L120.90",
              "segment_base": {
                "range": "0-1088",
                "index_range": "1089-4600"
              }
            },
            {
              "bandwidth": 37812,
              "mime_type": "video/mp4",
              "height": 144,
              "width": 256,
              "frame_rate": "155203/6474",
              "start_with_sap": 1,
              "sar": "N/A",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2f1220110000.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&nbs=1&deadline=1781320997&trid=8913c3b4260a490c9b3f367a50b33bc7i&mid=1715226141&platform=pc&uipk=5&os=akam&oi=2823883530&gen=playurlv3&upsig=031504f4ad5eb1a8dd42ee3911f36f10&uparams=e,nbs,deadline,trid,mid,platform,uipk,os,oi,gen&hdnts=exp=1781320997~hmac=ee64a4b9ef9fe6b9c6925728e664bb5afb357cd7f90d992195653bb282ac693b&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "hev1.1.6.L120.90",
              "segment_base": {
                "range": "0-1087",
                "index_range": "1088-4599"
              }
            }
          ],
          "audios": [
            {
              "bandwidth": 175739,
              "mime_type": "audio/mp4",
              "height": 0,
              "width": 0,
              "frame_rate": "",
              "start_with_sap": 1,
              "sar": "",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2d1301000023.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&os=akam&mid=1715226141&uipk=5&deadline=1781320997&gen=playurlv3&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&platform=pc&nbs=1&upsig=da06b773e48c0f24bc6243a431182575&uparams=e,os,mid,uipk,deadline,gen,oi,trid,platform,nbs&hdnts=exp=1781320997~hmac=fe8bd6a07fde3b309bc19bc6551f371681ff2479dbcf740f93a7d62d39eeec5a&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "mp4a.40.2",
              "segment_base": {
                "range": "0-816",
                "index_range": "817-4340"
              }
            },
            {
              "bandwidth": 93890,
              "mime_type": "audio/mp4",
              "height": 0,
              "width": 0,
              "frame_rate": "",
              "start_with_sap": 1,
              "sar": "",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2c1301000023.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&platform=pc&uipk=5&os=akam&oi=2823883530&trid=be0ebbdd55c64d66a85df94ad30362a5i&nbs=1&deadline=1781320997&gen=playurlv3&mid=1715226141&upsig=e28d91cf4f51f447747635f1cd235c96&uparams=e,platform,uipk,os,oi,trid,nbs,deadline,gen,mid&hdnts=exp=1781320997~hmac=f5d865b81b2e3b008c14678f025e5291a8c19f18257cb9878d6fa4ad21b92744&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "mp4a.40.2",
              "segment_base": {
                "range": "0-816",
                "index_range": "817-4340"
              }
            },
            {
              "bandwidth": 67170,
              "mime_type": "audio/mp4",
              "height": 0,
              "width": 0,
              "frame_rate": "",
              "start_with_sap": 1,
              "sar": "",
              "url": "https://upos-bstar1-mirrorakam.akamaized.net/iupxcodeboss/53/pd/n260529erjkx7dtwgxvrb1csufi2pd53-1-2a1301000023.m4s?e=ig8euxZM2rNcNbdlhoNvNC8BqJIzNbfqXBvEqxTEto8BTrNvN0GvT90W5JZMkX_YN0MvXg8gNEV4NC8xNEV4N03eN0B5tZlqNxTEto8BTrNvNeZVuJ10Kj_g2UB02J0mN0B5tZlqNCNEto8BTrNvNC7MTX502C8f2jmMQJ6mqF2fka1mqx6gqj0eN0B599M=&uipk=5&trid=be0ebbdd55c64d66a85df94ad30362a5i&mid=1715226141&platform=pc&nbs=1&deadline=1781320997&gen=playurlv3&os=akam&oi=2823883530&upsig=8a6f61f8760e0e4c8d1ec37f69320f80&uparams=e,uipk,trid,mid,platform,nbs,deadline,gen,os,oi&hdnts=exp=1781320997~hmac=e399bd312893ec84c80f2b6e13d044453ee69d3f19a671d5a6b08f8a8537e5a3&bvc=vod&orderid=0,2&logo=00000000&f=i_0_0",
              "codecs": "mp4a.40.2",
              "segment_base": {
                "range": "0-824",
                "index_range": "825-4348"
              }
            }
          ],
          "duration": 1451.074
        },
        "trusts": [
          "allanime",
          "apivtwo",
          "akamaized",
          "allanimenews"
        ],
        "fromCache": "2026-06-13T01:37:34.226Z"
      },
      "expiry_or_token_fields": {},
      "probes": [
        {
          "url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "referer": "",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0"
          },
          "follow_redirects": true,
          "status": 404,
          "final_url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "response_headers": {
            "Date": "Sat, 13 Jun 2026 01:37:35 GMT",
            "Content-Type": "text/plain",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "cloudflare",
            "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
            "X-Powered-By": "Express",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "max-age=120",
            "Vary": "Accept-Encoding",
            "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=t6Q3moADuZQW%2Bn5GNQ1d7DN9ES3y1iNWX7vuwToP%2FCIZDsUaY%2BPsss7CVu3%2FqASZSvftpXaeBAXX2vZjVfcfWr3eQrBW1cQFc2C5Vaep5IKCLBBHTu9N%2B%2FNifata2eA%2Fqe%2FdmaGJx%2BX42pU%3D\"}]}",
            "Cf-Cache-Status": "EXPIRED",
            "Server-Timing": "cfEdge;dur=8,cfOrigin;dur=595",
            "CF-RAY": "a0ad5eef6ed441a4-BOM",
            "alt-svc": "h3=\":443\"; ma=86400"
          },
          "body_preview": "Not found",
          "error": "HTTPError: HTTP Error 404: Not Found",
          "looks_hls": false
        },
        {
          "url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "referer": "https://allmanga.to/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://allmanga.to/"
          },
          "follow_redirects": true,
          "status": 404,
          "final_url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "response_headers": {
            "Date": "Sat, 13 Jun 2026 01:37:36 GMT",
            "Content-Type": "text/plain",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "cloudflare",
            "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
            "X-Powered-By": "Express",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "max-age=120",
            "Vary": "Accept-Encoding",
            "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=y5M9lSLKy9ejltQ9nVzHoqwgF74zwF35dzOxWp5Sm39cV%2F1ylyqkCQuId8Sqng73HuczeptTD4UFONS%2FKj6mUIki38MP6RS99DyAjT2c%2Fk9WKQLKJYtJVl6cR3TIZelDtHM70rcoi5htvRs%3D\"}]}",
            "Cf-Cache-Status": "EXPIRED",
            "Server-Timing": "cfEdge;dur=11,cfOrigin;dur=561",
            "CF-RAY": "a0ad5ef4d8a23a18-BOM",
            "alt-svc": "h3=\":443\"; ma=86400"
          },
          "body_preview": "Not found",
          "error": "HTTPError: HTTP Error 404: Not Found",
          "looks_hls": false
        },
        {
          "url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "referer": "https://gogoanime.tel/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://gogoanime.tel/"
          },
          "follow_redirects": true,
          "status": 404,
          "final_url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "response_headers": {
            "Date": "Sat, 13 Jun 2026 01:37:36 GMT",
            "Content-Type": "text/plain",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "cloudflare",
            "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
            "X-Powered-By": "Express",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "max-age=120",
            "Vary": "Accept-Encoding",
            "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=2BFE4Y22tG8dAiIdHwc4nytBR5%2B4fIE2WnVqrvYkOdFOJpFzcLMs8MWN7TIUl6RhX%2Bi6pNYwqoC%2FaAwpUfwcXSY0LCdKJqhzJS%2FiZW%2F9hE%2B3BuCPwlmIt3LjU9aIWxa6O7Hk8xe8QgRPSJA%3D\"}]}",
            "Cf-Cache-Status": "EXPIRED",
            "Server-Timing": "cfEdge;dur=8,cfOrigin;dur=298",
            "CF-RAY": "a0ad5efa294441fa-BOM",
            "alt-svc": "h3=\":443\"; ma=86400"
          },
          "body_preview": "Not found",
          "error": "HTTPError: HTTP Error 404: Not Found",
          "looks_hls": false
        },
        {
          "url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "referer": "https://anitaku.pe/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://anitaku.pe/"
          },
          "follow_redirects": true,
          "status": 404,
          "final_url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "response_headers": {
            "Date": "Sat, 13 Jun 2026 01:37:37 GMT",
            "Content-Type": "text/plain",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "cloudflare",
            "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
            "X-Powered-By": "Express",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "max-age=120",
            "Vary": "Accept-Encoding",
            "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=L5QC5xVjMkGQWOsT%2BHGp0TSshGz9agVLGleNsEC3AhJOrztZJvOe669nuVXYOhb%2FpJIzFw9MSafsMgQkg%2BEav6x%2BcYZt9ztSlpZLHzldGMw8SDTsXN01qJzJnZmjJ7SquHvRV262zc%2FAG%2BI%3D\"}]}",
            "Cf-Cache-Status": "EXPIRED",
            "Server-Timing": "cfEdge;dur=6,cfOrigin;dur=281",
            "CF-RAY": "a0ad5efe38e1ff7b-BOM",
            "alt-svc": "h3=\":443\"; ma=86400"
          },
          "body_preview": "Not found",
          "error": "HTTPError: HTTP Error 404: Not Found",
          "looks_hls": false
        },
        {
          "url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "referer": "https://yugenanime.tv/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://yugenanime.tv/"
          },
          "follow_redirects": true,
          "status": 404,
          "final_url": "https://allanime.day/apiak/sk.json?sr=dx-ep-srGrP23qJnjsHrRYD_8_sub",
          "response_headers": {
            "Date": "Sat, 13 Jun 2026 01:37:38 GMT",
            "Content-Type": "text/plain",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "cloudflare",
            "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
            "X-Powered-By": "Express",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "max-age=120",
            "Vary": "Accept-Encoding",
            "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=0IcvCdWeprsJsELq%2FfZr1D5N2wat0oek5q1Rv3Sojh5dPdFPtd8b2raPzU5m9%2BbwNtZfXIICiG%2FDd2ERAsCHdWAgvS3KAYEeIz2Rw7mconi%2B8onNadjQQvJzOF9o3OgCSxg2MNtBUdo%2FCIg%3D\"}]}",
            "Cf-Cache-Status": "EXPIRED",
            "Server-Timing": "cfEdge;dur=5,cfOrigin;dur=550",
            "CF-RAY": "a0ad5f03fadc85ff-BOM",
            "alt-svc": "h3=\":443\"; ma=86400"
          },
          "body_preview": "Not found",
          "error": "HTTPError: HTTP Error 404: Not Found",
          "looks_hls": false
        }
      ]
    }
  ]
}
```

## Test Episode: ERASED EP 1

### Exact persisted GraphQL request

```json
{
  "URL": "https://api.allanime.day/api?variables=%7B%22showId%22%3A%20%222DT65AtWa7RehsaHF%22%2C%20%22translationType%22%3A%20%22sub%22%2C%20%22episodeString%22%3A%20%221%22%7D&extensions=%7B%22persistedQuery%22%3A%20%7B%22version%22%3A%201%2C%20%22sha256Hash%22%3A%20%22d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec%22%7D%7D",
  "headers": {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://youtu-chan.com",
    "Referer": "https://allmanga.to/",
    "sec-ch-ua-platform": "\"Windows\""
  },
  "variables": {
    "showId": "2DT65AtWa7RehsaHF",
    "translationType": "sub",
    "episodeString": "1"
  },
  "extensions": {
    "persistedQuery": {
      "version": 1,
      "sha256Hash": "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"
    }
  }
}
```

### Exact raw GraphQL response

```json
{
  "status": 200,
  "final_url": "https://api.allanime.day/api?variables=%7B%22showId%22%3A%20%222DT65AtWa7RehsaHF%22%2C%20%22translationType%22%3A%20%22sub%22%2C%20%22episodeString%22%3A%20%221%22%7D&extensions=%7B%22persistedQuery%22%3A%20%7B%22version%22%3A%201%2C%20%22sha256Hash%22%3A%20%22d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec%22%7D%7D",
  "headers": {
    "Date": "Sat, 13 Jun 2026 01:37:39 GMT",
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": "10185",
    "Connection": "close",
    "Server": "cloudflare",
    "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
    "X-Powered-By": "Express",
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "public, max-age=120",
    "Etag": "W/\"27c9-v8iGKylbWEU7CTIIARvtqpiGSHo\"",
    "Accept-Ranges": "bytes",
    "Cf-Cache-Status": "MISS",
    "Server-Timing": "cfEdge;dur=5,cfOrigin;dur=551",
    "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=11z2sze7dQ9Ix6zmWY%2FXs4juZwFeWINTrIDrgIL3wbpANxBU95uwLyKcXyGlVfSTesRVxZsw2TVbeTYy7hqcQrYnfYPV7YZPZ6ppa6FNbefdFkntfbx9HtdiWVg4rDJqPU6Xoudps906wo7umZEK\"}]}",
    "CF-RAY": "a0ad5f0b9a272e56-BOM",
    "alt-svc": "h3=\":443\"; ma=86400"
  },
  "body": {
    "data": {
      "_m": "b7",
      "tobeparsed": "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"
    }
  }
}
```

### Encrypted `tobeparsed`

```text
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
```

### Decrypted episode JSON / raw sourceUrls

```json
{
  "episode": {
    "episodeString": "1",
    "uploadDate": {
      "hour": 19,
      "minute": 24,
      "year": 2016,
      "month": 0,
      "date": 7,
      "second": 31
    },
    "sourceUrls": [
      {
        "sourceUrl": "https://tools.fast4speed.rsvp/videos/2DT65AtWa7RehsaHF/sub/1?Authorization=3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld",
        "priority": 7.9,
        "sourceName": "Yt-mp4",
        "stype": "t",
        "type": "player",
        "fallBack": "mp4",
        "fileExtenstion": "mp4",
        "className": "",
        "streamerId": "allanime"
      },
      {
        "sourceUrl": "https://ok.ru/videoembed/2520546675346",
        "priority": 3.5,
        "sourceName": "Ok",
        "stype": "o",
        "type": "iframe",
        "sandbox": "allow-forms allow-scripts allow-same-origin",
        "className": "text-info",
        "streamerId": "allanime"
      },
      {
        "sourceUrl": "https://streamsb.net/e/5wmn1wgrbvss.html",
        "priority": 5.5,
        "sourceName": "Ss-Hls",
        "stype": "o",
        "type": "iframe",
        "className": "text-danger",
        "streamerId": "allanime",
        "downloads": {
          "sourceName": "StreamSB",
          "downloadUrl": "https://streamsb.net/d/5wmn1wgrbvss.html"
        }
      },
      {
        "sourceUrl": "https://mp4upload.com/embed-jw700v465vrm.html",
        "priority": 4,
        "sourceName": "Mp4",
        "stype": "o",
        "type": "iframe",
        "sandbox": "allow-forms allow-scripts allow-same-origin",
        "className": "",
        "streamerId": "allanime"
      },
      {
        "sourceUrl": "--175948514e4c4f57175b54575b5307515c050f5c0a0c0f0b0f0c0e590a0c0b5b0a0c0e0d0e0c0b0d0b0d0e0d0b0e0d010e080b0a0e0d0e0c0b080b0e0e0a0b080e0b0b0e0e0b0b0e0b0a0e0d0b0f0e0f0b5d0e0c0b0a0b090e0f0e0d0e0c0e0f0b0b0e0a0e080b0e0b0f0b0d0b0f0b0b0a0e0f590a0e0b0c0b0b0e0c0b0e0b0f0e0a0b5d0e0d0e0d0b080b0f0b0c0b0e0b0d0b0a0e0f0e0a0b0c0b5e0b080e0c0e0f0b5e0b0a0b0c0b0e0b5d0e080e0c0e0a0b5e0e0d0a0e0f590a0e0e5a0e0b0e0a0e5e0e0f0a010e0d0e0c0b0d0b0d0e0d0b0e0d010e080b0a0e0d0e0c0b080b0e0e0a0b080e0b0b0e0e0b0b0e0b0a0e0d0b0f0e0f0b5d0e0c0b0a0b090e0f0e0d0e0c0e0f0b0b0e0a0e080b0e0b0f0b0d0b0f0b0b0e080b0e0b0e0b0f0a000e5b0f0e0e090a0e0f590a0e0a590b0a0b5d0b0e0f0e0a590b090b0c0b0e0f0e0a590b0f0b0e0b5d0b0e0f0e0a590a0c0a590a0c0f0d0f0a0f0c0e0b0e0f0e5a0e0b0f0c0c5e0e0a0a0c0b5b0a0c0d090e5e0f5d0a0c0a590a0c0e0a0e0f0f0a0e0b0a0c0b5b0a0c0b0c0b0e0b0c0b080a5a0b0e0b080a5a0b0f0b0d0d0a0b0e0b0f0b5b0b0d0b090b5b0b0e0b0e0a000b0e0b0e0b0e0d5b0a0c0a590a0c0f0a0f0c0e0f0e000f0d0e590e0f0f0a0e5e0e010e000d0a0f5e0f0e0e0b0a0c0b5b0a0c0f0d0f0b0e0c0a0c0a590a0c0e5c0e0b0f5e0a0c0b5b0a0c0e0b0f0e0a5a0b0c0c0a0d0a0b080b0b0c0f0f0a0d090e0f0b090d0c0e0b0e5d0f0d0e0f0c5d0c080d010b0f0d010f0d0f0b0e0c0a0c0f5a",
        "priority": 8.5,
        "sourceName": "Default",
        "stype": "o",
        "type": "iframe",
        "className": "text-info",
        "streamerId": "allanime"
      }
    ],
    "thumbnail": null,
    "notes": null,
    "show": {
      "_id": "2DT65AtWa7RehsaHF",
      "name": "Boku dake ga Inai Machi",
      "englishName": "ERASED",
      "nativeName": "僕だけがいない街",
      "slugTime": null,
      "thumbnail": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/nx21234-v2NMgPyoVRoM.jpg",
      "lastEpisodeInfo": {
        "raw": {
          "episodeString": "12"
        },
        "sub": {
          "episodeString": "12",
          "notes": "Treasure"
        },
        "dub": {
          "episodeString": "12",
          "notes": "Treasure<note-split>Takaramono (宝物)"
        }
      },
      "lastEpisodeDate": {
        "sub": {
          "hour": 18,
          "minute": 59,
          "year": 2016,
          "month": 2,
          "date": 24
        },
        "dub": {
          "hour": 8,
          "minute": 35,
          "year": 2019,
          "month": 3,
          "date": 23
        },
        "raw": {}
      },
      "type": "TV",
      "season": {
        "quarter": "Winter",
        "year": 2016
      },
      "score": 8.32,
      "airedStart": {
        "year": 2016,
        "month": 0,
        "date": 7,
        "hour": 15,
        "minute": 55
      },
      "availableEpisodes": {
        "sub": 12,
        "dub": 12,
        "raw": 0
      },
      "episodeDuration": "1440000",
      "episodeCount": "12",
      "lastUpdateEnd": "2022-06-11T11:31:45.622Z",
      "characterCount": "20",
      "description": "When tragedy is about to strike, Satoru Fujinuma finds himself sent back several minutes before the accident occurs. The detached, 29-year-old manga artist has taken advantage of this powerful yet mysterious phenomenon, which he calls &quot;Revival,&quot; to save many lives.<br>\n <br>\nHowever, when he is wrongfully accused of murdering someone close to him, Satoru is sent back to the past once again, but this time to 1988, 18 years in the past. Soon, he realizes that the murder may be connected to the abduction and killing of one of his classmates, the solitary and mysterious Kayo Hinazuki, that took place when he was a child. This is his chance to make things right.<br>\n <br>\n<i>Boku dake ga Inai Machi</i> follows Satoru in his mission to uncover what truly transpired 18 years ago and prevent the death of his classmate while protecting those he cares about in the present.<br>\n<br>\n[Written by MAL Rewrite]",
      "broadcastInterval": "604800000",
      "banner": "https://s4.anilist.co/file/anilistcdn/media/anime/banner/21234-7lfSSPoMmwr2.jpg",
      "characters": null,
      "availableEpisodesDetail": {
        "sub": [
          "12",
          "11",
          "10",
          "9",
          "8",
          "7",
          "6",
          "5",
          "4",
          "3",
          "2",
          "1"
        ],
        "dub": [
          "12",
          "11",
          "10",
          "9",
          "8",
          "7",
          "6",
          "5",
          "4",
          "3",
          "2",
          "1"
        ],
        "raw": []
      },
      "nameOnlyString": "bokudakegainaimachi-2016",
      "isAdult": null,
      "relatedShows": [
        {
          "relation": "summary",
          "showId": "iYSdoQPkLRdyKjqN4"
        }
      ],
      "relatedMangas": [
        {
          "relation": "adaptation",
          "mangaId": "CYvSH3ZB2TQZnc2ND"
        }
      ],
      "altNames": [
        "The Town Where Only I am Missing",
        "Boku dake ga Inai Machi",
        "BokuMachi",
        "僕だけがいない街",
        "ERASED"
      ],
      "disqusIds": {}
    },
    "pageStatus": {
      "_id": "60b2fa3b0d40b89d72bfbe94",
      "notes": "Flashing Before My Eyes<note-split>Soumatou (走馬灯)",
      "pageId": "anime-bokudakegainaimachi_sub_1",
      "showId": "2DT65AtWa7RehsaHF",
      "views": "4684",
      "likesCount": "1",
      "commentCount": "0",
      "dislikesCount": "0",
      "reviewCount": "1",
      "userScoreCount": "7",
      "userScoreTotalValue": 67,
      "userScoreAverValue": 9.57,
      "viewers": {
        "firstViewers": [
          {
            "viewCount": null,
            "lastWatchedDate": "2020-08-18T13:43:48.351Z",
            "user": {
              "_id": "Mr2iZwnD9fJcSw989",
              "displayName": "DC16",
              "picture": "https://lh3.googleusercontent.com/a-/AOh14GiVlqLJTz0_nxv93H6t51RHmahhXpt4IlV5ui4XXA",
              "hideMe": false,
              "brief": null
            }
          }
        ],
        "recViewers": [
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-01T09:48:55.346Z",
            "user": null
          },
          {
            "viewCount": 2,
            "lastWatchedDate": "2026-06-06T11:01:05.126Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-02T09:37:50.517Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-04T07:21:31.009Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-04T19:31:34.625Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-05T15:13:19.870Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-06T02:31:42.218Z",
            "user": null
          },
          {
            "viewCount": 6,
            "lastWatchedDate": "2026-06-13T00:33:48.841Z",
            "user": {
              "_id": "6a1ea9a717bfcb03db91c07e",
              "displayName": "Rubies_2",
              "picture": "",
              "hideMe": false,
              "brief": ""
            }
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-09T15:04:49.501Z",
            "user": {
              "_id": "6483324e0f2e3bc2b892fdf7",
              "displayName": "New User",
              "picture": null,
              "hideMe": false,
              "brief": null
            }
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-11T17:59:33.872Z",
            "user": {
              "_id": "64204a925450af070a685fbf",
              "displayName": "Aryan Rai",
              "picture": "https://lh3.googleusercontent.com/a/AGNmyxZNqi8w_eovYjEWz9duAp4XENrEP6C2o4wB44G4=s96-c",
              "hideMe": false,
              "brief": null
            }
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T02:09:48.768Z",
            "user": null
          },
          {
            "viewCount": 1,
            "lastWatchedDate": "2026-06-12T21:27:43.250Z",
            "user": null
          }
        ]
      }
    },
    "episodeInfo": {
      "notes": "Flashing Before My Eyes<note-split>Soumatou (走馬灯)",
      "thumbnails": [
        "/data2/ep_tbs/2DT65AtWa7RehsaHF/1_dub.jpg",
        "/data2/ep_tbs/2DT65AtWa7RehsaHF/1_sub.jpg",
        "https://static.wixstatic.com/media/c43d7a_5e830315aa6346cebbbcb520779dc0aaf001.jpg",
        "https://static.wixstatic.com/media/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315f001.jpg"
      ],
      "vidInforssub": {
        "vidResolution": 1080,
        "vidPath": "/data2/media2/videos/2DT65AtWa7RehsaHF/sub/1.mp4",
        "vidSize": 185820676,
        "vidDuration": 1370.024
      },
      "uploadDates": {
        "sub": "2016-01-07T19:24:31.000Z",
        "dub": "2019-04-23T08:33:34.000Z"
      },
      "vidInforsdub": {
        "vidResolution": 1080,
        "vidPath": "/data2/media6/videos/2DT65AtWa7RehsaHF/dub/1.mp4",
        "vidSize": 179960866,
        "vidDuration": 1372.096
      },
      "vidInforsraw": null,
      "description": null
    },
    "versionFix": null
  }
}
```

### Server: Yt-mp4

```json
{
  "source_name": "Yt-mp4",
  "raw_source_url": "https://tools.fast4speed.rsvp/videos/2DT65AtWa7RehsaHF/sub/1?Authorization=3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld",
  "raw_expiry_or_token_fields": {
    "Authorization": [
      "3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld"
    ]
  },
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://tools.fast4speed.rsvp/videos/2DT65AtWa7RehsaHF/sub/1?Authorization=3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "status": 404,
    "final_url": "https://tools.fast4speed.rsvp/videos/2DT65AtWa7RehsaHF/sub/1?Authorization=3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:40 GMT",
      "Content-Type": "application/octet-stream",
      "Content-Length": "1",
      "Connection": "close",
      "Cache-Control": "private, max-age=0, no-store, no-cache, must-revalidate, post-check=0, pre-check=0",
      "Expires": "Thu, 01 Jan 1970 00:00:01 GMT",
      "Referrer-Policy": "same-origin",
      "X-Frame-Options": "SAMEORIGIN",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "xreop": "ace",
      "Server": "cloudflare",
      "CF-RAY": "a0ad5f130d3429f2-BOM"
    },
    "body_preview": " ",
    "error": "HTTPError: HTTP Error 404: Not Found",
    "looks_hls": false
  },
  "http_follow_redirect": {
    "url": "https://tools.fast4speed.rsvp/videos/2DT65AtWa7RehsaHF/sub/1?Authorization=3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "status": 404,
    "final_url": "https://tools.fast4speed.rsvp/videos/2DT65AtWa7RehsaHF/sub/1?Authorization=3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:40 GMT",
      "Content-Type": "application/octet-stream",
      "Content-Length": "1",
      "Connection": "close",
      "Cache-Control": "private, max-age=0, no-store, no-cache, must-revalidate, post-check=0, pre-check=0",
      "Expires": "Thu, 01 Jan 1970 00:00:01 GMT",
      "Referrer-Policy": "same-origin",
      "X-Frame-Options": "SAMEORIGIN",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "xreop": "ace",
      "Server": "cloudflare",
      "CF-RAY": "a0ad5f16dabc3a34-BOM"
    },
    "body_preview": " ",
    "error": "HTTPError: HTTP Error 404: Not Found",
    "looks_hls": false
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://tools.fast4speed.rsvp/videos/2DT65AtWa7RehsaHF/sub/1?Authorization=3_20260612113706_9a7cfbdd96d686f72bc00f9b_7b2fe6a26332bb0d84d2a22c714a7c411856f676_000_20260615113706_0034_dnld"
    ],
    "returncode": 1,
    "stderr": "ERROR: [generic] Unable to download webpage: HTTP Error 404: Not Found (caused by <HTTPError 404: Not Found>)\n",
    "stdout_bytes": 0
  }
}
```

### Server: Ok

```json
{
  "source_name": "Ok",
  "raw_source_url": "https://ok.ru/videoembed/2520546675346",
  "raw_expiry_or_token_fields": {},
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://ok.ru/videoembed/2520546675346",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
  },
  "http_follow_redirect": {
    "url": "https://ok.ru/videoembed/2520546675346",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "status": 200,
    "final_url": "https://ok.ru/videoembed/2520546675346",
    "response_headers": {
      "Server": "kittenx",
      "Date": "Sat, 13 Jun 2026 01:37:43 GMT",
      "Content-Type": "text/html;charset=UTF-8",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Vary": "Accept-Encoding",
      "Set-Cookie": "ss_wb=EUpaam8MDHPEtcyVPrR5YE7Cm6E8ycp3BYFETXUa-97CpTovJ2yM8o8hyKuinpLY9uvWkRIKxXy0Bgt1RlOF921DvdGntq-4zJQ; Secure; Max-Age=86400; HttpOnly; SameSite=None; Domain=ok.ru",
      "Content-Security-Policy": "default-src data: 'self' 'unsafe-inline' 'unsafe-eval' ok.ru *.ok.ru odnoklassniki.ru *.odnoklassniki.ru okcdn.ru http://*.okcdn.ru https://*.okcdn.ru mycdn.me http://*.mycdn.me https://*.mycdn.me http://st-ok.cdn-vk.ru https://st-ok.cdn-vk.ru http://st-ok-pts.cdn-vk.ru https://st-ok-pts.cdn-vk.ru wss://ad.mail.ru *.mail.ru *.imgsmail.ru *.mradx.net *.serving-sys.com *.googleapis.com *.gstatic.com www.google.com https://api-maps.yandex.ru yastatic.net yandex.st *.doubleverify.com *.adsafeprotected.com https://cdn.consentmanager.net https://football.sportmail.ru *.google.ru *.google.com *.googlesyndication.com *.yandex.ru static.dzeninfra.ru connect.ok.ru https://connect.ok.ru *.odkl.ru https://*.odkl.ru blob:;  script-src 'unsafe-inline' 'unsafe-eval' *.mail.ru https://*.mail.ru *.imgsmail.ru *.mradx.net ok.ru *.ok.ru odnoklassniki.ru *.odnoklassniki.ru okcdn.ru http://*.okcdn.ru https://*.okcdn.ru http://st-ok.cdn-vk.ru https://st-ok.cdn-vk.ru http://st-ok-pts.cdn-vk.ru https://st-ok-pts.cdn-vk.ru mycdn.me http://*.mycdn.me https://*.mycdn.me mc.yandex.ru an.yandex.ru yastatic.net yandex.st *.google-analytics.com api-maps.yandex.ru https://api-maps.yandex.ru https://clck.yandex.ru *.googleapis.com *.gstatic.com www.google.com www.youtube.com https://www.youtube.com *.ytimg.com https://*.ytimg.com *.doubleverify.com *.dvtps.com *.doubleclick.net *.googletagservices.com *.googlesyndication.com *.googleadservices.com *.goodgame.ru https://*.goodgame.ru https://*.moatads.com *.adlooxtracking.com *.adlooxtracking.ru *.adsafeprotected.com *.serving-sys.com *.serving-sys.ru *.weborama.fr *.weborama-tech.ru https://enterprise.api-maps.yandex.ru https://suggest-maps.yandex.ru https://*.hit.gemius.pl https://*.consentmanager.net https://gum.criteo.com https://football.sportmail.ru *.googletagmanager.com connect.facebook.net *.google.ru *.google.com *.googlesyndication.com yandex.ru static.dzeninfra.ru *.adtrafficquality.google *.odkl.ru https://*.odkl.ru appleid.cdn-apple.com;  worker-src blob: 'self';  connect-src * wss: blob: data:;  font-src * data: blob:; frame-src * blob: 'self';  img-src * data: blob: about:;  media-src * data: blob:;  object-src *;  report-uri /csp/report;",
      "Content-Security-Policy-Report-Only": "default-src data: blob: about: 'self' 'unsafe-inline' 'unsafe-eval' https: wss:; report-uri /csp/report?always;",
      "Last-Modified": "Sun, 20 Nov 2022 15:52:00 GMT",
      "Cache-Control": "no-store",
      "Pragma": "no-cache",
      "Expires": "Mon, 26 Jul 1997 05:00:00 GMT",
      "X-Trace-Id": "Db5GY4puFLc17IN60kEVVM_J3pt57A",
      "Server-Timing": "tid;desc=\"Db5GY4puFLc17IN60kEVVM_J3pt57A\",front;dur=18.934"
    },
    "body_preview": "<!DOCTYPE html>\n<html><head><!-- META START --><meta http-equiv=\"Content-Type\" content=\"text/html; charset=UTF-8\"></meta><meta http-equiv=\"X-UA-Compatible\" content=\"IE=edge\"></meta><title>Смотрите видео &quot;2DT65AtWa7RehsaHF_sub_1&quot; в ОК. Плеер Видео</title><meta http-equiv=\"Cache-Control\" content=\"no-cache\"></meta><meta http-equiv=\"Pragma\" content=\"no-cache\"></meta><meta http-equiv=\"Expires\" content=\"Mon, 26 Jul 1997 05:00:00 GMT\"></meta><meta name=\"referrer\" content=\"origin\"></meta><meta name=\"referrer\" content=\"no-referrer-when-downgrade\"></meta><meta name=\"v",
    "looks_hls": false
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://ok.ru/videoembed/2520546675346"
    ],
    "returncode": 1,
    "stderr": "ERROR: [Odnoklassniki] 2520546675346: Unable to download webpage: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')) (caused by TransportError(\"('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))\"))\n",
    "stdout_bytes": 0
  }
}
```

### Server: Ss-Hls

```json
{
  "source_name": "Ss-Hls",
  "raw_source_url": "https://streamsb.net/e/5wmn1wgrbvss.html",
  "raw_expiry_or_token_fields": {},
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://streamsb.net/e/5wmn1wgrbvss.html",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "status": 302,
    "final_url": "https://streamsb.net/e/5wmn1wgrbvss.html",
    "response_headers": {
      "cache-control": "max-age=0, private, must-revalidate",
      "connection": "close",
      "content-length": "11",
      "date": "Sat, 13 Jun 2026 01:37:47 GMT",
      "location": "http://ww1.streamsb.net",
      "server": "Cowboy",
      "set-cookie": "sid=7bc0a322-66c8-11f1-959a-7d0b426cdfd0; path=/; domain=.streamsb.net; expires=Thu, 01 Jul 2094 04:51:55 GMT; max-age=2147483647; secure; HttpOnly"
    },
    "body_preview": "Redirecting",
    "error": "HTTPError: HTTP Error 302: Found",
    "looks_hls": false
  },
  "http_follow_redirect": {
    "url": "https://streamsb.net/e/5wmn1wgrbvss.html",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "status": 200,
    "final_url": "https://streamsb.net/e/5wmn1wgrbvss.html",
    "response_headers": {
      "accept-ch": "Sec-CH-UA, Sec-CH-UA-Platform, Sec-CH-UA-Platform-Version, Sec-CH-UA-Mobile",
      "cache-control": "max-age=0, private, must-revalidate",
      "connection": "close",
      "content-length": "493",
      "content-type": "text/html; charset=utf-8",
      "date": "Sat, 13 Jun 2026 01:37:48 GMT",
      "server": "Cowboy",
      "set-cookie": "sid=7c488f39-66c8-11f1-a107-7d0b3cb18fc7; path=/; domain=.streamsb.net; expires=Thu, 01 Jul 2094 04:51:55 GMT; max-age=2147483647; secure; HttpOnly"
    },
    "body_preview": "<html><head><title>Loading...</title></head><body><script type='text/javascript'>window.location.replace('https://streamsb.net/e/5wmn1wgrbvss.html?ch=1&js=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJKb2tlbiIsImV4cCI6MTc4MTMyMTg2OCwiaWF0IjoxNzgxMzE0NjY4LCJpc3MiOiJKb2tlbiIsImpzIjoxLCJqdGkiOiIzMnM4MGc3ZHR1bDRyb2lxdWswbnZmODEiLCJuYmYiOjE3ODEzMTQ2NjgsInRzIjoxNzgxMzE0NjY4OTgzMTM0fQ.0GhDI5O-_pxp8qd5Ns9YCBrZb8VNWvzp5DBvTSf1gM8&sid=7c488f39-66c8-11f1-a107-7d0b3cb18fc7');</script></body></html>",
    "looks_hls": false
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://streamsb.net/e/5wmn1wgrbvss.html"
    ],
    "returncode": 1,
    "stderr": "ERROR: Unsupported URL: https://streamsb.net/e/5wmn1wgrbvss.html\n",
    "stdout_bytes": 0
  }
}
```

### Server: Mp4

```json
{
  "source_name": "Mp4",
  "raw_source_url": "https://mp4upload.com/embed-jw700v465vrm.html",
  "raw_expiry_or_token_fields": {},
  "decode_route": "No per-source decryption; URL is passed directly",
  "http_no_redirect": {
    "url": "https://mp4upload.com/embed-jw700v465vrm.html",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": false,
    "status": 301,
    "final_url": "https://mp4upload.com/embed-jw700v465vrm.html",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:52 GMT",
      "Content-Type": "text/html; charset=iso-8859-1",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Location": "https://www.mp4upload.com/embed-jw700v465vrm.html",
      "Server": "cloudflare",
      "Cf-Cache-Status": "DYNAMIC",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "Server-Timing": "cfEdge;dur=5,cfOrigin;dur=163",
      "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=nrXIXhVYiaLdFB32sVoapXgIyW6YEsD64WOm4N8v1MxRL%2BoK3a4whWGfWURAfIcR64kbV6EnbB6Ca502gKD3C6Rikb6xUsqgzvRcD4vD5Au%2FIQJP8dZiJ9R%2Bt4prX72ecUgNFnMOZxmSOnAZ\"}]}",
      "CF-RAY": "a0ad5f5fdc140884-SIN"
    },
    "body_preview": "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.01//EN\" \"http://www.w3.org/TR/html4/strict.dtd\">\n<html><head>\n<title>301 Moved Permanently</title>\n</head><body>\n<h1>Moved Permanently</h1>\n<p>The document has moved <a href=\"https://www.mp4upload.com/embed-jw700v465vrm.html\">here</a>.</p>\n<script defer src=\"https://static.cloudflareinsights.com/beacon.min.js/v833ccba57c9e4d2798f2e76cebdd09a11778172276447\" integrity=\"sha512-57MDmcccJXYtNnH+ZiBwzC4jb2rvgVCEokYN+L/nLlmO8rfYT/gIpW2A569iJ/3b+0UEasghjuZH/ma3wIs/EQ==\" data-cf-beacon='{\"version\":\"2024.11.0\",\"token\":\"328464446bd34ab3ba7bddcc28c2e3a6\",\"r\":1,\"se",
    "error": "HTTPError: HTTP Error 301: Moved Permanently",
    "looks_hls": false
  },
  "http_follow_redirect": {
    "url": "https://mp4upload.com/embed-jw700v465vrm.html",
    "referer": "",
    "request_headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Range": "bytes=0-0"
    },
    "follow_redirects": true,
    "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
  },
  "yt_dlp": {
    "command": [
      "yt-dlp",
      "-j",
      "--no-warnings",
      "https://mp4upload.com/embed-jw700v465vrm.html"
    ],
    "returncode": 1,
    "stderr": "ERROR: [generic] Unable to download webpage: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')) (caused by TransportError(\"('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))\"))\n",
    "stdout_bytes": 0
  }
}
```

### Server: Default

```json
{
  "source_name": "Default",
  "raw_source_url": "--175948514e4c4f57175b54575b5307515c050f5c0a0c0f0b0f0c0e590a0c0b5b0a0c0e0d0e0c0b0d0b0d0e0d0b0e0d010e080b0a0e0d0e0c0b080b0e0e0a0b080e0b0b0e0e0b0b0e0b0a0e0d0b0f0e0f0b5d0e0c0b0a0b090e0f0e0d0e0c0e0f0b0b0e0a0e080b0e0b0f0b0d0b0f0b0b0a0e0f590a0e0b0c0b0b0e0c0b0e0b0f0e0a0b5d0e0d0e0d0b080b0f0b0c0b0e0b0d0b0a0e0f0e0a0b0c0b5e0b080e0c0e0f0b5e0b0a0b0c0b0e0b5d0e080e0c0e0a0b5e0e0d0a0e0f590a0e0e5a0e0b0e0a0e5e0e0f0a010e0d0e0c0b0d0b0d0e0d0b0e0d010e080b0a0e0d0e0c0b080b0e0e0a0b080e0b0b0e0e0b0b0e0b0a0e0d0b0f0e0f0b5d0e0c0b0a0b090e0f0e0d0e0c0e0f0b0b0e0a0e080b0e0b0f0b0d0b0f0b0b0e080b0e0b0e0b0f0a000e5b0f0e0e090a0e0f590a0e0a590b0a0b5d0b0e0f0e0a590b090b0c0b0e0f0e0a590b0f0b0e0b5d0b0e0f0e0a590a0c0a590a0c0f0d0f0a0f0c0e0b0e0f0e5a0e0b0f0c0c5e0e0a0a0c0b5b0a0c0d090e5e0f5d0a0c0a590a0c0e0a0e0f0f0a0e0b0a0c0b5b0a0c0b0c0b0e0b0c0b080a5a0b0e0b080a5a0b0f0b0d0d0a0b0e0b0f0b5b0b0d0b090b5b0b0e0b0e0a000b0e0b0e0b0e0d5b0a0c0a590a0c0f0a0f0c0e0f0e000f0d0e590e0f0f0a0e5e0e010e000d0a0f5e0f0e0e0b0a0c0b5b0a0c0f0d0f0b0e0c0a0c0a590a0c0e5c0e0b0f5e0a0c0b5b0a0c0e0b0f0e0a5a0b0c0c0a0d0a0b080b0b0c0f0f0a0d090e0f0b090d0c0e0b0e5d0f0d0e0f0c5d0c080d010b0f0d010f0d0f0b0e0c0a0c0f5a",
  "raw_expiry_or_token_fields": {},
  "decode_route": "Per-source substitution cipher -> Clock JSON",
  "clock": {
    "decoded_path": "/apivtwo/clock.json?id=7d2473746a243c2465643535653659603265643036623063366336326537673e643231676564673362603637353733267a263433643637623e65653037343635326762343f3064673f3234363e6064623f65267a266b63626f672965643535653659603265643036623063366336326537673e64323167656467336260363735373360363637286c7661267a262a323e36762a313436762a37363e36762a242a2475727463676b63744f62243c24516f7e242a2462677263243c24343634302b36302b37355236373c35313c3636283636365c242a2472746768756a67726f6968527f7663243c24757364242a246d637f243c2463762b3442523033477251673154636e75674e40593759757364247b",
    "clock_url": "https://allanime.day/apivtwo/clock.json?id=7d2473746a243c2465643535653659603265643036623063366336326537673e643231676564673362603637353733267a263433643637623e65653037343635326762343f3064673f3234363e6064623f65267a266b63626f672965643535653659603265643036623063366336326537673e64323167656467336260363735373360363637286c7661267a262a323e36762a313436762a37363e36762a242a2475727463676b63744f62243c24516f7e242a2462677263243c24343634302b36302b37355236373c35313c3636283636365c242a2472746768756a67726f6968527f7663243c24757364242a246d637f243c2463762b3442523033477251673154636e75674e40593759757364247b",
    "status": 200,
    "final_url": "https://allanime.day/apivtwo/clock.json?id=7d2473746a243c2465643535653659603265643036623063366336326537673e643231676564673362603637353733267a263433643637623e65653037343635326762343f3064673f3234363e6064623f65267a266b63626f672965643535653659603265643036623063366336326537673e64323167656467336260363735373360363637286c7661267a262a323e36762a313436762a37363e36762a242a2475727463676b63744f62243c24516f7e242a2462677263243c24343634302b36302b37355236373c35313c3636283636365c242a2472746768756a67726f6968527f7663243c24757364242a246d637f243c2463762b3442523033477251673154636e75674e40593759757364247b",
    "response_headers": {
      "Date": "Sat, 13 Jun 2026 01:37:57 GMT",
      "Content-Type": "application/json",
      "Transfer-Encoding": "chunked",
      "Connection": "close",
      "Server": "cloudflare",
      "Nel": "{\"report_to\":\"cf-nel\",\"success_fraction\":0.0,\"max_age\":604800}",
      "X-Powered-By": "Express",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=150",
      "Vary": "Accept-Encoding",
      "Report-To": "{\"group\":\"cf-nel\",\"max_age\":604800,\"endpoints\":[{\"url\":\"https://a.nel.cloudflare.com/report/v4?s=1gUEiKtsRaYZvS2IniQHbUF6o%2FYg0RwXrDMkbNDUWnUG9cYJC6%2BKI9tmo4upsYPZqgpUeaXaUuQeYzhHzQSLAp8nCcbIpAdR%2B6P%2FvqdRpK1%2FrkkKGpeZyXOQ%2FGTT4MLWw2W1L1cfjzKsuNg%3D\"}]}",
      "Last-Modified": "Sat, 13 Jun 2026 01:37:57 GMT",
      "Cf-Cache-Status": "MISS",
      "Server-Timing": "cfEdge;dur=11,cfOrigin;dur=592",
      "CF-RAY": "a0ad5f780f4c3a47-BOM",
      "alt-svc": "h3=\":443\"; ma=86400"
    },
    "body": {
      "links": [
        {
          "link": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "hls": true,
          "resolutionStr": "Hls",
          "fromCache": "2026-06-13T01:37:56.915Z"
        }
      ]
    }
  },
  "clock_link_probes": [
    {
      "item": {
        "link": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
        "hls": true,
        "resolutionStr": "Hls",
        "fromCache": "2026-06-13T01:37:56.915Z"
      },
      "expiry_or_token_fields": {},
      "probes": [
        {
          "url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "referer": "",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0"
          },
          "follow_redirects": true,
          "status": 200,
          "final_url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "response_headers": {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "openresty/1.21.4.1",
            "Date": "Sat, 13 Jun 2026 01:36:48 GMT",
            "Last-Modified": "Sun, 19 Nov 2000 08:52:00 GMT",
            "Cache-Control": "public, max-age=86400, immutable",
            "Access-Control-Allow-Origin": "*",
            "Via": "1.1 google, 1.1 fb6514ed0fa65e8962789d347bfecb50.cloudfront.net (CloudFront)",
            "X-Cache": "Hit from cloudfront",
            "X-Amz-Cf-Pop": "BOM78-P4",
            "Alt-Svc": "h3=\":443\"; ma=86400",
            "X-Amz-Cf-Id": "NAfM9ccXkgnSqbOLpNzzbY0U2WEPbFtQlT2CIXIVZU23bzoBotHkLQ==",
            "Age": "69"
          },
          "body_preview": "#EXTM3U\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=752723,RESOLUTION=854x480,FRAME-RATE=23.974,CODECS=\"avc1.4d401f,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/480p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1383273,RESOLUTION=1280x720,FRAME-RATE=23.974,CODECS=\"avc1.640029,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/720p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2278136,RESOLUTION=1920x1080,FRAME-RATE=23.974,CODECS=\"av",
          "looks_hls": true
        },
        {
          "url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "referer": "https://allmanga.to/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://allmanga.to/"
          },
          "follow_redirects": true,
          "status": 200,
          "final_url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "response_headers": {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "openresty/1.21.4.1",
            "Date": "Fri, 12 Jun 2026 02:07:49 GMT",
            "Last-Modified": "Sun, 19 Nov 2000 08:52:00 GMT",
            "Cache-Control": "public, max-age=86400, immutable",
            "Access-Control-Allow-Origin": "*",
            "Via": "1.1 google, 1.1 430b52f5283b2b0c6d9bd4418733e4e6.cloudfront.net (CloudFront)",
            "X-Cache": "Hit from cloudfront",
            "X-Amz-Cf-Pop": "MCI50-P3",
            "Alt-Svc": "h3=\":443\"; ma=86400",
            "X-Amz-Cf-Id": "r9AEllrugns_BvRhsm2_zI0r_RpdGaajdcvu28Wkpc3JKOhqvP1FPw==",
            "Age": "84610"
          },
          "body_preview": "#EXTM3U\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=752723,RESOLUTION=854x480,FRAME-RATE=23.974,CODECS=\"avc1.4d401f,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/480p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1383273,RESOLUTION=1280x720,FRAME-RATE=23.974,CODECS=\"avc1.640029,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/720p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2278136,RESOLUTION=1920x1080,FRAME-RATE=23.974,CODECS=\"av",
          "looks_hls": true
        },
        {
          "url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "referer": "https://gogoanime.tel/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://gogoanime.tel/"
          },
          "follow_redirects": true,
          "status": 200,
          "final_url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "response_headers": {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "openresty/1.21.4.1",
            "Date": "Sat, 13 Jun 2026 01:36:48 GMT",
            "Last-Modified": "Sun, 19 Nov 2000 08:52:00 GMT",
            "Cache-Control": "public, max-age=86400, immutable",
            "Access-Control-Allow-Origin": "*",
            "Via": "1.1 google, 1.1 470da146cea57daec736ce1623056a0a.cloudfront.net (CloudFront)",
            "X-Cache": "Hit from cloudfront",
            "X-Amz-Cf-Pop": "BOM78-P4",
            "Alt-Svc": "h3=\":443\"; ma=86400",
            "X-Amz-Cf-Id": "4j25-vmlu5ZC-yGdMDjV6zT2xYAhMOp4eHTCCsvy5dz1IUIn3eNrIg==",
            "Age": "71"
          },
          "body_preview": "#EXTM3U\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=752723,RESOLUTION=854x480,FRAME-RATE=23.974,CODECS=\"avc1.4d401f,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/480p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1383273,RESOLUTION=1280x720,FRAME-RATE=23.974,CODECS=\"avc1.640029,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/720p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2278136,RESOLUTION=1920x1080,FRAME-RATE=23.974,CODECS=\"av",
          "looks_hls": true
        },
        {
          "url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "referer": "https://anitaku.pe/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://anitaku.pe/"
          },
          "follow_redirects": true,
          "status": 200,
          "final_url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "response_headers": {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "openresty/1.21.4.1",
            "Date": "Sat, 13 Jun 2026 01:36:48 GMT",
            "Last-Modified": "Sun, 19 Nov 2000 08:52:00 GMT",
            "Cache-Control": "public, max-age=86400, immutable",
            "Access-Control-Allow-Origin": "*",
            "Via": "1.1 google, 1.1 987a1f94c02320833af541bf3e9dcdf2.cloudfront.net (CloudFront)",
            "X-Cache": "Hit from cloudfront",
            "X-Amz-Cf-Pop": "BOM78-P4",
            "Alt-Svc": "h3=\":443\"; ma=86400",
            "X-Amz-Cf-Id": "bloKyjKsZO6HDYluhRX2f6CHoTFutVl3v3LS4imdllDfBh0h89TmCA==",
            "Age": "72"
          },
          "body_preview": "#EXTM3U\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=752723,RESOLUTION=854x480,FRAME-RATE=23.974,CODECS=\"avc1.4d401f,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/480p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1383273,RESOLUTION=1280x720,FRAME-RATE=23.974,CODECS=\"avc1.640029,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/720p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2278136,RESOLUTION=1920x1080,FRAME-RATE=23.974,CODECS=\"av",
          "looks_hls": true
        },
        {
          "url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "referer": "https://yugenanime.tv/",
          "request_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Range": "bytes=0-0",
            "Referer": "https://yugenanime.tv/"
          },
          "follow_redirects": true,
          "status": 200,
          "final_url": "https://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/,480p,720p,1080p,/mp4/file.mp4.urlset/master.m3u8",
          "response_headers": {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Transfer-Encoding": "chunked",
            "Connection": "close",
            "Server": "openresty/1.21.4.1",
            "Date": "Sat, 13 Jun 2026 01:36:48 GMT",
            "Last-Modified": "Sun, 19 Nov 2000 08:52:00 GMT",
            "Cache-Control": "public, max-age=86400, immutable",
            "Access-Control-Allow-Origin": "*",
            "Via": "1.1 google, 1.1 9f3f4cadb8601c4fc66883a04796dbd0.cloudfront.net (CloudFront)",
            "X-Cache": "Hit from cloudfront",
            "X-Amz-Cf-Pop": "BOM78-P4",
            "Alt-Svc": "h3=\":443\"; ma=86400",
            "X-Amz-Cf-Id": "WnZYWLgQgph3OcmtC5mYts1TWqJ8Mis-2AuoT7iAFeESk7qJIP-Onw==",
            "Age": "73"
          },
          "body_preview": "#EXTM3U\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=752723,RESOLUTION=854x480,FRAME-RATE=23.974,CODECS=\"avc1.4d401f,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/480p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1383273,RESOLUTION=1280x720,FRAME-RATE=23.974,CODECS=\"avc1.640029,mp4a.40.2\"\nhttps://repackager.wixmp.com/video.wixstatic.com/video/cb33c0_f4cb60d6e0e04c1a8b47acba5df01315/720p/mp4/file.mp4/index-v1-a1.m3u8\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=2278136,RESOLUTION=1920x1080,FRAME-RATE=23.974,CODECS=\"av",
          "looks_hls": true
        }
      ]
    }
  ]
}
```

## Ok Working vs Failing Comparison

```json
[
  {
    "episode": "Slime Season 4 EP 8",
    "raw_url": "https://ok.ru/videoembed/14469506337426",
    "expiry_or_token_fields": {},
    "http_no_redirect": {
      "url": "https://ok.ru/videoembed/14469506337426",
      "referer": "",
      "request_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Range": "bytes=0-0"
      },
      "follow_redirects": false,
      "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
    },
    "http_follow_redirect": {
      "url": "https://ok.ru/videoembed/14469506337426",
      "referer": "",
      "request_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Range": "bytes=0-0"
      },
      "follow_redirects": true,
      "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
    },
    "yt_dlp": {
      "command": [
        "yt-dlp",
        "-j",
        "--no-warnings",
        "https://ok.ru/videoembed/14469506337426"
      ],
      "returncode": 1,
      "stderr": "ERROR: [Odnoklassniki] 14469506337426: Unable to download webpage: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')) (caused by TransportError(\"('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))\"))\n",
      "stdout_bytes": 0
    }
  },
  {
    "episode": "ERASED EP 1",
    "raw_url": "https://ok.ru/videoembed/2520546675346",
    "expiry_or_token_fields": {},
    "http_no_redirect": {
      "url": "https://ok.ru/videoembed/2520546675346",
      "referer": "",
      "request_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Range": "bytes=0-0"
      },
      "follow_redirects": false,
      "error": "URLError: <urlopen error [Errno 104] Connection reset by peer>"
    },
    "http_follow_redirect": {
      "url": "https://ok.ru/videoembed/2520546675346",
      "referer": "",
      "request_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Range": "bytes=0-0"
      },
      "follow_redirects": true,
      "status": 200,
      "final_url": "https://ok.ru/videoembed/2520546675346",
      "response_headers": {
        "Server": "kittenx",
        "Date": "Sat, 13 Jun 2026 01:37:43 GMT",
        "Content-Type": "text/html;charset=UTF-8",
        "Transfer-Encoding": "chunked",
        "Connection": "close",
        "Vary": "Accept-Encoding",
        "Set-Cookie": "ss_wb=EUpaam8MDHPEtcyVPrR5YE7Cm6E8ycp3BYFETXUa-97CpTovJ2yM8o8hyKuinpLY9uvWkRIKxXy0Bgt1RlOF921DvdGntq-4zJQ; Secure; Max-Age=86400; HttpOnly; SameSite=None; Domain=ok.ru",
        "Content-Security-Policy": "default-src data: 'self' 'unsafe-inline' 'unsafe-eval' ok.ru *.ok.ru odnoklassniki.ru *.odnoklassniki.ru okcdn.ru http://*.okcdn.ru https://*.okcdn.ru mycdn.me http://*.mycdn.me https://*.mycdn.me http://st-ok.cdn-vk.ru https://st-ok.cdn-vk.ru http://st-ok-pts.cdn-vk.ru https://st-ok-pts.cdn-vk.ru wss://ad.mail.ru *.mail.ru *.imgsmail.ru *.mradx.net *.serving-sys.com *.googleapis.com *.gstatic.com www.google.com https://api-maps.yandex.ru yastatic.net yandex.st *.doubleverify.com *.adsafeprotected.com https://cdn.consentmanager.net https://football.sportmail.ru *.google.ru *.google.com *.googlesyndication.com *.yandex.ru static.dzeninfra.ru connect.ok.ru https://connect.ok.ru *.odkl.ru https://*.odkl.ru blob:;  script-src 'unsafe-inline' 'unsafe-eval' *.mail.ru https://*.mail.ru *.imgsmail.ru *.mradx.net ok.ru *.ok.ru odnoklassniki.ru *.odnoklassniki.ru okcdn.ru http://*.okcdn.ru https://*.okcdn.ru http://st-ok.cdn-vk.ru https://st-ok.cdn-vk.ru http://st-ok-pts.cdn-vk.ru https://st-ok-pts.cdn-vk.ru mycdn.me http://*.mycdn.me https://*.mycdn.me mc.yandex.ru an.yandex.ru yastatic.net yandex.st *.google-analytics.com api-maps.yandex.ru https://api-maps.yandex.ru https://clck.yandex.ru *.googleapis.com *.gstatic.com www.google.com www.youtube.com https://www.youtube.com *.ytimg.com https://*.ytimg.com *.doubleverify.com *.dvtps.com *.doubleclick.net *.googletagservices.com *.googlesyndication.com *.googleadservices.com *.goodgame.ru https://*.goodgame.ru https://*.moatads.com *.adlooxtracking.com *.adlooxtracking.ru *.adsafeprotected.com *.serving-sys.com *.serving-sys.ru *.weborama.fr *.weborama-tech.ru https://enterprise.api-maps.yandex.ru https://suggest-maps.yandex.ru https://*.hit.gemius.pl https://*.consentmanager.net https://gum.criteo.com https://football.sportmail.ru *.googletagmanager.com connect.facebook.net *.google.ru *.google.com *.googlesyndication.com yandex.ru static.dzeninfra.ru *.adtrafficquality.google *.odkl.ru https://*.odkl.ru appleid.cdn-apple.com;  worker-src blob: 'self';  connect-src * wss: blob: data:;  font-src * data: blob:; frame-src * blob: 'self';  img-src * data: blob: about:;  media-src * data: blob:;  object-src *;  report-uri /csp/report;",
        "Content-Security-Policy-Report-Only": "default-src data: blob: about: 'self' 'unsafe-inline' 'unsafe-eval' https: wss:; report-uri /csp/report?always;",
        "Last-Modified": "Sun, 20 Nov 2022 15:52:00 GMT",
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Expires": "Mon, 26 Jul 1997 05:00:00 GMT",
        "X-Trace-Id": "Db5GY4puFLc17IN60kEVVM_J3pt57A",
        "Server-Timing": "tid;desc=\"Db5GY4puFLc17IN60kEVVM_J3pt57A\",front;dur=18.934"
      },
      "body_preview": "<!DOCTYPE html>\n<html><head><!-- META START --><meta http-equiv=\"Content-Type\" content=\"text/html; charset=UTF-8\"></meta><meta http-equiv=\"X-UA-Compatible\" content=\"IE=edge\"></meta><title>Смотрите видео &quot;2DT65AtWa7RehsaHF_sub_1&quot; в ОК. Плеер Видео</title><meta http-equiv=\"Cache-Control\" content=\"no-cache\"></meta><meta http-equiv=\"Pragma\" content=\"no-cache\"></meta><meta http-equiv=\"Expires\" content=\"Mon, 26 Jul 1997 05:00:00 GMT\"></meta><meta name=\"referrer\" content=\"origin\"></meta><meta name=\"referrer\" content=\"no-referrer-when-downgrade\"></meta><meta name=\"v",
      "looks_hls": false
    },
    "yt_dlp": {
      "command": [
        "yt-dlp",
        "-j",
        "--no-warnings",
        "https://ok.ru/videoembed/2520546675346"
      ],
      "returncode": 1,
      "stderr": "ERROR: [Odnoklassniki] 2520546675346: Unable to download webpage: ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer')) (caused by TransportError(\"('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))\"))\n",
      "stdout_bytes": 0
    }
  }
]
```

## HLS Handling Conclusion

- URL, response Content-Type, response preview, and yt-dlp protocol fields above identify whether Fm-Hls/Ss-Hls resolve to HLS.
- The CLI labels Clock links containing `.m3u8` as `hls`.
- Generic embeds depend on yt-dlp to expose a playable URL and protocol.
- Desktop mpv supports `.m3u8` natively. Android direct-safe mode is false for HLS/external streams, so header-dependent streams use the local proxy when headers are present.

## No Changes Made

This was a read-only diagnostic run. `allmanga-cli`, config, history, preferences, and caches were not modified by this script.
