import { fmt } from '../../api.js'
import { HBars, STATUS_COLORS, StackedBars, TimeChart } from '../../components/charts.jsx'
import { ChartCard, Seg, Select } from '../../components/ui.jsx'

export const GRANS = [['day', 'Jour'], ['week', 'Semaine'], ['month', 'Mois'], ['year', 'Année']]
const STATUS_FIN = { Transmis: 'var(--ai)', Reçu: 'var(--series-1)', 'En analyse': 'var(--warning)', Traité: 'var(--good)' }

export function FinanceFilters({ g, setG, f, setF, unit, setUnit, options }) {
  const set = (k) => (v) => setF({ ...f, [k]: v })
  return (
    <div className="filters sticky-filters">
      <Seg value={g} onChange={setG} options={GRANS} />
      <Select value={f.product} onChange={set('product')} options={options?.product || []} placeholder="Tous les produits" />
      <Select value={f.category} onChange={set('category')} options={options?.category || []} placeholder="Toutes les catégories" />
      <Select value={f.zone} onChange={set('zone')} options={options?.zone || []} placeholder="Toutes les zones" />
      <Select value={f.country} onChange={set('country')} options={options?.country || []} placeholder="Tous les pays" />
      <Select value={f.entry_point} onChange={set('entry_point')} options={options?.entry_point || []} placeholder="Tous les points d'entrée" />
      <Select value={f.status} onChange={set('status')} options={options?.status || []} placeholder="Tous les statuts" />
      {(options?.units || []).length > 1 && <Seg value={unit} onChange={setUnit} options={options.units.map((u) => [u, u === 'USD' ? 'Dollars' : 'Dinars'])} />}
    </div>
  )
}

