"""
test_functions.py  –  pytest Tests für stac_api.py

Ausführen:
    pytest test_functions.py -v
    pytest test_functions.py -v --tb=short   # kompakter Fehler-Output

Keine echten HTTP-Requests – alle Netzwerkaufrufe werden gemockt.
"""

import pytest
from unittest.mock import MagicMock, patch

import requests as req_module

from api.stac_api import (
    COLLECTION_ID, ENVIRONMENTS, AUFTRAGSTYPEN, EXT_PRESETS,
    get_item_direct, get_collection_items,
    delete_asset, delete_item, abort_asset_upload, _write_base,
    check_asset_info, browser_url,
    stac_item_year, stac_item_area,
)

AUTH = ("testuser", "testpass")
BASE = "https://sys-data.int.bgdi.ch/api/stac/v1/"


def _mock_response(status: int = 200, json_data=None, raise_on_status=False):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else {}
    r.text = ""
    r.reason = ""
    if raise_on_status:
        r.raise_for_status.side_effect = req_module.HTTPError(response=r)
    else:
        r.raise_for_status = MagicMock()
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# Konstanten
# ═══════════════════════════════════════════════════════════════════════════════

class TestKonstanten:

    def test_collection_id(self):
        assert COLLECTION_ID == "ch.swisstopo.spezialbefliegungen"

    def test_environments_schluessel(self):
        assert "INT"  in ENVIRONMENTS
        assert "PROD" in ENVIRONMENTS

    @pytest.mark.parametrize("env", ["INT", "PROD"])
    def test_environments_auf_stac_v1(self, env):
        """Migration v0.9 -> v1: Segment heisst "v1" (nicht "v1.0" = 404) und
        muss mit "/" enden, sonst verwirft urljoin() die Version."""
        url = ENVIRONMENTS[env]
        assert url.endswith("/api/stac/v1/")
        assert "v0.9" not in url and "v1.0" not in url

    @pytest.mark.parametrize("env, host", [
        ("INT",  "https://sys-data.int.bgdi.ch/"),
        ("PROD", "https://data.geo.admin.ch/"),
    ])
    def test_browser_url_item(self, env, host):
        url = browser_url(env, "kry-2015-08-05t09230000")
        assert url.startswith(host)
        assert f"#/collections/{COLLECTION_ID}/items/kry-2015-08-05t09230000" in url

    def test_auftragstypen_vorhanden(self):
        assert "KRY (Kryosphäre)"   in AUFTRAGSTYPEN
        assert "RAM (Rapidmapping)" in AUFTRAGSTYPEN
        assert "Alle"               in AUFTRAGSTYPEN

    def test_ext_presets_nicht_leer(self):
        assert len(EXT_PRESETS) > 0
        for label, exts in EXT_PRESETS:
            assert isinstance(label, str)
            assert all(e.startswith(".") for e in exts)


