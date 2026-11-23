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

from accounts.management.commands.demo_users import GUEST
from cases.models import Case, Origin, Record

PATRONYMIC = r"[А-ЯЁ][а-яё]+(?:ич|вна|чна|тична|оглы|кызы)"  # «-ич» ловит и «Ильич», «Кузьмич»
NAME_RE = re.compile(rf"\b([А-ЯЁ])[а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+([А-ЯЁ])[а-яё]+\s+({PATRONYMIC})")
INN_RE = re.compile(r"(ИНН\s*)\d{10,12}")
SKIP = ("/admin", "/accounts/logout", "/health", "/evidence/", "/analysis/", "/static/")
ATTR_RE = re.compile(r'''(\s(?:href|src|action|data-index)=")([^"#]*)(#[^"]*)?"''')

# Демо обходит сайт от имени читателя без прав записи: формы загрузки, анализа, проверки и
# документов сервис сам не показывает. «Выйти» в копии ведёт на статичную страницу входа, а её
# форма проверяется в браузере: демонстрационная запись 12345 / 12345 открывает главную.
POST_FORM_RE = re.compile(
    r'<form\b(?![^>]*accounts/login/)[^>]*method="post"[^>]*>.*?</form>', re.S | re.I
)
LOGOUT_RE = re.compile(
    r'<form\b[^>]*action="[^"]*accounts/logout/"[^>]*>.*?(<button[^>]*>)(.*?)</button></form>', re.S
)
LOGIN_SCRIPT = """
<script>
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.querySelector('[name="password"]')) return;
  event.preventDefault();
  if (form.username.value.trim() === "12345" && form.password.value === "12345") { location.href = "%s"; return; }
  let note = form.querySelector(".demo-login-error");
  if (!note) { note = document.createElement("p"); note.className = "demo-login-error"; note.setAttribute("role", "alert"); note.style.cssText = "color:#ad231c;margin:12px 0 0;text-align:center"; form.append(note); }
  note.textContent = "Неверная почта или пароль.";
}, true);
</script>
"""
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
  const found = document.querySelector("[data-found]");
  const pager = document.querySelector("nav.pager");
  const tabs = [...document.querySelectorAll("nav.tabs a[data-attention]")];
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
      const on = a.dataset.attention === (state.attention || "") && a.dataset.review === (state.review || "");
      if (on) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
    for (const field of form.elements) {
      if (!field.name || !(field.name in state)) continue;
      field.value = state[field.name];
      // the select is driven by a button (static/js/app.js): show the chosen option on it
      const label = field.closest(".dd")?.querySelector(".dd-btn span");
      if (label && field.selectedIndex >= 0) label.textContent = field.options[field.selectedIndex].textContent;
    }
    if (push) history.replaceState(null, "", "?" + new URLSearchParams(Object.entries(state).filter(([, v]) => v)));
  }
  tabs.forEach((a) => a.addEventListener("click", (event) => {
    event.preventDefault();
    state.attention = a.dataset.attention;
    state.review = a.dataset.review;
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
        # the copy is shown as the demonstration account of the sign-in page
        user.first_name, user.last_name = GUEST["name"]
        user.save(update_fields=["first_name", "last_name"])
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
            file.write_text(html.replace("</body>", payload + "</body>", 1))

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
        if parts.path.endswith((".csv", ".json")):  # the CSV export and the search index
            return path
        if parts.query:
            query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if v))
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", query).strip("-") or "all"
            path = f"{path}/q/{slug}".strip("/")
        return f"{path}/index.html" if path else "index.html"

    def crawl(self, client, out, prefix):
        queue, seen = ["/", "/accounts/login/"], set()
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
            if url.endswith(".json"):
                # the search index: its links are site paths, the demo lives under the prefix
                data = json.loads(response.content)
                for item in data["items"] + data["actions"]:
                    path = self.target(self.canonical(item["url"])).removesuffix("index.html")
                    item["url"] = f"{prefix}{path}"
                file.write_text(json.dumps(data, ensure_ascii=False))
                continue
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

            html = LOGOUT_RE.sub(
                lambda m: (
                    m.group(1)
                    .replace("<button", '<a href="/accounts/login/"', 1)
                    .replace(' type="submit"', "")
                    + m.group(2)
                    + "</a>"
                ),
                html,
            )
            html = ATTR_RE.sub(rewrite, html)
            html = POST_FORM_RE.sub("", html)
            if url == "/accounts/login/":
                html = html.replace("</body>", LOGIN_SCRIPT % prefix + "</body>", 1)
            html = html.replace("</head>", '<meta name="robots" content="noindex">\n</head>', 1)
            file.write_text(html)
        return len([p for p in out.rglob("index.html")])
