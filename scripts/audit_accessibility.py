"""Automated WCAG 2.1 A/AA audit of the running console with axe-core.

    python scripts/audit_accessibility.py --url http://127.0.0.1:8000/ --axe path/to/axe.min.js

Manual QA tool, not part of CI: it needs a running server, Playwright's
Chromium and a local copy of axe-core (not vendored), e.g.
https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js.

Audits Explore, evidence, Plan and Research in light and dark themes, with
all <details> expanded. It first plants one known violation (an image with no
alt text) and aborts unless axe reports it, so an empty report cannot come
from a harness that silently checked nothing.

Automated checks cover only part of WCAG. Keyboard flow, focus management and
layout were checked by hand; see docs/accessibility-qa.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
RUN = ("async () => (await axe.run(document, {runOnly: {type: 'tag', values: "
       + json.dumps(TAGS) + "}})).violations"
       ".map(v => ({id: v.id, impact: v.impact, help: v.help, n: v.nodes.length,"
       " targets: v.nodes.slice(0, 4).map(n => n.target.join(' '))}))")


async def main(url: str, axe_source: str) -> int:
    from playwright.async_api import async_playwright

    found: dict = defaultdict(list)

    async def audit(page, label):
        await page.add_script_tag(content=axe_source)
        for v in await page.evaluate(RUN):
            found[(v["id"], v["impact"], v["help"])].append((label, v["n"], v["targets"]))

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(url, wait_until="networkidle")
        await page.add_script_tag(content=axe_source)
        planted = await page.evaluate(
            "async () => { const i = document.createElement('img'); document.body.appendChild(i);"
            f" const r = await ({RUN})(); i.remove(); return r.map(v => v.id); }}")
        if "image-alt" not in planted:
            print("Harness check failed: planted violation not detected.", file=sys.stderr)
            return 2

        for scheme in ("light", "dark"):
            page = await browser.new_page(viewport={"width": 1440, "height": 900},
                                          color_scheme=scheme)
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(2500)
            toggle = page.get_by_role(
                "button", name="Use light theme" if scheme == "light" else "Use dark theme")
            if await toggle.count():
                await toggle.click()
                await page.wait_for_timeout(500)
            await audit(page, f"{scheme}:explore")
            await page.locator(".atlas-observation").first.click()
            await page.wait_for_timeout(1200)
            await audit(page, f"{scheme}:evidence")
            for view in ("Plan", "Research"):
                await page.get_by_role("button", name=view, exact=True).click()
                await page.wait_for_timeout(1500)
                await page.evaluate(
                    "document.querySelectorAll('details').forEach(d => d.open = true)")
                await page.wait_for_timeout(400)
                await audit(page, f"{scheme}:{view.lower()}")
        await browser.close()

    if not found:
        print("No WCAG 2.1 A/AA violations detected by axe in 8 view/theme states.")
        return 0
    for (vid, impact, text), hits in sorted(found.items(), key=lambda kv: str(kv[0][1])):
        print(f"\n[{impact}] {vid}: {text}")
        for label, n, targets in hits:
            print(f"   {label:18s} x{n}  {targets[:3]}")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000/")
    ap.add_argument("--axe", type=Path, required=True, help="local axe.min.js")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.url, args.axe.read_text(encoding="utf-8"))))
