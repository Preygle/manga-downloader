from mangabinder.downloader import (
    chapter_name,
    find_chapter_links,
    find_images,
    image_extension,
    read_state,
    site_folder,
)
from mangabinder.volume_map import guess_series_title, parse_chapter_number

SERIES_PAGE = """
<a href="/">Home</a>
<a class="c" href="https://www.example.com/manga/monster-chapter-2/">Chapter 2</a>
<a href="/manga/monster-chapter-1/">Chapter 1</a>
<a href="/manga/monster-chapter-1/#comments">Chapter 1 comments</a>
<a href="https://other.site/manga/x-chapter-9/">Ad</a>
<a href='/manga/monster-chapter-1.5/'>Chapter 1.5</a>
"""


def test_site_folder():
    assert site_folder("https://www.example.com/manga/x/") == "example.com"
    assert site_folder("http://reader.example.org") == "reader.example.org"
    assert site_folder("http://localhost:8080/series/") == "localhost_8080"


def test_chapter_links_with_pattern():
    links = find_chapter_links(SERIES_PAGE, "https://www.example.com/", "/manga/monster-chapter-")
    assert links == [
        "https://www.example.com/manga/monster-chapter-2/",
        "https://www.example.com/manga/monster-chapter-1/",
        "https://www.example.com/manga/monster-chapter-1.5/",
    ]


def test_chapter_links_auto_detect_stays_on_site():
    links = find_chapter_links(SERIES_PAGE, "https://www.example.com/", "")
    assert len(links) == 3
    assert all("other.site" not in link for link in links)


def test_images_prefer_lazy_attributes_and_skip_placeholders():
    page = """
    <img src="/logo.svg">
    <img class="p" src="data:image/gif;base64,AAAA" data-src="https://cdn.example.com/1.jpg?v=2">
    <img src="https://cdn.example.com/2.webp">
    <img data-lazy-src="/img/3.PNG" src="/spinner.gif">
    <img src="https://cdn.example.com/2.webp">
    <img class='avatar avatar-70' data-src='https://www.example.com/wp-content/avatar/ab.jpg'>
    """
    assert find_images(page, "https://www.example.com/manga/c-1/") == [
        "https://cdn.example.com/1.jpg?v=2",
        "https://cdn.example.com/2.webp",
        "https://www.example.com/img/3.PNG",
    ]


def test_names_and_extensions():
    assert chapter_name("https://x.com/manga/monster-chapter-12/") == "monster-chapter-12"
    assert image_extension("https://cdn/x/1.JPG?w=1") == ".jpg"
    assert image_extension("https://cdn/x/image") == ".jpg"


def test_read_state(tmp_path):
    state = tmp_path / "download_state.txt"
    state.write_text("a-chapter-1:COMPLETED\n\n\nb-chapter-2:COMPLETED\n", encoding="utf-8")
    assert read_state(str(state)) == {"a-chapter-1", "b-chapter-2"}


def test_chapter_numbers_and_title():
    assert parse_chapter_number("monster-chapter-12") == 12
    assert parse_chapter_number("monster-chapter-10.5.pdf") == 10.5
    assert guess_series_title(["one-piece-chapter-1", "one-piece-chapter-2"]) == "One Piece"
