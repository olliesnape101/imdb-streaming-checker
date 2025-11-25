import csv

def parse_imdb_csv(file_path):
    """
    Reads the IMDb CSV export and returns a list of film dictionaries.
    """

    films = []

    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:

            imdb_id = row.get("Const", "").strip()
            if not imdb_id:
                continue  # skip malformed rows

            title = row.get("Title", "").strip()
            type_raw = row.get("Title Type", "").strip()

            # Normalise type names a bit
            type_map = {
                "movie": "Movie",
                "tvSeries": "TV Series",
                "tvMiniSeries": "TV Mini-Series",
                "tvEpisode": "TV Episode",
                "short": "Short",
                "video": "Video",
                "tvMovie": "TV Movie"
            }
            type_clean = type_map.get(type_raw, type_raw)

            # Position in the list (used for sorting: recently added)
            try:
                position = int(row.get("Position", "").strip())
            except:
                position = None

            # Year
            try:
                year = int(row.get("Year", "").strip())
            except:
                year = None

            # IMDb Rating
            try:
                rating = float(row.get("IMDb Rating", "").strip())
            except:
                rating = None

            # Runtime (mins)
            try:
                runtime = int(row.get("Runtime (mins)", "").strip())
            except:
                runtime = None

            # Genres (split comma-separated)
            genres_raw = row.get("Genres", "").strip()
            genres = [g.strip() for g in genres_raw.split(",") if g.strip()] if genres_raw else []

            # Directors
            directors = row.get("Directors", "").strip()

            films.append({
                "imdb_id": imdb_id,
                "title": title,
                "type": type_clean,
                "position": position,      # ⭐ NEW — used for sorting
                "year": year,
                "genres": genres,
                "rating": rating,
                "runtime": runtime,
                "directors": directors
            })

    return films
