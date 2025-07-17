import argparse
import requests
from bs4 import BeautifulSoup
import re
import os
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import csv

def is_corrupted_mp3(filepath):
    if not filepath.lower().endswith('.mp3'):
        return False
    try:
        from mutagen.mp3 import MP3
        MP3(filepath)
        return False
    except Exception:
        return True

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

    audio_text_pairs = []  # List of tuples: (mp3_path, txt_path)
    all_mp3_txt_links = [] # List of tuples: (mp3_href, txt_href, save_dir)

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
            save_dir = os.path.join('preseea', country_name)
            # Construct URLs using utterance_name
            mp3_href = f"mp3/{utterance_name}.mp3"
            txt_href = f"txt/{utterance_name}.txt"
            mp3_filename = f"{utterance_name}.mp3"
            txt_filename = f"{utterance_name}.txt"
            mp3_path = os.path.join(save_dir, mp3_filename)
            txt_path = os.path.join(save_dir, txt_filename)
            audio_text_pairs.append((mp3_path, txt_path))
            all_mp3_txt_links.append((mp3_href, txt_href, save_dir))
            # Download logic for mp3
            file_exists = os.path.exists(mp3_path)
            corrupted = False
            if file_exists:
                corrupted = is_corrupted_mp3(mp3_path)
            if file_exists and not corrupted:
                print(f"Already exists, skipping: {mp3_path}")
            else:
                if corrupted:
                    print(f"Corrupted file detected, will redownload: {mp3_path}")
                else:
                    print(f"Queueing: {mp3_href} -> {save_dir}")
                download_args.append((mp3_href, session, base_url, save_dir))
            # Download logic for txt
            if not os.path.exists(txt_path):
                print(f"Queueing: {txt_href} -> {save_dir}")
                download_args.append((txt_href, session, base_url, save_dir))

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

    # --- Retry missing pairs before metadata creation ---
    retry_download_args = []
    for (mp3_path, txt_path), (mp3_href, txt_href, save_dir) in zip(audio_text_pairs, all_mp3_txt_links):
        if not os.path.exists(mp3_path):
            retry_download_args.append((mp3_href, session, base_url, save_dir))
        if not os.path.exists(txt_path):
            retry_download_args.append((txt_href, session, base_url, save_dir))
    if retry_download_args:
        print(f"Retrying {len(retry_download_args)} missing files...")
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            future_to_args = {
                executor.submit(download_file, *args): args for args in retry_download_args
            }
            for future in as_completed(future_to_args):
                href, _, _, save_dir = future_to_args[future]
                try:
                    local_path = future.result()
                    print(f"Retried and saved: {local_path}")
                except Exception as e:
                    print(f"Failed to redownload {href}: {e}")

    # --- Prepare HuggingFace-style dataset folder ---
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    metadata_path = "metadata.csv"
    rows = []
    for mp3_path, txt_path in audio_text_pairs:
        if not (os.path.exists(mp3_path) and os.path.exists(txt_path)):
            continue
        # Copy mp3 to data/ (preserve filename)
        mp3_filename = os.path.basename(mp3_path)
        dest_mp3 = os.path.join(data_dir, mp3_filename)
        if not os.path.exists(dest_mp3):
            shutil.copy2(mp3_path, dest_mp3)
        # Read transcription with encoding fallback
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                transcription = f.read().strip().replace('\n', ' ')
        except UnicodeDecodeError:
            with open(txt_path, "r", encoding="latin-1") as f:
                transcription = f.read().strip().replace('\n', ' ')
        rows.append({
            "file_name": f"data/{mp3_filename}",
            "transcription": transcription
        })
    # Write metadata.csv
    with open(metadata_path, "w", encoding="utf-8", newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["file_name", "transcription"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"metadata.csv written with {len(rows)} entries.")

if __name__ == "__main__":
    main()