/** Les dix graphiques métier de Finance. `only` restreint la liste (vue d'ensemble). */
export default function FinanceCharts({ a, only }) {
  const c = a.charts
  const u = a.unit
  const gl = GRANS.find(([k]) => k === a.granularity)?.[1].toLowerCase()
  const show = (k) => !only || only.includes(k)
  const src = 'Dossiers transmis par la Douane'
  return (
    <div className="grid g2">
      {show('amounts_time') && (
        <ChartCard title="Évolution des montants à vérifier" question="Comment évoluent les montants associés aux dossiers transmis ?" rows={c.amounts_time.rows} unit={u} kind="time" source={src}
          help={{ why: 'Pour suivre le volume financier que représentent les dossiers reçus.', shows: `La valeur des opérations concernées, par ${gl} de transmission (${fmt.unit(u)}).`, read: 'Une hausse signifie que la Douane transmet des dossiers portant sur des montants plus importants ; elle ne mesure pas des recettes.' }}>
          <TimeChart rows={c.amounts_time.rows} unit={u} />
        </ChartCard>
      )}
      {show('categories') && (
        <ChartCard title="Répartition par catégorie de produit" question="Quelles catégories concentrent les montants les plus importants ?" rows={c.categories.rows} unit={u} source={src}
          help={{ why: 'Pour concentrer l’analyse sur les familles de produits les plus exposées.', shows: 'La valeur des opérations concernées par catégorie.', read: 'Une catégorie très dominante indique une concentration à examiner en priorité.' }}>
          <HBars rows={c.categories.rows} unit={u} />
        </ChartCard>
      )}
      {show('zones') && (
        <ChartCard title="Répartition géographique" question="Quelles zones concentrent les dossiers transmis ?" rows={c.zones.rows} unit="dossiers" source={src}
          help={{ why: 'Pour situer géographiquement les dossiers reçus.', shows: 'Le nombre de dossiers par zone commerciale associée.', read: 'La zone est celle des commerces de la catégorie ou la destination déclarée ; c’est une indication, pas une localisation d’entreprise.' }}>
          <HBars rows={c.zones.rows} unit="dossiers" />
        </ChartCard>
      )}
      {show('monthly') && (
        <ChartCard title="Évolution mensuelle" question="Le nombre de dossiers augmente-t-il ?" rows={c.monthly.rows} unit="dossiers" kind="time" source={src}
          help={{ why: 'Pour anticiper la charge d’analyse.', shows: 'Le nombre de dossiers transmis chaque mois.', read: 'Une hausse durable peut nécessiter davantage de moyens d’analyse.' }}>
          <TimeChart rows={c.monthly.rows} unit="dossiers" />
        </ChartCard>
      )}
      {show('entry_points') && (
        <ChartCard title="Points d'entrée" question="Quels points d'entrée apparaissent le plus souvent dans les dossiers transmis ?" rows={c.entry_points.rows} unit="dossiers" emptyText={c.entry_points.message}
          help={{ why: 'Pour savoir par où entrent les marchandises des dossiers.', shows: "Le nombre de dossiers par port, aéroport ou passage terrestre.", read: 'Un point d’entrée récurrent peut justifier un échange avec la Douane.' }}>
          <HBars rows={c.entry_points.rows} unit="dossiers" />
        </ChartCard>
      )}
      {show('origins') && (
        <ChartCard title="Origine des produits" question="Quels pays ou régions apparaissent dans les dossiers analysés ?" rows={c.origins.rows} unit={u} source={src} countries
          help={{ why: 'Pour connaître les pays d’origine des flux concernés.', shows: 'La valeur des opérations concernées par pays d’origine.', read: '« Information non disponible » regroupe les dossiers dont l’origine n’est pas publiée.' }}>
          <HBars rows={c.origins.rows} unit={u} countries />
        </ChartCard>
      )}
      {show('priority') && (
        <ChartCard title="Niveaux de priorité" question="Quelle part des dossiers est prioritaire ?" rows={c.priority.rows} unit="dossiers" source={src}
          help={{ why: 'Pour ordonner le travail d’analyse.', shows: 'Le nombre de dossiers « Prioritaire » et « Anomalie à vérifier ».', read: 'Commencez par les dossiers prioritaires.' }}>
          <HBars rows={c.priority.rows} unit="dossiers" colorBy={STATUS_COLORS} />
        </ChartCard>
      )}
      {show('status') && (
        <ChartCard title="Dossiers par statut" question="Où en est le traitement des dossiers reçus ?" rows={c.status.rows} unit="dossiers" source={src}
          help={{ why: 'Pour suivre l’avancement du traitement.', shows: 'Le nombre de dossiers transmis, reçus, en analyse et traités.', read: 'Beaucoup de dossiers « Reçu » signalent un retard de prise en charge.' }}>
          <HBars rows={c.status.rows} unit="dossiers" colorBy={STATUS_FIN} />
        </ChartCard>
      )}
      {show('category_amount') && (
        <ChartCard title="Catégorie × montant" question="Dans chaque catégorie, quelle part des montants relève des dossiers prioritaires ?"
          rows={c.category_amount.rows.map((r) => ({ label: r.category, value: c.category_amount.levels.reduce((s, l) => s + (r[l] || 0), 0) }))} unit={u} source={src}
          help={{ why: 'Pour croiser importance financière et niveau de priorité.', shows: 'Les montants de chaque catégorie, découpés par niveau de priorité.', read: 'Une catégorie à la fois lourde et prioritaire mérite l’attention en premier.' }}>
          <StackedBars rows={c.category_amount.rows} keys={c.category_amount.levels} unit={u} />
        </ChartCard>
      )}
      {show('gaps_time') && (
        <ChartCard title="Évolution des écarts à vérifier" question="Les écarts potentiels signalés augmentent-ils ?" rows={c.gaps_time.rows} unit={u} kind="time" source={src}
          help={{ why: 'Pour suivre les écarts de valeur potentiels signalés par la Douane.', shows: 'La somme des écarts potentiels (valeur attendue − valeur déclarée) par période.', read: 'Un écart potentiel est une estimation à vérifier, jamais un montant dû.' }}>
          <TimeChart rows={c.gaps_time.rows} unit={u} />
        </ChartCard>
      )}
      {show('products') && (
        <ChartCard title="Produits concernés" question="Quels produits représentent les montants les plus importants ?" rows={c.products.rows} unit={u} source={src}
          help={{ why: 'Pour identifier les produits à analyser en premier.', shows: 'La valeur des opérations concernées par produit.', read: 'Croisez avec le niveau de priorité du dossier.' }}>
          <HBars rows={c.products.rows} unit={u} />
        </ChartCard>
      )}
    </div>
  )
}
