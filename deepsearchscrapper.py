import asyncio
import csv
import os
import re
import html
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
                        tracks_data.append({"épisode": episode_title, "artiste": artist, "titre": title, "plateforme": "Deezer", "lien": deezer.group(1)})                        added_any = True
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
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write("<!DOCTYPE html>\n<html lang='fr'>\n<head>\n<meta charset='UTF-8'>\n")
            f.write("<meta name='viewport' content='width=device-width, initial-scale=1.0'>\n")
            f.write("<title>Laurent Garnier - [DEEP]Search Scraped Data</title>\n")
            f.write("<style>\n")
            f.write("body { font-family: system-ui, -apple-system, sans-serif; margin: 20px; background: #f4f4f9; color: #333; }\n")
            f.write("h1 { color: #e2007a; border-bottom: 2px solid #e2007a; padding-bottom: 10px; }\n")
            f.write(".controls { margin-bottom: 20px; display: flex; align-items: center; gap: 10px; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }\n")
            f.write("select { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 1em; }\n")
            f.write("table { border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-top: 20px; }\n")
            f.write("th, td { border: 1px solid #eee; padding: 12px; text-align: left; }\n")
            f.write("th { background-color: #e2007a; color: white; text-transform: uppercase; font-size: 0.85em; letter-spacing: 0.05em; }\n")
            f.write("tr:nth-child(even) { background-color: #fcfcfc; }\n")
            f.write("tr:hover { background-color: #fff0f7; }\n")
            f.write(".btn { display: inline-block; padding: 6px 16px; background: #e2007a; color: white; border-radius: 20px; text-decoration: none; font-size: 0.85em; font-weight: 600; transition: background 0.2s; cursor: pointer; border: none; }\n")
            f.write(".btn:hover { background: #c10068; }\n")
            f.write("</style>\n")
            f.write("<script>\n")
            f.write("function updateTable() {\n")
            f.write("  const selectedPlatform = document.getElementById('platformFilter').value;\n")
            f.write("  const hideDuplicates = document.getElementById('hideDuplicates').checked;\n")
            f.write("  const rows = document.querySelectorAll('tbody tr');\n")
            f.write("  const seen = new Set();\n")
            f.write("  let visibleCount = 0;\n")
            f.write("\\n")
            f.write("  rows.forEach(row => {\n")
            f.write("    const platform = row.getAttribute('data-platform');\n")
            f.write("    const artist = row.cells[1].innerText.trim().toLowerCase();\n")
            f.write("    const title = row.cells[2].innerText.trim().toLowerCase();\n")
            f.write("    const key = artist + '|' + title;\n")
            f.write("\\n")
            f.write("    let show = (selectedPlatform === 'all' || platform === selectedPlatform);\n")
            f.write("\\n")
            f.write("    if (show && hideDuplicates) {\n")
            f.write("      if (seen.has(key)) {\n")
            f.write("        show = false;\n")
            f.write("      } else {\n")
            f.write("        seen.add(key);\n")
            f.write("      }\n")
            f.write("    }\n")
            f.write("\\n")
            f.write("    if (show) {\n")
            f.write("      row.style.display = '';\n")
            f.write("      visibleCount++;\n")
            f.write("    } else {\n")
            f.write("      row.style.display = 'none';\n")
            f.write("    }\n")
            f.write("  });\n")
            f.write("  document.getElementById('totalCount').innerText = visibleCount;\n")
            f.write("}\n")
            f.write("\\n")
            f.write("function exportToCSV() {\n")
            f.write("  const rows = document.querySelectorAll('table tr');\n")
            f.write("  let csv = [];\n")
            f.write("  rows.forEach(row => {\n")
            f.write("    if (row.style.display !== 'none') {\n")
            f.write("      const cols = Array.from(row.cells).map((cell, index) => {\n")
            f.write("        let text = cell.innerText;\n")
            f.write("        if (index === 4) { // Link column\n")
            f.write("          const a = cell.querySelector('a');\n")
            f.write("          text = a ? a.href : '';\n")
            f.write("        }\n")
            f.write("        return '\"' + text.replace(/\"/g, '\"\"') + '\"';\n")
            f.write("      });\n")
            f.write("      csv.push(cols.join(','));\n")
            f.write("    }\n")
            f.write("  });\n")
            f.write("  const csvString = csv.join('\\\\n');\n")
            f.write("  const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });\n")
            f.write("  const link = document.createElement('a');\n")
            f.write("  link.href = URL.createObjectURL(blob);\n")
            f.write("  link.download = 'tracks_export.csv';\n")
            f.write("  link.click();\n")
            f.write("}\n")
            f.write("</script>\n")
            f.write("</head>\n<body>\n")
            f.write("<h1>Laurent Garnier - [DEEP]Search</h1>\n")
            f.write("<div class='controls'>\n")
            f.write("  <label for='platformFilter'>Filtrer par plateforme :</label>\n")
            f.write("  <select id='platformFilter' onchange='updateTable()'>\n")
            f.write("    <option value='all'>Toutes les plateformes</option>\n")
            f.write("    <option value='Spotify'>Spotify</option>\n")
            f.write("    <option value='Deezer'>Deezer</option>\n")
            f.write("    <option value='Apple Music'>Apple Music</option>\n")
            f.write("    <option value='YouTube'>YouTube</option>\n")
            f.write("    <option value='N/A'>N/A</option>\n")
            f.write("  </select>\n")
            f.write("  <label><input type='checkbox' id='hideDuplicates' onchange='updateTable()'> Masquer les doublons (Artiste/Titre)</label>\n")
            f.write("  <button onclick='exportToCSV()' class='btn'>Exporter en CSV</button>\n")
            f.write(f"  <span>&nbsp;&nbsp;<strong>Total :</strong> <span id='totalCount'>{len(all_tracks)}</span> pistes</span>\n")
            f.write("</div>\n")
            f.write("<table>\n<thead>\n<tr><th>Épisode</th><th>Artiste</th><th>Titre</th><th>Plateforme</th><th>Lien</th></tr>\n</thead>\n<tbody>\n")
            for track in all_tracks:
                link_html = f"<a href='{html.escape(track['lien'])}' class='btn' target='_blank'>Écouter</a>" if track['lien'] else ""
                f.write(f"<tr data-platform='{html.escape(track['plateforme'])}'><td>{html.escape(track['épisode'])}</td><td>{html.escape(track['artiste'])}</td><td>{html.escape(track['titre'])}</td><td>{html.escape(track['plateforme'])}</td><td>{link_html}</td></tr>\\n")
            f.write("</tbody>\n</table>\n</body>\n</html>")

        print(f"\\nSuccess! {len(all_tracks)} tracks saved to {csv_file} and {html_file}.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
