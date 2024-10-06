import os
import json
import requests
import discogs_client
import logging
import base64
import time
from fuzzywuzzy import fuzz

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up API keys from environment variables
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
DEEZER_API_URL = "https://api.deezer.com/"
DISCOGS_API_TOKEN = os.getenv("DISCOGS_API_TOKEN")
MUSICBRAINZ_API_URL = "https://musicbrainz.org/ws/2/"

def rate_limit(delay: float = 2.0) -> None:
    """
    Introduce a delay before executing the next function call to avoid hitting the rate limit for various APIs.

    Args:
        delay (float, optional): The duration of the delay in seconds. Defaults to 2.0.

    Returns:
        None
    """
    time.sleep(delay)

def clean_artist_name(artist: str) -> str:
    """
    Clean the artist's name by removing any text after a question mark or other unwanted characters.

    Args:
        artist (str): The artist's name that needs to be cleaned.

    Returns:
        str: The cleaned artist name.
    """
    # Split the string at the first question mark and return the first part
    # Remove leading and trailing whitespace
    return artist.split('?')[0].strip()

def fuzzy_match(target, candidate, threshold=85):
    """
    Compares the target string against the candidate string and returns True if the fuzzy
    match ratio between the two strings exceeds the specified threshold.

    Ensures that the target is contained within the candidate to avoid false positives.

    Args:
        target (str): The target string to compare against the candidate.
        candidate (str): The candidate string to compare against the target.
        threshold (int, optional): The minimum fuzzy match ratio required to return True.
            Defaults to 85.

    Returns:
        bool: True if the fuzzy match ratio between target and candidate exceeds the threshold,
            and the target is contained within the candidate.
    """
    return fuzz.token_sort_ratio(target, candidate) >= threshold or target.lower() in candidate.lower()

def authenticate_spotify() -> str | None:
    """
    Authenticate with Spotify using client ID and secret.

    Returns:
        str | None: An access token if authentication is successful, None otherwise.
    """
    # Encode client ID and secret as base64
    auth_url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    # Create the headers with the base64 encoded client ID and secret
    headers = {"Authorization": f"Basic {auth_header}"}
    # Create the data with the grant type
    data = {"grant_type": "client_credentials"}
    # Post the request to the Spotify API to obtain an access token
    response = requests.post(auth_url, headers=headers, data=data)
    # If the request is successful, return the access token
    if response.status_code == 200:
        return response.json().get("access_token")
    # If the request fails, log an error and return None
    logging.error(f"Spotify authentication failed: {response.status_code} - {response.text}")
    return None

def get_spotify_album_preview(spotify_token, album_id):
    """
    Fetch the preview URL for tracks from a specific Spotify album using the album's ID.

    :param spotify_token: The Spotify OAuth token
    :param album_id: The unique ID of the album to search for
    :return: Preview URL if found, otherwise None
    """
    # Set up the endpoint URL and parameters
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
    headers = {
        "Authorization": f"Bearer {spotify_token}",  # Include the OAuth token
        "Content-Type": "application/json"  # Set the content type to JSON
    }
    params = {
        "market": "DE"  # Set the market to Germany
    }

    # Make the request to the API
    response = requests.get(url, headers=headers, params=params)

    # Check if the request was successful
    if response.status_code == 200:
        data = response.json()

        # Loop through the tracks in the album to find the preview URL
        for track in data['items']:  # Iterate over the tracks in the album
            if track.get('preview_url'):  # Check if the track has a preview URL
                logging.info(f"Found Spotify album track preview for album '{album_id}': {track['preview_url']}")
                return track['preview_url']  # Return the preview URL
    else:
        logging.error(f"Failed to fetch tracks from Spotify album with ID '{album_id}'. Status code: {response.status_code}")

    return None  # Return None if no preview URL is found