# ═══════════════════════════════════════════════════════════════════════════════
# check_asset_info
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckAssetInfo:

    URL = "https://example.com/file.tif"

    def _resp(self, status=200, headers=None):
        r = _mock_response(status)
        r.headers = headers or {}
        return r

    def test_leere_url_gibt_minus_1(self):
        assert check_asset_info("", AUTH)["status"] == -1

    def test_200_ok(self):
        with patch("api.stac_api.requests.head", return_value=self._resp(200)):
            assert check_asset_info(self.URL, AUTH)["status"] == 200

    def test_404_nicht_gefunden(self):
        with patch("api.stac_api.requests.head", return_value=self._resp(404)):
            assert check_asset_info(self.URL, AUTH)["status"] == 404

    def test_403_wird_mit_auth_wiederholt(self):
        """Bei 403 soll ein zweiter HEAD-Request mit Auth gesendet werden."""
        with patch("api.stac_api.requests.head",
                   side_effect=[self._resp(403), self._resp(200)]) as mock_head:
            result = check_asset_info(self.URL, AUTH)
        assert result["status"] == 200
        assert mock_head.call_count == 2
        _, kwargs = mock_head.call_args
        assert kwargs.get("auth") == AUTH

    def test_timeout_gibt_minus_2(self):
        with patch("api.stac_api.requests.head",
                   side_effect=req_module.exceptions.Timeout):
            assert check_asset_info(self.URL, AUTH)["status"] == -2

    def test_netzwerkfehler_gibt_minus_3(self):
        with patch("api.stac_api.requests.head",
                   side_effect=ConnectionError("no route")):
            assert check_asset_info(self.URL, AUTH)["status"] == -3

    def test_groesse_und_datum_werden_gelesen(self):
        headers = {"Content-Length": "12345", "Last-Modified": "Wed, 20 Aug 2024 10:00:00 GMT"}
        with patch("api.stac_api.requests.head", return_value=self._resp(200, headers)):
            result = check_asset_info(self.URL, AUTH)
        assert result["size_bytes"] == 12345
        assert result["last_modified"] == headers["Last-Modified"]

    def test_400_ueber_50gb_gibt_minus_4(self):
        """CloudFront antwortet auf HEAD für Assets > 50 GB korrekterweise mit
        400 - der Range-Probe (GET Range: bytes=0-0) bestätigt die Grösse per
        206/Content-Range, daraufhin soll status auf -4 (kein Fehler) wechseln."""
        total_size = 60 * 1024 ** 3
        range_resp = self._resp(206, {"Content-Range": f"bytes 0-0/{total_size}"})
        with patch("api.stac_api.requests.head", return_value=self._resp(400)), \
             patch("api.stac_api.requests.get", return_value=range_resp):
            result = check_asset_info(self.URL, AUTH)
        assert result["status"] == -4
        assert result["size_bytes"] == total_size

    def test_400_unter_50gb_bleibt_echter_fehler(self):
        """Ein 400 ohne bestätigte Range-Antwort > 50 GB ist ein echter
        Fehler und darf nicht als -4 maskiert werden."""
        with patch("api.stac_api.requests.head", return_value=self._resp(400)), \
             patch("api.stac_api.requests.get", return_value=self._resp(404)):
            result = check_asset_info(self.URL, AUTH)
        assert result["status"] == 400


# ═══════════════════════════════════════════════════════════════════════════════
# get_item_direct
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetItemDirect:

    ITEM = {
        "id": "test-item-001",
        "assets": {"nrgb_cog": {"href": "https://example.com/file.tif"}},
    }

    def test_item_gefunden(self):
        with patch("api.stac_api._session_get", return_value=_mock_response(200, self.ITEM)):
            result = get_item_direct(BASE, AUTH, "test-item-001")
        assert result == self.ITEM

    def test_item_nicht_gefunden_404(self):
        with patch("api.stac_api._session_get", return_value=_mock_response(404)):
            result = get_item_direct(BASE, AUTH, "existiert-nicht")
        assert result is None

    def test_item_id_wird_getrimmt(self):
        with patch("api.stac_api._session_get",
                   return_value=_mock_response(200, self.ITEM)) as mock_get:
            get_item_direct(BASE, AUTH, "  test-item-001  ")
        url = mock_get.call_args[0][0]
        assert "test-item-001" in url
        assert "  " not in url

    def test_url_enthaelt_collection_und_item(self):
        with patch("api.stac_api._session_get",
                   return_value=_mock_response(200, self.ITEM)) as mock_get:
            get_item_direct(BASE, AUTH, "item-abc")
        url = mock_get.call_args[0][0]
        assert f"collections/{COLLECTION_ID}/items/item-abc" in url

    @pytest.mark.parametrize("env", ["INT", "PROD"])
    def test_url_exakt_v1(self, env):
        with patch("api.stac_api._session_get",
                   return_value=_mock_response(200, self.ITEM)) as mock_get:
            get_item_direct(ENVIRONMENTS[env], AUTH, "item-abc")
        assert mock_get.call_args[0][0] == (
            f"{ENVIRONMENTS[env]}collections/{COLLECTION_ID}/items/item-abc")

    def test_v1_asset_felder_stoeren_nicht(self):
        """Echte v1-Asset-Struktur (live von PROD, 2026-09-23): gsd statt
        eo:gsd, file:checksum statt checksum:multihash, teils in Grossschreibung.
        Das Tool wertet diese Felder nicht aus – Area-Erkennung bleibt stabil."""
        item = {
            "id": "kry-2015-08-05t09230000",
            "stac_version": "1.0.0",
            "properties": {"datetime": "2015-08-05T09:23:00Z"},
            "assets": {"kry-2015-08-05t09230000-dsm-hillshade.tif": {
                "title": "DSM-HILLSHADE",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "href": "https://data.geo.admin.ch/ch.swisstopo.spezialbefliegungen/"
                        "kry-2015-08-05t09230000/kry-2015-08-05t09230000-dsm-hillshade.tif",
                "description": "Area: RANDA, TerrainModel: DSM",
                "gsd": 1.0,
                "proj:epsg": 2056,
                "file:checksum": "1220F2C0F083C8BD36F9974E9663017A43B3ABEFEE0B7C318F52D2501D39F7E2C165",
            }},
        }
        assert stac_item_area(item) == "RANDA"
        assert stac_item_year(item) == "2015"


