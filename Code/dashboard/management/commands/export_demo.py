"""Static read-only demo of the app for GitHub Pages.

Crawls every page reachable from the overview as a signed-in head of department and writes
them as plain files under OUTDIR, links rewritten for the site prefix (e.g. /repo-name/).
The registry filters and search work in the demo: for every filter value the server itself
lists the matching objects, the registry page keeps those lists and the search fields of each
object, and a small script intersects them in the browser. The site is crawled as a read-only
user of the copy, so the forms that write (upload, analysis run, staff review, documents) are
not rendered at all, exactly as the service shows them to such a user.

Run it on a COPY of the database: real people's names in the research rows are masked in
place before crawling, so a public demo never shows a living person next to a risk label.

    SQLITE_PATH=/tmp/demo.sqlite3 python manage.py export_demo out --prefix /kod-prozrachnosti/
"""

import json
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings

from cases.models import Case, Origin, Record

PATRONYMIC = r"[А-ЯЁ][а-яё]+(?:ич|вна|чна|тична|оглы|кызы)"  # «-ич» ловит и «Ильич», «Кузьмич»
NAME_RE = re.compile(rf"\b([А-ЯЁ])[а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+([А-ЯЁ])[а-яё]+\s+({PATRONYMIC})")
INN_RE = re.compile(r"(ИНН\s*)\d{10,12}")
SKIP = ("/admin", "/accounts/logout", "/health", "/evidence/", "/analysis/", "/static/")
ATTR_RE = re.compile(r'''(\s(?:href|src|action)=")([^"#]*)(#[^"]*)?"''')

# Демо обходит сайт от имени читателя без прав записи: формы загрузки, анализа, проверки и
# документов сервис сам не показывает. Остаётся форма «Выйти» — в статичной копии она не нужна.
POST_FORM_RE = re.compile(r'<form\b[^>]*method="post"[^>]*>.*?</form>', re.S | re.I)
READER = "демо-просмотр"
READER_PERMISSIONS = ("view_case", "view_evidence", "view_review", "export_cases")
ROW_RE = re.compile(r'<tr class="row">.*?</tr>', re.S)
CASE_ID_RE = re.compile(r"/cases/([0-9a-f-]{36})/")

