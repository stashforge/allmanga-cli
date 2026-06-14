"""AllAnime payload and clock URL decoding."""

import base64
import hashlib
import subprocess


def decrypt_tobeparsed(encoded):
    key = hashlib.sha256(b"Xot36i3lK3:v1").hexdigest()
    try:
        encrypted = base64.b64decode(encoded)
    except Exception:
        return None
    if len(encrypted) < 30:
        return None
    iv = encrypted[1:13].hex() + "00000002"
    ciphertext = encrypted[13:len(encrypted) - 16]
    command = [
        "openssl", "enc", "-d", "-aes-256-ctr",
        "-K", key, "-iv", iv, "-nosalt", "-nopad",
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        output, _ = process.communicate(input=ciphertext)
        if process.returncode != 0:
            return None
        return output.decode("utf-8", errors="ignore")
    except Exception:
        return None
