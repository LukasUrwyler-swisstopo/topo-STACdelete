# STAC / GDWH Deleting-Tool

Löscht Daten gezielt aus dem **Geodata-Warehouse (GDWH)** und aus **STAC** (Collection `ch.swisstopo.spezialbefliegungen`) – typischerweise, um einen fehlerhaften Import vor einem Re-Import sauber zu entfernen.

> ⚠️ **Löschungen sind endgültig.** Es gibt keinen Papierkorb und keine Wiederherstellung. Neue Abläufe immer zuerst auf **INT** ausprobieren, erst dann auf **PROD**.

## Auf einen Blick

| Tab | Was wird gelöscht? | Anmeldung |
|---|---|---|
| **GDWH Imports** | ganze DataPackages (Imports) | automatisch über die Windows-Anmeldung |
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
- **Python 3.6+** mit dem Paket `requests`. Das zusätzlich nötige `requests-negotiate-sspi` installiert das Tool beim ersten Start selbst.
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

## Tab „GDWH Imports“ – DataPackages löschen

### Schritt für Schritt

1. **Umgebung wählen** (Abschnitt 1): INT = Test, PROD = Live-Daten.
2. **GDS-Key wählen** (Abschnitt 2, **Pflicht**), z.B. `SB_DSM` oder `SB_DOP`. Das Feld ist anfangs leer – ohne GDS-Key lässt sich nichts laden. Mit **Alle GDS** landen alle GDS-Keys in einer gemeinsamen Liste – jede Zeile zeigt trotzdem ihren eigenen GDS-Key, und gelöscht wird jeweils unter dem richtigen.
   Ein Wechsel des GDS-Keys nach dem Laden leert die Liste wieder.
3. **Imports laden** (Abschnitt 1, links neben INT/PROD). Der Button zeigt, wo das Laden steht:

   | Button | Bedeutung |
   |---|---|
   | 🟡 **Imports laden** (gesperrt) | GDS-Key fehlt noch – darunter steht ein Hinweis |
   | 🟡 **Imports laden** | bereit zum Laden |
   | 🟡 **Imports werden geladen** | lädt – Umgebung und GDS-Key sind solange gesperrt |
   | 🟢 **Imports geladen** | Liste ist vollständig. Nochmals klicken = neu laden |

4. **Liste eingrenzen** (Abschnitt 2). Die Filter wirken sofort, ohne neu zu laden, und gelten gleichzeitig:
   - **Auftragstyp:** KRY / RAM / Alle (voreingestellt ist KRY)
   - **Jahr:** z.B. `2024`
   - **AREA:** z.B. `OBERAAR`
   - **datapackageId:** die ganze ID einfügen oder nur einen Teil davon, Gross-/Kleinschreibung egal

   Packages, bei denen GDWH (noch) kein Jahr, keine AREA oder keinen Auftragstyp kennt, werden von diesen Filtern nicht ausgeblendet.