FILTER_SCRIPT = """
<script>
(function () {
  const data = JSON.parse(document.getElementById("demo-index").textContent);
  const form = document.querySelector("form.filters");
  const body = document.querySelector("table.tbl tbody");
  const found = [...document.querySelectorAll("h2")].find((h) => h.textContent.startsWith("Найдено"));
  const pager = document.querySelector("nav.pager");
  const tabs = [...document.querySelectorAll("nav.seg a")];
  if (!form || !body) return;
  const state = Object.fromEntries(new URLSearchParams(location.search));
  const hidden = form.querySelector('input[name="attention"]');
  if (hidden && !state.attention) state.attention = hidden.value;
  function apply(push) {
    let ids = data.order;
    for (const [name, sets] of Object.entries(data.sets)) {
      const value = state[name];
      if (value) ids = ids.filter((id) => (sets[value] || []).includes(id));
    }
    const q = (state.q || "").trim().toLowerCase();
    if (q) ids = ids.filter((id) => data.text[id].includes(q));
    body.innerHTML = ids.length ? ids.map((id) => data.rows[id]).join("")
      : '<tr><td colspan="6" class="empty">Ничего не найдено. Измените фильтры.</td></tr>';
    if (found) found.textContent = "Найдено: " + ids.length;
    if (pager) pager.hidden = true;
    tabs.forEach((a) => {
      const value = new URL(a.href, location.href).searchParams.get("attention") || a.dataset.attention || "";
      a.toggleAttribute("aria-current", value === (state.attention || ""));
      if (a.hasAttribute("aria-current")) a.setAttribute("aria-current", "true");
    });
    for (const field of form.elements) if (field.name && field.name in state) field.value = state[field.name];
    if (push) history.replaceState(null, "", "?" + new URLSearchParams(Object.entries(state).filter(([, v]) => v)));
  }
  tabs.forEach((a) => a.addEventListener("click", (event) => {
    event.preventDefault();
    state.attention = a.dataset.attention || "";
    apply(true);
  }));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    for (const field of form.elements) if (field.name && field.name !== "attention") state[field.name] = field.value;
    apply(true);
  });
  if (Object.values(state).some(Boolean)) apply(false);
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
            STORAGES={
                **settings.STORAGES,
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        ):
            client = Client()
            client.force_login(self.reader())
            pages = self.crawl(client, out, prefix)
            self.add_registry_filters(client, out)
        shutil.copytree(Path(settings.BASE_DIR) / "static", out / "static")
        (out / ".nojekyll").write_text("")
        (out / "404.html").write_text(
            f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={prefix}">'
        )
        self.stdout.write(self.style.SUCCESS(f"{pages} pages → {out}"))

    @staticmethod
    def reader():
        """Read-only user of the database copy: views everything, writes nothing."""
        user, _ = get_user_model().objects.get_or_create(username=READER)
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="cases", codename__in=READER_PERMISSIONS
            )
        )
        return user

    @staticmethod
    def case_ids(html):
        return list(dict.fromkeys(CASE_ID_RE.findall(html)))

    def listed(self, client, params):
        """Ids of the cases the server lists for these filters, over all pages, in its order."""
        ids, page = [], 1
        while True:
            html = client.get("/cases/", {**params, "page": page}).content.decode()
            body = html.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
            ids += self.case_ids(body)
            if f"page={page + 1}" not in html:
                return ids
            page += 1

    def add_registry_filters(self, client, out):
        """Registry filters for the static demo: the server's answer for every filter value."""
        first = client.get("/cases/").content.decode()
        options = {}
        for name, select in re.findall(
            r'<select[^>]*name="(\w+)"[^>]*>(.*?)</select>', first, re.S
        ):
            values = re.findall(r'<option(?: value="([^"]*)")?[^>]*>([^<]*)</option>', select)
            options[name] = [
                value if value or not text.strip() else text.strip() for value, text in values
            ]
            options[name] = [
                value for value in options[name] if value and not value.startswith(("Все", "Любой"))
            ]
        options["attention"] = sorted(set(re.findall(r"[?&]attention=(\w+)", first)))
        sets = {
            name: {v: self.listed(client, {name: v}) for v in values}
            for name, values in options.items()
        }
        order = self.listed(client, {})
        rows = {}
        for file in (out / "cases").glob("**/index.html"):
            if file.parent.name == "cases" or "page-" in str(file.parent.name):
                for row in ROW_RE.findall(file.read_text()):
                    case_id = CASE_ID_RE.search(row)
                    if case_id:
                        rows.setdefault(case_id.group(1), row)
        text = {}
        for case in Case.objects.prefetch_related("records"):
            fields = [case.reference, case.title, case.cadastral_number, case.address]
            fields += [record.title for record in case.records.all()]
            text[str(case.pk)] = " ".join(filter(None, fields)).lower()
        missing = [case_id for case_id in order if case_id not in rows]
        if missing:
            raise CommandError(f"registry rows not exported: {missing[:3]}")
        index = json.dumps(
            {
                "order": order,
                "rows": rows,
                "sets": sets,
                "text": {i: text.get(i, "") for i in order},
            },
            ensure_ascii=False,
        ).replace("</", "<\\/")
        payload = f'<script id="demo-index" type="application/json">{index}</script>{FILTER_SCRIPT}'
        for file in [out / "cases" / "index.html", *(out / "cases" / "q").glob("*/index.html")]:
            html = file.read_text()
            html = re.sub(r'<a href="([^"]*)" data-lbl', self.tab_mark, html)
            file.write_text(html.replace("</body>", payload + "</body>", 1))

    @staticmethod
    def tab_mark(match):
        """Вкладка итога анализа помнит своё значение: скрипт фильтров переключает её на месте."""
        value = re.search(r"attention-(\w+)", match.group(1))
        return f'<a href="{match.group(1)}" data-attention="{value.group(1) if value else ""}" data-lbl'

    def mask_real_people(self):
        changed = 0
        for record in Record.objects.all():
            facts = record.facts
            for fact in facts.values():
                if fact.get("origin") == Origin.AUTHOR_MARKED_REAL and isinstance(
                    fact.get("value"), str
                ):
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
                if not link or link.startswith(
                    ("http:", "https:", "mailto:", "data:", "javascript:")
                ):
                    return match.group(0)
                absolute = self.canonical(urljoin(current, link))
                if absolute.startswith("/static/"):
                    return f'{attr}{prefix}{absolute.lstrip("/")}{anchor}"'
                if any(absolute.startswith(skip) for skip in SKIP):
                    return (
                        f'{attr}#{anchor.lstrip("#")}"'
                        if attr.strip().startswith("href")
                        else match.group(0)
                    )
                # one filter at a time (plus a page number): combinations of filters would explode
                params = [k for k, v in parse_qsl(urlsplit(absolute).query) if v and k != "page"]
                if len(params) <= 1 and absolute not in seen:
                    queue.append(absolute)
                path = self.target(absolute).removesuffix("index.html")
                return f'{attr}{prefix}{path}{anchor}"'

            html = ATTR_RE.sub(rewrite, html)
            html = POST_FORM_RE.sub("", html)
            # the map builds card links in JS
            html = html.replace('href="/cases/${f.id}/"', f'href="{prefix}cases/${{f.id}}/"')
            html = html.replace("</head>", '<meta name="robots" content="noindex">\n</head>', 1)
            file.write_text(html)
        return len([p for p in out.rglob("index.html")])
