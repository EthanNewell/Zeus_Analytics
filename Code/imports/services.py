class ImportNotConfigured(Exception):
    """Replace this adapter after developer #2 implements the agreed CSV contract."""


def import_csv(*, actor, uploaded_file):
    raise ImportNotConfigured("Импорт пока недоступен. Данные не были загружены.")
