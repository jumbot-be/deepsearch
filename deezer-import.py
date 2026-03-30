import requests
import time
import sys
import os

# --- CONFIGURATION ---
# You need to create an app on https://developers.deezer.com/myapps
# to get your APP_ID and APP_SECRET.
# Then you need to get an ACCESS_TOKEN with 'manage_library' permission.
APP_ID = "YOUR_APP_ID"
ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
PLAYLIST_NAME = "Laurent Garnier - [DEEP]Search"

def search_track(artist, title):
    """Search for a track on Deezer and return its ID."""
    query = f'artist:\"{artist}\" track:\"{title}\"'
    url = f"https://api.deezer.com/search?q={query}"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get("data"):
            return data["data"][0]["id"]
    except Exception as e:
        print(f"Error searching for {artist} - {title}: {e}")
    return None

def create_playlist(name):
    """Create a new playlist and return its ID."""
    url = f"https://api.deezer.com/user/me/playlists"
    params = {
        "access_token": ACCESS_TOKEN,
        "title": name,
        "request_method": "POST"
    }
    try:
        response = requests.post(url, params=params)
        data = response.json()
        if \"id\" in data:
            print(f"Created playlist '{name}' with ID: {data['id']}")
            return data[\"id\"]
        else:
            print(f"Failed to create playlist: {data}")
    except Exception as e:
        print(f"Error creating playlist: {e}")
    return None

def add_tracks_to_playlist(playlist_id, track_ids):
    """Add a list of track IDs to the playlist."""
    track_ids_str = \",\".join(map(str, track_ids))
    url = f"https://api.deezer.com/playlist/{playlist_id}/tracks"
    params = {
        "access_token": ACCESS_TOKEN,
        "songs": track_ids_str,
        "request_method": \"POST\"
    }
    try:
        response = requests.post(url, params=params)
        if response.text == \"true\":
            return True
        else:
            print(f"Failed to add tracks: {response.json()}")
    except Exception as e:
        print(f"Error adding tracks: {e}")
    return False

def main():
    if ACCESS_TOKEN == \"YOUR_ACCESS_TOKEN\":
        print(\"Please set your Deezer ACCESS_TOKEN in the script.\")
        return

    csv_file = 'scraped_data.csv'
    if not os.path.exists(csv_file):
        print(f"File {csv_file} not found. Run the scraper first.")
        return

    tracks_to_import = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        seen = set()
        for row in reader:
            key = (row['artiste'].lower(), row['titre'].lower())
            if key not in seen:
                tracks_to_import.append({'artiste': row['artiste'], 'titre': row['titre']})
                seen.add(key)

    print(f"Found {len(tracks_to_import)} unique tracks in CSV.")

    deezer_ids = []
    for i, track in enumerate(tracks_to_import):
        print(f"[{i+1}/{len(tracks_to_import)}] Searching: {track['artiste']} - {track['titre']}... \", end=\"\")
        track_id = search_track(track['artiste'], track['titre'])
        if track_id:
            print(f\"Found (ID: {track_id})\")
            deezer_ids.append(track_id)
        else:
            print(\"Not found\")
        time.sleep(0.1)

    if not deezer_ids:
        print(\"No tracks found on Deezer.\")
        return

    playlist_id = create_playlist(PLAYLIST_NAME)
    if playlist_id:
        print(f\"Adding {len(deezer_ids)} tracks to playlist...\")
        batch_size = 50
        success_count = 0
        for i in range(0, len(deezer_ids), batch_size):
            batch = deezer_ids[i:i+batch_size]
            if add_tracks_to_playlist(playlist_id, batch):
                success_count += len(batch)

        print(f\"Successfully imported {success_count} tracks to Deezer!\")

if __name__ == \"__main__\":
    main()
