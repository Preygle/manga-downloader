"""mangabinder command line: download | convert | merge | cbz | web | gui."""

import argparse
import multiprocessing
import sys

from mangabinder import REPO_URL, __version__
from mangabinder.paths import default_library


def _setup_streams():
    # Line-buffered, never crash on characters the console can't show
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass


def _positive_float(value):
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def cmd_download(args):
    from mangabinder.downloader import DownloadError, download
    try:
        result = download(args.url, pattern=args.pattern, library=args.library, threads=args.threads,
                          start=args.start, resume=not args.fresh)
    except DownloadError as exc:
        print(f"[!] {exc}")
        return 1
    if args.convert or args.volumes:
        print("\n--- Converting chapters to PDF ---")
        _convert(result.folder, volumes=args.volumes, title=args.title)
    return 1 if result.failed else 0


def _convert(folder, volumes=False, title=None, workers=None, overwrite=False):
    from mangabinder.convert import DEFAULT_WORKERS, convert_folder
    output = convert_folder(folder, workers=workers or DEFAULT_WORKERS, overwrite=overwrite)
    if volumes:
        print("\n--- Merging chapters into volumes ---")
        from mangabinder.volumes import merge_into_volumes
        return bool(merge_into_volumes(output, title=title))
    return True


def cmd_convert(args):
    try:
        ok = _convert(args.folder, volumes=args.volumes, title=args.title,
                      workers=args.workers, overwrite=args.overwrite)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        return 1
    return 0 if ok else 1


def cmd_merge(args):
    from mangabinder.volumes import merge_into_volumes
    result = merge_into_volumes(args.folder, output_dir=args.output, title=args.title,
                                series_id=args.series_id, source=args.source, dry_run=args.dry_run,
                                use_cache=not args.no_cache, overwrite=args.overwrite)
    return 0 if (result or args.dry_run) else 1


def cmd_cbz(args):
    from mangabinder.cbz import cbz_folder
    try:
        cbz_folder(args.folder, args.output, workers=args.workers, overwrite=args.overwrite,
                   dpi=args.dpi, split_spreads=not args.no_split, jpeg_quality=args.quality)
    except FileNotFoundError as exc:
        print(f"[!] {exc}")
        return 1
    return 0


def cmd_web(args):
    from mangabinder.web import serve
    return serve(args.library, port=args.port, open_browser=not args.no_browser, host=args.host)


def cmd_gui(args):
    from mangabinder.gui import main as gui_main
    gui_main()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mangabinder",
        description="Download manga chapters, convert them to PDF, bind them into volumes and export CBZ.",
        epilog=f"Run 'mangabinder web' for the browser interface. Docs: {REPO_URL}",
    )
    parser.add_argument("--version", action="version", version=f"mangabinder {__version__}")
    sub = parser.add_subparsers(title="commands", metavar="<command>")

    p = sub.add_parser("download", help="download every chapter from a manga site",
                       description="Download every chapter linked from a manga site's series page.")
    p.add_argument("url", help="series page that links to every chapter")
    p.add_argument("-p", "--pattern", default="",
                   help="text every chapter link contains, e.g. /manga/title-chapter- "
                        "(default: detect links like .../chapter-12)")
    p.add_argument("-l", "--library", default=".", help="where to create the download folder (default: here)")
    p.add_argument("-t", "--threads", type=int, default=16, help="chapters downloaded in parallel (default 16)")
    p.add_argument("-s", "--start", type=_positive_float, default=None, help="skip chapters before this number")
    p.add_argument("--fresh", action="store_true", help="ignore earlier progress and download everything again")
    p.add_argument("--convert", action="store_true", help="convert the chapters to PDF afterwards")
    p.add_argument("--volumes", action="store_true", help="convert, then merge the PDFs into volumes")
    p.add_argument("--title", default=None, help="series title for the volume lookup")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("convert", help="turn downloaded chapter folders into PDFs",
                       description="Build <folder>_pdf/<chapter>.pdf from each chapter's images.")
    p.add_argument("folder", help="download folder containing one sub-folder per chapter")
    p.add_argument("--volumes", action="store_true", help="also merge the chapter PDFs into volumes")
    p.add_argument("--title", default=None, help="series title for the volume lookup")
    p.add_argument("--workers", type=int, default=None, help="parallel processes (default: half your CPUs)")
    p.add_argument("--overwrite", action="store_true", help="rebuild PDFs that are already up to date")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("merge", help="bind chapter PDFs into volume PDFs",
                       description="Merge chapter PDFs into volumes using a chapter->volume map "
                                   "looked up on MangaDex / AniList.")
    p.add_argument("folder", help="folder of chapter PDFs (e.g. example.com_pdf)")
    p.add_argument("-o", "--output", default=None, help="output folder (default: <folder>_volumes)")
    p.add_argument("--title", default=None, help="series title to look up (default: guessed from file names)")
    p.add_argument("--series-id", default=None, help="use this MangaDex/AniList id instead of searching")
    p.add_argument("--source", default="mangadex", choices=["mangadex", "anilist"],
                   help="which site --series-id belongs to")
    p.add_argument("--dry-run", action="store_true", help="print the volume plan without writing files")
    p.add_argument("--overwrite", action="store_true", help="rebuild volumes that already exist")
    p.add_argument("--no-cache", action="store_true", help="ignore the cached lookup")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("cbz", help="convert PDFs to CBZ comic archives",
                       description="Convert every PDF in a folder to a CBZ, splitting two-page spreads.")
    p.add_argument("folder", help="folder of PDFs (chapters or volumes)")
    p.add_argument("-o", "--output", default=None, help="output folder (default: <folder>_cbz)")
    p.add_argument("--dpi", type=int, default=150, help="render resolution (default 150)")
    p.add_argument("--quality", type=int, default=85, help="JPEG quality 1-95 (default 85)")
    p.add_argument("--no-split", action="store_true", help="keep two-page spreads as one image")
    p.add_argument("--workers", type=int, default=2, help="parallel processes (default 2)")
    p.add_argument("--overwrite", action="store_true", help="rebuild CBZ files that already exist")
    p.set_defaults(func=cmd_cbz)

    p = sub.add_parser("web", help="open the browser interface",
                       description="Serve the MangaBinder web interface on http://127.0.0.1.")
    p.add_argument("-l", "--library", default=default_library(),
                   help="folder that holds your downloads (default: %(default)s)")
    p.add_argument("--port", type=int, default=8765, help="port to listen on (default 8765)")
    p.add_argument("--host", default="127.0.0.1",
                   help="address to listen on; use 0.0.0.0 to allow other devices, e.g. your phone "
                        "(default 127.0.0.1, this computer only)")
    p.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    p.set_defaults(func=cmd_web)

    p = sub.add_parser("gui", help="small desktop window for PDF -> CBZ")
    p.set_defaults(func=cmd_gui)
    return parser


def main(argv=None):
    multiprocessing.freeze_support()  # required for the Windows .exe
    _setup_streams()
    argv = sys.argv[1:] if argv is None else argv
    frozen = getattr(sys, "frozen", False)
    if not argv and frozen:
        argv = ["web"]  # double-clicked mangabinder.exe

    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        code = args.func(args) or 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        print(f"[!] {exc}")
        code = 1
    if frozen and not sys.argv[1:] and code:
        input("Press Enter to close...")  # keep the window open long enough to read the error
    return code


if __name__ == "__main__":
    sys.exit(main())
