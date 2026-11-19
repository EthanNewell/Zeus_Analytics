"""Реальные земельные торги с torgi.gov.ru для правила И4 (единственный участник).

Берёт открытые данные ГИС «Торги» (публичный API сайта) по одному субъекту РФ:
- электронные аукционы по ЗК РФ, признанные несостоявшимися, потому что подана только одна
  заявка (протокол с причиной «Подана только одна заявка…», п. 14 ст. 39.12 ЗК РФ);
- для сравнения — состоявшиеся аукционы, где цена выросла (признак конкуренции).
Имён участников API не отдаёт: в протоколе есть только номер заявки и цена.

Сайт открыт только для российских адресов и подписан российским корневым центром
сертификации (Минцифры): запускать с российского адреса, указав сертификаты в CA_BUNDLE.

    CA_BUNDLE=/path/russian_trusted_ca.pem python3 torgi_fetch.py 61 10 5 > torgi_61.json

Запросы идут по одному с паузой — нагрузка на сайт как у человека в браузере.
"""

import json
import os
import ssl
import sys
import time
import urllib.request

API = "https://torgi.gov.ru/new/api/public/lotcards"
PAUSE = 1.2
SINGLE = "ZK_EA_14_39.12_1"  # «Подана только одна заявка на участие в аукционе»


def get(url, context):
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=40, context=context) as response:
        data = json.load(response)
    time.sleep(PAUSE)
    return data


def search(context, region, status, page, size=50):
    url = (
        f"{API}/search?catCode=2&biddType=ZK&lotStatus={status}&subjRF={region}"
        f"&withFacets=false&size={size}&page={page}&sort=updateDate,desc"
    )
    return get(url, context)["content"]


def characteristic(card, code):
    for item in card.get("characteristics") or []:
        if item.get("code") == code:
            return item.get("characteristicValue")
    return None


def attribute(card, suffix):
    for item in card.get("attributes") or []:
        if (item.get("code") or "").startswith(suffix):
            value = item.get("value")
            return value.get("name") if isinstance(value, dict) else value
    return None


def summary(card, kind):
    protocols = card.get("protocols") or []
    reasons = [p.get("abandonedReason") or {} for p in protocols]
    results = [r for p in protocols for r in (p.get("results") or [])]
    return {
        "kind": kind,
        "id": card["id"],
        "notice": card.get("noticeNumber"),
        "url": f"https://torgi.gov.ru/new/public/lots/lot/{card['id']}",
        "name": card.get("lotName"),
        "cadastral": characteristic(card, "CadastralNumber"),
        "area": characteristic(card, "SquareZU"),
        "category": (card.get("category") or {}).get("name"),
        "address": card.get("estateAddress"),
        "form": (card.get("biddForm") or {}).get("name"),
        "transaction": card.get("typeTransaction"),
        "contract": attribute(card, "DA_contractType"),
        "ownership": (card.get("ownershipForm") or {}).get("name"),
        "price_min": card.get("priceMin"),
        "price_fin": card.get("priceFin"),
        "auction_date": card.get("auctionStartDate"),
        "protocol_date": max((p.get("publishDate") or "" for p in protocols), default=""),
        "protocol_numbers": [p.get("protocolNumber") for p in protocols],
        "reasons": [r.get("name") for r in reasons if r.get("name")],
        "applications": len({r.get("orderNumber") for r in results if r.get("orderNumber")}),
    }


def main(region, want_single, want_competitive):
    context = ssl.create_default_context(cafile=os.environ.get("CA_BUNDLE"))
    found = []
    page = 0
    single = 0
    while single < want_single and page < 4:
        for lot in search(context, region, "FAILED", page):
            if lot.get("biddForm", {}).get("code") != "EA":
                continue
            card = get(f"{API}/{lot['id']}", context)
            codes = [
                (p.get("abandonedReason") or {}).get("code") for p in card.get("protocols") or []
            ]
            if SINGLE in codes:
                found.append(summary(card, "single"))
                single += 1
                if single >= want_single:
                    break
        page += 1
    competitive = 0
    page = 0
    while competitive < want_competitive and page < 3:
        for lot in search(context, region, "SUCCEED", page):
            if lot.get("biddForm", {}).get("code") != "EA":
                continue
            if not (
                lot.get("priceFin") and lot.get("priceMin") and lot["priceFin"] > lot["priceMin"]
            ):
                continue
            found.append(summary(get(f"{API}/{lot['id']}", context), "competitive"))
            competitive += 1
            if competitive >= want_competitive:
                break
        page += 1
    json.dump(found, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
