import os
import json
from datetime import date

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

from imdb_parser import parse_imdb_csv
from tmdb_api import get_providers_fresh, get_providers_cached, sql_delete

load_dotenv()

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"


# ============================================================
# Watchlist metadata helpers
# ============================================================

def _watchlist_meta_path(csv_filename: str) -> str:
    """
    Store watchlist-level metadata next to the CSV, as:
        uploads/<csv_filename>.json
    """
    return os.path.join(app.config["UPLOAD_FOLDER"], f"{csv_filename}.json")


def load_watchlist_meta(csv_filename: str) -> dict:
    path = _watchlist_meta_path(csv_filename)
    if not os.path.exists(path):
        return {"filename": csv_filename, "regions": {}}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "regions" not in data or not isinstance(data["regions"], dict):
        data["regions"] = {}
    if "filename" not in data:
        data["filename"] = csv_filename

    return data


def save_watchlist_meta(csv_filename: str, meta: dict) -> None:
    meta.setdefault("filename", csv_filename)
    path = _watchlist_meta_path(csv_filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)


# ============================================================
# INDEX PAGE
# ============================================================

@app.route("/")
def index():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    files = os.listdir(app.config["UPLOAD_FOLDER"])

    # CSV files
    existing_files = [f for f in files if f.lower().endswith(".csv")]

    # Metadata JSON files
    meta_files = [f for f in files if f.lower().endswith(".json")]

    # SQL rows exist?
    import sqlite3
    conn = sqlite3.connect("cache.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM film_cache")
    db_count = c.fetchone()[0]
    conn.close()

    # Show button if ANY data exists anywhere
    show_delete_all = (
        len(existing_files) > 0 or
        len(meta_files) > 0 or
        db_count > 0
    )

    return render_template(
        "index.html",
        existing_files=existing_files,
        show_delete_all=show_delete_all
    )

# ============================================================
# INSTRUCTIONS PAGE
# ============================================================

@app.route("/instructions")
def instructions():
    return render_template("instructions.html")

# ============================================================
# WATCHLIST INFO (for popup)
# ============================================================

@app.route("/watchlist_info", methods=["POST"])
def watchlist_info():
    payload = request.get_json(force=True)
    filename = (payload.get("filename") or "").strip()
    regions = payload.get("regions") or []

    if not filename:
        return jsonify({"error": "Missing filename"}), 400

    meta = load_watchlist_meta(filename)
    out = {}

    for r in regions:
        last_date = meta["regions"].get(r)
        if last_date:
            out[r] = {"status": "has_data", "date": last_date}
        else:
            out[r] = {"status": "no_data"}

    return jsonify({"regions": out})


# ============================================================
# DELETE FILE
# ============================================================

@app.route("/delete/<filename>", methods=["DELETE"])
def delete_file(filename):
    csv_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    meta_path = _watchlist_meta_path(filename)

    # 1. Parse the CSV FIRST → extract imdb_ids BEFORE deleting it
    imdb_ids = []
    if os.path.exists(csv_path):
        try:
            films = parse_imdb_csv(csv_path)
            imdb_ids = [film["imdb_id"] for film in films]
        except Exception:
            pass

    # 2. Identify imdb_ids also used in OTHER watchlists
    other_watchlists = [
        f for f in os.listdir(app.config["UPLOAD_FOLDER"])
        if f.endswith(".csv") and f != filename
    ]

    shared_ids = set()
    for wl in other_watchlists:
        path = os.path.join(app.config["UPLOAD_FOLDER"], wl)
        try:
            other_films = parse_imdb_csv(path)
            other_ids = {film["imdb_id"] for film in other_films}
            shared_ids |= (set(imdb_ids) & other_ids)
        except Exception:
            pass

    # 3. Delete CSV + meta JSON
    if os.path.exists(csv_path):
        os.remove(csv_path)

    if os.path.exists(meta_path):
        os.remove(meta_path)

    # 4. Delete per-film cache JSONs NOT shared with other lists
    for imdb_id in imdb_ids:
        if imdb_id in shared_ids:
            continue
        sql_delete(imdb_id)

    return ("", 204)

# ============================================================
# DELETE ALL FILES
# ============================================================

@app.route("/delete_all", methods=["DELETE"])
def delete_all():
    # 1. Delete all CSVs and all metadata JSONs
    folder = app.config["UPLOAD_FOLDER"]
    for f in os.listdir(folder):
        path = os.path.join(folder, f)
        os.remove(path)

    # 2. Clear SQL cache table
    import sqlite3
    conn = sqlite3.connect("cache.db")
    c = conn.cursor()
    c.execute("DELETE FROM film_cache")
    conn.commit()
    conn.close()

    return ("", 204)


# ============================================================
# PROCESS WATCHLIST → BUILD RESULTS
# ============================================================