# ═══════════════════════════════════════════════════════════════════════════════
# get_collection_items
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetCollectionItems:

    def test_einzelne_seite(self):
        data = {"features": [{"id": "item-1"}, {"id": "item-2"}], "links": []}
        with patch("api.stac_api._session_get", return_value=_mock_response(200, data)):
            result = get_collection_items(BASE, AUTH)
        assert len(result) == 2

    def test_paginierung_zwei_seiten(self):
        page1 = {
            "features": [{"id": "item-1"}],
            "links": [{"rel": "next", "href": "https://example.com/page2"}],
        }
        page2 = {"features": [{"id": "item-2"}, {"id": "item-3"}], "links": []}

        responses = iter([_mock_response(200, page1), _mock_response(200, page2)])
        with patch("api.stac_api._session_get", side_effect=lambda *a, **kw: next(responses)):
            result = get_collection_items(BASE, AUTH)

        assert len(result) == 3
        assert result[0]["id"] == "item-1"
        assert result[2]["id"] == "item-3"

    def test_leere_collection(self):
        data = {"features": [], "links": []}
        with patch("api.stac_api._session_get", return_value=_mock_response(200, data)):
            result = get_collection_items(BASE, AUTH)
        assert result == []

    def test_log_fn_wird_bei_paginierung_aufgerufen(self):
        page1 = {
            "features": [{"id": "item-1"}],
            "links": [{"rel": "next", "href": "https://example.com/page2"}],
        }
        page2 = {"features": [{"id": "item-2"}], "links": []}
        log_calls = []
        responses = iter([_mock_response(200, page1), _mock_response(200, page2)])
        with patch("api.stac_api._session_get", side_effect=lambda *a, **kw: next(responses)):
            get_collection_items(BASE, AUTH, log_fn=lambda msg: log_calls.append(msg))
        assert len(log_calls) == 1
        assert "Paginierung" in log_calls[0]

    def test_paginierung_v1_cursor_link(self):
        """v1 liefert den next-Link mit cursor+limit bereits im href (live
        verifiziert). Er muss unverändert und ohne zusätzliche params folgen,
        sonst würde limit doppelt gesetzt bzw. der Cursor verloren gehen."""
        next_href = (f"{BASE}collections/{COLLECTION_ID}/items"
                     "?cursor=cD1rcnktMjAxOC0wOS0xMXQxMTM0MDAwMA%3D%3D&limit=1000")
        page1 = {"features": [{"id": "item-1"}],
                 "links": [{"rel": "next", "href": next_href}]}
        page2 = {"features": [{"id": "item-2"}], "links": []}
        responses = iter([_mock_response(200, page1), _mock_response(200, page2)])
        with patch("api.stac_api._session_get",
                   side_effect=lambda *a, **kw: next(responses)) as mock_get:
            result = get_collection_items(BASE, AUTH, log_fn=lambda _m: None)
        assert [it["id"] for it in result] == ["item-1", "item-2"]
        first, second = mock_get.call_args_list
        assert first.args[0] == f"{BASE}collections/{COLLECTION_ID}/items"
        assert second.args[0] == next_href
        assert second.args[2] is None