def search_musicbrainz_for_album(artist, album):
    """
    Search MusicBrainz for an album using the artist and album name.

    Args:
        artist (str): The artist name.
        album (str): The album name.

    Returns:
        list: A list of track names found in MusicBrainz.
    """
    # Construct the URL and parameters for the search request
    url = f"{MUSICBRAINZ_API_URL}recording/"
    params = {'query': f'artist:"{artist}" AND release:"{album}"', 'fmt': 'json', 'limit': 10}
    # Set the User-Agent header to identify the application
    headers = {'User-Agent': 'MusicTriviaApp/1.0 (example@example.com)'}
    # Send the request to MusicBrainz
    response = requests.get(url, headers=headers, params=params)
    # Rate limit the requests to avoid hitting the limits
    rate_limit()

    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()
        # If the response contains recordings, extract the track titles
        if data.get('recordings'):
            tracks = [recording['title'] for recording in data['recordings']]
            return tracks
    # Log an info message if no matches were found
    logging.info(f"No matches found in MusicBrainz for {album} by {artist}")
    # Return an empty list if no matches were found
    return []

def get_discogs_album_tracks(artist, album):
    """
    Fetch album tracklist from Discogs.

    This function searches for an album in Discogs using the artist and album name,
    and returns the tracklist of the first result.

    Args:
        artist (str): The artist name.
        album (str): The album name.

    Returns:
        list: The tracklist of the album.
    """
    discogs_api = discogs_client.Client('MusicTriviaApp', user_token=DISCOGS_API_TOKEN)
    try:
        # Clean the artist name
        artist = clean_artist_name(artist)
        # Search for the album in Discogs
        results = discogs_api.search(album, artist=artist, type='release')
        # Rate limit the requests to avoid hitting the limits
        rate_limit()
        # If there are results, get the first one and extract the tracklist
        if results.count > 0:
            release = results[0]
            tracklist = [track.title for track in release.tracklist]

            return tracklist
    except Exception as e:
        # Log an error if something goes wrong
        logging.error(f"Error fetching Discogs data: {e}")
    # Log an info message if no matches were found
    logging.info(f"No matches found in Discogs for {album} by {artist}")
    # Return an empty list if no matches were found
    return []

def get_spotify_link(artist, album, possible_songs, spotify_token):
    """
    Search for an album, tracks, or artist on Spotify and return the link.

    The function first searches for an album with the given artist and album name.
    If no exact match is found, it tries a broader search based on album name only.
    If still no match is found, it searches for individual tracks.
    If still no match is found, it searches for an artist page.
    If no match is found at all, it returns None.
    """
    headers = {"Authorization": f"Bearer {spotify_token}"}
    search_url = "https://api.spotify.com/v1/search"
    artist_list = artist.split("&")
    spotify_tracks = []

    # Step 1: Search for an album and artist on Spotify
    for artist_name in artist_list:
        artist_name = artist_name.strip()

        try:
            params = {"q": f"album:{album} artist:{artist_name}", "type": "album"}
            response = requests.get(search_url, headers=headers, params=params)
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if data['albums']['items']:
                    for album_data in data['albums']['items']:
                        album_name = album_data['name']
                        artist_result_name = album_data['artists'][0]['name']

                        # Ensure both album and artist name have a good fuzzy match
                        if fuzzy_match(album, album_name) and fuzzy_match(artist_name, artist_result_name):
                            album_id = album_data['id']
                            # Fetch tracks from the matched album
                            album_tracks_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}/tracks", headers=headers)
                            if album_tracks_response.status_code == 200:
                                album_tracks_data = album_tracks_response.json()
                                for track in album_tracks_data['items']:
                                    spotify_tracks.append(track['name'])
                            logging.info(f"Found Spotify album link for '{artist_name}' - '{album}': {album_data['external_urls']['spotify']}")
                            return album_data['external_urls']['spotify'], spotify_tracks

            # If no exact match found, try a broader search based on album name only
            logging.info(f"No exact match for album '{album}' with artist '{artist_name}' found. Trying broader search.")
            params = {"q": f"album:{album}", "type": "album"}
            response = requests.get(search_url, headers=headers, params=params)
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if data['albums']['items']:
                    for album_data in data['albums']['items']:
                        album_name = album_data['name']
                        artist_result_name = album_data['artists'][0]['name']

                        # Ensure both album and artist name match more strictly
                        if fuzzy_match(album, album_name) and fuzzy_match(artist_name, artist_result_name):
                            album_id = album_data['id']
                            # Fetch tracks from the matched album
                            album_tracks_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}/tracks", headers=headers)
                            if album_tracks_response.status_code == 200:
                                album_tracks_data = album_tracks_response.json()
                                for track in album_tracks_data['items']:
                                    spotify_tracks.append(track['name'])
                            logging.info(f"Found Spotify album link in broader search for '{artist_name}' - '{album}': {album_data['external_urls']['spotify']}")
                            return album_data['external_urls']['spotify'], spotify_tracks

        except Exception as e:
            logging.error(f"Error fetching Spotify album link for '{artist_name}': {e}")

    # Step 2: Fallback - Search for individual tracks if no album is found
    for song in possible_songs:
        for artist_name in artist_list:
            artist_name = artist_name.strip()
            try:
                params = {"q": f"track:{song} artist:{artist_name}", "type": "track"}
                response = requests.get(search_url, headers=headers, params=params)
                rate_limit()

                if response.status_code == 200:
                    data = response.json()
                    if data['tracks']['items']:
                        logging.info(f"Found Spotify track link for '{artist_name}' - '{song}': {data['tracks']['items'][0]['external_urls']['spotify']}")
                        return data['tracks']['items'][0]['external_urls']['spotify'], spotify_tracks
            except Exception as e:
                logging.error(f"Error fetching Spotify track link for '{artist_name}' - '{song}': {e}")

    # Step 3: Fallback - Search for artist page if no album or track is found
    for artist_name in artist_list:
        artist_name = artist_name.strip()
        try:
            params = {"q": f"artist:{artist_name}", "type": "artist"}
            response = requests.get(search_url, headers=headers, params=params)
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if data['artists']['items']:
                    logging.info(f"Found Spotify artist page link for '{artist_name}': {data['artists'][0]['external_urls']['spotify']}")
                    return data['artists'][0]['external_urls']['spotify'], spotify_tracks
        except Exception as e:
            logging.error(f"Error fetching Spotify artist link for '{artist_name}': {e}")

    # Final fallback: No link found
    logging.info(f"No Spotify link found for '{artist}' - '{album}'")
    return None, spotify_tracks

