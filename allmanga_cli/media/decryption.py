"""AllAnime payload and clock URL decoding."""

import base64
import hashlib
import json
import subprocess
import time


_ALLANIME_KEY_HEX = "ff102360a5065bb72fc128f7efa5042dbf4db582e5c58754078265926a76bfd8"


def decrypt_tobeparsed(encoded):
    key = bytes.fromhex(_ALLANIME_KEY_HEX)
    try:
        encrypted = base64.b64decode(encoded)
    except Exception:
        return None
    if len(encrypted) < 30:
        return None
        
    iv = encrypted[1:13]
    # The ciphertext and auth tag are the remainder
    ciphertext_with_tag = encrypted[13:]
    
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(iv, ciphertext_with_tag, None)
        return decrypted.decode("utf-8", errors="ignore")
    except Exception:
        pass
        
    for lib in ("Cryptodome", "Crypto"):
        try:
            AES = __import__(f"{lib}.Cipher", fromlist=["AES"]).AES
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
            decrypted = cipher.decrypt_and_verify(ciphertext_with_tag[:-16], ciphertext_with_tag[-16:])
            return decrypted.decode("utf-8", errors="ignore")
        except ImportError:
            continue
        except Exception as exc:
            import sys
            sys.stderr.write(f"\n[DEBUG] {lib} decryption failed: {exc}\n")
            sys.stderr.flush()
            continue
            
    return None
def generate_aa_req() -> str:
    has_crypto = False
    last_exc = None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        has_crypto = True
    except Exception as exc:
        last_exc = exc
        
    if not has_crypto:
        for lib in ("Cryptodome", "Crypto"):
            try:
                __import__(f"{lib}.Cipher.AES")
                has_crypto = True
                break
            except Exception as exc:
                last_exc = exc

    if not has_crypto:
        from ..core.api import ProviderDependencyError
        raise ProviderDependencyError(
            f"\n\033[91m[ERROR] AllAnime playback requires a cryptography library.\n"
            f"        Failed to import 'cryptography', 'pycryptodomex', or 'pycryptodome':\n"
            f"        {last_exc}\n\n"
            f"        Please install it with your package manager or run: pipx inject allmanga-cli pycryptodomex\033[0m\n"
        )

    epoch = 6885
    build_id = "64"
    query_hash = "f4662f4b7510b26795dd53ef824a0bf1740fbbc5d1273fab18222ac831bca8d0"
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

    payload_bytes = payload_json.encode('utf-8')

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(allanime_key)
        encrypted = aesgcm.encrypt(iv, payload_bytes, None)
    except ImportError:
        encrypted = None
        for lib in ("Cryptodome", "Crypto"):
            try:
                AES = __import__(f"{lib}.Cipher", fromlist=["AES"]).AES
                cipher = AES.new(allanime_key, AES.MODE_GCM, nonce=iv)
                ciphertext, tag = cipher.encrypt_and_digest(payload_bytes)
                encrypted = ciphertext + tag
                break
            except ImportError:
                continue
        if encrypted is None:
            raise RuntimeError("No supported cryptography library found for encryption")

    result = b'\x01' + iv + encrypted
    return base64.b64encode(result).decode('ascii')
