# STAC / GDWH Deleting-Tool

Löscht Daten gezielt aus **STAC** (Collection `ch.swisstopo.spezialbefliegungen`) und führt zum manuellen Löschen im **Geodata-Warehouse (GDWH)** – typischerweise, um einen fehlerhaften Import vor einem Re-Import sauber zu entfernen.

> ⚠️ **Löschungen sind endgültig.** Es gibt keinen Papierkorb und keine Wiederherstellung. Neue Abläufe immer zuerst auf **INT** ausprobieren, erst dann auf **PROD**.

## Auf einen Blick

| Tab | Was wird gelöscht? | Anmeldung |
|---|---|---|
| **GDWH Imports** | nichts direkt – öffnet die GDWH-API (Swagger), dort wird manuell gelöscht | Windows-Anmeldung im Browser |
| **STAC Items & Assets** | Assets – und Items, die dadurch leer werden | STAC-Zugangsdaten (`secrets/stac_credentials.json`) |

Die Daten fliessen GDWH → automatischer STAC-Upload. Bei einem Re-Import müssen deshalb meist **beide** Systeme bereinigt werden.

## Starten

Im cmd-Terminal:
```bash
python pfad/GUI_STAC_GDWH_delete.py
```
<img width="713" height="676" alt="image" src="https://github.com/user-attachments/assets/6c11bb18-c7a4-4faf-8f76-7624d0f838a9" />

## Voraussetzungen

- **Netzwerk:** Bundesnetz oder VPN – GDWH ist nur intern erreichbar.
- **Python 3.6+** mit dem Paket `requests`.
- **Nur für STAC:** Datei `secrets/stac_credentials.json` mit den Zugangsdaten. Diese bei TBKN/swisstopo anfragen.

```json
// secrets/stac_credentials.json
{
    "INT":  { "username": "...", "password": "..." },
    "PROD": { "username": "...", "password": "..." }
}
```

> Der Ordner `secrets/` ist per `.gitignore` von Git ausgeschlossen – Zugangsdaten nie committen.

---

## Tab „GDWH Imports“ – Link zur GDWH-API

GDWH-Imports werden nicht im Tool gelöscht, sondern manuell über die offizielle Swagger-Oberfläche der GDWH-API (PROD):
<https://ltgdwh.adr.admin.ch/gdwh-api/v2/swagger/index.html>

Der Tab enthält nur den Button **GDWH-API (Swagger) im Browser öffnen …**. Vor dem Öffnen erscheint ein Hinweis, der mit **OK** bestätigt werden muss:

| GDS | Selbst löschen? |
|---|---|
| `SB_DOP`, `SB_DOP_16`, `SB_DSM` | ✅ ja, problemlos manuell |
| `SB_DSM_PUNKTWOLKE` | ❌ **nein** – nur durch das Team GDWH, sonst Konflikt mit dem ReleaseKey |

Lässt sich kein Browser starten, kopiert das Tool den Link in die Zwischenablage.

---

## Tab „STAC Items & Assets“ – Assets löschen

### Schritt für Schritt

1. **Umgebung wählen** (INT/PROD) → **Credentials laden**. Der Button wird grün („Credentials geladen“), sobald die Zugangsdaten gelesen sind.
2. **ITEM-Liste laden** – holt die ganze Collection, das kann etwas dauern. Danach heisst der Button „ITEM-Liste aktualisieren“.
3. **Liste eingrenzen** (Abschnitt 2). Die Filter wirken sofort und gelten gleichzeitig:
   - **Auftragstyp, Jahr, Area, Item-ID** (Teilstring genügt)
   - **Asset-Key:** Teil des Keys oder Dateinamens, z.B. `nrgb`, `16bit`, `thumbnail`
   - **Dateiendung:** `tif/tiff`, `copc.laz/laz`, `jpg/jpeg`, `kml`, `txt` – mehrere Häkchen gelten als „oder“
