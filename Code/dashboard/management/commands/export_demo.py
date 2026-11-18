"""Static read-only demo of the app for GitHub Pages.

Crawls every page reachable from the overview as a signed-in head of department and writes
them as plain files under OUTDIR, links rewritten for the site prefix (e.g. /repo-name/).
Forms do nothing in the demo: a script explains that only viewing is available.

Run it on a COPY of the database: real people's names in the research rows are masked in
place before crawling, so a public demo never shows a living person next to a risk label.

    SQLITE_PATH=/tmp/demo.sqlite3 python manage.py export_demo out --prefix /kod-prozrachnosti/
"""

import re
import shutil
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings

from cases.models import Origin, Record

PATRONYMIC = r"[А-ЯЁ][а-яё]+(?:вич|вна|чна|тична|оглы|кызы)"
NAME_RE = re.compile(rf"\b([А-ЯЁ])[а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+([А-ЯЁ])[а-яё]+\s+({PATRONYMIC})")
INN_RE = re.compile(r"(ИНН\s*)\d{10,12}")
SKIP = ("/admin", "/accounts/logout", "/health", "/evidence/", "/analysis/", "/static/")
ATTR_RE = re.compile(r'''(\s(?:href|src|action)=")([^"#]*)(#[^"]*)?"''')

DEMO_SCRIPT = """
<script>
(function () {
  function note() {
    let box = document.querySelector("[data-toasts]");
    if (!box) { box = document.createElement("div"); box.className = "toasts"; box.dataset.toasts = ""; document.body.appendChild(box); }
    box.innerHTML = '<div class="toast" role="status"><span class="body-s">Демо-версия: здесь только просмотр. Загрузка, анализ, проверка и фильтры работают в полной версии.</span></div>';
    box.removeAttribute("data-hidden");
    clearTimeout(window.__demoNote); window.__demoNote = setTimeout(() => box.setAttribute("data-hidden", ""), 4500);
  }
  document.addEventListener("submit", (event) => { event.preventDefault(); note(); }, true);
})();
</script>
"""


def mask(text):
    """«Иванова Ольга Эльмаровна (ИНН 761200180374)» → «И. О. Э. (ИНН скрыт)»."""
    text = NAME_RE.sub(lambda m: f"{m.group(1)}. {m.group(2)}. {m.group(3)[0]}.", text)
    return INN_RE.sub(r"\1скрыт", text)


class Command(BaseCommand):
    help = "Export a static read-only demo (for GitHub Pages) from a copy of the database."

    def add_arguments(self, parser):
        parser.add_argument("outdir")
        parser.add_argument("--prefix", default="/", help="Site prefix, e.g. /kod-prozrachnosti/")
        parser.add_argument("--user", default="head")

    def handle(self, outdir, prefix, user, **options):
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Run on a SQLite copy: the command masks names in place.")
        if not prefix.endswith("/"):
            prefix += "/"
        out = Path(outdir)
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        self.mask_real_people()
        actor = get_user_model().objects.get(username=user)
        from analysis.services import run_analysis

        run_analysis(actor=actor)
        with override_settings(
            DEBUG=False,
            ALLOWED_HOSTS=["testserver"],
            STORAGES={**settings.STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
        ):
            client = Client()
            client.force_login(actor)
            pages = self.crawl(client, out, prefix)
        shutil.copytree(Path(settings.BASE_DIR) / "static", out / "static")
        (out / ".nojekyll").write_text("")
        (out / "404.html").write_text(
            f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={prefix}">'
        )
        self.stdout.write(self.style.SUCCESS(f"{pages} pages → {out}"))

    def mask_real_people(self):
        changed = 0
        for record in Record.objects.all():
            facts = record.facts
            for fact in facts.values():
                if fact.get("origin") == Origin.AUTHOR_MARKED_REAL and isinstance(fact.get("value"), str):
                    masked = mask(fact["value"])
                    if masked != fact["value"]:
                        fact["value"] = masked
                        changed += 1
            record.title = mask(record.title)
            record.facts = facts
            record.save(update_fields=["facts", "title"])
        self.stdout.write(f"masked {changed} real-person fields")

    @staticmethod
    def canonical(url):
        """One spelling per page: empty parameters dropped, one value per key, keys sorted."""
        parts = urlsplit(url)
        params = dict((k, v) for k, v in parse_qsl(parts.query) if v)
        query = urlencode(sorted(params.items()))
        return parts.path + (f"?{query}" if query else "")

    def target(self, url):
        """Site URL (path + query) → relative file path of the static page."""
        parts = urlsplit(url)
        path = parts.path.strip("/")
        if parts.path.endswith(".csv"):
            return path
        if parts.query:
            query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if v))
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", query).strip("-") or "all"
            path = f"{path}/q/{slug}".strip("/")
        return f"{path}/index.html" if path else "index.html"

    def crawl(self, client, out, prefix):
        queue, seen = ["/"], set()
        while queue:
            url = self.canonical(queue.pop(0))
            if url in seen:
                continue
            seen.add(url)
            response = client.get(url)
            if response.status_code != 200:
                continue
            file = out / self.target(url)
            file.parent.mkdir(parents=True, exist_ok=True)
            if url.endswith(".csv"):
                file.write_bytes(response.content)
                continue
            html = response.content.decode()

            def rewrite(match, current=url):
                attr, link, anchor = match.group(1), match.group(2), match.group(3) or ""
                if not link or link.startswith(("http:", "https:", "mailto:", "data:", "javascript:")):
                    return match.group(0)
                absolute = self.canonical(urljoin(current, link))
                if absolute.startswith("/static/"):
                    return f'{attr}{prefix}{absolute.lstrip("/")}{anchor}"'
                if any(absolute.startswith(skip) for skip in SKIP):
                    return f'{attr}#{anchor.lstrip("#")}"' if attr.strip().startswith("href") else match.group(0)
                # one filter at a time (plus a page number): combinations of filters would explode
                params = [k for k, v in parse_qsl(urlsplit(absolute).query) if v and k != "page"]
                if len(params) <= 1 and absolute not in seen:
                    queue.append(absolute)
                path = self.target(absolute).removesuffix("index.html")
                return f'{attr}{prefix}{path}{anchor}"'

            html = ATTR_RE.sub(rewrite, html)
            # the map builds card links in JS
            html = html.replace('href="/cases/${f.id}/"', f'href="{prefix}cases/${{f.id}}/"')
            html = html.replace("</head>", '<meta name="robots" content="noindex">\n</head>', 1)
            html = html.replace("</body>", DEMO_SCRIPT + "</body>", 1)
            file.write_text(html)
        return len([p for p in out.rglob("index.html")])
