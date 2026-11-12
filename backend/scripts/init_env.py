"""
.env dosyasını yoksa .env.example'dan oluşturur; gizli anahtar ve ilk yönetici şifresini rastgele üretir.
Var olan .env dosyasına dokunmaz.
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    target, example = ROOT / ".env", ROOT / ".env.example"
    if target.exists():
        print(".env zaten var; değiştirilmedi.")
        return 0
    password = secrets.token_urlsafe(12)
    content = example.read_text(encoding="utf-8")
    content = content.replace("HKY_SECRET_KEY=", f"HKY_SECRET_KEY={secrets.token_urlsafe(48)}", 1)
    content = content.replace("ADMIN_PASSWORD=", f"ADMIN_PASSWORD={password}", 1)
    target.write_text(content, encoding="utf-8")
    print(f".env oluşturuldu. İlk giriş: admin@hky.local / {password}")
    print("Bu şifreyi not edin; ilk girişten sonra .env içindeki ADMIN_PASSWORD satırını silebilirsiniz.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