# ═══════════════════════════════════════════════════════════════════════════════
# delete_asset
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeleteAsset:

    def test_success_200(self):
        with patch("api.stac_api._session_delete", return_value=_mock_response(200)):
            ok, code, reason = delete_asset(BASE, AUTH, "item-001", "nrgb_cog")
        assert ok is True
        assert code == 200
        assert reason == ""

    def test_success_204(self):
        with patch("api.stac_api._session_delete", return_value=_mock_response(204)):
            ok, code, _ = delete_asset(BASE, AUTH, "item-001", "nrgb_cog")
        assert ok is True
        assert code == 204

    def test_fail_403(self):
        with patch("api.stac_api._session_delete", return_value=_mock_response(403)):
            ok, code, _ = delete_asset(BASE, AUTH, "item-001", "nrgb_cog")
        assert ok is False
        assert code == 403

    def test_fail_404(self):
        with patch("api.stac_api._session_delete", return_value=_mock_response(404)):
            ok, code, _ = delete_asset(BASE, AUTH, "item-001", "nrgb_cog")
        assert ok is False

    def test_fail_reason_from_json_description(self):
        with patch("api.stac_api._session_delete",
                   return_value=_mock_response(400, json_data={"description": "Cannot delete last asset"})):
            ok, code, reason = delete_asset(BASE, AUTH, "item-001", "nrgb_cog")
        assert ok is False
        assert code == 400
        assert reason == "Cannot delete last asset"

    def test_url_korrekt_aufgebaut(self):
        with patch("api.stac_api._session_delete",
                   return_value=_mock_response(200)) as mock_del:
            delete_asset(BASE, AUTH, "item-abc", "my_asset_key")
        url = mock_del.call_args[0][0]
        assert f"collections/{COLLECTION_ID}/items/item-abc/assets/my_asset_key" in url

    @pytest.mark.parametrize("env", ["INT", "PROD"])
    def test_url_exakt_v09(self, env):
        """DELETE muss exakt an den v0.9-Endpunkt gehen (v1 ignoriert Basic
        Auth) – ein 'in'-Vergleich würde einen durch urljoin() verlorenen
        Versions-Pfad nicht bemerken."""
        with patch("api.stac_api._session_delete",
                   return_value=_mock_response(204)) as mock_del:
            delete_asset(ENVIRONMENTS[env], AUTH, "item-abc", "my_asset_key")
        assert mock_del.call_args[0][0] == (
            f"{_write_base(ENVIRONMENTS[env])}collections/{COLLECTION_ID}"
            "/items/item-abc/assets/my_asset_key")


# ═══════════════════════════════════════════════════════════════════════════════
# delete_item
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeleteItem:

    def test_success_200(self):
        with patch("api.stac_api._session_delete", return_value=_mock_response(200)):
            ok, code, _ = delete_item(BASE, AUTH, "item-001")
        assert ok is True
        assert code == 200

    def test_success_204(self):
        with patch("api.stac_api._session_delete", return_value=_mock_response(204)):
            ok, _, _ = delete_item(BASE, AUTH, "item-001")
        assert ok is True

    def test_fail_404(self):
        with patch("api.stac_api._session_delete", return_value=_mock_response(404)):
            ok, code, _ = delete_item(BASE, AUTH, "item-999")
        assert ok is False
        assert code == 404

    def test_url_korrekt_aufgebaut(self):
        with patch("api.stac_api._session_delete",
                   return_value=_mock_response(200)) as mock_del:
            delete_item(BASE, AUTH, "item-xyz")
        url = mock_del.call_args[0][0]
        assert f"collections/{COLLECTION_ID}/items/item-xyz" in url
        assert "/assets/" not in url

    @pytest.mark.parametrize("env", ["INT", "PROD"])
    def test_url_exakt_v09(self, env):
        with patch("api.stac_api._session_delete",
                   return_value=_mock_response(204)) as mock_del:
            delete_item(ENVIRONMENTS[env], AUTH, "item-xyz")
        assert mock_del.call_args[0][0] == (
            f"{_write_base(ENVIRONMENTS[env])}collections/{COLLECTION_ID}/items/item-xyz")


