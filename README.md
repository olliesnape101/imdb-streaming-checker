# Check Streaming Platforms From IMDb Lists

## Description

This repo is a web-based application running locally via [Flask](https://flask.palletsprojects.com/en/stable/). Users can upload an IMDb list of films/TV shows, and see streaming platform availability for any user-selected regions. This is ideal for VPN users who wish to see which films and shows are available across different regions, using their subscriptions.

Users can filter by film attributes (e.g. IMDb rating, year, etc), as well as available streaming sites across any selected regions. Streaming platform data is fetched using the [TMDB API](https://developer.themoviedb.org/docs/getting-started).

**Please note:** for large lists, there will be a longer wait time when first fetching, but data is stored locally to prevent re-fetches. If any data is outdated, you'll be prompted if you wish to refresh or simply use stored data.

The regions with available platform data are:

- United Kingdom
- United States
- Canada
- Australia
- Germany
- France
- Spain
- Italy

---
## How to Run

### Step 0: Clone Repository

Run this via terminal:

```bash
git clone https://github.com/olliesnape101/imdb-streaming-checker.git
````

Then navigate to the project directory:

```bash
cd imdb-streaming-checker
```

### Step 1: Install dependencies

In the root directory, run:

```bash
pip install -r requirements.txt
```

### Step 2: Get your TMDB API key

For personal use (see [terms of use](https://www.themoviedb.org/api-terms-of-use?language=en-GB)), you can obtain a TMDB API key for free via their developer plan:

1. Sign up for an account at [TMDB](https://www.themoviedb.org/)
2. Sign in and head to [API subscription settings](https://www.themoviedb.org/subscription)
3. Sign up for a **Free Developer** plan to generate your API key
4. Once done, you should see your API key at the bottom of [this page](https://www.themoviedb.org/settings/api) (it should look something like the key below), then copy your key for later use

```
Example API key (this is NOT a valid key):
a1bc23d456e1ad3adw4fea23ad3dw23f
```

### Step 3: API key in `.env`

Create a `.env` file in the root directory:

```bash
code .env
```

Inside it, add the below, pasting in your TMDB API key:

```
TMDB_API_KEY=your_tmdb_api_key_here
```

### 4. Run the application

From the root directory:

```bash
flask run
```

Then open the URL shown in your terminal (typically http://127.0.0.1:5000)

---

## Files Included

```
.
├── app.py
│   └─ Main Flask application. Handles routing, file uploads,
│      CSV processing, database operations, and rendering templates.
│
├── imdb_parser.py
│   └─ Reads and parses IMDb CSV exports into Python dictionaries.
│      Normalises fields (types, genres, years, ratings, etc.).
│
├── tmdb_api.py
│   └─ Interfaces with the TMDb API. Fetches streaming providers,
│      manages caching in SQLite, and handles refresh logic.
│
├── requirements.txt
│   └─ Lists Python dependencies needed to run the project.
│
├── .env
│   └─ Stores your TMDB_API_KEY. Must be created manually by the user as above.
│      Format:
│          TMDB_API_KEY=your_api_key_here
│
├── watchlist.db
│   └─ SQLite database storing cached provider data for titles.
│      Auto-generated when running the app.
│
├── uploads/
│   └─ Stores uploaded IMDb CSV files.
│
├── templates/
│   ├── index.html
│   │   └─ Homepage. Lets users upload CSVs, select regions, and
│   │      choose between existing files or new uploads.
│   │
│   ├── instructions.html
│   │   └─ Step-by-step guide showing users how to export IMDb lists properly.
│   │
│   └── results.html
│       └─ Displays full streaming availability results with sorting,
│          filtering, SNA toggles, platform grouping, and JS logic.
│
├── static/
│   └── css/
│       └── styles.css
│           └─ Styling for all pages, buttons, forms, filter panels,
│              tables, layout, and responsive formatting.
│
└── README.md
    └─ Documentation for the project, how it works, installation,
       environment setup, and CS50 video link.
```