4. Optional **Assets prüfen (HEAD)** – prüft, ob jede Datei erreichbar ist: ✓ grün = in Ordnung, ✗ rot/gelb = fehlerhaft oder nicht erreichbar. Danach:
   - **Fehlerhafte anzeigen** – nur fehlerhafte Assets und leere Items
   - **Fehlerhafte auswählen** – kreuzt genau diese an
5. **Assets ankreuzen** – einzeln oder mit **Alle auswählen**.
6. **Ausgewählte Assets löschen …** → [Sicherheitsabfrage](#sicherheitsabfrage) bestätigen.

Wird ein Item durch die Löschung ganz leer, löscht das Tool es automatisch mit – die Sicherheitsabfrage zeigt das vorher an. Erfolgreich gelöschte Einträge verschwinden aus der Liste, fehlgeschlagene bleiben für einen neuen Versuch stehen.

### Weitere Ansichten und Abkürzungen

- **ITEMs only with Thumbnail** – Items, die nur noch aus dem Thumbnail bestehen (keine Nutzdaten).
- **ITEMs ohne Thumbnail** – nur bei Auftragstyp RAM sichtbar, weil dort ein Thumbnail Pflicht ist.
- **Doppelklick** auf ein Asset öffnet es im Browser.
- **Rechtsklick:** URL kopieren, im Browser öffnen, Item-ID kopieren, im STAC Browser öffnen.
- **STAC Browser öffnen** (Abschnitt 1) öffnet die Collection im STAC Browser und kopiert den Link.

> **Gelöscht, aber noch sichtbar?** Ein gelöschtes Asset bleibt bis ca. **15 Minuten** in der ITEM-Liste und über seinen Download-Link erreichbar. Das ist eine Verzögerung auf Seite STAC (Katalog und Speicher), kein Fehler – nach 15 Minuten neu laden.

---

## Sicherheitsabfrage

Vor jeder Löschung erscheint ein roter Dialog mit Umgebung und Anzahl der betroffenen Daten:

1. Häkchen setzen: „Ich verstehe, dass die Daten permanent und unwiderruflich gelöscht werden.“
2. Den Namen der Umgebung eintippen (`INT` oder `PROD`).
3. Erst dann wird **JETZT LÖSCHEN** aktiv.

Während eine Löschung läuft, lässt sich die Umgebung nicht wechseln.

## Protokolle

Im Ordner `logs/` (nicht in Git):

- `stac_gdwh_delete_JJJJ-MM-TT.log` – Tagesprotokoll
- `LOG_STAC_<INT|PROD>_<Jahr>_<Area>_<Datum>.log` – ein Protokoll pro Löschvorgang

## Probleme und Lösungen

| Problem | Lösung |
|---|---|
| GDWH: Swagger-Seite lädt nicht | Bundesnetz/VPN prüfen. GDWH nutzt die Windows-Anmeldung des Browsers. |
| STAC: „Credentials laden“ meldet einen Fehler | Gibt es `secrets/stac_credentials.json`, und ist sie wie oben aufgebaut? |
| STAC: gelöschtes Asset noch sichtbar | ca. 15 Minuten warten, dann neu laden. |

---

## Technische Details

- **GDWH API v2** – [Swagger PROD](https://ltgdwh.adr.admin.ch/gdwh-api/v2/swagger/index.html), [Swagger INT](https://ltgdwhi.adr.admin.ch/gdwh-api/v2/swagger/index.html)
  - Imports auflisten: `GET /api/geodatasets/{gdsKey}/data/imports`
  - Import löschen: `DELETE /api/geodatasets/{gdsKey}/data/imports/{datapackageId}` → Job, Status über `GET /api/jobs/{jobId}`
- **STAC API** – INT `sys-data.int.bgdi.ch`, PROD `data.geo.admin.ch`
  - Lesen über v1, Löschen vorerst über v0.9: v1 akzeptiert keine Basic Auth mehr, nur noch JWT (AWS Cognito)
  - Verbindung über den Bundes-Proxy, ausserhalb des Bundesnetzes automatisch direkt
- Koordinaten in LV95 (EPSG:2056)

### Tests

```bash
pytest test/test_functions.py -v
```
