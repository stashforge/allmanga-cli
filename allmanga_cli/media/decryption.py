"""AllAnime payload and clock URL decoding."""

import base64
import hashlib
import json
import subprocess
import time


import base64
import hashlib
import json

_ALLANIME_PASSPHRASE = b"Xot36i3lK3:v1"

def decrypt_tobeparsed(encoded):
    key = hashlib.sha256(_ALLANIME_PASSPHRASE).digest()
    try:
        encrypted = base64.b64decode(encoded)
    except Exception:
        return None
    if len(encrypted) < 30:
        return None
        
    iv12 = encrypted[1:13]
    ciphertext = encrypted[13:]
    
    # Counter for AES-CTR: iv12 + 00 00 00 02
    nonce = iv12 + b'\x00\x00\x00\x02'
    
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(ciphertext) + decryptor.finalize()
        return decrypted.decode("utf-8", errors="ignore")
    except Exception:
        pass
        
    for lib in ("Cryptodome", "Crypto"):
        try:
            AES = __import__(f"{lib}.Cipher", fromlist=["AES"]).AES
            from Crypto.Util import Counter
            ctr = Counter.new(128, initial_value=int.from_bytes(nonce, byteorder="big"))
            cipher = AES.new(key, AES.MODE_CTR, counter=ctr)
            decrypted = cipher.decrypt(ciphertext)
            return decrypted.decode("utf-8", errors="ignore")
        except ImportError:
            continue
        except Exception as exc:
            import sys
            sys.stderr.write(f"\\n[DEBUG] {lib} decryption failed: {exc}\\n")
            sys.stderr.flush()
            continue
            
    return None
