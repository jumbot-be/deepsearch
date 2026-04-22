import asyncio
import csv
import os
import re
import html
import urllib.parse
import argparse
from collections import OrderedDict
from playwright.async_api import async_playwright

def get_episode_sort_key(title):
    """Generates a sortable key for an episode title based on date."""
    months = {
        'jan': '01', 'janv': '01',
        'fév': '02', 'fev': '02',
        'mar': '03',
        'avr': '04',
        'mai': '05',
        'juin': '06',
        'juil': '07',
        'aoû': '08', 'aou': '08',
        'sep': '09', 'sept': '09',
        'oct': '10',
        'nov': '11',
        'dec': '12', 'déc': '12'
    }

    # Try to find year (4 digits) and month abbreviation
    year_match = re.search(r'20\d{2}', title)
    year = year_match.group(0) if year_match else "9999" # Default high for unknowns

    month_val = "00"
    title_lower = title.lower()
    for m, val in months.items():
        if m in title_lower:
            month_val = val
            break

    # Handle "Hors Série" or special cases
    if "hors série" in title_lower:
        # Extract years from range like 66/76's or 2007/2016's
        range_match = re.search(r'(\d+)/(\d+)', title)
        if range_match:
            # We use the start of the range as part of the sort key
            return f"0000-{range_match.group(1).zfill(4)}"
        return "0000-0000"

    return f"{year}-{month_val}"

async def accept_cookies(page):
    """Accepts cookies if the button is found."""
    try:
        cookie_button = await page.wait_for_selector("#didomi-notice-agree-button", timeout=5000)
        if cookie_button:
            await cookie_button.click()
            print("Cookies accepted.")
            await page.wait_for_timeout(1000)
    except Exception:
        pass

async def get_episode_links(page):
    """Extracts all episode URLs from the main podcast page."""
    print("Extracting episode links from main page...")
    await page.goto("https://www.radiofrance.fr/fip/podcasts/deep-search-par-laurent-garnier")
    await accept_cookies(page)

    # Scroll to the bottom to load all episodes
    last_height = await page.evaluate("document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            # Try one more time to be sure
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
        last_height = new_height

    links = await page.query_selector_all("a")
    episode_urls = []
    seen_urls = set()
    for link in links:
        href = await link.get_attribute("href")
        if href and "/fip/podcasts/deep-search-par-laurent-garnier/" in href:
            full_url = f"https://www.radiofrance.fr{href}" if href.startswith("/") else href
            full_url = full_url.rstrip('/')
            if full_url != "https://www.radiofrance.fr/fip/podcasts/deep-search-par-laurent-garnier":
                if full_url not in seen_urls:
                    episode_urls.append(full_url)
                    seen_urls.add(full_url)

    print(f"Found {len(episode_urls)} episode links.")
    return episode_urls # Return in DOM order (newest first)

async def scrape_episode(page, url):
    """Scrapes track data from a single episode page."""
    print(f"Scraping episode: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
    except Exception as e:
        print(f"Error loading {url}: {e}")
        return []

    # Extract episode title
    episode_title = "Inconnu"
    try:
        h1 = await page.query_selector("h1")
        if h1:
            episode_title = (await h1.inner_text()).strip()
    except:
        pass

    tracks_data = []
    content = await page.content()

    # Attempt 1: Extract from Svelte state (most comprehensive)
    try:
        tracklist_match = re.search(r'trackList:(\[.*?\]),seo:', content, re.DOTALL)
        if tracklist_match:
            data_str = tracklist_match.group(1)
            song_blocks = re.split(r'\{__typename:"Song"', data_str)[1:]
            for block in song_blocks:
                title_match = re.search(r'text:"(.*?)"', block)
                artist_match = re.search(r'title:"(.*?)"', block)
                if title_match and artist_match:
                    title = html.unescape(title_match.group(1))
                    artist = html.unescape(artist_match.group(1))

                    added_any = False
                    spotify = re.search(r'spotifyLink:"(.*?)"', block)
                    deezer = re.search(r'deezerLink:"(.*?)"', block)
                    apple = re.search(r'itunesLink:"(.*?)"', block)

                    links = {}
                    if spotify and spotify.group(1) != "void 0":
                        links["Spotify"] = spotify.group(1)
                    if deezer and deezer.group(1) != "void 0":
                        links["Deezer"] = deezer.group(1)
                    if apple and apple.group(1) != "void 0":
                        links["Apple Music"] = apple.group(1)

                    tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "liens": links})

            if tracks_data:
                print(f"  -> Extracted {len(tracks_data)} track-platform entries from Svelte state.")
                return tracks_data
    except Exception as e:
        print(f"  -> Svelte extraction failed: {e}")

    # Attempt 2: DOM scraping (fallback)
    print("  -> Falling back to DOM scraping...")
    cards = await page.query_selector_all(".CardSide")
    for card in cards:
        artist_elem = await card.query_selector(".title")
        title_elem = await card.query_selector(".subtext")

        if artist_elem and title_elem:
            artist = (await artist_elem.inner_text()).strip()
            title = (await title_elem.inner_text()).strip()
            if "[DEEP]Search" in artist: continue

            track_links = {}
            links = await card.query_selector_all("a")
            for link in links:
                href = await link.get_attribute("href")
                if not href: continue
                platform = None
                if "spotify.com" in href: platform = "Spotify"
                elif "deezer.com" in href: platform = "Deezer"
                elif "music.apple.com" in href: platform = "Apple Music"
                elif "youtube.com" in href: platform = "YouTube"

                if platform:
                    track_links[platform] = href

            tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "liens": track_links})

    return tracks_data

