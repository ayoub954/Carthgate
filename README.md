# DIWANA TRACE AI

**Intelligence au service du contrôle commercial.**

De grandes activités commerciales peuvent être cachées derrière de nombreuses petites importations et ventes en ligne.
DIWANA TRACE AI aide la Douane à rassembler ces signaux, détecter les situations à vérifier, comprendre où concentrer
ses contrôles, puis transmettre les dossiers pertinents à Finance pour analyse.

Données → Analyse IA → Anomalie → Agent Douane → Vérification humaine → Transmission → Agent Finance → Analyse financière.

Données réelles uniquement (aucun mode démonstration). Une information absente est affichée comme
« Information non disponible » ou « Source non connectée ».

## Deux espaces séparés (contrôle d'accès côté serveur)

| Rôle | Espace | Routes serveur |
|---|---|---|
| `ROLE_DOUANE` | `/douane` — vue d'ensemble, investigation IA, anomalies et dossiers, conseiller IA, carte des contrôles, intelligence géographique, parcours intelligent, commerce en ligne, produits observés, dossiers transmis, rapports | `/api/douane/*` |
| `ROLE_FINANCE` | `/finance` — dossiers reçus, analyse financière, analyse économique, statistiques, rapports | `/api/finance/*` |
| `ROLE_ADMIN` | `/administration` — comptes, journal des accès, sources | `/api/admin/*` |

Toute autre combinaison renvoie **403** (tentative journalisée). Finance ne voit que les dossiers effectivement transmis.

## Lancer (Windows PowerShell, une commande par ligne)

Terminal 1 — serveur :
```powershell
cd backend
.\venv\Scripts\python -m uvicorn app.main:app --reload
```
Terminal 2 — interface :
```powershell
cd frontend
npm run dev          # http://localhost:5173
```
Si le port 8000 est déjà utilisé : lancer le serveur avec `--port 8010` puis, dans le terminal de l'interface,
`$env:DIWANA_API="http://127.0.0.1:8010"; npm run dev`.

## Comptes

Les rôles sont enregistrés sur le serveur (mot de passe haché). Convention : `prenom.nom@douane.com`, `prenom.nom@finance.com`.
```powershell
cd backend
.\venv\Scripts\python -m app.users create prenom.nom@douane.com ROLE_DOUANE --name "Prénom Nom"
.\venv\Scripts\python -m app.users list
.\venv\Scripts\python -m app.users password prenom.nom@douane.com
```
Un administrateur peut aussi créer et désactiver des comptes depuis l'espace Administration.

## Installation locale (première fois)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.\venv\Scripts\python -m app.pipeline      # téléchargement + analyse des données réelles (≈15–25 min)
cd ..\frontend
npm install
```

## Déclarations détaillées

La détection de fragmentation au niveau des opérations individuelles (petits envois répétés, points d'entrée, modes
mer / air / terre) nécessite un extrait autorisé des déclarations. Un agent Douane peut l'importer depuis la vue
d'ensemble (CSV ou Excel ; colonnes obligatoires : `declaration_date`, `hs_code`, `declared_value`). Sans cet extrait,
l'analyse porte sur les statistiques officielles (INS, Nations unies) et les observations commerciales publiques.

## Tests
```powershell
cd backend
.\venv\Scripts\python -m pytest -q
```

## Règles
Anomalie ≠ fraude · observation ≠ vente · corrélation ≠ preuve · projection ≠ certitude ·
pays de la marque ≠ pays de fabrication ≠ pays d'exportation ≠ pays de provenance ·
priorité élevée = priorité de vérification humaine · l'IA ne transmet jamais un dossier : seul un agent de la Douane le fait.
