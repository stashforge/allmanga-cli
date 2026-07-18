"""AllAnime payload and clock URL decoding."""

import base64
import hashlib
import json
import subprocess
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_ALLANIME_KEY_HEX = "cf4777b5778aeadc9449e12769ea545d00c43cd8ff65d482364586cde204f359"


def decrypt_tobeparsed(encoded):
    key = _ALLANIME_KEY_HEX
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


def generate_aa_req() -> str:
    epoch = 4130
    build_id = "12"
    query_hash = "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"
    allanime_key = bytes.fromhex(_ALLANIME_KEY_HEX)

    ts = int(time.time() / 300) * 300 * 1000

    payload_iv = f"{epoch}:{build_id}:{query_hash}:{ts}"
    payload_dict = {
        "v": 1,
        "ts": ts,
        "epoch": epoch,
        "buildId": build_id,
        "qh": query_hash
    }
    payload_json = json.dumps(payload_dict, separators=(',', ':'))

    iv = hashlib.sha256(payload_iv.encode('utf-8')).digest()[:12]

    aesgcm = AESGCM(allanime_key)
    encrypted = aesgcm.encrypt(iv, payload_json.encode('utf-8'), None)

    result = b'\x01' + iv + encrypted
    return base64.b64encode(result).decode('ascii')