def get_deezer_link(artist, album, possible_songs):
    """
    Search for an album, tracks, or artist on Deezer and return the link.

    The function first searches for an album with the given artist and album name.
    If no exact match is found, it tries a broader search based on album name only.
    If still no match is found, it searches for an artist page.
    If no match is found at all, it returns None.
    """
    deezer_tracks = []

    def normalize_string(value):
        """Normalize a string by lowercasing and trimming whitespace."""
        return value.lower().strip()

    def is_valid_match(result_album_name, result_artist_name, target_album_name, target_artist_name):
        """
        Returns True if the result album name contains the core target album name and artist names match.
        Uses fuzzy matching for a more accurate comparison.
        """
        return (fuzzy_match(target_album_name, result_album_name) and
                fuzzy_match(target_artist_name, result_artist_name))

    def search_deezer_for_artist(artist_name, album_name):
        """Helper function to search Deezer for an album by a given artist."""
        logging.info(f"Searching for album '{album_name}' by artist '{artist_name}' on Deezer.")
        response = requests.get(f"{DEEZER_API_URL}search/album?q=artist:'{artist_name}' album:'{album_name}'")
        rate_limit()
        if response.status_code == 200:
            return response.json()
        return None

    artist_list = artist.split("&")

    for artist_name in artist_list:
        artist_name = artist_name.strip()
        data = search_deezer_for_artist(artist_name, album)

        if data and data['data']:
            # Sort results by release date (newest first)
            sorted_data = sorted(data['data'], key=lambda x: x.get('release_date', ''), reverse=True)

            for album_data in sorted_data:
                deezer_album = album_data['title']
                deezer_artist = album_data['artist']['name']

                if is_valid_match(deezer_album, deezer_artist, album, artist_name):
                    album_id = album_data['id']
                    # Fetch the album tracks from Deezer
                    album_tracks_response = requests.get(f"{DEEZER_API_URL}album/{album_id}")
                    if album_tracks_response.status_code == 200:
                        album_tracks_data = album_tracks_response.json()
                        for track in album_tracks_data['tracks']['data']:
                            deezer_tracks.append(track['title'])
                    logging.info(f"Found Deezer album link for '{artist_name}' - '{album}': {album_data['link']}")
                    return album_data['link'], deezer_tracks

    # If no exact match, attempt a broader search based on album name only
    logging.info(f"No exact match for album '{album}'. Trying album name only on Deezer.")
    response = requests.get(f"{DEEZER_API_URL}search/album?q={album}")
    rate_limit()

    if response.status_code == 200:
        data = response.json()
        if data['data']:
            # Sort results by release date (newest first)
            sorted_data = sorted(data['data'], key=lambda x: x.get('release_date', ''), reverse=True)

            for album_data in sorted_data:
                deezer_album = album_data['title']
                deezer_artist = album_data['artist']['name']
                for artist_name in artist_list:
                    artist_name = artist_name.strip()
                    if is_valid_match(deezer_album, deezer_artist, album, artist_name):
                        album_id = album_data['id']
                        # Fetch the album tracks from Deezer
                        album_tracks_response = requests.get(f"{DEEZER_API_URL}album/{album_id}")
                        if album_tracks_response.status_code == 200:
                            album_tracks_data = album_tracks_response.json()
                            for track in album_tracks_data['tracks']['data']:
                                deezer_tracks.append(track['title'])
                        logging.info(f"Found Deezer album link for '{artist_name}' - '{album}': {album_data['link']}")
                        return album_data['link'], deezer_tracks

    # Fallback: Search for artist page if no album or track is found
    for artist_name in artist_list:
        artist_name = artist_name.strip()
        try:
            logging.info(f"Searching for artist '{artist_name}' on Deezer.")
            response = requests.get(f"{DEEZER_API_URL}search/artist?q={artist_name}")
            rate_limit()

            if response.status_code == 200:
                data = response.json()
                if data['data']:
                    logging.info(f"Found Deezer artist page link for '{artist_name}': {data['data'][0]['link']}")
                    return data['data'][0]['link'], deezer_tracks
        except Exception as e:
            logging.error(f"Error fetching Deezer artist link for '{artist_name}': {e}")

    logging.info(f"No Deezer link found for '{artist}' - '{album}'")
    return None, deezer_tracks

