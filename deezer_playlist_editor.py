import os
import csv
import requests
import time
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

DEEZER_API_BASE = "https://api.deezer.com"

def get_access_token():
    return request.headers.get('Authorization')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    token = get_access_token()
    if not token:
        return jsonify({"error": "No access token"}), 401

    url = f"{DEEZER_API_BASE}/user/me/playlists"
    params = {"access_token": token}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if "data" in data:
            return jsonify(data["data"])
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/playlists', methods=['POST'])
def create_playlist():
    token = get_access_token()
    title = request.json.get('title')
    if not token or not title:
        return jsonify({"error": "Missing token or title"}), 400

    url = f"{DEEZER_API_BASE}/user/me/playlists"
    params = {
        "access_token": token,
        "title": title,
        "request_method": "POST"
    }
    try:
        response = requests.post(url, params=params)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/playlists/<int:playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    token = get_access_token()
    if not token:
        return jsonify({"error": "No access token"}), 401

    url = f"{DEEZER_API_BASE}/playlist/{playlist_id}"
    params = {
        "access_token": token,
        "request_method": "DELETE"
    }
    try:
        response = requests.post(url, params=params)
        return jsonify({"success": response.text == "true"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/playlists/<int:playlist_id>/tracks', methods=['GET'])
def get_playlist_tracks(playlist_id):
    token = get_access_token()
    if not token:
        return jsonify({"error": "No access token"}), 401

    url = f"{DEEZER_API_BASE}/playlist/{playlist_id}/tracks"
    params = {"access_token": token}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if "data" in data:
            return jsonify(data["data"])
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/playlists/<int:playlist_id>/tracks', methods=['POST'])
def add_tracks(playlist_id):
    token = get_access_token()
    track_ids = request.json.get('track_ids') # list of ids
    if not token or not track_ids:
        return jsonify({"error": "Missing token or track_ids"}), 400

    track_ids_str = ",".join(map(str, track_ids))
    url = f"{DEEZER_API_BASE}/playlist/{playlist_id}/tracks"
    params = {
        "access_token": token,
        "songs": track_ids_str,
        "request_method": "POST"
    }
    try:
        response = requests.post(url, params=params)
        return jsonify({"success": response.text == "true"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/playlists/<int:playlist_id>/tracks', methods=['DELETE'])
def remove_tracks(playlist_id):
    token = get_access_token()
    track_ids = request.json.get('track_ids') # list of ids
    if not token or not track_ids:
        return jsonify({"error": "Missing token or track_ids"}), 400

    track_ids_str = ",".join(map(str, track_ids))
    url = f"{DEEZER_API_BASE}/playlist/{playlist_id}/tracks"
    params = {
        "access_token": token,
        "songs": track_ids_str,
        "request_method": "DELETE"
    }
    try:
        response = requests.post(url, params=params)
        return jsonify({"success": response.text == "true"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/import-csv', methods=['POST'])
def import_csv():
    token = get_access_token()
    playlist_id = request.json.get('playlist_id')
    if not token or not playlist_id:
        return jsonify({"error": "Missing token or playlist_id"}), 400

    csv_file = 'scraped_data.csv'
    if not os.path.exists(csv_file):
        return jsonify({"error": "CSV file not found"}), 404

    tracks_to_import = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        seen = set()
        for row in reader:
            key = (row['artiste'].lower(), row['titre'].lower())
            if key not in seen:
                tracks_to_import.append({
                    'artiste': row['artiste'],
                    'titre': row['titre'],
                    'plateforme': row['plateforme'],
                    'lien': row['lien']
                })
                seen.add(key)

    deezer_ids = []
    for track in tracks_to_import:
        track_id = None
        # Try to extract ID from existing Deezer link
        if track['plateforme'] == 'Deezer' and 'deezer.com/track/' in track['lien']:
            try:
                track_id = track['lien'].split('/track/')[-1].split('?')[0]
            except:
                pass

        # Fallback to search
        if not track_id:
            query = f'artist:"{track["artiste"]}" track:"{track["titre"]}"'
            url = f"{DEEZER_API_BASE}/search?q={query}"
            try:
                resp = requests.get(url)
                data = resp.json()
                if data.get("data"):
                    track_id = data["data"][0]["id"]
            except:
                pass

        if track_id:
            deezer_ids.append(track_id)

        time.sleep(0.05) # Small delay to avoid rate limiting

    if not deezer_ids:
        return jsonify({"message": "No tracks found on Deezer"}), 200

    # Add in batches
    batch_size = 50
    success_count = 0
    for i in range(0, len(deezer_ids), batch_size):
        batch = deezer_ids[i:i+batch_size]
        track_ids_str = ",".join(map(str, batch))
        url = f"{DEEZER_API_BASE}/playlist/{playlist_id}/tracks"
        params = {
            "access_token": token,
            "songs": track_ids_str,
            "request_method": "POST"
        }
        try:
            response = requests.post(url, params=params)
            if response.text == "true":
                success_count += len(batch)
        except:
            pass

    return jsonify({"success": True, "count": success_count})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
