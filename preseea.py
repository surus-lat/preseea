import argparse
import requests
from bs4 import BeautifulSoup
import re
import os
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

def download_file(url, session, base_url, save_dir):
    local_filename = os.path.basename(urlparse(url).path)
    full_url = urljoin(base_url, url)
    os.makedirs(save_dir, exist_ok=True)
    local_path = os.path.join(save_dir, local_filename)
    with session.get(full_url, stream=True) as r:
        r.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_path

def main():
    parser = argparse.ArgumentParser(description="Crawl PRESEEA corpus for txt/audio links.")
    parser.add_argument('--country', type=str, help='Country name to filter data')
    parser.add_argument('--concurrent', type=int, default=1, help='Number of concurrent downloads')
    args = parser.parse_args()

    base_url = 'https://preseea.uah.es/corpus/'
    url = base_url + 'busqueda.php'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': 'https://preseea.uah.es/corpus/consultas.php'
    }

    country = args.country if args.country else ".*"
    session = requests.Session()
    pagenum = 0
    total_downloaded = 0
    concurrent = args.concurrent

    while True:
        post_data = (
            f"patron=%3Ctext%3E%5B(word%3D'.*'%25c)%5D+%3A%3A+(match.text_pais+%3D+'{country}'%25c)^"
            f"&patron2=%3Ctext%3E%5B(word%3D'.*'%25c)%5D+%3A%3A+(match.text_pais+%3D+'{country}'%25c)"
        )
        page_url = f"{url}?pagenum={pagenum}"
        response = session.post(page_url, headers=headers, data=post_data)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        # Find all rows in the main table
        download_args = []
        for row in soup.find_all('tr'):
            # Find utterance name from <a title="Ampliar contexto">
            utter_a = row.find('a', title="Ampliar contexto")
            if not utter_a:
                continue
            utterance_name = utter_a.get_text(strip=True)
            tds = row.find_all('td')
            if len(tds) < 2:
                continue
            country_name = tds[-2].get_text(strip=True)
            # Find all <a> with .txt or .mp3 in href in this row
            for link in row.find_all('a', href=True):
                href = link['href']
                if re.search(r'\.(txt|mp3)$', href, re.IGNORECASE):
                    save_dir = os.path.join('preseea', country_name)
                    local_filename = os.path.basename(urlparse(href).path)
                    local_path = os.path.join(save_dir, local_filename)
                    if os.path.exists(local_path):
                        print(f"Already exists, skipping: {local_path}")
                        continue
                    print(f"Queueing: {href} -> {save_dir}")
                    download_args.append((href, session, base_url, save_dir))

        # Concurrent download
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            future_to_args = {
                executor.submit(download_file, *args): args for args in download_args
            }
            for future in as_completed(future_to_args):
                href, _, _, save_dir = future_to_args[future]
                try:
                    local_path = future.result()
                    print(f"Saved as: {local_path}")
                    total_downloaded += 1
                except Exception as e:
                    print(f"Failed to download {href}: {e}")

        # Check for pagination: look for "Siguientes"
        next_page = soup.find('a', href=re.compile(r"javascript:buscando\(\d+\)"), style="text-decoration:none;")
        if next_page and "Siguientes" in next_page.text:
            pagenum += 1
            print(f"Moving to page {pagenum}...")
        else:
            break

    print(f"Total files downloaded: {total_downloaded}")

if __name__ == "__main__":
    main()
