# Review Extraction

MVP pour extraire automatiquement des paramètres méthodologiques d'articles PDF dans une revue systématique, avec validation par un second agent indépendant.

Le pipeline produit:

- un screening full paper inclusion/exclusion avant extraction;
- un JSON de screening par article;
- un fichier Excel `summary.xlsx` avec feuilles `Summary`, `Screening`, `Extraction` et `Review required`;
- un JSON structuré par article et par question;
- un CSV synthèse pour la revue;
- une confiance finale;
- les preuves textuelles utilisées;
- un indicateur `review_required`;
- un PDF surligné lorsque les citations peuvent être retrouvées dans le document.

La phase amont applique la grille:

- population: inclure les populations humaines saines ou non saines; exclure les études animales;
- outcome: inclure cinématique/posture de l'épaule; exclure le membre supérieur sans épaule;
- study design: inclure recherche prospective primaire; exclure revues, analyses secondaires/rétrospectives et proceedings;
- langue: inclure les articles en anglais.

L'extraction détaillée est lancée seulement si le screening final est `include` sans révision humaine requise. Les articles exclus ou incertains gardent un `*.screening.json`, une ligne dans `summary.csv`, et un PDF surligné des preuves de screening si le surlignage est activé.

## Installation

```powershell
conda env create -f environment.yml
conda activate review-extraction
copy .env.example .env
```

Ajoutez votre clé dans `.env`:

```text
OPENAI_API_KEY=sk-...
```

## Usage CLI

```powershell
review-extract .\pdfs --out .\outputs
```

Ou pour un seul PDF:

```powershell
review-extract .\paper.pdf --out .\outputs
```

Options utiles:

```powershell
review-extract .\pdfs --out .\outputs --no-highlight
review-extract .\pdfs --out .\outputs --model gpt-5.5 --validator-model gpt-5.5
```

## Reprise sans relancer l'IA

Par defaut, la CLI reutilise les fichiers deja presents dans `outputs`:

- si `article.json` existe, aucun appel OpenAI n'est refait pour cet article;
- si seul `article.screening.json` existe, le screening est reutilise et le pipeline reprend a l'extraction detaillee si elle est autorisee;
- les PDF surlignes, `summary.csv` et `summary.xlsx` peuvent etre regeneres a partir des JSON existants.

Commande de reprise:

```powershell
review-extract .\pdf_input --out .\outputs
```

La console affiche la progression:

```text
Found 12 PDF(s) to process.
[1/12] article.pdf: reuse existing JSON: article.json
[1/12] article.pdf: done
[2/12] autre_article.pdf: extract PDF text
[2/12] autre_article.pdf: screen full paper
```

Pour forcer une nouvelle analyse OpenAI et ignorer les JSON existants:

```powershell
review-extract .\pdf_input --out .\outputs --force
```

## Tests

Les tests unitaires utilisent `unittest`, donc ils peuvent tourner sans `pytest`:

```powershell
python -B -m unittest discover -s tests -v
```

## API locale

```powershell
uvicorn review_extraction.api:app --reload
```

Puis téléverser un PDF:

```powershell
curl -X POST "http://127.0.0.1:8000/extract" -F "file=@paper.pdf" -F "output_dir=outputs"
```

## Architecture

```mermaid
flowchart TD
    A["PDF"] --> B["Extraction texte + pages"]
    B --> C["Agent extracteur"]
    B --> D["Agent validateur indépendant"]
    C --> E["Réponses initiales"]
    D --> F["Audit item par item"]
    E --> G["Fusion + arbitrage léger"]
    F --> G
    G --> H["JSON final + confidence + review_required"]
    G --> I["PDF surligné"]
```

Le validateur reçoit les passages et les réponses de l'extracteur, mais doit refaire l'analyse comme critique indépendant. Une révision humaine est exigée si les agents divergent, si la confiance est basse ou si les preuves sont insuffisantes.