def get_preview_url(artist, album, possible_songs, spotify_token):
    """
    Get a preview URL from Deezer or Spotify for the album, song, or artist.

    The function first searches for the album on Deezer and tries to find a
    preview URL for an album track. If no album preview is found, it searches
    for previews for specific songs on Deezer. If no Deezer preview is found,
    it searches for previews for the album on Spotify. If no Spotify album
    preview is found, it searches for previews for specific songs on Spotify.
    """
    headers = {"Authorization": f"Bearer {spotify_token}"}
    search_url = "https://api.spotify.com/v1/search"
    artist_list = artist.split("&")

    # 1. Try to find a preview URL for the album on Deezer
    try:
        for artist_name in artist_list:
            artist_name = artist_name.strip()
            response = requests.get(f"{DEEZER_API_URL}search/album?q=artist:'{artist_name}' album:'{album}'")
            rate_limit()
            if response.status_code == 200:
                data = response.json()
                if data['data']:
                    for album_data in data['data']:
                        if fuzzy_match(album_data['title'], album):
                            album_id = album_data['id']
                            album_tracks_response = requests.get(f"{DEEZER_API_URL}album/{album_id}")
                            if album_tracks_response.status_code == 200:
                                album_tracks_data = album_tracks_response.json()
                                for track in album_tracks_data['tracks']['data']:
                                    if 'preview' in track and track['preview']:
                                        logging.info(f"Found Deezer album track preview for '{artist}' - '{album}': {track['preview']}")
                                        return track['preview']
    except Exception as e:
        logging.error(f"Error fetching Deezer album preview for '{artist}' - '{album}': {e}")

    # 2. Try to find previews for specific songs on Deezer
    for song in possible_songs:
        for artist_name in artist_list:
            artist_name = artist_name.strip()
            try:
                response = requests.get(f"{DEEZER_API_URL}search/track?q=artist:'{artist_name}' track:'{song}'")
                rate_limit()
                if response.status_code == 200:
                    data = response.json()
                    if data['data']:
                        for track in data['data']:
                            if fuzzy_match(track['album']['title'], album):
                                if 'preview' in track and track['preview']:
                                    logging.info(f"Found Deezer preview for '{artist}' - '{album}' (song: {song}): {track['preview']}")
                                    return track['preview']
            except Exception as e:
                logging.error(f"Error fetching Deezer preview for '{artist}' - '{album}' (song: {song}): {e}")

    # 3. Try to find previews for the album on Spotify
    try:
        for artist_name in artist_list:
            artist_name = artist_name.strip()
            params = {"q": f"album:{album} artist:{artist_name}", "type": "album"}
            response = requests.get(search_url, headers=headers, params=params)
            rate_limit()
            if response.status_code == 200:
                data = response.json()
                if data['albums']['items']:
                    for album_item in data['albums']['items']:
                        if fuzzy_match(album_item['name'], album):
                            album_id = album_item['id']
                            preview_url = get_spotify_album_preview(spotify_token, album_id)
                            if preview_url:
                                logging.info(f"Found Spotify album track preview for '{artist}' - '{album}': {preview_url}")
                                return preview_url
    except Exception as e:
        logging.error(f"Error fetching Spotify album preview for '{artist}' - '{album}': {e}")

    # 4. Try to find previews for specific songs on Spotify
    for song in possible_songs:
        try:
            for artist_name in artist_list:
                artist_name = artist_name.strip()
                params = {"q": f"track:{song} artist:{artist_name}", "type": "track"}
                response = requests.get(search_url, headers=headers, params=params)
                rate_limit()

                if response.status_code == 200:
                    data = response.json()
                    if data['tracks']['items']:
                        for track_item in data['tracks']['items']:
                            if fuzzy_match(track_item['album']['name'], album):
                                if 'preview_url' in track_item and track_item['preview_url']:
                                    logging.info(f"Found Spotify track preview for '{artist}' - '{album}' (song: {song}): {track_item['preview_url']}")
                                    return track_item['preview_url']
        except Exception as e:
            logging.error(f"Error fetching Spotify track preview for '{artist}' - '{album}' (song: {song}): {e}")

    logging.info(f"No preview found for '{artist}' - '{album}'")
    return None

