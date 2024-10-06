# Music Links Enricher

This Python script enriches a JSON file with links to albums and tracks on Spotify and Deezer, as well as preview URLs (30-second snippets) when available. It searches for albums or tracks by artist name and album title and appends the relevant links to the JSON data.

## Features

- **Spotify Integration**: Finds Spotify album and track links using the Spotify Web API.
- **Deezer Integration**: Finds Deezer album and track links using the Deezer API.
- **Track Previews**: Provides 30-second preview URLs for tracks when available.
- **Fallback Logic**: If an album is not found, the script searches for individual tracks and artist pages.
- **MusicBrainz & Discogs**: Fetches tracklist data from MusicBrainz and Discogs as well.
- **Logging**: Provides detailed logging, including found Spotify and Deezer links, previews, and any errors.

## Requirements

- Python 3.x
- Spotify Developer Account with `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`
- Deezer API Access
- Discogs API Token
- MusicBrainz integration (no API key required)

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/dcschmid/music_links_enricher
cd music-links-enricher
```

### 2. Set Up a Virtual Environment

It is recommended to use a Python virtual environment to manage dependencies:

#### On macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

#### On Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

Once the virtual environment is activated, install the necessary Python packages:

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

You need to set up your environment variables for accessing Spotify, Deezer, and Discogs APIs. You can do this by creating a .env file in the project directory or exporting the variables in your terminal session.

```bash
export SPOTIFY_CLIENT_ID='your_spotify_client_id'
export SPOTIFY_CLIENT_SECRET='your_spotify_client_secret'
export DISCOGS_API_TOKEN='your_discogs_api_token'
```

### 5. Prepare Your Input JSON File

The script expects an input JSON file containing data about the albums. The file should have the following structure:

```json
[
    {
        "artist": "Artist Name",
        "album": "Album Title"
    }
]
```

### 6. Run the Script

To run the script and enrich your JSON file with Spotify, Deezer, and preview links, use the following command:

```bash
python music_links_enricher.py path/to/your/input.json
```

The script will modify the input JSON file by adding the following fields for each album:

- spotify_link: Link to the album or track on Spotify
- deezer_link: Link to the album or track on Deezer
- preview_url: Preview URL for a 30-second track snippet (if available)

#### Example:

```bash
python music_links_enricher.py albums.json
```

### 7. Deactivate the Virtual Environment

After you’ve finished running the script, you can deactivate the virtual environment using:

```bash
deactivate
```

### Logging

The script logs all found URLs and any errors encountered during the execution. It logs the following:

- Found Spotify and Deezer album links
- Found track preview URLs
- Errors when searching for albums or tracks

### Dependencies

Here are the core dependencies of the project, listed in requirements.txt:

- requests
- discogs-client
- fuzzywuzzy
- python-Levenshtein
- python-dotenv

Make sure to install these dependencies using the command:

```bash
pip install -r requirements.txt
```
