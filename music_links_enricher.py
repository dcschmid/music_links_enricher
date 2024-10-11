import os
import json
import requests
import discogs_client
import logging
import base64
import time
from fuzzywuzzy import fuzz
import jwt

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up API keys from environment variables
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
DEEZER_API_URL = "https://api.deezer.com/"
DISCOGS_API_TOKEN = os.getenv("DISCOGS_API_TOKEN")
MUSICBRAINZ_API_URL = "https://musicbrainz.org/ws/2/"
APPLE_MUSIC_KEY_ID = os.getenv("APPLE_MUSIC_KEY_ID")
APPLE_MUSIC_TEAM_ID = os.getenv("APPLE_MUSIC_TEAM_ID")
APPLE_MUSIC_PRIVATE_KEY_PATH = os.getenv("APPLE_MUSIC_PRIVATE_KEY_PATH")

# Common title variants to improve search results
TITLE_VARIANTS = [
    "Deluxe", "Remastered", "Anniversary", "Special Edition", "Expanded Edition", "Live",
    "Reissue", "Bonus Tracks", "Limited Edition", "Original", "Collector's Edition"
]
ALBUM_TYPES = ["album", "ep", "compilation", "live"]

def rate_limit(delay: float = 2.0) -> None:
    """Introduce a delay before executing the next function call to avoid hitting the rate limit for various APIs."""
    time.sleep(delay)

def clean_artist_name(artist: str) -> str:
    """Clean the artist's name by removing any text after a question mark or other unwanted characters."""
    return artist.split('?')[0].strip()

def fuzzy_match(target, candidate, threshold=85):
    """Compares the target string against the candidate string and returns True if the fuzzy match ratio between the two strings exceeds the specified threshold."""
    return fuzz.token_sort_ratio(target, candidate) >= threshold or target.lower() in candidate.lower()