def update_json_with_links(file_path):
    """Reads a JSON file, updates it with Spotify, Deezer, and preview links, and saves the updated JSON.

    This function reads a JSON file containing a list of albums, each with an artist and album name.
    It then uses the MusicBrainz, Discogs, Spotify, and Deezer APIs to find the album on each service
    and to find the tracks on the album. It uses the tracks to search for preview URLs on Spotify.
    Finally, it saves the updated JSON back to the same file.
    """
    with open(file_path, 'r') as file:
        data = json.load(file)

    spotify_token = authenticate_spotify()

    for album_data in data:
        artist = album_data['artist']
        album = album_data['album']

        possible_songs = search_musicbrainz_for_album(artist, album)
        possible_songs += get_discogs_album_tracks(artist, album)

        spotify_link, spotify_tracks = get_spotify_link(artist, album, possible_songs, spotify_token)
        album_data['spotify_link'] = spotify_link

        deezer_link, deezer_tracks = get_deezer_link(artist, album, possible_songs)
        album_data['deezer_link'] = deezer_link

        # Extend possible songs with tracks found on Spotify and Deezer
        possible_songs += spotify_tracks + deezer_tracks

        preview_url = get_preview_url(artist, album, possible_songs, spotify_token)
        album_data['preview_url'] = preview_url

    with open(file_path, 'w') as file:
        json.dump(data, file, indent=2)

    logging.info(f"Updated JSON saved to {file_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Update JSON with Spotify, Deezer, and preview links")
    parser.add_argument("file_path", help="Path to the JSON file")
    args = parser.parse_args()

    update_json_with_links(args.file_path)