async def main():
    parser = argparse.ArgumentParser(description="Scraper pour le podcast Deep Search de Laurent Garnier.")
    parser.add_argument("--last", action="store_true", help="Scraper uniquement le dernier épisode publié.")
    parser.add_argument("--url", type=str, help="Scraper un épisode spécifique via son URL.")
    args = parser.parse_args()

    csv_file = 'scraped_data.csv'
    all_tracks = []

    # Load existing data if appending
    if (args.last or args.url) and os.path.exists(csv_file):
        print(f"Loading existing data from {csv_file}...")
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if 'liens' not in reader.fieldnames:
                print("Warning: CSV format is outdated (missing 'liens'). Re-scraping all data.")
            else:
                for row in reader:
                    # Convert liens string back to dict
                    liens = {}
                    if row['liens']:
                        for part in row['liens'].split("; "):
                            if ": " in part:
                                p, u = part.split(": ", 1)
                                liens[p] = u
                    all_tracks.append({
                        "épisode": row['épisode'],
                        "artiste": row['artiste'],
                        "titre": row['titre'],
                        "liens": liens
                    })
                print(f"Loaded {len(all_tracks)} existing tracks.")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        if args.url:
            episode_urls = [args.url]
        else:
            episode_urls = await get_episode_links(page)
            if args.last:
                episode_urls = episode_urls[:1] # links are sorted by URL, we need to be careful

        new_tracks = []
        for i, url in enumerate(episode_urls):
            print(f"[{i+1}/{len(episode_urls)}] ", end="")
            tracks = await scrape_episode(page, url)
            new_tracks.extend(tracks)

        all_tracks.extend(new_tracks)

        # Save to CSV
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['épisode', 'artiste', 'titre', 'liens'])
            writer.writeheader()
            # Convert liens dict to string for CSV
            csv_tracks = []
            for t in all_tracks:
                row = {
                    "épisode": t['épisode'],
                    "artiste": t['artiste'],
                    "titre": t['titre'],
                    "liens": "; ".join([f"{p}: {u}" for p, u in t['liens'].items()])
                }
                csv_tracks.append(row)
            writer.writerows(csv_tracks)

        # Save to HTML
        html_file = 'index.html'

        # Collect unique episodes for the filter dropdown
        episodes = sorted(list({t['épisode'] for t in all_tracks}), key=get_episode_sort_key, reverse=True)
        episode_options = "\n".join([f"<option value='{html.escape(e)}'>{html.escape(e)}</option>" for e in episodes])

        table_rows = ""
        for track in all_tracks:
            platforms = list(track['liens'].keys())
            platform_str = " ".join(platforms) if platforms else "N/A"
            episode_sort = get_episode_sort_key(track['épisode'])

            link_html = '<div class="search-container">'
            # Official buttons
            for platform, url in track['liens'].items():
                link_html += f"<a href='{html.escape(url)}' class='btn' target='_blank'>{html.escape(platform)}</a>"

            # Search buttons (always present)
            yt_query = urllib.parse.quote(f"{track['artiste']} {track['titre']} youtube")
            sc_query = urllib.parse.quote(f"{track['artiste']} {track['titre']} soundcloud")
            bc_query = urllib.parse.quote(f"{track['artiste']} {track['titre']} bandcamp")

            link_html += f"""
                <a href="https://www.google.com/search?q={yt_query}" class="btn btn-search" target="_blank">YouTube 🔍</a>
                <a href="https://www.google.com/search?q={sc_query}" class="btn btn-search" target="_blank">SoundCloud 🔍</a>
                <a href="https://www.google.com/search?q={bc_query}" class="btn btn-search" target="_blank">Bandcamp 🔍</a>
            </div>"""

            table_rows += f"<tr data-platforms='{html.escape(platform_str)}'><td data-sort='{html.escape(episode_sort)}'>{html.escape(track['épisode'])}</td><td>{html.escape(track['artiste'])}</td><td>{html.escape(track['titre'])}</td><td>{html.escape(', '.join(platforms) or 'N/A')}</td><td>{link_html}</td></tr>\n"

        html_content = f"""<!DOCTYPE html>
<html lang='fr'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>Laurent Garnier - [DEEP]Search Scraped Data</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; margin: 20px; background: #f4f4f9; color: #333; }}
        h1 {{ color: #e2007a; border-bottom: 2px solid #e2007a; padding-bottom: 10px; }}
        .controls {{ margin-bottom: 20px; display: flex; align-items: center; gap: 10px; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); flex-wrap: wrap; }}
        select {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 1em; }}
        table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-top: 20px; }}
        th, td {{ border: 1px solid #eee; padding: 12px; text-align: left; }}
        th {{ background-color: #e2007a; color: white; text-transform: uppercase; font-size: 0.85em; letter-spacing: 0.05em; }}
        tr:nth-child(even) {{ background-color: #fcfcfc; }}
        tr:hover {{ background-color: #fff0f7; }}
        .btn {{ display: inline-block; padding: 6px 16px; background: #e2007a; color: white; border-radius: 20px; text-decoration: none; font-size: 0.85em; font-weight: 600; transition: background 0.2s; cursor: pointer; border: none; white-space: nowrap; }}
        .btn:hover {{ background: #c10068; }}
        .btn-search {{ background: #555; font-size: 0.75em; padding: 4px 10px; margin-right: 4px; }}
        .btn-search:hover {{ background: #333; }}
        .search-container {{ display: flex; flex-wrap: wrap; gap: 4px; }}
        .sort-btn {{ cursor: pointer; user-select: none; margin-left: 5px; opacity: 0.6; transition: opacity 0.2s; }}
        .sort-btn:hover {{ opacity: 1; color: #fff; }}
        .sort-btn.active {{ opacity: 1; font-weight: bold; }}
        th {{ position: relative; }}
    </style>
    <script>
        function updateTable() {{
            const selectedEpisode = document.getElementById('episodeFilter').value;
            const hideDuplicates = document.getElementById('hideDuplicates').checked;
            const tbody = document.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const seen = new Set();
            let visibleCount = 0;

            rows.forEach(row => {{
                const episode = row.cells[0].innerText.trim();
                const artist = row.cells[1].innerText.trim().toLowerCase();
                const title = row.cells[2].innerText.trim().toLowerCase();
                const key = artist + '|' + title;

                let show = (selectedEpisode === 'all' || episode === selectedEpisode);

                if (show && hideDuplicates) {{
                    if (seen.has(key)) {{
                        show = false;
                    }} else {{
                        seen.add(key);
                    }}
                }}

                if (show) {{
                    row.style.display = '';
                    visibleCount++;
                }} else {{
                    row.style.display = 'none';
                }}
            }});
            document.getElementById('totalCount').innerText = visibleCount;
        }}

        function sortTable(columnIndex, direction) {{
            const tbody = document.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));

            // Update active states of sort buttons
            document.querySelectorAll('.sort-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');

            const sortedRows = rows.sort((a, b) => {{
                const aCell = a.cells[columnIndex];
                const bCell = b.cells[columnIndex];

                const aValue = aCell.getAttribute('data-sort') || aCell.innerText.trim();
                const bValue = bCell.getAttribute('data-sort') || bCell.innerText.trim();

                return direction === 'asc'
                    ? aValue.localeCompare(bValue, 'fr', {{ sensitivity: 'base' }})
                    : bValue.localeCompare(aValue, 'fr', {{ sensitivity: 'base' }});
            }});

            // Re-append sorted rows
            sortedRows.forEach(row => tbody.appendChild(row));

            // Re-apply filters and duplicate hiding after sorting
            updateTable();
        }}

        function exportToCSV() {{
            const rows = document.querySelectorAll('table tr');
            let csv = [];
            rows.forEach(row => {{
                if (row.style.display !== 'none') {{
                    const cols = Array.from(row.cells).map((cell, index) => {{
                        let text = cell.innerText;
                        if (index === 4) {{ // Link column (Platforms & Searches)
                            const links = Array.from(cell.querySelectorAll('a')).map(a => a.innerText + ": " + a.href);
                            text = links.join("; ");
                        }}
                        return '"' + text.replace(/"/g, '""') + '"';
                    }});
                    csv.push(cols.join(','));
                }}
            }});
            const csvString = csv.join('\\n');
            const blob = new Blob([csvString], {{ type: 'text/csv;charset=utf-8;' }});
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'tracks_export.csv';
            link.click();
        }}
    </script>
</head>
<body>
    <h1>Laurent Garnier - [DEEP]Search</h1>
    <div class='controls'>
        <label for='episodeFilter'>Filtrer par épisode :</label>
        <select id='episodeFilter' onchange='updateTable()'>
            <option value='all'>Tous les épisodes</option>
            {episode_options}
        </select>
        <label><input type='checkbox' id='hideDuplicates' onchange='updateTable()'> Masquer les doublons (Artiste/Titre)</label>
        <button onclick='exportToCSV()' class='btn'>Exporter en CSV</button>
        <span>&nbsp;&nbsp;<strong>Total :</strong> <span id='totalCount'>{len(all_tracks)}</span> pistes</span>
    </div>
    <table>
        <thead>
            <tr>
                <th>
                    Épisode
                    <span class="sort-btn" onclick="sortTable(0, 'asc')">▲</span>
                    <span class="sort-btn" onclick="sortTable(0, 'desc')">▼</span>
                </th>
                <th>
                    Artiste
                    <span class="sort-btn" onclick="sortTable(1, 'asc')">▲</span>
                    <span class="sort-btn" onclick="sortTable(1, 'desc')">▼</span>
                </th>
                <th>
                    Titre
                    <span class="sort-btn" onclick="sortTable(2, 'asc')">▲</span>
                    <span class="sort-btn" onclick="sortTable(2, 'desc')">▼</span>
                </th>
                <th>Plateforme</th>
                <th>Lien</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
</body>
</html>"""

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"\nSuccess! {len(all_tracks)} tracks saved to {csv_file} and {html_file}.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