def authenticate_spotify() -> str | None:
    """Authenticate with Spotify using client ID and secret."""
    auth_url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    headers = {"Authorization": f"Basic {auth_header}"}
    data = {"grant_type": "client_credentials"}
    response = requests.post(auth_url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json().get("access_token")
    logging.error(f"Spotify authentication failed: {response.status_code} - {response.text}")
    return None

def authenticate_apple_music() -> str:
    """Generate a JWT for Apple Music API authentication."""
    with open(APPLE_MUSIC_PRIVATE_KEY_PATH, 'r') as f:
        private_key = f.read()

    headers = {'alg': 'ES256', 'kid': APPLE_MUSIC_KEY_ID}
    payload = {'iss': APPLE_MUSIC_TEAM_ID, 'iat': int(time.time()), 'exp': int(time.time()) + 3600}

    token = jwt.encode(payload, private_key, algorithm='ES256', headers=headers)

    return token.decode('utf-8') if isinstance(token, bytes) else token

def get_apple_music_preview(artist, album, possible_songs, token):
    """Search for an album or song preview URL on Apple Music with album variants."""
    url = f"https://api.music.apple.com/v1/catalog/de/search"
    headers = {"Authorization": f"Bearer {token}"}

    # Try album preview using variants
    for variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
        params = {'term': f'{artist} {variant}', 'types': 'albums', 'limit': 1}
        response = requests.get(url, headers=headers, params=params)
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if 'albums' in data['results'] and data['results']['albums']['data']:
                album_data = data['results']['albums']['data'][0]
                album_id = album_data['id']

                # Fetch album tracks to get previews
                album_tracks_response = requests.get(f"https://api.music.apple.com/v1/catalog/de/albums/{album_id}/tracks", headers=headers)
                if album_tracks_response.status_code == 200:
                    album_tracks_data = album_tracks_response.json()
                    for track in album_tracks_data['data']:
                        if 'previews' in track['attributes'] and track['attributes']['previews']:
                            preview_url = track['attributes']['previews'][0]['url']
                            logging.info(f"Found Apple Music album preview for track: {track['attributes']['name']} - {preview_url}")
                            return preview_url

    # If no album preview, try to get a song preview
    for song in possible_songs:
        params = {'term': f'{artist} {song}', 'types': 'songs', 'limit': 1}
        response = requests.get(url, headers=headers, params=params)
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if 'songs' in data['results'] and data['results']['songs']['data']:
                song_data = data['results']['songs']['data'][0]
                if 'previews' in song_data['attributes'] and song_data['attributes']['previews']:
                    preview_url = song_data['attributes']['previews'][0]['url']
                    logging.info(f"Found Apple Music song preview: {song_data['attributes']['name']} - {preview_url}")
                    return preview_url

    logging.info("No Apple Music preview found.")
    return None


def get_deezer_preview(artist, album, possible_songs):
    """Search for an album or song preview URL on Deezer."""
    deezer_tracks = []

    # Deezer API URL
    DEEZER_API_URL = "https://api.deezer.com"

    # Search for album using variants
    for variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
        response = requests.get(f"{DEEZER_API_URL}/search/album?q=artist:'{artist}' album:'{variant}'")
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if 'data' in data and data['data']:
                album_data = data['data'][0]  # Take the first matching album
                album_id = album_data['id']

                # Get the album's tracklist to find previews
                album_tracks_response = requests.get(f"{DEEZER_API_URL}/album/{album_id}/tracks")
                if album_tracks_response.status_code == 200:
                    album_tracks_data = album_tracks_response.json()
                    for track in album_tracks_data['data']:
                        if 'preview' in track and track['preview']:
                            logging.info(f"Found Deezer album preview for track: {track['title']} - {track['preview']}")
                            return track['preview']

    # If no album preview found, search for individual tracks
    for song in possible_songs:
        response = requests.get(f"{DEEZER_API_URL}/search/track?q=artist:'{artist}' track:'{song}'")
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if 'data' in data and data['data']:
                track_data = data['data'][0]  # Take the first matching track
                if 'preview' in track_data and track_data['preview']:
                    logging.info(f"Found Deezer song preview: {track_data['title']} - {track_data['preview']}")
                    return track_data['preview']

    logging.info("No Deezer preview found.")
    return None


def get_spotify_preview(artist, album, possible_songs, spotify_token):
    """Search for an album or song preview URL on Spotify."""
    headers = {"Authorization": f"Bearer {spotify_token}"}
    search_url = "https://api.spotify.com/v1/search"
    spotify_tracks = []

    # Search for album using variants
    for variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
        params = {"q": f"album:{variant} artist:{artist}", "type": "album", "limit": 1}
        response = requests.get(search_url, headers=headers, params=params)
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if data['albums']['items']:
                album_id = data['albums']['items'][0]['id']
                album_tracks_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}/tracks", headers=headers)

                if album_tracks_response.status_code == 200:
                    album_tracks_data = album_tracks_response.json()
                    for track in album_tracks_data['items']:
                        if 'preview_url' in track and track['preview_url']:
                            logging.info(f"Found Spotify album preview for track: {track['name']} - {track['preview_url']}")
                            return track['preview_url']  # Return the first available preview

    # If no album preview found, search for individual tracks
    for song in possible_songs:
        params = {"q": f"track:{song} artist:{artist}", "type": "track", "limit": 1}
        response = requests.get(search_url, headers=headers, params=params)
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if data['tracks']['items']:
                track = data['tracks']['items'][0]
                if 'preview_url' in track and track['preview_url']:
                    logging.info(f"Found Spotify song preview: {track['name']} - {track['preview_url']}")
                    return track['preview_url']

    logging.info("No Spotify preview found.")
    return None


def get_music_preview_link(artist, album, possible_songs, apple_music_token, spotify_token):
    """Get music preview from Apple Music, Deezer, or Spotify, in that order."""
    # Try Apple Music (album, song, artist)
    preview_url = get_apple_music_preview(artist, album, possible_songs, apple_music_token)
    if preview_url:
        return preview_url

    # Try Deezer (album, song, artist)
    preview_url = get_deezer_preview(artist, album, possible_songs)
    if preview_url:
        return preview_url

    # Try Spotify (album, song, artist)
    preview_url = get_spotify_preview(artist, album, possible_songs, spotify_token)
    if preview_url:
        return preview_url

    logging.info("No preview link found on Apple Music, Deezer, or Spotify.")
    return None