5. **Packages ankreuzen** – einzeln oder mit **Alle auswählen** (wählt nur, was gerade sichtbar ist).
6. Optional: **E-Mail** eintragen – GDWH schickt nach Abschluss eine Benachrichtigung.
7. **Ausgewählte DataPackages löschen …** → [Sicherheitsabfrage](#sicherheitsabfrage-beide-tabs) bestätigen.

### So liest man einen Eintrag

```
☐ 2024  OBERAAR    [SB_DSM · Dateiformat]
        KRY    Aufnahmedatum
        Kommentar   ·   Importdatum
        datapackageId: 3f2a9c1e-5b7d-4e2a-9c1f-0a1b2c3d4e5f   [⧉ Kopieren]
```

- Die **datapackageId** ist der eindeutige Nachweis, welches DataPackage importiert wurde. Genau diese ID schickt das Tool beim Löschen an GDWH. `⧉ Kopieren` legt sie in die Zwischenablage.
- Fehlen Auftragstyp und Aufnahmedatum, steht in Zeile 2 der Schwerpunkt des Footprints (LV95).

### Warum lässt sich ein Package nicht ankreuzen?

| Anzeige | Bedeutung | Was tun? |
|---|---|---|
| ⏳ **Frisch importiert** (gelb, Jahr „NEU“) | Der Import ist jünger als 24 h. GDWH ergänzt Area, Jahr und Auftragstyp erst nach einigen Stunden. Beim Laden erscheint dazu ein Hinweis. | Später nochmals laden. |
| ⚠ **Kein FileMetadata-Match seit über 24h** (rot) | GDWH-Anomalie: Import ohne Metadaten, z.B. Rest einer früheren, unvollständigen Löschung. Nicht auswählbar, bis geklärt ist, ob die Daten noch existieren. | datapackageId kopieren und im GDWH-Portal prüfen. Der Button **GDWH-Anomalien anzeigen (>24h ohne Daten)** zeigt nur diese Fälle. |
| ⚠ **Status: … (nicht löschbar)** | GDWH löscht nur Packages mit Status „Imported“. | Status im GDWH-Portal prüfen. |

### Was passiert beim Löschen?

1. Das Tool startet für jedes ausgewählte Package einen Lösch-Auftrag (Job) im GDWH.
2. Es verfolgt alle Jobs gleichzeitig (Abfrage alle 4 s, höchstens 300 s). Den Fortschritt zeigt die Statusanzeige, Details stehen im Log-Fenster.
3. Erst wenn ein Job erfolgreich war, räumt das Tool zusätzlich den Ordner des Packages im Ingest-Bucket auf.

| Ergebnis | In der Liste | Was tun? |
|---|---|---|
| ✅ Erfolgreich bestätigt | verschwindet | – |
| ❌ Fehlgeschlagen | bleibt stehen | Fehler im Log prüfen, ggf. nochmals löschen |
| ❔ Status unklar / Timeout | bleibt stehen | per E-Mail-Benachrichtigung oder im GDWH-Portal prüfen (der Bucket wird hier bewusst nicht aufgeräumt) |

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
6. **Ausgewählte Assets löschen …** → [Sicherheitsabfrage](#sicherheitsabfrage-beide-tabs) bestätigen.

Wird ein Item durch die Löschung ganz leer, löscht das Tool es automatisch mit – die Sicherheitsabfrage zeigt das vorher an. Erfolgreich gelöschte Einträge verschwinden aus der Liste, fehlgeschlagene bleiben für einen neuen Versuch stehen.

### Weitere Ansichten und Abkürzungen

- **ITEMs only with Thumbnail** – Items, die nur noch aus dem Thumbnail bestehen (keine Nutzdaten).
- **ITEMs ohne Thumbnail** – nur bei Auftragstyp RAM sichtbar, weil dort ein Thumbnail Pflicht ist.
- **Doppelklick** auf ein Asset öffnet es im Browser.
- **Rechtsklick:** URL kopieren, im Browser öffnen, Item-ID kopieren, im STAC Browser öffnen.
- **STAC Browser öffnen** (Abschnitt 1) öffnet die Collection im STAC Browser und kopiert den Link.

> **Gelöscht, aber noch sichtbar?** Ein gelöschtes Asset bleibt bis ca. **15 Minuten** in der ITEM-Liste und über seinen Download-Link erreichbar. Das ist eine Verzögerung auf Seite STAC (Katalog und Speicher), kein Fehler – nach 15 Minuten neu laden.

---

## Sicherheitsabfrage (beide Tabs)

Vor jeder Löschung erscheint ein roter Dialog mit Umgebung und Anzahl der betroffenen Daten:

1. Häkchen setzen: „Ich verstehe, dass die Daten permanent und unwiderruflich gelöscht werden.“
2. Den Namen der Umgebung eintippen (`INT` oder `PROD`).
3. Erst dann wird **JETZT LÖSCHEN** aktiv.

Während eine Löschung läuft, lässt sich die Umgebung nicht wechseln.

## Protokolle

Im Ordner `logs/` (nicht in Git):

- `stac_gdwh_delete_JJJJ-MM-TT.log` – Tagesprotokoll
- `LOG_<STAC|GDWH>_<INT|PROD>_<Jahr>_<Area>_<Datum>.log` – ein Protokoll pro Löschvorgang

## Probleme und Lösungen

| Problem | Lösung |
|---|---|
| GDWH: Laden schlägt fehl | Bundesnetz/VPN prüfen. GDWH nutzt die Windows-Anmeldung – das GDWH-Portal muss im Browser erreichbar sein. |
| GDWH: Liste leer, obwohl die datapackageId stimmt | Auftragstyp, Jahr und AREA prüfen (z.B. Auftragstyp auf „Alle“). Ist die ID nur durch diese Filter ausgeblendet, zeigt die leere Liste einen Hinweis. |
| STAC: „Credentials laden“ meldet einen Fehler | Gibt es `secrets/stac_credentials.json`, und ist sie wie oben aufgebaut? |
| STAC: gelöschtes Asset noch sichtbar | ca. 15 Minuten warten, dann neu laden. |
| Erster Start: Installation von `requests-negotiate-sspi` schlägt fehl | Manuell installieren: `python -m pip install --user requests-negotiate-sspi --proxy http://proxy-bvcol.admin.ch:8080` |

---

## Technische Details

- **GDWH API v2** – INT `ltgdwhi.adr.admin.ch`, PROD `ltgdwh.adr.admin.ch` ([Swagger INT](https://ltgdwhi.adr.admin.ch/gdwh-api/v2/swagger/index.html))
  - Laden: `GET /api/geodatasets/{gdsKey}/data/imports`, Metadaten über `POST …/fileMetadata/search` (verknüpft über `importUuid` = `uuid` = datapackageId)
  - Löschen: `DELETE …/data/imports/{datapackageId}` → Job, verfolgt über `GET /api/jobs/{jobId}`
  - Bucket aufräumen: `DELETE …/dataPackages/{datapackageId}`
  - Anmeldung per Windows-SSPI, direkte Verbindung ohne Proxy
- **STAC API** – INT `sys-data.int.bgdi.ch`, PROD `data.geo.admin.ch`
  - Lesen über v1, Löschen vorerst über v0.9: v1 akzeptiert keine Basic Auth mehr, nur noch JWT (AWS Cognito)
  - Verbindung über den Bundes-Proxy, ausserhalb des Bundesnetzes automatisch direkt
- `secrets/proxy_config.json` (optional): zusätzliche Proxies für die automatische Paket-Installation
- Koordinaten in LV95 (EPSG:2056)

### Tests

```bash
pytest test/test_functions.py -v
```
