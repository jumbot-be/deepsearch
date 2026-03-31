import asyncio
import csv
import os
import re
import html
import urllib.parse
from playwright.async_api import async_playwright

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
    episode_urls = set()
    for link in links:
        href = await link.get_attribute("href")
        if href and "/fip/podcasts/deep-search-par-laurent-garnier/" in href:
            full_url = f"https://www.radiofrance.fr{href}" if href.startswith("/") else href
            if full_url.rstrip('/') != "https://www.radiofrance.fr/fip/podcasts/deep-search-par-laurent-garnier":
                episode_urls.add(full_url)

    print(f"Found {len(episode_urls)} episode links.")
    return sorted(list(episode_urls))

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

                    if spotify and spotify.group(1) != "void 0":
                        tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "plateforme": "Spotify", "lien": spotify.group(1)})
                        added_any = True
                    if deezer and deezer.group(1) != "void 0":
                        tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "plateforme": "Deezer", "lien": deezer.group(1)})
                        added_any = True
                    if apple and apple.group(1) != "void 0":
                        tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "plateforme": "Apple Music", "lien": apple.group(1)})
                        added_any = True

                    if not added_any:
                        tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "plateforme": "N/A", "lien": ""})

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

            added_any = False
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
                    tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "plateforme": platform, "lien": href})
                    added_any = True

            if not added_any:
                tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "plateforme": "N/A", "lien": ""})

    return tracks_data

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        episode_urls = await get_episode_links(page)

        all_tracks = []
        for i, url in enumerate(episode_urls):
            print(f"[{i+1}/{len(episode_urls)}] ", end="")
            tracks = await scrape_episode(page, url)
            all_tracks.extend(tracks)

        # Save to CSV
        csv_file = 'scraped_data.csv'
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['épisode', 'artiste', 'titre', 'plateforme', 'lien'])
            writer.writeheader()
            writer.writerows(all_tracks)

        # Save to HTML
        html_file = 'index.html'

        table_rows = ""
        for track in all_tracks:
            if track['lien']:
                link_html = f"<a href='{html.escape(track['lien'])}' class='btn' target='_blank'>Écouter</a>"
            else:
                yt_query = urllib.parse.quote(f"{track['artiste']} {track['titre']} youtube")
                sc_query = urllib.parse.quote(f"{track['artiste']} {track['titre']} soundcloud")
                bc_query = urllib.parse.quote(f"{track['artiste']} {track['titre']} bandcamp")

                link_html = f"""<div class="search-container">
                    <a href="https://www.google.com/search?q={yt_query}" class="btn btn-search" target="_blank">YouTube</a>
                    <a href="https://www.google.com/search?q={sc_query}" class="btn btn-search" target="_blank">SoundCloud</a>
                    <a href="https://www.google.com/search?q={bc_query}" class="btn btn-search" target="_blank">Bandcamp</a>
                </div>"""

            table_rows += f"<tr data-platform='{html.escape(track['plateforme'])}'><td>{html.escape(track['épisode'])}</td><td>{html.escape(track['artiste'])}</td><td>{html.escape(track['titre'])}</td><td>{html.escape(track['plateforme'])}</td><td>{link_html}</td></tr>\n"

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
            const selectedPlatform = document.getElementById('platformFilter').value;
            const hideDuplicates = document.getElementById('hideDuplicates').checked;
            const tbody = document.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const seen = new Set();
            let visibleCount = 0;

            rows.forEach(row => {{
                const platform = row.getAttribute('data-platform');
                const artist = row.cells[1].innerText.trim().toLowerCase();
                const title = row.cells[2].innerText.trim().toLowerCase();
                const key = artist + '|' + title;

                let show = (selectedPlatform === 'all' || platform === selectedPlatform);

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
                const aText = a.cells[columnIndex].innerText.trim();
                const bText = b.cells[columnIndex].innerText.trim();

                return direction === 'asc'
                    ? aText.localeCompare(bText, 'fr', {{ sensitivity: 'base' }})
                    : bText.localeCompare(aText, 'fr', {{ sensitivity: 'base' }});
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
                        if (index === 4) {{ // Link column
                            const a = cell.querySelector('a');
                            text = a ? a.href : '';
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
        <label for='platformFilter'>Filtrer par plateforme :</label>
        <select id='platformFilter' onchange='updateTable()'>
            <option value='all'>Toutes les plateformes</option>
            <option value='Spotify'>Spotify</option>
            <option value='Deezer'>Deezer</option>
            <option value='Apple Music'>Apple Music</option>
            <option value='YouTube'>YouTube</option>
            <option value='N/A'>N/A</option>
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