def get_apple_music_link(artist, album, possible_songs, token):
    """Search for an album, track, or artist on Apple Music and return the link."""
    url = f"https://api.music.apple.com/v1/catalog/de/search"
    headers = {"Authorization": f"Bearer {token}"}

    # Search for album using variants
    for variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
        params = {'term': f'{artist} {variant}', 'types': 'albums', 'limit': 1}
        response = requests.get(url, headers=headers, params=params)
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if 'albums' in data['results'] and data['results']['albums']['data']:
                album_data = data['results']['albums']['data'][0]
                album_url = album_data['attributes']['url']
                album_name = album_data['attributes']['name']
                artist_name = album_data['attributes']['artistName']
                logging.info(f"Found Apple Music album: {album_name} by {artist_name} - {album_url}")
                return album_url

    # If no album found, search for individual tracks from possible_songs
    for song in possible_songs:
        params = {'term': f'{artist} {song}', 'types': 'songs', 'limit': 1}
        response = requests.get(url, headers=headers, params=params)
        rate_limit()

        if response.status_code == 200:
            data = response.json()
            if 'songs' in data['results'] and data['results']['songs']['data']:
                song_data = data['results']['songs']['data'][0]
                song_url = song_data['attributes']['url']
                song_name = song_data['attributes']['name']
                logging.info(f"Found Apple Music song: {song_name} by {artist} - {song_url}")
                return song_url

    # If no album or track found, fallback to artist page
    params = {'term': f'{artist}', 'types': 'artists', 'limit': 1}
    response = requests.get(url, headers=headers, params=params)
    rate_limit()

    if response.status_code == 200:
        data = response.json()
        if 'artists' in data['results'] and data['results']['artists']['data']:
            artist_data = data['results']['artists']['data'][0]
            artist_url = artist_data['attributes']['url']
            logging.info(f"Found Apple Music artist: {artist} - {artist_url}")
            return artist_url

    logging.error(f"Failed to fetch from Apple Music. Status code: {response.status_code}")
    return None

def get_spotify_link(artist, album, possible_songs, spotify_token):
    """Search for an album, tracks, or artist on Spotify and return the link."""
    headers = {"Authorization": f"Bearer {spotify_token}"}
    search_url = "https://api.spotify.com/v1/search"
    artist_list = artist.split("&")
    spotify_tracks = []

    # Improve search with partial matches and variant handling
    for artist_name in artist_list:
        artist_name = artist_name.strip()

        try:
            # First try full album name with variants
            for variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
                params = {"q": f"album:{variant} artist:{artist_name}", "type": "album", "limit": 5}  # Limit results
                response = requests.get(search_url, headers=headers, params=params)
                rate_limit()

                if response.status_code == 200:
                    data = response.json()
                    if data['albums']['items']:
                        for album_data in data['albums']['items']:
                            album_name = album_data['name']
                            artist_result_name = album_data['artists'][0]['name']

                            # Use more flexible fuzzy matching for the album title and strict for artist
                            if fuzzy_match(album, album_name, threshold=80) and fuzzy_match(artist_name, artist_result_name, threshold=90):
                                album_id = album_data['id']
                                album_tracks_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}/tracks", headers=headers)
                                if album_tracks_response.status_code == 200:
                                    album_tracks_data = album_tracks_response.json()
                                    for track in album_tracks_data['items']:
                                        spotify_tracks.append(track['name'])
                                    logging.info(f"Found Spotify album link for '{artist_name}' - '{album}': {album_data['external_urls']['spotify']}")
                                    return album_data['external_urls']['spotify'], spotify_tracks

            # If no results found, broaden the search by looking for album name only
            params = {"q": f"album:{album}", "type": "album", "limit": 5}
            response = requests.get(search_url, headers=headers, params=params)
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if data['albums']['items']:
                    for album_data in data['albums']['items']:
                        album_name = album_data['name']
                        artist_result_name = album_data['artists'][0]['name']

                        # Again, fuzzy match album with a broader match for artist name
                        if fuzzy_match(album, album_name, threshold=85) and fuzzy_match(artist_name, artist_result_name, threshold=85):
                            album_id = album_data['id']
                            album_tracks_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}/tracks", headers=headers)
                            if album_tracks_response.status_code == 200:
                                album_tracks_data = album_tracks_response.json()
                                for track in album_tracks_data['items']:
                                    spotify_tracks.append(track['name'])
                                logging.info(f"Found Spotify album link (broader search) for '{artist_name}' - '{album}': {album_data['external_urls']['spotify']}")
                                return album_data['external_urls']['spotify'], spotify_tracks

        except Exception as e:
            logging.error(f"Error fetching Spotify album link for '{artist_name}' - '{album}': {e}")

    # Try searching for individual tracks
    for song in possible_songs:
        for artist_name in artist_list:
            artist_name = artist_name.strip()
            try:
                params = {"q": f"track:{song} artist:{artist_name}", "type": "track", "limit": 5}
                response = requests.get(search_url, headers=headers, params=params)
                rate_limit()

                if response.status_code == 200:
                    data = response.json()
                    if data['tracks']['items']:
                        logging.info(f"Found Spotify track link for '{artist_name}' - '{song}': {data['tracks']['items'][0]['external_urls']['spotify']}")
                        return data['tracks']['items'][0]['external_urls']['spotify'], spotify_tracks
            except Exception as e:
                logging.error(f"Error fetching Spotify track link for '{artist_name}' - '{song}': {e}")

    # Final fallback: search for artist page
    for artist_name in artist_list:
        artist_name = artist_name.strip()
        try:
            params = {"q": f"artist:{artist_name}", "type": "artist", "limit": 1}
            response = requests.get(search_url, headers=headers, params=params)
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if data['artists']['items']:
                    logging.info(f"Found Spotify artist page link for '{artist_name}': {data['artists'][0]['external_urls']['spotify']}")
                    return data['artists'][0]['external_urls']['spotify'], spotify_tracks
        except Exception as e:
            logging.error(f"Error fetching Spotify artist link for '{artist_name}': {e}")

    logging.info(f"No Spotify link found for '{artist}' - '{album}'")
    return None, spotify_tracks