# ═══════════════════════════════════════════════════════════════════════════════
# _write_base / abort_asset_upload – Überbrückung: Schreiben über v0.9
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteBase:

    @pytest.mark.parametrize("env, expected", [
        ("INT",  "https://sys-data.int.bgdi.ch/api/stac/v0.9/"),
        ("PROD", "https://data.geo.admin.ch/api/stac/v0.9/"),
    ])
    def test_v1_wird_zu_v09(self, env, expected):
        assert _write_base(ENVIRONMENTS[env]) == expected

    def test_unerwartete_url_wirft_fehler(self):
        """Ohne v1-Segment lieber abbrechen als an eine falsche URL löschen."""
        with pytest.raises(ValueError):
            _write_base("https://data.geo.admin.ch/api/stac/v2/")

    def test_abort_geht_an_v09(self):
        with patch("api.stac_api._session_post",
                   return_value=_mock_response(200, json_data={"status": "aborted"})) as mock_post:
            ok, _, _ = abort_asset_upload(ENVIRONMENTS["PROD"], AUTH, "item-a", "asset-b", "up-1")
        assert ok is True
        assert mock_post.call_args[0][0] == (
            f"https://data.geo.admin.ch/api/stac/v0.9/collections/{COLLECTION_ID}"
            "/items/item-a/assets/asset-b/uploads/up-1/abort")

    def test_lesen_bleibt_auf_v1(self):
        with patch("api.stac_api._session_get",
                   return_value=_mock_response(200, json_data={"id": "item-a"})) as mock_get:
            get_item_direct(ENVIRONMENTS["PROD"], AUTH, "item-a")
        assert "/api/stac/v1/" in mock_get.call_args[0][0]


# ═══════════════════════════════════════════════════════════════════════════════
# stac_item_year
# ═══════════════════════════════════════════════════════════════════════════════

class TestStacItemYear:

    def test_aus_properties_datetime(self):
        item = {"id": "x", "properties": {"datetime": "2024-08-20T10:27:00Z"}}
        assert stac_item_year(item) == "2024"

    def test_aus_item_id_fallback(self):
        item = {"id": "ch.swisstopo.spezialbefliegungen_kry_2023-08-15t09850000",
                "properties": {}}
        assert stac_item_year(item) == "2023"

    def test_id_hat_prioritaet_vor_properties(self):
        """Laut Docstring: ID trägt das Befliegungsdatum, properties.datetime
        kann das (davon abweichende) Importdatum sein – die ID gewinnt."""
        item = {"id": "kry_2020-01-01",
                "properties": {"datetime": "2024-08-20T00:00:00Z"}}
        assert stac_item_year(item) == "2020"

    def test_properties_ist_fallback_wenn_id_kein_jahr_hat(self):
        item = {"id": "kry-keinjahr",
                "properties": {"datetime": "2024-08-20T00:00:00Z"}}
        assert stac_item_year(item) == "2024"

    def test_kein_datum_gibt_leerstring(self):
        assert stac_item_year({"id": "kein-datum", "properties": {}}) == ""

    def test_leeres_item(self):
        assert stac_item_year({}) == ""


# ═══════════════════════════════════════════════════════════════════════════════
# stac_item_area
# ═══════════════════════════════════════════════════════════════════════════════

class TestStacItemArea:

    def test_aus_properties_area(self):
        item = {"properties": {"area": "oberaar"}, "bbox": []}
        assert stac_item_area(item) == "OBERAAR"

    def test_aus_properties_aoi(self):
        item = {"properties": {"aoi": "gorner"}, "bbox": []}
        assert stac_item_area(item) == "GORNER"

    def test_properties_hat_prioritaet_vor_bbox(self):
        item = {
            "properties": {"area": "RHONE"},
            "bbox": [7.5, 45.8, 7.9, 46.2],
        }
        assert stac_item_area(item) == "RHONE"

    # Hinweis: stac_item_area() implementiert keine bbox-basierte Nächste-
    # Nachbar-AOI-Schätzung (dafür bräuchte es eine Referenztabelle echter
    # AOI-Koordinaten) – Tests, die genau das erwartet hatten, wurden entfernt.

    def test_kein_bbox_kein_property_gibt_leerstring(self):
        assert stac_item_area({"properties": {}}) == ""

    def test_leeres_item(self):
        assert stac_item_area({}) == ""
