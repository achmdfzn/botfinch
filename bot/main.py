"""Entry point Finch. Cara jalanin:  python main.py

Jalankan dari folder root project (discord-bot-finch/).
Config (.env) otomatis dibaca oleh src/config.py saat di-import.
"""
import asyncio
import logging
import sys

from src import config  # ringan: cuma butuh python-dotenv


def setup_logging() -> None:
    import os

    # Pastikan folder logs ada sebelum FileHandler dibuat
    os.makedirs("logs", exist_ok=True)

    # Set console encoding to UTF-8 on Windows if possible
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/finch.log", encoding="utf-8"),
        ],
    )
    # discord.py terlalu berisik di level INFO — turunkan ke WARNING
    logging.getLogger("discord").setLevel(logging.WARNING)


def main() -> None:
    # Reconfigure stdout ke UTF-8 lebih awal biar print ❌ tidak crash di Windows cp1252
    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    masalah = config.settings.validate()
    if masalah:
        try:
            print("❌ " + "\n❌ ".join(masalah))
        except UnicodeEncodeError:
            print("[X] " + "\n[X] ".join(masalah))
        sys.exit(1)

    # Import berat (discord.py) setelah config valid — biar pesan error
    # config tetap ramah walau dependency belum ter-install.
    from src.bot import FinchBot

    setup_logging()
    bot = FinchBot()
    try:
        asyncio.run(bot.start(config.settings.token))
    except Exception as exc:
        log = logging.getLogger("finch")
        log.exception("Bot crash: %s", exc)
        print("❌ Bot gagal jalan: %s" % exc)
        sys.exit(1)


if __name__ == "__main__":
    main()