def get_deezer_link(artist, album, possible_songs):
    """Search for an album, tracks, or artist on Deezer and return the link."""
    deezer_tracks = []

    def is_valid_match(result_album_name, result_artist_name, target_album_name, target_artist_name):
        return (fuzzy_match(target_album_name, result_album_name) and fuzzy_match(target_artist_name, result_artist_name))

    artist_list = artist.split("&")

    # Search for album using variants
    for artist_name in artist_list:
        artist_name = artist_name.strip()

        for variant in [album] + [f"{album} {suffix}" for suffix in TITLE_VARIANTS]:
            response = requests.get(f"{DEEZER_API_URL}search/album?q=artist:'{artist_name}' album:'{variant}'")
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    sorted_data = sorted(data['data'], key=lambda x: x.get('release_date', ''), reverse=True)

                    for album_data in sorted_data:
                        deezer_album = album_data['title']
                        deezer_artist = album_data['artist']['name']

                        if is_valid_match(deezer_album, deezer_artist, album, artist_name):
                            album_id = album_data['id']
                            album_tracks_response = requests.get(f"{DEEZER_API_URL}album/{album_id}")
                            if album_tracks_response.status_code == 200:
                                album_tracks_data = album_tracks_response.json()
                                for track in album_tracks_data['tracks']['data']:
                                    deezer_tracks.append(track['title'])
                            logging.info(f"Found Deezer album link for '{artist_name}' - '{album}': {album_data['link']}")
                            return album_data['link'], deezer_tracks

    # If no album found, search for individual tracks from possible_songs
    for song in possible_songs:
        for artist_name in artist_list:
            artist_name = artist_name.strip()
            response = requests.get(f"{DEEZER_API_URL}search/track?q=artist:'{artist_name}' track:'{song}'")
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    track_data = data['data'][0]
                    track_url = track_data['link']
                    track_name = track_data['title']
                    logging.info(f"Found Deezer track link for '{track_name}' by {artist_name} - {track_url}")
                    return track_url, deezer_tracks

    # Fallback: search for artist page
    for artist_name in artist_list:
        artist_name = artist_name.strip()
        try:
            response = requests.get(f"{DEEZER_API_URL}search/artist?q={artist_name}")
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    artist_data = data['data'][0]
                    artist_url = artist_data['link']
                    logging.info(f"Found Deezer artist page link for '{artist_name}': {artist_url}")
                    return artist_url, deezer_tracks
        except Exception as e:
            logging.error(f"Error fetching Deezer artist link for '{artist_name}': {e}")

    logging.info(f"No Deezer link found for '{artist}' - '{album}'")
    return None, deezer_tracks

def update_json_with_links(file_path):
    """Reads a JSON file, updates it with Spotify, Deezer, Apple Music, and preview links, and saves the updated JSON."""
    with open(file_path, 'r') as file:
        data = json.load(file)

    spotify_token = authenticate_spotify()
    apple_music_token = authenticate_apple_music()

    for album_data in data:
        artist = album_data['artist']
        album = album_data['album']

        possible_songs = []  # Add function to fetch possible songs from MusicBrainz or Discogs if needed
        spotify_link, spotify_tracks = get_spotify_link(artist, album, possible_songs, spotify_token)
        album_data['spotify_link'] = spotify_link

        deezer_link, deezer_tracks = get_deezer_link(artist, album, possible_songs)
        album_data['deezer_link'] = deezer_link

        apple_music_link = get_apple_music_link(artist, album, possible_songs, apple_music_token)
        album_data['apple_music_link'] = apple_music_link

        preview_url = get_music_preview_link(artist, album, possible_songs, apple_music_token, spotify_token)
        album_data['preview_link'] = preview_url

        possible_songs += spotify_tracks + deezer_tracks

    with open(file_path, 'w') as file:
        json.dump(data, file, indent=2)

    logging.info(f"Updated JSON saved to {file_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Update JSON with Spotify, Deezer, and Apple Music links")
    parser.add_argument("file_path", help="Path to the JSON file")
    args = parser.parse_args()

    update_json_with_links(args.file_path)
