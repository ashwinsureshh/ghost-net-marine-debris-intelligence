"""The offline export must not fetch its code or fonts (it runs from file://).

Chromium blocks crossorigin module scripts and stylesheets on file:// pages,
which rendered the export blank. inline_assets() removes every such fetch.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # build_static_export imports the web app

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_static_export import inline_assets  # noqa: E402

INDEX = (
    '<!doctype html><html><head>'
    '<script type="module" crossorigin src="./assets/index-abc.js"></script>'
    '<link rel="stylesheet" crossorigin href="./assets/index-abc.css">'
    '</head><body><div id="root"></div></body></html>'
)


def _dist(tmp_path, js='console.log("</script>");'):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index-abc.js").write_text(js, encoding="utf-8")
    (assets / "font.woff2").write_bytes(b"\x00font")
    (assets / "index-abc.css").write_text(
        "@font-face{src:url(./font.woff2)}.x{behavior:url(#default#VML)}", encoding="utf-8")
    return tmp_path


def test_no_asset_is_fetched_after_inlining(tmp_path):
    html = inline_assets(INDEX, _dist(tmp_path))
    assert "src=\"./assets" not in html and "href=\"./assets" not in html
    assert "crossorigin" not in html
    assert '<script type="module">' in html


def test_fonts_become_data_uris_and_other_urls_are_left_alone(tmp_path):
    html = inline_assets(INDEX, _dist(tmp_path))
    assert "url(data:font/woff2;base64," + base64.b64encode(b"\x00font").decode() + ")" in html
    assert "url(#default#VML)" in html


def test_a_closing_script_tag_inside_the_bundle_cannot_end_the_tag(tmp_path):
    html = inline_assets(INDEX, _dist(tmp_path))
    body = html.split('<script type="module">', 1)[1]
    assert body.index("</script>") > body.index("<\\/script>")


def test_an_unexpected_build_layout_is_refused_rather_than_half_inlined(tmp_path):
    dist = _dist(tmp_path)
    (dist / "assets" / "x.js").write_text("", encoding="utf-8")
    two_scripts = INDEX.replace(
        "</head>", '<script type="module" src="./assets/x.js"></script></head>')
    with pytest.raises(ValueError, match="build layout changed"):
        inline_assets(two_scripts, dist)
