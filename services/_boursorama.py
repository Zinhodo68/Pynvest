"""Scraping Boursorama pour les OPCVM français."""
import re
from typing import Optional
import httpx
from bs4 import BeautifulSoup


BASE_URL = 'https://www.boursorama.com'
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}


def search_opcvm(query: str, limit: int = 10) -> list[dict]:
    """Recherche d'OPCVM sur Boursorama par nom ou ISIN.

    Retourne : [{'name', 'isin', 'url', 'currency'}, ...]
    """
    if not query or len(query) < 3:
        return []

    try:
        # API de recherche interne de Boursorama
        url = f'{BASE_URL}/recherche/_instruments/{query}'
        response = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'lxml')
        results = []

        # Sélectionne les lignes du tableau de résultats
        for row in soup.select('table.c-table tbody tr')[:limit]:
            cells = row.select('td')
            if len(cells) < 2:
                continue

            link = cells[0].select_one('a')
            if not link:
                continue

            name = link.get_text(strip=True)
            href = link.get('href', '')

            # Filtre : on ne garde que les OPCVM (URL contient /opcvm/)
            if '/opcvm/' not in href and '/sicav/' not in href:
                continue

            # Tente d'extraire l'ISIN depuis le tooltip ou le data attribute
            isin_match = re.search(r'\b([A-Z]{2}[A-Z0-9]{9}\d)\b',
                                     row.get_text(' ', strip=True))
            isin = isin_match.group(1) if isin_match else None

            results.append({
                'name': name,
                'isin': isin,
                'url': BASE_URL + href if href.startswith('/') else href,
                'currency': 'EUR',  # OPCVM FR généralement en EUR
                'symbol': isin or name[:20],  # On utilise l'ISIN comme symbole
                'type': 'Fonds',
                'exchange': 'Boursorama',
            })

        return results

    except Exception as e:
        print(f'Erreur recherche Boursorama: {e}')
        return []


def get_opcvm_price(url_or_isin: str) -> Optional[dict]:
    """Récupère le dernier cours d'un OPCVM Boursorama.

    Retourne : {'price', 'currency', 'date', 'name'}
    """
    try:
        # Si c'est un ISIN, on construit l'URL de recherche
        if re.match(r'^[A-Z]{2}[A-Z0-9]{9}\d$', url_or_isin):
            results = search_opcvm(url_or_isin, limit=1)
            if not results:
                return None
            url = results[0]['url']
        else:
            url = url_or_isin

        response = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'lxml')

        # Le cours est dans une balise spécifique de Boursorama
        price_elem = soup.select_one('.c-instrument--last')
        if not price_elem:
            price_elem = soup.select_one('[data-ist-last]')

        if not price_elem:
            return None

        price_text = price_elem.get_text(strip=True)
        # Nettoyage : "123,45 EUR" → 123.45
        price_clean = re.sub(r'[^\d,.\-]', '', price_text).replace(',', '.')

        try:
            price = float(price_clean)
        except ValueError:
            return None

        # Nom et devise
        name_elem = soup.select_one('h1.c-faceplate__company-title')
        name = name_elem.get_text(strip=True) if name_elem else ''

        return {
            'price': price,
            'currency': 'EUR',
            'name': name,
        }

    except Exception as e:
        print(f'Erreur récupération cours Boursorama: {e}')
        return None