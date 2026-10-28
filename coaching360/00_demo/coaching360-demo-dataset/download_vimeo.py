#!/usr/bin/env python3
"""Download a Vimeo video (including unlisted links with a hash) using yt-dlp.

Usage:
    pip install yt-dlp
    python3 download_vimeo.py [URL] [--out DIR] [--cookies-from-browser chrome]

The tracking/turnstile query string Vimeo appends to share links is stripped;
only the video id and the unlisted hash are needed.
"""
import argparse
import re
import sys

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp is not installed. Run: pip install yt-dlp")

DEFAULT_URL = "https://vimeo.com/1225614257/c9d16f7d98"


def clean_url(url: str) -> str:
    """Turn a Vimeo share link into a player URL, which works without login.

    The vimeo.com page URL requires a logged-in session for unlisted videos;
    player.vimeo.com/video/<id>?h=<hash> does not.
    """
    m = re.search(r"vimeo\.com/(?:video/)?(\d+)(?:/([0-9a-f]+)|.*[?&]h=([0-9a-f]+))?", url)
    if not m:
        return url
    video_id, path_hash, query_hash = m.groups()
    unlisted_hash = path_hash or query_hash
    return f"https://player.vimeo.com/video/{video_id}" + (f"?h={unlisted_hash}" if unlisted_hash else "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--out", default="videos", help="output directory (default: videos)")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER",
                        help="use your logged-in browser session (chrome, safari, firefox...) "
                             "if the video requires login")
    args = parser.parse_args()

    url = clean_url(args.url)
    print(f"Downloading {url}")

    opts = {
        "outtmpl": f"{args.out}/%(title)s [%(id)s].%(ext)s",
        "format": "bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "http_headers": {"Referer": "https://vimeo.com/"},
    }
    if args.cookies_from_browser:
        opts["cookiesfrombrowser"] = (args.cookies_from_browser,)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            sys.exit(ydl.download([url]))
    except yt_dlp.utils.DownloadError:
        # yt-dlp already printed the error message
        sys.exit("Download failed. If login is required, retry with --cookies-from-browser chrome")


if __name__ == "__main__":
    main()