@app.route("/process", methods=["POST"])
def process():

    selected_name = (request.form.get("existing_file") or "").strip()

    upload = request.files.get("file")
    upload_valid = upload and upload.filename != ""

    regions = request.form.getlist("regions")
    if not regions:
        regions = ["GB"]

    if not selected_name and not upload_valid:
        return "Please upload a file or choose an existing one.", 400

    today_str = date.today().isoformat()

    # Is the *uploaded* file the one whose radio is selected?
    selected_source = request.form.get("selected_source", "existing")

    is_new_upload_selected = (
        upload_valid
        and selected_source == "uploaded"
    )

    # ------------------------------------------------------------
    # Decide CSV path, and handle overwrite behaviour if needed
    # ------------------------------------------------------------
    csv_filename: str
    filepath: str
    films = []
    meta = None  # will be set below

    if is_new_upload_selected:
        # User chose the newly uploaded file (radio for that file).
        # If a CSV with that name already exists, we treat this as an overwrite
        # and must:
        #   1) Parse the OLD CSV first → old_imdb_ids
        #   2) See which of those are in other watchlists
        #   3) Save the new CSV (overwrite)
        #   4) Parse the NEW CSV → new_imdb_ids
        #   5) Delete cache JSONs for imdb_ids that were only in the old list
        #      and not in any other watchlist
        csv_filename = upload.filename
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], csv_filename)

        old_imdb_ids = []
        ids_in_other_lists = set()

        if os.path.exists(filepath):
            # 1) Read old CSV → old_imdb_ids
            try:
                old_films = parse_imdb_csv(filepath)
                old_imdb_ids = [f["imdb_id"] for f in old_films]
            except Exception:
                old_imdb_ids = []

            # 2) Check other watchlists for shared ids
            other_watchlists = [
                f for f in os.listdir(app.config["UPLOAD_FOLDER"])
                if f.endswith(".csv") and f != csv_filename
            ]
            for wl in other_watchlists:
                wl_path = os.path.join(app.config["UPLOAD_FOLDER"], wl)
                try:
                    wl_films = parse_imdb_csv(wl_path)
                    wl_ids = {f["imdb_id"] for f in wl_films}
                    ids_in_other_lists |= (set(old_imdb_ids) & wl_ids)
                except Exception:
                    pass

        # 3) Save the new CSV (overwrite or create)
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        upload.save(filepath)

        # 4) Parse the NEW CSV
        films = parse_imdb_csv(filepath)
        new_ids = {f["imdb_id"] for f in films}

        # 5) Delete cache JSONs for imdb_ids that were only in the OLD version
        #    of this watchlist and are not used elsewhere and not in new list
        for imdb_id in old_imdb_ids:
            if imdb_id in new_ids:
                continue
            if imdb_id in ids_in_other_lists:
                continue
            film_json = os.path.join("cache", f"{imdb_id}.json")
            if os.path.exists(film_json):
                os.remove(film_json)

        # Overwrite metadata completely for this watchlist (fresh regions)
        meta = {"filename": csv_filename, "regions": {}}

    else:
        # Using a previously uploaded file, ignore the uploaded file
        csv_filename = selected_name
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], csv_filename)

        if not os.path.exists(filepath):
            return "Selected file not found.", 400

        films = parse_imdb_csv(filepath)
        meta = load_watchlist_meta(csv_filename)
        # IMPORTANT: do NOT save the uploaded file here
        upload_valid = False

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], csv_filename)

        # If a new file was uploaded but not saved yet, save it now
        if upload_valid and not os.path.exists(filepath):
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            upload.save(filepath)

        if not os.path.exists(filepath):
            return "Selected file not found.", 400

        films = parse_imdb_csv(filepath)
        meta = load_watchlist_meta(csv_filename)

    # ------------------------------------------------------------
    # Refresh vs cached logic
    # ------------------------------------------------------------
    refresh_mode = request.form.get("refresh_mode", "auto")  # "refresh" / "use_saved" / "auto"
    existing_dates = meta.get("regions", {})

    refresh_regions = set()
    cached_regions = set()

    if is_new_upload_selected:
        # New upload always "refresh" for selected regions (per-film logic
        # inside tmdb_api will still skip refetch if up to date for today).
        refresh_regions = set(regions)
    else:
        for r in regions:
            last = existing_dates.get(r)
            if last is None:
                # No stored data for this region on this watchlist
                refresh_regions.add(r)
            else:
                if refresh_mode == "refresh":
                    refresh_regions.add(r)
                else:
                    cached_regions.add(r)

    # ------------------------------------------------------------
    # Build provider data for every film
    # ------------------------------------------------------------
    results = []

    for film in films:
        imdb_id = film["imdb_id"]
        imdb_type = film["type"]
        providers = {}

        if refresh_regions:
            fresh = get_providers_fresh(imdb_id, imdb_type, list(refresh_regions), today_str)
            providers.update(fresh["providers"])

        if cached_regions:
            cached = get_providers_cached(imdb_id, list(cached_regions))
            providers.update(cached["providers"])

        for r in regions:
            providers.setdefault(r, [])

        film["providers"] = providers
        results.append(film)

    # ------------------------------------------------------------
    # Update watchlist metadata for refreshed regions
    # ------------------------------------------------------------
    if refresh_regions:
        # For overwrite case we already ensured meta has fresh "regions": {}
        for r in refresh_regions:
            meta["regions"][r] = today_str
        save_watchlist_meta(csv_filename, meta)

    return render_template(
        "results.html",
        results=results,
        regions=regions,
        filename=csv_filename
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)
