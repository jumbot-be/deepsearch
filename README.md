# Deep Search Scraper

Ce projet permet de récupérer les informations des pistes musicales de l'émission "[DEEP]Search" de Laurent Garnier sur Radio France, de générer une page HTML interactive pour les consulter, et d'importer ces pistes dans une playlist Deezer.

## Installation

1.  **Installer les dépendances Python :**

    ```bash
    pip install -r requirements.txt
    ```

2.  **Installer les navigateurs pour Playwright :**

    ```bash
    playwright install
    ```

## Utilisation

### 1. Scrapper les données

Le script `deepsearchscrapper.py` parcourt les épisodes de l'émission, extrait les pistes (Artiste, Titre) et les liens vers les plateformes (Spotify, Deezer, Apple Music).

```bash
python deepsearchscrapper.py
```

Cela générera deux fichiers :
- `scraped_data.csv` : Les données brutes au format CSV.
- `index.html` : Une page web interactive avec filtres et recherche.

### 2. Importer dans Deezer

Le script `deezer-import.py` permet de créer une playlist sur votre compte Deezer à partir du fichier `scraped_data.csv`.

**Note :** Vous devez éditer le fichier `deezer-import.py` pour y renseigner votre `ACCESS_TOKEN`.

```bash
python deezer-import.py
```

### 3. Générer un HTML de test

Si vous souhaitez tester le rendu de la page HTML sans lancer un scrap complet, vous pouvez utiliser :

```bash
python generate_test_html.py
```

## Structure du projet

- `deepsearchscrapper.py` : Script principal de scraping utilisant Playwright.
- `deezer-import.py` : Script d'importation vers l'API Deezer.
- `generate_test_html.py` : Script utilitaire pour générer un exemple d'interface.
- `scraped_data.csv` : Données extraites.
- `index.html` : Interface utilisateur finale.
- `requirements.txt` : Liste des dépendances Python.
